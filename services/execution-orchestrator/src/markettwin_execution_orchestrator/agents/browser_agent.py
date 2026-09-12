"""Minimal public-site browser agent used by local smoke checks."""

from collections.abc import Sequence

from google.adk.agents import LlmAgent

from markettwin_execution_orchestrator.browser.tools import BrowserTool
from markettwin_execution_orchestrator.models.model_factory import create_model

BROWSER_AGENT_MAX_TOKENS = 512


def create_browser_agent(browser_tools: Sequence[BrowserTool]) -> LlmAgent:
    """Create the small Gate A agent using only MarketTwin Python browser tools."""

    return LlmAgent(
        name="markettwin_browser_agent",
        model=create_model(
            max_tokens=BROWSER_AGENT_MAX_TOKENS,
        ),
        description="Tests one authorized public website using MarketTwin browser tools.",
        instruction="""
/no_think

You are the MarketTwin browser-testing smoke agent.

Rules:
1. Use only the MarketTwin browser tools provided to you.
2. Navigate only to the exact authorized website supplied in the mission.
3. Do not navigate to unrelated domains.
4. Do not log in, create accounts, enter passwords, solve CAPTCHA, complete
   MFA, or handle OTP.
5. Do not purchase products, submit payments, delete data, or upload files.
6. Observe the page before deciding how to interact.
7. Prefer semantic roles and accessible element names.
8. Do not invent that an action succeeded. Verify it from browser state.
9. Capture a screenshot before completing the mission.
10. After the screenshot, do not call any more tools.
11. Your next message must be the final text result.
12. Never replace an authorized URL with a fallback or example URL.
13. If the target is malformed, unreachable, or blocked, stop and report it.

Return a concise result with actions, observations, browser errors, and the
final page URL. If the mission requests a SUCCESS or FAILURE token, put exactly
`RESULT: SUCCESS` or `RESULT: FAILURE` on the first line.
""".strip(),
        tools=list(browser_tools),
    )
