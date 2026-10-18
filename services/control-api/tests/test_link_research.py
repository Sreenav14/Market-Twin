"""Linked research stays public, bounded, attributed and unapproved."""

import socket
import time
from types import SimpleNamespace
from urllib.parse import urlsplit

import pytest
from fastapi import HTTPException
from markettwin_control_api.api import ingestion
from markettwin_control_api.knowledge import link_research as research


@pytest.mark.parametrize(
    "url",
    [
        "file:///etc/passwd",
        "https://user:secret@example.com",
        "http://example.com:9000",
        "javascript:alert(1)",
    ],
)
def test_invalid_link_rejected(url):
    with pytest.raises(ValueError):
        research.public_url(url)


@pytest.mark.parametrize(
    "address", ["127.0.0.1", "10.0.0.1", "169.254.169.254", "::1", "192.168.1.1"]
)
def test_private_dns_never_connects(monkeypatch, address):
    monkeypatch.setattr(
        socket,
        "getaddrinfo",
        lambda *_args, **_kwargs: [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (address, 80))],
    )
    monkeypatch.setattr(
        socket, "create_connection", lambda *_args, **_kwargs: pytest.fail("Must not connect")
    )
    with pytest.raises(ValueError, match="public"):
        research.download_page("http://example.com", time.monotonic() + 5)


def test_research_preserves_sources_and_is_bounded(monkeypatch):
    fetched = []

    def page(url, _deadline, **_kwargs):
        fetched.append(url)
        links = "".join(
            f'<a href="/docs/{i}">Documentation</a>' for i in range(research.MAX_PAGES + 10)
        )
        return (
            url,
            (f"<h1>Product instructions</h1><script>unsafe invisible</script>{links}"
             "<p>Open Settings then choose Profile.</p>").encode(),
            "text/html",
        )

    monkeypatch.setattr(research, "download_page", page)
    filename, content = research.research_link("https://example.com/docs")
    assert filename == "example.com-research.txt"
    assert len(fetched) == research.MAX_PAGES
    assert all(f"SOURCE URL: {url}" in content.decode() for url in fetched)
    assert b"unsafe invisible" not in content
    assert b"not an exhaustive" in content


async def test_link_permission_checked_before_network(monkeypatch):
    async def denied(*_args, **_kwargs):
        raise HTTPException(403, "Denied")

    monkeypatch.setattr(ingestion, "require_ingestion_access", denied)
    monkeypatch.setattr(
        ingestion, "research_link", lambda *_: pytest.fail("No network before authorization")
    )
    with pytest.raises(HTTPException) as error:
        await ingestion.ingest_link(
            SimpleNamespace(),
            ingestion.LinkKnowledgeRequest(
                url="https://example.com", name="Docs", roles=["product_knowledge"]
            ),
            SimpleNamespace(),
        )
    assert error.value.status_code == 403


async def test_link_reuses_draft_ingestion_and_retains_references(monkeypatch):
    async def allowed(*_args, **_kwargs):
        return "user"

    async def store(workspace, request, file, name, roles):
        assert await file.read() == b"SOURCE URL: https://example.com/docs\nObserved instructions"
        assert file.filename == "example.com-research.txt"
        assert roles == ["product_knowledge"]
        return SimpleNamespace(status="draft", processing_status="queued")

    monkeypatch.setattr(ingestion, "require_ingestion_access", allowed)
    monkeypatch.setattr(
        ingestion,
        "research_link",
        lambda *_: (
            "example.com-research.txt",
            b"SOURCE URL: https://example.com/docs\nObserved instructions",
        ),
    )
    monkeypatch.setattr(ingestion, "ingest_source", store)
    result = await ingestion.ingest_link(
        SimpleNamespace(),
        ingestion.LinkKnowledgeRequest(
            url="https://example.com/docs", name="Docs", roles=["product_knowledge"]
        ),
        SimpleNamespace(),
    )
    assert result.status == "draft"


def test_browser_renders_javascript_expands_content_and_discovers_deep_pages(monkeypatch):
    fetched = []
    def page(url, _deadline, **_kwargs):
        fetched.append(url)
        if url.endswith("/deep"):
            html = "<h1>Deep workflow</h1><p>Verify the saved profile after correcting input.</p>"
        elif url.endswith("/guide"):
            html = '<h1>Guide</h1><a href="/deep">Full workflow</a>'
        else:
            html = '''<div id="app"></div><script>
              document.querySelector('#app').innerHTML = '<h1>Rendered product</h1>' +
                '<details><summary>Instructions</summary><p>Choose Settings then Profile.</p>' +
                '<a href="/guide">Guide</a></details>';
              fetch('/unsafe', {method:'POST'});
            </script>'''
        assert not url.endswith("/unsafe")
        return url, html.encode(), "text/html"
    monkeypatch.setattr(research, "download_page", page)
    _, content = research.research_link("https://example.com/")
    assert b"Rendered product" in content
    assert b"Choose Settings then Profile" in content
    assert b"Opened read-only navigation/disclosure: Instructions" in content
    assert b"SOURCE URL: https://example.com/deep" in content
    assert len(fetched) == 3


def test_connected_link_scope_and_spa_routes():
    origin = "https://example.com/"
    assert research.same_site_link(origin, "/guide#heading", origin) == "https://example.com/guide"
    assert research.same_site_link(origin, "#/guide", origin) == "https://example.com/#/guide"
    assert research.same_site_link(origin, "https://other.example/", origin) is None
    assert research.same_site_link(origin, "/logout", origin) is None


def test_asset_budget_never_blocks_later_page_navigation(monkeypatch):
    # Real pages load many subresources; those must not starve page navigation.
    scripts = "".join(f'<script src="/asset-{i}.js"></script>' for i in range(100))

    def page(url, _deadline, **_kwargs):
        if url.endswith(".js"):
            return url, b"window.loaded = true;", "application/javascript"
        if url.endswith("/p1") or url.endswith("/p2") or url.endswith("/p3"):
            return url, f"<h1>Section {url[-2:]}</h1>{scripts}".encode(), "text/html"
        links = "".join(f'<a href="/p{i}">Section {i}</a>' for i in (1, 2, 3))
        return url, f"<h1>Home</h1>{links}".encode(), "text/html"

    monkeypatch.setattr(research, "download_page", page)
    _, content = research.research_link("https://example.com/")
    assert b"Could not inspect" not in content
    assert b"SOURCE URL: https://example.com/p3" in content


def test_off_origin_assets_do_not_block_page_text(monkeypatch):
    def page(url, _deadline, **_kwargs):
        if urlsplit(url).netloc != "example.com":
            time.sleep(5)
            return url, b"third-party", "application/javascript"
        scripts = "".join(f'<script src="https://cdn.example/a{i}.js"></script>' for i in range(20))
        html = f"<h1>Visible product</h1><p>Open Settings then choose Profile.</p>{scripts}"
        return url, html.encode(), "text/html"

    monkeypatch.setattr(research, "download_page", page)
    started = time.monotonic()
    _, content = research.research_link("https://example.com/")
    assert time.monotonic() - started < 12
    assert b"Visible product" in content
    assert b"Browser rendering did not finish" not in content
