import asyncio

from backend.core.gui_agent import GUIAgentSafetyError, PlaywrightGUIAgent


def test_validate_url_allows_http_https():
    agent = PlaywrightGUIAgent()

    agent.validate_url("https://example.com")
    agent.validate_url("http://example.com")


def test_validate_url_blocks_dangerous_protocols():
    agent = PlaywrightGUIAgent()

    dangerous_urls = [
        "file:///C:/Windows/System32/drivers/etc/hosts",
        "javascript:alert(1)",
        "data:text/html,<h1>x</h1>",
    ]

    for url in dangerous_urls:
        try:
            agent.validate_url(url)
        except GUIAgentSafetyError:
            pass
        else:
            raise AssertionError(f"危险 URL 应该被拦截：{url}")


def test_allowed_domains():
    agent = PlaywrightGUIAgent(
        allowed_domains=["example.com"],
    )

    agent.validate_url("https://example.com")
    agent.validate_url("https://sub.example.com")

    try:
        agent.validate_url("https://not-example.com")
    except GUIAgentSafetyError:
        pass
    else:
        raise AssertionError("非允许域名应该被拦截")


def test_clean_text():
    agent = PlaywrightGUIAgent()

    text = agent._clean_text(" hello   world \n\n\n test ")

    assert text == "hello world\n\n test"


def test_run_dry_without_browser():
    agent = PlaywrightGUIAgent()

    result = asyncio.run(
        agent.run(
            task="测试 dry run",
            start_url="https://example.com",
            take_screenshot=False,
            use_llm_summary=False,
            use_browser=False,
        )
    )

    assert result.observation.title == "DRY RUN PAGE"
    assert result.observation.screenshot_path is None
    assert "dry-run" in " ".join(result.steps)
    assert "页面标题" in result.summary


def test_run_dry_still_validates_url():
    agent = PlaywrightGUIAgent()

    try:
        asyncio.run(
            agent.run(
                task="测试危险 URL",
                start_url="file:///C:/secret.txt",
                use_llm_summary=False,
                use_browser=False,
            )
        )
    except GUIAgentSafetyError:
        pass
    else:
        raise AssertionError("dry-run 模式也必须校验 URL")
