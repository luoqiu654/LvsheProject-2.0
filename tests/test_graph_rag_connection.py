"""Graph RAG 连接验证脚本。"""
import sys
sys.stdout.reconfigure(encoding="utf-8")

from backend.core.graph_rag import Neo4jConnector, get_graph_rag

print("=" * 50)
print("1. 直接测试 Neo4jConnector")
print("=" * 50)

connector = Neo4jConnector()
print(f"URI: {connector.uri}")
print(f"User: {connector.user}")
print(f"Database: {connector.database}")
print(f"Password configured: {bool(connector.password)}")

ok = connector.connect()
print(f"\nconnect() returned: {ok}")
print(f"is_connected: {connector.is_connected}")
print(f"use_memory_fallback: {connector._use_memory_fallback}")

if connector.is_connected:
    print(f"\nNeo4j 节点数: {connector.count_nodes()}")
    print(f"Neo4j 关系数: {connector.count_relations()}")
else:
    print("\n[警告] Neo4j 未连接，使用内存模式")

connector.close()

print("\n" + "=" * 50)
print("2. 测试 GraphRAG 单例（get_stats 会自动重连）")
print("=" * 50)

rag = get_graph_rag()
stats = rag.get_stats()
print(f"Stats: {stats}")

print("\n[完成]")
