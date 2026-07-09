"""直接测试 LLMGateway.chat_stream 方法"""
import asyncio
import sys
import os

# 设置项目根目录
os.chdir(r"c:\Projects\LvsheProject")
sys.path.insert(0, r"c:\Projects\LvsheProject")

from backend.core.llm_gateway import gateway, LLMGatewayError

OUT = r"c:\Projects\LvsheProject\tests\stream_debug.txt"

async def main():
    with open(OUT, "w", encoding="utf-8") as f:
        f.write("开始测试 chat_stream...\n")
        f.flush()

        messages = [
            {"role": "system", "content": "你是法律助手"},
            {"role": "user", "content": "你好"},
        ]

        chunk_count = 0
        full_text = ""

        try:
            async for chunk in gateway.chat_stream(
                messages=messages,
                model="glm-4.7-flash",
                max_tokens=50,
            ):
                chunk_count += 1
                full_text += chunk
                f.write(f"  chunk {chunk_count}: {repr(chunk)}\n")
                f.flush()

            f.write(f"\n总共收到 {chunk_count} 个片段\n")
            f.write(f"拼接文本: {full_text}\n")

        except LLMGatewayError as e:
            f.write(f"LLMGatewayError: {e}\n")
        except Exception as e:
            f.write(f"其他异常: {type(e).__name__}: {e}\n")

        f.write("测试完成\n")

asyncio.run(main())
