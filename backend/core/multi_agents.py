from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass, field
from typing import Any, Optional, TypedDict

from langgraph.graph import END, START, StateGraph

from backend.config import PROJECT_ROOT
from backend.core.llm_gateway import LLMGateway, LLMGatewayError, gateway as default_gateway
from backend.core.rag import LegalRAG, rag as default_rag


@dataclass
class DebateRound:
    """
    单轮辩论记录。
    """

    round_num: int
    plaintiff_statement: str
    defendant_statement: str


@dataclass
class AgentOpinion:
    """
    单个智能体的意见。
    """

    role: str
    viewpoint: str
    content: str


@dataclass
class JudgeVerdict:
    """
    法官最终判决。
    """

    winner: str  # "原告" / "被告" / "无法判断"
    plaintiff_win_rate: float  # 原告胜诉概率 0-100
    defendant_win_rate: float  # 被告胜诉概率 0-100
    key_points: list[str]  # 关键胜负点
    reasoning: str  # 判决理由
    action_suggestions: list[str]  # 行动建议


@dataclass
class MultiAgentDebateResult:
    """
    多智能体会诊最终结果。
    """

    case: str
    research_summary: str
    debate_rounds: list[DebateRound]  # 多轮辩论记录
    judge_verdict: JudgeVerdict  # 法官明确判决
    judge_summary: str  # 法官详细总结
    steps: list[str] = field(default_factory=list)

    # 兼容旧接口
    @property
    def opinions(self) -> list[AgentOpinion]:
        """兼容旧接口，返回最后一轮的双方观点。"""
        if not self.debate_rounds:
            return []
        last_round = self.debate_rounds[-1]
        return [
            AgentOpinion(
                role="Plaintiff Advocate",
                viewpoint="权利主张方",
                content=last_round.plaintiff_statement,
            ),
            AgentOpinion(
                role="Defendant Advocate",
                viewpoint="抗辩方",
                content=last_round.defendant_statement,
            ),
        ]


class MultiAgentState(TypedDict, total=False):
    """
    LangGraph 多智能体状态（增强版：支持多轮迭代）。

    新增字段：
    - debate_round: 当前辩论轮次
    - convergence_score: 收敛分数（0-100，越高表示双方意见越接近）
    - short_term_memory: 短期记忆，存储关键论点供下一轮参考
    - should_continue: 是否继续下一轮辩论
    - plaintiff_history: 原告历史发言
    - defendant_history: 被告历史发言
    """

    case: str
    research_summary: str
    debate_rounds: list[dict]  # 辩论轮次记录
    judge_summary: str
    judge_verdict: dict  # 法官判决
    steps: list[str]
    use_llm: bool
    max_rounds: int  # 最大辩论轮数
    convergence_threshold: float  # 收敛阈值，默认 80
    debate_round: int  # 当前轮次
    convergence_score: float  # 收敛分数
    short_term_memory: list[str]  # 短期记忆：关键论点
    should_continue: bool  # 是否继续迭代
    plaintiff_history: list[str]  # 原告历史发言
    defendant_history: list[str]  # 被告历史发言
    current_plaintiff: str  # 当前轮原告发言
    current_defendant: str  # 当前轮被告发言


