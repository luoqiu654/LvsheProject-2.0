"""法庭模拟专家会诊系统（交互式重写版）。

核心类 ``CourtSimulator`` 模拟完整庭审流程：
审判长开场 → 原告陈述 → 被告答辩 → 多轮辩论（法官自主追问 + 用户询问）→ 最终判决。

关键设计：
1. 使用 ``gateway.chat_stream_with_reasoning`` 流式生成原被告发言
   - reasoning_content → SSE ``thinking`` 事件（前端折叠展示）
   - content → SSE ``speech`` 事件（正式发言）
2. 法官用 ``gateway.chat`` 非流式判断是否追问（返回 JSON 决策）
   - should_ask=false 时跳过追问，进入下一轮
3. 被问方必须回答法官追问；若回答含"不清楚/不知道"等，触发用户询问
   - 发送 ``user_question`` 事件，流暂停等待用户回答
   - 用户回答后继续辩论
4. 最终判决明确胜负，禁止"原告50%被告50%"端水判决
   - 仅当用户也明确表示"不知道"时，才判"证据不足"

向后兼容：保留 ``LegalMultiAgentDebate`` 供 ``backend/api/routes.py`` 使用。
"""
from __future__ import annotations

import asyncio
import json
import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, AsyncGenerator, Callable, Optional

from backend.core.llm_gateway import LLMGateway, LLMGatewayError, gateway as default_gateway


# ========== 角色常量 ==========

ROLE_CHIEF_JUDGE = "chief_judge"   # 审判长
ROLE_PLAINTIFF = "plaintiff"       # 原告
ROLE_DEFENDANT = "defendant"       # 被告
ROLE_JUDGE = "judge"               # 中立法官
ROLE_VERDICT = "verdict"           # 判决

# 发言种类（用于区分陈述 / 追问 / 回答）
KIND_OPENING = "opening"
KIND_STATEMENT = "statement"       # 原被告陈述
KIND_INQUIRY = "inquiry"           # 法官追问
KIND_ANSWER = "answer"             # 原被告回答法官
KIND_VERDICT = "verdict"
KIND_USER = "user"                 # 用户回答

# ========== System Prompts ==========

SYSTEM_CHIEF_JUDGE = (
    "你是庭审审判长（主Agent），负责组织庭审秩序与控制节奏。根据案件描述，拆分案件核心事实，"
    "分别向原告和被告介绍。用庄重威严的语气。"
    "你同时也是用户与庭审之间的桥梁：当法官认为某项关键证据对判决有重大影响，"
    "且原被告双方均无法确认是否能提供该证据时，由你向用户（当事人）发起询问，"
    "让用户回答是否持有相关证据。"
)

SYSTEM_PLAINTIFF = (
    "你是原告代理人。\n"
    "1. 代表原告利益，坚定有力地陈述\n"
    "2. 必须正面回答法官的追问，不得回避\n"
    "3. 如果你方确实不清楚某个事实，如实回答\"不清楚此事，需要当事人确认\"\n"
    "4. 引用法律条文支持你的主张"
)

SYSTEM_DEFENDANT = (
    "你是被告代理人。\n"
    "1. 代表被告利益，坚定有力地陈述\n"
    "2. 必须正面回答法官的追问，不得回避\n"
    "3. 如果你方确实不清楚某个事实，如实回答\"不清楚此事，需要当事人确认\"\n"
    "4. 引用法律条文支持你的主张"
)

SYSTEM_JUDGE = (
    "你是中立法官，正在审理一起案件。你的职责：\n"
    "1. 仔细倾听原告和被告的辩论，发现矛盾点和证据薄弱环节\n"
    "2. 主动追问，不要和稀泥。如果某方说法有漏洞，直接追问\n"
    "3. 如果双方都无法确认关键事实，向用户询问补充信息\n"
    "4. 只有当用户也表示不知道时，才判定证据不足\n"
    "5. 最终判决要明确：谁胜诉、谁败诉、为什么、引用哪条法律\n"
    "6. 不要给出\"原告50%被告50%\"这种端水判决\n"
    "你是犀利、专业、公正的法官。"
)

# ========== 模型选择 ==========

MODEL_SPEECH = "glm-4.7-flash"    # 陈述/回答（有思考过程可展示）
MODEL_DECISION = "glm-4.6"        # 法官追问决策（稳定 JSON）
MODEL_VERDICT = "glm-5.2"         # 最终判决（旗舰）

# 当事人"不清楚"关键事实的关键词（触发向用户询问）
UNCLEAR_PATTERNS = (
    "不清楚", "不知道", "无法确认", "暂无此证据", "需要当事人确认",
    "无法提供", "记不清", "不记得", "尚无证据", "无法核实",
)

# 用户明确表示"不知道"的关键词（触发证据不足判决）
USER_UNKNOWN_PATTERNS = (
    "不知道", "不清楚", "无法确认", "记不清", "不记得", "无从得知", "确实没有",
)


# ========== 新版数据结构 ==========


@dataclass
class SpeechRecord:
    """单次发言记录。"""

    role: str              # chief_judge / plaintiff / defendant / judge / verdict
    content: str
    round_number: int     # 0 = 开场, 1+ = 辩论轮次
    timestamp: str = ""


@dataclass
class TrialRound:
    """单轮辩论记录。"""

    round_number: int
    plaintiff_speech: str
    defendant_speech: str
    judge_inquiry: str = ""
    plaintiff_answer: str = ""
    defendant_answer: str = ""
    user_answer: str = ""


@dataclass
class JudgeDecision:
    """法官追问决策（由 LLM 返回的 JSON 解析而来）。

    should_ask: 是否追问。False 时跳过追问直接进入下一轮。
    question: 法官追问的问题（should_ask=True 时填写）。
    target: 追问对象 plaintiff / defendant / both。
    """

    should_ask: bool = False
    question: str = ""
    target: str = "both"


@dataclass
class EvidenceItem:
    """本案所需的关键证据项（法官主动梳理）。"""

    name: str              # 证据名称
    why_key: str            # 为何关键
    target_party: str       # 向谁确认：plaintiff / defendant / user


@dataclass
class Verdict:
    """法官判决（结构化）。"""

    winner: str                       # 原告 / 被告 / 部分支持 / 无法判断
    plaintiff_win_rate: float
    defendant_win_rate: float
    key_points: list[str] = field(default_factory=list)
    reasoning: str = ""
    action_suggestions: list[str] = field(default_factory=list)
    full_text: str = ""              # 完整判决书


@dataclass
class TrialResult:
    """庭审完整结果。"""

    trial_id: str
    case: str
    opening: str
    rounds: list[TrialRound] = field(default_factory=list)
    verdict: Optional[Verdict] = None
    summary: str = ""
    speeches: list[SpeechRecord] = field(default_factory=list)
    created_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        """序列化为可被 FastAPI 直接返回的 dict。"""
        return {
            "trial_id": self.trial_id,
            "case": self.case,
            "opening": self.opening,
            "rounds": [
                {
                    "round_number": r.round_number,
                    "plaintiff_speech": r.plaintiff_speech,
                    "defendant_speech": r.defendant_speech,
                    "judge_inquiry": r.judge_inquiry,
                    "plaintiff_answer": r.plaintiff_answer,
                    "defendant_answer": r.defendant_answer,
                    "user_answer": r.user_answer,
                }
                for r in self.rounds
            ],
            "verdict": (
                {
                    "winner": self.verdict.winner,
                    "plaintiff_win_rate": self.verdict.plaintiff_win_rate,
                    "defendant_win_rate": self.verdict.defendant_win_rate,
                    "key_points": self.verdict.key_points,
                    "reasoning": self.verdict.reasoning,
                    "action_suggestions": self.verdict.action_suggestions,
                    "full_text": self.verdict.full_text,
                }
                if self.verdict
                else None
            ),
            "summary": self.summary,
            "speeches": [
                {
                    "role": s.role,
                    "content": s.content,
                    "round_number": s.round_number,
                    "timestamp": s.timestamp,
                }
                for s in self.speeches
            ],
            "created_at": self.created_at,
        }


