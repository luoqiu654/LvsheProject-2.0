"""
合同诊疗视觉 AI 流水线核心模块。

流水线流程：
1. 文档转图片（Word→PIL 渲染分页图片 / PDF→pdf2image，失败降级 pdfplumber）
2. 视觉识别（GLM-OCR 逐页识别文字并合并）
3. 文本诊断（GLM 文本模型分析风险，输出结构化 RiskPoint 列表）
4. 批注生成（ContractAnnotator 注入风险点生成红色高亮+批注的 .docx）
5. 摘要图生成（GLM-Image 生成风险预警可视化摘要图）

所有产物缓存到：output/contract_review/{user_id}/{review_id}/
"""

from __future__ import annotations

import io
import json
import re
import shutil
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, AsyncIterator, Optional

from backend.config import PROJECT_ROOT, settings
from backend.core.contract_annotator import (
    AnnotationResult,
    ContractAnnotator,
    RiskPoint,
    contract_annotator,
)
from backend.core.llm_gateway import LLMGatewayError, gateway


# ========== 数据结构 ==========

REVIEW_ROOT = settings.contract_output_path  # output/contract_review
MAX_PAGES_FOR_VISION = 20  # 单次视觉识别最多处理页数，避免大文档超时


@dataclass
class PipelineStage:
    """单个处理阶段状态。"""

    stage: str  # parse / vision / diagnose / annotate / image
    status: str  # pending / running / done / error / skipped
    message: str = ""
    progress: float = 0.0  # 0-100


@dataclass
class PipelineResult:
    """流水线最终结果。"""

    review_id: str
    user_id: str
    original_filename: str
    extracted_text: str = ""
    risk_points: list[dict[str, Any]] = field(default_factory=list)
    annotated_filename: str = ""
    annotated_path: str = ""
    summary_image_filename: str = ""
    summary_image_path: str = ""
    summary: str = ""
    stages: list[dict[str, Any]] = field(default_factory=list)
    high_risk_count: int = 0
    medium_risk_count: int = 0
    low_risk_count: int = 0
    success: bool = False
    error: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# ========== 流水线 ==========


