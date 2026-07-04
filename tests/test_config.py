from backend.config import settings


def test_settings_load():
    summary = settings.safe_summary()

    assert summary["app_name"] == "LvsheProject"
    assert "backend" in summary
    assert "default_llm_provider" in summary
    assert "chroma_path" in summary
    assert "upload_path" in summary


def test_secret_not_exposed():
    summary = settings.safe_summary()
    text = str(summary).lower()

    assert "sk-" not in text
    assert "api_key=" not in text
