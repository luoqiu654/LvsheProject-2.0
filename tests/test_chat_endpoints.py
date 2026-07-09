"""测试基本 chat 接口和 multi-turn 接口"""
import urllib.request
import json
import sys

BASE = "http://127.0.0.1:8001"
OUT = r"c:\Projects\LvsheProject\tests\chat_test_result.txt"

with open(OUT, "w", encoding="utf-8") as f:
    def log(msg):
        f.write(msg + "\n")
        f.flush()

    # 1. 测试基本 /chat 接口（非流式）
    log("=" * 50)
    log("1. 测试 /api/chat (非流式)")
    body1 = json.dumps({"message": "你好", "use_llm": True}).encode()
    req1 = urllib.request.Request(
        f"{BASE}/api/chat",
        data=body1,
        headers={"Content-Type": "application/json"},
    )
    try:
        r = urllib.request.urlopen(req1, timeout=30)
        result = json.loads(r.read().decode())
        log(f"   状态: {r.status}")
        log(f"   回答: {result.get('answer', '<空>')[:200]}")
    except Exception as e:
        log(f"   错误: {e}")

    # 2. 测试 /api/chat/multi-turn 接口（流式）
    log("=" * 50)
    log("2. 测试 /api/chat/multi-turn (流式)")
    body2 = json.dumps({
        "messages": [{"role": "user", "content": "你好，请用一句话介绍你自己"}],
        "max_tokens": 100,
    }).encode()
    req2 = urllib.request.Request(
        f"{BASE}/api/chat/multi-turn",
        data=body2,
        headers={"Content-Type": "application/json"},
    )
    try:
        r = urllib.request.urlopen(req2, timeout=60)
        full = r.read().decode()
        log(f"   状态: {r.status}")
        log(f"   原始响应长度: {len(full)}")
        log(f"   原始响应前500字符: {full[:500]}")
        # 解析 SSE
        chunks = []
        for line in full.split("\n\n"):
            line = line.strip()
            if line.startswith("data:"):
                payload = line[5:].strip()
                try:
                    obj = json.loads(payload)
                    if "text" in obj:
                        chunks.append(obj["text"])
                except:
                    pass
        log(f"   文本片段数: {len(chunks)}")
        log(f"   拼接文本: {''.join(chunks)[:200]}")
    except Exception as e:
        log(f"   错误: {e}")

    # 3. 测试 /api/models 接口
    log("=" * 50)
    log("3. 测试 /api/models")
    req3 = urllib.request.Request(f"{BASE}/api/models")
    try:
        r = urllib.request.urlopen(req3, timeout=10)
        result = json.loads(r.read().decode())
        log(f"   文本模型: {result.get('text_models', [])}")
        log(f"   默认模型: {result.get('default_model', '')}")
    except Exception as e:
        log(f"   错误: {e}")

    log("=" * 50)
    log("测试完成")
