"""法庭多 Agent 子类（v3.3 专家会诊重构）。

将原 ``CourtSimulator`` 单类拆分为 1 主 agent + 3 子 agent 架构：
- ``CourtSubAgent``：基类，具备 RAG 检索 + skill 调用能力
- ``PlaintiffAgent``：原告子 agent
- ``DefendantAgent``：被告子 agent
- ``JudgeAgent``：法官子 agent（含追问决策 / 证据梳理 / 判决生成 / 打回检查）

设计要点：
1. ``speak`` / ``answer_question`` 流式 yield ``(kind, text)``，kind 为 'reasoning'/'content'，不混。
2. RAG 检索超时 5s 返回空串，skill 调用异常忽略，均不阻塞主流程。
3. 判决修复"LLM 服务不可用"误导文案：
   - LLM 真正调用失败（LLMGatewayError）→ "LLM 调用失败，请检查网络和 API 配置"
   - LLM 返回内容但 JSON 解析失败 → 从自由文本提取判决（不用 fallback）
4. 模型名从 ``multi_agents`` 模块导入（与 config 中 default_llm_model / chat_models 一致），不硬编码。
"""
from __future__ import annotations

import asyncio
import json
import re
from dataclasses import dataclass, field
from typing import Any, AsyncGenerator, Optional

from backend.core.llm_gateway import LLMGateway, LLMGatewayError
from backend.core.rag import LegalRAG
from backend.core.skills import SkillRegistry
# 复用 multi_agents.py 的角色 prompt 与模型常量（值与 config 中模型清单一致，不在此硬编码）
from backend.core.multi_agents import (
    MODEL_DECISION,
    MODEL_SPEECH,
    MODEL_VERDICT,
    SYSTEM_DEFENDANT,
    SYSTEM_JUDGE,
    SYSTEM_PLAINTIFF,
    UNCLEAR_PATTERNS,
)


# ========== 数据结构 ==========


@dataclass
class EvidenceItem:
    """本案所需的关键证据项（法官主动梳理）。"""

    name: str              # 证据名称，如"合同原件"
    why_key: str           # 为何关键，如"证明合同关系成立"
    target_party: str      # 向谁确认：'user' / 'plaintiff' / 'defendant'


@dataclass
class Verdict:
    """法官判决（结构化）。

    注意：``reasoning`` 不再写"LLM 服务不可用"等误导文案。
    """

    winner: str             # "原告胜诉" / "被告胜诉" / "部分支持" / "无法判断"
    reasoning: str          # 判决理由（非"LLM 服务不可用"误导文案）
    full_text: str          # 完整判决书文本
    compensation: str = ""  # 赔偿/责任（可选）


# ========== 基类 ==========


