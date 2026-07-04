from __future__ import annotations

import asyncio
import hashlib
import math
import re
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

import chromadb

from backend.config import PROJECT_ROOT, settings
from backend.core.llm_gateway import LLMGateway, LLMGatewayError, gateway as default_gateway


@dataclass
class DocumentChunk:
    """
    切分后的文档块。

    parent_text 用于 Context Enrichment：
    - 检索时使用较小 chunk
    - 生成答案时使用更完整 parent_text
    """

    chunk_id: str
    text: str
    parent_text: str
    source: str
    chunk_index: int


@dataclass
class RAGSearchResult:
    """
    单条 RAG 检索结果。
    """

    chunk_id: str
    text: str
    enriched_text: str
    source: str
    distance: float
    keyword_score: float
    final_score: float


@dataclass
class RAGAnswer:
    """
    RAG 最终回答。
    """

    question: str
    answer: str
    contexts: list[RAGSearchResult]
    transformed_queries: list[str]
    hyde_answer: str


class HashEmbedding:
    """
    一个纯 Python 的轻量级 Hash Embedding。

    为什么先用它：
    1. 不需要下载模型
    2. 不依赖 PyTorch / sentence-transformers
    3. Python 3.14 阶段更稳
    4. 便于先跑通 ChromaDB + RAG 主流程

    后续可以替换为：
    - sentence-transformers 中文模型
    - 通义 / 智谱 / 硅基流动 embedding API
    """

    def __init__(self, dim: int = 384) -> None:
        self.dim = dim

    def embed(self, text: str) -> list[float]:
        vector = [0.0] * self.dim

        tokens = self._tokenize(text)
        if not tokens:
            tokens = [text[:20] or "empty"]

        for token in tokens:
            digest = hashlib.md5(token.encode("utf-8")).hexdigest()
            index = int(digest[:8], 16) % self.dim
            sign = 1.0 if int(digest[8:10], 16) % 2 == 0 else -1.0
            vector[index] += sign

        norm = math.sqrt(sum(x * x for x in vector))
        if norm == 0:
            return vector

        return [x / norm for x in vector]

    def embed_many(self, texts: list[str]) -> list[list[float]]:
        return [self.embed(text) for text in texts]

    def _tokenize(self, text: str) -> list[str]:
        text = text.lower().strip()

        chinese_chars = re.findall(r"[\u4e00-\u9fff]", text)
        chinese_bigrams = [
            "".join(chinese_chars[i : i + 2])
            for i in range(max(0, len(chinese_chars) - 1))
        ]

        words = re.findall(r"[a-zA-Z0-9_]+", text)

        legal_keywords = re.findall(
            r"合同|违约|定金|赔偿|租赁|劳动|解除|责任|履行|生效|争议|权利|义务",
            text,
        )

        return chinese_bigrams + words + legal_keywords


