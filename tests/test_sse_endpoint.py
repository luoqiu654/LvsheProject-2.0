import urllib.request
import json

body = json.dumps({
    "messages": [{"role": "user", "content": "你好，请用一句话介绍你自己"}],
    "max_tokens": 80,
}).encode()

req = urllib.request.Request(
    "http://127.0.0.1:8001/api/chat/multi-turn",
    data=body,
    headers={"Content-Type": "application/json"},
)

try:
    r = urllib.request.urlopen(req, timeout=30)
    text = r.read().decode()
    with open(r"c:\Projects\LvsheProject\tests\sse_result.txt", "w", encoding="utf-8") as f:
        f.write(text)
    print("OK, wrote", len(text), "chars")
except Exception as e:
    with open(r"c:\Projects\LvsheProject\tests\sse_result.txt", "w", encoding="utf-8") as f:
        f.write(f"ERROR: {e}")
    print("ERROR:", e)
