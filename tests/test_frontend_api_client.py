from frontend.api_client import LvsheAPIClient


def test_api_client_base_url_strip():
    client = LvsheAPIClient(base_url="http://127.0.0.1:8000/")

    assert client.base_url == "http://127.0.0.1:8000"


def test_api_client_has_methods():
    client = LvsheAPIClient()

    assert hasattr(client, "health")
    assert hasattr(client, "rag_ask")
    assert hasattr(client, "agent_run")
    assert hasattr(client, "skill_run")
    assert hasattr(client, "memory_chat")
    assert hasattr(client, "multi_agents_debate")
    assert hasattr(client, "gui_browse")