class LegalMultiAgentDebate:
    """
    法律多智能体会诊 / 辩论系统。

    角色：
    1. Researcher：法律检索员
    2. Plaintiff Advocate：原告代理
    3. Defendant Advocate：被告代理
    4. Judge：中立法官

    新增特性：
    - 多轮辩论（原告→被告→原告→被告...）
    - 法官明确判决（哪方胜诉、胜率多少、关键胜负点）
    - 支持配置辩论轮数
    """

    def __init__(
        self,
        llm_gateway: Optional[LLMGateway] = None,
        rag_engine: Optional[LegalRAG] = None,
    ) -> None:
        self.llm_gateway = llm_gateway or default_gateway
        self.rag_engine = rag_engine or default_rag
        self.graph = self._build_graph()

    def _build_graph(self):
        """
        构建支持多轮迭代的 LangGraph 图。

        流程：
        START -> researcher -> plaintiff -> defendant -> judge
                                                            ↓
                                                    [条件判断]
                                                继续 ↗   ↘ 结束
                                          plaintiff <-     -> END
        """
        workflow = StateGraph(MultiAgentState)

        # 添加节点
        workflow.add_node("researcher", self._researcher_node_v2)
        workflow.add_node("plaintiff", self._plaintiff_node_v2)
        workflow.add_node("defendant", self._defendant_node_v2)
        workflow.add_node("judge", self._judge_node_v2)

        # 边
        workflow.add_edge(START, "researcher")
        workflow.add_edge("researcher", "plaintiff")
        workflow.add_edge("plaintiff", "defendant")
        workflow.add_edge("defendant", "judge")

        # 条件边：法官判断是否需要继续辩论
        workflow.add_conditional_edges(
            "judge",
            self._should_continue_debate,
            {
                "continue": "plaintiff",  # 继续下一轮
                "end": END,  # 结束
            },
        )

        return workflow.compile()

    def _should_continue_debate(self, state: MultiAgentState) -> str:
        """
        条件边函数：判断是否继续辩论。

        判断条件：
        1. 未达到最大轮次
        2. 收敛分数未达到阈值
        3. 法官认为结论不明确
        """
        current_round = state.get("debate_round", 1)
        max_rounds = state.get("max_rounds", 3)
        convergence_score = state.get("convergence_score", 0.0)
        convergence_threshold = state.get("convergence_threshold", 80.0)
        should_continue = state.get("should_continue", False)

        # 条件1：达到最大轮次则结束
        if current_round >= max_rounds:
            return "end"

        # 条件2：收敛分数达到阈值则结束
        if convergence_score >= convergence_threshold:
            return "end"

        # 条件3：法官认为需要继续
        if should_continue:
            return "continue"

        # 默认结束
        return "end"

    def _calculate_similarity(self, text1: str, text2: str) -> float:
        """
        计算两段文本的相似度（基于关键词重叠的简单实现）。

        返回 0-100 的相似度分数。
        """
        # 简单的关键词提取
        def extract_keywords(text: str) -> set[str]:
            # 中文分词简化版：按常见分隔符拆分，过滤短词
            import re
            words = re.findall(r'[\u4e00-\u9fa5]{2,}', text)
            # 过滤停用词
            stopwords = {"的", "了", "是", "在", "和", "与", "或", "等", "也", "都", "就", "又", "及", "其", "此", "该", "本", "我", "你", "他", "她", "它", "们"}
            return set(w for w in words if w not in stopwords and len(w) >= 2)

        keywords1 = extract_keywords(text1)
        keywords2 = extract_keywords(text2)

        if not keywords1 or not keywords2:
            return 0.0

        intersection = keywords1 & keywords2
        union = keywords1 | keywords2

        if not union:
            return 0.0

        return len(intersection) / len(union) * 100

    def _extract_key_points(self, text: str, max_points: int = 5) -> list[str]:
        """
        从发言中提取关键论点，存入短期记忆。
        """
        # 简单实现：按句号/换行拆分，取前几句
        import re
        sentences = re.split(r'[。\n]', text)
        sentences = [s.strip() for s in sentences if s.strip() and len(s.strip()) > 10]
        return sentences[:max_points]

    async def run(
        self,
        case: str,
        use_llm: bool = True,
        max_rounds: int = 3,
        convergence_threshold: float = 80.0,
        use_graph: bool = True,
    ) -> MultiAgentDebateResult:
        """
        运行多智能体会诊。

        Args:
            case: 案件事实
            use_llm: 是否使用 LLM
            max_rounds: 最大辩论轮数，默认 3 轮
            convergence_threshold: 收敛阈值（0-100），默认 80
            use_graph: 是否使用 LangGraph 图执行（默认 True）

        新增特性：
        - 多轮自主迭代：法官判断是否需要继续辩论
        - 收敛条件：双方意见相似度达到阈值时提前结束
        - 短期记忆：每轮关键论点存入记忆供下一轮参考
        """
        if use_graph:
            return await self._run_with_graph(
                case=case,
                use_llm=use_llm,
                max_rounds=max_rounds,
                convergence_threshold=convergence_threshold,
            )
        else:
            return await self._run_legacy(
                case=case,
                use_llm=use_llm,
                max_rounds=max_rounds,
            )

    async def _run_with_graph(
        self,
        case: str,
        use_llm: bool,
        max_rounds: int,
        convergence_threshold: float,
    ) -> MultiAgentDebateResult:
        """使用 LangGraph 图执行多轮辩论。"""
        initial_state: MultiAgentState = {
            "case": case,
            "use_llm": use_llm,
            "max_rounds": max_rounds,
            "convergence_threshold": convergence_threshold,
            "steps": [],
        }

        result = await self.graph.ainvoke(initial_state)

        # 转换结果格式
        debate_rounds = [
            DebateRound(
                round_num=r["round_num"],
                plaintiff_statement=r["plaintiff_statement"],
                defendant_statement=r["defendant_statement"],
            )
            for r in result.get("debate_rounds", [])
        ]

        verdict_dict = result.get("judge_verdict", {})
        judge_verdict = JudgeVerdict(
            winner=verdict_dict.get("winner", "无法判断"),
            plaintiff_win_rate=float(verdict_dict.get("plaintiff_win_rate", 50)),
            defendant_win_rate=float(verdict_dict.get("defendant_win_rate", 50)),
            key_points=verdict_dict.get("key_points", []),
            reasoning=verdict_dict.get("reasoning", ""),
            action_suggestions=verdict_dict.get("action_suggestions", []),
        )

        return MultiAgentDebateResult(
            case=case,
            research_summary=result.get("research_summary", ""),
            debate_rounds=debate_rounds,
            judge_verdict=judge_verdict,
            judge_summary=result.get("judge_summary", ""),
            steps=result.get("steps", []),
        )

    async def _run_legacy(
        self,
        case: str,
        use_llm: bool,
        max_rounds: int,
    ) -> MultiAgentDebateResult:
        """
        传统执行方式（不使用 LangGraph 循环）。
        保留用于向后兼容和调试。
        """
        # ========== 第一轮：Researcher 检索 ==========
        research_summary = await self._do_research(case, use_llm)
        steps = ["Researcher：完成法律资料检索"]

        # ========== 多轮辩论 ==========
        debate_rounds: list[DebateRound] = []
        plaintiff_history: list[str] = []
        defendant_history: list[str] = []

        for round_num in range(1, max_rounds + 1):
            # 原告发言
            plaintiff_statement = await self._do_plaintiff_speech(
                case=case,
                research_summary=research_summary,
                round_num=round_num,
                defendant_history=defendant_history,
                use_llm=use_llm,
            )
            plaintiff_history.append(plaintiff_statement)
            steps.append(f"第 {round_num} 轮 - 原告代理：发表观点")

            # 被告发言
            defendant_statement = await self._do_defendant_speech(
                case=case,
                research_summary=research_summary,
                round_num=round_num,
                plaintiff_statement=plaintiff_statement,
                plaintiff_history=plaintiff_history,
                use_llm=use_llm,
            )
            defendant_history.append(defendant_statement)
            steps.append(f"第 {round_num} 轮 - 被告代理：发表抗辩")

            debate_rounds.append(
                DebateRound(
                    round_num=round_num,
                    plaintiff_statement=plaintiff_statement,
                    defendant_statement=defendant_statement,
                )
            )

        # ========== 法官判决 ==========
        judge_verdict, judge_summary = await self._do_judge_verdict(
            case=case,
            research_summary=research_summary,
            debate_rounds=debate_rounds,
            use_llm=use_llm,
        )
        steps.append("Judge：完成最终判决")

        return MultiAgentDebateResult(
            case=case,
            research_summary=research_summary,
            debate_rounds=debate_rounds,
            judge_verdict=judge_verdict,
            judge_summary=judge_summary,
            steps=steps,
        )

    # ========== Researcher ==========
    async def _do_research(self, case: str, use_llm: bool) -> str:
        rag_answer = await self.rag_engine.answer(
            question=case,
            top_k=3,
            use_llm_query_transform=False,
            use_llm_hyde=False,
            use_llm_answer=False,
        )

        if not rag_answer.contexts:
            return "法律检索员未在当前知识库中检索到明确相关资料。"

        lines = ["法律检索员检索到以下资料："]
        for index, item in enumerate(rag_answer.contexts, start=1):
            content = item.enriched_text.strip().replace("\n", " ")
            if len(content) > 300:
                content = content[:300] + "..."

            lines.append(
                f"{index}. 来源：{item.source}；相关度：{item.final_score:.4f}；内容：{content}"
            )

        return "\n".join(lines)

    # ========== 原告发言 ==========
    async def _do_plaintiff_speech(
        self,
        case: str,
        research_summary: str,
        round_num: int,
        defendant_history: list[str],
        use_llm: bool,
    ) -> str:
        if use_llm:
            return await self._llm_plaintiff_speech(
                case=case,
                research_summary=research_summary,
                round_num=round_num,
                defendant_history=defendant_history,
            )
        else:
            return self._fallback_plaintiff_speech(
                case=case,
                research_summary=research_summary,
                round_num=round_num,
                defendant_history=defendant_history,
            )

    async def _llm_plaintiff_speech(
        self,
        case: str,
        research_summary: str,
        round_num: int,
        defendant_history: list[str],
    ) -> str:
        # 构建被告历史观点摘要
        defendant_summary = ""
        if defendant_history:
            defendant_summary = "\n\n".join(
                f"第 {i+1} 轮被告观点：\n{opinion[:500]}"
                for i, opinion in enumerate(defendant_history)
            )

        round_instruction = ""
        if round_num == 1:
            round_instruction = "这是第一轮辩论，请全面陈述本方观点和主张。"
        else:
            round_instruction = f"这是第 {round_num} 轮辩论。请针对被告前几轮的抗辩要点进行针对性反驳，强化本方主张，提出新的论据或法律依据。不要重复之前说过的内容。"

        prompt = f"""
你现在扮演：原告代理律师

角色要求：
你代表权利主张方。请尽量从守约方、受损方、主张赔偿或解除合同的一方角度分析。

{round_instruction}

案件问题：
{case}

法律检索资料：
{research_summary}

被告历史观点：
{defendant_summary or "暂无（第一轮）"}

请输出：
1. 本轮核心主张
2. 针对被告抗辩的反驳要点
3. 新的法律依据或事实论据
4. 证据强化方向

要求：
- 使用中文
- 不要编造法条编号
- 只能基于案件信息和检索资料分析
- 每轮要有新内容，不要重复
- 保持专业但有攻击性，全力维护当事人权益
""".strip()

        try:
            return await self.llm_gateway.chat_text(
                user_message=prompt,
                system_message="你是经验丰富、辩才出众的原告代理律师，全力为当事人争取最大权益。",
                max_tokens=1000,
                temperature=0.4,
            )
        except LLMGatewayError:
            return self._fallback_plaintiff_speech(
                case=case,
                research_summary=research_summary,
                round_num=round_num,
                defendant_history=defendant_history,
            )

    def _fallback_plaintiff_speech(
        self,
        case: str,
        research_summary: str,
        round_num: int,
        defendant_history: list[str],
    ) -> str:
        if round_num == 1:
            return (
                f"【原告方第 {round_num} 轮陈述】\n"
                "1. 核心主张：被告未按合同约定履行义务，已构成违约，我方有权要求继续履行或赔偿损失。\n"
                "2. 事实依据：合同依法成立有效，对双方具有约束力。被告未按约定完成交付/履行，违反了合同义务。\n"
                "3. 法律依据：当事人一方不履行合同义务或者履行合同义务不符合约定的，应当承担继续履行、采取补救措施或者赔偿损失等违约责任。\n"
                "4. 证据清单：合同文本、付款凭证、沟通记录、催告函、损失证明。\n"
                "5. 诉讼请求：请求判令被告继续履行合同/支付违约金/赔偿实际损失。\n\n"
                f"案件：{case}\n\n"
                f"检索资料：\n{research_summary}"
            )
        else:
            return (
                f"【原告方第 {round_num} 轮反驳】\n"
                f"1. 针对被告第 {round_num-1} 轮抗辩的反驳：被告提出的抗辩理由不能成立。合同约定明确，被告违约事实清楚，不能以约定不明为由免除责任。\n"
                "2. 强化主张：即使合同部分条款约定不够详细，根据法律规定和交易习惯，也应当按照通常标准履行。被告长期不履行本身就构成根本违约。\n"
                "3. 补充证据：我方已提交充分证据证明损失实际发生，包括但不限于付款记录、沟通记录、第三方报价等。\n"
                "4. 新的法律点：被告迟延履行主要债务，经催告后在合理期限内仍未履行，我方有权解除合同并要求赔偿全部损失。\n"
                "5. 结论：被告抗辩缺乏事实和法律依据，请求法庭支持我方全部诉讼请求。\n\n"
                f"案件：{case}"
            )

    # ========== 被告发言 ==========
    async def _do_defendant_speech(
        self,
        case: str,
        research_summary: str,
        round_num: int,
        plaintiff_statement: str,
        plaintiff_history: list[str],
        use_llm: bool,
    ) -> str:
        if use_llm:
            return await self._llm_defendant_speech(
                case=case,
                research_summary=research_summary,
                round_num=round_num,
                plaintiff_statement=plaintiff_statement,
                plaintiff_history=plaintiff_history,
            )
        else:
            return self._fallback_defendant_speech(
                case=case,
                research_summary=research_summary,
                round_num=round_num,
                plaintiff_statement=plaintiff_statement,
                plaintiff_history=plaintiff_history,
            )

    async def _llm_defendant_speech(
        self,
        case: str,
        research_summary: str,
        round_num: int,
        plaintiff_statement: str,
        plaintiff_history: list[str],
    ) -> str:
        round_instruction = ""
        if round_num == 1:
            round_instruction = "这是第一轮辩论，请全面陈述抗辩理由。"
        else:
            round_instruction = f"这是第 {round_num} 轮辩论。请针对原告本轮的主张进行针对性反驳，提出新的抗辩理由或事实依据。不要重复之前说过的内容。"

        prompt = f"""
你现在扮演：被告代理律师

角色要求：
你代表抗辩方。请从合同约定不明、损失证据不足、违约程度较轻、责任可减轻、原告也有过错等角度提出抗辩。

{round_instruction}

案件问题：
{case}

法律检索资料：
{research_summary}

原告本轮主张：
{plaintiff_statement[:800]}

请输出：
1. 本轮核心抗辩
2. 针对原告主张的反驳要点
3. 新的抗辩理由或事实依据
4. 减责或免责方向

要求：
- 使用中文
- 不要编造法条编号
- 只能基于案件信息和检索资料分析
- 每轮要有新内容，不要重复
- 保持专业、理性，全力为当事人减轻责任
""".strip()

        try:
            return await self.llm_gateway.chat_text(
                user_message=prompt,
                system_message="你是经验丰富、沉稳理性的被告代理律师，全力为当事人争取最小责任。",
                max_tokens=1000,
                temperature=0.4,
            )
        except LLMGatewayError:
            return self._fallback_defendant_speech(
                case=case,
                research_summary=research_summary,
                round_num=round_num,
                plaintiff_statement=plaintiff_statement,
                plaintiff_history=plaintiff_history,
            )

    def _fallback_defendant_speech(
        self,
        case: str,
        research_summary: str,
        round_num: int,
        plaintiff_statement: str,
        plaintiff_history: list[str],
    ) -> str:
        if round_num == 1:
            return (
                f"【被告方第 {round_num} 轮抗辩】\n"
                "1. 核心抗辩：原告主张缺乏充分的合同依据和事实依据。合同对相关义务约定不明确，不能认定我方违约。\n"
                "2. 约定不明抗辩：合同中对交付时间、验收标准、违约责任等关键条款约定不清晰，属于约定不明，应当协商补充，不能直接认定我方违约。\n"
                "3. 损失证据不足：原告主张的损失缺乏充分证据证明，损失金额计算不合理，且无法证明与我方行为有直接因果关系。\n"
                "4. 原告也有过错：合同履行过程中，原告也存在配合不足、需求变更、迟延付款等情形，应当减轻我方责任。\n"
                "5. 减责请求：即使认定我方有一定责任，也应当根据过错程度、损失大小适当减轻，原告主张的赔偿金额明显过高。\n\n"
                f"案件：{case}\n\n"
                f"检索资料：\n{research_summary}"
            )
        else:
            return (
                f"【被告方第 {round_num} 轮反驳】\n"
                f"1. 针对原告第 {round_num} 轮主张的反驳：原告的反驳不能成立。原告始终回避合同约定不明的核心问题，其主张的法律依据不适用于本案。\n"
                "2. 新的抗辩点：根据法律规定，当事人就有关合同内容约定不明确的，应当按照合同相关条款或者交易习惯确定。本案中原告要求的内容超出了合同约定范围。\n"
                "3. 程序抗辩：原告未履行必要的催告义务，也未给予合理的履行期限，直接主张赔偿或解除合同不符合法律规定。\n"
                "4. 损失扩大抗辩：即使存在损失，原告也有义务采取适当措施防止损失扩大，没有采取适当措施致使损失扩大的，不得就扩大的损失请求赔偿。\n"
                "5. 结论：原告的诉讼请求缺乏充分的事实和法律依据，请求法庭依法驳回或大幅减少赔偿金额。\n\n"
                f"案件：{case}"
            )

    # ========== 法官判决 ==========
    async def _do_judge_verdict(
        self,
        case: str,
        research_summary: str,
        debate_rounds: list[DebateRound],
        use_llm: bool,
    ) -> tuple[JudgeVerdict, str]:
        if use_llm:
            return await self._llm_judge_verdict(
                case=case,
                research_summary=research_summary,
                debate_rounds=debate_rounds,
            )
        else:
            return self._fallback_judge_verdict(
                case=case,
                research_summary=research_summary,
                debate_rounds=debate_rounds,
            )

    async def _llm_judge_verdict(
        self,
        case: str,
        research_summary: str,
        debate_rounds: list[DebateRound],
    ) -> tuple[JudgeVerdict, str]:
        # 构建辩论历史
        debate_history = ""
        for r in debate_rounds:
            debate_history += f"\n=== 第 {r.round_num} 轮 ===\n"
            debate_history += f"原告：{r.plaintiff_statement[:400]}\n"
            debate_history += f"被告：{r.defendant_statement[:400]}\n"

        prompt = f"""
你现在扮演一位经验丰富的法官。
请综合案件事实、法律检索资料和双方 {len(debate_rounds)} 轮辩论，给出明确的判决。

案件事实：
{case}

法律检索资料：
{research_summary}

双方辩论历史：
{debate_history}

请严格按照以下 JSON 格式输出判决结果，不要输出其他解释文字：
{{
  "winner": "原告" 或 "被告" 或 "无法判断",
  "plaintiff_win_rate": 数字（0-100，表示原告胜诉概率）,
  "defendant_win_rate": 数字（0-100，表示被告胜诉概率）,
  "key_points": ["关键胜负点1", "关键胜负点2", "关键胜负点3"],
  "reasoning": "详细的判决理由，分析双方主张和抗辩的合理性",
  "action_suggestions": ["行动建议1", "行动建议2", "行动建议3"]
}}

要求：
1. winner 只能是 "原告"、"被告"、"无法判断" 三者之一
2. plaintiff_win_rate + defendant_win_rate 应该约等于 100
3. key_points 至少 3 条
4. reasoning 要详细，分析双方的优势和劣势
5. action_suggestions 至少 3 条，给出具体的实务建议
6. 不要编造法条编号
7. 如果资料不足，winner 填 "无法判断"，并说明缺少什么信息
""".strip()

        try:
            text = await self.llm_gateway.chat_text(
                user_message=prompt,
                system_message="你是一位公正、严谨、经验丰富的法官，擅长根据事实和法律给出明确的判决。",
                max_tokens=1500,
                temperature=0.1,
            )

            # 提取 JSON
            import json
            import re

            text = text.strip()
            if text.startswith("```"):
                text = re.sub(r"^```json", "", text, flags=re.IGNORECASE).strip()
                text = re.sub(r"^```", "", text).strip()
                text = re.sub(r"```$", "", text).strip()

            match = re.search(r"\{.*\}", text, flags=re.DOTALL)
            if not match:
                raise ValueError("未找到 JSON")

            data = json.loads(match.group(0))

            verdict = JudgeVerdict(
                winner=data.get("winner", "无法判断"),
                plaintiff_win_rate=float(data.get("plaintiff_win_rate", 50)),
                defendant_win_rate=float(data.get("defendant_win_rate", 50)),
                key_points=data.get("key_points", []),
                reasoning=data.get("reasoning", ""),
                action_suggestions=data.get("action_suggestions", []),
            )

            # 生成详细总结文本
            summary = self._verdict_to_summary(verdict, case, research_summary, debate_rounds)

            return verdict, summary

        except Exception:
            return self._fallback_judge_verdict(
                case=case,
                research_summary=research_summary,
                debate_rounds=debate_rounds,
            )

    def _fallback_judge_verdict(
        self,
        case: str,
        research_summary: str,
        debate_rounds: list[DebateRound],
    ) -> tuple[JudgeVerdict, str]:
        # 简单规则：根据案件关键词判断
        q = case.lower()

        # 默认五五开
        plaintiff_rate = 50
        defendant_rate = 50
        winner = "无法判断"

        # 原告有利因素
        plaintiff_factors = [
            "违约", "未交付", "迟延", "不履行", "赔偿", "解除合同",
            "证据充分", "合同明确", "书面约定",
        ]
        # 被告有利因素
        defendant_factors = [
            "约定不明", "没有约定", "证据不足", "损失无法证明",
            "原告也有过错", "协商不成", "管辖",
        ]

        for factor in plaintiff_factors:
            if factor in q:
                plaintiff_rate += 10

        for factor in defendant_factors:
            if factor in q:
                defendant_rate += 10

        # 归一化
        total = plaintiff_rate + defendant_rate
        if total > 0:
            plaintiff_rate = int(plaintiff_rate / total * 100)
            defendant_rate = 100 - plaintiff_rate

        if plaintiff_rate > 60:
            winner = "原告"
        elif defendant_rate > 60:
            winner = "被告"
        else:
            winner = "无法判断"

        verdict = JudgeVerdict(
            winner=winner,
            plaintiff_win_rate=plaintiff_rate,
            defendant_win_rate=defendant_rate,
            key_points=[
                "合同约定是否明确是本案关键争议点",
                "违约事实的认定需要充分证据支持",
                "损失金额的计算和因果关系需要证明",
                "双方是否均有过错影响责任划分",
            ],
            reasoning=(
                "综合双方辩论和现有证据，本案的核心争议在于合同义务是否明确约定以及违约事实的认定。"
                "原告主张被告违约并要求赔偿，但需要提供充分的证据证明违约事实和损失金额。"
                "被告以约定不明、证据不足等理由进行抗辩，具有一定合理性。"
                "根据现有信息，双方各有优劣，最终结果取决于具体证据和法庭认定。"
            ),
            action_suggestions=[
                "尽快收集和整理全部证据，包括合同、沟通记录、付款凭证等",
                "尝试与对方协商解决，争取达成和解协议",
                "如协商不成，可考虑委托专业律师评估后再决定是否诉讼",
                "注意诉讼时效，及时主张权利",
            ],
        )

        summary = self._verdict_to_summary(verdict, case, research_summary, debate_rounds)
        return verdict, summary

    def _verdict_to_summary(
        self,
        verdict: JudgeVerdict,
        case: str,
        research_summary: str,
        debate_rounds: list[DebateRound],
    ) -> str:
        """
        将判决对象转换为可读的总结文本。
        """
        lines = []

        lines.append("## ⚖️ 最终判决")
        lines.append("")

        # 胜负结果
        if verdict.winner == "原告":
            lines.append(f"### 🎯 判决结果：**原告更可能胜诉**")
        elif verdict.winner == "被告":
            lines.append(f"### 🎯 判决结果：**被告更可能胜诉**")
        else:
            lines.append(f"### 🎯 判决结果：**暂时无法判断，需更多证据**")

        lines.append("")

        # 胜率
        lines.append("### 📊 胜率评估")
        lines.append(f"- 原告胜诉概率：**{verdict.plaintiff_win_rate:.0f}%**")
        lines.append(f"- 被告胜诉概率：**{verdict.defendant_win_rate:.0f}%**")
        lines.append("")

        # 关键胜负点
        lines.append("### 🔑 关键胜负点")
        for i, point in enumerate(verdict.key_points, start=1):
            lines.append(f"{i}. {point}")
        lines.append("")

        # 判决理由
        lines.append("### 📝 判决理由")
        lines.append(verdict.reasoning)
        lines.append("")

        # 行动建议
        lines.append("### 💡 实务行动建议")
        for i, suggestion in enumerate(verdict.action_suggestions, start=1):
            lines.append(f"{i}. {suggestion}")
        lines.append("")

        # 风险提示
        lines.append("---")
        lines.append("⚠️ **风险提示**：以上分析仅基于当前提供的有限信息，不构成正式法律意见。")
        lines.append("复杂案件或正式诉讼前，建议咨询专业律师。")

        return "\n".join(lines)

    # ========== 以下为 v2 版本的 LangGraph 节点方法（支持多轮迭代） ==========

    async def _researcher_node_v2(self, state: MultiAgentState) -> MultiAgentState:
        """Researcher 节点 v2：初始化状态并执行法律检索。"""
        case = state["case"]
        steps = state.get("steps", [])
        use_llm = state.get("use_llm", True)

        research_summary = await self._do_research(case, use_llm)
        steps = steps + ["Researcher：完成法律资料检索"]

        return {
            "research_summary": research_summary,
            "steps": steps,
            "debate_round": 0,
            "convergence_score": 0.0,
            "short_term_memory": [],
            "plaintiff_history": [],
            "defendant_history": [],
            "debate_rounds": [],
            "should_continue": True,
        }

    async def _plaintiff_node_v2(self, state: MultiAgentState) -> MultiAgentState:
        """原告节点 v2：支持多轮，参考历史和短期记忆。"""
        case = state["case"]
        research_summary = state.get("research_summary", "")
        steps = state.get("steps", [])
        use_llm = state.get("use_llm", True)
        current_round = state.get("debate_round", 0) + 1
        defendant_history = state.get("defendant_history", [])
        short_term_memory = state.get("short_term_memory", [])

        # 构建记忆上下文
        memory_context = ""
        if short_term_memory:
            memory_context = "关键论点记忆：\n" + "\n".join(f"- {m}" for m in short_term_memory[-10:])

        # 生成原告发言
        plaintiff_statement = await self._do_plaintiff_speech(
            case=case,
            research_summary=research_summary + ("\n\n" + memory_context if memory_context else ""),
            round_num=current_round,
            defendant_history=defendant_history,
            use_llm=use_llm,
        )

        steps = steps + [f"第 {current_round} 轮 - 原告代理：发表观点"]

        return {
            "current_plaintiff": plaintiff_statement,
            "debate_round": current_round,
            "steps": steps,
        }

    async def _defendant_node_v2(self, state: MultiAgentState) -> MultiAgentState:
        """被告节点 v2：支持多轮，参考历史和短期记忆。"""
        case = state["case"]
        research_summary = state.get("research_summary", "")
        steps = state.get("steps", [])
        use_llm = state.get("use_llm", True)
        current_round = state.get("debate_round", 1)
        plaintiff_statement = state.get("current_plaintiff", "")
        plaintiff_history = state.get("plaintiff_history", [])
        short_term_memory = state.get("short_term_memory", [])

        # 构建记忆上下文
        memory_context = ""
        if short_term_memory:
            memory_context = "关键论点记忆：\n" + "\n".join(f"- {m}" for m in short_term_memory[-10:])

        # 生成被告发言
        defendant_statement = await self._do_defendant_speech(
            case=case,
            research_summary=research_summary + ("\n\n" + memory_context if memory_context else ""),
            round_num=current_round,
            plaintiff_statement=plaintiff_statement,
            plaintiff_history=plaintiff_history,
            use_llm=use_llm,
        )

        steps = steps + [f"第 {current_round} 轮 - 被告代理：发表抗辩"]

        return {
            "current_defendant": defendant_statement,
            "steps": steps,
        }

    async def _judge_node_v2(self, state: MultiAgentState) -> MultiAgentState:
        """
        法官节点 v2：
        1. 计算本轮收敛分数
        2. 提取关键论点存入短期记忆
        3. 判断是否需要继续辩论
        4. 如果结束，生成最终判决
        """
        case = state["case"]
        research_summary = state.get("research_summary", "")
        steps = state.get("steps", [])
        use_llm = state.get("use_llm", True)
        current_round = state.get("debate_round", 1)
        max_rounds = state.get("max_rounds", 3)
        convergence_threshold = state.get("convergence_threshold", 80.0)

        plaintiff_statement = state.get("current_plaintiff", "")
        defendant_statement = state.get("current_defendant", "")
        plaintiff_history = state.get("plaintiff_history", [])
        defendant_history = state.get("defendant_history", [])
        short_term_memory = state.get("short_term_memory", [])
        debate_rounds = state.get("debate_rounds", [])

        # ========== 1. 计算收敛分数 ==========
        convergence_score = self._calculate_similarity(plaintiff_statement, defendant_statement)

        # ========== 2. 提取关键论点存入短期记忆 ==========
        plaintiff_points = self._extract_key_points(plaintiff_statement, max_points=3)
        defendant_points = self._extract_key_points(defendant_statement, max_points=3)
        new_memory = [f"[原告第{current_round}轮] {p}" for p in plaintiff_points] + \
                     [f"[被告第{current_round}轮] {p}" for p in defendant_points]
        updated_memory = short_term_memory + new_memory
        # 限制记忆长度，保留最近的 30 条
        if len(updated_memory) > 30:
            updated_memory = updated_memory[-30:]

        # ========== 3. 更新历史和轮次记录 ==========
        updated_plaintiff_history = plaintiff_history + [plaintiff_statement]
        updated_defendant_history = defendant_history + [defendant_statement]

        current_round_dict = {
            "round_num": current_round,
            "plaintiff_statement": plaintiff_statement,
            "defendant_statement": defendant_statement,
        }
        updated_debate_rounds = debate_rounds + [current_round_dict]

        # ========== 4. 判断是否继续 ==========
        should_continue = True
        judge_summary = ""
        judge_verdict = None

        # 检查是否需要结束
        if current_round >= max_rounds:
            should_continue = False
        elif convergence_score >= convergence_threshold:
            should_continue = False
        else:
            # 让法官判断是否还需要继续（使用 LLM 或规则）
            if use_llm:
                should_continue = await self._judge_should_continue(
                    case=case,
                    research_summary=research_summary,
                    plaintiff_statement=plaintiff_statement,
                    defendant_statement=defendant_statement,
                    round_num=current_round,
                )
            else:
                # 规则：未达到最大轮次则继续
                should_continue = current_round < max_rounds

        # ========== 5. 如果结束，生成最终判决 ==========
        if not should_continue:
            # 转换为 DebateRound 对象列表
            debate_round_objs = [
                DebateRound(
                    round_num=r["round_num"],
                    plaintiff_statement=r["plaintiff_statement"],
                    defendant_statement=r["defendant_statement"],
                )
                for r in updated_debate_rounds
            ]

            verdict, summary = await self._do_judge_verdict(
                case=case,
                research_summary=research_summary,
                debate_rounds=debate_round_objs,
                use_llm=use_llm,
            )
            judge_summary = summary
            judge_verdict = {
                "winner": verdict.winner,
                "plaintiff_win_rate": verdict.plaintiff_win_rate,
                "defendant_win_rate": verdict.defendant_win_rate,
                "key_points": verdict.key_points,
                "reasoning": verdict.reasoning,
                "action_suggestions": verdict.action_suggestions,
            }
            steps = steps + [f"Judge：完成最终判决（共 {current_round} 轮辩论）"]
        else:
            steps = steps + [f"Judge：第 {current_round} 轮评估，收敛度 {convergence_score:.1f}%，继续下一轮"]

        result = {
            "debate_round": current_round,
            "convergence_score": convergence_score,
            "short_term_memory": updated_memory,
            "plaintiff_history": updated_plaintiff_history,
            "defendant_history": updated_defendant_history,
            "debate_rounds": updated_debate_rounds,
            "should_continue": should_continue,
            "steps": steps,
        }

        if judge_summary:
            result["judge_summary"] = judge_summary
        if judge_verdict:
            result["judge_verdict"] = judge_verdict

        return result

    async def _judge_should_continue(
        self,
        case: str,
        research_summary: str,
        plaintiff_statement: str,
        defendant_statement: str,
        round_num: int,
    ) -> bool:
        """
        使用 LLM 判断是否需要继续辩论。

        返回 True 表示需要继续，False 表示可以结束。
        """
        prompt = f"""
你是一位经验丰富的法官。现在正在进行多轮法庭辩论，目前是第 {round_num} 轮。

请判断双方的辩论是否已经充分，是否需要继续下一轮。

案件事实：
{case[:500]}

原告本轮观点：
{plaintiff_statement[:600]}

被告本轮观点：
{defendant_statement[:600]}

法律检索资料：
{research_summary[:400]}

请判断：
1. 双方是否已经充分表达了各自的核心观点？
2. 是否还有重要的法律点或事实点没有讨论到？
3. 继续辩论是否能产生新的有价值的观点？

请只回答 "是" 或 "否"：
- 回答 "是"：表示需要继续下一轮辩论
- 回答 "否"：表示辩论已经充分，可以结束并给出判决
""".strip()

        try:
            result = await self.llm_gateway.chat_text(
                user_message=prompt,
                system_message="你是一位严谨、理性的法官，擅长判断辩论是否充分。",
                max_tokens=10,
                temperature=0.1,
            )
            return "是" in result
        except LLMGatewayError:
            # 失败时默认继续（最多到 max_rounds）
            return True

    # ========== 以下为兼容旧接口的 LangGraph 节点方法 ==========
    async def _researcher_node(self, state: MultiAgentState) -> MultiAgentState:
        """兼容旧接口的 Researcher 节点。"""
        case = state["case"]
        steps = state.get("steps", [])
        use_llm = state.get("use_llm", True)

        research_summary = await self._do_research(case, use_llm)
        steps = steps + ["Researcher：完成法律资料检索"]

        return {
            "research_summary": research_summary,
            "steps": steps,
        }

    async def _plaintiff_node(self, state: MultiAgentState) -> MultiAgentState:
        """兼容旧接口的原告节点。"""
        case = state["case"]
        research_summary = state.get("research_summary", "")
        steps = state.get("steps", [])
        use_llm = state.get("use_llm", True)

        opinion = await self._do_plaintiff_speech(
            case=case,
            research_summary=research_summary,
            round_num=1,
            defendant_history=[],
            use_llm=use_llm,
        )

        steps = steps + ["Plaintiff Advocate：完成权利主张方观点"]

        return {
            "plaintiff_opinion": opinion,
            "steps": steps,
        }

    async def _defendant_node(self, state: MultiAgentState) -> MultiAgentState:
        """兼容旧接口的被告节点。"""
        case = state["case"]
        research_summary = state.get("research_summary", "")
        steps = state.get("steps", [])
        use_llm = state.get("use_llm", True)
        plaintiff_opinion = state.get("plaintiff_opinion", "")

        opinion = await self._do_defendant_speech(
            case=case,
            research_summary=research_summary,
            round_num=1,
            plaintiff_statement=plaintiff_opinion,
            plaintiff_history=[plaintiff_opinion],
            use_llm=use_llm,
        )

        steps = steps + ["Defendant Advocate：完成抗辩方观点"]

        return {
            "defendant_opinion": opinion,
            "steps": steps,
        }

    async def _judge_node(self, state: MultiAgentState) -> MultiAgentState:
        """兼容旧接口的法官节点。"""
        case = state["case"]
        research_summary = state.get("research_summary", "")
        plaintiff_opinion = state.get("plaintiff_opinion", "")
        defendant_opinion = state.get("defendant_opinion", "")
        steps = state.get("steps", [])
        use_llm = state.get("use_llm", True)

        debate_rounds = [
            DebateRound(
                round_num=1,
                plaintiff_statement=plaintiff_opinion,
                defendant_statement=defendant_opinion,
            )
        ]

        _, judge_summary = await self._do_judge_verdict(
            case=case,
            research_summary=research_summary,
            debate_rounds=debate_rounds,
            use_llm=use_llm,
        )

        steps = steps + ["Judge：完成中立综合判断"]

        return {
            "judge_summary": judge_summary,
            "steps": steps,
        }


