"""验证所有新路由是否正确注册"""
import urllib.request
import json

OUT = r"c:\Projects\LvsheProject\tests\routes_verify.txt"
BASE = "http://127.0.0.1:8001"

with open(OUT, "w", encoding="utf-8") as f:
    def log(msg):
        f.write(msg + "\n")
        f.flush()

    # 1. 健康检查
    log("=" * 50)
    log("1. 后端健康检查 /health")
    try:
        r = urllib.request.urlopen(f"{BASE}/health", timeout=5)
        log(f"  状态: {r.status}, 响应: {r.read().decode()[:200]}")
    except Exception as e:
        log(f"  错误: {e}")

    # 2. OpenAPI 文档 - 检查所有路由
    log("\n2. 检查 OpenAPI 路由列表")
    try:
        r = urllib.request.urlopen(f"{BASE}/openapi.json", timeout=10)
        spec = json.loads(r.read().decode())
        paths = list(spec.get("paths", {}).keys())
        log(f"  总路由数: {len(paths)}")
        # 分类显示新路由
        new_routes = [p for p in paths if "/contract/" in p or "/expert/" in p]
        log(f"  合同诊疗+专家会诊路由:")
        for p in sorted(new_routes):
            methods = list(spec["paths"][p].keys())
            log(f"    {methods} {p}")
        # 检查关键新路由
        expected = [
            "/api/contract/visual-review",
            "/api/expert/trial",
            "/api/expert/trial/stream",
        ]
        for e in expected:
            found = e in paths
            log(f"  {'✓' if found else '✗'} {e}: {'已注册' if found else '未找到'}")
    except Exception as e:
        log(f"  错误: {e}")

    # 3. 模型列表
    log("\n3. /api/models")
    try:
        r = urllib.request.urlopen(f"{BASE}/api/models", timeout=10)
        result = json.loads(r.read().decode())
        log(f"  文本模型: {result.get('text_models', [])}")
        log(f"  视觉模型: {result.get('vision_model', '')}")
        log(f"  图像模型: {result.get('image_model', '')}")
    except Exception as e:
        log(f"  错误: {e}")

    # 4. 系统状态
    log("\n4. /api/status")
    try:
        r = urllib.request.urlopen(f"{BASE}/api/status", timeout=10)
        result = json.loads(r.read().decode())
        modules = result.get("modules", {})
        log(f"  Graph RAG连接: {modules.get('graph_rag_connected', 'N/A')}")
        log(f"  LLM网关: {modules.get('llm_gateway', 'N/A')}")
    except Exception as e:
        log(f"  错误: {e}")

    log("\n" + "=" * 50)
    log("验证完成")
