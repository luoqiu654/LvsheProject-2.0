from __future__ import annotations

import asyncio
import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Optional
from urllib.parse import urlparse

from backend.config import PROJECT_ROOT, settings
from backend.core.llm_gateway import LLMGateway, LLMGatewayError, gateway as default_gateway


@dataclass
class BrowserLink:
    """
    页面链接信息。
    """
    text: str
    href: str


@dataclass
class BrowserObservation:
    """
    浏览器观察结果。
    """
    url: str
    title: str
    text_preview: str
    links: list[BrowserLink] = field(default_factory=list)
    screenshot_path: Optional[str] = None


@dataclass
class GUIAgentResult:
    """
    GUI Agent 运行结果。
    """
    task: str
    start_url: str
    observation: BrowserObservation
    summary: str
    steps: list[str]


class GUIAgentSafetyError(RuntimeError):
    """GUI Agent 安全异常。"""


class PlaywrightGUIAgent:
    """
    Playwright 浏览器自动化 Agent。
    （省略原有注释，功能不变）
    """

    def __init__(
        self,
        llm_gateway: Optional[LLMGateway] = None,
        output_dir: str | Path | None = None,
        allowed_domains: Optional[list[str]] = None,
    ) -> None:
        self.llm_gateway = llm_gateway or default_gateway
        self.output_dir = Path(output_dir or PROJECT_ROOT / "data" / "gui_agent")
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.allowed_domains = allowed_domains or []
        self.max_text_chars = 5000
        self.max_links = 20

    async def run(
        self,
        task: str,
        start_url: str,
        take_screenshot: bool = True,
        use_llm_summary: bool = True,
        use_browser: bool = True,
    ) -> GUIAgentResult:
        steps = [
            f"收到任务：{task}",
            f"起始网址：{start_url}",
        ]
        self.validate_url(start_url)
        steps.append("安全检查：URL 通过校验")

        if use_browser:
            observation = await self._observe_page(url=start_url, take_screenshot=take_screenshot)
            steps.append("浏览器观察：已打开网页并提取页面信息")
        else:
            observation = BrowserObservation(
                url=start_url,
                title="DRY RUN PAGE",
                text_preview="这是不启动浏览器的测试观察结果。",
                links=[],
                screenshot_path=None,
            )
            steps.append("浏览器观察：dry-run 模式，未启动真实浏览器")

        if use_llm_summary:
            summary = await self._summarize_with_llm(task=task, observation=observation)
            steps.append("总结节点：已调用 LLM 生成页面总结")
        else:
            summary = self._fallback_summary(task=task, observation=observation)
            steps.append("总结节点：使用本地模板生成页面总结")

        return GUIAgentResult(
            task=task,
            start_url=start_url,
            observation=observation,
            summary=summary,
            steps=steps,
        )

    async def _observe_page(self, url: str, take_screenshot: bool = True) -> BrowserObservation:
        try:
            from playwright.async_api import async_playwright
        except Exception as exc:
            raise RuntimeError(
                "Playwright 未安装。请先执行：uv add playwright && uv run playwright install chromium"
            ) from exc

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=settings.browser_headless)
            page = await browser.new_page(viewport={"width": 1366, "height": 768})
            await page.goto(url, wait_until="domcontentloaded", timeout=30000)
            try:
                await page.wait_for_load_state("networkidle", timeout=5000)
            except Exception:
                pass

            title = await page.title()
            text = await self._safe_inner_text(page)
            text_preview = self._clean_text(text)[:self.max_text_chars]
            links = await self._extract_links(page)
            screenshot_path = None
            if take_screenshot:
                screenshot_path = await self._take_screenshot(page)
            await browser.close()

        return BrowserObservation(
            url=url,
            title=title,
            text_preview=text_preview,
            links=links,
            screenshot_path=screenshot_path,
        )

    async def _safe_inner_text(self, page: Any) -> str:
        try:
            return await page.locator("body").inner_text(timeout=5000)
        except Exception:
            return ""

    async def _extract_links(self, page: Any) -> list[BrowserLink]:
        raw_links = await page.eval_on_selector_all(
            "a",
            """
            elements => elements.slice(0, 50).map(a => ({
                text: (a.innerText || a.textContent || '').trim(),
                href: a.href || ''
            }))
            """,
        )
        links: list[BrowserLink] = []
        for item in raw_links:
            text = self._clean_text(str(item.get("text", "")))
            href = str(item.get("href", "")).strip()
            if not href:
                continue
            if len(text) > 80:
                text = text[:80] + "..."
            links.append(BrowserLink(text=text or href, href=href))
            if len(links) >= self.max_links:
                break
        return links

    async def _take_screenshot(self, page: Any) -> str:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"gui_agent_{timestamp}_{uuid.uuid4().hex[:8]}.png"
        path = self.output_dir / filename
        await page.screenshot(path=str(path), full_page=True)
        return str(path.relative_to(PROJECT_ROOT))

    async def _summarize_with_llm(self, task: str, observation: BrowserObservation) -> str:
        links_text = "\n".join(
            f"- {link.text}: {link.href}" for link in observation.links[:10]
        )
        prompt = f"""
你是一个网页浏览 GUI Agent。
请根据页面观察结果完成用户任务。

用户任务：
{task}

页面 URL：
{observation.url}

页面标题：
{observation.title}

页面正文摘要：
{observation.text_preview[:3000]}

页面链接：
{links_text}

要求：
1. 用中文回答
2. 先总结页面主要内容
3. 再说明与用户任务相关的信息
4. 如果页面信息不足，请明确说明
5. 不要编造网页中没有的信息
""".strip()
        try:
            return await self.llm_gateway.chat_text(
                user_message=prompt,
                system_message="你是谨慎的网页浏览与信息提取助手。",
                max_tokens=1000,
                temperature=0.2,
            )
        except LLMGatewayError:
            return self._fallback_summary(task=task, observation=observation)

    def _fallback_summary(self, task: str, observation: BrowserObservation) -> str:
        link_lines = "\n".join(
            f"- {link.text}: {link.href}" for link in observation.links[:5]
        )
        return (
            f"任务：{task}\n\n"
            f"页面标题：{observation.title}\n"
            f"页面 URL：{observation.url}\n\n"
            f"页面文本预览：\n{observation.text_preview[:800]}\n\n"
            f"前 5 个链接：\n{link_lines or '未提取到链接'}\n\n"
            f"截图路径：{observation.screenshot_path or '未截图'}"
        )

    def validate_url(self, url: str) -> None:
        parsed = urlparse(url)
        if parsed.scheme not in {"http", "https"}:
            raise GUIAgentSafetyError(
                f"不允许访问该协议：{parsed.scheme or '空协议'}。仅允许 http/https。"
            )
        if not parsed.netloc:
            raise GUIAgentSafetyError("URL 缺少域名。")
        host = parsed.hostname or ""
        if self.allowed_domains:
            allowed = any(
                host == domain or host.endswith("." + domain)
                for domain in self.allowed_domains
            )
            if not allowed:
                raise GUIAgentSafetyError(
                    f"域名不在允许列表中：{host}。允许列表：{self.allowed_domains}"
                )

    def _clean_text(self, text: str) -> str:
        text = text.replace("\r\n", "\n").replace("\r", "\n")
        text = re.sub(r"[ \t]+", " ", text)
        # 去除每行末尾的空格
        text = re.sub(r" +\n", "\n", text)
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text.strip()


gui_agent = PlaywrightGUIAgent()


async def _demo() -> None:
    result = await gui_agent.run(
        task="打开网页，提取页面标题、主要内容和截图。",
        start_url="https://example.com/",
        take_screenshot=True,
        use_llm_summary=True,
        use_browser=True,
    )
    print("执行步骤：")
    for step in result.steps:
        print("-", step)
    print("\n页面标题：")
    print(result.observation.title)
    print("\n页面 URL：")
    print(result.observation.url)
    print("\n截图路径：")
    print(result.observation.screenshot_path)
    print("\n链接：")
    for link in result.observation.links:
        print(f"- {link.text}: {link.href}")
    print("\n总结：")
    print(result.summary)


if __name__ == "__main__":
    asyncio.run(_demo())