@dataclass
class CourtSubAgent:
    """法庭子 agent 基类。

    所有子 agent 共享 RAG 检索 + skill 调用 + 流式发言能力。
    子类通过 ``_system_prompt`` 属性提供角色专属 system prompt。
    """

    role: str                          # "plaintiff" / "defendant" / "judge"
    role_label: str                    # "原告" / "被告" / "法官"
    gateway: LLMGateway
    rag: Optional[LegalRAG] = None
    skill_registry: Optional[SkillRegistry] = None
    memory: list = field(default_factory=list)   # 本轮庭审对话历史

    # ---------- 角色专属 system prompt（子类覆盖）----------

    @property
    def _system_prompt(self) -> str:
        """子类覆盖：返回角色专属的 system prompt 基础文本。"""
        return ""

    # ---------- 流式发言 ----------

    async def speak(
        self,
        context: str,
        case: str,
        history: list[dict],
        temperature: float = 0.4,
    ) -> AsyncGenerator[tuple[str, str], None]:
        """流式发言，yield ``(kind, text)``，kind 为 'reasoning'/'content'。

        1. 调用 ``_retrieve_law_context`` 自主检索相关法律条文（RAG，超时 5s）
        2. 构建 system_prompt = 基础角色 prompt + 检索到的法律条文
        3. 调用 ``gateway.chat_stream_with_reasoning`` 流式生成
        4. 流式结束后若 content 为空但 reasoning 非空，yield 一次 ('content', reasoning) 作 fallback
        """
        law_context = await self._retrieve_law_context(f"{context} {case}")
        messages = self._build_speak_messages(context, case, history, law_context)

        content_acc = ""
        reasoning_acc = ""

        try:
            async for kind, text in self.gateway.chat_stream_with_reasoning(
                messages=messages,
                model=MODEL_SPEECH,
                temperature=temperature,
                max_tokens=1000,
            ):
                if kind == "reasoning":
                    reasoning_acc += text
                    yield ("reasoning", text)
                else:  # content
                    content_acc += text
                    yield ("content", text)
        except LLMGatewayError:
            if not content_acc:
                yield ("content", f"（{self.role_label}暂无回应，LLM 调用失败）")

        # content 为空但 reasoning 非空，回退用 reasoning 作为发言
        if not content_acc and reasoning_acc:
            yield ("content", reasoning_acc)

    async def answer_question(
        self,
        question: str,
        case: str,
        history: list[dict],
    ) -> AsyncGenerator[tuple[str, str], None]:
        """回答法官追问，必须正面回答（不逃避）。同 speak 但用追问专用 prompt。"""
        law_context = await self._retrieve_law_context(question)
        messages = self._build_answer_messages(question, case, history, law_context)

        content_acc = ""
        reasoning_acc = ""

        try:
            async for kind, text in self.gateway.chat_stream_with_reasoning(
                messages=messages,
                model=MODEL_SPEECH,
                temperature=0.5,
                max_tokens=700,
            ):
                if kind == "reasoning":
                    reasoning_acc += text
                    yield ("reasoning", text)
                else:  # content
                    content_acc += text
                    yield ("content", text)
        except LLMGatewayError:
            if not content_acc:
                yield ("content", f"（{self.role_label}暂无回应，LLM 调用失败）")

        if not content_acc and reasoning_acc:
            yield ("content", reasoning_acc)

    # ---------- RAG 检索 ----------

    async def _retrieve_law_context(self, query: str) -> str:
        """调用 ``LegalRAG.search(query, top_k=3)``，返回拼接条文文本。

        异常或超时 5s 返回空串（不阻塞流程）。
        """
        if self.rag is None:
            return ""
        try:
            results, _transformed, _hyde = await asyncio.wait_for(
                self.rag.search(query, top_k=3),
                timeout=5.0,
            )
        except asyncio.TimeoutError:
            return ""
        except Exception:
            return ""

        if not results:
            return ""

        lines: list[str] = []
        for item in results:
            text = (getattr(item, "enriched_text", "") or getattr(item, "text", "")).strip()
            if not text:
                continue
            source = getattr(item, "source", "法律知识库")
            lines.append(f"【来源：{source}】\n{text}")
        return "\n\n".join(lines)

    # ---------- skill 调用（可选，异常忽略）----------

    async def _call_skill(self, skill_name: str, input_data: str) -> str:
        """可选 skill 调用，异常忽略，返回空串表示未调用或失败。"""
        if self.skill_registry is None:
            return ""
        try:
            execute = getattr(self.skill_registry, "execute", None)
            if execute is None:
                return ""
            result = await execute(skill_name, input_data)
            # SkillExecutionResult 或字符串
            if hasattr(result, "output_text"):
                return getattr(result, "output_text", "") or ""
            return str(result) if result else ""
        except Exception:
            return ""

    # ---------- 不清楚检测 ----------

    def _detect_unclear(self, text: str) -> bool:
        """检测回答是否含'不清楚/不知道/不了解/不记得'等关键词。"""
        if not text:
            return False
        return any(pattern in text for pattern in UNCLEAR_PATTERNS)

    # ---------- 消息构建 ----------

    def _build_speak_messages(
        self,
        context: str,
        case: str,
        history: list[dict],
        law_context: str,
    ) -> list[dict]:
        """构建 LLM messages（system + user，history 折叠进 user 文本）。"""
        system_content = self._system_prompt
        if law_context:
            system_content += "\n\n【相关法律条文（RAG 检索）】\n" + law_context

        history_text = self._format_history(history)
        user_content = (
            f"{context}\n\n"
            f"案件描述：\n{case}\n\n"
            f"之前辩论记录：\n{history_text}\n\n"
            f"请作为{self.role_label}代理人发言。"
        )
        return [
            {"role": "system", "content": system_content},
            {"role": "user", "content": user_content},
        ]

    def _build_answer_messages(
        self,
        question: str,
        case: str,
        history: list[dict],
        law_context: str,
    ) -> list[dict]:
        """构建追问回答专用 messages，强调正面回答法官追问。"""
        system_content = self._system_prompt
        if law_context:
            system_content += "\n\n【相关法律条文（RAG 检索）】\n" + law_context

        history_text = self._format_history(history)
        user_content = (
            f"法官追问：\n{question}\n\n"
            f"案件描述：\n{case[:500]}\n\n"
            f"之前辩论记录：\n{history_text[:600]}\n\n"
            f"请作为{self.role_label}代理人正面回答法官的追问：\n"
            f"1. 直接回应法官的问题，不得回避\n"
            f"2. 如有相关证据，说明证据内容\n"
            f"3. 如确无相关证据或确实不清楚，明确表示\"不清楚此事，需要当事人确认\"\n"
            f"4. 不得含糊其辞、不得顾左右而言他\n"
        )
        return [
            {"role": "system", "content": system_content},
            {"role": "user", "content": user_content},
        ]

    @staticmethod
    def _format_history(history: list[dict]) -> str:
        """格式化已有辩论记录，供 prompt 使用。"""
        if not history:
            return "暂无（首轮陈述）"
        role_labels = {
            "plaintiff": "原告",
            "defendant": "被告",
            "judge": "法官",
            "chief_judge": "审判长",
            "user": "当事人",
            "verdict": "判决",
        }
        lines: list[str] = []
        for item in history:
            if not isinstance(item, dict):
                continue
            role = str(item.get("role", ""))
            content = str(item.get("content", ""))
            if not content:
                continue
            label = role_labels.get(role, role or "发言")
            lines.append(f"{label}：{content[:500]}")
        return "\n".join(lines) if lines else "暂无（首轮陈述）"


