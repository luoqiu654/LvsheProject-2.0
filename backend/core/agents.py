from __future__ import annotations

import ast
import asyncio
import json
import logging
import operator
import re
from dataclasses import dataclass
from typing import Any, Literal, Optional, TypedDict

from langgraph.graph import END, START, StateGraph

from backend.core.llm_gateway import LLMGateway, LLMGatewayError, gateway as default_gateway
from backend.core.rag import LegalRAG, rag as default_rag

logger = logging.getLogger(__name__)


ToolName = Literal["law_search", "contract_risk_check", "calculator", "direct_answer"]


class LegalAgentState(TypedDict, total=False):
    """
    LangGraph Agent 状态。

    LangGraph 的核心思想：
    - 每个节点接收 state
    - 节点处理后返回新的字段
    - 图负责把 state 在节点之间传递
    """

    question: str
    plan: dict[str, Any]
    tool_name: str
    tool_input: str
    tool_result: str
    final_answer: str
    steps: list[str]
    use_llm: bool


@dataclass
class AgentRunResult:
    """
    Agent 最终运行结果。
    """

    question: str
    final_answer: str
    tool_name: str
    tool_input: str
    tool_result: str
    steps: list[str]


class SafeCalculator:
    """
    安全计算器。

    只允许：
    - 数字
    - + - * / // % **
    - 括号
    - 一元正负号

    不允许：
    - 函数调用
    - 属性访问
    - 变量名
    - import
    """

    allowed_operators = {
        ast.Add: operator.add,
        ast.Sub: operator.sub,
        ast.Mult: operator.mul,
        ast.Div: operator.truediv,
        ast.FloorDiv: operator.floordiv,
        ast.Mod: operator.mod,
        ast.Pow: operator.pow,
        ast.USub: operator.neg,
        ast.UAdd: operator.pos,
    }

    def calculate(self, expression: str) -> float | int:
        expression = expression.strip()

        if not re.fullmatch(r"[0-9+\-*/().%\s]+", expression):
            raise ValueError("表达式包含不允许的字符")

        tree = ast.parse(expression, mode="eval")
        return self._eval_node(tree.body)

    def _eval_node(self, node: ast.AST) -> float | int:
        if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
            return node.value

        if isinstance(node, ast.BinOp):
            op_type = type(node.op)
            if op_type not in self.allowed_operators:
                raise ValueError("不支持的二元运算符")
            left = self._eval_node(node.left)
            right = self._eval_node(node.right)

            if isinstance(node.op, (ast.Div, ast.FloorDiv, ast.Mod)) and right == 0:
                raise ValueError("除数不能为 0")

            return self.allowed_operators[op_type](left, right)

        if isinstance(node, ast.UnaryOp):
            op_type = type(node.op)
            if op_type not in self.allowed_operators:
                raise ValueError("不支持的一元运算符")
            value = self._eval_node(node.operand)
            return self.allowed_operators[op_type](value)

        raise ValueError("表达式不安全或不支持")


