"""Local capability probes: no external sites, credentials, or payment requests."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from types import SimpleNamespace

from markettwin_execution_orchestrator.browser.action_policy import (
    ensure_low_risk_click_target,
    ensure_non_sensitive_fill,
)
from markettwin_execution_orchestrator.browser.contracts import AllowedOrigin, BrowserEventBuffer
from markettwin_execution_orchestrator.browser.controller import BrowserController
from markettwin_execution_orchestrator.browser.errors import BrowserPolicyError
from markettwin_execution_orchestrator.browser.observations import build_observation
from markettwin_execution_orchestrator.browser.policy import validate_target_url
from playwright.async_api import async_playwright


def outcome(operation) -> str:
    try:
        operation()
    except BrowserPolicyError as exc:
        return f"blocked: {type(exc).__name__}"
    return "allowed_by_this_check"


async def main() -> None:
    origins = (AllowedOrigin("https", "shop.example"),)
    policies = {
        "merchant": outcome(lambda: validate_target_url(
            "https://shop.example/pricing", origins, "public_only",
        )),
        "external_script": outcome(lambda: validate_target_url(
            "https://js.stripe.com/v3/", origins, "public_only",
        )),
        "external_identity_provider": outcome(lambda: validate_target_url(
            "https://login.example/signin", origins, "public_only",
        )),
        "payment_button": outcome(lambda: ensure_low_risk_click_target("Pay now")),
        "generic_button": outcome(lambda: ensure_low_risk_click_target("Continue")),
        "payment_field": outcome(lambda: ensure_non_sensitive_fill(
            label="Card number", input_type="text", autocomplete="cc-number",
        )),
    }
    paused = SimpleNamespace(
        capture_enabled=False, state="human_control", event_buffer=BrowserEventBuffer(),
    )
    BrowserController._on_console(paused, "error", "SYNTHETIC_HUMAN_PHASE_EVENT")
    log_during_pause = bool(paused.event_buffer.all_console_errors)

    samples = {}
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(headless=True)
        try:
            context = await browser.new_context(viewport={"width": 1280, "height": 900})
            await context.route("**/*", lambda route: route.abort())
            page = await context.new_page()

            async def observe():
                session = SimpleNamespace(
                    page=page, context=context, timeout_ms=2000, capture_enabled=False,
                    action_number=1, event_buffer=BrowserEventBuffer(),
                )
                return await build_observation(session)

            await page.set_content("""
                <h1>Merchant checkout</h1>
                <iframe title="Payment widget" srcdoc='
                    <h2>Embedded payment summary</h2><p>Total USD 49.00</p>
                    <button>Review payment</button>'></iframe>
            """)
            framed = page.frame_locator("iframe").get_by_role("button", name="Review payment")
            await framed.wait_for(state="visible")
            observation = await observe()
            samples["iframe"] = {
                "frame_locator_finds_button": await framed.count() == 1,
                "top_level_role_locator_finds_button": (
                    await page.get_by_role("button", name="Review payment").count() == 1
                ),
                "collector_lists_button": any(
                    element.name == "Review payment" for element in observation.visible_elements
                ),
                "model_aria_contains_total": "49.00" in observation.to_dict()["aria_snapshot"],
            }

            await page.set_content('<h1>Product</h1><div id="host"></div>')
            await page.evaluate("""() => {
                const root = document.querySelector('#host').attachShadow({mode:'open'});
                root.innerHTML = '<button>Choose yearly billing</button>';
            }""")
            observation = await observe()
            samples["open_shadow_root"] = {
                "role_locator_finds_button": (
                    await page.get_by_role("button", name="Choose yearly billing").count() == 1
                ),
                "collector_lists_button": any(
                    element.name == "Choose yearly billing"
                    for element in observation.visible_elements
                ),
                "model_aria_contains_button": (
                    "Choose yearly billing" in observation.to_dict()["aria_snapshot"]
                ),
            }

            await page.set_content('<h1>Order</h1><canvas width="400" height="100"></canvas>')
            await page.evaluate("""() => {
                const ctx = document.querySelector('canvas').getContext('2d');
                ctx.font = '24px Arial'; ctx.fillText('Total USD 49.00', 10, 40);
            }""")
            observation = await observe()
            samples["canvas_only_total"] = {
                "canvas_has_drawn_pixels": await page.evaluate("""() => {
                    const ctx = document.querySelector('canvas').getContext('2d');
                    return ctx.getImageData(0,0,400,100).data.some(value => value !== 0);
                }"""),
                "model_text_contains_total": "49.00" in json.dumps(observation.to_dict()),
            }
            await context.close()
        finally:
            await browser.close()
    result = {
        "kind": "local_synthetic_capability_probe_not_a_payment_provider_test",
        "policy_checks": policies, "browser_samples": samples,
        "console_error_recorded_while_capture_disabled": log_during_pause,
        "limitations": [
            "No external website reachability was tested.",
            "The iframe is local srcdoc, not a Stripe integration or cross-origin payment test.",
            "A generic allowed label does not prove that an actual transaction would succeed.",
            "The pause probe uses a synthetic event, not a real secret exposure.",
        ],
    }
    Path(__file__).with_name("access-probe-results.json").write_text(
        json.dumps(result, indent=2) + "\n", encoding="utf-8",
    )
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
