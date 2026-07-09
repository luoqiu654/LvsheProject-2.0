"""合同诊疗子路由：视觉 AI 流水线。

提供：
- POST /api/contract/visual-review  上传文档，启动视觉流水线（SSE 流式进度 + 最终结果）
- GET  /api/contract/preview/{review_id}  预览批注文档（返回独立 HTML 页面，支持新窗口打开）
- GET  /api/contract/download/{review_id}  下载批注后的 .docx 文件
- GET  /api/contract/summary-image/{review_id}  获取风险预警摘要图
- GET  /api/contract/reviews/{user_id}  列出用户历史审查记录
"""

from __future__ import annotations

import html
import json
import tempfile
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, StreamingResponse

from backend.core.contract_pipeline import contract_pipeline
from backend.core.llm_gateway import LLMGatewayError


router = APIRouter(prefix="/api/contract", tags=["合同诊疗"])

MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB
ALLOWED_EXT = {".docx", ".pdf"}


@router.post("/visual-review")
async def visual_review(
    file: UploadFile = File(...),
    user_id: str = Form(default="default_user"),
):
    """
    上传 Word/PDF 合同，启动视觉 AI 流水线。

    返回 SSE 事件流：
    - data: {"stage":"parse","status":"running","message":"...","progress":5}
    - ...
    - data: {"done":true,"result":{review_id, risk_points, summary, ...}}
    - data: {"error":"...","result":{...}}  (出错时)
    - data: [DONE]

    最终 result 字段包含：review_id、risk_points、summary、annotated_filename、
    summary_image_filename、各风险等级计数等。
    """

    # 校验文件
    if not file.filename:
        raise HTTPException(status_code=400, detail="缺少文件名")
    ext = Path(file.filename).suffix.lower()
    if ext not in ALLOWED_EXT:
        raise HTTPException(status_code=400, detail=f"仅支持 .docx 与 .pdf，收到 {ext}")

    content = await file.read()
    if len(content) == 0:
        raise HTTPException(status_code=400, detail="文件为空")
    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(status_code=413, detail=f"文件过大（{len(content)} bytes），最大支持 10MB")

    # 保存到临时文件供流水线读取
    with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as tmp:
        tmp.write(content)
        tmp_path = tmp.name

    async def generate():
        try:
            async for event in contract_pipeline.process_document_stream(
                file_path=tmp_path,
                filename=file.filename,
                user_id=user_id,
            ):
                yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
            yield "data: [DONE]\n\n"
        except LLMGatewayError as exc:
            yield f"data: {json.dumps({'error': str(exc)}, ensure_ascii=False)}\n\n"
            yield "data: [DONE]\n\n"
        except Exception as exc:
            yield f"data: {json.dumps({'error': f'服务端错误: {exc}'}, ensure_ascii=False)}\n\n"
            yield "data: [DONE]\n\n"
        finally:
            # 清理临时文件
            try:
                Path(tmp_path).unlink(missing_ok=True)
            except Exception:
                pass

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/preview/{review_id}", response_class=HTMLResponse)
async def contract_preview(
    review_id: str,
    user_id: Optional[str] = None,
):
    """
    预览批注文档。

    返回一个独立、带样式的 HTML 页面，可直接在浏览器新窗口/新标签页打开。
    页面包含：风险摘要面板 + 批注文档内容（红色高亮+批注）+ 风险摘要图。
    """
    review_dir = contract_pipeline.find_review_dir(review_id, user_id)
    if not review_dir:
        raise HTTPException(status_code=404, detail="审查记录不存在")

    meta = contract_pipeline.load_metadata(review_dir)
    if not meta:
        raise HTTPException(status_code=404, detail="审查元数据缺失")

    # 查找批注文档
    annotated_name = meta.get("annotated_filename") or f"annotated_{review_id}.docx"
    annotated_path = review_dir / annotated_name
    if not annotated_path.exists():
        # 兜底：查找目录内 annotated_*.docx
        candidates = list(review_dir.glob("annotated_*.docx"))
        annotated_path = candidates[0] if candidates else None

    doc_html = ""
    if annotated_path and annotated_path.exists():
        try:
            doc_html = _render_docx_to_html(annotated_path)
        except Exception as exc:
            doc_html = f"<p style='color:#b91c1c'>批注文档渲染失败：{html.escape(str(exc))}</p>"
    else:
        doc_html = "<p style='color:#888'>未找到批注文档文件。</p>"

    # 摘要图 URL
    summary_image_name = meta.get("summary_image_filename") or ""
    summary_image_html = ""
    if summary_image_name and (review_dir / summary_image_name).exists():
        summary_image_html = (
            f"<img class='summary-img' src='/api/contract/summary-image/{review_id}' "
            f"alt='风险预警摘要图' />"
        )

    # 风险摘要面板
    risk_points = meta.get("risk_points", [])
    risk_cards = "".join(_render_risk_card(r, i) for i, r in enumerate(risk_points, 1))

    title = html.escape(meta.get("original_filename") or "合同诊疗报告")
    created = html.escape(meta.get("created_at") or "")
    summary = html.escape(meta.get("summary") or "")

    html_page = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8" />
