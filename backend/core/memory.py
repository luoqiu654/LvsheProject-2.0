from __future__ import annotations

import asyncio
import json
import re
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from backend.config import settings
from backend.core.agents import LegalAgent


@dataclass
class MemoryRecord:
    """
    单条长期记忆。

    当前用于本地 MVP：
    - user_id 做用户隔离
    - category 做记忆分类
    - content 是可被检索的记忆内容
    """

    id: str
    user_id: str
    content: str
    category: str = "general"
    source: str = "local"
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )


@dataclass
class MemorySearchResult:
    """
    记忆检索结果。
    """

    record: MemoryRecord
    score: float


class LocalMemoryStore:
    """
    本地长期记忆存储。

    当前实现目标：
    1. 开发阶段不依赖外部服务
    2. 不需要 OpenAI embedding
    3. 支持 Windows + Python 3.14 稳定运行
    4. 后续可以平滑替换为 mem0 / 向量数据库
    """

    # 这些词太通用，单独命中时不能证明语义相关。
    # 例如：“租赁合同”不应该仅因为共享“合同”而匹配“劳动合同”。
    STOPWORDS = {
        "合同",
        "问题",
        "情况",
        "内容",
        "用户",
        "关注",
        "相关",
        "法律",
    }

    # 业务强关键词：这些词命中时更能代表检索意图。
    DOMAIN_KEYWORDS = {
        "违约",
        "定金",
        "赔偿",
        "租赁",
        "租房",
        "劳动",
        "解除",
        "责任",
        "履行",
        "生效",
        "争议",
        "风险",
        "审查",
        "律师",
        "网站",
        "开发",
        "交付",
        "付款",
        "验收",
        "保密",
        "知识产权",
        "服务",
        "软件",
    }

    def __init__(self, store_path: str | Path | None = None) -> None:
        memory_dir = Path(store_path or settings.memory_path)
        memory_dir.mkdir(parents=True, exist_ok=True)

        self.db_path = memory_dir / "local_memories.json"
        if not self.db_path.exists():
            self._write_all([])

    def add(
        self,
        content: str,
        user_id: str = "default_user",
        category: str = "general",
        metadata: Optional[dict[str, Any]] = None,
    ) -> MemoryRecord:
        content = content.strip()
        if not content:
            raise ValueError("记忆内容不能为空")

        record = MemoryRecord(
            id=str(uuid.uuid4()),
            user_id=user_id,
            content=content,
            category=category,
            metadata=metadata or {},
        )

        records = self._read_all()
        records.append(record)
        self._write_all(records)

        return record

    def search(
        self,
        query: str,
        user_id: str = "default_user",
        limit: int = 5,
    ) -> list[MemorySearchResult]:
        query = query.strip()
        if not query:
            return []

        records = [
            record for record in self._read_all()
            if record.user_id == user_id
        ]

        results: list[MemorySearchResult] = []

        for record in records:
            score = self._score(query, record.content)
            if score > 0:
                results.append(
                    MemorySearchResult(
                        record=record,
                        score=score,
                    )
                )

        results.sort(key=lambda item: item.score, reverse=True)
        return results[:limit]

    def get_all(self, user_id: str = "default_user") -> list[MemoryRecord]:
        return [
            record for record in self._read_all()
            if record.user_id == user_id
        ]

    def delete_all(self, user_id: str = "default_user") -> int:
        records = self._read_all()
        kept = [record for record in records if record.user_id != user_id]
        deleted_count = len(records) - len(kept)
        self._write_all(kept)
        return deleted_count

    def delete_one(self, memory_id: str, user_id: str = "default_user") -> bool:
        """删除单条记忆，仅在 user_id 匹配时生效。返回是否删除成功。"""
        records = self._read_all()
        before = len(records)
        kept = [
            record
            for record in records
            if not (record.id == memory_id and record.user_id == user_id)
        ]
        if len(kept) == before:
            return False
        self._write_all(kept)
        return True

    def count(self, user_id: str | None = None) -> int:
        records = self._read_all()
        if user_id is None:
            return len(records)
        return len([record for record in records if record.user_id == user_id])

    def _read_all(self) -> list[MemoryRecord]:
        if not self.db_path.exists():
            return []

        text = self.db_path.read_text(encoding="utf-8").strip()
        if not text:
            return []

        raw = json.loads(text)
        return [MemoryRecord(**item) for item in raw]

    def _write_all(self, records: list[MemoryRecord]) -> None:
        data = [asdict(record) for record in records]
        self.db_path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def _score(self, query: str, content: str) -> float:
        """
        本地简易相关性评分。

        设计目标：
        - 允许“网站开发合同”匹配“网站开发合同风险”
        - 避免“租赁合同”仅因为共享“合同”而误匹配“劳动合同”
        - 不依赖外部 embedding
        """

        q_all = set(self._tokenize(query))
        c_all = set(self._tokenize(content))

        if not q_all or not c_all:
            return 0.0

        # 去掉通用词后的有效 token。
        q_tokens = q_all - self.STOPWORDS
        c_tokens = c_all - self.STOPWORDS

        if not q_tokens or not c_tokens:
            return 0.0

        overlap = q_tokens & c_tokens
        if not overlap:
            return 0.0

        # 如果只命中了非常短、非常弱的碎片，降低误召回。
        strong_overlap = overlap & self.DOMAIN_KEYWORDS

        # 对中文 bigram 做一个补充判断：
        # 例如“网站”“开发”“租赁”“劳动”这类词是强信号。
        if not strong_overlap:
            meaningful_overlap = {
                token for token in overlap
                if len(token) >= 2 and token not in self.STOPWORDS
            }
            if not meaningful_overlap:
                return 0.0

        # 使用较保守的 Jaccard-like 评分，避免宽松误匹配。
        union = q_tokens | c_tokens
        base_score = len(overlap) / max(len(union), 1)

        # 强关键词命中时略微加权，但最高不超过 1。
        bonus = 0.15 if strong_overlap else 0.0

        return min(base_score + bonus, 1.0)

    def _tokenize(self, text: str) -> list[str]:
        """
        面向中文法律 MVP 的轻量 tokenizer。

        包含：
        - 中文 bigram
        - 英文/数字词
        - 法律领域关键词
        """

        text = text.lower().strip()

        chinese_chars = re.findall(r"[\u4e00-\u9fff]", text)
        chinese_bigrams = [
            "".join(chinese_chars[i: i + 2])
            for i in range(max(0, len(chinese_chars) - 1))
        ]

        words = re.findall(r"[a-zA-Z0-9_]+", text)

        legal_keywords = re.findall(
            r"知识产权|网站开发|软件开发|劳动合同|租赁合同|"
            r"合同|违约|定金|赔偿|租赁|租房|劳动|解除|责任|履行|"
            r"生效|争议|风险|审查|律师|网站|开发|交付|付款|验收|"
            r"保密|服务|软件",
            text,
        )

        return chinese_bigrams + words + legal_keywords