# ========== 原告子 agent ==========


class PlaintiffAgent(CourtSubAgent):
    """原告子 agent。

    使用 ``SYSTEM_PLAINTIFF``，增强提示：必须基于事实和证据陈述，可引用法律条文。
    """

    def __init__(
        self,
        gateway: LLMGateway,
        rag: Optional[LegalRAG] = None,
        skill_registry: Optional[SkillRegistry] = None,
    ) -> None:
        super().__init__(
            role="plaintiff",
            role_label="原告",
            gateway=gateway,
            rag=rag,
            skill_registry=skill_registry,
        )

    @property
    def _system_prompt(self) -> str:
        return (
            SYSTEM_PLAINTIFF
            + "\n5. 必须基于事实和证据陈述，引用相关法律条文支撑主张"
        )


# ========== 被告子 agent ==========


class DefendantAgent(CourtSubAgent):
    """被告子 agent。

    使用 ``SYSTEM_DEFENDANT``，增强提示：必须针对原告主张答辩，可引用法律条文。
    """

    def __init__(
        self,
        gateway: LLMGateway,
        rag: Optional[LegalRAG] = None,
        skill_registry: Optional[SkillRegistry] = None,
    ) -> None:
        super().__init__(
            role="defendant",
            role_label="被告",
            gateway=gateway,
            rag=rag,
            skill_registry=skill_registry,
        )

    @property
    def _system_prompt(self) -> str:
        return (
            SYSTEM_DEFENDANT
            + "\n5. 必须针对原告主张进行答辩，引用相关法律条文支撑抗辩"
        )


# ========== 法官子 agent ==========