<meta name="viewport" content="width=device-width, initial-scale=1.0" />
<title>合同诊疗预览 - {title}</title>
<style>
  * {{ box-sizing: border-box; }}
  body {{ margin: 0; font-family: -apple-system, "Segoe UI", "PingFang SC", "Microsoft YaHei", sans-serif;
         background: #f3f4f6; color: #1f2937; }}
  .container {{ max-width: 960px; margin: 0 auto; padding: 24px 16px 80px; }}
  header {{ background: linear-gradient(135deg, #1e3a8a, #2563eb); color: #fff;
            padding: 24px; border-radius: 12px; margin-bottom: 20px; }}
  header h1 {{ margin: 0 0 8px; font-size: 22px; }}
  header .meta {{ font-size: 13px; opacity: 0.85; }}
  .summary-box {{ background: #fff; border-radius: 12px; padding: 20px; margin-bottom: 20px;
                  box-shadow: 0 1px 3px rgba(0,0,0,0.08); }}
  .summary-box h2 {{ margin: 0 0 12px; font-size: 16px; }}
  .stats {{ display: flex; gap: 12px; flex-wrap: wrap; margin: 12px 0; }}
  .stat {{ flex: 1; min-width: 100px; padding: 14px; border-radius: 10px; text-align: center; color: #fff; }}
  .stat.high {{ background: #dc2626; }}
  .stat.medium {{ background: #ea580c; }}
  .stat.low {{ background: #ca8a04; }}
  .stat .num {{ font-size: 26px; font-weight: 700; }}
  .stat .label {{ font-size: 12px; opacity: 0.9; }}
  .summary-img {{ width: 100%; max-width: 480px; border-radius: 10px; margin: 12px auto; display: block; }}
  .doc-section {{ background: #fff; border-radius: 12px; padding: 28px 32px; box-shadow: 0 1px 3px rgba(0,0,0,0.08); }}
  .doc-section h2 {{ margin: 0 0 16px; font-size: 16px; border-bottom: 2px solid #e5e7eb; padding-bottom: 10px; }}
  .doc-content p {{ margin: 0 0 8px; line-height: 1.8; font-size: 14px; }}
  .risk-card {{ border-left: 4px solid #ccc; background: #f9fafb; padding: 12px 16px;
               border-radius: 0 8px 8px 0; margin-bottom: 12px; }}
  .risk-card.high {{ border-color: #dc2626; background: #fef2f2; }}
  .risk-card.medium {{ border-color: #ea580c; background: #fff7ed; }}
  .risk-card.low {{ border-color: #ca8a04; background: #fefce8; }}
  .risk-card .title {{ font-weight: 600; margin-bottom: 6px; }}
  .risk-card .label {{ display:inline-block; font-size:11px; padding:2px 8px; border-radius:4px; color:#fff; margin-right:6px; }}
  .risk-card .label.high {{ background:#dc2626; }}
  .risk-card .label.medium {{ background:#ea580c; }}
  .risk-card .label.low {{ background:#ca8a04; }}
  .risk-card .clause {{ font-size: 13px; color:#374151; background:#fff; padding:6px 10px; border-radius:6px; margin:6px 0; }}
  .risk-card .desc {{ font-size: 13px; color:#4b5563; margin: 4px 0; }}
  .risk-card .sug {{ font-size: 13px; color:#15803d; margin-top: 4px; }}
  footer {{ text-align:center; color:#9ca3af; font-size:12px; margin-top:32px; }}
</style>
</head>
<body>
  <div class="container">
    <header>
      <h1>合同诊疗报告</h1>
      <div class="meta">文件：{title} · 生成时间：{created}</div>
    </header>

    <section class="summary-box">
      <h2>风险概览</h2>
      <div class="stats">
        <div class="stat high"><div class="num">{meta.get('high_risk_count', 0)}</div><div class="label">高风险</div></div>
        <div class="stat medium"><div class="num">{meta.get('medium_risk_count', 0)}</div><div class="label">中风险</div></div>
        <div class="stat low"><div class="num">{meta.get('low_risk_count', 0)}</div><div class="label">低风险</div></div>
      </div>
      <p style="font-size:14px;line-height:1.7;color:#374151;">{summary or '暂无摘要'}</p>
      {summary_image_html}
    </section>

    <section class="summary-box">
      <h2>风险点清单（共 {len(risk_points)} 项）</h2>
      {risk_cards or '<p style="color:#888">未识别到风险点。</p>'}
    </section>

    <section class="doc-section">
      <h2>批注文档内容</h2>
      <div class="doc-content">
        {doc_html}
      </div>
    </section>

    <footer>由 LvsheProject 合同诊疗视觉 AI 流水线生成 · GLM-OCR + GLM + GLM-Image</footer>
  </div>
</body>
</html>
"""
    return HTMLResponse(content=html_page)


@router.get("/download/{review_id}")
async def contract_download(
    review_id: str,
    user_id: Optional[str] = None,
):
    """下载批注后的 .docx 文件。"""
    review_dir = contract_pipeline.find_review_dir(review_id, user_id)
    if not review_dir:
        raise HTTPException(status_code=404, detail="审查记录不存在")

    meta = contract_pipeline.load_metadata(review_dir)
    annotated_name = (meta or {}).get("annotated_filename") or ""
    annotated_path = review_dir / annotated_name if annotated_name else None

    if not annotated_path or not annotated_path.exists():
        candidates = list(review_dir.glob("annotated_*.docx"))
        if not candidates:
            raise HTTPException(status_code=404, detail="批注文档不存在")
        annotated_path = candidates[0]
        annotated_name = annotated_path.name

    download_name = f"批注合同_{review_id}.docx"
    return FileResponse(
        path=str(annotated_path),
        filename=download_name,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    )


@router.get("/summary-image/{review_id}")
async def contract_summary_image(
    review_id: str,
    user_id: Optional[str] = None,
):
    """获取风险预警摘要图。"""
    review_dir = contract_pipeline.find_review_dir(review_id, user_id)
    if not review_dir:
        raise HTTPException(status_code=404, detail="审查记录不存在")

    meta = contract_pipeline.load_metadata(review_dir)
    image_name = (meta or {}).get("summary_image_filename") or ""
    image_path = review_dir / image_name if image_name else None

    if not image_path or not image_path.exists():
        candidates = list(review_dir.glob("summary_*.png"))
        if not candidates:
            raise HTTPException(status_code=404, detail="风险摘要图不存在")
        image_path = candidates[0]

    return FileResponse(path=str(image_path), media_type="image/png")


@router.get("/reviews/{user_id}")
async def list_reviews(user_id: str):
    """列出用户的历史审查记录。"""
    reviews = contract_pipeline.list_reviews(user_id)
    return {
        "ok": True,
        "user_id": user_id,
        "total": len(reviews),
        "reviews": reviews,
    }


# ========== 工具函数 ==========


def _render_docx_to_html(docx_path: Path) -> str:
    """将批注后的 docx 渲染为 HTML，保留高亮与颜色样式。"""
    from docx import Document
    from docx.enum.text import WD_COLOR_INDEX

    doc = Document(str(docx_path))
    parts: list[str] = []

    highlight_map = {
        WD_COLOR_INDEX.RED: "#fecaca",
        WD_COLOR_INDEX.YELLOW: "#fef08a",
        WD_COLOR_INDEX.GREEN: "#bbf7d0",
        WD_COLOR_INDEX.CYAN: "#a5f3fc",
        WD_COLOR_INDEX.PINK: "#fbcfe8",
    }

    for para in doc.paragraphs:
        if not para.text.strip():
            parts.append("<p>&nbsp;</p>")
            continue

        runs_html: list[str] = []
        for run in para.runs:
            if not run.text:
                continue
            styles: list[str] = []
            try:
                color = run.font.color
                if color and color.rgb:
                    styles.append(f"color:#{color.rgb}")
            except Exception:
                pass
            hl = run.font.highlight_color
            if hl and hl in highlight_map:
                styles.append(f"background:{highlight_map[hl]}")
            if run.font.bold:
                styles.append("font-weight:bold")
            if run.font.italic:
                styles.append("font-style:italic")
            style_attr = f' style="{";".join(styles)}"' if styles else ""
            runs_html.append(f"<span{style_attr}>{html.escape(run.text)}</span>")

        content = "".join(runs_html) if runs_html else html.escape(para.text)
        parts.append(f"<p>{content}</p>")

    return "\n".join(parts)


def _render_risk_card(risk: dict, idx: int) -> str:
    """渲染单个风险点卡片 HTML。"""
    level = (risk.get("risk_level") or "medium").lower()
    level_label = {"high": "高风险", "medium": "中风险", "low": "低风险"}.get(level, "中风险")
    risk_type = html.escape(str(risk.get("risk_type", "")))
    clause = html.escape(str(risk.get("clause_text", "")))
    desc = html.escape(str(risk.get("description", "")))
    sug = html.escape(str(risk.get("suggestion", "")))

    return f"""
    <div class="risk-card {level}">
      <div class="title">
        <span class="label {level}">{level_label}</span>
        #{idx} {risk_type}
      </div>
      <div class="clause">{clause}</div>
      <div class="desc">{desc}</div>
      <div class="sug">修改建议：{sug}</div>
    </div>
    """