multi_agent_debate = LegalMultiAgentDebate()


async def _demo() -> None:
    # 确保示例法律知识库已索引
    default_rag.index_directory(PROJECT_ROOT / "data" / "raw")

    case = (
        "甲方委托乙方开发网站，合同金额5000元。"
        "乙方迟迟没有交付，合同没有明确写交付时间，"
        "也没有明确违约金。甲方想要求赔偿，应该怎么办？"
    )

    result = await multi_agent_debate.run(
        case=case,
        use_llm=True,
        max_rounds=2,  # demo 用 2 轮，快一点
    )

    print("案件：")
    print(result.case)

    print("\n执行步骤：")
    for step in result.steps:
        print("-", step)

    print("\n法律检索员：")
    print(result.research_summary)

    print("\n" + "=" * 80)
    print("多轮辩论：")
    for r in result.debate_rounds:
        print(f"\n--- 第 {r.round_num} 轮 ---")
        print("\n【原告】")
        print(r.plaintiff_statement[:300] + "...")
        print("\n【被告】")
        print(r.defendant_statement[:300] + "...")

    print("\n" + "=" * 80)
    print("法官最终判决：")
    print(f"胜者：{result.judge_verdict.winner}")
    print(f"原告胜率：{result.judge_verdict.plaintiff_win_rate}%")
    print(f"被告胜率：{result.judge_verdict.defendant_win_rate}%")
    print(f"关键胜负点：{result.judge_verdict.key_points}")
    print(f"判决理由：{result.judge_verdict.reasoning[:200]}...")

    print("\n法官详细总结：")
    print(result.judge_summary)


