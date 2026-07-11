from __future__ import annotations

import asyncio
import base64
import traceback
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal, Optional

from litellm import acompletion

from backend.config import settings


# 模型类型：文本 / 视觉 / 图像生成
ModelType = Literal["text", "vision", "image"]


def _mask_api_key(key: str, min_show: int = 6) -> str:
    """脱敏 API Key，只保留前后几位，中间用星号代替。"""
    s = (key or "").strip()
    if not s:
        return "<empty>"
    if len(s) <= min_show + 4:
        return s[:4] + "*" * (len(s) - 4)
    return s[:min_show] + "*" * (len(s) - min_show - 4) + s[-4:]


def _detect_mime_from_bytes(data: bytes) -> str:
    """通过图片字节头判断实际 MIME 类型（不依赖文件扩展名）。"""
    if len(data) >= 4 and data[:4] == b'\x89PNG':
        return "png"
    if len(data) >= 2 and data[:2] == b'\xff\xd8':
        return "jpeg"
    if len(data) >= 6 and data[:6] in (b'GIF87a', b'GIF89a'):
        return "gif"
    if len(data) >= 12 and data[:4] == b'RIFF' and data[8:12] == b'WEBP':
        return "webp"
    return "png"


@dataclass(frozen=True)
class ProviderModelConfig:
    """
    LLM 供应商单个模型配置。

    支持多供应商（智谱AI / 百炼 / 通用OpenAI兼容接口），
    所有供应商共用同一个数据结构，只是模型名和 API 地址不同。

    - model: 模型名（如 glm-4.7-flash / qwen-plus / gpt-4o）
    - model_type: 模型类型（text / vision / image）
    - api_key 只来自 .env
    - model_for_litellm 统一使用 openai/ 前缀（OpenAI 兼容接口）
    - api_key 字段在 repr 中隐藏（避免密钥泄露）
    """

    model: str
    model_type: ModelType
    api_key: str = field(repr=False)
    api_base: str

    @property
    def model_for_litellm(self) -> str:
        return f"openai/{self.model}"

    def safe_repr(self) -> str:
        """安全的表示形式，不暴露完整密钥。"""
        return (
            f"ProviderModelConfig("
            f"model={self.model!r}, "
            f"model_type={self.model_type!r}, "
            f"api_key={_mask_api_key(self.api_key)!r}, "
            f"api_base={self.api_base!r})"
        )


# 向后兼容别名
ZhipuModelConfig = ProviderModelConfig


class LLMGatewayError(RuntimeError):
    """LLM 网关统一异常。"""


