from fastapi.testclient import TestClient

from backend.main import app


client = TestClient(app)


def test_health():
    response = client.get("/health")

    assert response.status_code == 200
    data = response.json()
    assert data["ok"] is True
    assert data["app_name"] == "LvsheProject"


def test_status():
    response = client.get("/api/status")

    assert response.status_code == 200
    data = response.json()

    assert data["ok"] is True
    assert "qwen" in data["available_llm_providers"]
    assert data["modules"]["rag"] is True
    assert data["modules"]["multi_agents"] is True


def test_rag_index_sample():
    response = client.post("/api/rag/index-sample")

    assert response.status_code == 200
    data = response.json()

    assert data["ok"] is True
    assert data["total_chunks"] >= 0


def test_agent_run_without_llm():
    response = client.post(
        "/api/agent/run",
        json={
            "question": "合同违约可以要求赔偿吗？",
            "use_llm": False,
        },
    )

    assert response.status_code == 200
    data = response.json()

    assert data["ok"] is True
    assert data["tool_name"] in ["law_search", "contract_risk_check", "calculator", "direct_answer"]
    assert data["final_answer"]


def test_skills_run_without_llm():
    response = client.post(
        "/api/skills/run",
        json={
            "input_text": "请审查这个合同条款风险：甲方委托乙方开发网站。",
            "use_llm": False,
        },
    )

    assert response.status_code == 200
    data = response.json()

    assert data["ok"] is True
    assert data["skill_name"] == "contract-risk-review"
    assert data["output_text"]


def test_memory_chat_without_llm():
    response = client.post(
        "/api/memory/chat",
        json={
            "message": "我叫小蔡，我关注网站开发合同风险。",
            "user_id": "api_test_user",
            "use_llm": False,
        },
    )

    assert response.status_code == 200
    data = response.json()

    assert data["ok"] is True
    assert data["user_id"] == "api_test_user"
    assert data["answer"]


def test_gui_browse_dry_run():
    response = client.post(
        "/api/gui/browse",
        json={
            "task": "测试网页观察",
            "start_url": "https://example.com",
            "take_screenshot": False,
            "use_llm_summary": False,
            "use_browser": False,
        },
    )

    assert response.status_code == 200
    data = response.json()

    assert data["ok"] is True
    assert data["title"] == "DRY RUN PAGE"
    assert data["summary"]


def test_multi_agents_debate_without_llm():
    response = client.post(
        "/api/multi-agents/debate",
        json={
            "case": "合同一方违约，另一方想要求赔偿。",
            "use_llm": False,
        },
    )

    assert response.status_code == 200
    data = response.json()

    assert data["ok"] is True
    assert len(data["opinions"]) == 2
    assert data["judge_summary"]
