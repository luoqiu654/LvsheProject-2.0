import urllib.request, json
r = urllib.request.urlopen("http://127.0.0.1:8001/api/status", timeout=5)
d = json.loads(r.read().decode())
with open(r"c:\Projects\LvsheProject\tests\status_check.txt", "w", encoding="utf-8") as f:
    f.write(f"LLM gateway: {d['modules'].get('llm_gateway')}\n")
    f.write(f"providers: {d.get('available_llm_providers', [])}\n")
    f.write(f"graph_rag_connected: {d['modules'].get('graph_rag_connected')}\n")
