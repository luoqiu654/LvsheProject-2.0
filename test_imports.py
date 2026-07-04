"""
模块导入测试脚本。
测试所有新增模块是否能正常导入。
"""
import sys
sys.path.insert(0, '.')

print('=== 测试导入各模块 ===')
print()

# 1. 测试配置
try:
    from backend.config import settings
    print('✅ config 导入成功')
    print(f'   APP_NAME: {settings.app_name}')
    print(f'   IMAGE_RAG_ENABLED: {settings.image_rag_enabled}')
    print(f'   GRAPH_RAG_ENABLED: {settings.graph_rag_enabled}')
    print(f'   MINIO_ENABLED: {settings.minio_enabled}')
    print(f'   UNSTRUCTURED_ENABLED: {settings.unstructured_enabled}')
except Exception as e:
    print(f'❌ config 导入失败: {e}')
    import traceback
    traceback.print_exc()

print()

# 2. 测试文档解析器
try:
    from backend.utils.document_parser import document_parser
    print('✅ document_parser 导入成功')
    info = document_parser.get_parser_info()
    print(f'   支持格式: {len(info["supported_extensions"])} 种')
    print(f'   Unstructured可用: {info["unstructured_available"]}')
    print(f'   MinIO连接: {info["minio_connected"]}')
except Exception as e:
    print(f'❌ document_parser 导入失败: {e}')
    import traceback
    traceback.print_exc()

print()

# 3. 测试图像RAG
try:
    from backend.core.image_rag import get_image_rag
    image_rag = get_image_rag()
    print('✅ image_rag 导入成功')
    print(f'   嵌入器类型: {image_rag.embedder.__class__.__name__}')
    print(f'   图像数量: {image_rag.count()}')
except Exception as e:
    print(f'❌ image_rag 导入失败: {e}')
    import traceback
    traceback.print_exc()

print()

# 4. 测试Graph RAG
try:
    from backend.core.graph_rag import get_graph_rag
    graph_rag = get_graph_rag()
    print('✅ graph_rag 导入成功')
    stats = graph_rag.get_stats()
    print(f'   节点数: {stats["nodes"]}')
    print(f'   关系数: {stats["relations"]}')
    print(f'   内存模式: {stats["use_memory_fallback"]}')
except Exception as e:
    print(f'❌ graph_rag 导入失败: {e}')
    import traceback
    traceback.print_exc()

print()

# 5. 测试合同标注
try:
    from backend.core.contract_annotator import contract_annotator
    print('✅ contract_annotator 导入成功')
except Exception as e:
    print(f'❌ contract_annotator 导入失败: {e}')
    import traceback
    traceback.print_exc()

print()

# 6. 测试安全命令
try:
    from backend.core.safe_commands import safe_command_executor
    print('✅ safe_command_executor 导入成功')
except Exception as e:
    print(f'❌ safe_command_executor 导入失败: {e}')
    import traceback
    traceback.print_exc()

print()

# 7. 测试多智能体
try:
    from backend.core.multi_agents import multi_agent_debate
    print('✅ multi_agent_debate 导入成功')
except Exception as e:
    print(f'❌ multi_agent_debate 导入失败: {e}')
    import traceback
    traceback.print_exc()

print()

# 8. 测试API schemas
try:
    from backend.api import schemas
    print('✅ schemas 导入成功')
    print(f'   模型数量: {len([x for x in dir(schemas) if not x.startswith("_")])}')
except Exception as e:
    print(f'❌ schemas 导入失败: {e}')
    import traceback
    traceback.print_exc()

print()
print('=== 导入测试完成 ===')