class Mem0Adapter:
    """
    mem0 真实适配器。

    当前项目默认不启用它，原因：
    - mem0 默认通常需要 OpenAI-compatible embedding
    - 当前开发阶段先保证本地 MVP 稳定
    - 后续补充 embedding 配置后，可把 backend 改成 "mem0"
    """

    def __init__(self) -> None:
        try:
            from mem0 import Memory
        except Exception as exc:
            raise RuntimeError(f"mem0 未安装或不可用：{exc}") from exc

        # 这里保留最小初始化。
        # 真实生产配置建议使用 Memory.from_config(config)。
        self.memory = Memory()

    def add(
        self,
        content: str,
        user_id: str = "default_user",
        category: str = "general",
        metadata: Optional[dict[str, Any]] = None,
    ) -> Any:
        messages = [
            {
                "role": "user",
                "content": content,
            }
        ]
        return self.memory.add(
            messages,
            user_id=user_id,
            metadata={
                "category": category,
                **(metadata or {}),
            },
        )

    def search(
        self,
        query: str,
        user_id: str = "default_user",
        limit: int = 5,
    ) -> Any:
        return self.memory.search(
            query,
            filters={"user_id": user_id},
            limit=limit,
        )


class LegalMemoryManager:
    """
    法律 Agent 长期记忆管理器。

    当前默认 backend="local"：
    - 稳定
    - 可测试
    - 可演示
    - 不泄露密钥
    - 不依赖外部 embedding 服务
    """

    def __init__(
        self,
        backend: str = "local",
        store_path: str | Path | None = None,
        legal_agent: Optional[LegalAgent] = None,
    ) -> None:
        self.backend = backend
        self.legal_agent = legal_agent or LegalAgent()

        if backend == "local":
            self.store = LocalMemoryStore(store_path=store_path)
        elif backend == "mem0":
            self.store = Mem0Adapter()
        else:
            raise ValueError(f"不支持的 memory backend：{backend}")

    def remember(
        self,
        content: str,
        user_id: str = "default_user",
        category: str = "general",
        metadata: Optional[dict[str, Any]] = None,
    ) -> MemoryRecord | Any:
        """
        手动添加一条记忆。
        """
        if not content.strip():
            raise ValueError("记忆内容不能为空")

        return self.store.add(
            content=content,
            user_id=user_id,
            category=category,
            metadata=metadata,
        )

    def recall(
        self,
        query: str,
        user_id: str = "default_user",
        limit: int = 5,
    ) -> list[MemorySearchResult] | Any:
        """
        检索与当前问题相关的记忆。
        """
        return self.store.search(
            query=query,
            user_id=user_id,
            limit=limit,
        )

    def get_all(self, user_id: str = "default_user") -> list[MemoryRecord] | Any:
        if hasattr(self.store, "get_all"):
            return self.store.get_all(user_id=user_id)
        raise RuntimeError("当前 memory backend 不支持 get_all")

    def clear_user(self, user_id: str = "default_user") -> int:
        if hasattr(self.store, "delete_all"):
            return self.store.delete_all(user_id=user_id)
        raise RuntimeError("当前 memory backend 不支持 delete_all")

    def delete_one(self, memory_id: str, user_id: str = "default_user") -> bool:
        """删除单条记忆。"""
        if hasattr(self.store, "delete_one"):
            return self.store.delete_one(memory_id=memory_id, user_id=user_id)
        raise RuntimeError("当前 memory backend 不支持 delete_one")

    def extract_memories_from_interaction(
        self,
        user_message: str,
        assistant_message: str = "",
    ) -> list[tuple[str, str]]:
        """
        从一轮对话中抽取可长期保存的记忆。

        返回：
        [(category, content), ...]
        """
        memories: list[tuple[str, str]] = []
        text = user_message.strip()

        # 1. 用户姓名
        name_patterns = [
            r"我叫([\u4e00-\u9fffA-Za-z0-9_]{2,20})",
            r"我的名字是([\u4e00-\u9fffA-Za-z0-9_]{2,20})",
            r"我是([\u4e00-\u9fffA-Za-z0-9_]{2,20})",
        ]

        for pattern in name_patterns:
            match = re.search(pattern, text)
            if match:
                memories.append(
                    (
                        "user_profile",
                        f"用户姓名可能是：{match.group(1)}",
                    )
                )
                break

        # 2. 偏好
        if "简洁" in text or "简单" in text or "不要太长" in text:
            memories.append(
                (
                    "preference",
                    "用户偏好：回答尽量简洁、直接。",
                )
            )

        if "详细" in text or "一步一步" in text or "解释清楚" in text:
            memories.append(
                (
                    "preference",
                    "用户偏好：回答需要详细，并尽量一步一步解释。",
                )
            )

        # 3. 常见合同类型 / 业务场景
        if "网站开发" in text or "开发网站" in text or "软件开发" in text:
            memories.append(
                (
                    "business_context",
                    "用户关注网站开发合同或软件开发服务合同。",
                )
            )

        if "租房" in text or "租赁" in text:
            memories.append(
                (
                    "business_context",
                    "用户关注租赁合同或租房相关法律问题。",
                )
            )

        if "劳动合同" in text or "入职" in text or "公司不签合同" in text:
            memories.append(
                (
                    "business_context",
                    "用户关注劳动合同或劳动用工风险。",
                )
            )

        # 4. 历史咨询主题
        legal_keywords = [
            "合同",
            "违约",
            "赔偿",
            "定金",
            "租赁",
            "劳动",
            "审查",
            "风险",
            "交付",
            "付款",
            "验收",
            "保密",
            "知识产权",
        ]
        if any(keyword in text for keyword in legal_keywords):
            memories.append(
                (
                    "consultation_topic",
                    f"用户曾咨询：{text[:120]}",
                )
            )

        return memories

    def remember_interaction(
        self,
        user_message: str,
        assistant_message: str = "",
        user_id: str = "default_user",
    ) -> list[MemoryRecord | Any]:
        """
        从一轮对话中抽取并保存记忆。
        """
        extracted = self.extract_memories_from_interaction(
            user_message=user_message,
            assistant_message=assistant_message,
        )

        saved = []
        for category, content in extracted:
            saved.append(
                self.remember(
                    content=content,
                    user_id=user_id,
                    category=category,
                    metadata={
                        "source": "interaction",
                    },
                )
            )

        return saved

    def build_memory_context(
        self,
        query: str,
        user_id: str = "default_user",
        limit: int = 5,
    ) -> str:
        """
        构造可注入 Agent / LLM 的记忆上下文。
        """
        results = self.recall(
            query=query,
            user_id=user_id,
            limit=limit,
        )

        if not results:
            return "暂无相关长期记忆。"

        lines = ["用户相关长期记忆："]

        for item in results:
            if isinstance(item, MemorySearchResult):
                lines.append(
                    f"- [{item.record.category}] {item.record.content}"
                )
            else:
                lines.append(f"- {item}")

        return "\n".join(lines)

    async def chat_with_memory(
        self,
        message: str,
        user_id: str = "default_user",
        use_llm: bool = True,
    ) -> dict[str, Any]:
        """
        带长期记忆的 Agent 对话。

        流程：
        1. 检索相关记忆
        2. 将记忆拼接到用户问题前
        3. 调用 LegalAgent
        4. 从本轮交互抽取新记忆
        """
        memory_context = self.build_memory_context(
            query=message,
            user_id=user_id,
            limit=5,
        )

        enhanced_question = (
            f"{memory_context}\n\n"
            f"当前用户问题：{message}"
        )

        agent_result = await self.legal_agent.run(
            enhanced_question,
            use_llm=use_llm,
        )

        saved_memories = self.remember_interaction(
            user_message=message,
            assistant_message=agent_result.final_answer,
            user_id=user_id,
        )

        return {
            "user_id": user_id,
            "message": message,
            "memory_context": memory_context,
            "saved_memories": saved_memories,
            "agent_result": agent_result,
            "answer": agent_result.final_answer,
        }