class LegalAgent:
    """
    法律单智能体。

    能力：
    1. 使用 LangGraph 编排 Agent 流程
    2. 能根据问题选择工具
    3. 能调用 RAG 工具查询法律知识库
    4. 能做合同风险初筛
    5. 能做安全数学计算
    6. 能用 LLM 汇总工具结果
    """

    def __init__(
        self,
        llm_gateway: Optional[LLMGateway] = None,
        rag_engine: Optional[LegalRAG] = None,
    ) -> None:
        self.llm_gateway = llm_gateway or default_gateway
        self.rag_engine = rag_engine or default_rag
        self.calculator = SafeCalculator()
        self.graph = self._build_graph()

    def _build_graph(self):
        workflow = StateGraph(LegalAgentState)

        workflow.add_node("plan", self._plan_node)
        workflow.add_node("tool", self._tool_node)
        workflow.add_node("final", self._final_node)

        workflow.add_edge(START, "plan")
        workflow.add_conditional_edges(
            "plan",
            self._should_use_tool,
            {True: "tool", False: "final"},
        )
        workflow.add_conditional_edges(
            "tool",
            self._should_continue_tools,
            {True: "plan", False: "final"},
        )
        workflow.add_edge("final", END)

        return workflow.compile()

    def _should_use_tool(self, state: LegalAgentState) -> bool:
        """检查是否需要调用工具。保持当前行为：始终进入工具节点。"""
        return True

    def _should_continue_tools(self, state: LegalAgentState) -> bool:
        """检查是否需要继续调用工具（最多 3 次工具调用避免无限循环）。"""
        step_count = len(state.get("steps", []))
        if step_count >= 3:
            return False
        return False  # 保持当前行为，后续可扩展

    async def run(
        self,
        question: str,
        use_llm: bool = True,
    ) -> AgentRunResult:
        """
        运行 Agent。

        use_llm=False 时：
        - 不联网
        - 用规则规划
        - 用模板生成最终答案
        - 适合单元测试
        """
        initial_state: LegalAgentState = {
            "question": question,
            "steps": [],
            "use_llm": use_llm,
        }

        final_state = await self.graph.ainvoke(initial_state)

        return AgentRunResult(
            question=question,
            final_answer=final_state.get("final_answer", ""),
            tool_name=final_state.get("tool_name", "direct_answer"),
            tool_input=final_state.get("tool_input", question),
            tool_result=final_state.get("tool_result", ""),
            steps=final_state.get("steps", []),
        )

    async def _plan_node(self, state: LegalAgentState) -> LegalAgentState:
        question = state["question"]
        steps = state.get("steps", [])
        use_llm = state.get("use_llm", True)

        plan: dict[str, Any]

        if use_llm:
            plan = await self._llm_plan(question)
        else:
            plan = self._fallback_plan(question)

        tool_name = plan.get("tool_name", "direct_answer")
        tool_input = plan.get("tool_input", question)

        steps = steps + [
            f"计划节点：选择工具 {tool_name}，输入：{tool_input}"
        ]

        return {
            "plan": plan,
            "tool_name": tool_name,
            "tool_input": tool_input,
            "steps": steps,
        }

    async def _tool_node(self, state: LegalAgentState) -> LegalAgentState:
        tool_name = state.get("tool_name", "direct_answer")
        tool_input = state.get("tool_input", state["question"])
        steps = state.get("steps", [])

        if tool_name == "law_search":
            tool_result = await self._tool_law_search(tool_input)

        elif tool_name == "contract_risk_check":
            tool_result = self._tool_contract_risk_check(tool_input)

        elif tool_name == "calculator":
            tool_result = self._tool_calculator(tool_input)

        else:
            tool_result = "无需调用外部工具，直接根据通用法律知识和已有上下文回答。"

        steps = steps + [f"工具节点：{tool_name} 执行完成"]

        return {
            "tool_result": tool_result,
            "steps": steps,
        }

    async def _final_node(self, state: LegalAgentState) -> LegalAgentState:
        question = state["question"]
        tool_name = state.get("tool_name", "direct_answer")
        tool_result = state.get("tool_result", "")
        steps = state.get("steps", [])
        use_llm = state.get("use_llm", True)

        if use_llm:
            final_answer = await self._llm_final_answer(
                question=question,
                tool_name=tool_name,
                tool_result=tool_result,
            )
        else:
            final_answer = self._fallback_final_answer(
                question=question,
                tool_name=tool_name,
                tool_result=tool_result,
            )

        steps = steps + ["总结节点：生成最终回答"]

        return {
            "final_answer": final_answer,
            "steps": steps,
        }

    async def _llm_plan(self, question: str) -> dict[str, Any]:
        """
        让 LLM 输出 JSON 计划。

        如果 LLM 输出不可解析，则自动回退到规则规划。
        """
        prompt = f"""
你是一个法律 Agent 的任务规划器。
请根据用户问题选择一个最合适的工具。

可用工具：
1. law_search：查询法律知识库。适合合同、违约、定金、租赁、劳动、法律依据等问题。
2. contract_risk_check：合同风险初筛。适合用户提供合同条款、想审查合同风险的问题。
3. calculator：安全计算器。适合计算金额、比例、违约金等数学问题。
4. direct_answer：无需工具，直接回答。

请只输出 JSON，不要输出解释。
JSON 格式：
{{
  "tool_name": "law_search",
  "tool_input": "用于工具的输入",
  "reason": "选择原因"
}}

用户问题：
{question}
""".strip()

        try:
            text = await self.llm_gateway.chat_text(
                user_message=prompt,
                system_message="你是只输出 JSON 的法律 Agent 规划器。",
                max_tokens=512,
                temperature=0,
            )
            plan = self._extract_json(text)

            if plan.get("tool_name") not in {
                "law_search",
                "contract_risk_check",
                "calculator",
                "direct_answer",
            }:
                return self._fallback_plan(question)

            if not plan.get("tool_input"):
                plan["tool_input"] = question

            return plan

        except Exception as exc:
            logger.warning("LLM 规划失败，使用规则兜底: %s", exc, exc_info=True)
            return self._fallback_plan(question)

    def _fallback_plan(self, question: str) -> dict[str, Any]:
        """
        规则兜底规划器。

        即使 LLM 不可用，Agent 仍能工作。
        """
        q = question.strip()

        # ✅ 修复1：先判断合同风险，再判断计算器
        if any(keyword in q for keyword in ["风险", "审查", "条款", "甲方", "乙方", "合同文本"]):
            return {
                "tool_name": "contract_risk_check",
                "tool_input": q,
                "reason": "问题看起来像合同审查或风险识别",
            }

        expression = self._extract_math_expression(q)
        if expression:
            return {
                "tool_name": "calculator",
                "tool_input": expression,
                "reason": "问题中包含可计算表达式",
            }

        if any(keyword in q for keyword in ["合同", "违约", "定金", "租赁", "劳动", "赔偿", "解除", "法律依据"]):
            return {
                "tool_name": "law_search",
                "tool_input": q,
                "reason": "问题涉及法律知识库检索",
            }

        return {
            "tool_name": "direct_answer",
            "tool_input": q,
            "reason": "无需调用工具",
        }

    async def _tool_law_search(self, query: str) -> str:
        """
        RAG 法律检索工具。
        """
        answer = await self.rag_engine.answer(
            question=query,
            top_k=3,
            use_llm_query_transform=False,
            use_llm_hyde=False,
            use_llm_answer=False,
        )

        if not answer.contexts:
            return "知识库中暂时没有检索到相关法律资料。"

        lines = [f"检索到 {len(answer.contexts)} 条相关资料："]

        for index, item in enumerate(answer.contexts, start=1):
            snippet = item.enriched_text.strip().replace("\n", " ")
            if len(snippet) > 260:
                snippet = snippet[:260] + "..."

            lines.append(
                f"{index}. 来源：{item.source}；相关度分数：{item.final_score:.4f}；内容：{snippet}"
            )

        return "\n".join(lines)

    def _tool_contract_risk_check(self, contract_text: str) -> str:
        """
        合同风险初筛工具。

        当前是规则 MVP，后续 skills.py 会把它升级为正式 Agent Skill。
        """
        rules = [
            ("违约责任", ["违约责任", "违约金", "赔偿"], "合同中建议明确违约责任、违约金或损失赔偿计算方式。"),
            ("争议解决", ["争议解决", "仲裁", "诉讼", "管辖"], "合同中建议明确争议解决方式和管辖地点。"),
            ("履行期限", ["履行期限", "交付时间", "完成时间", "付款时间"], "合同中建议明确履行期限、交付时间或付款时间。"),
            ("合同主体", ["甲方", "乙方", "身份证", "统一社会信用代码"], "合同中建议明确双方主体身份信息。"),
            ("解除条款", ["解除合同", "终止合同", "解除权"], "合同中建议约定解除或终止条件。"),
        ]

        findings: list[str] = []

        for name, keywords, suggestion in rules:
            hit = any(keyword in contract_text for keyword in keywords)
            if hit:
                findings.append(f"✅ 已发现【{name}】相关表述。")
            else:
                findings.append(f"⚠️ 未明显发现【{name}】相关表述。建议：{suggestion}")

        return "\n".join(findings)

    def _tool_calculator(self, expression: str) -> str:
        try:
            result = self.calculator.calculate(expression)
            return f"计算表达式：{expression}\n计算结果：{result}"
        except Exception as exc:
            logger.warning("计算器执行失败: %s", exc)
            return f"计算失败：{exc}"

    async def _llm_final_answer(
        self,
        question: str,
        tool_name: str,
        tool_result: str,
    ) -> str:
        prompt = f"""
你是一个严谨、友好的中文法律 AI Agent。
你刚刚调用了工具，请基于工具结果回答用户。

要求：
1. 先给结论
2. 再说明依据或分析
3. 如果是合同风险审查，请列出风险点和修改建议
4. 不要编造法条编号
5. 结尾提醒复杂情况咨询专业律师

用户问题：
{question}

调用工具：
{tool_name}

工具结果：
{tool_result}
""".strip()

        try:
            return await self.llm_gateway.chat_text(
                user_message=prompt,
                system_message="你是专业、严谨、不会编造依据的法律 AI Agent。",
                max_tokens=1200,
                temperature=0.2,
            )
        except LLMGatewayError as exc:
            logger.warning("LLM 最终回答失败，使用模板兜底: %s", exc)
            return self._fallback_final_answer(question, tool_name, tool_result)

    def _fallback_final_answer(
        self,
        question: str,
        tool_name: str,
        tool_result: str,
    ) -> str:
        return (
            f"结论：我已根据问题调用工具 `{tool_name}` 完成初步分析。\n\n"
            f"用户问题：{question}\n\n"
            f"工具结果：\n{tool_result}\n\n"
            f"提示：以上为 AI 初步分析，复杂案件或正式合同签署前建议咨询专业律师。"
        )

    def _extract_json(self, text: str) -> dict[str, Any]:
        """
        从 LLM 输出中提取 JSON。
        """
        text = text.strip()

        if text.startswith("```"):
            text = re.sub(r"^```json", "", text, flags=re.IGNORECASE).strip()
            text = re.sub(r"^```", "", text).strip()
            text = re.sub(r"```$", "", text).strip()

        match = re.search(r"\{.*\}", text, flags=re.DOTALL)
        if not match:
            raise ValueError("未找到 JSON 对象")

        return json.loads(match.group(0))

    def _extract_math_expression(self, question: str) -> Optional[str]:
        """
        从问题中提取数学表达式。

        示例：
        - 10000 * 0.2
        - 5000+300
        """
        # ✅ 修复2：必须包含运算符，才认为是数学表达式
        matches = re.findall(r"[0-9][0-9+\-*/().%\s]*[+\-*/%][0-9+\-*/().%\s]*[0-9)]", question)
        if not matches:
            return None

        expression = matches[0].replace("%", "/100")
        return expression.strip()


agent = LegalAgent()


async def _demo() -> None:
    # 确保 RAG 示例知识库已索引
    from backend.config import PROJECT_ROOT

    default_rag.index_directory(PROJECT_ROOT / "data" / "raw")

    questions = [
        "合同一方违约了，我可以要求赔偿吗？",
        "请帮我审查这个合同条款风险：甲方委托乙方开发网站，费用5000元，但没有写交付时间和违约责任。",
        "违约金是 10000 * 0.2，帮我算一下。",
    ]

    for q in questions:
        print("=" * 80)
        print("用户问题：", q)

        result = await agent.run(q, use_llm=True)

        print("\n执行步骤：")
        for step in result.steps:
            print("-", step)

        print("\n工具：", result.tool_name)
        print("\n工具结果：")
        print(result.tool_result)

        print("\n最终回答：")
        print(result.final_answer)


if __name__ == "__main__":
    asyncio.run(_demo())