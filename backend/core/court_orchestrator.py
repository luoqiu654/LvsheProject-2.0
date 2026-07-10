"""法庭 LangGraph 主编排器（v3.3 专家会诊重构）。

1 主 agent（``CourtOrchestrator``）+ 3 子 agent（``PlaintiffAgent``/``DefendantAgent``/``JudgeAgent``）。

设计要点：
1. ``CourtState`` dataclass 承载整场庭审状态（发言 / 追问 / 用户回答 / 证据 / 判决）。
2. ``_build_graph`` 构建 LangGraph 状态图（可选依赖：langgraph 未安装时返回 None，
   不影响导入）。图结构文档化状态流转：opening → evidence_inquiry → user_evidence_question
   → plaintiff_stmt → defendant_stmt → judge_decision（↔ inquiry_answer）→ verdict → verdict_check。
3. ``stream_trial`` 用顺序 async 逻辑模拟状态流转（比纯 LangGraph 异步流式 + 用户问答回调更可控），
   流式 yield SSE 事件 dict，事件类型与现有 ``multi_agents.py`` 一致：
   thinking_note / thinking / speech / speech_end / evidence_list / user_question /
   user_answer / verdict / round_end / done / error。
4. 法官不端水：``check_rebuttal`` 检测端水 / 无法判断（用户没说"不知道"时）→ 打回重审，
   最多重试 2 次后强制接受，避免无限循环。
5. 每个节点 try/except，异常 yield error 事件但继续流程（不整体中断）。

兼容：不修改 ``routes.py`` 的 /multi-agents/debate 和 ``expert_routes.py`` 的 /trial/stream。
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, AsyncGenerator, Callable, Optional

from backend.core.court_agents import (
    DefendantAgent,
    EvidenceItem,
    JudgeAgent,
    PlaintiffAgent,
    Verdict,
)
from backend.core.llm_gateway import LLMGateway, LLMGatewayError
from backend.core.multi_agents import (
    KIND_ANSWER,
    KIND_INQUIRY,
    KIND_OPENING,
    KIND_STATEMENT,
    ROLE_DEFENDANT,
    ROLE_JUDGE,
    ROLE_PLAINTIFF,
    ROLE_VERDICT,
    UNCLEAR_PATTERNS,
    USER_UNKNOWN_PATTERNS,
)
from backend.core.rag import LegalRAG
from backend.core.skills import SkillRegistry


# ========== 状态 ==========


@dataclass
class CourtState:
    """整场庭审的状态机数据。"""

    case: str
    rounds_planned: int
    current_round: int = 0
    # 所有发言 [{role, kind, text, round}]（role 与 multi_agents ROLE_* 一致）
    speeches: list[dict] = field(default_factory=list)
    # 法官追问历史 [{question, target, round}]
    judge_questions: list[dict] = field(default_factory=list)
    # 用户回答 [{question_id, question, answer/content, round}]
    user_answers: list[dict] = field(default_factory=list)
    # 用户是否明确说"不知道"（触发证据不足判决）
    user_said_unknown: bool = False
    # 法官梳理的关键证据清单
    evidence_items: list[EvidenceItem] = field(default_factory=list)
    # 最终判决
    verdict: Optional[Verdict] = None
    # 判决是否需打回重审
    needs_rebuttal: bool = False
    # 判决打回重试次数
    retry_count: int = 0
    # 错误信息（非致命，流程继续）
    error: Optional[str] = None


# ========== 编排器 ==========


class CourtOrchestrator:
    """1 主 agent + 3 子 agent 的 LangGraph 编排器。

    主 agent（本类）负责状态流转与 SSE 事件编排；
    3 个子 agent（plaintiff/defendant/judge）负责具体发言与决策。
    """

    # 判决打回最大重试次数（避免无限循环）
    _MAX_VERDICT_RETRIES = 2
    # 单轮法官追问最大次数（避免无限追问）
    _MAX_INQUIRIES_PER_ROUND = 4

    def __init__(
        self,
        gateway: LLMGateway,
        rag: Optional[LegalRAG] = None,
        skill_registry: Optional[SkillRegistry] = None,
    ) -> None:
        self.gateway = gateway
        self.rag = rag
        self.skill_registry = skill_registry

        self.plaintiff = PlaintiffAgent(
            gateway=gateway, rag=rag, skill_registry=skill_registry,
        )
        self.defendant = DefendantAgent(
            gateway=gateway, rag=rag, skill_registry=skill_registry,
        )
        self.judge = JudgeAgent(
            gateway=gateway, rag=rag, skill_registry=skill_registry,
        )
        # LangGraph 状态图（可选依赖；未安装 langgraph 时为 None）
        self.graph = self._build_graph()

    # ========== LangGraph 状态图（可选依赖）==========

    def _build_graph(self):
        """构建 LangGraph 状态图。

        langgraph 未安装时返回 None，不影响 orchestrator 导入与 stream_trial 执行。
        stream_trial 用顺序 async 逻辑驱动状态流转，不依赖此图的编译执行。
        """
        try:
            from langgraph.graph import END, StateGraph
        except ImportError:
            return None

        graph = StateGraph(CourtState)
        # Nodes（方法签名为 async generator，图仅做结构文档化，不实际编译执行）
        graph.add_node("opening", self._node_opening)
        graph.add_node("evidence_inquiry", self._node_evidence_inquiry)
        graph.add_node("user_evidence_question", self._node_user_evidence_question)
        graph.add_node("plaintiff_stmt", self._node_plaintiff_stmt)
        graph.add_node("defendant_stmt", self._node_defendant_stmt)
        graph.add_node("judge_decision", self._node_judge_decision)
        graph.add_node("inquiry_answer", self._node_inquiry_answer)
        graph.add_node("verdict", self._node_verdict)
        graph.add_node("verdict_check", self._node_verdict_check)
        # Edges
        graph.set_entry_point("opening")
        graph.add_edge("opening", "evidence_inquiry")
        graph.add_edge("evidence_inquiry", "user_evidence_question")
        graph.add_edge("user_evidence_question", "plaintiff_stmt")
        graph.add_edge("plaintiff_stmt", "defendant_stmt")
        graph.add_edge("defendant_stmt", "judge_decision")
        graph.add_conditional_edges(
            "judge_decision",
            self._route_after_judge_decision,
            {
                "ask": "inquiry_answer",
                "verdict": "verdict",
                "more_rounds": "plaintiff_stmt",
            },
        )
        graph.add_edge("inquiry_answer", "judge_decision")
        graph.add_edge("verdict", "verdict_check")
        graph.add_conditional_edges(
            "verdict_check",
            self._route_after_verdict_check,
            {
                "accept": END,
                "rebuttal": "verdict",
            },
        )
        try:
            return graph.compile()
        except Exception:
            return None

    # ========== 路由函数（供 LangGraph 条件边）==========

    @staticmethod
    def _route_after_judge_decision(state: CourtState) -> str:
        """judge_decision 后的路由：'ask' / 'verdict' / 'more_rounds'。"""
        decision = getattr(state, "_last_decision", None)
        if isinstance(decision, dict) and decision.get("should_ask"):
            return "ask"
        if state.current_round >= state.rounds_planned:
            return "verdict"
        return "more_rounds"

    @staticmethod
    def _route_after_verdict_check(state: CourtState) -> str:
        """verdict_check 后的路由：'accept' / 'rebuttal'。"""
        if state.needs_rebuttal and state.retry_count < CourtOrchestrator._MAX_VERDICT_RETRIES:
            return "rebuttal"
        return "accept"

    # ========== 主入口：流式庭审 ==========

    async def stream_trial(
        self,
        case: str,
        rounds: int = 2,
        answer_callback: Optional[Callable[..., Any]] = None,
    ) -> AsyncGenerator[dict[str, Any], None]:
        """流式执行庭审，yield SSE 事件 dict。

        事件类型与 ``multi_agents.py`` 的 ``stream_trial_interactive`` 一致：
        - trial_started: {trial_id}
        - thinking_note: {role, text, round} 编排提示（离散步骤）
        - thinking: {role, text, round} 模型 reasoning_content（段落）
        - speech: {role, kind, text, round} 发言
        - speech_end: {role, kind, round}
        - tool_call: {role, tool, input, round} 自主 Agent 工具调用记录
        - tool_result: {role, tool, output, round} 工具调用结果
        - evidence_list: {items, round}
        - user_question: {question_id, question, context, round}
        - user_answer: {question_id, answer, round}
        - verdict: {verdict, round}
        - round_end: {round}
        - done: {trial_id, result}
        - error: {message, round?}

        Args:
            case: 案件描述
            rounds: 辩论轮数（1-5）
            answer_callback: async 回调，向用户追问并等待回答。
                兼容两种签名：``(question_id, question, context) -> str``（expert_routes.py）
                和 `` (question) -> str``。
        """
        rounds = max(1, min(rounds, 5))
        trial_id = self._new_trial_id()
        state = CourtState(case=case, rounds_planned=rounds)

        yield {"type": "trial_started", "trial_id": trial_id}

        try:
            # 1. 法官开庭陈述
            async for ev in self._node_opening(state):
                yield ev

            # 2. 法官梳理证据清单
            async for ev in self._node_evidence_inquiry(state):
                yield ev

            # 3. 向用户追问证据（target_party="user"）
            async for ev in self._node_user_evidence_question(state, answer_callback):
                yield ev

            # 4. 多轮辩论
            for rn in range(1, rounds + 1):
                state.current_round = rn
                try:
                    # 原告陈述
                    async for ev in self._node_plaintiff_stmt(state):
                        yield ev
                    # 被告答辩
                    async for ev in self._node_defendant_stmt(state):
                        yield ev
                    # 法官决策 + 追问循环（judge_decision ↔ inquiry_answer）
                    async for ev in self._node_judge_decision_and_inquiry(
                        state, answer_callback,
                    ):
                        yield ev
                except Exception as exc:
                    state.error = str(exc)
                    yield {
                        "type": "error",
                        "message": f"第 {rn} 轮辩论出错：{exc}（已跳过，继续）",
                        "round": rn,
                    }
                yield {"type": "round_end", "round": rn}

            # 5. 判决 + 打回检查
            async for ev in self._node_verdict_and_check(state, answer_callback):
                yield ev

            # 6. 完成
            result = self._build_result(state, trial_id)
            yield {"type": "done", "trial_id": trial_id, "result": result}

        except Exception as exc:
            yield {"type": "error", "message": str(exc)}

    # ========== 节点：开庭陈述 ==========

    async def _node_opening(
        self, state: CourtState,
    ) -> AsyncGenerator[dict[str, Any], None]:
        """法官开庭陈述（流式 + reasoning）。"""
        yield {
            "type": "thinking_note",
            "role": ROLE_JUDGE,
            "text": "法官正在开庭陈述...",
            "round": 0,
        }
        opening_text = ""
        try:
            async for kind, text in self.judge.speak(
                context=(
                    "请作为中立法官宣布开庭，介绍案情、明确争议焦点，"
                    "并组织原被告双方进入辩论环节。用庄重威严的庭审语言。"
                ),
                case=state.case,
                history=[],
                temperature=0.5,
            ):
                if kind == "reasoning":
                    yield {
                        "type": "thinking",
                        "role": ROLE_JUDGE,
                        "text": text,
                        "round": 0,
                    }
                else:
                    opening_text += text
                    yield {
                        "type": "speech",
                        "role": ROLE_JUDGE,
                        "kind": KIND_OPENING,
                        "text": text,
                        "round": 0,
                    }
        except Exception as exc:
            yield {
                "type": "error",
                "message": f"开庭陈述生成失败：{exc}",
                "round": 0,
            }
        if not opening_text:
            opening_text = self._fallback_opening(state.case)
            yield {
                "type": "speech",
                "role": ROLE_JUDGE,
                "kind": KIND_OPENING,
                "text": opening_text,
                "round": 0,
            }
        yield {
            "type": "speech_end",
            "role": ROLE_JUDGE,
            "kind": KIND_OPENING,
            "round": 0,
        }
        state.speeches.append({
            "role": ROLE_JUDGE,
            "kind": KIND_OPENING,
            "text": opening_text,
            "round": 0,
        })

    # ========== 节点：证据梳理 ==========

    async def _node_evidence_inquiry(
        self, state: CourtState,
    ) -> AsyncGenerator[dict[str, Any], None]:
        """法官梳理本案所需关键证据清单。"""
        yield {
            "type": "thinking_note",
            "role": ROLE_JUDGE,
            "text": "法官正在梳理本案所需的关键证据清单...",
            "round": 0,
        }
        history = self._build_history(state)
        try:
            evidence_items = await self.judge.generate_evidence_inquiry(
                state.case, history,
            )
        except Exception:
            evidence_items = []
        state.evidence_items = evidence_items

        if not evidence_items:
            return

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
        evidence_speech = self._format_evidence_speech(evidence_items)
        if evidence_speech:
            yield {
                "type": "speech",
                "role": ROLE_JUDGE,
                "kind": KIND_INQUIRY,
                "text": evidence_speech,
                "round": 0,
            }
            yield {
                "type": "speech_end",
                "role": ROLE_JUDGE,
                "kind": KIND_INQUIRY,
                "round": 0,
            }
            state.speeches.append({
                "role": ROLE_JUDGE,
                "kind": KIND_INQUIRY,
                "text": evidence_speech,
                "round": 0,
            })

    # ========== 节点：向用户追问证据 ==========

    async def _node_user_evidence_question(
        self,
        state: CourtState,
        answer_callback: Optional[Callable[..., Any]],
    ) -> AsyncGenerator[dict[str, Any], None]:
        """对 target_party='user' 的证据，向用户追问。"""
        if not state.evidence_items or answer_callback is None:
            return

        for idx, ev in enumerate(state.evidence_items):
            if ev.target_party != "user":
                continue
            question_id = f"ev_{idx}"
            question = (
                f"法官要求您确认证据：{ev.name}\n"
                f"为何关键：{ev.why_key}\n"
                f"您是否持有该证据？如有，请说明证据内容。"
            )
            context = (
                f"该证据（{ev.name}）对本案判决有重大影响，"
                f"需当事人（您）确认是否持有。"
                f"若您不持有或不清楚，请明确说明。"
            )
            yield {
                "type": "user_question",
                "question_id": question_id,
                "question": question,
                "context": context,
                "evidence_name": ev.name,
                "round": 0,
            }
            answer = await self._call_answer_callback(
                answer_callback, question_id, question, context,
            )
            yield {
                "type": "user_answer",
                "question_id": question_id,
                "answer": answer,
                "round": 0,
            }
            if self._is_user_unknown(answer):
                state.user_said_unknown = True
            state.user_answers.append({
                "question_id": question_id,
                "question": question,
                "answer": answer,
                "content": answer,
                "round": 0,
            })

    # ========== 节点：原告陈述 ==========

    async def _node_plaintiff_stmt(
        self, state: CourtState,
    ) -> AsyncGenerator[dict[str, Any], None]:
        """原告陈述（流式 + reasoning）。"""
        rn = state.current_round
        yield {
            "type": "thinking_note",
            "role": ROLE_PLAINTIFF,
            "text": f"原告正在准备第 {rn} 轮陈述...",
            "round": rn,
        }
        # 展示原告调用 law_search 工具检索法律条文（自主 Agent 工具调用记录）
        yield {
            "type": "tool_call",
            "role": ROLE_PLAINTIFF,
            "tool": "law_search",
            "input": state.case[:200],
            "round": rn,
        }
        plaintiff_law_context = await self.plaintiff._retrieve_law_context(
            state.case,
        )
        if plaintiff_law_context:
            yield {
                "type": "tool_result",
                "role": ROLE_PLAINTIFF,
                "tool": "law_search",
                "output": plaintiff_law_context[:500],
                "round": rn,
            }
        context = (
            f"这是第 {rn} 轮辩论。请全面陈述诉讼请求、事实和理由，"
            if rn == 1
            else f"这是第 {rn} 轮辩论。请针对被告之前的抗辩进行反驳，"
        )
        history = self._build_history(state)
        speech_text = ""
        try:
            async for kind, text in self.plaintiff.speak(
                context=context,
                case=state.case,
                history=history,
                temperature=0.6,
            ):
                if kind == "reasoning":
                    yield {
                        "type": "thinking",
                        "role": ROLE_PLAINTIFF,
                        "text": text,
                        "round": rn,
                    }
                else:
                    speech_text += text
                    yield {
                        "type": "speech",
                        "role": ROLE_PLAINTIFF,
                        "kind": KIND_STATEMENT,
                        "text": text,
                        "round": rn,
                    }
        except Exception as exc:
            yield {
                "type": "error",
                "message": f"原告陈述生成失败：{exc}",
                "round": rn,
            }
        if not speech_text:
            speech_text = self._fallback_speech("plaintiff", state.case, rn)
            yield {
                "type": "speech",
                "role": ROLE_PLAINTIFF,
                "kind": KIND_STATEMENT,
                "text": speech_text,
                "round": rn,
            }
        yield {
            "type": "speech_end",
            "role": ROLE_PLAINTIFF,
            "kind": KIND_STATEMENT,
            "round": rn,
        }
        state.speeches.append({
            "role": ROLE_PLAINTIFF,
            "kind": KIND_STATEMENT,
            "text": speech_text,
            "round": rn,
        })

    # ========== 节点：被告答辩 ==========

    async def _node_defendant_stmt(
        self, state: CourtState,
    ) -> AsyncGenerator[dict[str, Any], None]:
        """被告答辩（流式 + reasoning）。"""
        rn = state.current_round
        yield {
            "type": "thinking_note",
            "role": ROLE_DEFENDANT,
            "text": f"被告正在准备第 {rn} 轮答辩...",
            "round": rn,
        }
        # 展示被告调用 law_search 工具检索法律条文（自主 Agent 工具调用记录）
        yield {
            "type": "tool_call",
            "role": ROLE_DEFENDANT,
            "tool": "law_search",
            "input": state.case[:200],
            "round": rn,
        }
        defendant_law_context = await self.defendant._retrieve_law_context(
            state.case,
        )
        if defendant_law_context:
            yield {
                "type": "tool_result",
                "role": ROLE_DEFENDANT,
                "tool": "law_search",
                "output": defendant_law_context[:500],
                "round": rn,
            }
        context = (
            "这是第一轮答辩，请针对原告的诉讼请求进行全面抗辩。"
            if rn == 1
            else f"这是第 {rn} 轮答辩，请针对原告最新主张进行抗辩。"
        )
        history = self._build_history(state)
        speech_text = ""
        try:
            async for kind, text in self.defendant.speak(
                context=context,
                case=state.case,
                history=history,
                temperature=0.6,
            ):
                if kind == "reasoning":
                    yield {
                        "type": "thinking",
                        "role": ROLE_DEFENDANT,
                        "text": text,
                        "round": rn,
                    }
                else:
                    speech_text += text
                    yield {
                        "type": "speech",
                        "role": ROLE_DEFENDANT,
                        "kind": KIND_STATEMENT,
                        "text": text,
                        "round": rn,
                    }
        except Exception as exc:
            yield {
                "type": "error",
                "message": f"被告答辩生成失败：{exc}",
                "round": rn,
            }
        if not speech_text:
            speech_text = self._fallback_speech("defendant", state.case, rn)
            yield {
                "type": "speech",
                "role": ROLE_DEFENDANT,
                "kind": KIND_STATEMENT,
                "text": speech_text,
                "round": rn,
            }
        yield {
            "type": "speech_end",
            "role": ROLE_DEFENDANT,
            "kind": KIND_STATEMENT,
            "round": rn,
        }
        state.speeches.append({
            "role": ROLE_DEFENDANT,
            "kind": KIND_STATEMENT,
            "text": speech_text,
            "round": rn,
        })

    # ========== 节点：法官决策 + 追问循环 ==========

    async def _node_judge_decision_and_inquiry(
        self,
        state: CourtState,
        answer_callback: Optional[Callable[..., Any]],
    ) -> AsyncGenerator[dict[str, Any], None]:
        """法官决策 + 追问循环（judge_decision ↔ inquiry_answer）。

        循环最多 _MAX_INQUIRIES_PER_ROUND 次追问，防止无限循环。
        每次循环：judge.decide_inquiry → 若 should_ask 则追问被问方/用户 → 回到决策；
        若 !should_ask 则结束循环（由 stream_trial 决定下一轮或判决）。
        """
        rn = state.current_round
        for _ in range(self._MAX_INQUIRIES_PER_ROUND):
            yield {
                "type": "thinking_note",
                "role": ROLE_JUDGE,
                "text": f"法官正在审查第 {rn} 轮辩论，判断是否需要追问...",
                "round": rn,
            }
            history = self._build_history(state)
            try:
                decision = await self.judge.decide_inquiry(
                    state.case, history, rn,
                )
            except Exception:
                decision = {"should_ask": False, "target": "", "question": ""}

            should_ask = bool(decision.get("should_ask", False))
            question = str(decision.get("question", "")).strip()
            target = str(decision.get("target", "")).lower()

            if not should_ask or not question:
                yield {
                    "type": "thinking_note",
                    "role": ROLE_JUDGE,
                    "text": f"法官审查后认为第 {rn} 轮辩论无需追问。",
                    "round": rn,
                }
                return  # 结束追问循环，交回 stream_trial

            # 法官追问（一次性发出）
            yield {
                "type": "speech",
                "role": ROLE_JUDGE,
                "kind": KIND_INQUIRY,
                "text": question,
                "round": rn,
            }
            yield {
                "type": "speech_end",
                "role": ROLE_JUDGE,
                "kind": KIND_INQUIRY,
                "round": rn,
            }
            state.speeches.append({
                "role": ROLE_JUDGE,
                "kind": KIND_INQUIRY,
                "text": question,
                "round": rn,
            })
            state.judge_questions.append({
                "question": question,
                "target": target,
                "round": rn,
            })

            # 被问方回答
            if target in ("plaintiff", "both"):
                async for ev in self._stream_party_answer(
                    state, "plaintiff", question, rn, answer_callback,
                ):
                    yield ev
            if target in ("defendant", "both"):
                async for ev in self._stream_party_answer(
                    state, "defendant", question, rn, answer_callback,
                ):
                    yield ev
            if target == "user":
                # 直接向用户追问
                async for ev in self._ask_user_direct(
                    state, question, rn, answer_callback,
                ):
                    yield ev
            # 回到循环顶部，judge 再次决策

    async def _stream_party_answer(
        self,
        state: CourtState,
        party: str,
        judge_question: str,
        rn: int,
        answer_callback: Optional[Callable[..., Any]],
    ) -> AsyncGenerator[dict[str, Any], None]:
        """被问方（原告/被告）回答法官追问，流式 yield。

        若回答含"不清楚"等关键词，触发向用户追问。
        """
        agent = self.plaintiff if party == "plaintiff" else self.defendant
        role = ROLE_PLAINTIFF if party == "plaintiff" else ROLE_DEFENDANT
        role_label = "原告" if party == "plaintiff" else "被告"
        yield {
            "type": "thinking_note",
            "role": role,
            "text": f"{role_label}正在针对法官追问组织回答...",
            "round": rn,
        }
        history = self._build_history(state)
        answer_text = ""
        try:
            async for kind, text in agent.answer_question(
                question=judge_question,
                case=state.case,
                history=history,
            ):
                if kind == "reasoning":
                    yield {
                        "type": "thinking",
                        "role": role,
                        "text": text,
                        "round": rn,
                    }
                else:
                    answer_text += text
                    yield {
                        "type": "speech",
                        "role": role,
                        "kind": KIND_ANSWER,
                        "text": text,
                        "round": rn,
                    }
        except Exception as exc:
            yield {
                "type": "error",
                "message": f"{role_label}回答生成失败：{exc}",
                "round": rn,
            }
        if not answer_text:
            answer_text = f"（{role_label}暂无回应）"
            yield {
                "type": "speech",
                "role": role,
                "kind": KIND_ANSWER,
                "text": answer_text,
                "round": rn,
            }
        yield {
            "type": "speech_end",
            "role": role,
            "kind": KIND_ANSWER,
            "round": rn,
        }
        state.speeches.append({
            "role": role,
            "kind": KIND_ANSWER,
            "text": answer_text,
            "round": rn,
        })

        # 证据检查：回答含"不清楚" → 向用户询问
        if self._needs_user_input(answer_text) and answer_callback is not None:
            async for ev in self._ask_user_for_unclear(
                state, party, answer_text, judge_question, rn, answer_callback,
            ):
                yield ev

    async def _ask_user_for_unclear(
        self,
        state: CourtState,
        party: str,
        party_answer: str,
        judge_question: str,
        rn: int,
        answer_callback: Callable[..., Any],
    ) -> AsyncGenerator[dict[str, Any], None]:
        """因原被告回答含"不清楚"，向用户追问补充信息。"""
        role_label = "原告" if party == "plaintiff" else "被告"
        question_id = f"q{rn}_{party}"
        question = (
            f"法官追问：{judge_question[:200]}\n\n"
            f"{role_label}代理人回答：\"{party_answer[:300]}\"\n\n"
            f"由于{role_label}方对上述关键事实不清楚，请您（当事人）确认："
            f"您是否持有相关证据？事实经过究竟如何？请详细说明。"
        )
        context = (
            f"第 {rn} 轮辩论中，法官就关键事实追问{role_label}方，"
            f"但{role_label}方表示不清楚。该事实对判决有重大影响，"
            f"需要您（当事人）提供补充信息以做出公正判决。"
            f"若您也不清楚，请在回答中明确说明。"
        )
        yield {
            "type": "user_question",
            "question_id": question_id,
            "question": question,
            "context": context,
            "round": rn,
        }
        answer = await self._call_answer_callback(
            answer_callback, question_id, question, context,
        )
        yield {
            "type": "user_answer",
            "question_id": question_id,
            "answer": answer,
            "round": rn,
        }
        if self._is_user_unknown(answer):
            state.user_said_unknown = True
        state.user_answers.append({
            "question_id": question_id,
            "question": question,
            "answer": answer,
            "content": answer,
            "round": rn,
        })

    async def _ask_user_direct(
        self,
        state: CourtState,
        judge_question: str,
        rn: int,
        answer_callback: Optional[Callable[..., Any]],
    ) -> AsyncGenerator[dict[str, Any], None]:
        """法官直接向用户追问。"""
        if answer_callback is None:
            return
        question_id = f"q{rn}_user"
        question = judge_question
        context = (
            f"第 {rn} 轮辩论中，法官直接向您（当事人）追问。"
            f"请如实回答，若不清楚请明确说明。"
        )
        yield {
            "type": "user_question",
            "question_id": question_id,
            "question": question,
            "context": context,
            "round": rn,
        }
        answer = await self._call_answer_callback(
            answer_callback, question_id, question, context,
        )
        yield {
            "type": "user_answer",
            "question_id": question_id,
            "answer": answer,
            "round": rn,
        }
        if self._is_user_unknown(answer):
            state.user_said_unknown = True
        state.user_answers.append({
            "question_id": question_id,
            "question": question,
            "answer": answer,
            "content": answer,
            "round": rn,
        })

    # ========== 节点：判决 + 打回检查 ==========

    async def _node_verdict_and_check(
        self,
        state: CourtState,
        answer_callback: Optional[Callable[..., Any]] = None,
    ) -> AsyncGenerator[dict[str, Any], None]:
        """生成判决 + 打回检查（含重试循环）。

        - 判决前显式检索法律条文并展示 tool_call/tool_result 事件（自主 Agent 工具调用）
        - judge.render_verdict 生成判决（内部设置 _user_said_unknown）
        - judge.check_rebuttal 检查是否打回
        - 端水 / 无法判断（用户没说"不知道"）→ 打回，retry_count++
          打回原因为"需继续追问用户"时，先向用户追问关键证据
        - retry_count >= _MAX_VERDICT_RETRIES → 强制接受
        """
        rn = state.rounds_planned + 1
        while True:
            yield {
                "type": "thinking_note",
                "role": ROLE_JUDGE,
                "text": "法官正在综合所有辩论和证据，撰写判决书...",
                "round": rn,
            }
            # 法官判决前显式检索法律条文，展示自主 Agent 工具调用记录
            yield {
                "type": "tool_call",
                "role": ROLE_JUDGE,
                "tool": "law_search",
                "input": state.case[:200],
                "round": rn,
            }
            law_context = await self.judge._retrieve_law_context(state.case)
            if law_context:
                yield {
                    "type": "tool_result",
                    "role": ROLE_JUDGE,
                    "tool": "law_search",
                    "output": law_context[:500],
                    "round": rn,
                }
            history = self._build_history(state)
            try:
                verdict = await self.judge.render_verdict(
                    state.case, history, state.user_answers,
                )
            except Exception as exc:
                verdict = self._fallback_verdict(state.case, str(exc))
                yield {
                    "type": "error",
                    "message": f"判决生成失败：{exc}",
                    "round": rn,
                }
            state.verdict = verdict
            # 同步 user_said_unknown 到 state（judge.render_verdict 已设置内部状态）
            state.user_said_unknown = self.judge._user_said_unknown

            yield {
                "type": "verdict",
                "verdict": self._verdict_to_dict(verdict),
                "round": rn,
            }

            # 打回检查
            state.needs_rebuttal = False
            try:
                needs_rebuttal, reason = self.judge.check_rebuttal(verdict)
            except Exception:
                needs_rebuttal, reason = False, ""
            if needs_rebuttal and state.retry_count < self._MAX_VERDICT_RETRIES:
                state.retry_count += 1
                state.needs_rebuttal = True
                # 如果打回原因是"需继续追问用户"，先向用户追问关键证据
                if "追问用户" in reason and answer_callback is not None:
                    question_id = f"verdict_retry_{state.retry_count}"
                    question = (
                        "为了做出公正判决，请您补充关键信息：您是否持有与本案相关的"
                        "书面证据（如合同、收据、转账记录等）？如有请详细说明。"
                    )
                    context = (
                        "法官在判决前需要您确认关键证据是否持有，以便做出明确判决。"
                    )
                    yield {
                        "type": "user_question",
                        "question_id": question_id,
                        "question": question,
                        "context": context,
                        "round": rn,
                    }
                    answer = await self._call_answer_callback(
                        answer_callback, question_id, question, context,
                    )
                    yield {
                        "type": "user_answer",
                        "question_id": question_id,
                        "answer": answer,
                        "round": rn,
                    }
                    if self._is_user_unknown(answer):
                        state.user_said_unknown = True
                    state.user_answers.append({
                        "question_id": question_id,
                        "question": question,
                        "answer": answer,
                        "content": answer,
                        "round": rn,
                    })
                yield {
                    "type": "thinking_note",
                    "role": ROLE_JUDGE,
                    "text": (
                        f"判决被法官打回重审（原因：{reason}），"
                        f"正在重新撰写（第 {state.retry_count} 次重试）..."
                    ),
                    "round": rn,
                }
                continue  # 回到 verdict
            # 接受判决
            break

    # ========== LangGraph 节点占位（供 _build_graph 注册）==========
    # 以下节点在 stream_trial 中由组合方法（_node_judge_decision_and_inquiry /
    # _node_verdict_and_check）覆盖，此处仅提供 LangGraph 图结构注册所需的占位。
    # opening / evidence_inquiry / user_evidence_question / plaintiff_stmt /
    # defendant_stmt 节点直接复用上方同名流式 async generator 方法。

    async def _node_judge_decision(self, state: CourtState) -> CourtState:
        return state

    async def _node_inquiry_answer(self, state: CourtState) -> CourtState:
        return state

    async def _node_verdict(self, state: CourtState) -> CourtState:
        return state

    async def _node_verdict_check(self, state: CourtState) -> CourtState:
        return state

    # ========== 工具方法 ==========

    @staticmethod
    def _now() -> str:
        return datetime.now().isoformat()

    @staticmethod
    def _new_trial_id() -> str:
        return uuid.uuid4().hex[:16]

    @staticmethod
    def _build_history(state: CourtState) -> list[dict]:
        """将 state.speeches 转为子 agent 期望的 history 格式。

        子 agent ``_format_history`` 读取 ``role`` / ``content`` 键。
        """
        return [
            {"role": s["role"], "content": s["text"]}
            for s in state.speeches
        ]

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

    @staticmethod
    def _needs_user_input(answer: str) -> bool:
        """检查回答是否表明当事人不清楚关键事实（需向用户询问）。"""
        if not answer:
            return False
        return any(p in answer for p in UNCLEAR_PATTERNS)

    @staticmethod
    def _is_user_unknown(user_answer: str) -> bool:
        """用户是否明确表示不知道（触发证据不足判决）。"""
        if not user_answer:
            return False
        return any(p in user_answer for p in USER_UNKNOWN_PATTERNS)

    @staticmethod
    def _verdict_to_dict(verdict: Verdict) -> dict[str, Any]:
        """将 Verdict 转为 SSE 事件 dict。"""
        return {
            "winner": verdict.winner,
            "reasoning": verdict.reasoning,
            "full_text": verdict.full_text,
            "compensation": verdict.compensation,
        }

    @staticmethod
    def _fallback_opening(case: str) -> str:
        return (
            "## 审判长开场白\n\n"
            "现在开庭。本案的基本情况如下：\n\n"
            f"{case[:500]}\n\n"
            "经审查，本案的核心争议焦点为：双方当事人的权利义务关系及责任承担问题。\n"
            "现在进入法庭调查和辩论阶段。请原告首先陈述诉讼请求、事实和理由。"
        )

    @staticmethod
    def _fallback_speech(role: str, case: str, round_num: int) -> str:
        names = {"plaintiff": "原告", "defendant": "被告", "judge": "法官"}
        name = names.get(role, role)
        return (
            f"【{name}第 {round_num} 轮发言】\n"
            f"（发言生成失败，此为占位发言）\n"
            f"案件：{case[:200]}"
        )

    @staticmethod
    def _fallback_verdict(case: str, error_msg: str = "") -> Verdict:
        return Verdict(
            winner="无法判断",
            reasoning=f"判决生成失败：{error_msg}" if error_msg else "无法生成判决理由。",
            full_text=(
                "## 判决书\n\n"
                "（判决生成失败，请检查 LLM 配置后重试。）\n\n"
                f"案件：{case[:200]}"
            ),
            compensation="",
        )

    @staticmethod
    async def _call_answer_callback(
        answer_callback: Optional[Callable[..., Any]],
        question_id: str,
        question: str,
        context: str,
    ) -> str:
        """调用 answer_callback，兼容两种签名。

        优先匹配 expert_routes.py 的 3 参数签名：
            ``answer_callback(question_id, question, context) -> str``
        回退到单参数签名（任务设计文档）：
            ``answer_callback(question) -> str``
        """
        if answer_callback is None:
            return "（无回答回调）"
        try:
            return await answer_callback(question_id, question, context)
        except TypeError:
            try:
                return await answer_callback(question)
            except Exception as exc:
                return f"（用户回答失败：{exc}）"
        except Exception as exc:
            return f"（用户回答失败：{exc}）"

    def _build_result(self, state: CourtState, trial_id: str) -> dict[str, Any]:
        """构建 done 事件的 result 字段。"""
        verdict_dict = (
            self._verdict_to_dict(state.verdict) if state.verdict else None
        )
        return {
            "trial_id": trial_id,
            "case": state.case,
            "rounds": state.rounds_planned,
            "speeches": [
                {
                    "role": s["role"],
                    "kind": s.get("kind", ""),
                    "text": s["text"],
                    "round": s.get("round", 0),
                }
                for s in state.speeches
            ],
            "evidence_items": [
                {
                    "name": e.name,
                    "why_key": e.why_key,
                    "target_party": e.target_party,
                }
                for e in state.evidence_items
            ],
            "user_answers": list(state.user_answers),
            "user_said_unknown": state.user_said_unknown,
            "verdict": verdict_dict,
            "retry_count": state.retry_count,
            "created_at": self._now(),
        }
