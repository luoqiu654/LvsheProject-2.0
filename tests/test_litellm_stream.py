"""直接测试 litellm acompletion streaming"""
import asyncio
import sys
import os

os.chdir(r"c:\Projects\LvsheProject")
sys.path.insert(0, r"c:\Projects\LvsheProject")

from backend.config import settings
import litellm

OUT = r"c:\Projects\LvsheProject\tests\litellm_stream_debug.txt"

async def main():
    with open(OUT, "w", encoding="utf-8") as f:
        api_key = settings.zhipu_api_key
        if hasattr(api_key, "get_secret_value"):
            api_key = api_key.get_secret_value()
        api_base = settings.zhipu_base_url
        model = "glm-4.7-flash"

        f.write(f"api_base: {api_base}\n")
        f.write(f"model: {model}\n")
        f.write(f"api_key set: {bool(api_key)}\n\n")

        messages = [
            {"role": "system", "content": "你是法律助手"},
            {"role": "user", "content": "说一句话"},
        ]

        # 测试1: 非流式
        f.write("=" * 40 + "\n")
        f.write("测试1: 非流式 acompletion\n")
        try:
            resp = await litellm.acompletion(
                model=f"openai/{model}",
                messages=messages,
                api_key=api_key,
                api_base=api_base,
                max_tokens=50,
            )
            f.write(f"  类型: {type(resp)}\n")
            f.write(f"  响应: {resp}\n")
        except Exception as e:
            f.write(f"  异常: {type(e).__name__}: {e}\n")

        # 测试2: 流式 - await 后迭代
        f.write("\n" + "=" * 40 + "\n")
        f.write("测试2: 流式 await acompletion(stream=True) 后迭代\n")
        try:
            response = await litellm.acompletion(
                model=f"openai/{model}",
                messages=messages,
                api_key=api_key,
                api_base=api_base,
                max_tokens=50,
                stream=True,
            )
            f.write(f"  response 类型: {type(response)}\n")
            count = 0
            async for chunk in response:
                count += 1
                f.write(f"  chunk {count}: type={type(chunk)}, repr={repr(chunk)[:200]}\n")
            f.write(f"  总共 {count} 个 chunk\n")
        except Exception as e:
            f.write(f"  异常: {type(e).__name__}: {e}\n")

        # 测试3: 流式 - 不 await 直接迭代
        f.write("\n" + "=" * 40 + "\n")
        f.write("测试3: 流式 acompletion(stream=True) 不 await 直接迭代\n")
        try:
            response = litellm.acompletion(
                model=f"openai/{model}",
                messages=messages,
                api_key=api_key,
                api_base=api_base,
                max_tokens=50,
                stream=True,
            )
            f.write(f"  response 类型: {type(response)}\n")
            count = 0
            async for chunk in response:
                count += 1
                f.write(f"  chunk {count}: type={type(chunk)}, repr={repr(chunk)[:200]}\n")
            f.write(f"  总共 {count} 个 chunk\n")
        except Exception as e:
            f.write(f"  异常: {type(e).__name__}: {e}\n")

        f.write("\n测试完成\n")

asyncio.run(main())