# ========== 以下为 v3 版本：子 Agent 自主检索 + 针对性攻防辩论 ==========

@dataclass
class AgentDebateRound:
    """v3版本：单轮辩论记录。"""
    round_num: int
    plaintiff_statement: str
    plaintiff_legal_basis: list[str]  # 原告引用的法律依据
    defendant_statement: str
    defendant_legal_basis: list[str]  # 被告引用的法律依据
    judge_comment: str = ""
    convergence_score: float = 0.0


class DebateAgent:
    """
    辩论角色子 Agent。

    每个角色都具备：
    1. 自主 RAG 检索能力：从法律知识库中查找相关依据
    2. 立场导向：根据己方角色选择有利的法律条文
    3. 针对性反驳：分析对方论点漏洞，组织反击
    """

    def __init__(
        self,
        role: str,  # "plaintiff" / "defendant" / "judge"
        llm_gateway: Optional[LLMGateway] = None,
        rag: Optional[LegalRAG] = None,
    ) -> None:
        self.role = role
        self.llm_gateway = llm_gateway or default_gateway
        self.rag = rag or default_rag

    async def retrieve_legal_basis(
        self,
        case: str,
        focus_points: list[str],
        opponent_args: Optional[str] = None,
        top_k: int = 5,
    ) -> list[str]:
        """
        自主检索法律依据。

        根据案情和争议焦点，自动判断法律类别，检索相关法条。
        如果有对方论点，会针对性检索反驳依据。
        """
        # 构建检索查询
        queries = [case] + focus_points
        if opponent_args:
            queries.append(f"反驳以下论点的法律依据：{opponent_args[:300]}")

        all_contexts = []
        for query in queries[:3]:  # 最多3个查询
            contexts, _, _ = await self.rag.search(
                question=query,
                top_k=top_k,
                auto_detect_category=True,
                use_llm_query_transform=False,
                use_llm_hyde=False,
            )
            all_contexts.extend(contexts)

        # 去重并提取法条内容
        seen = set()
        legal_basis = []
        for ctx in all_contexts:
            if ctx.text not in seen and len(ctx.text.strip()) > 10:
                seen.add(ctx.text)
                legal_basis.append(f"[{ctx.source}] {ctx.text[:200]}")
                if len(legal_basis) >= 6:
                    break

        return legal_basis

    async def generate_argument(
        self,
        case: str,
        legal_basis: list[str],
        opponent_last_statement: Optional[str] = None,
        round_num: int = 1,
        debate_history: list[dict] | None = None,
    ) -> str:
        """生成辩论发言。"""
        role_prompts = {
            "plaintiff": self._plaintiff_prompt,
            "defendant": self._defendant_prompt,
        }
        prompt_fn = role_prompts.get(self.role)
        if not prompt_fn:
            return ""

        prompt = prompt_fn(
            case=case,
            legal_basis=legal_basis,
            opponent_last_statement=opponent_last_statement,
            round_num=round_num,
            debate_history=debate_history or [],
        )

        try:
            return await self.llm_gateway.chat_text(
                user_message=prompt,
                system_message=f"你是法庭{self._role_name()}，专业、严谨、有逻辑，善于运用法律条文。",
                max_tokens=800,
                temperature=0.7,
            )
        except LLMGatewayError:
            return self._fallback_argument(case, legal_basis, round_num)

    def _role_name(self) -> str:
        return {
            "plaintiff": "原告代理人",
            "defendant": "被告代理人",
            "judge": "法官",
        }.get(self.role, self.role)

    def _plaintiff_prompt(
        self,
        case: str,
        legal_basis: list[str],
        opponent_last_statement: Optional[str],
        round_num: int,
        debate_history: list[dict],
    ) -> str:
        basis_text = "\n".join(f"- {b}" for b in legal_basis) if legal_basis else "（暂未检索到具体法条）"

        if round_num == 1:
            return f"""
你是原告方代理律师。请针对以下案件，代表原告提出诉讼主张和法律依据。

【案件事实】
{case}

【可引用的法律依据】
{basis_text}

【要求】
1. 明确原告的核心诉讼请求
2. 陈述事实与理由
3. 引用相关法律条文支撑主张
4. 逻辑清晰，分点陈述
5. 字数控制在300-500字

请直接输出原告代理意见：
""".strip()
        else:
            return f"""
你是原告方代理律师。这是第 {round_num} 轮辩论。

【案件事实】
{case}

【被告上一轮论点】
{opponent_last_statement[:500] if opponent_last_statement else "无"}

【可引用的法律依据】
{basis_text}

【要求】
1. 针对被告上一轮的论点进行逐一反驳
2. 找出被告论述中的法律漏洞和事实偏差
3. 用法律条文强化己方主张
4. 保持专业、理性的辩论风格
5. 字数控制在300-500字

请直接输出原告反驳意见：
""".strip()

    def _defendant_prompt(
        self,
        case: str,
        legal_basis: list[str],
        opponent_last_statement: Optional[str],
        round_num: int,
        debate_history: list[dict],
    ) -> str:
        basis_text = "\n".join(f"- {b}" for b in legal_basis) if legal_basis else "（暂未检索到具体法条）"

        return f"""
你是被告方代理律师。这是第 {round_num} 轮辩论。

【案件事实】
{case}

【原告上一轮主张】
{opponent_last_statement[:500] if opponent_last_statement else "原告尚未陈述"}

【可引用的法律依据】
{basis_text}

【要求】
1. 针对原告的诉讼请求和事实理由进行抗辩
2. 找出原告诉求中的法律依据不足、事实不清之处
3. 提出对被告有利的法律解释和事实主张
4. 引用相关法律条文支撑抗辩
5. 逻辑清晰，分点反驳
6. 字数控制在300-500字

请直接输出被告抗辩意见：
""".strip()

    def _fallback_argument(self, case: str, legal_basis: list[str], round_num: int) -> str:
        role_name = self._role_name()
        basis = "；".join(legal_basis[:3]) if legal_basis else "相关法律规定"
        return f"【{role_name}第{round_num}轮意见】基于案件事实和{basis}，{self.role}方坚持己方立场。"