class LegalRAG:
    """
    法律 RAG 引擎。

    已实现的进阶 RAG 技术：
    1. Query Transformation：把用户问题改写成多个检索查询
    2. HyDE：先生成假设性回答，再用假设性回答参与检索
    3. Context Enrichment：检索小 chunk，生成时补充 parent_text
    4. Hybrid Search：向量检索 + 关键词重排
    """

    def __init__(
        self,
        persist_dir: Optional[str | Path] = None,
        collection_name: Optional[str] = None,
        llm_gateway: Optional[LLMGateway] = None,
        embedding: Optional[HashEmbedding] = None,
    ) -> None:
        self.persist_dir = Path(persist_dir or settings.chroma_path)
        self.collection_name = collection_name or settings.chroma_collection_name
        self.llm_gateway = llm_gateway or default_gateway
        self.embedding = embedding or HashEmbedding()

        self.persist_dir.mkdir(parents=True, exist_ok=True)

        self.client = chromadb.PersistentClient(path=str(self.persist_dir))
        self.collection = self.client.get_or_create_collection(
            name=self.collection_name,
            metadata={"description": "LvsheProject legal RAG collection"},
        )

    def chunk_text(
        self,
        text: str,
        source: str,
        chunk_size: int = 260,
        overlap: int = 60,
        parent_window: int = 1,
    ) -> list[DocumentChunk]:
        """
        将长文本切成小块，同时保留 parent_text。

        chunk_size:
            每个检索块的大致字符数

        overlap:
            相邻块重叠字符数，避免语义被切断

        parent_window:
            上下文增强窗口，当前 chunk 前后各取几个 chunk 作为 parent_text
        """
        clean_text = self._normalize_text(text)
        if not clean_text:
            return []

        raw_chunks: list[str] = []
        start = 0

        while start < len(clean_text):
            end = start + chunk_size
            raw_chunks.append(clean_text[start:end])

            if end >= len(clean_text):
                break

            start = max(0, end - overlap)

        result: list[DocumentChunk] = []
        doc_prefix = hashlib.md5(source.encode("utf-8")).hexdigest()[:10]

        for index, chunk in enumerate(raw_chunks):
            parent_start = max(0, index - parent_window)
            parent_end = min(len(raw_chunks), index + parent_window + 1)
            parent_text = "\n".join(raw_chunks[parent_start:parent_end])

            result.append(
                DocumentChunk(
                    chunk_id=f"{doc_prefix}-{index}",
                    text=chunk,
                    parent_text=parent_text,
                    source=source,
                    chunk_index=index,
                )
            )

        return result

    def index_text(
        self,
        text: str,
        source: str,
        reset_source: bool = True,
    ) -> int:
        """
        将一段文本写入 ChromaDB。

        reset_source=True:
            重复索引同一个 source 时，先删除旧数据，避免重复。
        """
        chunks = self.chunk_text(text=text, source=source)

        if not chunks:
            return 0

        if reset_source:
            self.delete_by_source(source)

        ids = [chunk.chunk_id for chunk in chunks]
        documents = [chunk.text for chunk in chunks]
        embeddings = self.embedding.embed_many(documents)

        metadatas = [
            {
                "source": chunk.source,
                "chunk_index": chunk.chunk_index,
                "parent_text": chunk.parent_text,
            }
            for chunk in chunks
        ]

        self.collection.upsert(
            ids=ids,
            documents=documents,
            embeddings=embeddings,
            metadatas=metadatas,
        )

        return len(chunks)

    def index_file(self, file_path: str | Path) -> int:
        """
        索引单个文本文件。
        """
        path = Path(file_path)
        text = path.read_text(encoding="utf-8")
        source = str(path.relative_to(PROJECT_ROOT)) if path.is_absolute() else str(path)
        return self.index_text(text=text, source=source)

    def index_directory(self, directory: str | Path) -> int:
        """
        索引目录下的 .txt 和 .md 文件。
        """
        directory = Path(directory)

        total = 0
        for path in directory.rglob("*"):
            if path.suffix.lower() not in {".txt", ".md"}:
                continue
            total += self.index_file(path)

        return total

    def delete_by_source(self, source: str) -> None:
        """
        删除某个来源的旧 chunk。
        """
        try:
            old = self.collection.get(where={"source": source})
            ids = old.get("ids", [])
            if ids:
                self.collection.delete(ids=ids)
        except Exception:
            # Chroma 在空集合或 where 无结果时，不同版本表现可能略有差异。
            # 这里保持删除操作幂等。
            return

    def count(self) -> int:
        return self.collection.count()

    async def transform_query(self, question: str, use_llm: bool = True) -> list[str]:
        """
        Query Transformation：
        将用户问题改写成多个更适合检索的问题。
        """
        fallback = self._fallback_transform_query(question)

        if not use_llm:
            return fallback

        prompt = f"""
请把下面的法律咨询问题改写成 3 个适合知识库检索的中文短查询。
要求：
1. 每行一个查询
2. 不要编号
3. 不要解释

用户问题：
{question}
""".strip()

        try:
            text = await self.llm_gateway.chat_text(
                user_message=prompt,
                system_message="你是法律知识库检索查询改写助手。",
                max_tokens=256,
                temperature=0.1,
            )
            queries = [
                line.strip(" -0123456789.、")
                for line in text.splitlines()
                if line.strip()
            ]
            queries = [q for q in queries if q]

            merged = [question] + queries + fallback
            return self._unique_keep_order(merged)[:6]

        except LLMGatewayError:
            return fallback

    async def generate_hyde_answer(self, question: str, use_llm: bool = True) -> str:
        """
        HyDE：
        先让 LLM 生成一个“可能的法律回答”，
        再用这个回答参与向量检索。
        """
        if not use_llm:
            return self._fallback_hyde(question)

        prompt = f"""
请根据常见中国民事法律知识，为下面问题写一段可能的简短回答。
这段回答只用于向量检索增强，不要求完全准确。
请控制在 120 字以内。

问题：
{question}
""".strip()

        try:
            return await self.llm_gateway.chat_text(
                user_message=prompt,
                system_message="你是法律 RAG 的 HyDE 假设文档生成器。",
                max_tokens=256,
                temperature=0.2,
            )
        except LLMGatewayError:
            return self._fallback_hyde(question)

    async def search(
        self,
        question: str,
        top_k: int = 4,
        use_llm_query_transform: bool = True,
        use_llm_hyde: bool = True,
    ) -> tuple[list[RAGSearchResult], list[str], str]:
        """
        执行进阶检索流程。

        返回：
        1. 检索结果
        2. 改写后的查询列表
        3. HyDE 假设回答
        """
        transformed_queries = await self.transform_query(
            question,
            use_llm=use_llm_query_transform,
        )
        hyde_answer = await self.generate_hyde_answer(
            question,
            use_llm=use_llm_hyde,
        )

        retrieval_queries = self._unique_keep_order(
            transformed_queries + [hyde_answer]
        )

        all_results: dict[str, RAGSearchResult] = {}

        for query in retrieval_queries:
            query_embedding = self.embedding.embed(query)

            raw = self.collection.query(
                query_embeddings=[query_embedding],
                n_results=top_k,
                include=["documents", "metadatas", "distances"],
            )

            ids = raw.get("ids", [[]])[0]
            docs = raw.get("documents", [[]])[0]
            metadatas = raw.get("metadatas", [[]])[0]
            distances = raw.get("distances", [[]])[0]

            for chunk_id, doc, metadata, distance in zip(ids, docs, metadatas, distances):
                keyword_score = self._keyword_score(question, doc)
                final_score = (1 / (1 + float(distance))) + keyword_score

                existing = all_results.get(chunk_id)
                if existing is None or final_score > existing.final_score:
                    all_results[chunk_id] = RAGSearchResult(
                        chunk_id=chunk_id,
                        text=doc,
                        enriched_text=metadata.get("parent_text", doc),
                        source=metadata.get("source", "unknown"),
                        distance=float(distance),
                        keyword_score=keyword_score,
                        final_score=final_score,
                    )

        ranked = sorted(
            all_results.values(),
            key=lambda item: item.final_score,
            reverse=True,
        )

        return ranked[:top_k], transformed_queries, hyde_answer

    async def answer(
        self,
        question: str,
        top_k: int = 4,
        use_llm_query_transform: bool = True,
        use_llm_hyde: bool = True,
        use_llm_answer: bool = True,
    ) -> RAGAnswer:
        """
        RAG 问答入口。
        """
        contexts, transformed_queries, hyde_answer = await self.search(
            question=question,
            top_k=top_k,
            use_llm_query_transform=use_llm_query_transform,
            use_llm_hyde=use_llm_hyde,
        )

        if not contexts:
            return RAGAnswer(
                question=question,
                answer="知识库中暂时没有检索到相关内容。",
                contexts=[],
                transformed_queries=transformed_queries,
                hyde_answer=hyde_answer,
            )

        context_text = "\n\n".join(
            [
                f"【资料{index + 1}｜来源：{item.source}】\n{item.enriched_text}"
                for index, item in enumerate(contexts)
            ]
        )

        if not use_llm_answer:
            return RAGAnswer(
                question=question,
                answer=f"已检索到 {len(contexts)} 条相关资料，可用于回答该问题。",
                contexts=contexts,
                transformed_queries=transformed_queries,
                hyde_answer=hyde_answer,
            )

        prompt = f"""
你是一个严谨的中文法律 AI 助手。
请只根据下面的资料回答用户问题。

要求：
1. 先给出简洁结论
2. 再列出依据
3. 如果资料不足，请明确说明“仅根据当前知识库无法完全判断”
4. 不要编造法条编号
5. 结尾提示用户复杂案件应咨询专业律师

用户问题：
{question}

可用资料：
{context_text}
""".strip()

        try:
            answer_text = await self.llm_gateway.chat_text(
                user_message=prompt,
                system_message="你是严谨、专业、不会编造依据的法律 AI 助手。",
                max_tokens=1200,
                temperature=0.2,
            )
        except LLMGatewayError:
            answer_text = (
                "LLM 生成答案失败，但已完成知识库检索。"
                "你可以查看 contexts 中的资料。"
            )

        return RAGAnswer(
            question=question,
            answer=answer_text,
            contexts=contexts,
            transformed_queries=transformed_queries,
            hyde_answer=hyde_answer,
        )

    def _fallback_transform_query(self, question: str) -> list[str]:
        queries = [question]

        if "违约" in question:
            queries.append("合同违约责任 赔偿 继续履行 补救措施")
        if "定金" in question:
            queries.append("定金 债权担保 违约")
        if "劳动" in question:
            queries.append("劳动合同 工作内容 劳动报酬 社会保险")
        if "租" in question or "租赁" in question:
            queries.append("租赁合同 租金 转租 解除合同")

        queries.append("合同效力 履行义务 诚信原则")
        return self._unique_keep_order(queries)

    def _fallback_hyde(self, question: str) -> str:
        return (
            f"该问题可能涉及合同成立、合同效力、履行义务、违约责任、"
            f"损失赔偿或合同解除等民事法律风险。问题：{question}"
        )

    def _keyword_score(self, question: str, document: str) -> float:
        q_tokens = set(HashEmbedding()._tokenize(question))
        d_tokens = set(HashEmbedding()._tokenize(document))

        if not q_tokens or not d_tokens:
            return 0.0

        overlap = q_tokens & d_tokens
        return len(overlap) / max(len(q_tokens), 1)

    def _normalize_text(self, text: str) -> str:
        text = text.replace("\r\n", "\n").replace("\r", "\n")
        text = re.sub(r"\n{3,}", "\n\n", text)
        text = re.sub(r"[ \t]+", " ", text)
        return text.strip()

    def _unique_keep_order(self, items: list[str]) -> list[str]:
        seen = set()
        result = []

        for item in items:
            clean = item.strip()
            if not clean:
                continue
            if clean in seen:
                continue
            seen.add(clean)
            result.append(clean)

        return result


rag = LegalRAG()


async def _demo() -> None:
    raw_dir = PROJECT_ROOT / "data" / "raw"

    indexed = rag.index_directory(raw_dir)
    print(f"索引完成，新增/更新 chunk 数：{indexed}")
    print(f"当前向量库 chunk 总数：{rag.count()}")

    question = "合同一方违约了，我可以要求赔偿吗？"

    result = await rag.answer(
        question=question,
        top_k=3,
        use_llm_query_transform=True,
        use_llm_hyde=True,
        use_llm_answer=True,
    )

    print("\n用户问题：")
    print(result.question)

    print("\nQuery Transformation：")
    for query in result.transformed_queries:
        print("-", query)

    print("\nHyDE：")
    print(result.hyde_answer)

    print("\n检索来源：")
    for item in result.contexts:
        print(
            f"- {item.source} | distance={item.distance:.4f} | "
            f"keyword={item.keyword_score:.4f} | final={item.final_score:.4f}"
        )

    print("\n最终回答：")
    print(result.answer)


if __name__ == "__main__":
    asyncio.run(_demo())
