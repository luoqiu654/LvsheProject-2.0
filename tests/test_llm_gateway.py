import asyncio

from backend.core.llm_gateway import LLMGateway, LLMGatewayError


def test_available_providers():
    gateway = LLMGateway()
    providers = gateway.available_providers()

    assert "qwen" in providers
    assert "glm" in providers


def test_provider_config_not_expose_secret():
    gateway = LLMGateway()
    config = gateway.get_provider_config("qwen")

    assert config.name == "qwen"
    assert config.model == "qwen3.7-plus"
    assert config.model_for_litellm == "openai/qwen3.7-plus"
    assert "compatible-mode/v1" in config.api_base

    text = repr(config)
    assert "sk-" not in text.lower()


def test_missing_provider_raises_error():
    gateway = LLMGateway()

    try:
        gateway.get_provider_config("not-exist")
    except LLMGatewayError as exc:
        assert "不可用" in str(exc)
    else:
        raise AssertionError("不存在的 provider 应该抛出异常")


def test_extract_text_from_dict_response():
    gateway = LLMGateway()

    fake_response = {
        "choices": [
            {
                "message": {
                    "content": "测试成功"
                }
            }
        ]
    }

    assert gateway.extract_text(fake_response) == "测试成功"


def test_chat_text_with_mock(monkeypatch):
    async def fake_acompletion(**kwargs):
        assert kwargs["model"] == "openai/qwen3.7-plus"
        assert kwargs["api_key"]
        assert kwargs["api_base"]
        assert kwargs["messages"][0]["role"] == "system"
        assert kwargs["messages"][1]["role"] == "user"

        return {
            "choices": [
                {
                    "message": {
                        "content": "模拟回复成功"
                    }
                }
            ]
        }

    monkeypatch.setattr(
        "backend.core.llm_gateway.acompletion",
        fake_acompletion,
    )

    gateway = LLMGateway()

    result = asyncio.run(
        gateway.chat_text(
            user_message="你好",
            provider="qwen",
        )
    )

    assert result == "模拟回复成功"
