"""检查 streaming chunk 的 delta 结构"""
import asyncio
import sys
import os

os.chdir(r"c:\Projects\LvsheProject")
sys.path.insert(0, r"c:\Projects\LvsheProject")

from backend.config import settings
import litellm

OUT = r"c:\Projects\LvsheProject\tests\chunk_delta_debug.txt"

async def main():
    with open(OUT, "w", encoding="utf-8") as f:
        api_key = settings.zhipu_api_key
        if hasattr(api_key, "get_secret_value"):
            api_key = api_key.get_secret_value()

        messages = [
            {"role": "system", "content": "你是法律助手"},
            {"role": "user", "content": "说一句话"},
        ]

        response = await litellm.acompletion(
            model="openai/glm-4.7-flash",
            messages=messages,
            api_key=api_key,
            api_base=settings.zhipu_base_url,
            max_tokens=100,
            stream=True,
        )

        count = 0
        has_content = 0
        has_reasoning = 0

        async for chunk in response:
            count += 1
            try:
                delta = chunk.choices[0].delta
                content = getattr(delta, "content", None)
                reasoning = getattr(delta, "reasoning_content", None)

                if content:
                    has_content += 1
                if reasoning:
                    has_reasoning += 1

                if count <= 5 or count >= count - 3:
                    f.write(f"chunk {count}: content={repr(content)}, reasoning={repr(reasoning)[:100]}\n")
            except Exception as e:
                f.write(f"chunk {count}: error={e}\n")

        f.write(f"\n总共 {count} chunks, 有content的 {has_content}, 有reasoning的 {has_reasoning}\n")

asyncio.run(main())
