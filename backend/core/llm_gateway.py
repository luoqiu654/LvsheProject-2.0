from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any, Literal, Optional

from litellm import acompletion

from backend.config import settings


ProviderName = Literal["qwen", "glm"]


def _mask_api_key(key: str, min_show: int = 6) -> str:
    """脱敏 API Key，只保留前后几位，中间用星号代替。"""
    s = (key or "").strip()
    if not s:
        return "<empty>"
    if len(s) <= min_show + 4:
        return s[:4] + "*" * (len(s) - 4)
    return s[:min_show] + "*" * (len(s) - min_show - 4) + s[-4:]


@dataclass(frozen=True)
class LLMProviderConfig:
    """
    单个 LLM 提供商配置。

    注意：
    - api_key 只来自 .env
    - model_for_litellm 统一使用 openai/ 前缀
    - api_base 使用各平台 OpenAI 兼容地址
    - api_key 字段在 repr 中隐藏（避免密钥泄露）
    """

    name: ProviderName
    model: str
    api_key: str = field(repr=False)   # ⭐ 关键：隐藏 api_key
    api_base: str

    @property
    def model_for_litellm(self) -> str:
        return f"openai/{self.model}"

    def safe_repr(self) -> str:
        """安全的表示形式，不暴露完整密钥。"""
        return (
            f"LLMProviderConfig("
            f"name={self.name!r}, "
            f"model={self.model!r}, "
            f"api_key={_mask_api_key(self.api_key)!r}, "
            f"api_base={self.api_base!r})"
        )


class LLMGatewayError(RuntimeError):
    """LLM 网关统一异常。"""


