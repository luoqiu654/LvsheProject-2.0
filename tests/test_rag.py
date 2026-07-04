import asyncio

from backend.core.rag import LegalRAG


SAMPLE_TEXT = """
合同依法成立后，对当事人具有法律约束力。
当事人应当按照约定全面履行自己的义务。

一方不履行合同义务或者履行合同义务不符合约定的，
应当承担继续履行、采取补救措施或者赔偿损失等违约责任。

租赁合同应当明确租赁物、租赁期限、租金、维修责任和违约责任。
承租人未经出租人同意转租的，出租人可以依法解除合同。
"""


def test_hash_embedding_dimension():
    rag = LegalRAG(collection_name="test_hash_embedding_dimension")
    vector = rag.embedding.embed("合同违约责任")

    assert len(vector) == 384
    assert any(x != 0 for x in vector)


def test_chunk_text():
    rag = LegalRAG(collection_name="test_chunk_text")
    chunks = rag.chunk_text(SAMPLE_TEXT, source="unit_test", chunk_size=80, overlap=10)

    assert len(chunks) >= 2
    assert chunks[0].source == "unit_test"
    assert chunks[0].text
    assert chunks[0].parent_text


def test_index_and_count(tmp_path):
    rag = LegalRAG(
        persist_dir=tmp_path / "chroma",
        collection_name="test_index_and_count",
    )

    count = rag.index_text(SAMPLE_TEXT, source="unit_test")
    assert count > 0
    assert rag.count() == count


def test_search_without_llm(tmp_path):
    rag = LegalRAG(
        persist_dir=tmp_path / "chroma",
        collection_name="test_search_without_llm",
    )

    rag.index_text(SAMPLE_TEXT, source="unit_test")

    contexts, queries, hyde = asyncio.run(
        rag.search(
            question="合同违约可以要求赔偿吗？",
            top_k=2,
            use_llm_query_transform=False,
            use_llm_hyde=False,
        )
    )

    assert len(contexts) > 0
    assert len(queries) > 0
    assert "合同" in hyde
    assert any("违约" in item.enriched_text or "赔偿" in item.enriched_text for item in contexts)


def test_answer_without_llm(tmp_path):
    rag = LegalRAG(
        persist_dir=tmp_path / "chroma",
        collection_name="test_answer_without_llm",
    )

    rag.index_text(SAMPLE_TEXT, source="unit_test")

    answer = asyncio.run(
        rag.answer(
            question="租赁合同可以随便转租吗？",
            top_k=2,
            use_llm_query_transform=False,
            use_llm_hyde=False,
            use_llm_answer=False,
        )
    )

    assert answer.question == "租赁合同可以随便转租吗？"
    assert len(answer.contexts) > 0
    assert "已检索到" in answer.answer
