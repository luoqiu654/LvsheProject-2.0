"""debate_adapter 单元测试（v3.7 从 test_multi_agents.py 迁移）。

测试 LegalMultiAgentDebate 的无 LLM 回退逻辑。
"""
import asyncio

from backend.core.debate_adapter import (
    DebateRound,
    JudgeVerdict,
    LegalMultiAgentDebate,
    MultiAgentDebateResult,
)


def test_multi_agent_run_without_llm():
    """测试多智能体运行（无 LLM 模式，回退结果）。"""
    debate = LegalMultiAgentDebate()

    result = asyncio.run(
        debate.run(
            case="合同一方违约了，另一方可以要求赔偿吗？",
            use_llm=False,
            max_rounds=2,
        )
    )

    # 基础字段
    assert result.case
    assert result.research_summary
    assert result.judge_summary
    assert result.steps  # 回退模式有占位步骤

    # 多轮辩论
    assert len(result.debate_rounds) == 2
    assert isinstance(result.debate_rounds[0], DebateRound)
    assert result.debate_rounds[0].round_num == 1
    assert result.debate_rounds[0].plaintiff_statement
    assert result.debate_rounds[0].defendant_statement

    # 法官判决
    assert isinstance(result.judge_verdict, JudgeVerdict)
    assert result.judge_verdict.winner == "无法判断"
    assert 0 <= result.judge_verdict.plaintiff_win_rate <= 100
    assert 0 <= result.judge_verdict.defendant_win_rate <= 100
    assert result.judge_verdict.reasoning
    assert result.judge_verdict.action_suggestions

    # 兼容旧接口：opinions
    assert len(result.opinions) == 2
    assert result.opinions[0].role == "Plaintiff Advocate"
    assert result.opinions[1].role == "Defendant Advocate"


def test_multi_agent_opinion_roles():
    """测试双方观点的角色。"""
    debate = LegalMultiAgentDebate()

    result = asyncio.run(
        debate.run(
            case="乙方未按合同交付，甲方想主张违约责任。",
            use_llm=False,
            max_rounds=1,
        )
    )

    # 兼容旧接口
    roles = [opinion.role for opinion in result.opinions]
    viewpoints = [opinion.viewpoint for opinion in result.opinions]

    assert "Plaintiff Advocate" in roles
    assert "Defendant Advocate" in roles
    assert "权利主张方" in viewpoints
    assert "抗辩方" in viewpoints

    # 第一轮辩论
    assert len(result.debate_rounds) == 1
    assert "原告" in result.debate_rounds[0].plaintiff_statement
    assert "被告" in result.debate_rounds[0].defendant_statement


def test_researcher_handles_empty_knowledge_base():
    """测试空知识库的处理（无 LLM 模式）。"""
    debate = LegalMultiAgentDebate()

    result = asyncio.run(
        debate.run(
            case="一个知识库里没有的问题",
            use_llm=False,
            max_rounds=1,
        )
    )

    assert result.research_summary
    assert result.judge_summary
    assert len(result.debate_rounds) == 1
    assert len(result.opinions) == 2  # 兼容旧接口


def test_different_round_counts():
    """测试不同辩论轮数。"""
    debate = LegalMultiAgentDebate()

    # 测试 1 轮
    result_1 = asyncio.run(
        debate.run(case="测试", use_llm=False, max_rounds=1)
    )
    assert len(result_1.debate_rounds) == 1

    # 测试 3 轮
    result_3 = asyncio.run(
        debate.run(case="测试", use_llm=False, max_rounds=3)
    )
    assert len(result_3.debate_rounds) == 3

    # 每轮都有双方发言
    for r in result_3.debate_rounds:
        assert r.plaintiff_statement
        assert r.defendant_statement


def test_result_is_multi_agent_debate_result():
    """测试返回类型正确。"""
    debate = LegalMultiAgentDebate()

    result = asyncio.run(
        debate.run(case="测试案件", use_llm=False, max_rounds=1)
    )

    assert isinstance(result, MultiAgentDebateResult)
    assert isinstance(result.judge_verdict, JudgeVerdict)
    assert isinstance(result.debate_rounds[0], DebateRound)
