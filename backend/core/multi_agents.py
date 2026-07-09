"""法庭模拟专家会诊系统。

核心类 ``CourtSimulator`` 模拟完整庭审流程：
审判长开场 → 原告陈述 → 被告答辩 → 多轮辩论（含法官追问）→ 最终判决。

支持两种调用方式：
1. ``run_trial`` — 非流式，返回完整 ``TrialResult``
2. ``stream_trial`` — 流式，异步生成器 yield 每个角色的发言片段

向后兼容：保留 ``LegalMultiAgentDebate`` 供 ``backend/api/routes.py`` 使用。
"""
from __future__ import annotations

import asyncio
import json
import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, AsyncGenerator, Optional

from backend.core.llm_gateway import LLMGateway, LLMGatewayError, gateway as default_gateway


# ========== 角色常量 ==========

ROLE_CHIEF_JUDGE = "chief_judge"   # 审判长
ROLE_PLAINTIFF = "plaintiff"       # 原告
ROLE_DEFENDANT = "defendant"       # 被告
ROLE_JUDGE = "judge"               # 中立法官
ROLE_VERDICT = "verdict"           # 判决

# ========== System Prompts ==========

SYSTEM_CHIEF_JUDGE = (
    "你是庭审审判长，负责组织庭审秩序。根据案件描述，拆分案件核心事实，"
    "分别向原告和被告介绍。用庄重威严的语气。"
)

SYSTEM_PLAINTIFF = (
    "你是原告代理人，代表原告利益。基于案件事实陈述诉讼请求、事实和理由，"
    "进行举证质证。用坚定有力的语气维护原告权益。"
)

SYSTEM_DEFENDANT = (
    "你是被告代理人，代表被告利益。针对原告指控进行答辩，提出抗辩理由和证据。"
    "用冷静理性的语气维护被告权益。"
)

SYSTEM_JUDGE = (
    "你是中立法官，不偏袒任何一方。根据双方辩论内容和相关法律依据，"
    "适时追问双方，最终做出公正判决。引用具体法律条文。"
)

# ========== 模型选择 ==========

