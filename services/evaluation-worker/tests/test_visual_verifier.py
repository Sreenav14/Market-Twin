"""Tests for MarketTwin visual evidence verification."""

import asyncio
import json
from pathlib import Path
from types import SimpleNamespace
from typing import cast

import pytest
from litellm.exceptions import RateLimitError
from markettwin_evaluation_worker import visual_verifier


@pytest.mark.asyncio
async def test_visual_verifier_sends_real_image_bytes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Viewport and crop bytes must be sent to the vision model."""

    viewport_path = tmp_path / "viewport.png"
    focused_path = tmp_path / "focused.png"

    viewport_path.write_bytes(
        b"viewport-image-bytes"
    )
    focused_path.write_bytes(
        b"focused-image-bytes"
    )

    captured_request: dict[str, object] = {}

    async def fake_acompletion(
        **kwargs: object,
    ) -> object:
        captured_request.update(kwargs)

        return SimpleNamespace(
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(
                        content=json.dumps(
                            {
                                "status": "satisfied",
                                "rationale": (
                                    "The heading is clearly visible."
                                ),
                                "observed_details": [
                                    "Heading text is readable.",
                                ],
                            }
                        )
                    )
                )
            ]
        )

    monkeypatch.setattr(
        visual_verifier,
        "acompletion",
        fake_acompletion,
    )

    monkeypatch.delenv(
        "MODEL_API_KEY",
        raising=False,
    )
    monkeypatch.delenv(
        "OPENAI_API_KEY",
        raising=False,
    )

    result = await visual_verifier.verify_visual_criterion(
        criterion=(
            "The Software testing heading is visible."
        ),
        viewport_path=viewport_path,
        focused_path=focused_path,
    )

    assert result.status == "satisfied"
    assert (
        result.rationale
        == "The heading is clearly visible."
    )

    messages_value = captured_request["messages"]
    assert isinstance(messages_value, list)
    messages = cast(list[object], messages_value)
    assert messages

    user_message_value = messages[0]
    assert isinstance(user_message_value, dict)
    user_message = cast(dict[str, object], user_message_value)

    content_value = user_message["content"]
    assert isinstance(content_value, list)
    content = cast(list[object], content_value)

    image_parts: list[dict[str, object]] = []
    for part in content:
        if not isinstance(part, dict):
            continue
        typed_part = cast(dict[str, object], part)
        if typed_part.get("type") == "image_url":
            image_parts.append(typed_part)

    assert len(image_parts) == 2

    for part in image_parts:
        image_url = cast(
            dict[str, object],
            part["image_url"],
        )

        assert isinstance(
            image_url,
            dict,
        )

        url = image_url["url"]

        assert isinstance(url, str)
        assert url.startswith(
            "data:image/png;base64,"
        )

    assert str(viewport_path) not in str(
        captured_request
    )
    assert str(focused_path) not in str(
        captured_request
    )


@pytest.mark.asyncio
async def test_visual_verifier_retries_rate_limits(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A transient provider rate limit must not abort the evaluation."""

    viewport_path = tmp_path / "viewport.png"
    viewport_path.write_bytes(b"viewport-image-bytes")
    attempts = 0
    delays: list[float] = []

    async def fake_acompletion(**_kwargs: object) -> object:
        nonlocal attempts
        attempts += 1

        if attempts == 1:
            raise RateLimitError(
                message="Rate limited",
                llm_provider="openai",
                model="gpt-4o-mini",
            )

        return SimpleNamespace(
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(
                        content=json.dumps(
                            {
                                "status": "satisfied",
                                "rationale": "The heading is visible.",
                                "observed_details": [],
                            }
                        )
                    )
                )
            ]
        )

    async def fake_sleep(delay: float) -> None:
        delays.append(delay)

    monkeypatch.setattr(
        visual_verifier,
        "acompletion",
        fake_acompletion,
    )
    monkeypatch.setattr(
        asyncio,
        "sleep",
        fake_sleep,
    )

    result = await visual_verifier.verify_visual_criterion(
        criterion="The heading is visible.",
        viewport_path=viewport_path,
    )

    assert result.status == "satisfied"
    assert attempts == 2
    assert delays == [1.0]


@pytest.mark.asyncio
async def test_visual_verifier_marks_exhausted_rate_limit_unverified(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Persistent rate limits must not roll back the entire report."""

    viewport_path = tmp_path / "viewport.png"
    viewport_path.write_bytes(b"viewport-image-bytes")
    attempts = 0
    delays: list[float] = []

    async def always_rate_limited(**_kwargs: object) -> object:
        nonlocal attempts
        attempts += 1
        raise RateLimitError(
            message="Rate limited",
            llm_provider="openai",
            model="gpt-4o-mini",
        )

    async def fake_sleep(delay: float) -> None:
        delays.append(delay)

    monkeypatch.setattr(
        visual_verifier,
        "acompletion",
        always_rate_limited,
    )
    monkeypatch.setattr(
        asyncio,
        "sleep",
        fake_sleep,
    )

    result = await visual_verifier.verify_visual_criterion(
        criterion="The heading is visible.",
        viewport_path=viewport_path,
    )

    assert result.status == "unverified"
    assert "rate-limited" in result.rationale
    assert attempts == visual_verifier.VISUAL_RATE_LIMIT_MAX_ATTEMPTS
    assert delays == [1.0, 2.0, 4.0]
