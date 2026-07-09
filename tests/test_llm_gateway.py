import asyncio

from backend.core.llm_gateway import LLMGateway, LLMGatewayError


def test_available_providers():
    gateway = LLMGateway()
    providers = gateway.available_providers()

    # 现在返回的是 4 个 GLM 文本模型名
    assert "glm-4.7-flash" in providers
    assert "glm-4.6" in providers


def test_available_models_includes_vision_and_image():
    gateway = LLMGateway()
    models = gateway.available_models()

    # 文本模型
    assert "glm-4.7-flash" in models
    # 视觉模型
    assert "glm-ocr" in models
    # 图像生成模型
    assert "glm-image" in models


def test_provider_config_not_expose_secret():
    gateway = LLMGateway()
    config = gateway.get_provider_config("glm-4.7-flash")

    assert config.model == "glm-4.7-flash"
    assert config.model_for_litellm == "openai/glm-4.7-flash"
    assert "bigmodel.cn" in config.api_base

    # api_key 不能在 repr 中泄露
    text = repr(config)
    assert "iW7DnQlFqJkff9nt" not in text
    assert "3aa2324d49144f6499c6e301cc18084a" not in text


def test_legacy_provider_name_maps_to_default():
    """旧 provider 名（qwen/glm）应映射到默认模型（向后兼容）。"""
    gateway = LLMGateway()
    config_qwen = gateway.get_provider_config("qwen")
    config_glm = gateway.get_provider_config("glm")
    config_default = gateway.get_provider_config(None)

    # 旧 provider 名都映射到默认模型
    assert config_qwen.model == config_default.model
    assert config_glm.model == config_default.model


def test_missing_provider_raises_error_when_no_api_key(monkeypatch):
    """没有 API Key 时调用应抛出异常。"""
    gateway = LLMGateway()

    # 如果已配置 API Key，跳过这个测试
    if gateway.is_available:
        return

    try:
        gateway.get_provider_config("glm-4.7-flash")
    except LLMGatewayError as exc:
        assert "API Key" in str(exc) or "未配置" in str(exc)
    else:
        raise AssertionError("未配置 API Key 时应该抛出异常")


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
        assert kwargs["model"] == "openai/glm-4.7-flash"
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

    # 如果没有 API Key，跳过（避免 _ensure_available 抛错）
    if not gateway.is_available:
        return

    result = asyncio.run(
        gateway.chat_text(
            user_message="你好",
            model="glm-4.7-flash",
        )
    )

    assert result == "模拟回复成功"


def test_chat_text_legacy_provider_with_mock(monkeypatch):
    """旧 provider 名 'glm' 应该能正常调用并使用默认模型。"""
    async def fake_acompletion(**kwargs):
        # 默认模型应该是 glm-4.7-flash
        assert kwargs["model"] == "openai/glm-4.7-flash"

        return {
            "choices": [
                {
                    "message": {
                        "content": "向后兼容成功"
                    }
                }
            ]
        }

    monkeypatch.setattr(
        "backend.core.llm_gateway.acompletion",
        fake_acompletion,
    )

    gateway = LLMGateway()

    if not gateway.is_available:
        return

    result = asyncio.run(
        gateway.chat_text(
            user_message="你好",
            provider="glm",  # 旧 provider 名
        )
    )

    assert result == "向后兼容成功"