MODEL_OPENING = "glm-4.7-flash"    # 开场白（快速）
MODEL_DEBATE = "glm-4.6"           # 辩论 / 追问（稳定）
MODEL_VERDICT = "glm-5.2"          # 最终判决（旗舰）


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
    法庭模拟专家会诊系统。

    角色：
    1. 审判长（主Agent）：拆分案件事实，控制庭审秩序，介绍案情
    2. 原告Agent：陈述诉讼请求、事实理由、举证质证
    3. 被告Agent：答辩、反诉、举证质证
    4. 法官Agent：追问双方，最终判决

    流程：
    审判长开场 → 原告陈述 → 被告答辩 → [多轮辩论] → 法官最终判决
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
        return "\n\n".join(lines)

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

    def _judge_inquiry_prompt(
        self,
        case: str,
        opening: str,
        round_num: int,
        rounds_so_far: list[TrialRound],
        plaintiff_speech: str,
        defendant_speech: str,
    ) -> str:
        return (
            f"请作为中立法官，对第 {round_num} 轮辩论进行追问。\n\n"
            f"案件描述：\n{case[:600]}\n\n"
            f"审判长开场白：\n{opening[:400]}\n\n"
            f"原告本轮主张：\n{plaintiff_speech[:600]}\n\n"
            f"被告本轮抗辩：\n{defendant_speech[:600]}\n\n"
            f"请针对双方辩论中的疑点、矛盾点或法律适用问题进行追问。\n"
            f"可以追问原告、被告或双方。引用相关法律条文。\n"
            f"字数 200-400 字。"
        )

    def _verdict_prompt(
        self,
        case: str,
        opening: str,
        rounds: list[TrialRound],
    ) -> str:
        debate = self._format_debate_history(rounds)
        return (
            f"请作为中立法官，综合案件事实和多轮辩论，做出最终判决。\n\n"
            f"案件描述：\n{case}\n\n"
            f"审判长开场白：\n{opening[:500]}\n\n"
            f"完整辩论记录：\n{debate}\n\n"
            f"请严格按照以下 JSON 格式输出（不要输出其他文字）：\n"
            f'{{\n'
            f'  "winner": "原告"或"被告"或"部分支持"或"无法判断",\n'
            f'  "plaintiff_win_rate": 0-100 的数字,\n'
            f'  "defendant_win_rate": 0-100 的数字,\n'
            f'  "key_points": ["关键胜负点1", "关键胜负点2", "关键胜负点3"],\n'
            f'  "reasoning": "详细的判决理由，分析双方主张和抗辩的合理性",\n'
            f'  "action_suggestions": ["建议1", "建议2", "建议3"],\n'
            f'  "verdict_text": "完整的判决书文本，包括首部、事实认定、'
            f'本院认为、判决主文等，用 Markdown 格式，500-1000 字"\n'
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

    # ========== 非流式生成 ==========

    async def _gen_opening(self, case: str) -> str:
        try:
            return await self.gateway.chat_text(
                user_message=self._opening_prompt(case),
                system_message=SYSTEM_CHIEF_JUDGE,
                model=MODEL_OPENING,
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
                model=MODEL_DEBATE,
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
                model=MODEL_DEBATE,
                temperature=0.6,
                max_tokens=1000,
            )
        except LLMGatewayError:
            return self._fallback_speech("defendant", case, round_num)

    async def _gen_judge_inquiry(
        self,
        case: str,
        opening: str,
        round_num: int,
        rounds_so_far: list[TrialRound],
        plaintiff_speech: str,
        defendant_speech: str,
    ) -> str:
        try:
            return await self.gateway.chat_text(
                user_message=self._judge_inquiry_prompt(
                    case, opening, round_num, rounds_so_far,
                    plaintiff_speech, defendant_speech,
                ),
                system_message=SYSTEM_JUDGE,
                model=MODEL_DEBATE,
                temperature=0.4,
                max_tokens=600,
            )
        except LLMGatewayError:
            return self._fallback_speech("judge", case, round_num)

    async def _gen_verdict(
        self,
        case: str,
        opening: str,
        rounds: list[TrialRound],
    ) -> Verdict:
        try:
            text = await self.gateway.chat_text(
                user_message=self._verdict_prompt(case, opening, rounds),
                system_message=SYSTEM_JUDGE,
                model=MODEL_VERDICT,
                temperature=0.2,
                max_tokens=2000,
            )
            return self._parse_verdict(text, case)
        except LLMGatewayError:
            return self._fallback_verdict(case)

    # ========== 流式生成 ==========

    async def _stream_opening(self, case: str) -> AsyncGenerator[str, None]:
        try:
            async for chunk in self.gateway.chat_stream(
                messages=[
                    {"role": "system", "content": SYSTEM_CHIEF_JUDGE},
                    {"role": "user", "content": self._opening_prompt(case)},
                ],
                model=MODEL_OPENING,
                temperature=0.5,
                max_tokens=1200,
            ):
                yield chunk
        except LLMGatewayError:
            yield self._fallback_opening(case)

    async def _stream_plaintiff(
        self,
        case: str,
        opening: str,
        round_num: int,
        rounds_so_far: list[TrialRound],
    ) -> AsyncGenerator[str, None]:
        try:
            async for chunk in self.gateway.chat_stream(
                messages=[
                    {"role": "system", "content": SYSTEM_PLAINTIFF},
                    {"role": "user", "content": self._plaintiff_prompt(
                        case, opening, round_num, rounds_so_far,
                    )},
                ],
                model=MODEL_DEBATE,
                temperature=0.6,
                max_tokens=1000,
            ):
                yield chunk
        except LLMGatewayError:
            yield self._fallback_speech("plaintiff", case, round_num)

    async def _stream_defendant(
        self,
        case: str,
        opening: str,
        round_num: int,
        rounds_so_far: list[TrialRound],
        plaintiff_speech: str,
    ) -> AsyncGenerator[str, None]:
        try:
            async for chunk in self.gateway.chat_stream(
                messages=[
                    {"role": "system", "content": SYSTEM_DEFENDANT},
                    {"role": "user", "content": self._defendant_prompt(
                        case, opening, round_num, rounds_so_far, plaintiff_speech,
                    )},
                ],
                model=MODEL_DEBATE,
                temperature=0.6,
                max_tokens=1000,
            ):
                yield chunk
        except LLMGatewayError:
            yield self._fallback_speech("defendant", case, round_num)

    async def _stream_judge_inquiry(
        self,
        case: str,
        opening: str,
        round_num: int,
        rounds_so_far: list[TrialRound],
        plaintiff_speech: str,
        defendant_speech: str,
    ) -> AsyncGenerator[str, None]:
        try:
            async for chunk in self.gateway.chat_stream(
                messages=[
                    {"role": "system", "content": SYSTEM_JUDGE},
                    {"role": "user", "content": self._judge_inquiry_prompt(
                        case, opening, round_num, rounds_so_far,
                        plaintiff_speech, defendant_speech,
                    )},
                ],
                model=MODEL_DEBATE,
                temperature=0.4,
                max_tokens=600,
            ):
                yield chunk
        except LLMGatewayError:
            yield self._fallback_speech("judge", case, round_num)

    async def _stream_verdict_text(
        self,
        case: str,
        opening: str,
        rounds: list[TrialRound],
    ) -> AsyncGenerator[str, None]:
        """流式生成判决书文本。"""
        try:
            async for chunk in self.gateway.chat_stream(
                messages=[
                    {"role": "system", "content": SYSTEM_JUDGE},
                    {"role": "user", "content": self._verdict_prompt(case, opening, rounds)},
                ],
                model=MODEL_VERDICT,
                temperature=0.2,
                max_tokens=2000,
            ):
                yield chunk
        except LLMGatewayError:
            yield self._fallback_verdict(case).full_text

    # ========== 解析 / Fallback ==========

    def _parse_verdict(self, text: str, case: str) -> Verdict:
        """从 LLM 返回的 JSON 文本中解析判决。"""
        raw = text.strip()
        # 去掉 markdown 代码块
        if raw.startswith("```"):
            raw = re.sub(r"^```(?:json)?", "", raw, flags=re.IGNORECASE).strip()
            raw = re.sub(r"```$", "", raw).strip()
        # 提取 JSON 对象
        match = re.search(r"\{.*\}", raw, flags=re.DOTALL)
        if not match:
            # 无法解析，用原始文本作为 full_text
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

    # ========== 主入口：非流式 ==========

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

            # 法官追问
            j_inquiry = await self._gen_judge_inquiry(
                case_description, opening, rn, trial_rounds, p_speech, d_speech,
            )
            speeches.append(SpeechRecord(ROLE_JUDGE, j_inquiry, rn, self._now()))

            trial_rounds.append(TrialRound(rn, p_speech, d_speech, j_inquiry))

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

    # ========== 主入口：流式 ==========

    async def stream_trial(
        self,
        case_description: str,
        rounds: int = 2,
    ) -> AsyncGenerator[dict[str, Any], None]:
        """
        运行完整庭审（流式），yield 每个事件的 dict。

        事件格式：
            {"event": "speech_start", "role": "chief_judge", "round": 0}
            {"event": "speech_chunk", "role": "chief_judge", "text": "...", "round": 0}
            {"event": "speech_end", "role": "chief_judge", "round": 0}
            ...
            {"event": "done", "trial_id": "...", "result": {...}}
            {"event": "error", "message": "..."}
        """
        rounds = max(1, min(rounds, 5))
        trial_id = self._new_trial_id()
        now = self._now()

        speeches: list[SpeechRecord] = []
        trial_rounds: list[TrialRound] = []

        try:
            # 1. 审判长开场
            opening = ""
            yield {"event": "speech_start", "role": ROLE_CHIEF_JUDGE, "round": 0}
            async for chunk in self._stream_opening(case_description):
                opening += chunk
                yield {"event": "speech_chunk", "role": ROLE_CHIEF_JUDGE, "text": chunk, "round": 0}
            yield {"event": "speech_end", "role": ROLE_CHIEF_JUDGE, "round": 0}
            speeches.append(SpeechRecord(ROLE_CHIEF_JUDGE, opening, 0, now))

            # 2. 多轮辩论
            for rn in range(1, rounds + 1):
                # 原告
                p_speech = ""
                yield {"event": "speech_start", "role": ROLE_PLAINTIFF, "round": rn}
                async for chunk in self._stream_plaintiff(
                    case_description, opening, rn, trial_rounds,
                ):
                    p_speech += chunk
                    yield {"event": "speech_chunk", "role": ROLE_PLAINTIFF, "text": chunk, "round": rn}
                yield {"event": "speech_end", "role": ROLE_PLAINTIFF, "round": rn}
                speeches.append(SpeechRecord(ROLE_PLAINTIFF, p_speech, rn, self._now()))

                # 被告
                d_speech = ""
                yield {"event": "speech_start", "role": ROLE_DEFENDANT, "round": rn}
                async for chunk in self._stream_defendant(
                    case_description, opening, rn, trial_rounds, p_speech,
                ):
                    d_speech += chunk
                    yield {"event": "speech_chunk", "role": ROLE_DEFENDANT, "text": chunk, "round": rn}
                yield {"event": "speech_end", "role": ROLE_DEFENDANT, "round": rn}
                speeches.append(SpeechRecord(ROLE_DEFENDANT, d_speech, rn, self._now()))

                # 法官追问
                j_inquiry = ""
                yield {"event": "speech_start", "role": ROLE_JUDGE, "round": rn}
                async for chunk in self._stream_judge_inquiry(
                    case_description, opening, rn, trial_rounds, p_speech, d_speech,
                ):
                    j_inquiry += chunk
                    yield {"event": "speech_chunk", "role": ROLE_JUDGE, "text": chunk, "round": rn}
                yield {"event": "speech_end", "role": ROLE_JUDGE, "round": rn}
                speeches.append(SpeechRecord(ROLE_JUDGE, j_inquiry, rn, self._now()))

                trial_rounds.append(TrialRound(rn, p_speech, d_speech, j_inquiry))

            # 3. 最终判决（流式生成判决书文本）
            verdict_text = ""
            yield {"event": "speech_start", "role": ROLE_VERDICT, "round": rounds + 1}
            async for chunk in self._stream_verdict_text(
                case_description, opening, trial_rounds,
            ):
                verdict_text += chunk
                yield {"event": "speech_chunk", "role": ROLE_VERDICT, "text": chunk, "round": rounds + 1}
            yield {"event": "speech_end", "role": ROLE_VERDICT, "round": rounds + 1}

            # 解析判决 JSON
            verdict = self._parse_verdict(verdict_text, case_description)
            # 如果解析后 full_text 为空（JSON 无 verdict_text），用原始文本
            if not verdict.full_text:
                verdict.full_text = verdict_text
            speeches.append(SpeechRecord(ROLE_VERDICT, verdict.full_text, rounds + 1, self._now()))

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

            yield {"event": "done", "trial_id": trial_id, "result": result.to_dict()}

        except Exception as exc:
            yield {"event": "error", "message": str(exc)}


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
            steps.append(f"第 {r.round_number} 轮 - 法官追问")
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
