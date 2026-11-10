"""State identity must preserve distinct authorized browser destinations."""

import pytest

from markettwin_execution_orchestrator.workflow.harness_state import canonical_url


@pytest.mark.parametrize(("url", "expected"), [
    ("http://example.test:80/path", "http://example.test/path"),
    ("https://example.test:443/path", "https://example.test/path"),
    ("http://example.test:443/path", "http://example.test:443/path"),
    ("https://example.test:80/path", "https://example.test:80/path"),
    ("http://[::1]:8080/path", "http://[::1]:8080/path"),
    ("http://[::1]/path", "http://[::1]/path"),
])
def test_canonical_url_preserves_origin(url: str, expected: str) -> None:
    assert canonical_url(url) == expected
