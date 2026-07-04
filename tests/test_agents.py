import asyncio

from backend.core.agents import LegalAgent, SafeCalculator
from backend.core.rag import LegalRAG


SAMPLE_TEXT = """
依法成立的合同，对当事人具有法律约束力。
当事人一方不履行合同义务或者履行合同义务不符合约定的，
应当承担继续履行、采取补救措施或者赔偿损失等违约责任。
"""


def test_safe_calculator():
    calculator = SafeCalculator()

    assert calculator.calculate("10000 * 0.2") == 2000
    assert calculator.calculate("(100 + 50) / 3") == 50

    try:
        calculator.calculate("__import__('os').system('dir')")
    except ValueError:
        pass
    else:
        raise AssertionError("危险表达式应该被拒绝")


def test_agent_fallback_plan_law_search(tmp_path):
    rag = LegalRAG(
        persist_dir=tmp_path / "chroma",
        collection_name="test_agent_fallback_plan_law_search",
    )
    rag.index_text(SAMPLE_TEXT, source="unit_test")

    agent = LegalAgent(rag_engine=rag)

    result = asyncio.run(
        agent.run(
            "合同违约可以要求赔偿吗？",
            use_llm=False,
        )
    )

    assert result.tool_name == "law_search"
    assert "检索到" in result.tool_result
    assert "违约" in result.final_answer


def test_agent_fallback_plan_contract_risk():
    agent = LegalAgent()

    result = asyncio.run(
        agent.run(
            "请审查这个合同条款风险：甲方委托乙方开发系统，费用5000元。",
            use_llm=False,
        )
    )

    assert result.tool_name == "contract_risk_check"
    assert "违约责任" in result.tool_result
    assert "争议解决" in result.tool_result


def test_agent_fallback_plan_calculator():
    agent = LegalAgent()

    result = asyncio.run(
        agent.run(
            "违约金按照 10000 * 0.2 计算是多少？",
            use_llm=False,
        )
    )

    assert result.tool_name == "calculator"
    assert "2000" in result.tool_result


def test_agent_direct_answer():
    agent = LegalAgent()

    result = asyncio.run(
        agent.run(
            "你好，你能做什么？",
            use_llm=False,
        )
    )

    assert result.tool_name == "direct_answer"
    assert "无需调用外部工具" in result.tool_result
