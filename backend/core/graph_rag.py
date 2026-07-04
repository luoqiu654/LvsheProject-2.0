"""
Graph RAG模块 - 基于Neo4j的法律知识图谱检索增强。

功能：
1. 构建法律知识图谱：法律条款、案例、当事人关系等
2. 实体和关系提取：从文本中提取法律实体和关系
3. 图检索增强：当用户询问"类似案例"或"法律关系"时使用
4. 返回结构化结果：相关节点、关系路径、置信度
5. 与文本RAG协同工作，实现混合检索

技术选型：
- 图数据库：Neo4j
- 集成方式：直接使用neo4j driver（保持核心逻辑自主可控）
- 实体提取：基于规则 + LLM辅助
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass, field
from typing import Any, Optional

from backend.config import settings
from backend.core.llm_gateway import LLMGateway, LLMGatewayError, gateway as default_gateway


# ========== 数据结构 ==========

@dataclass
class GraphNode:
    """
    知识图谱节点。
    """
    node_id: str
    node_type: str  # "Law" / "Case" / "Person" / "Organization" / "Concept"
    name: str
    properties: dict[str, Any] = field(default_factory=dict)
    confidence: float = 1.0


@dataclass
class GraphRelation:
    """
    知识图谱关系。
    """
    relation_id: str
    relation_type: str  # "REFERENCES" / "SIMILAR_TO" / "INVOLVES" / "APPLIES_TO"
    source_id: str
    target_id: str
    properties: dict[str, Any] = field(default_factory=dict)
    confidence: float = 1.0


@dataclass
class GraphSearchResult:
    """
    图检索结果。
    """
    nodes: list[GraphNode]
    relations: list[GraphRelation]
    paths: list[list[str]]  # 节点ID路径
    summary: str
    confidence: float


@dataclass
class GraphRAGAnswer:
    """
    Graph RAG最终回答。
    """
    query: str
    search_result: GraphSearchResult
    answer: str
    related_laws: list[GraphNode]
    related_cases: list[GraphNode]


# ========== 实体提取器 ==========

class LegalEntityExtractor:
    """
    法律实体提取器。

    从法律文本中提取实体和关系。
    采用规则 + LLM混合方式。
    """

    # 法律实体类型关键词
    LAW_KEYWORDS = [
        "法", "条例", "规定", "办法", "细则", "通则", "法典",
        "合同法", "民法典", "劳动法", "公司法", "刑法", "民法",
    ]

    CASE_KEYWORDS = [
        "案", "案件", "判例", "案例", "判决书", "裁定书",
    ]

    PERSON_PATTERNS = [
        r"甲方[：:]\s*([^，,。；;\n]+)",
        r"乙方[：:]\s*([^，,。；;\n]+)",
        r"原告[：:]\s*([^，,。；;\n]+)",
        r"被告[：:]\s*([^，,。；;\n]+)",
        r"当事人[：:]\s*([^，,。；;\n]+)",
    ]

    def __init__(self, llm_gateway: Optional[LLMGateway] = None) -> None:
        self.llm_gateway = llm_gateway or default_gateway

    def extract_entities(self, text: str, use_llm: bool = True) -> tuple[list[GraphNode], list[GraphRelation]]:
        """
        从文本中提取实体和关系。

        Args:
            text: 法律文本
            use_llm: 是否使用LLM增强提取

        Returns:
            (节点列表, 关系列表)
        """
        nodes: list[GraphNode] = []
        relations: list[GraphRelation] = []

        # 1. 基于规则提取
        rule_nodes, rule_relations = self._extract_by_rules(text)
        nodes.extend(rule_nodes)
        relations.extend(rule_relations)

        # 2. LLM增强提取（可选）
        if use_llm:
            try:
                llm_nodes, llm_relations = self._extract_by_llm(text)
                nodes.extend(llm_nodes)
                relations.extend(llm_relations)
            except LLMGatewayError:
                # LLM失败时只用规则
                pass

        # 3. 去重
        nodes = self._deduplicate_nodes(nodes)
        relations = self._deduplicate_relations(relations)

        return nodes, relations

    def _extract_by_rules(self, text: str) -> tuple[list[GraphNode], list[GraphRelation]]:
        """基于规则提取实体。"""
        nodes: list[GraphNode] = []
        relations: list[GraphRelation] = []

        # 提取法律条款
        law_entities = self._extract_law_entities(text)
        nodes.extend(law_entities)

        # 提取案例
        case_entities = self._extract_case_entities(text)
        nodes.extend(case_entities)

        # 提取当事人
        person_entities = self._extract_person_entities(text)
        nodes.extend(person_entities)

        # 构建关系（案例引用法律）
        for case in case_entities:
            for law in law_entities[:3]:  # 每个案例最多关联3个法律
                relations.append(GraphRelation(
                    relation_id=str(uuid.uuid4())[:12],
                    relation_type="REFERENCES",
                    source_id=case.node_id,
                    target_id=law.node_id,
                    properties={"description": f"{case.name} 引用 {law.name}"},
                    confidence=0.6,
                ))

        # 构建关系（当事人涉及案例）
        for person in person_entities:
            for case in case_entities:
                relations.append(GraphRelation(
                    relation_id=str(uuid.uuid4())[:12],
                    relation_type="INVOLVES",
                    source_id=case.node_id,
                    target_id=person.node_id,
                    properties={"description": f"{case.name} 涉及 {person.name}"},
                    confidence=0.5,
                ))

        return nodes, relations

    def _extract_law_entities(self, text: str) -> list[GraphNode]:
        """提取法律实体。"""
        nodes = []
        seen = set()

        # 匹配《XXX法》格式
        pattern = r"《([^》]+)》"
        matches = re.findall(pattern, text)

        for match in matches:
            # 判断是否是法律
            if any(kw in match for kw in self.LAW_KEYWORDS):
                if match not in seen:
                    seen.add(match)
                    nodes.append(GraphNode(
                        node_id=f"law_{hash(match) % 100000:05d}",
                        node_type="Law",
                        name=match,
                        properties={
                            "full_name": match,
                            "category": self._classify_law(match),
                        },
                        confidence=0.9,
                    ))

        return nodes

    def _extract_case_entities(self, text: str) -> list[GraphNode]:
        """提取案例实体。"""
        nodes = []
        seen = set()

        # 匹配XXX案格式
        pattern = r"([^，,。；;\n《》]{2,20}案)"
        matches = re.findall(pattern, text)

        for match in matches:
            if any(kw in match for kw in self.CASE_KEYWORDS):
                if match not in seen and len(match) > 2:
                    seen.add(match)
                    nodes.append(GraphNode(
                        node_id=f"case_{hash(match) % 100000:05d}",
                        node_type="Case",
                        name=match,
                        properties={
                            "case_type": self._classify_case(match),
                        },
                        confidence=0.7,
                    ))

        return nodes

    def _extract_person_entities(self, text: str) -> list[GraphNode]:
        """提取当事人实体。"""
        nodes = []
        seen = set()

        for pattern in self.PERSON_PATTERNS:
            matches = re.findall(pattern, text)
            for match in matches:
                match = match.strip()
                if match and match not in seen and len(match) < 50:
                    seen.add(match)
                    # 判断是个人还是组织
                    node_type = "Organization" if any(
                        kw in match for kw in ["公司", "企业", "厂", "店", "所", "中心", "集团"]
                    ) else "Person"

                    nodes.append(GraphNode(
                        node_id=f"entity_{hash(match) % 100000:05d}",
                        node_type=node_type,
                        name=match,
                        properties={
                            "role": self._extract_role(pattern),
                        },
                        confidence=0.8,
                    ))

        return nodes

    def _classify_law(self, name: str) -> str:
        """分类法律。"""
        if "合同" in name:
            return "合同法"
        elif "劳动" in name:
            return "劳动法"
        elif "公司" in name:
            return "公司法"
        elif "婚姻" in name or "继承" in name:
            return "婚姻家庭法"
        elif "物权" in name:
            return "物权法"
        elif "侵权" in name:
            return "侵权责任法"
        else:
            return "其他"

    def _classify_case(self, name: str) -> str:
        """分类案例。"""
        if "合同" in name:
            return "合同纠纷"
        elif "劳动" in name:
            return "劳动争议"
        elif "婚姻" in name:
            return "婚姻家庭"
        elif "侵权" in name:
            return "侵权纠纷"
        else:
            return "其他"

    def _extract_role(self, pattern: str) -> str:
        """从模式中提取角色。"""
        if "甲方" in pattern:
            return "甲方"
        elif "乙方" in pattern:
            return "乙方"
        elif "原告" in pattern:
            return "原告"
        elif "被告" in pattern:
            return "被告"
        else:
            return "当事人"

    async def _extract_by_llm(self, text: str) -> tuple[list[GraphNode], list[GraphRelation]]:
        """使用LLM提取实体和关系。"""
        prompt = f"""