class EnhancedMultiAgentDebate:
    """
    v3 增强版多智能体辩论系统。

    核心升级：
    1. 每个角色都是独立子 Agent，具备自主 RAG 检索能力
    2. 原告、被告各自从法律知识库中寻找对己方有利的依据
    3. 每轮辩论针对对方上一轮论点的漏洞进行反击
    4. 自动识别法律类别，精准检索相关法条
    """

    def __init__(
        self,
        llm_gateway: Optional[LLMGateway] = None,
        rag: Optional[LegalRAG] = None,
    ) -> None:
        self.llm_gateway = llm_gateway or default_gateway
        self.rag = rag or default_rag

        # 初始化三个角色 Agent
        self.plaintiff_agent = DebateAgent("plaintiff", llm_gateway, rag)
        self.defendant_agent = DebateAgent("defendant", llm_gateway, rag)

    async def run_debate(
        self,
        case: str,
        max_rounds: int = 5,
        convergence_threshold: float = 80.0,
        use_llm: bool = True,
    ) -> dict:
        """
        运行完整的增强版辩论流程。

        返回：
            {
                "case": 案件描述,
                "rounds": [AgentDebateRound],
                "final_verdict": 最终判决,
                "total_rounds": 总轮数,
            }
        """
        rounds: list[AgentDebateRound] = []
        plaintiff_statement = ""
        defendant_statement = ""

        for current_round in range(1, max_rounds + 1):
            # ===== 原告方：检索法律依据 + 生成主张 =====
            plaintiff_focus = self._extract_focus_points(case, "plaintiff")
            plaintiff_basis = await self.plaintiff_agent.retrieve_legal_basis(
                case=case,
                focus_points=plaintiff_focus,
                opponent_args=defendant_statement if current_round > 1 else None,
            )
            plaintiff_statement = await self.plaintiff_agent.generate_argument(
                case=case,
                legal_basis=plaintiff_basis,
                opponent_last_statement=defendant_statement if current_round > 1 else None,
                round_num=current_round,
            )

            # ===== 被告方：检索法律依据 + 针对性抗辩 =====
            defendant_focus = self._extract_focus_points(case, "defendant")
            defendant_basis = await self.defendant_agent.retrieve_legal_basis(
                case=case,
                focus_points=defendant_focus,
                opponent_args=plaintiff_statement,
            )
            defendant_statement = await self.defendant_agent.generate_argument(
                case=case,
                legal_basis=defendant_basis,
                opponent_last_statement=plaintiff_statement,
                round_num=current_round,
            )

            # ===== 收敛度计算 =====
            convergence = self._calculate_convergence(plaintiff_statement, defendant_statement)

            # 记录本轮
            round_record = AgentDebateRound(
                round_num=current_round,
                plaintiff_statement=plaintiff_statement,
                plaintiff_legal_basis=plaintiff_basis,
                defendant_statement=defendant_statement,
                defendant_legal_basis=defendant_basis,
                convergence_score=convergence,
            )
            rounds.append(round_record)

            # 检查是否提前终止
            if convergence >= convergence_threshold:
                break

        # ===== 生成最终判决 =====
        final_verdict = await self._generate_final_verdict(case, rounds)

        return {
            "case": case,
            "rounds": rounds,
            "final_verdict": final_verdict,
            "total_rounds": len(rounds),
        }

    def _extract_focus_points(self, case: str, role: str) -> list[str]:
        """从案件中提取争议焦点（简化版关键词提取）。"""
        keywords = ["赔偿", "违约", "合同", "侵权", "责任", "损失", "过错", "解除", "履行"]
        focus = [kw for kw in keywords if kw in case]
        return focus[:3] if focus else ["案件核心争议"]

    def _calculate_convergence(self, p_text: str, d_text: str) -> float:
        """计算双方观点收敛度（简化版相似度）。"""
        # 基于共同关键词的简单计算
        def get_keywords(text: str) -> set:
            words = re.findall(r"[\u4e00-\u9fff]{2,4}", text)
            return set(words)

        p_kw = get_keywords(p_text)
        d_kw = get_keywords(d_text)
        if not p_kw or not d_kw:
            return 0.0

        intersection = len(p_kw & d_kw)
        union = len(p_kw | d_kw)
        return round((intersection / union) * 100, 2) if union > 0 else 0.0

    async def _generate_final_verdict(self, case: str, rounds: list[AgentDebateRound]) -> dict:
        """生成最终判决。"""
        debate_summary = "\n".join(
            f"第{r.round_num}轮：\n【原告】{r.plaintiff_statement[:200]}...\n【被告】{r.defendant_statement[:200]}..."
            for r in rounds
        )

        prompt = f"""
请作为法官，根据以下案件和多轮辩论，给出最终判决意见。

【案件事实】
{case}

【辩论过程】
{debate_summary}

【判决要求】
1. 判定胜诉方（原告/被告/部分支持）
2. 给出原告胜率和被告胜率（百分比）
3. 列出3-5个关键胜负点
4. 说明判决理由
5. 给出行动建议

请以JSON格式输出：
{{
    "winner": "原告/被告/部分支持",
    "plaintiff_win_rate": 数字,
    "defendant_win_rate": 数字,
    "key_points": ["要点1", "要点2"],
    "reasoning": "判决理由",
    "action_suggestions": ["建议1", "建议2"]
}}
""".strip()

        try:
            result = await self.llm_gateway.chat_text(
                user_message=prompt,
                system_message="你是一位公正的法官，基于事实和法律做出判决。",
                max_tokens=600,
                temperature=0.3,
            )
            # 简单解析JSON
            import json as _json
            try:
                return _json.loads(result)
            except _json.JSONDecodeError:
                return {
                    "winner": "待裁定",
                    "plaintiff_win_rate": 50,
                    "defendant_win_rate": 50,
                    "key_points": ["需进一步审理"],
                    "reasoning": result[:300],
                    "action_suggestions": ["补充证据后再审"],
                }
        except LLMGatewayError:
            return {
                "winner": "待裁定",
                "plaintiff_win_rate": 50,
                "defendant_win_rate": 50,
                "key_points": ["辩论已完成", "需法官最终裁决"],
                "reasoning": "双方已完成多轮辩论，等待法官最终判决。",
                "action_suggestions": ["提交合议庭审议"],
            }


# 全局实例
enhanced_debate = EnhancedMultiAgentDebate()


if __name__ == "__main__":
    asyncio.run(_demo())
