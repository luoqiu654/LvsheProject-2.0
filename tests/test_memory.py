import asyncio

from backend.core.agents import LegalAgent
from backend.core.memory import LegalMemoryManager, LocalMemoryStore


def test_local_memory_add_search(tmp_path):
    store = LocalMemoryStore(store_path=tmp_path / "memory")

    store.add(
        content="用户关注网站开发合同。",
        user_id="u1",
        category="business_context",
    )

    results = store.search(
        query="网站开发合同有什么风险？",
        user_id="u1",
    )

    assert len(results) == 1
    assert results[0].record.category == "business_context"
    assert results[0].score > 0


def test_user_isolation(tmp_path):
    store = LocalMemoryStore(store_path=tmp_path / "memory")

    store.add("用户A关注租赁合同。", user_id="user_a")
    store.add("用户B关注劳动合同。", user_id="user_b")

    results_a = store.search("租赁合同", user_id="user_a")
    results_b = store.search("租赁合同", user_id="user_b")

    assert len(results_a) == 1
    assert len(results_b) == 0


def test_extract_memories_from_interaction(tmp_path):
    manager = LegalMemoryManager(
        store_path=tmp_path / "memory",
    )

    extracted = manager.extract_memories_from_interaction(
        user_message="我叫小蔡，我经常审查网站开发合同，希望你一步一步解释清楚。",
        assistant_message="好的。",
    )

    categories = [item[0] for item in extracted]
    contents = [item[1] for item in extracted]

    assert "user_profile" in categories
    assert "preference" in categories
    assert "business_context" in categories
    assert any("小蔡" in content for content in contents)


def test_remember_interaction_and_context(tmp_path):
    manager = LegalMemoryManager(
        store_path=tmp_path / "memory",
    )

    saved = manager.remember_interaction(
        user_message="我叫小蔡，我关注网站开发合同风险。",
        assistant_message="好的。",
        user_id="u1",
    )

    assert len(saved) >= 2

    context = manager.build_memory_context(
        query="网站开发合同",
        user_id="u1",
    )

    assert "用户相关长期记忆" in context
    assert "网站开发合同" in context


def test_clear_user(tmp_path):
    manager = LegalMemoryManager(
        store_path=tmp_path / "memory",
    )

    manager.remember("用户关注合同风险。", user_id="u1")
    assert len(manager.get_all("u1")) == 1

    deleted = manager.clear_user("u1")

    assert deleted == 1
    assert len(manager.get_all("u1")) == 0


def test_chat_with_memory_without_llm(tmp_path):
    manager = LegalMemoryManager(
        store_path=tmp_path / "memory",
        legal_agent=LegalAgent(),
    )

    result = asyncio.run(
        manager.chat_with_memory(
            message="我叫小蔡，我关注网站开发合同风险。",
            user_id="u1",
            use_llm=False,
        )
    )

    assert result["user_id"] == "u1"
    assert result["answer"]
    assert len(result["saved_memories"]) >= 1

    result2 = asyncio.run(
        manager.chat_with_memory(
            message="合同没有写交付时间，有什么风险？",
            user_id="u1",
            use_llm=False,
        )
    )

    assert "用户相关长期记忆" in result2["memory_context"]