请从下面的法律文本中提取实体和关系。

要求：
1. 提取法律、案例、当事人等实体
2. 提取实体之间的关系（引用、涉及、相似等）
3. 用JSON格式输出
4. 只提取明确提到的内容

输出格式：
{{
  "nodes": [
    {{"id": "唯一ID", "type": "Law/Case/Person/Organization", "name": "实体名称", "confidence": 0.8}}
  ],
  "relations": [
    {{"id": "唯一ID", "type": "REFERENCES/INVOLVES/SIMILAR_TO", "source": "源节点ID", "target": "目标节点ID", "confidence": 0.7}}
  ]
}}

文本：
{text[:2000]}
""".strip()

        try:
            response = await self.llm_gateway.chat_text(
                user_message=prompt,
                system_message="你是专业的法律知识图谱构建助手。",
                max_tokens=1024,
                temperature=0.1,
            )

            # 解析JSON
            import json
            try:
                data = json.loads(response)
            except json.JSONDecodeError:
                # 尝试提取JSON部分
                json_match = re.search(r'\{.*\}', response, re.DOTALL)
                if json_match:
                    data = json.loads(json_match.group())
                else:
                    return [], []

            nodes = []
            for n in data.get("nodes", []):
                nodes.append(GraphNode(
                    node_id=str(n.get("id", uuid.uuid4())[:12]),
                    node_type=n.get("type", "Concept"),
                    name=n.get("name", ""),
                    confidence=float(n.get("confidence", 0.5)),
                ))

            relations = []
            for r in data.get("relations", []):
                relations.append(GraphRelation(
                    relation_id=str(r.get("id", uuid.uuid4())[:12]),
                    relation_type=r.get("type", "RELATED_TO"),
                    source_id=r.get("source", ""),
                    target_id=r.get("target", ""),
                    confidence=float(r.get("confidence", 0.5)),
                ))

            return nodes, relations

        except Exception:
            return [], []

    def _deduplicate_nodes(self, nodes: list[GraphNode]) -> list[GraphNode]:
        """节点去重。"""
        seen = {}
        result = []

        for node in nodes:
            key = (node.node_type, node.name)
            if key not in seen:
                seen[key] = node
                result.append(node)
            else:
                # 保留置信度高的
                if node.confidence > seen[key].confidence:
                    seen[key] = node
                    result = [n for n in result if not (n.node_type == node.node_type and n.name == node.name)]
                    result.append(node)

        return result

    def _deduplicate_relations(self, relations: list[GraphRelation]) -> list[GraphRelation]:
        """关系去重。"""
        seen = set()
        result = []

        for rel in relations:
            key = (rel.relation_type, rel.source_id, rel.target_id)
            if key not in seen:
                seen.add(key)
                result.append(rel)

        return result


# ========== Neo4j图数据库连接器 ==========

class Neo4jConnector:
    """
    Neo4j数据库连接器。

    设计原则：
    1. 懒加载连接
    2. 自动降级：如果Neo4j不可用，使用内存模拟
    3. 核心逻辑自主可控，不依赖LangChain的Neo4jGraph
    """

    def __init__(
        self,
        uri: Optional[str] = None,
        user: Optional[str] = None,
        password: Optional[str] = None,
        database: Optional[str] = None,
    ) -> None:
        self.uri = uri or settings.neo4j_uri
        self.user = user or settings.neo4j_user
        self.password = password or (
            settings.neo4j_password.get_secret_value()
            if settings.neo4j_password
            else None
        )
        self.database = database or settings.neo4j_database

        self._driver = None
        self._connected = False
        self._use_memory_fallback = False

        # 内存fallback存储
        self._memory_nodes: dict[str, GraphNode] = {}
        self._memory_relations: list[GraphRelation] = []

    def connect(self) -> bool:
        """
        连接Neo4j数据库。

        Returns:
            True 表示连接成功，False 表示失败（将使用内存fallback）
        """
        if self._connected:
            return True

        if not self.password:
            print("[GraphRAG] Neo4j密码未配置，使用内存模式")
            self._use_memory_fallback = True
            return False

        try:
            from neo4j import GraphDatabase

            self._driver = GraphDatabase.driver(
                self.uri,
                auth=(self.user, self.password),
            )
            # 测试连接
            self._driver.verify_connectivity()
            self._connected = True
            print("[GraphRAG] Neo4j连接成功")
            return True

        except Exception as exc:
            print(f"[GraphRAG] Neo4j连接失败，使用内存模式: {exc}")
            self._use_memory_fallback = True
            return False

    def close(self) -> None:
        """关闭连接。"""
        if self._driver:
            self._driver.close()
            self._driver = None
            self._connected = False

    @property
    def is_connected(self) -> bool:
        return self._connected

    def add_node(self, node: GraphNode) -> None:
        """添加节点。"""
        if self._use_memory_fallback or not self.connect():
            self._memory_nodes[node.node_id] = node
            return

        try:
            with self._driver.session(database=self.database) as session:
                # 构建属性
                props = {
                    "name": node.name,
                    "node_type": node.node_type,
                    "confidence": node.confidence,
                    **node.properties,
                }

                # 使用MERGE避免重复
                query = f"""
                MERGE (n:{node.node_type} {{node_id: $node_id}})
                SET n.name = $name,
                    n.confidence = $confidence,
                    n += $properties
                """
                session.run(
                    query,
                    node_id=node.node_id,
                    name=node.name,
                    confidence=node.confidence,
                    properties=node.properties,
                )
        except Exception as exc:
            print(f"[GraphRAG] 添加节点失败: {exc}")
            self._memory_nodes[node.node_id] = node

    def add_relation(self, relation: GraphRelation) -> None:
        """添加关系。"""
        if self._use_memory_fallback or not self.connect():
            self._memory_relations.append(relation)
            return

        try:
            with self._driver.session(database=self.database) as session:
                query = f"""
                MATCH (a {{node_id: $source_id}})
                MATCH (b {{node_id: $target_id}})
                MERGE (a)-[r:{relation.relation_type}]->(b)
                SET r.confidence = $confidence,
                    r += $properties
                """
                session.run(
                    query,
                    source_id=relation.source_id,
                    target_id=relation.target_id,
                    confidence=relation.confidence,
                    properties=relation.properties,
                )
        except Exception as exc:
            print(f"[GraphRAG] 添加关系失败: {exc}")
            self._memory_relations.append(relation)

    def add_nodes(self, nodes: list[GraphNode]) -> None:
        """批量添加节点。"""
        for node in nodes:
            self.add_node(node)

    def add_relations(self, relations: list[GraphRelation]) -> None:
        """批量添加关系。"""
        for rel in relations:
            self.add_relation(rel)

    def search_similar_cases(self, query: str, limit: int = 5) -> list[GraphNode]:
        """搜索相似案例。"""
        if self._use_memory_fallback or not self.connect():
            return self._memory_search(query, node_type="Case", limit=limit)

        try:
            with self._driver.session(database=self.database) as session:
                # 简单的文本匹配搜索
                query = """
                MATCH (c:Case)
                WHERE c.name CONTAINS $keyword
                   OR c.description CONTAINS $keyword
                RETURN c
                ORDER BY c.confidence DESC
                LIMIT $limit
                """
                # 提取关键词
                keyword = self._extract_keyword(query)
                result = session.run(query, keyword=keyword, limit=limit)

                nodes = []
                for record in result:
                    node_data = record["c"]
                    nodes.append(GraphNode(
                        node_id=node_data.get("node_id", ""),
                        node_type="Case",
                        name=node_data.get("name", ""),
                        properties=dict(node_data),
                        confidence=node_data.get("confidence", 0.5),
                    ))
                return nodes

        except Exception as exc:
            print(f"[GraphRAG] 搜索失败: {exc}")
            return self._memory_search(query, node_type="Case", limit=limit)

    def search_related_laws(self, query: str, limit: int = 5) -> list[GraphNode]:
        """搜索相关法律。"""
        if self._use_memory_fallback or not self.connect():
            return self._memory_search(query, node_type="Law", limit=limit)

        try:
            with self._driver.session(database=self.database) as session:
                query_cypher = """
                MATCH (l:Law)
                WHERE l.name CONTAINS $keyword
                RETURN l
                ORDER BY l.confidence DESC
                LIMIT $limit
                """
                keyword = self._extract_keyword(query)
                result = session.run(query_cypher, keyword=keyword, limit=limit)

                nodes = []
                for record in result:
                    node_data = record["l"]
                    nodes.append(GraphNode(
                        node_id=node_data.get("node_id", ""),
                        node_type="Law",
                        name=node_data.get("name", ""),
                        properties=dict(node_data),
                        confidence=node_data.get("confidence", 0.5),
                    ))
                return nodes

        except Exception as exc:
            print(f"[GraphRAG] 搜索法律失败: {exc}")
            return self._memory_search(query, node_type="Law", limit=limit)

    def get_related_nodes(
        self,
        node_id: str,
        relation_type: Optional[str] = None,
        limit: int = 10,
    ) -> tuple[list[GraphNode], list[GraphRelation]]:
        """获取关联节点。"""
        if self._use_memory_fallback or not self.connect():
            return self._memory_get_related(node_id, relation_type, limit)

        # Neo4j实现
        # ... 简化版本，返回空
        return [], []

    def _memory_search(
        self,
        query: str,
        node_type: Optional[str] = None,
        limit: int = 5,
    ) -> list[GraphNode]:
        """内存模式搜索。"""
        results = []
        query_lower = query.lower()

        for node in self._memory_nodes.values():
            if node_type and node.node_type != node_type:
                continue

            # 简单的文本匹配
            score = 0
            if query_lower in node.name.lower():
                score += 1.0
            for key, value in node.properties.items():
                if isinstance(value, str) and query_lower in value.lower():
                    score += 0.5

            if score > 0:
                results.append((node, score))

        # 排序
        results.sort(key=lambda x: x[1], reverse=True)
        return [node for node, _ in results[:limit]]

    def _memory_get_related(
        self,
        node_id: str,
        relation_type: Optional[str] = None,
        limit: int = 10,
    ) -> tuple[list[GraphNode], list[GraphRelation]]:
        """内存模式获取关联节点。"""
        related_relations = []
        related_node_ids = set()

        for rel in self._memory_relations:
            if relation_type and rel.relation_type != relation_type:
                continue

            if rel.source_id == node_id:
                related_relations.append(rel)
                related_node_ids.add(rel.target_id)
            elif rel.target_id == node_id:
                related_relations.append(rel)
                related_node_ids.add(rel.source_id)

            if len(related_node_ids) >= limit:
                break

        related_nodes = [
            self._memory_nodes[nid]
            for nid in related_node_ids
            if nid in self._memory_nodes
        ]

        return related_nodes, related_relations

    def _extract_keyword(self, query: str) -> str:
        """从查询中提取关键词。"""
        # 简单实现：取查询中的核心词
        words = re.findall(r"[\u4e00-\u9fa5]+", query)
        if words:
            # 取最长的词作为关键词
            return max(words, key=len)
        return query[:10]

    def count_nodes(self) -> int:
        """统计节点数。"""
        if self._use_memory_fallback:
            return len(self._memory_nodes)
        return 0  # Neo4j版本需实现

    def count_relations(self) -> int:
        """统计关系数。"""
        if self._use_memory_fallback:
            return len(self._memory_relations)
        return 0


# ========== Graph RAG主类 ==========

class GraphRAG:
    """
    基于知识图谱的RAG引擎。

    功能：
    1. 从法律文本构建知识图谱
    2. 图检索：相似案例、相关法律、关系路径
    3. 与文本RAG协同工作
    4. 返回结构化结果
    """

    def __init__(
        self,
        connector: Optional[Neo4jConnector] = None,
        extractor: Optional[LegalEntityExtractor] = None,
        llm_gateway: Optional[LLMGateway] = None,
    ) -> None:
        self.connector = connector or Neo4jConnector()
        self.extractor = extractor or LegalEntityExtractor()
        self.llm_gateway = llm_gateway or default_gateway

        # 尝试连接
        self.connector.connect()

    def index_text(
        self,
        text: str,
        source: str = "",
        use_llm: bool = True,
    ) -> tuple[int, int]:
        """
        索引文本，提取实体和关系并存入图谱。

        Args:
            text: 法律文本
            source: 来源标识
            use_llm: 是否使用LLM增强提取

        Returns:
            (节点数, 关系数)
        """
        # 提取实体和关系
        nodes, relations = self.extractor.extract_entities(text, use_llm=use_llm)

        # 添加source属性
        for node in nodes:
            node.properties["source"] = source
        for rel in relations:
            rel.properties["source"] = source

        # 存入图谱
        self.connector.add_nodes(nodes)
        self.connector.add_relations(relations)

        return len(nodes), len(relations)

    def index_file(self, file_path: str, use_llm: bool = True) -> tuple[int, int]:
        """索引文件。"""
        from pathlib import Path
        path = Path(file_path)
        text = path.read_text(encoding="utf-8")
        return self.index_text(text, source=str(path), use_llm=use_llm)

    async def search(
        self,
        query: str,
        search_type: str = "auto",
        top_k: int = 5,
    ) -> GraphSearchResult:
        """
        图检索。

        Args:
            query: 查询文本
            search_type: 检索类型 "case" / "law" / "relation" / "auto"
            top_k: 返回结果数

        Returns:
            图检索结果
        """
        # 自动判断检索类型
        if search_type == "auto":
            search_type = self._classify_query(query)

        nodes: list[GraphNode] = []
        relations: list[GraphRelation] = []
        paths: list[list[str]] = []

        if search_type == "case":
            # 搜索相似案例
            cases = self.connector.search_similar_cases(query, limit=top_k)
            nodes.extend(cases)

            # 获取每个案例的相关法律
            for case in cases:
                related_laws, rels = self.connector.get_related_nodes(
                    case.node_id,
                    relation_type="REFERENCES",
                )
                nodes.extend(related_laws)
                relations.extend(rels)

                # 构建路径
                for law in related_laws:
                    paths.append([case.node_id, law.node_id])

        elif search_type == "law":
            # 搜索相关法律
            laws = self.connector.search_related_laws(query, limit=top_k)
            nodes.extend(laws)

        elif search_type == "relation":
            # 搜索关系
            # 先找相关节点，再找关系
            cases = self.connector.search_similar_cases(query, limit=3)
            laws = self.connector.search_related_laws(query, limit=3)
            nodes.extend(cases)
            nodes.extend(laws)

        # 生成摘要
        summary = self._generate_summary(query, nodes, search_type)

        # 计算置信度
        confidence = sum(n.confidence for n in nodes) / max(len(nodes), 1)

        return GraphSearchResult(
            nodes=nodes,
            relations=relations,
            paths=paths,
            summary=summary,
            confidence=confidence,
        )

    async def answer(
        self,
        query: str,
        top_k: int = 5,
        use_llm_answer: bool = True,
    ) -> GraphRAGAnswer:
        """
        Graph RAG问答。

        Args:
            query: 用户问题
            top_k: 返回结果数
            use_llm_answer: 是否使用LLM生成回答

        Returns:
            Graph RAG回答
        """
        # 图检索
        search_result = await self.search(query, top_k=top_k)

        # 分类节点
        related_laws = [n for n in search_result.nodes if n.node_type == "Law"]
        related_cases = [n for n in search_result.nodes if n.node_type == "Case"]

        if not use_llm_answer:
            return GraphRAGAnswer(
                query=query,
                search_result=search_result,
                answer=f"已找到 {len(related_laws)} 条相关法律，{len(related_cases)} 个相关案例。",
                related_laws=related_laws,
                related_cases=related_cases,
            )

        # 构建上下文
        context_parts = []

        if related_laws:
            context_parts.append("相关法律：")
            for i, law in enumerate(related_laws, 1):
                context_parts.append(f"{i}. {law.name}")

        if related_cases:
            context_parts.append("\n相关案例：")
            for i, case in enumerate(related_cases, 1):
                context_parts.append(f"{i}. {case.name}")

        context_text = "\n".join(context_parts)

        # LLM生成回答
        prompt = f"""