# ========== 向后兼容数据结构（供 routes.py 使用）==========


@dataclass
class DebateRound:
    """旧版单轮辩论记录。"""

    round_num: int
    plaintiff_statement: str
    defendant_statement: str


@dataclass
class AgentOpinion:
    """旧版单方意见。"""

    role: str
    viewpoint: str
    content: str


@dataclass
class JudgeVerdict:
    """旧版法官判决。"""

    winner: str
    plaintiff_win_rate: float
    defendant_win_rate: float
    key_points: list[str] = field(default_factory=list)
    reasoning: str = ""
    action_suggestions: list[str] = field(default_factory=list)


@dataclass
class MultiAgentDebateResult:
    """旧版会诊结果（routes.py 依赖）。"""

    case: str
    research_summary: str
    debate_rounds: list[DebateRound]
    judge_verdict: JudgeVerdict
    judge_summary: str
    steps: list[str] = field(default_factory=list)

    @property
    def opinions(self) -> list[AgentOpinion]:
        if not self.debate_rounds:
            return []
        last = self.debate_rounds[-1]
        return [
            AgentOpinion("Plaintiff Advocate", "权利主张方", last.plaintiff_statement),
            AgentOpinion("Defendant Advocate", "抗辩方", last.defendant_statement),
        ]


# ========== CourtSimulator: 法庭模拟核心 ==========


