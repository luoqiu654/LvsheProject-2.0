"""向后兼容：旧版多智能体辩论适配器（v3.7 从 multi_agents.py 提取）。

``LegalMultiAgentDebate`` 内部委托给 ``CourtOrchestrator.stream_trial()``，
将流式事件组装为旧版 ``MultiAgentDebateResult`` 数据结构。

供 ``backend/api/routes.py`` 的 ``/multi-agents/debate`` 端点使用（已标记 deprecated）。
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Optional

from backend.core.court_orchestrator import CourtOrchestrator
from backend.core.llm_gateway import LLMGateway, gateway as default_gateway
from backend.core.rag import rag as default_rag
from backend.core.skills import registry as default_skill_registry

logger = logging.getLogger(__name__)


# ========== 向后兼容数据结构 ==========


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


# ========== LegalMultiAgentDebate：向后兼容适配器 ==========


def _map_winner(new_winner: str) -> str:
    """将新版判决 winner 映射为旧版期望值。"""
    mapping = {
        "原告胜诉": "原告",
        "被告胜诉": "被告",
        "部分支持": "部分支持",
        "无法判断": "无法判断",
    }
    return mapping.get(new_winner, new_winner)


class LegalMultiAgentDebate:
    """
    向后兼容：旧版多智能体辩论接口。

    内部委托给 ``CourtOrchestrator``，将结果适配为旧版数据结构。
    供 ``backend/api/routes.py`` 的 ``/multi-agents/debate`` 端点使用（deprecated）。
    """

    def __init__(self, llm_gateway: Optional[LLMGateway] = None) -> None:
        gw = llm_gateway or default_gateway
        self._orchestrator = CourtOrchestrator(
            gateway=gw,
            rag=default_rag,
            skill_registry=default_skill_registry,
        )
        self._gateway = gw

    async def run(
        self,
        case: str,
        use_llm: bool = True,
        max_rounds: int = 3,
        **kwargs: Any,
    ) -> MultiAgentDebateResult:
        """旧版 run 接口，委托给 CourtOrchestrator.stream_trial。"""
        if not use_llm or not self._gateway.is_available:
            return self._fallback_result(case, max_rounds)

        rounds = max(1, min(max_rounds, 5))
        try:
            result_dict = await self._consume_stream(case, rounds)
        except Exception as exc:
            logger.warning("CourtOrchestrator 庭审失败，使用回退结果: %s", exc, exc_info=True)
            return self._fallback_result(case, max_rounds)

        return self._adapt_result(case, result_dict)

    async def _consume_stream(self, case: str, rounds: int) -> dict[str, Any]:
        """消费 stream_trial 事件流，返回 done 事件中的 result。"""
        final_result: dict[str, Any] = {}
        async for event in self._orchestrator.stream_trial(case, rounds=rounds):
            if event.get("type") == "done":
                final_result = event.get("result", {})
            elif event.get("type") == "error":
                logger.warning("庭审流事件错误: %s", event.get("message", ""))
        return final_result

    def _adapt_result(self, case: str, result: dict[str, Any]) -> MultiAgentDebateResult:
        """将新版 stream_trial result dict 适配为旧版 MultiAgentDebateResult。"""
        speeches: list[dict[str, Any]] = result.get("speeches", [])

        # 提取开场白（round=0 的 judge 发言）
        opening = ""
        for s in speeches:
            if s.get("round") == 0 and s.get("role") in ("judge", "chief_judge"):
                opening = s.get("text", "")
                break
        if not opening:
            opening = "（庭审开场白生成失败，已跳过）"

        # 按轮次提取原被告陈述
        rounds_map: dict[int, dict[str, str]] = {}
        for s in speeches:
            rn = s.get("round", 0)
            if rn < 1:
                continue
            role = s.get("role", "")
            kind = s.get("kind", "")
            text = s.get("text", "")
            if rn not in rounds_map:
                rounds_map[rn] = {"plaintiff": "", "defendant": ""}
            if role == "plaintiff" and kind in ("statement", "opening", ""):
                if not rounds_map[rn]["plaintiff"]:
                    rounds_map[rn]["plaintiff"] = text
            elif role == "defendant" and kind in ("statement", "opening", ""):
                if not rounds_map[rn]["defendant"]:
                    rounds_map[rn]["defendant"] = text

        debate_rounds = [
            DebateRound(
                round_num=rn,
                plaintiff_statement=rounds_map[rn]["plaintiff"] or "（原告未陈述）",
                defendant_statement=rounds_map[rn]["defendant"] or "（被告未答辩）",
            )
            for rn in sorted(rounds_map.keys())
        ]
        if not debate_rounds:
            debate_rounds = [DebateRound(1, "（无辩论记录）", "（无辩论记录）")]

        # 适配判决
        verdict_dict = result.get("verdict")
        if verdict_dict:
            winner = _map_winner(verdict_dict.get("winner", "无法判断"))
            judge_verdict = JudgeVerdict(
                winner=winner,
                plaintiff_win_rate=100.0 if winner == "原告" else (0.0 if winner == "被告" else 50.0),
                defendant_win_rate=100.0 if winner == "被告" else (0.0 if winner == "原告" else 50.0),
                key_points=[],
                reasoning=verdict_dict.get("reasoning", ""),
                action_suggestions=[],
            )
            judge_summary = verdict_dict.get("full_text", "") or verdict_dict.get("reasoning", "")
        else:
            judge_verdict = JudgeVerdict(
                winner="无法判断",
                plaintiff_win_rate=50,
                defendant_win_rate=50,
                key_points=["庭审未生成有效判决"],
                reasoning="庭审未生成有效判决。",
                action_suggestions=["请检查 LLM 配置并重试"],
            )
            judge_summary = "庭审未生成有效判决。"

        # 构建步骤列表
        steps = ["审判长：开庭并拆分案件事实"]
        for r in debate_rounds:
            steps.append(f"第 {r.round_num} 轮 - 原告陈述")
            steps.append(f"第 {r.round_num} 轮 - 被告答辩")
        steps.append("法官：做出最终判决")

        return MultiAgentDebateResult(
            case=case,
            research_summary=opening,
            debate_rounds=debate_rounds,
            judge_verdict=judge_verdict,
            judge_summary=judge_summary,
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
            action_suggestions=["检查 LLM API Key 配置"],
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

multi_agent_debate = LegalMultiAgentDebate()