请根据知识图谱检索结果，回答用户的法律问题。

要求：
1. 先给出简洁结论
2. 列出相关法律和案例
3. 如果信息不足，请明确说明
4. 不要编造不存在的法律条文

用户问题：
{query}

知识图谱检索结果：
{context_text}
""".strip()

        try:
            answer_text = await self.llm_gateway.chat_text(
                user_message=prompt,
                system_message="你是专业的法律知识图谱问答助手。",
                max_tokens=800,
                temperature=0.2,
            )
        except LLMGatewayError:
            answer_text = "知识图谱检索完成，但LLM生成回答失败。"

        return GraphRAGAnswer(
            query=query,
            search_result=search_result,
            answer=answer_text,
            related_laws=related_laws,
            related_cases=related_cases,
        )

    def _classify_query(self, query: str) -> str:
        """分类查询类型。"""
        if any(kw in query for kw in ["案例", "判例", "类似", "案"]):
            return "case"
        elif any(kw in query for kw in ["法律", "法条", "规定", "条款"]):
            return "law"
        elif any(kw in query for kw in ["关系", "关联", "路径"]):
            return "relation"
        else:
            return "case"  # 默认搜索案例

    def _generate_summary(
        self,
        query: str,
        nodes: list[GraphNode],
        search_type: str,
    ) -> str:
        """生成检索摘要。"""
        law_count = sum(1 for n in nodes if n.node_type == "Law")
        case_count = sum(1 for n in nodes if n.node_type == "Case")
        person_count = sum(1 for n in nodes if n.node_type in ("Person", "Organization"))

        parts = []
        if law_count:
            parts.append(f"{law_count} 条相关法律")
        if case_count:
            parts.append(f"{case_count} 个相关案例")
        if person_count:
            parts.append(f"{person_count} 个相关当事人")

        if parts:
            return f"找到 {'、'.join(parts)}"
        else:
            return "未找到相关节点"

    def get_stats(self) -> dict[str, Any]:
        """获取图谱统计信息。"""
        return {
            "nodes": self.connector.count_nodes(),
            "relations": self.connector.count_relations(),
            "is_connected": self.connector.is_connected,
            "use_memory_fallback": self.connector._use_memory_fallback,
        }


# 全局单例
_graph_rag: Optional[GraphRAG] = None


def get_graph_rag() -> GraphRAG:
    """获取Graph RAG单例。"""
    global _graph_rag
    if _graph_rag is None:
        _graph_rag = GraphRAG()
    return _graph_rag


graph_rag = get_graph_rag


if __name__ == "__main__":
    # 简单测试
    rag = get_graph_rag()
    print(f"Graph RAG初始化完成: {rag.get_stats()}")

    # 测试索引
    sample_text = """
根据《民法典》第五百七十七条规定，当事人一方不履行合同义务或者履行合同义务不符合约定的，
应当承担继续履行、采取补救措施或者赔偿损失等违约责任。

在张三诉李四合同纠纷案中，法院认为被告李四未按合同约定交付货物，构成违约。
"""

    nodes, relations = rag.index_text(sample_text, source="test")
    print(f"\n索引完成：{nodes} 个节点，{relations} 个关系")
    print(f"当前统计：{rag.get_stats()}")