class CourtSimulator:
    """
    法庭模拟专家会诊系统（交互式重写版）。

    角色：
    1. 审判长（主Agent）：拆分案件事实，控制庭审秩序
    2. 原告Agent：陈述诉讼请求、事实理由、举证质证
    3. 被告Agent：答辩、反诉、举证质证
    4. 法官Agent：自主追问双方，最终判决

    流程：
    审判长开场 → 原告陈述 → 被告答辩 → [多轮辩论(法官自主追问)] → 法官最终判决
    """

    def __init__(self, llm_gateway: Optional[LLMGateway] = None) -> None:
        self.gateway = llm_gateway or default_gateway

    # ========== 工具方法 ==========

    @staticmethod
    def _now() -> str:
        return datetime.now().isoformat()

    @staticmethod
    def _new_trial_id() -> str:
        return uuid.uuid4().hex[:16]

    def _format_debate_history(self, rounds: list[TrialRound]) -> str:
        """格式化已有辩论记录，供下一轮 prompt 使用。"""
        if not rounds:
            return "暂无（首轮陈述）"
        lines: list[str] = []
        for r in rounds:
            lines.append(f"--- 第 {r.round_number} 轮 ---")
            lines.append(f"原告：{r.plaintiff_speech[:500]}")
            lines.append(f"被告：{r.defendant_speech[:500]}")
            if r.judge_inquiry:
                lines.append(f"法官追问：{r.judge_inquiry[:400]}")
            if r.plaintiff_answer:
                lines.append(f"原告回答法官：{r.plaintiff_answer[:400]}")
            if r.defendant_answer:
                lines.append(f"被告回答法官：{r.defendant_answer[:400]}")
            if r.user_answer:
                lines.append(f"用户（当事人）补充证据：{r.user_answer[:400]}")
        return "\n\n".join(lines)

    @staticmethod
    def _needs_user_input(answer: str) -> bool:
        """检查回答是否表明当事人不清楚关键事实（需向用户询问）。"""
        return any(p in answer for p in UNCLEAR_PATTERNS)

    @staticmethod
    def _is_user_unknown(user_answer: str) -> bool:
        """用户是否明确表示不知道（触发证据不足判决）。"""
        return any(p in user_answer for p in USER_UNKNOWN_PATTERNS)

    # ========== Prompt 构建 ==========

    def _opening_prompt(self, case: str) -> str:
        return (
            f"请作为庭审审判长，宣布开庭并介绍案情。\n\n"
            f"案件描述：\n{case}\n\n"
            f"请完成以下工作：\n"
            f"1. 宣布开庭，说明本次庭审的审理范围\n"
            f"2. 拆分案件核心事实（分别归纳对原告有利和被告有利的事实要点）\n"
            f"3. 明确争议焦点\n"
            f"4. 组织原被告双方进入辩论环节\n\n"
            f"请用庄重、威严的庭审语言，字数 500-800 字。"
        )

    def _plaintiff_prompt(
        self,
        case: str,
        opening: str,
        round_num: int,
        rounds_so_far: list[TrialRound],
    ) -> str:
        history = self._format_debate_history(rounds_so_far)
        if round_num == 1:
            instruction = "这是第一轮陈述，请全面陈述诉讼请求、事实和理由。"
        else:
            instruction = (
                f"这是第 {round_num} 轮辩论。请针对被告之前的抗辩进行反驳，"
                f"提出新的论据和法律依据。不要重复之前说过的内容。"
            )
        return (
            f"{instruction}\n\n"
            f"案件描述：\n{case}\n\n"
            f"审判长开场白：\n{opening[:600]}\n\n"
            f"之前辩论记录：\n{history}\n\n"
            f"请作为原告代理人发言：\n"
            f"1. 明确诉讼请求\n"
            f"2. 陈述事实和理由\n"
            f"3. 引用相关法律依据\n"
            f"4. 进行举证质证\n\n"
            f"用坚定有力的语气，字数 400-600 字。"
        )

    def _defendant_prompt(
        self,
        case: str,
        opening: str,
        round_num: int,
        rounds_so_far: list[TrialRound],
        plaintiff_speech: str,
    ) -> str:
        history = self._format_debate_history(rounds_so_far)
        if round_num == 1:
            instruction = "这是第一轮答辩，请全面进行抗辩。"
        else:
            instruction = (
                f"这是第 {round_num} 轮辩论。请针对原告本轮主张进行反驳，"
                f"提出新的抗辩理由。不要重复之前说过的内容。"
            )
        return (
            f"{instruction}\n\n"
            f"案件描述：\n{case}\n\n"
            f"审判长开场白：\n{opening[:600]}\n\n"
            f"原告本轮主张：\n{plaintiff_speech[:800]}\n\n"
            f"之前辩论记录：\n{history}\n\n"
            f"请作为被告代理人发言：\n"
            f"1. 针对原告主张进行答辩\n"
            f"2. 提出抗辩理由和事实依据\n"
            f"3. 引用相关法律依据\n"
            f"4. 进行举证质证\n\n"
            f"用冷静理性的语气，字数 400-600 字。"
        )

    def _judge_decision_prompt(
        self,
        case: str,
        opening: str,
        round_num: int,
        rounds_so_far: list[TrialRound],
        plaintiff_speech: str,
        defendant_speech: str,
    ) -> str:
        """法官判断是否需要追问。返回严格 JSON。"""
        history = self._format_debate_history(rounds_so_far)
        return (
            f"你是中立法官，正在审理第 {round_num} 轮辩论。请判断是否需要追问。\n\n"
            f"案件描述：\n{case[:600]}\n\n"
            f"审判长开场白：\n{opening[:400]}\n\n"
            f"之前辩论记录：\n{history[:800]}\n\n"
            f"原告本轮主张：\n{plaintiff_speech[:600]}\n\n"
            f"被告本轮抗辩：\n{defendant_speech[:600]}\n\n"
            f"【判断原则】\n"
            f"- 如果存在实质性疑点（证据链断裂、事实矛盾、法律适用争议、关键证据缺失），追问\n"
            f"- 如果本轮已充分辩论、无实质疑点，不追问\n"
            f"- 不要为了追问而追问，但也不要放过真正的疑点\n"
            f"- 你是犀利法官，发现漏洞就要追问，不和稀泥\n\n"
            f"请严格按以下 JSON 格式输出（不要输出其他文字、不要 markdown 代码块）：\n"
            f'{{\n'
            f'  "should_ask": true 或 false,\n'
            f'  "question": "追问的问题（should_ask=true 时必填，要犀利、一针见血）",\n'
            f'  "target": "plaintiff" 或 "defendant" 或 "both"\n'
            f'}}'
        )

    def _plaintiff_answer_prompt(
        self,
        case: str,
        opening: str,
        round_num: int,
        rounds_so_far: list[TrialRound],
        plaintiff_speech: str,
        defendant_speech: str,
        judge_question: str,
    ) -> str:
        history = self._format_debate_history(rounds_so_far)
        return (
            f"你是原告代理人。法官在第 {round_num} 轮辩论后向你追问，"
            f"你必须正面回答法官的问题。\n\n"
            f"案件描述：\n{case[:500]}\n\n"
            f"审判长开场白：\n{opening[:400]}\n\n"
            f"之前辩论记录：\n{history[:600]}\n\n"
            f"你本轮的陈述：\n{plaintiff_speech[:400]}\n\n"
            f"被告本轮抗辩：\n{defendant_speech[:400]}\n\n"
            f"【法官追问】\n{judge_question}\n\n"
            f"请针对法官的追问正面回答：\n"
            f"1. 直接回应法官的问题，不得回避\n"
            f"2. 如有相关证据，说明证据内容\n"
            f"3. 如确无相关证据或确实不清楚，明确表示\"不清楚此事，需要当事人确认\"\n"
            f"4. 不得含糊其辞、不得顾左右而言他\n\n"
            f"用坚定有力的语气，字数 200-400 字。"
        )

    def _defendant_answer_prompt(
        self,
        case: str,
        opening: str,
        round_num: int,
        rounds_so_far: list[TrialRound],
        plaintiff_speech: str,
        defendant_speech: str,
        judge_question: str,
    ) -> str:
        history = self._format_debate_history(rounds_so_far)
        return (
            f"你是被告代理人。法官在第 {round_num} 轮辩论后向你追问，"
            f"你必须正面回答法官的问题。\n\n"
            f"案件描述：\n{case[:500]}\n\n"
            f"审判长开场白：\n{opening[:400]}\n\n"
            f"之前辩论记录：\n{history[:600]}\n\n"
            f"原告本轮主张：\n{plaintiff_speech[:400]}\n\n"
            f"你本轮的抗辩：\n{defendant_speech[:400]}\n\n"
            f"【法官追问】\n{judge_question}\n\n"
            f"请针对法官的追问正面回答：\n"
            f"1. 直接回应法官的问题，不得回避\n"
            f"2. 如有相关证据，说明证据内容\n"
            f"3. 如确无相关证据或确实不清楚，明确表示\"不清楚此事，需要当事人确认\"\n"
            f"4. 不得含糊其辞、不得顾左右而言他\n\n"
            f"用冷静理性的语气，字数 200-400 字。"
        )

    def _verdict_prompt(
        self,
        case: str,
        opening: str,
        rounds: list[TrialRound],
        user_said_unknown: bool = False,
    ) -> str:
        debate = self._format_debate_history(rounds)
        if user_said_unknown:
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
                "1. winner 只能是\"原告\"或\"被告\"（或\"部分支持\"并说明哪部分）\n"
                "2. 禁止\"原告50%被告50%\"这种端水判决\n"
                "3. 必须明确谁胜诉、谁败诉、为什么、引用哪条法律\n"
            )
        return (
            f"请作为中立法官，综合案件事实和多轮辩论，做出最终判决。\n\n"
            f"案件描述：\n{case}\n\n"
            f"审判长开场白：\n{opening[:500]}\n\n"
            f"完整辩论记录：\n{debate}\n\n"
            f"{evidence_note}\n"
            f"请严格按照以下 JSON 格式输出（不要输出其他文字、不要 markdown 代码块）：\n"
            f'{{\n'
            f'  "winner": "原告"或"被告"或"部分支持"或"无法判断",\n'
            f'  "plaintiff_win_rate": 0-100 的数字,\n'
            f'  "defendant_win_rate": 0-100 的数字,\n'
            f'  "key_points": ["关键胜负点1", "关键胜负点2", "关键胜负点3"],\n'
            f'  "reasoning": "详细的判决理由，分析双方主张和抗辩的合理性",\n'
            f'  "action_suggestions": ["建议1", "建议2", "建议3"],\n'
            f'  "verdict_text": "完整的判决书文本，包括首部、事实认定、本院认为、'
            f'判决主文等，用 Markdown 格式，500-1000 字，必须引用具体法律条文"\n'
            f'}}\n\n'
            f"要求：\n"
            f'1. winner 只能是"原告"、"被告"、"部分支持"、"无法判断"之一\n'
            f"2. plaintiff_win_rate + defendant_win_rate 约等于 100\n"
            f"3. key_points 至少 3 条\n"
            f"4. reasoning 要详细分析双方优劣\n"
            f"5. action_suggestions 至少 3 条\n"
            f"6. verdict_text 是完整判决书，引用具体法律条文\n"
            f"7. 不要编造法条编号"
        )

    def _build_user_question(
        self, role: str, answer: str, judge_question: str, round_num: int,
    ) -> tuple[str, str]:
        """构造向用户询问的问题和上下文。"""
        role_label = "原告" if role == "plaintiff" else "被告"
        question = (
            f"法官追问：{judge_question[:200]}\n\n"
            f"{role_label}代理人回答：\"{answer[:300]}\"\n\n"
            f"由于{role_label}方对上述关键事实不清楚，请您（当事人）确认相关情况："
            f"您是否持有相关证据？事实经过究竟如何？请详细说明。"
        )
        context = (
            f"第 {round_num} 轮辩论中，法官就关键事实追问{role_label}方，"
            f"但{role_label}方表示不清楚。该事实对判决有重大影响，"
            f"需要您（当事人）提供补充信息以做出公正判决。"
            f"若您也不清楚，请在回答中明确说明。"
        )
        return question, context

    # ========== 证据梳理（法官主动）==========

    def _evidence_inquiry_prompt(
        self,
        case: str,
        opening: str,
        rounds_so_far: list[TrialRound],
    ) -> str:
        """构造证据梳理 prompt，要求 LLM 输出 JSON 证据清单。"""
        history = self._format_debate_history(rounds_so_far) if rounds_so_far else "暂无（开庭阶段）"
        return (
            f"你是中立法官，正在梳理本案做出判决所必需的关键证据清单。\n\n"
            f"案件描述：\n{case[:800]}\n\n"
            f"审判长开场白：\n{opening[:500]}\n\n"
            f"已有辩论：\n{history[:400]}\n\n"
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
        """从 LLM 返回的 JSON 文本中解析证据清单。"""
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
            items.append(EvidenceItem(
                name=name,
                why_key=str(ev.get("why_key", "")),
                target_party=target,
            ))
        return items

    async def _gen_evidence_inquiry(
        self,
        case: str,
        opening: str,
        rounds_so_far: list[TrialRound],
    ) -> list[EvidenceItem]:
        """非流式生成证据梳理清单，返回 EvidenceItem 列表。"""
        try:
            response = await self.gateway.chat(
                messages=[
                    {"role": "system", "content": SYSTEM_JUDGE},
                    {"role": "user", "content": self._evidence_inquiry_prompt(
                        case, opening, rounds_so_far,
                    )},
                ],
                model=MODEL_DECISION,
                temperature=0.3,
                max_tokens=800,
            )
            text = self.gateway.extract_text(response)
            # content 为空时回退用 reasoning
            if not text:
                text = self.gateway.extract_reasoning(response)
            return self._parse_evidence_list(text)
        except Exception:
            return []

    @staticmethod
    def _format_evidence_speech(items: list[EvidenceItem]) -> str:
        """将证据清单格式化为法官发言文本（speech 卡片展示）。"""
        if not items:
            return ""
        lines = ["## 法官证据梳理\n"]
        lines.append("经审查，本案做出判决需确认以下关键证据：\n")
        for i, ev in enumerate(items, 1):
            target_label = {
                "plaintiff": "原告方",
                "defendant": "被告方",
                "user": "当事人（您）",
            }.get(ev.target_party, "当事人")
            lines.append(f"{i}. **{ev.name}**（向{target_label}确认）")
            if ev.why_key:
                lines.append(f"   - 为何关键：{ev.why_key}")
        lines.append("\n请相关方就上述证据是否能提供做出说明。")
        return "\n".join(lines)

    # ========== 流式发言（含 reasoning）==========

    async def _stream_role_speech(
        self,
        messages: list[dict[str, str]],
        role: str,
        kind: str,
        model: str,
        round_num: int,
        temperature: float = 0.6,
        max_tokens: int = 1000,
        fallback_text: str = "",
    ) -> AsyncGenerator[dict[str, Any], None]:
        """
        流式生成角色发言，yield thinking / speech / speech_end 事件。

        - reasoning_content → ``thinking`` 事件（前端折叠展示）
        - content → ``speech`` 事件（正式发言）
        - 最后 yield ``speech_end`` 标记发言结束
        - 流式结束后若 content 累积为空但 reasoning 非空，
          回退用 reasoning 作为 speech 内容，保证发言卡片非空
        """
        content_acc = ""
        reasoning_acc = ""
        try:
            async for typ, text in self.gateway.chat_stream_with_reasoning(
                messages=messages,
                model=model,
                temperature=temperature,
                max_tokens=max_tokens,
            ):
                if typ == "reasoning":
                    reasoning_acc += text
                    yield {
                        "type": "thinking",
                        "role": role,
                        "text": text,
                        "round": round_num,
                    }
                else:  # content
                    content_acc += text
                    yield {
                        "type": "speech",
                        "role": role,
                        "text": text,
                        "kind": kind,
                        "round": round_num,
                    }
        except LLMGatewayError:
            if fallback_text:
                yield {
                    "type": "speech",
                    "role": role,
                    "text": fallback_text,
                    "kind": kind,
                    "round": round_num,
                }
                content_acc += fallback_text
        # 流式结束后若 content 累积为空但 reasoning 非空，回退用 reasoning 作为发言
        if not content_acc and reasoning_acc:
            yield {
                "type": "speech",
                "role": role,
                "text": reasoning_acc,
                "kind": kind,
                "round": round_num,
            }
        yield {
            "type": "speech_end",
            "role": role,
            "kind": kind,
            "round": round_num,
        }

    # ========== 非流式生成（供 run_trial 使用）==========

    async def _gen_opening(self, case: str) -> str:
        try:
            return await self.gateway.chat_text(
                user_message=self._opening_prompt(case),
                system_message=SYSTEM_CHIEF_JUDGE,
                model=MODEL_SPEECH,
                temperature=0.5,
                max_tokens=1200,
            )
        except LLMGatewayError:
            return self._fallback_opening(case)

    async def _gen_plaintiff(
        self,
        case: str,
        opening: str,
        round_num: int,
        rounds_so_far: list[TrialRound],
    ) -> str:
        try:
            return await self.gateway.chat_text(
                user_message=self._plaintiff_prompt(case, opening, round_num, rounds_so_far),
                system_message=SYSTEM_PLAINTIFF,
                model=MODEL_SPEECH,
                temperature=0.6,
                max_tokens=1000,
            )
        except LLMGatewayError:
            return self._fallback_speech("plaintiff", case, round_num)

    async def _gen_defendant(
        self,
        case: str,
        opening: str,
        round_num: int,
        rounds_so_far: list[TrialRound],
        plaintiff_speech: str,
    ) -> str:
        try:
            return await self.gateway.chat_text(
                user_message=self._defendant_prompt(
                    case, opening, round_num, rounds_so_far, plaintiff_speech,
                ),
                system_message=SYSTEM_DEFENDANT,
                model=MODEL_SPEECH,
                temperature=0.6,
                max_tokens=1000,
            )
        except LLMGatewayError:
            return self._fallback_speech("defendant", case, round_num)

    # ---------- 法官决策 / 回答 ----------

    def _parse_judge_decision(self, text: str) -> JudgeDecision:
        """从 LLM 返回的 JSON 文本中解析法官追问决策。"""
        raw = text.strip()
        if raw.startswith("```"):
            raw = re.sub(r"^```(?:json)?", "", raw, flags=re.IGNORECASE).strip()
            raw = re.sub(r"```$", "", raw).strip()
        match = re.search(r"\{.*\}", raw, flags=re.DOTALL)
        if not match:
            return JudgeDecision(should_ask=False)
        try:
            data = json.loads(match.group(0))
        except json.JSONDecodeError:
            return JudgeDecision(should_ask=False)

        should_ask = bool(data.get("should_ask", False))
        target = str(data.get("target", "both")).lower()
        if target not in ("plaintiff", "defendant", "both"):
            target = "both"
        return JudgeDecision(
            should_ask=should_ask,
            question=str(data.get("question", "")) if should_ask else "",
            target=target,
        )

    async def _gen_judge_decision(
        self,
        case: str,
        opening: str,
        round_num: int,
        rounds_so_far: list[TrialRound],
        plaintiff_speech: str,
        defendant_speech: str,
    ) -> JudgeDecision:
        """非流式调用 gateway.chat 让法官判断是否追问。"""
        try:
            response = await self.gateway.chat(
                messages=[
                    {"role": "system", "content": SYSTEM_JUDGE},
                    {"role": "user", "content": self._judge_decision_prompt(
                        case, opening, round_num, rounds_so_far,
                        plaintiff_speech, defendant_speech,
                    )},
                ],
                model=MODEL_DECISION,
                temperature=0.2,
                max_tokens=600,
            )
            text = self.gateway.extract_text(response)
            decision = self._parse_judge_decision(text)
            if decision.should_ask and not decision.question.strip():
                decision.should_ask = False
            return decision
        except Exception:
            return JudgeDecision(should_ask=False)

    async def _gen_plaintiff_answer(
        self,
        case: str,
        opening: str,
        round_num: int,
        rounds_so_far: list[TrialRound],
        plaintiff_speech: str,
        defendant_speech: str,
        judge_question: str,
    ) -> str:
        try:
            return await self.gateway.chat_text(
                user_message=self._plaintiff_answer_prompt(
                    case, opening, round_num, rounds_so_far,
                    plaintiff_speech, defendant_speech, judge_question,
                ),
                system_message=SYSTEM_PLAINTIFF,
                model=MODEL_SPEECH,
                temperature=0.5,
                max_tokens=700,
            )
        except Exception:
            return "（原告暂无回应，LLM 不可用）"

    async def _gen_defendant_answer(
        self,
        case: str,
        opening: str,
        round_num: int,
        rounds_so_far: list[TrialRound],
        plaintiff_speech: str,
        defendant_speech: str,
        judge_question: str,
    ) -> str:
        try:
            return await self.gateway.chat_text(
                user_message=self._defendant_answer_prompt(
                    case, opening, round_num, rounds_so_far,
                    plaintiff_speech, defendant_speech, judge_question,
                ),
                system_message=SYSTEM_DEFENDANT,
                model=MODEL_SPEECH,
                temperature=0.5,
                max_tokens=700,
            )
        except Exception:
            return "（被告暂无回应，LLM 不可用）"

    async def _gen_verdict_structured(
        self,
        case: str,
        opening: str,
        rounds: list[TrialRound],
        user_said_unknown: bool = False,
    ) -> tuple[Verdict, str]:
        """非流式生成判决，返回 (Verdict, reasoning_text)。"""
        try:
            response = await self.gateway.chat(
                messages=[
                    {"role": "system", "content": SYSTEM_JUDGE},
                    {"role": "user", "content": self._verdict_prompt(
                        case, opening, rounds, user_said_unknown,
                    )},
                ],
                model=MODEL_VERDICT,
                temperature=0.2,
                max_tokens=2000,
            )
            reasoning = self.gateway.extract_reasoning(response)
            text = self.gateway.extract_text(response)
            # 判决回退例外：当 content 为空时，从 reasoning 提取判决内容
            # （_parse_verdict 已支持正则提取 {...}）
            if not text and reasoning:
                text = reasoning
            verdict = self._parse_verdict(text, case)
            if not verdict.full_text:
                verdict.full_text = text or reasoning
            # 确保 VerdictPanel 拿到真实内容（非空）
            if not verdict.full_text:
                verdict.full_text = self._fallback_verdict(case).full_text
            return verdict, reasoning
        except LLMGatewayError:
            return self._fallback_verdict(case), ""

    async def _gen_verdict(
        self,
        case: str,
        opening: str,
        rounds: list[TrialRound],
    ) -> Verdict:
        """非流式生成判决（供 run_trial 使用）。"""
        verdict, _ = await self._gen_verdict_structured(case, opening, rounds)
        return verdict

    # ========== 解析 / Fallback ==========

    def _parse_verdict(self, text: str, case: str) -> Verdict:
        """从 LLM 返回的 JSON 文本中解析判决。"""
        raw = text.strip()
        if raw.startswith("```"):
            raw = re.sub(r"^```(?:json)?", "", raw, flags=re.IGNORECASE).strip()
            raw = re.sub(r"```$", "", raw).strip()
        match = re.search(r"\{.*\}", raw, flags=re.DOTALL)
        if not match:
            return self._fallback_verdict(case, raw)
        try:
            data = json.loads(match.group(0))
        except json.JSONDecodeError:
            return self._fallback_verdict(case, raw)

        p_rate = float(data.get("plaintiff_win_rate", 50))
        d_rate = float(data.get("defendant_win_rate", 100 - p_rate))
        return Verdict(
            winner=data.get("winner", "无法判断"),
            plaintiff_win_rate=p_rate,
            defendant_win_rate=d_rate,
            key_points=data.get("key_points", []),
            reasoning=data.get("reasoning", ""),
            action_suggestions=data.get("action_suggestions", []),
            full_text=data.get("verdict_text", text),
        )

    def _fallback_verdict(self, case: str, raw_text: str = "") -> Verdict:
        full_text = raw_text if raw_text else (
            "## 判决书\n\n"
            "经审理，本院认为双方各有主张与抗辩，综合现有证据和辩论情况，"
            "做出如下判决：\n\n"
            "（因 LLM 不可用，此为占位判决，请检查 API 配置后重试。）\n\n"
            f"案件：{case[:200]}"
        )
        return Verdict(
            winner="无法判断",
            plaintiff_win_rate=50,
            defendant_win_rate=50,
            key_points=["需进一步审查证据", "双方争议焦点需明确", "法律适用待确认"],
            reasoning="因 LLM 服务不可用，无法生成详细判决理由。",
            action_suggestions=["检查 API 配置", "补充证据材料", "咨询专业律师"],
            full_text=full_text,
        )

    def _fallback_opening(self, case: str) -> str:
        return (
            "## 审判长开场白\n\n"
            "现在开庭。本案的基本情况如下：\n\n"
            f"{case[:500]}\n\n"
            "经审判长审查，本案的核心争议焦点为：双方当事人的权利义务关系及责任承担问题。\n"
            "现在进入法庭调查和辩论阶段。请原告首先陈述诉讼请求、事实和理由。"
        )

    def _fallback_speech(self, role: str, case: str, round_num: int) -> str:
        names = {
            "plaintiff": "原告",
            "defendant": "被告",
            "judge": "法官",
        }
        name = names.get(role, role)
        return (
            f"【{name}第 {round_num} 轮发言】\n"
            f"（LLM 不可用，此为占位发言）\n"
            f"案件：{case[:200]}"
        )

    @staticmethod
    def _verdict_to_dict(verdict: Verdict) -> dict[str, Any]:
        return {
            "winner": verdict.winner,
            "plaintiff_win_rate": verdict.plaintiff_win_rate,
            "defendant_win_rate": verdict.defendant_win_rate,
            "key_points": verdict.key_points,
            "reasoning": verdict.reasoning,
            "action_suggestions": verdict.action_suggestions,
            "full_text": verdict.full_text,
        }

    # ========== 主入口：非流式（供 routes.py / POST /trial 使用）==========

    async def run_trial(
        self,
        case_description: str,
        rounds: int = 2,
    ) -> TrialResult:
        """
        运行完整庭审（非流式）。

        Args:
            case_description: 案件描述
            rounds: 辩论轮数（1-5），默认 2

        Returns:
            TrialResult: 完整庭审结果
        """
        rounds = max(1, min(rounds, 5))
        trial_id = self._new_trial_id()
        now = self._now()

        speeches: list[SpeechRecord] = []
        trial_rounds: list[TrialRound] = []

        # 1. 审判长开场
        opening = await self._gen_opening(case_description)
        speeches.append(SpeechRecord(ROLE_CHIEF_JUDGE, opening, 0, now))

        # 2. 多轮辩论
        for rn in range(1, rounds + 1):
            # 原告
            p_speech = await self._gen_plaintiff(
                case_description, opening, rn, trial_rounds,
            )
            speeches.append(SpeechRecord(ROLE_PLAINTIFF, p_speech, rn, self._now()))

            # 被告
            d_speech = await self._gen_defendant(
                case_description, opening, rn, trial_rounds, p_speech,
            )
            speeches.append(SpeechRecord(ROLE_DEFENDANT, d_speech, rn, self._now()))

            # 法官判断是否追问
            decision = await self._gen_judge_decision(
                case_description, opening, rn, trial_rounds, p_speech, d_speech,
            )
            j_inquiry = ""
            p_answer = ""
            d_answer = ""
            user_answer = ""

            if decision.should_ask and decision.question:
                j_inquiry = decision.question
                speeches.append(SpeechRecord(ROLE_JUDGE, j_inquiry, rn, self._now()))

                target = decision.target
                if target in ("plaintiff", "both"):
                    p_answer = await self._gen_plaintiff_answer(
                        case_description, opening, rn, trial_rounds,
                        p_speech, d_speech, j_inquiry,
                    )
                    speeches.append(SpeechRecord(ROLE_PLAINTIFF, p_answer, rn, self._now()))
                if target in ("defendant", "both"):
                    d_answer = await self._gen_defendant_answer(
                        case_description, opening, rn, trial_rounds,
                        p_speech, d_speech, j_inquiry,
                    )
                    speeches.append(SpeechRecord(ROLE_DEFENDANT, d_answer, rn, self._now()))
                # 非交互模式：evidence_needed 时无法询问用户，仅记录

            trial_rounds.append(TrialRound(
                rn, p_speech, d_speech, j_inquiry, p_answer, d_answer,
            ))

        # 3. 最终判决
        verdict = await self._gen_verdict(case_description, opening, trial_rounds)
        if verdict.full_text:
            speeches.append(SpeechRecord(ROLE_VERDICT, verdict.full_text, rounds + 1, self._now()))

        summary = (
            f"庭审完成，共 {rounds} 轮辩论。"
            f"判决结果：{verdict.winner}。"
            f"原告胜诉概率 {verdict.plaintiff_win_rate:.0f}%，"
            f"被告胜诉概率 {verdict.defendant_win_rate:.0f}%。"
        )

        return TrialResult(
            trial_id=trial_id,
            case=case_description,
            opening=opening,
            rounds=trial_rounds,
            verdict=verdict,
            summary=summary,
            speeches=speeches,
            created_at=now,
        )

    # ========== 主入口：交互式流式 ==========

    async def stream_trial_interactive(
        self,
        case_description: str,
        rounds: int = 2,
        answer_callback: Optional[Callable[..., Any]] = None,
        trial_id: Optional[str] = None,
    ) -> AsyncGenerator[dict[str, Any], None]:
        """
        运行完整庭审（交互式流式）。

        流程：
        1. 审判长开场（流式 + reasoning）
        2. 多轮辩论：
           a. 原告陈述（流式 + reasoning）
           b. 被告答辩（流式 + reasoning）
           c. 法官追问决策（非流式 JSON）
              - should_ask=false 时跳过追问，进入下一轮
           d. 追问：法官提问 → 被问方必须回答（流式 + reasoning）
           e. 证据检查：若回答含"不清楚/不知道"，触发 user_question
              - 发送 user_question 事件，流暂停等待 answer_callback 返回
              - 用户回答后继续辩论
           f. round_end
        3. 最终判决（非流式，提取 reasoning）
           - 证据充分：明确胜负（禁止端水）
           - 用户也说"不知道"：判"证据不足"+ 倾向性意见

        事件格式：
            {"type":"trial_started","trial_id":"..."}
            {"type":"thinking","role":"plaintiff","text":"...","round":1}
            {"type":"speech","role":"plaintiff","text":"...","kind":"statement","round":1}
            {"type":"speech_end","role":"plaintiff","kind":"statement","round":1}
            {"type":"user_question","question_id":"q1_p","question":"...","context":"...","round":1}
            {"type":"user_answer","question_id":"q1_p","answer":"...","round":1}
            {"type":"round_end","round":1}
            {"type":"verdict","verdict":{...},"round":N}
            {"type":"done","trial_id":"...","result":{...}}
            {"type":"error","message":"..."}
        """
        rounds = max(1, min(rounds, 5))
        trial_id = trial_id or self._new_trial_id()
        now = self._now()

        speeches: list[SpeechRecord] = []
        trial_rounds: list[TrialRound] = []
        user_said_unknown = False

        try:
            # 通知前端 trial_id
            yield {"type": "trial_started", "trial_id": trial_id}

            # 1. 审判长开场（流式 + reasoning）
            opening = ""
            opening_msgs = [
                {"role": "system", "content": SYSTEM_CHIEF_JUDGE},
                {"role": "user", "content": self._opening_prompt(case_description)},
            ]
            async for ev in self._stream_role_speech(
                opening_msgs, ROLE_CHIEF_JUDGE, KIND_OPENING, MODEL_SPEECH, 0,
                temperature=0.5, max_tokens=1200,
                fallback_text=self._fallback_opening(case_description),
            ):
                yield ev
                if ev["type"] == "speech":
                    opening += ev["text"]
            speeches.append(SpeechRecord(ROLE_CHIEF_JUDGE, opening, 0, now))

            # 1.5 法官证据梳理（opening 之后、第一轮辩论前）
            evidence_user_answer = ""
            yield {
                "type": "thinking_note",
                "role": ROLE_JUDGE,
                "text": "法官正在梳理本案所需的关键证据清单...",
                "round": 0,
            }
            evidence_items = await self._gen_evidence_inquiry(
                case_description, opening, trial_rounds,
            )
            if evidence_items:
                yield {
                    "type": "evidence_list",
                    "items": [
                        {
                            "name": e.name,
                            "why_key": e.why_key,
                            "target_party": e.target_party,
                        }
                        for e in evidence_items
                    ],
                    "round": 0,
                }
                evidence_text = self._format_evidence_speech(evidence_items)
                if evidence_text:
                    yield {
                        "type": "speech",
                        "role": ROLE_JUDGE,
                        "text": evidence_text,
                        "kind": KIND_INQUIRY,
                        "round": 0,
                    }
                    yield {
                        "type": "speech_end",
                        "role": ROLE_JUDGE,
                        "kind": KIND_INQUIRY,
                        "round": 0,
                    }
                    speeches.append(SpeechRecord(
                        ROLE_JUDGE, evidence_text, 0, self._now(),
                    ))
                # 对每项 target_party="user" 的证据，向用户针对性追问
                user_evidence_answers: list[str] = []
                for idx, ev in enumerate(evidence_items):
                    if ev.target_party != "user" or answer_callback is None:
                        continue
                    question_id = f"ev_{idx}"
                    ev_q = (
                        f"法官要求您确认证据：{ev.name}\n"
                        f"为何关键：{ev.why_key}\n"
                        f"您是否持有该证据？如有，请说明证据内容。"
                    )
                    ev_ctx = (
                        f"该证据（{ev.name}）对本案判决有重大影响，"
                        f"需当事人（您）确认是否持有。"
                        f"若您不持有或不清楚，请明确说明。"
                    )
                    yield {
                        "type": "user_question",
                        "question_id": question_id,
                        "question": ev_q,
                        "context": ev_ctx,
                        "evidence_name": ev.name,
                        "round": 0,
                    }
                    try:
                        ev_ans = await answer_callback(question_id, ev_q, ev_ctx)
                    except Exception as exc:
                        ev_ans = f"（用户回答失败：{exc}）"
                    if not isinstance(ev_ans, str):
                        ev_ans = str(ev_ans)
                    yield {
                        "type": "user_answer",
                        "question_id": question_id,
                        "answer": ev_ans,
                        "round": 0,
                    }
                    if self._is_user_unknown(ev_ans):
                        user_said_unknown = True
                    user_evidence_answers.append(f"【证据：{ev.name}】{ev_ans}")
                if user_evidence_answers:
                    evidence_user_answer = "\n\n".join(user_evidence_answers)

            # 2. 多轮辩论
            for rn in range(1, rounds + 1):
                p_speech = ""
                d_speech = ""
                j_inquiry = ""
                p_answer = ""
                d_answer = ""
                user_answer = ""
                try:
                    # a. 原告陈述（流式 + reasoning）
                    p_msgs = [
                        {"role": "system", "content": SYSTEM_PLAINTIFF},
                        {"role": "user", "content": self._plaintiff_prompt(
                            case_description, opening, rn, trial_rounds,
                        )},
                    ]
                    async for ev in self._stream_role_speech(
                        p_msgs, ROLE_PLAINTIFF, KIND_STATEMENT, MODEL_SPEECH, rn,
                        temperature=0.6, max_tokens=1000,
                        fallback_text=self._fallback_speech("plaintiff", case_description, rn),
                    ):
                        yield ev
                        if ev["type"] == "speech":
                            p_speech += ev["text"]
                    speeches.append(SpeechRecord(ROLE_PLAINTIFF, p_speech, rn, self._now()))

                    # b. 被告答辩（流式 + reasoning）
                    d_msgs = [
                        {"role": "system", "content": SYSTEM_DEFENDANT},
                        {"role": "user", "content": self._defendant_prompt(
                            case_description, opening, rn, trial_rounds, p_speech,
                        )},
                    ]
                    async for ev in self._stream_role_speech(
                        d_msgs, ROLE_DEFENDANT, KIND_STATEMENT, MODEL_SPEECH, rn,
                        temperature=0.6, max_tokens=1000,
                        fallback_text=self._fallback_speech("defendant", case_description, rn),
                    ):
                        yield ev
                        if ev["type"] == "speech":
                            d_speech += ev["text"]
                    speeches.append(SpeechRecord(ROLE_DEFENDANT, d_speech, rn, self._now()))

                    # c. 法官追问决策（非流式 JSON）
                    yield {
                        "type": "thinking_note",
                        "role": ROLE_JUDGE,
                        "text": f"法官正在审查第 {rn} 轮辩论，判断是否需要追问...",
                        "round": rn,
                    }
                    decision = await self._gen_judge_decision(
                        case_description, opening, rn, trial_rounds, p_speech, d_speech,
                    )

                    if decision.should_ask and decision.question:
                        j_inquiry = decision.question
                        target = decision.target
                        target_label = {
                            "plaintiff": "原告", "defendant": "被告", "both": "原被告双方",
                        }.get(target, "双方")

                        # d. 法官追问（已由决策 LLM 生成，一次性发出）
                        yield {
                            "type": "speech",
                            "role": ROLE_JUDGE,
                            "text": j_inquiry,
                            "kind": KIND_INQUIRY,
                            "round": rn,
                        }
                        yield {
                            "type": "speech_end",
                            "role": ROLE_JUDGE,
                            "kind": KIND_INQUIRY,
                            "round": rn,
                        }
                        speeches.append(SpeechRecord(ROLE_JUDGE, j_inquiry, rn, self._now()))

                        # 原告回答法官
                        if target in ("plaintiff", "both"):
                            yield {
                                "type": "thinking_note",
                                "role": ROLE_PLAINTIFF,
                                "text": f"原告正在针对法官追问（对象：{target_label}）组织回答...",
                                "round": rn,
                            }
                            pa_msgs = [
                                {"role": "system", "content": SYSTEM_PLAINTIFF},
                                {"role": "user", "content": self._plaintiff_answer_prompt(
                                    case_description, opening, rn, trial_rounds,
                                    p_speech, d_speech, j_inquiry,
                                )},
                            ]
                            async for ev in self._stream_role_speech(
                                pa_msgs, ROLE_PLAINTIFF, KIND_ANSWER, MODEL_SPEECH, rn,
                                temperature=0.5, max_tokens=700,
                                fallback_text="（原告暂无回应）",
                            ):
                                yield ev
                                if ev["type"] == "speech":
                                    p_answer += ev["text"]
                            speeches.append(SpeechRecord(ROLE_PLAINTIFF, p_answer, rn, self._now()))

                            # 证据检查：原告回答含"不清楚" → 向用户询问
                            if self._needs_user_input(p_answer) and answer_callback is not None:
                                question_id = f"q{rn}_plaintiff"
                                ev_q, ev_ctx = self._build_user_question(
                                    "plaintiff", p_answer, j_inquiry, rn,
                                )
                                yield {
                                    "type": "user_question",
                                    "question_id": question_id,
                                    "question": ev_q,
                                    "context": ev_ctx,
                                    "round": rn,
                                }
                                try:
                                    u_ans = await answer_callback(question_id, ev_q, ev_ctx)
                                except Exception as exc:
                                    u_ans = f"（用户回答失败：{exc}）"
                                if not isinstance(u_ans, str):
                                    u_ans = str(u_ans)
                                yield {
                                    "type": "user_answer",
                                    "question_id": question_id,
                                    "answer": u_ans,
                                    "round": rn,
                                }
                                if self._is_user_unknown(u_ans):
                                    user_said_unknown = True
                                user_answer = u_ans

                        # 被告回答法官
                        if target in ("defendant", "both"):
                            yield {
                                "type": "thinking_note",
                                "role": ROLE_DEFENDANT,
                                "text": f"被告正在针对法官追问（对象：{target_label}）组织回答...",
                                "round": rn,
                            }
                            da_msgs = [
                                {"role": "system", "content": SYSTEM_DEFENDANT},
                                {"role": "user", "content": self._defendant_answer_prompt(
                                    case_description, opening, rn, trial_rounds,
                                    p_speech, d_speech, j_inquiry,
                                )},
                            ]
                            async for ev in self._stream_role_speech(
                                da_msgs, ROLE_DEFENDANT, KIND_ANSWER, MODEL_SPEECH, rn,
                                temperature=0.5, max_tokens=700,
                                fallback_text="（被告暂无回应）",
                            ):
                                yield ev
                                if ev["type"] == "speech":
                                    d_answer += ev["text"]
                            speeches.append(SpeechRecord(ROLE_DEFENDANT, d_answer, rn, self._now()))

                            # 证据检查：被告回答含"不清楚" → 向用户询问
                            if self._needs_user_input(d_answer) and answer_callback is not None:
                                question_id = f"q{rn}_defendant"
                                ev_q, ev_ctx = self._build_user_question(
                                    "defendant", d_answer, j_inquiry, rn,
                                )
                                yield {
                                    "type": "user_question",
                                    "question_id": question_id,
                                    "question": ev_q,
                                    "context": ev_ctx,
                                    "round": rn,
                                }
                                try:
                                    d_u_ans = await answer_callback(question_id, ev_q, ev_ctx)
                                except Exception as exc:
                                    d_u_ans = f"（用户回答失败：{exc}）"
                                if not isinstance(d_u_ans, str):
                                    d_u_ans = str(d_u_ans)
                                yield {
                                    "type": "user_answer",
                                    "question_id": question_id,
                                    "answer": d_u_ans,
                                    "round": rn,
                                }
                                if self._is_user_unknown(d_u_ans):
                                    user_said_unknown = True
                                if user_answer:
                                    user_answer += f"\n（被告方追问）{d_u_ans}"
                                else:
                                    user_answer = d_u_ans
                    else:
                        # 法官决定不追问
                        yield {
                            "type": "thinking_note",
                            "role": ROLE_JUDGE,
                            "text": f"法官审查后认为第 {rn} 轮辩论无需追问，进入下一环节。",
                            "round": rn,
                        }
                except Exception as exc:
                    yield {
                        "type": "error",
                        "message": f"第 {rn} 轮辩论出错：{exc}（已跳过，继续下一轮）",
                        "round": rn,
                    }
                # 注入证据梳理阶段的用户回答到第 1 轮
                round_user_answer = user_answer
                if rn == 1 and evidence_user_answer:
                    round_user_answer = (
                        evidence_user_answer
                        + (f"\n\n{user_answer}" if user_answer else "")
                    )
                trial_rounds.append(TrialRound(
                    rn, p_speech, d_speech, j_inquiry, p_answer, d_answer, round_user_answer,
                ))
                yield {"type": "round_end", "round": rn}

            # 3. 最终判决（非流式，提取 reasoning）
            yield {
                "type": "thinking_note",
                "role": ROLE_JUDGE,
                "text": "法官正在综合所有辩论和证据，撰写判决书...",
                "round": rounds + 1,
            }
            verdict, v_reasoning = await self._gen_verdict_structured(
                case_description, opening, trial_rounds, user_said_unknown,
            )
            # 若判决模型有 reasoning_content，作为思考过程展示
            if v_reasoning:
                yield {
                    "type": "thinking",
                    "role": ROLE_JUDGE,
                    "text": v_reasoning,
                    "round": rounds + 1,
                }
            speeches.append(SpeechRecord(
                ROLE_VERDICT, verdict.full_text, rounds + 1, self._now(),
            ))

            yield {
                "type": "verdict",
                "verdict": self._verdict_to_dict(verdict),
                "round": rounds + 1,
            }

            summary = (
                f"庭审完成，共 {rounds} 轮辩论。"
                f"判决结果：{verdict.winner}。"
                f"原告胜诉概率 {verdict.plaintiff_win_rate:.0f}%，"
                f"被告胜诉概率 {verdict.defendant_win_rate:.0f}%。"
            )

            result = TrialResult(
                trial_id=trial_id,
                case=case_description,
                opening=opening,
                rounds=trial_rounds,
                verdict=verdict,
                summary=summary,
                speeches=speeches,
                created_at=now,
            )

            yield {"type": "done", "trial_id": trial_id, "result": result.to_dict()}

        except Exception as exc:
            yield {"type": "error", "message": str(exc)}


# ========== 向后兼容：LegalMultiAgentDebate（供 routes.py 使用）==========


class LegalMultiAgentDebate:
    """
    向后兼容：旧版多智能体辩论接口。

    内部委托给 ``CourtSimulator``，将结果适配为旧版数据结构。
    供 ``backend/api/routes.py`` 的 ``/multi-agents/debate`` 端点使用。
    """

    def __init__(self, llm_gateway: Optional[LLMGateway] = None) -> None:
        self._simulator = CourtSimulator(llm_gateway)

    async def run(
        self,
        case: str,
        use_llm: bool = True,
        max_rounds: int = 3,
        **kwargs: Any,
    ) -> MultiAgentDebateResult:
        """旧版 run 接口，委托给 CourtSimulator。"""
        if not use_llm or not self._simulator.gateway.is_available:
            return self._fallback_result(case, max_rounds)

        rounds = max(1, min(max_rounds, 3))
        try:
            trial = await self._simulator.run_trial(case, rounds=rounds)
        except Exception:
            return self._fallback_result(case, max_rounds)

        debate_rounds = [
            DebateRound(r.round_number, r.plaintiff_speech, r.defendant_speech)
            for r in trial.rounds
        ]

        verdict = trial.verdict or Verdict("无法判断", 50, 50)
        judge_verdict = JudgeVerdict(
            winner=verdict.winner,
            plaintiff_win_rate=verdict.plaintiff_win_rate,
            defendant_win_rate=verdict.defendant_win_rate,
            key_points=verdict.key_points,
            reasoning=verdict.reasoning,
            action_suggestions=verdict.action_suggestions,
        )

        steps = ["审判长：开庭并拆分案件事实"]
        for r in trial.rounds:
            steps.append(f"第 {r.round_number} 轮 - 原告陈述")
            steps.append(f"第 {r.round_number} 轮 - 被告答辩")
            if r.judge_inquiry:
                steps.append(f"第 {r.round_number} 轮 - 法官追问")
            if r.plaintiff_answer:
                steps.append(f"第 {r.round_number} 轮 - 原告回答法官")
            if r.defendant_answer:
                steps.append(f"第 {r.round_number} 轮 - 被告回答法官")
            if r.user_answer:
                steps.append(f"第 {r.round_number} 轮 - 用户补充证据")
        steps.append("法官：做出最终判决")

        return MultiAgentDebateResult(
            case=trial.case,
            research_summary=trial.opening,
            debate_rounds=debate_rounds,
            judge_verdict=judge_verdict,
            judge_summary=verdict.full_text,
            steps=steps,
        )

    def _fallback_result(self, case: str, max_rounds: int) -> MultiAgentDebateResult:
        """LLM 不可用时的简易回退结果。"""
        debate_rounds = [
            DebateRound(
                round_num=i,
                plaintiff_statement=f"【原告第 {i} 轮】（LLM 不可用，占位）",
                defendant_statement=f"【被告第 {i} 轮】（LLM 不可用，占位）",
            )
            for i in range(1, max_rounds + 1)
        ]
        verdict = JudgeVerdict(
            winner="无法判断",
            plaintiff_win_rate=50,
            defendant_win_rate=50,
            key_points=["LLM 不可用，无法分析"],
            reasoning="LLM 服务未配置或不可用。",
            action_suggestions=["检查 ZHIPU_API_KEY 配置"],
        )
        return MultiAgentDebateResult(
            case=case,
            research_summary="（LLM 不可用，无检索摘要）",
            debate_rounds=debate_rounds,
            judge_verdict=verdict,
            judge_summary="LLM 不可用，无法生成判决。",
            steps=["LLM 不可用，使用占位结果"],
        )


# ========== 全局实例 ==========

court_simulator = CourtSimulator()
multi_agent_debate = LegalMultiAgentDebate()


# ========== Demo ==========

async def _demo() -> None:
    case = (
        "甲方委托乙方开发网站，合同金额 50000 元。"
        "乙方迟迟未交付，合同未明确交付时间，"
        "甲方要求解除合同并赔偿损失。"
    )
    print("开始法庭模拟...")
    result = await court_simulator.run_trial(case, rounds=2)
    print(f"\n庭审ID: {result.trial_id}")
    print(f"开场白:\n{result.opening[:200]}...")
    for r in result.rounds:
        print(f"\n=== 第 {r.round_number} 轮 ===")
        print(f"原告: {r.plaintiff_speech[:100]}...")
        print(f"被告: {r.defendant_speech[:100]}...")
        print(f"法官: {r.judge_inquiry[:100]}...")
    if result.verdict:
        print(f"\n判决: {result.verdict.winner}")
        print(f"原告胜率: {result.verdict.plaintiff_win_rate}%")
    print(f"\n总结: {result.summary}")


if __name__ == "__main__":
    asyncio.run(_demo())
