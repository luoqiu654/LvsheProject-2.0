import asyncio

from backend.core.multi_agents import (
    DebateRound,
    JudgeVerdict,
    LegalMultiAgentDebate,
    MultiAgentDebateResult,
)
from backend.core.rag import LegalRAG


SAMPLE_TEXT = """
合同依法成立后，对当事人具有法律约束力。
当事人应当按照约定全面履行自己的义务。
一方不履行合同义务或者履行合同义务不符合约定的，
应当承担继续履行、采取补救措施或者赔偿损失等违约责任。
当事人可以约定违约金，也可以约定损失赔偿额的计算方法。
"""


def test_multi_agent_run_without_llm(tmp_path):
    """测试多智能体运行（无 LLM 模式）。"""
    rag = LegalRAG(
        persist_dir=tmp_path / "chroma",
        collection_name="test_multi_agent_run_without_llm",
    )
    rag.index_text(SAMPLE_TEXT, source="unit_test")

    debate = LegalMultiAgentDebate(rag_engine=rag)

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
    assert "Researcher" in result.steps[0]
    assert "Judge" in result.steps[-1]

    # 新字段：多轮辩论
    assert len(result.debate_rounds) == 2
    assert isinstance(result.debate_rounds[0], DebateRound)
    assert result.debate_rounds[0].round_num == 1
    assert result.debate_rounds[0].plaintiff_statement
    assert result.debate_rounds[0].defendant_statement

    # 新字段：法官判决
    assert isinstance(result.judge_verdict, JudgeVerdict)
    assert result.judge_verdict.winner in ("原告", "被告", "无法判断")
    assert 0 <= result.judge_verdict.plaintiff_win_rate <= 100
    assert 0 <= result.judge_verdict.defendant_win_rate <= 100
    assert len(result.judge_verdict.key_points) >= 3
    assert result.judge_verdict.reasoning
    assert len(result.judge_verdict.action_suggestions) >= 3

    # 兼容旧接口：opinions
    assert len(result.opinions) == 2
    assert result.opinions[0].role == "Plaintiff Advocate"
    assert result.opinions[1].role == "Defendant Advocate"


def test_multi_agent_opinion_roles(tmp_path):
    """测试双方观点的角色。"""
    rag = LegalRAG(
        persist_dir=tmp_path / "chroma",
        collection_name="test_multi_agent_opinion_roles",
    )
    rag.index_text(SAMPLE_TEXT, source="unit_test")

    debate = LegalMultiAgentDebate(rag_engine=rag)

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

    # 新接口：第一轮辩论
    assert len(result.debate_rounds) == 1
    assert "原告" in result.debate_rounds[0].plaintiff_statement
    assert "被告" in result.debate_rounds[0].defendant_statement


def test_judge_verdict_contains_key_sections(tmp_path):
    """测试法官判决包含关键部分。"""
    rag = LegalRAG(
        persist_dir=tmp_path / "chroma",
        collection_name="test_judge_verdict_contains_key_sections",
    )
    debate = LegalMultiAgentDebate(rag_engine=rag)

    verdict, summary = asyncio.run(
        debate._do_judge_verdict(
            case="测试案件",
            research_summary="检索资料",
            debate_rounds=[
                DebateRound(
                    round_num=1,
                    plaintiff_statement="原告观点",
                    defendant_statement="被告观点",
                )
            ],
            use_llm=False,
        )
    )

    # 判决对象
    assert isinstance(verdict, JudgeVerdict)
    assert verdict.winner in ("原告", "被告", "无法判断")
    assert len(verdict.key_points) >= 3
    assert len(verdict.action_suggestions) >= 3

    # 总结文本
    assert "最终判决" in summary
    assert "胜率评估" in summary
    assert "关键胜负点" in summary
    assert "判决理由" in summary
    assert "行动建议" in summary


def test_researcher_handles_empty_knowledge_base(tmp_path):
    """测试空知识库的处理。"""
    rag = LegalRAG(
        persist_dir=tmp_path / "chroma",
        collection_name="test_researcher_handles_empty_knowledge_base",
    )

    debate = LegalMultiAgentDebate(rag_engine=rag)

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


def test_different_round_counts(tmp_path):
    """测试不同辩论轮数。"""
    rag = LegalRAG(
        persist_dir=tmp_path / "chroma",
        collection_name="test_different_round_counts",
    )
    rag.index_text(SAMPLE_TEXT, source="unit_test")

    debate = LegalMultiAgentDebate(rag_engine=rag)

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