class JudgeAgent(CourtSubAgent):
    """法官子 agent。

    使用 ``SYSTEM_JUDGE``，额外具备：
    - ``decide_inquiry``：非流式 JSON 决策是否追问
    - ``generate_evidence_inquiry``：梳理关键证据清单
    - ``render_verdict``：生成最终判决（修复"LLM 服务不可用"误导文案）
    - ``check_rebuttal``：判决打回检查
    """

    # 用户明确表示"不知道"的关键词（触发证据不足判决）
    _USER_UNKNOWN_PATTERNS = (
        "不知道", "不清楚", "无法确认", "记不清", "不记得", "无从得知", "确实没有",
    )
    # 端水判决关键词
    _DUANSHUI_PATTERNS = (
        "各50%", "各50％", "50%对50%", "50％对50％", "各占50", "一半一半",
        "各打五十大板", "各承担50",
    )

    def __init__(
        self,
        gateway: LLMGateway,
        rag: Optional[LegalRAG] = None,
        skill_registry: Optional[SkillRegistry] = None,
    ) -> None:
        super().__init__(
            role="judge",
            role_label="法官",
            gateway=gateway,
            rag=rag,
            skill_registry=skill_registry,
        )
        # 记录用户是否明确表示"不知道"，供 check_rebuttal 判断
        self._user_said_unknown: bool = False

    @property
    def _system_prompt(self) -> str:
        return SYSTEM_JUDGE

    # ---------- 追问决策 ----------

    async def decide_inquiry(
        self,
        case: str,
        history: list[dict],
        rounds_so_far: int,
    ) -> dict:
        """非流式 JSON 决策：是否追问、追问谁、问什么。

        返回 ``{should_ask: bool, target: str, question: str}``。
        target 为 'plaintiff' / 'defendant' / 'user' / 'both'。
        异常返回 ``{should_ask: False, target: "", question: ""}``。
        """
        try:
            prompt = self._inquiry_decision_prompt(case, history, rounds_so_far)
            response = await self.gateway.chat(
                messages=[
                    {"role": "system", "content": SYSTEM_JUDGE},
                    {"role": "user", "content": prompt},
                ],
                model=MODEL_DECISION,
                temperature=0.2,
                max_tokens=600,
            )
            text = self.gateway.extract_text(response)
            return self._parse_inquiry_decision(text)
        except Exception:
            return {"should_ask": False, "target": "", "question": ""}

    def _inquiry_decision_prompt(
        self,
        case: str,
        history: list[dict],
        rounds_so_far: int,
    ) -> str:
        history_text = self._format_history(history)
        return (
            f"你是中立法官，正在审理第 {rounds_so_far} 轮辩论。请判断是否需要追问。\n\n"
            f"案件描述：\n{case[:600]}\n\n"
            f"之前辩论记录：\n{history_text[:800]}\n\n"
            f"【判断原则】\n"
            f"- 如果存在实质性疑点（证据链断裂、事实矛盾、法律适用争议、关键证据缺失），追问\n"
            f"- 如果本轮已充分辩论、无实质疑点，不追问\n"
            f"- 不要为了追问而追问，但也不要放过真正的疑点\n"
            f"- 你是犀利法官，发现漏洞就要追问，不和稀泥\n\n"
            f"请严格按以下 JSON 格式输出（不要输出其他文字、不要 markdown 代码块）：\n"
            f'{{\n'
            f'  "should_ask": true 或 false,\n'
            f'  "question": "追问的问题（should_ask=true 时必填，要犀利、一针见血）",\n'
            f'  "target": "plaintiff" 或 "defendant" 或 "user" 或 "both"\n'
            f'}}'
        )

    def _parse_inquiry_decision(self, text: str) -> dict:
        raw = text.strip()
        if raw.startswith("```"):
            raw = re.sub(r"^```(?:json)?", "", raw, flags=re.IGNORECASE).strip()
            raw = re.sub(r"```$", "", raw).strip()
        match = re.search(r"\{.*\}", raw, flags=re.DOTALL)
        if not match:
            return {"should_ask": False, "target": "", "question": ""}
        try:
            data = json.loads(match.group(0))
        except json.JSONDecodeError:
            return {"should_ask": False, "target": "", "question": ""}

        should_ask = bool(data.get("should_ask", False))
        target = str(data.get("target", "both")).lower()
        if target not in ("plaintiff", "defendant", "user", "both"):
            target = "both"
        question = str(data.get("question", "")) if should_ask else ""
        if should_ask and not question.strip():
            should_ask = False
        return {"should_ask": should_ask, "target": target, "question": question}

    # ---------- 证据梳理 ----------

    async def generate_evidence_inquiry(
        self,
        case: str,
        history: list[dict],
    ) -> list[EvidenceItem]:
        """梳理本案所需关键证据清单。

        返回 ``[EvidenceItem(name, why_key, target_party)]``。
        target_party: 'user' / 'plaintiff' / 'defendant'。
        异常返回空列表。
        """
        try:
            prompt = self._evidence_inquiry_prompt(case, history)
            response = await self.gateway.chat(
                messages=[
                    {"role": "system", "content": SYSTEM_JUDGE},
                    {"role": "user", "content": prompt},
                ],
                model=MODEL_DECISION,
                temperature=0.2,
                max_tokens=800,
            )
            text = self.gateway.extract_text(response)
            return self._parse_evidence_list(text)
        except Exception:
            return []

    def _evidence_inquiry_prompt(self, case: str, history: list[dict]) -> str:
        history_text = self._format_history(history) if history else "暂无（开庭阶段）"
        return (
            f"你是中立法官，正在梳理本案做出判决所必需的关键证据清单。\n\n"
            f"案件描述：\n{case[:800]}\n\n"
            f"已有辩论：\n{history_text[:400]}\n\n"
            f"请列出本案做出判决所必需的关键证据清单（3-5 项），"
            f"用于向原被告双方或当事人（用户）确认是否能提供。\n\n"
            f"请严格按以下 JSON 格式输出（不要输出其他文字、不要 markdown 代码块）：\n"
            f'{{\n'
            f'  "evidence": [\n'
            f'    {{\n'
            f'      "name": "证据名称",\n'
            f'      "why_key": "为何关键（简短说明）",\n'
            f'      "target_party": "plaintiff" 或 "defendant" 或 "user"\n'
            f'    }}\n'
            f'  ]\n'
            f'}}'
        )

    def _parse_evidence_list(self, text: str) -> list[EvidenceItem]:
        raw = text.strip()
        if raw.startswith("```"):
            raw = re.sub(r"^```(?:json)?", "", raw, flags=re.IGNORECASE).strip()
            raw = re.sub(r"```$", "", raw).strip()
        match = re.search(r"\{.*\}", raw, flags=re.DOTALL)
        if not match:
            return []
        try:
            data = json.loads(match.group(0))
        except json.JSONDecodeError:
            return []

        items: list[EvidenceItem] = []
        for ev in data.get("evidence", []):
            if not isinstance(ev, dict):
                continue
            name = str(ev.get("name", "")).strip()
            if not name:
                continue
            target = str(ev.get("target_party", "user")).lower()
            if target not in ("plaintiff", "defendant", "user"):
                target = "user"
            items.append(
                EvidenceItem(
                    name=name,
                    why_key=str(ev.get("why_key", "")),
                    target_party=target,
                )
            )
        return items

    # ---------- 判决生成 ----------

    async def render_verdict(
        self,
        case: str,
        history: list[dict],
        user_answers: list[dict],
    ) -> Verdict:
        """生成最终判决。

        用 ``gateway.chat(model=MODEL_VERDICT)``。
        - content 为空时回退用 reasoning 作判决文本。
        - ``_parse_verdict`` 容错：JSON 解析失败时从自由文本提取判决信息。
        - LLMGatewayError → 文案"LLM 调用失败，请检查网络和 API 配置"（非"LLM 服务不可用"）。
        - 明确胜负，禁止端水。

        同时记录 ``self._user_said_unknown`` 供 ``check_rebuttal`` 使用。
        """
        self._user_said_unknown = self._check_user_unknown(user_answers)

        prompt = self._verdict_prompt(case, history, user_answers)
        try:
            response = await self.gateway.chat(
                messages=[
                    {"role": "system", "content": SYSTEM_JUDGE},
                    {"role": "user", "content": prompt},
                ],
                model=MODEL_VERDICT,
                temperature=0.2,
                max_tokens=2000,
            )
            reasoning = self.gateway.extract_reasoning(response)
            text = self.gateway.extract_text(response)
            # content 为空时回退用 reasoning 作判决文本
            if not text and reasoning:
                text = reasoning
            verdict = self._parse_verdict(text)
            if not verdict.full_text:
                verdict.full_text = text or reasoning
            return verdict
        except LLMGatewayError:
            # LLM 真正调用失败（非 JSON 解析失败）
            return Verdict(
                winner="无法判断",
                reasoning="LLM 调用失败，请检查网络和 API 配置。",
                full_text=(
                    "## 判决书\n\n"
                    "（LLM 调用失败，请检查网络和 API 配置后重试。）\n\n"
                    f"案件：{case[:200]}"
                ),
                compensation="",
            )

    def _verdict_prompt(
        self,
        case: str,
        history: list[dict],
        user_answers: list[dict],
    ) -> str:
        history_text = self._format_history(history)
        user_text = self._format_user_answers(user_answers)

        if self._user_said_unknown:
            evidence_note = (
                "【关键提示】当事人（用户）在庭审中明确表示对关键事实\"不清楚/不知道\"，"
                "关键证据无法确认。因此现有证据不足以做出明确判决。\n"
                "请在判决中：\n"
                "1. winner 设为\"无法判断\"\n"
                "2. 说明为何证据不足（哪些关键事实无法确认）\n"
                "3. 给出现有证据下的倾向性意见（哪一方更有可能胜诉）\n"
                "4. 建议当事人补充哪些证据后再行诉讼\n"
            )
        else:
            evidence_note = (
                "【关键提示】证据充分，必须给出明确判决。\n"
                "1. winner 只能是\"原告胜诉\"或\"被告胜诉\""
                "（或\"部分支持\"并说明哪部分）\n"
                "2. 禁止\"各50%\"这种端水判决\n"
                "3. 必须明确谁胜诉、谁败诉、为什么、引用哪条法律\n"
            )

        return (
            f"请作为中立法官，综合案件事实和多轮辩论，做出最终判决。\n\n"
            f"案件描述：\n{case}\n\n"
            f"完整辩论记录：\n{history_text}\n\n"
            f"当事人补充回答：\n{user_text}\n\n"
            f"{evidence_note}\n"
            f"请严格按照以下 JSON 格式输出（不要输出其他文字、不要 markdown 代码块）：\n"
            f'{{\n'
            f'  "winner": "原告胜诉"或"被告胜诉"或"部分支持"或"无法判断",\n'
            f'  "reasoning": "详细的判决理由，分析双方主张和抗辩的合理性，引用法律条文",\n'
            f'  "compensation": "赔偿/责任承担说明（如适用，否则留空）",\n'
            f'  "full_text": "完整的判决书文本，包括首部、事实认定、本院认为、'
            f'判决主文等，用 Markdown 格式，500-1000 字，必须引用具体法律条文"\n'
            f'}}\n\n'
            f"要求：\n"
            f'1. winner 只能是"原告胜诉"、"被告胜诉"、"部分支持"、"无法判断"之一\n'
            f"2. reasoning 要详细分析双方优劣\n"
            f"3. full_text 是完整判决书，引用具体法律条文\n"
            f"4. 不要编造法条编号"
        )

    def _check_user_unknown(self, user_answers: list[dict]) -> bool:
        """检查用户回答是否含\"不知道/不清楚\"等关键词。"""
        if not user_answers:
            return False
        for ans in user_answers:
            if not isinstance(ans, dict):
                continue
            content = str(ans.get("content") or ans.get("answer") or "")
            if any(pattern in content for pattern in self._USER_UNKNOWN_PATTERNS):
                return True
        return False

    @staticmethod
    def _format_user_answers(user_answers: list[dict]) -> str:
        if not user_answers:
            return "暂无当事人补充回答"
        lines: list[str] = []
        for i, ans in enumerate(user_answers, start=1):
            if not isinstance(ans, dict):
                continue
            question = str(ans.get("question", ""))
            content = str(ans.get("content") or ans.get("answer") or "")
            if question:
                lines.append(f"问题{i}：{question}")
            lines.append(f"回答{i}：{content[:400]}")
        return "\n".join(lines) if lines else "暂无当事人补充回答"

    def _parse_verdict(self, text: str) -> Verdict:
        """从 LLM 返回文本解析判决。

        JSON 解析失败时从自由文本提取判决信息：
        - winner 用正则匹配\"原告胜诉/被告胜诉\"等关键词
        - reasoning / full_text 用原文
        """
        if not text:
            return Verdict(
                winner="无法判断",
                reasoning="",
                full_text="",
                compensation="",
            )

        raw = text.strip()
        if raw.startswith("```"):
            raw = re.sub(r"^```(?:json)?", "", raw, flags=re.IGNORECASE).strip()
            raw = re.sub(r"```$", "", raw).strip()

        match = re.search(r"\{.*\}", raw, flags=re.DOTALL)
        if match:
            try:
                data = json.loads(match.group(0))
                winner = str(data.get("winner", "无法判断")).strip()
                reasoning = str(data.get("reasoning", "")).strip()
                full_text = str(
                    data.get("full_text") or data.get("verdict_text") or ""
                ).strip()
                compensation = str(data.get("compensation", "")).strip()
                if not full_text:
                    full_text = raw
                return Verdict(
                    winner=winner,
                    reasoning=reasoning,
                    full_text=full_text,
                    compensation=compensation,
                )
            except json.JSONDecodeError:
                pass  # 落到自由文本提取

        # JSON 解析失败：从自由文本提取判决（不用 fallback，用原文）
        winner = self._extract_winner_from_text(raw)
        return Verdict(
            winner=winner,
            reasoning=raw,
            full_text=raw,
            compensation="",
        )

    @staticmethod
    def _extract_winner_from_text(text: str) -> str:
        """从自由文本提取胜负，用正则匹配关键词。"""
        if not text:
            return "无法判断"
        # 优先级：原告胜诉 > 被告胜诉 > 部分支持 > 无法判断
        if re.search(r"原告(胜诉|获胜|诉请成立|主张成立|全部支持)", text):
            return "原告胜诉"
        if re.search(r"(被告(胜诉|获胜|抗辩成立)|驳回原告)", text):
            return "被告胜诉"
        if "部分支持" in text or "部分成立" in text:
            return "部分支持"
        if "无法判断" in text or "证据不足" in text:
            return "无法判断"
        return "无法判断"

    # ---------- 判决打回检查 ----------

    def check_rebuttal(self, verdict: Verdict) -> tuple[bool, str]:
        """判决打回检查。

        - 若 verdict.winner='无法判断' 且用户没说'不知道' → 打回，返回 (True, '需继续追问用户')
        - 若 verdict.winner 明确胜负 → 不打回，返回 (False, '')
        - 若端水（'各50%'等）→ 打回，返回 (True, '禁止端水')
        """
        winner = (verdict.winner or "").strip()
        full_text = (verdict.full_text or "") + (verdict.reasoning or "")

        # 检查端水判决
        if any(pattern in full_text for pattern in self._DUANSHUI_PATTERNS):
            return (True, "禁止端水")

        # 明确胜负：不打回
        if winner in ("原告胜诉", "被告胜诉"):
            return (False, "")
        if winner == "部分支持":
            return (False, "")

        # 无法判断：根据用户是否说"不知道"决定
        if winner in ("无法判断", ""):
            if self._user_said_unknown:
                # 用户也明确表示不知道，证据不足判决合理
                return (False, "")
            return (True, "需继续追问用户")

        return (False, "")
