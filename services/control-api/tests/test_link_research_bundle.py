"""Research bundle assembly records every text cap it applies (SKR step 4)."""

from markettwin_control_api.knowledge.link_research import (
    MAX_BUNDLE_PAGE_CHARS,
    MAX_STATE_CHARS,
    _assemble_bundle,  # pyright: ignore[reportPrivateUsage]
)


def test_bundle_records_page_shortening_and_caps_the_text() -> None:
    long_text = "x" * (MAX_BUNDLE_PAGE_CHARS + 1)
    filename, payload = _assemble_bundle(
        "https://example.com/docs",
        [("https://example.com/a", long_text)],
        [],
        pending_count=0,
        truncated_states=0,
    )
    bundle = payload.decode("utf-8")
    assert filename == "example.com-research.txt"
    assert (
        "Research text limits applied: 1 inspected page(s) were shortened "
        "to 100,000 characters."
    ) in bundle
    assert "x" * MAX_BUNDLE_PAGE_CHARS in bundle
    assert "x" * (MAX_BUNDLE_PAGE_CHARS + 1) not in bundle


def test_bundle_records_state_shortening_and_pending_pages() -> None:
    _filename, payload = _assemble_bundle(
        "https://example.com/docs",
        [("https://example.com/a", "short")],
        [],
        pending_count=3,
        truncated_states=2,
    )
    bundle = payload.decode("utf-8")
    assert "Stopped with 3 discovered pages pending due to research limits." in bundle
    assert f"2 rendered state(s) were shortened to {MAX_STATE_CHARS:,} characters." in bundle
    assert "inspected page(s) were shortened" not in bundle


def test_bundle_without_caps_records_no_text_limits() -> None:
    _filename, payload = _assemble_bundle(
        "https://example.com/docs",
        [("https://example.com/a", "short")],
        [],
        pending_count=0,
        truncated_states=0,
    )
    assert "Research text limits applied" not in payload.decode("utf-8")