class LLMGateway:
    """
    LiteLLM 多模型网关。

    当前支持：
    1. qwen: qwen3.7-plus
    2. glm: glm-5.1

    设计原则：
    - 业务代码不直接调用具体厂商 SDK
    - 业务代码不读取 API Key
    - 后续 Agent / RAG / Multi-Agent 统一依赖本类
    """

    def __init__(self) -> None:
        self._providers = self._build_providers()

    def _secret_to_str(self, value: Any) -> Optional[str]:
        if value is None:
            return None

        if hasattr(value, "get_secret_value"):
            secret = value.get_secret_value()
            return secret if secret else None

        text = str(value)
        return text if text else None

    def _build_providers(self) -> dict[str, LLMProviderConfig]:
        providers: dict[str, LLMProviderConfig] = {}

        qwen_key = self._secret_to_str(settings.qwen_api_key)
        if qwen_key:
            providers["qwen"] = LLMProviderConfig(
                name="qwen",
                model="qwen3.7-plus",
                api_key=qwen_key,
                api_base=settings.qwen_base_url
                or "https://dashscope.aliyuncs.com/compatible-mode/v1",
            )

        glm_key = self._secret_to_str(settings.zhipu_api_key)
        if glm_key:
            providers["glm"] = LLMProviderConfig(
                name="glm",
                model="glm-5.1",
                api_key=glm_key,
                api_base=settings.zhipu_base_url
                or "https://open.bigmodel.cn/api/paas/v4",
            )

        return providers

    def available_providers(self) -> list[str]:
        """
        返回当前可用模型提供商。

        只要 .env 中配置了对应 API Key，就会出现在这里。
        """
        return sorted(self._providers.keys())

    def get_provider_config(self, provider: Optional[str] = None) -> LLMProviderConfig:
        """
        获取指定 provider 配置。

        provider 为空时使用 DEFAULT_LLM_PROVIDER。
        """
        provider_name = provider or settings.default_llm_provider

        if provider_name not in self._providers:
            available = ", ".join(self.available_providers()) or "无"
            raise LLMGatewayError(
                f"LLM provider 不可用：{provider_name}。"
                f"当前可用 provider：{available}。"
                f"请检查 .env 中对应 API Key。"
            )

        return self._providers[provider_name]

    async def chat(
        self,
        messages: list[dict[str, str]],
        provider: Optional[str] = None,
        model: Optional[str] = None,
        temperature: float = 0.2,
        max_tokens: int = 1024,
    ) -> Any:
        """
        调用聊天模型，返回 LiteLLM 原始响应对象。

        messages 示例：
        [
            {"role": "system", "content": "你是法律助手"},
            {"role": "user", "content": "什么是合同？"}
        ]
        """
        config = self.get_provider_config(provider)

        model_name = model or config.model

        try:
            response = await acompletion(
                model=f"openai/{model_name}",
                messages=messages,
                api_key=config.api_key,
                api_base=config.api_base,
                temperature=temperature,
                max_tokens=max_tokens,
            )
            return response

        except Exception as exc:
            raise LLMGatewayError(
                f"调用 LLM 失败，provider={config.name}, model={model_name}。"
                f"错误信息：{exc}"
            ) from exc

    async def chat_text(
        self,
        user_message: str,
        system_message: str = "你是一个严谨、专业、友好的中文法律 AI 助手。",
        provider: Optional[str] = None,
        model: Optional[str] = None,
        temperature: float = 0.2,
        max_tokens: int = 1024,
    ) -> str:
        """
        简化版聊天接口，直接返回文本。
        """
        response = await self.chat(
            messages=[
                {"role": "system", "content": system_message},
                {"role": "user", "content": user_message},
            ],
            provider=provider,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
        )

        return self.extract_text(response)

    async def chat_stream(
        self,
        messages: list[dict[str, str]],
        provider: Optional[str] = None,
        model: Optional[str] = None,
        temperature: float = 0.2,
        max_tokens: int = 1024,
    ):
        """
        流式调用聊天模型，返回异步生成器，yield 每个 chunk 的文本。

        用法：
            async for chunk in gateway.chat_stream(messages):
                print(chunk, end="")
        """
        from litellm import acompletion

        config = self.get_provider_config(provider)
        model_name = model or config.model

        try:
            response = await acompletion(
                model=f"openai/{model_name}",
                messages=messages,
                api_key=config.api_key,
                api_base=config.api_base,
                temperature=temperature,
                max_tokens=max_tokens,
                stream=True,
            )

            async for chunk in response:
                text = self._extract_chunk_text(chunk)
                if text:
                    yield text

        except Exception as exc:
            raise LLMGatewayError(
                f"调用 LLM 流式失败，provider={config.name}, model={model_name}。"
                f"错误信息：{exc}"
            ) from exc

    async def chat_text_stream(
        self,
        user_message: str,
        system_message: str = "你是一个严谨、专业、友好的中文法律 AI 助手。",
        provider: Optional[str] = None,
        model: Optional[str] = None,
        temperature: float = 0.2,
        max_tokens: int = 1024,
    ):
        """
        简化版流式聊天接口，直接 yield 文本片段。
        """
        async for chunk in self.chat_stream(
            messages=[
                {"role": "system", "content": system_message},
                {"role": "user", "content": user_message},
            ],
            provider=provider,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
        ):
            yield chunk

    def _extract_chunk_text(self, chunk: Any) -> str:
        """
        从流式响应的 chunk 中提取文本。
        """
        try:
            if isinstance(chunk, dict):
                choices = chunk.get("choices", [])
                if choices:
                    delta = choices[0].get("delta", {})
                    return delta.get("content", "") or ""
            else:
                if hasattr(chunk, "choices") and chunk.choices:
                    delta = chunk.choices[0].delta
                    if hasattr(delta, "content") and delta.content:
                        return delta.content
            return ""
        except Exception:
            return ""

    def extract_text(self, response: Any) -> str:
        """
        从 LiteLLM / OpenAI 兼容响应中提取文本。

        同时兼容：
        - 对象形式 response.choices[0].message.content
        - dict 形式 response["choices"][0]["message"]["content"]
        """
        try:
            if isinstance(response, dict):
                return response["choices"][0]["message"]["content"]

            return response.choices[0].message.content

        except Exception as exc:
            raise LLMGatewayError(f"无法解析 LLM 响应文本：{exc}") from exc

    async def health_check(self, provider: Optional[str] = None) -> dict[str, Any]:
        """
        真实联网健康检查。

        注意：
        - 会消耗少量 token
        - 只用于本地验证
        """
        config = self.get_provider_config(provider)
        text = await self.chat_text(
            user_message="请只回复：OK",
            system_message="你是健康检查程序。",
            provider=config.name,
            max_tokens=16,
            temperature=0,
        )

        return {
            "provider": config.name,
            "model": config.model,
            "api_base": config.api_base,
            "ok": "OK" in text.upper(),
            "reply": text,
        }


gateway = LLMGateway()


async def _demo() -> None:
    print("可用 provider：", gateway.available_providers())

    for provider in gateway.available_providers():
        result = await gateway.health_check(provider)
        print(result)


if __name__ == "__main__":
    asyncio.run(_demo())