memory_manager = LegalMemoryManager()


async def _demo() -> None:
    from backend.config import PROJECT_ROOT
    from backend.core.rag import rag

    # 保证 RAG 示例知识库已索引
    rag.index_directory(PROJECT_ROOT / "data" / "raw")

    user_id = "demo_user"

    print("清空 demo_user 旧记忆")
    memory_manager.clear_user(user_id)

    print("\n第 1 轮：写入用户偏好和业务场景")
    result1 = await memory_manager.chat_with_memory(
        message="我叫小蔡，我经常审查网站开发合同，希望你回答详细一点。",
        user_id=user_id,
        use_llm=False,
    )

    print("保存的记忆：")
    for record in result1["saved_memories"]:
        print("-", record.content)

    print("\n第 2 轮：检索记忆并回答")
    result2 = await memory_manager.chat_with_memory(
        message="这个合同没有写交付时间和违约责任，有什么风险？",
        user_id=user_id,
        use_llm=False,
    )

    print("记忆上下文：")
    print(result2["memory_context"])

    print("\nAgent 回答：")
    print(result2["answer"])

    print("\n当前所有记忆：")
    for record in memory_manager.get_all(user_id):
        print(f"- [{record.category}] {record.content}")


if __name__ == "__main__":
    asyncio.run(_demo())