class LLMGateway:
    """
    多供应商统一 LLM 网关。

    支持通过 LLM_PROVIDER 环境变量切换供应商：
    - zhipu（智谱AI）：GLM-4.7-Flash / GLM-4.6 / GLM-5.2 / GLM-OCR / GLM-Image
    - dashscope（百炼/通义千问）：qwen-turbo / qwen-plus / qwen-max / qwen-vl-max
    - openai（通用OpenAI兼容）：适用于任何 OpenAI 兼容接口的供应商

    所有供应商通过 LiteLLM + openai/ 前缀统一接入，业务代码无需感知供应商差异。

    设计原则：
    - 业务代码不直接调用具体厂商 SDK
    - 业务代码不读取 API Key
    - Agent / RAG / Multi-Agent 统一依赖本类
    - 切换供应商只需修改 .env 中的 LLM_PROVIDER 和对应 API Key
    """

    def __init__(self) -> None:
        self._provider: str = settings.active_provider
        self._api_key: Optional[str] = self._secret_to_str(settings.active_api_key)
        self._api_base: str = settings.active_base_url
        self._default_model: str = settings.active_default_model
        self._vision_model: str = settings.active_vision_model
        self._image_model: str = settings.active_image_model
        self._chat_models: list[str] = settings.active_chat_models_list

    def _secret_to_str(self, value: Any) -> Optional[str]:
        if value is None:
            return None
        if hasattr(value, "get_secret_value"):
            secret = value.get_secret_value()
            return secret if secret else None
        text = str(value)
        return text if text else None

    @property
    def is_available(self) -> bool:
        """是否已配置可用的 API Key。"""
        return self._api_key is not None and len(self._api_key) > 0

    def _ensure_available(self) -> None:
        """确保 API Key 已配置。"""
        if not self.is_available:
            provider = self._provider
            key_map = {
                "zhipu": "ZHIPU_API_KEY",
                "dashscope": "DASHSCOPE_API_KEY",
                "openai": "OPENAI_COMPAT_API_KEY",
            }
            env_name = key_map.get(provider, "LLM API Key")
            raise LLMGatewayError(
                f"LLM API Key 未配置（当前供应商: {provider}）。"
                f"请在 .env 中设置 {env_name}。"
            )

    def _resolve_model(self, model: Optional[str]) -> str:
        """
        解析模型名。

        - 传入有效模型名则直接使用
        - 传入 None 则使用默认模型
        - 传入 "qwen" / "glm" 等旧 provider 名则映射到默认模型（向后兼容）
        """
        if model is None or model.strip() == "":
            return self._default_model

        model = model.strip()

        # 向后兼容：旧的 provider 名映射到默认模型
        legacy_providers = {"qwen", "glm", "zhipu"}
        if model.lower() in legacy_providers:
            return self._default_model

        return model

    def _build_config(self, model: Optional[str] = None, model_type: ModelType = "text") -> ProviderModelConfig:
        """构建模型配置。"""
        self._ensure_available()

        if model_type == "vision":
            resolved_model = self._vision_model
        elif model_type == "image":
            resolved_model = self._image_model
        else:
            resolved_model = self._resolve_model(model)

        return ZhipuModelConfig(
            model=resolved_model,
            model_type=model_type,
            api_key=self._api_key,  # type: ignore[arg-type]
            api_base=self._api_base,
        )

    def available_providers(self) -> list[str]:
        """
        返回当前可用的文本模型列表。

        向后兼容：旧代码用这个方法获取 provider 列表。
        现在返回的是模型名列表（如 ["glm-4.7-flash", "glm-4.7-flashx", ...]）。
        """
        if not self.is_available:
            return []
        return list(self._chat_models)

    def available_models(self) -> list[str]:
        """返回所有可用模型列表（包括文本、视觉、图像生成）。"""
        if not self.is_available:
            return []
        return list(self._chat_models) + [self._vision_model, self._image_model]

    def get_provider_config(self, provider: Optional[str] = None) -> ProviderModelConfig:
        """
        获取指定模型的配置。

        向后兼容：provider 参数现在接受模型名。
        为空时使用默认模型。
        """
        return self._build_config(model=provider, model_type="text")

    # ========== 文本对话 ==========

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

        provider / model 参数现在都接受模型名（如 "glm-4.7-flash"）。
        两者效果相同，model 优先级更高。
        """
        config = self._build_config(model=model or provider, model_type="text")
        model_name = config.model

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
                f"调用 LLM 失败，model={model_name}。"
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
        流式调用聊天模型，返回异步生成器，yield 每个 chunk 的**正式回答**文本。

        注意：只 yield content 字段（正式回答），不 yield reasoning_content（思考过程）。
        若需同时获取思考过程，使用 chat_stream_with_reasoning()。

        用法：
            async for chunk in gateway.chat_stream(messages):
                print(chunk, end="")
        """
        from litellm import acompletion

        config = self._build_config(model=model or provider, model_type="text")
        model_name = config.model

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
                f"调用 LLM 流式失败，model={model_name}。"
                f"错误信息：{exc}"
            ) from exc

    async def chat_stream_with_reasoning(
        self,
        messages: list[dict[str, str]],
        provider: Optional[str] = None,
        model: Optional[str] = None,
        temperature: float = 0.2,
        max_tokens: int = 1024,
    ):
        """
        流式调用聊天模型，返回异步生成器，yield (type, text) 元组。

        - type="reasoning"：思考过程（GLM-4.7-Flash 等推理模型的 reasoning_content）
        - type="content"：正式回答（content 字段）

        用法：
            async for typ, text in gateway.chat_stream_with_reasoning(messages):
                if typ == "reasoning":
                    # 展示在思考面板
                    pass
                else:
                    # 展示为正式回答
                    pass
        """
        from litellm import acompletion

        config = self._build_config(model=model or provider, model_type="text")
        model_name = config.model

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
                reasoning = self._extract_chunk_reasoning(chunk)
                if reasoning:
                    yield ("reasoning", reasoning)
                content = self._extract_chunk_text(chunk)
                if content:
                    yield ("content", content)

        except Exception as exc:
            raise LLMGatewayError(
                f"调用 LLM 流式失败，model={model_name}。"
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
        从流式响应的 chunk 中提取**正式回答**文本（content 字段）。

        注意：GLM-4.7-Flash 等推理模型会先输出 reasoning_content（思考过程），
        再输出 content（正式回答）。此方法只返回 content，不返回 reasoning_content。
        思考过程通过 _extract_chunk_reasoning 单独提取。
        """
        try:
            if isinstance(chunk, dict):
                choices = chunk.get("choices", [])
                if choices:
                    delta = choices[0].get("delta", {})
                    return delta.get("content") or ""
            else:
                if hasattr(chunk, "choices") and chunk.choices:
                    delta = chunk.choices[0].delta
                    return getattr(delta, "content", None) or ""
            return ""
        except Exception:
            return ""

    def _extract_chunk_reasoning(self, chunk: Any) -> str:
        """
        从流式响应的 chunk 中提取**思考过程**文本（reasoning_content 字段）。

        仅 GLM-4.7-Flash 等推理模型会输出此字段。
        普通模型（如 glm-4.6）无此字段，返回空字符串。
        """
        try:
            if isinstance(chunk, dict):
                choices = chunk.get("choices", [])
                if choices:
                    delta = choices[0].get("delta", {})
                    return delta.get("reasoning_content") or ""
            else:
                if hasattr(chunk, "choices") and chunk.choices:
                    delta = chunk.choices[0].delta
                    return getattr(delta, "reasoning_content", None) or ""
            return ""
        except Exception:
            return ""

    def extract_text(self, response: Any) -> str:
        """
        从 LiteLLM / OpenAI 兼容响应中提取**正式回答**文本（content 字段）。

        注意：只返回 content，不返回 reasoning_content。
        若需获取思考过程，使用 extract_reasoning()。
        """
        try:
            if isinstance(response, dict):
                msg = response["choices"][0]["message"]
                return msg.get("content") or ""

            msg = response.choices[0].message
            return getattr(msg, "content", None) or ""

        except Exception as exc:
            raise LLMGatewayError(f"无法解析 LLM 响应文本：{exc}") from exc

    def extract_reasoning(self, response: Any) -> str:
        """
        从 LLM 响应中提取**思考过程**文本（reasoning_content 字段）。

        仅 GLM-4.7-Flash 等推理模型有此字段，普通模型返回空字符串。
        """
        try:
            if isinstance(response, dict):
                msg = response["choices"][0]["message"]
                return msg.get("reasoning_content") or ""

            msg = response.choices[0].message
            return getattr(msg, "reasoning_content", None) or ""
        except Exception:
            return ""

    # ========== 视觉模型（GLM-OCR 文档分析）==========

    async def chat_with_vision(
        self,
        image: str | Path | bytes,
        prompt: str = "请识别并提取图片中的所有文字内容，保持原有格式。",
        system_message: str = "你是一个专业的文档识别助手，擅长从图片中提取文字、表格和公式。",
        temperature: float = 0.1,
        max_tokens: int = 2048,
    ) -> str:
        """
        使用 GLM-OCR 视觉模型识别图片内容。

        Args:
            image: 图片路径 / base64字符串 / 图片字节
            prompt: 识别提示词
            system_message: 系统提示词
            temperature: 温度参数
            max_tokens: 最大输出 token 数

        Returns:
            识别到的文本内容
        """
        config = self._build_config(model_type="vision")
        model_name = config.model

        # 将图片转为 base64 data URL
        image_data_url = self._image_to_data_url(image)

        # 图片大小检查：base64 编码后过长时拒绝（避免请求超时或超出模型限制）
        b64_payload = (
            image_data_url.split(",", 1)[1]
            if "," in image_data_url
            else image_data_url
        )
        if len(b64_payload) > 5_000_000:
            raise LLMGatewayError(
                f"图片过大，base64 编码后长度约 {len(b64_payload)} 字符"
                f"（上限 5000000）。请压缩图片后重试。"
            )

        # 详细日志（调试用）
        print(f"[LLMGateway] chat_with_vision 调用参数：")
        print(f"  model_name: {model_name}")
        print(f"  api_base: {config.api_base}")
        print(f"  image_data_url (前80字符): {image_data_url[:80]}")
        print(f"  image_base64_size: {len(b64_payload)} 字符")

        messages = [
            {"role": "system", "content": system_message},
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": image_data_url}},
                ],
            },
        ]

        try:
            response = await acompletion(
                model=f"openai/{model_name}",
                messages=messages,
                api_key=config.api_key,
                api_base=config.api_base,
                temperature=temperature,
                max_tokens=max_tokens,
            )
            return self.extract_text(response)

        except Exception as exc:
            print(f"[LLMGateway] 视觉模型调用失败，model={model_name}")
            print(f"  错误类型: {type(exc).__name__}")
            print(f"  错误信息: {exc}")
            traceback.print_exc()
            raise LLMGatewayError(
                f"调用视觉模型失败，model={model_name}。"
                f"错误类型：{type(exc).__name__}，错误信息：{exc}"
            ) from exc

    def _image_to_data_url(self, image: str | Path | bytes) -> str:
        """
        将图片转为 base64 data URL。

        支持：
        - 文件路径
        - base64 字符串（已编码）
        - 图片字节

        MIME 类型通过图片字节头自动检测（不依赖扩展名）。
        """
        # 如果已经是 data URL 格式
        if isinstance(image, str) and image.startswith("data:image"):
            return image

        # 如果是 base64 字符串（不带 data: 前缀）
        if isinstance(image, str) and not image.startswith("/") and not image.startswith("data:"):
            # 尝试判断是否是文件路径
            if not Path(image).exists():
                # 假设是 base64 字符串，解码后通过字节头检测 MIME 类型
                try:
                    decoded = base64.b64decode(image)
                    mime_ext = _detect_mime_from_bytes(decoded)
                except Exception:
                    mime_ext = "png"
                return f"data:image/{mime_ext};base64,{image}"

        # 从文件读取
        if isinstance(image, (str, Path)):
            path = Path(image)
            if not path.exists():
                raise LLMGatewayError(f"图片文件不存在：{image}")

            image_bytes = path.read_bytes()
            # 优先通过字节头检测实际格式，扩展名仅作 fallback
            mime_ext = _detect_mime_from_bytes(image_bytes)
        else:
            # 字节输入：通过字节头检测 MIME 类型（而非固定 png）
            image_bytes = image
            mime_ext = _detect_mime_from_bytes(image_bytes)

        base64_str = base64.b64encode(image_bytes).decode("utf-8")
        return f"data:image/{mime_ext};base64,{base64_str}"

    # ========== 图像生成模型（GLM-Image）==========

    async def generate_image(
        self,
        prompt: str,
        size: str = "1024x1024",
        n: int = 1,
        user_id: str = "default",
    ) -> list[str]:
        """
        使用 GLM-Image 模型生成图片。

        Args:
            prompt: 图片描述提示词
            size: 图片尺寸（如 1024x1024 / 768x1344 / 1344x768）
            n: 生成图片数量
            user_id: 用户ID（用于存储隔离）

        Returns:
            生成的图片文件路径列表
        """
        config = self._build_config(model_type="image")
        model_name = config.model

        try:
            from litellm import aimage_generation

            response = await aimage_generation(
                model=f"openai/{model_name}",
                prompt=prompt,
                api_key=config.api_key,
                api_base=config.api_base,
                n=n,
                size=size,
            )

            # 解析响应，保存图片
            image_paths = self._save_generated_images(response, user_id)
            return image_paths

        except Exception as exc:
            raise LLMGatewayError(
                f"调用图像生成模型失败，model={model_name}。"
                f"错误信息：{exc}"
            ) from exc

    def _save_generated_images(self, response: Any, user_id: str) -> list[str]:
        """
        保存生成的图片到用户隔离目录。

        Returns:
            保存的图片文件路径列表
        """
        from datetime import datetime
        import re

        # 用户目录隔离（安全设计）
        safe_user_id = re.sub(r'[^a-zA-Z0-9_\-]', '_', user_id) or "anonymous"
        output_dir = settings.contract_output_path / safe_user_id / "generated_images"
        output_dir.mkdir(parents=True, exist_ok=True)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        saved_paths: list[str] = []

        try:
            images = []
            if isinstance(response, dict):
                images = response.get("data", [])
            elif hasattr(response, "data"):
                images = response.data

            for i, img_data in enumerate(images):
                # 兼容两种格式：URL 或 base64
                if isinstance(img_data, dict):
                    url = img_data.get("url", "")
                    b64 = img_data.get("b64_json", "")
                elif hasattr(img_data, "url"):
                    url = img_data.url
                    b64 = getattr(img_data, "b64_json", "")
                else:
                    continue

                filename = f"{timestamp}_{i}.png"
                file_path = output_dir / filename

                if b64:
                    # base64 编码的图片
                    image_bytes = base64.b64decode(b64)
                    file_path.write_bytes(image_bytes)
                elif url:
                    # URL 格式，下载图片
                    import requests
                    img_response = requests.get(url, timeout=60)
                    if img_response.status_code == 200:
                        file_path.write_bytes(img_response.content)
                    else:
                        raise LLMGatewayError(f"下载生成图片失败：{img_response.status_code}")

                saved_paths.append(str(file_path))

        except Exception as exc:
            raise LLMGatewayError(f"保存生成图片失败：{exc}") from exc

        return saved_paths

    # ========== 健康检查 ==========

    async def health_check(self, model: Optional[str] = None) -> dict[str, Any]:
        """
        真实联网健康检查。

        注意：
        - 会消耗少量 token
        - 只用于本地验证
        """
        config = self._build_config(model=model, model_type="text")
        model_name = config.model

        text = await self.chat_text(
            user_message="请只回复：OK",
            system_message="你是健康检查程序。",
            model=model_name,
            max_tokens=16,
            temperature=0,
        )

        return {
            "provider": self._provider,
            "model": model_name,
            "api_base": config.api_base,
            "ok": "OK" in text.upper(),
            "reply": text,
        }


gateway = LLMGateway()


async def _demo() -> None:
    print(f"当前供应商: {gateway._provider}")
    print("可用文本模型：", gateway.available_providers())
    print("所有模型：", gateway.available_models())

    if not gateway.is_available:
        print("⚠️ LLM API Key 未配置，请检查 .env")
        return

    # 测试默认模型
    result = await gateway.health_check()
    print("健康检查：", result)


if __name__ == "__main__":
    asyncio.run(_demo())
