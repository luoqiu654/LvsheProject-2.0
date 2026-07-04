import asyncio
from pathlib import Path

from backend.core.rag import LegalRAG
from backend.core.skills import SkillExecutor, SkillRegistry


SAMPLE_TEXT = """
合同依法成立后，对当事人具有法律约束力。
一方不履行合同义务或者履行合同义务不符合约定的，
应当承担继续履行、采取补救措施或者赔偿损失等违约责任。
"""


def test_skill_registry_discover():
    registry = SkillRegistry()

    names = registry.list_names()

    assert "law-search" in names
    assert "contract-risk-review" in names
    assert "legal-consultation" in names


def test_skill_metadata():
    registry = SkillRegistry()

    skill = registry.get("contract-risk-review")

    assert skill.name == "contract-risk-review"
    assert "contract" in skill.description.lower()
    assert "Contract Risk Review Skill" in skill.instructions


def test_skill_match_contract_review():
    registry = SkillRegistry()

    skill = registry.match("请审查这个合同条款风险：甲方委托乙方开发网站")

    assert skill is not None
    assert skill.name == "contract-risk-review"


def test_skill_match_law_search():
    registry = SkillRegistry()

    skill = registry.match("合同违约可以要求赔偿吗？")

    assert skill is not None
    assert skill.name == "law-search"


def test_execute_contract_risk_review():
    executor = SkillExecutor()

    result = asyncio.run(
        executor.execute(
            skill_name="contract-risk-review",
            input_text="甲方委托乙方开发网站，费用5000元。",
            use_llm=False,
        )
    )

    assert result.skill_name == "contract-risk-review"
    assert "违约责任" in result.output_text
    assert "review_checklist.md" in str(result.used_resources) or "review_checklist.md" in result.output_text


def test_execute_law_search_with_temp_rag(tmp_path):
    rag = LegalRAG(
        persist_dir=tmp_path / "chroma",
        collection_name="test_execute_law_search_with_temp_rag",
    )
    rag.index_text(SAMPLE_TEXT, source="unit_test")

    executor = SkillExecutor(rag_engine=rag)

    result = asyncio.run(
        executor.execute(
            skill_name="law-search",
            input_text="合同违约可以赔偿吗？",
            use_llm=False,
        )
    )

    assert result.skill_name == "law-search"
    assert "法律知识库检索结果" in result.output_text
    assert "违约" in result.output_text


def test_execute_best_match_without_llm():
    executor = SkillExecutor()

    result = asyncio.run(
        executor.execute_best_match(
            input_text="请审查这个合同条款风险：甲方委托乙方开发网站，费用5000元。",
            use_llm=False,
        )
    )

    assert result.skill_name == "contract-risk-review"
    assert result.output_text