class ContractPipeline:
    """
    合同诊疗视觉 AI 流水线。

    串联：视觉模型(GLM-OCR) → 文本模型(GLM) → 图像生成模型(GLM-Image) → 文档批注器。
    """

    def __init__(
        self,
        llm_gateway=gateway,
        annotator: ContractAnnotator = contract_annotator,
    ) -> None:
        self.gateway = llm_gateway
        self.annotator = annotator

    # ---- 公开入口 ----

    async def process_document_stream(
        self,
        file_path: str | Path,
        filename: str,
        user_id: str,
    ) -> AsyncIterator[dict[str, Any]]:
        """
        异步生成器：yield 进度事件，最后一个事件为最终结果。

        事件格式：
            {"stage": "parse", "status": "running", "message": "...", "progress": 10}
            ...
            {"done": True, "result": {...}}
            {"error": "..."}
        """
        review_id = self._make_review_id()
        result = PipelineResult(
            review_id=review_id,
            user_id=user_id,
            original_filename=filename,
        )
        stages: list[PipelineStage] = []

        def record(stage: PipelineStage) -> dict[str, Any]:
            stages.append(stage)
            return asdict(stage)

        try:
            # 校验网关可用
            if not self.gateway.is_available:
                raise LLMGatewayError("智谱 API Key 未配置，无法启动视觉流水线。")

            file_path = Path(file_path)
            ext = file_path.suffix.lower()
            if ext not in {".docx", ".pdf"}:
                raise ValueError(f"仅支持 .docx 与 .pdf 文件，收到 {ext}")

            # ===== 阶段 1：文档解析 → 图片 =====
            yield record(PipelineStage("parse", "running", "正在解析文档并转换为图片...", 5))
            try:
                if ext == ".pdf":
                    page_images, fallback_text = await self._pdf_to_images(file_path)
                else:
                    page_images, fallback_text = self._word_to_images(file_path)
            except Exception as exc:
                raise LLMGatewayError(f"文档解析失败：{exc}") from exc

            yield record(
                PipelineStage(
                    "parse",
                    "done",
                    f"已解析 {len(page_images)} 张页面图片" + ("（使用文本降级）" if not page_images else ""),
                    20,
                )
            )

            # ===== 阶段 2：视觉识别 =====
            yield record(PipelineStage("vision", "running", "视觉 AI 正在识别文档内容...", 25))
            extracted_text = ""
            if page_images:
                try:
                    extracted_text = await self._extract_text_via_vision(page_images)
                except Exception as exc:
                    # 视觉识别失败：降级使用直接提取的文本
                    extracted_text = fallback_text or self._extract_text_fallback(file_path)
                    yield record(
                        PipelineStage("vision", "error", f"视觉识别失败，已降级为文本提取：{exc}", 40)
                    )
            else:
                # PDF 无 poppler 等情况：直接使用文本
                extracted_text = fallback_text or self._extract_text_fallback(file_path)
                yield record(PipelineStage("vision", "skipped", "无页面图片，使用直接文本提取", 40))

            if not extracted_text.strip():
                raise LLMGatewayError("未能从文档中提取到任何文本内容。")

            result.extracted_text = extracted_text
            if stages[-1].status != "error" and stages[-1].status != "skipped":
                yield record(PipelineStage("vision", "done", "视觉识别完成", 40))

            # ===== 阶段 3：文本诊断 =====
            yield record(PipelineStage("diagnose", "running", "语言 AI 正在诊断风险条款...", 45))
            try:
                risks, summary = await self._diagnose_risks(extracted_text)
            except Exception as exc:
                raise LLMGatewayError(f"风险诊断失败：{exc}") from exc

            result.risk_points = [self._risk_to_dict(r) for r in risks]
            result.summary = summary
            result.high_risk_count = sum(1 for r in risks if r.risk_level == "high")
            result.medium_risk_count = sum(1 for r in risks if r.risk_level == "medium")
            result.low_risk_count = sum(1 for r in risks if r.risk_level == "low")
            yield record(
                PipelineStage(
                    "diagnose",
                    "done",
                    f"诊断完成，发现 {len(risks)} 个风险点（高 {result.high_risk_count}/中 {result.medium_risk_count}/低 {result.low_risk_count}）",
                    65,
                )
            )

            # ===== 阶段 4：生成批注文档 =====
            yield record(PipelineStage("annotate", "running", "正在生成批注文档...", 70))
            try:
                annotated_path, annotated_filename = await self._generate_annotated(
                    file_path, filename, risks, user_id, review_id
                )
            except Exception as exc:
                raise LLMGatewayError(f"批注文档生成失败：{exc}") from exc

            result.annotated_path = annotated_path
            result.annotated_filename = annotated_filename
            yield record(PipelineStage("annotate", "done", "批注文档已生成", 85))

            # ===== 阶段 5：生成风险摘要图 =====
            yield record(PipelineStage("image", "running", "图像生成 AI 正在生成风险预警摘要图...", 88))
            summary_image_path = ""
            summary_image_filename = ""
            try:
                summary_image_path, summary_image_filename = await self._generate_summary_image(
                    risks, summary, user_id, review_id
                )
            except Exception as exc:
                # 摘要图生成失败不阻断整体流程
                yield record(PipelineStage("image", "error", f"摘要图生成失败：{exc}", 95))

            result.summary_image_path = summary_image_path
            result.summary_image_filename = summary_image_filename
            if summary_image_path:
                yield record(PipelineStage("image", "done", "风险摘要图已生成", 95))

            # ===== 收尾：保存元数据 =====
            result.stages = [asdict(s) for s in stages]
            result.success = True
            self._save_metadata(result, user_id, review_id)

            yield {"done": True, "result": result.to_dict()}

        except Exception as exc:
            result.error = str(exc)
            result.stages = [asdict(s) for s in stages]
            result.success = False
            try:
                self._save_metadata(result, user_id, review_id)
            except Exception:
                pass
            yield {"error": str(exc), "result": result.to_dict()}

    # ---- 文档转图片 ----

    def _word_to_images(self, file_path: Path) -> tuple[list[bytes], str]:
        """
        Word → 图片：用 python-docx 读取段落，再用 PIL 渲染为分页图片。

        若 unstructured 可用则优先使用其解析（结构更完整）。
        返回 (页面图片字节列表, 直接提取的文本)。
        """
        text = self._extract_word_text(file_path)
        if not text.strip():
            return [], ""
        images = self._render_text_to_images(text)
        return images, text

    def _extract_word_text(self, file_path: Path) -> str:
        """优先 unstructured，降级 python-docx。"""
        # 优先 unstructured
        try:
            from backend.utils.document_parser import document_parser

            parsed = document_parser._parse_docx_smart(file_path)
            if parsed.text and parsed.text.strip():
                return parsed.text
        except Exception:
            pass

        # 降级 python-docx
        from docx import Document

        doc = Document(str(file_path))
        paragraphs = [p.text for p in doc.paragraphs if p.text.strip()]
        return "\n".join(paragraphs)

    async def _pdf_to_images(self, file_path: Path) -> tuple[list[bytes], str]:
        """
        PDF → 图片：优先 pdf2image（需 poppler），失败降级 pdfplumber 提取文本。

        返回 (页面图片字节列表, 直接提取的文本)。无图片时列表为空。
        """
        # 优先 pdf2image
        try:
            from pdf2image import convert_from_path

            pil_images = convert_from_path(str(file_path), dpi=150)
            images: list[bytes] = []
            for img in pil_images[:MAX_PAGES_FOR_VISION]:
                buf = io.BytesIO()
                img.save(buf, format="PNG")
                images.append(buf.getvalue())
            # 同时提取一份文本作为降级兜底
            fallback = self._extract_text_fallback(file_path)
            return images, fallback
        except Exception:
            # 降级 pdfplumber
            text = self._extract_text_fallback(file_path)
            return [], text

    def _extract_text_fallback(self, file_path: Path) -> str:
        """直接提取文本（pdfplumber / python-docx），作为视觉识别的降级方案。"""
        ext = file_path.suffix.lower()
        try:
            if ext == ".pdf":
                import pdfplumber

                parts: list[str] = []
                with pdfplumber.open(str(file_path)) as pdf:
                    for page in pdf.pages:
                        t = page.extract_text()
                        if t:
                            parts.append(t)
                return "\n\n".join(parts)
            elif ext == ".docx":
                return self._extract_word_text(file_path)
        except Exception:
            pass
        return ""

    def _render_text_to_images(self, text: str) -> list[bytes]:
        """将纯文本渲染为 A4 分页 PNG 图片（每页约 42 行）。"""
        from PIL import Image, ImageDraw, ImageFont

        font = self._load_cjk_font(size=20)
        # 行宽限制（按字符数粗略估算，中文约 38 字/行）
        wrapped_lines: list[str] = []
        for raw in text.split("\n"):
            if not raw.strip():
                wrapped_lines.append("")
                continue
            for i in range(0, max(len(raw), 1), 38):
                wrapped_lines.append(raw[i : i + 38])

        lines_per_page = 42
        pages = [
            wrapped_lines[i : i + lines_per_page]
            for i in range(0, len(wrapped_lines), lines_per_page)
        ]

        images: list[bytes] = []
        for page in pages[:MAX_PAGES_FOR_VISION]:
            img = Image.new("RGB", (1240, 1754), "white")  # ~A4 @150dpi
            draw = ImageDraw.Draw(img)
            y = 50
            for line in page:
                draw.text((50, y), line, fill="black", font=font)
                y += 30
            buf = io.BytesIO()
            img.save(buf, format="PNG")
            images.append(buf.getvalue())
        return images

    def _load_cjk_font(self, size: int = 20):
        """加载支持中文的字体（Windows 优先微软雅黑/黑体，Linux 回退文泉驿）。"""
        from PIL import ImageFont

        candidates = [
            "C:/Windows/Fonts/msyh.ttc",
            "C:/Windows/Fonts/msyh.ttf",
            "C:/Windows/Fonts/simhei.ttf",
            "C:/Windows/Fonts/simsun.ttc",
            "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc",
            "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
        ]
        for path in candidates:
            try:
                return ImageFont.truetype(path, size)
            except Exception:
                continue
        return ImageFont.load_default()

    # ---- 视觉识别 ----

    async def _extract_text_via_vision(self, page_images: list[bytes]) -> str:
        """逐页调用 GLM-OCR 识别文字，合并结果。"""
        prompt = "请完整提取这份合同文档中的所有文字内容，保持原有条款编号和结构。只输出识别到的文字，不要添加解释。"
        parts: list[str] = []
        for idx, img_bytes in enumerate(page_images):
            try:
                text = await self.gateway.chat_with_vision(
                    image=img_bytes,
                    prompt=prompt,
                    max_tokens=4096,
                )
                if text:
                    parts.append(text.strip())
            except Exception:
                # 单页识别失败跳过，继续其他页
                continue
        return "\n\n".join(parts)

    # ---- 文本诊断 ----

    async def _diagnose_risks(self, contract_text: str) -> tuple[list[RiskPoint], str]:
        """调用 GLM 文本模型诊断风险，返回结构化 RiskPoint 列表与摘要。"""
        # 截断过长文本，避免超出上下文
        truncated = contract_text[:8000]

        system = (
            "你是一位资深的中国合同法律审查专家，精通《民法典》合同编及相关法律法规。"
            "你的任务是识别合同中的风险条款并给出专业修改建议。"
            "请严格按要求的 JSON 格式输出，不要输出任何 JSON 之外的内容。"
        )
        user = (
            "请审查以下合同文本，识别其中的风险条款（如违约责任不对等、付款条件模糊、"
            "知识产权归属不清、保密条款缺失、管辖条款不利、自动续约、单方解除权等）。\n\n"
            "请以严格的 JSON 格式返回，不要包含 markdown 代码块标记，格式如下：\n"
            "{\n"
            '  "risks": [\n'
            "    {\n"
            '      "id": "risk-1",\n'
            '      "clause_text": "问题条款原文摘录",\n'
            '      "risk_level": "high",\n'
            '      "risk_type": "风险类型",\n'
            '      "description": "风险说明",\n'
            '      "suggestion": "修改建议"\n'
            "    }\n"
            "  ],\n"
            '  "summary": "整体审查结论摘要"\n'
            "}\n\n"
            "风险等级：high=高风险（可能导致重大损失/违法）、medium=中风险（需修改）、low=低风险（建议优化）。\n"
            "至少识别 2 个风险点，若合同过于简短无法识别风险则返回空 risks 数组并在 summary 中说明。\n\n"
            f"合同文本：\n{truncated}"
        )

        response = await self.gateway.chat(
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            model=settings.active_model_decision,
            temperature=0.2,
            max_tokens=4096,
        )
        raw = self.gateway.extract_text(response)

        risks, summary = self._parse_risk_json(raw)
        return risks, summary

    def _parse_risk_json(self, raw: str) -> tuple[list[RiskPoint], str]:
        """从 LLM 输出中解析 JSON 风险点，兼容 markdown 代码块包裹。"""
        text = raw.strip()
        # 去除可能的 markdown 代码块标记
        if text.startswith("```"):
            text = re.sub(r"^```(?:json)?\s*", "", text)
            text = re.sub(r"\s*```$", "", text)

        # 尝试提取第一个 JSON 对象
        match = re.search(r"\{[\s\S]*\}", text)
        if match:
            text = match.group(0)

        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            # 解析失败，返回空结果
            return [], raw[:300]

        risks: list[RiskPoint] = []
        for idx, item in enumerate(data.get("risks", []), start=1):
            level = str(item.get("risk_level", "medium")).lower().strip()
            if level not in {"high", "medium", "low"}:
                level = "medium"
            risks.append(
                RiskPoint(
                    id=str(item.get("id") or f"risk-{idx}"),
                    clause_text=str(item.get("clause_text", ""))[:500],
                    risk_level=level,
                    risk_type=str(item.get("risk_type", "未分类"))[:60],
                    description=str(item.get("description", "")),
                    suggestion=str(item.get("suggestion", "")),
                )
            )

        summary = str(data.get("summary", ""))
        return risks, summary

    # ---- 批注文档 ----

    async def _generate_annotated(
        self,
        original_path: Path,
        original_filename: str,
        risks: list[RiskPoint],
        user_id: str,
        review_id: str,
    ) -> tuple[str, str]:
        """
        生成批注文档并归档到 review 子目录。

        返回 (最终批注文档绝对路径, 文件名)。
        """
        # 1. 读取原始文件字节
        original_bytes = original_path.read_bytes()

        # 2. 用 annotator 保存原始文件到用户隔离目录（annotator 安全检查要求文件在 user_dir 下）
        saved_original_path = self.annotator.save_original(
            file_bytes=original_bytes,
            original_filename=original_filename,
            user_id=user_id,
        )

        # 3. 生成批注文档（annotator 写入 user_dir）
        annotation_result: AnnotationResult = self.annotator.annotate_contract(
            original_path=saved_original_path,
            risk_points=risks,
            user_id=user_id,
        )
        if not annotation_result.success:
            raise RuntimeError(annotation_result.error_message or "批注生成失败")

        # 4. 归档到 review 子目录
        review_dir = self._get_review_dir(user_id, review_id)
        annotated_src = Path(annotation_result.annotated_path)
        annotated_dst = review_dir / f"annotated_{review_id}.docx"
        shutil.copy2(annotated_src, annotated_dst)

        # 同时归档原始文件
        original_dst = review_dir / f"original_{review_id}{Path(original_filename).suffix}"
        shutil.copy2(saved_original_path, original_dst)

        return str(annotated_dst), annotated_dst.name

    # ---- 摘要图 ----

    async def _generate_summary_image(
        self,
        risks: list[RiskPoint],
        summary: str,
        user_id: str,
        review_id: str,
    ) -> tuple[str, str]:
        """
        调用 GLM-Image 生成风险预警可视化摘要图，归档到 review 子目录。

        返回 (最终图片绝对路径, 文件名)。
        """
        high = sum(1 for r in risks if r.risk_level == "high")
        medium = sum(1 for r in risks if r.risk_level == "medium")
        low = sum(1 for r in risks if r.risk_level == "low")

        prompt = (
            "生成一张合同风险预警摘要图：深色商务背景，中央显示'合同风险审查报告'标题，"
            f"下方用三个数据卡片展示'高风险 {high}'、'中风险 {medium}'、'低风险 {low}'，"
            "配色使用红/橙/黄三色区分，整体风格专业简洁，适合作为报告封面。"
        )

        image_paths = await self.gateway.generate_image(
            prompt=prompt,
            size="1024x1024",
            n=1,
            user_id=user_id,
        )
        if not image_paths:
            raise RuntimeError("图像生成模型未返回图片。")

        # 归档到 review 子目录
        review_dir = self._get_review_dir(user_id, review_id)
        src = Path(image_paths[0])
        dst = review_dir / f"summary_{review_id}.png"
        shutil.copy2(src, dst)
        return str(dst), dst.name

    # ---- 元数据 / 目录管理 ----

    def _make_review_id(self) -> str:
        return f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}"

    def _get_review_dir(self, user_id: str, review_id: str) -> Path:
        """获取/创建 review 子目录：output/contract_review/{user_id}/{review_id}/"""
        safe_user = re.sub(r"[^a-zA-Z0-9_\-]", "_", user_id) or "anonymous"
        review_dir = REVIEW_ROOT / safe_user / review_id
        review_dir.mkdir(parents=True, exist_ok=True)
        return review_dir

    def _save_metadata(self, result: PipelineResult, user_id: str, review_id: str) -> None:
        """保存审查元数据 metadata.json。"""
        review_dir = self._get_review_dir(user_id, review_id)
        meta = {
            "review_id": review_id,
            "user_id": user_id,
            "original_filename": result.original_filename,
            "created_at": datetime.now().isoformat(),
            "success": result.success,
            "error": result.error,
            "summary": result.summary,
            "risk_count": len(result.risk_points),
            "high_risk_count": result.high_risk_count,
            "medium_risk_count": result.medium_risk_count,
            "low_risk_count": result.low_risk_count,
            "annotated_filename": result.annotated_filename,
            "summary_image_filename": result.summary_image_filename,
            "risk_points": result.risk_points,
        }
        (review_dir / "metadata.json").write_text(
            json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    # ---- 查询 ----

    def find_review_dir(self, review_id: str, user_id: Optional[str] = None) -> Optional[Path]:
        """
        根据 review_id 查找审查目录。

        优先在指定 user_id 目录下查找，找不到则全局搜索（review_id 含 uuid 不可猜测）。
        """
        if user_id:
            safe_user = re.sub(r"[^a-zA-Z0-9_\-]", "_", user_id) or "anonymous"
            candidate = REVIEW_ROOT / safe_user / review_id
            if candidate.exists():
                return candidate

        # 全局搜索
        if REVIEW_ROOT.exists():
            for user_dir in REVIEW_ROOT.iterdir():
                if not user_dir.is_dir():
                    continue
                candidate = user_dir / review_id
                if candidate.exists():
                    return candidate
        return None

    def load_metadata(self, review_dir: Path) -> Optional[dict[str, Any]]:
        meta_path = review_dir / "metadata.json"
        if not meta_path.exists():
            return None
        try:
            return json.loads(meta_path.read_text(encoding="utf-8"))
        except Exception:
            return None

    def list_reviews(self, user_id: str) -> list[dict[str, Any]]:
        """列出用户的历史审查记录。"""
        safe_user = re.sub(r"[^a-zA-Z0-9_\-]", "_", user_id) or "anonymous"
        user_root = REVIEW_ROOT / safe_user
        if not user_root.exists():
            return []
        reviews: list[dict[str, Any]] = []
        for review_dir in sorted(user_root.iterdir(), reverse=True):
            if not review_dir.is_dir():
                continue
            meta = self.load_metadata(review_dir)
            if meta:
                reviews.append(meta)
            else:
                reviews.append(
                    {
                        "review_id": review_dir.name,
                        "user_id": user_id,
                        "original_filename": "",
                        "created_at": "",
                        "success": False,
                        "summary": "",
                        "risk_count": 0,
                        "high_risk_count": 0,
                        "medium_risk_count": 0,
                        "low_risk_count": 0,
                        "annotated_filename": "",
                        "summary_image_filename": "",
                        "risk_points": [],
                    }
                )
        return reviews

    # ---- 工具 ----

    @staticmethod
    def _risk_to_dict(risk: RiskPoint) -> dict[str, Any]:
        return {
            "id": risk.id,
            "clause_text": risk.clause_text,
            "risk_level": risk.risk_level,
            "risk_type": risk.risk_type,
            "description": risk.description,
            "suggestion": risk.suggestion,
        }


# 全局实例
contract_pipeline = ContractPipeline()
