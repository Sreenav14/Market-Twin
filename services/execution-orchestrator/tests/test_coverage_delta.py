"""Phase 1a section 10.6: the pure coverage-delta matcher (T-V1..T-V5)."""

from markettwin_execution_orchestrator.workflow.coverage_delta import (
    build_coverage_delta,
)

BASE = "https://app.test"


def test_any_recorded_state_on_a_page_matches_the_snapshot():
    url = f"{BASE}/states"
    block = _map([_page(url, states=[_state("closed"), _state("open")])])
    for state_id in ("closed", "open"):
        delta = build_coverage_delta(map_block=block, absorbed={url: state_id},
                                     attempted_failed=[], frontier_remaining=[])
        assert delta["present"] == [url]
        assert delta["changed"] == []


def _page(url, *, status="fetch_ok", states=()):
    return {"url": url, "effective_url": url, "pattern": "/x",
            "status": status, "requires_auth": False, "states": list(states)}


def _state(state_id=None):
    return {"state_key": "default", "state_id": state_id,
            "element_signature": None, "form_signature": None}


def _map(pages, *, total=None, truncated=False):
    return {"map_id": "map-1", "version_number": 2,
            "release_state": "partial", "release_scope": "inventory",
            "built_at": "2026-11-13T00:00:00+00:00", "base_url": BASE + "/",
            "routes": [page["url"] for page in pages],
            "routes_truncated": truncated, "pages": pages,
            "counts": {"expected": total if total is not None else len(pages),
                       "reachable": len(pages), "blocked_auth": 0,
                       "blocked_wall": 0, "gone": 0}}


def test_delta_partitions_the_expected_set_exactly():
    """T-V1: 6 expected pages — absorbed (one via a matching seeded
    state), attempted-failed, frontier, never queued — plus one
    absorbed URL the map never carried. The categories partition the
    expected set exactly."""
    urls = [f"{BASE}/p{i}" for i in range(1, 7)]
    pages = [_page(url) for url in urls]
    pages[5] = _page(urls[5], states=[_state("seed-6")])
    delta = build_coverage_delta(
        map_block=_map(pages),
        absorbed={urls[0]: "live-1", urls[1]: "live-2", urls[5]: "seed-6",
                  f"{BASE}/extra": "live-x"},
        attempted_failed=[urls[2]],
        frontier_remaining=[urls[3]],
    )
    assert delta["map_id"] == "map-1"
    assert delta["map_version"] == 2
    assert delta["expected_in_snapshot"] == 6
    assert delta["map_expected_total"] == 6
    assert delta["delta_scope"] == "full"
    assert delta["present"] == [urls[0], urls[1], urls[5]]
    assert delta["present_count"] == 3
    assert delta["unreachable"] == [urls[2]]
    assert delta["missing"] == [{"url": urls[3], "status": "fetch_ok"},
                                {"url": urls[4], "status": "fetch_ok"}]
    assert delta["changed"] == []
    assert delta["new"] == [f"{BASE}/extra"]
    assert delta["counts"] == {"present": 3, "missing": 2, "unreachable": 1,
                               "changed": 0, "new": 1}
    partitioned = (
        set(delta["present"])
        | {entry["url"] for entry in delta["missing"]}
        | set(delta["unreachable"])
        | {entry["url"] for entry in delta["changed"]}
    )
    assert partitioned == set(urls)


def test_attempted_failed_is_never_reported_missing():
    """T-V2: a URL that was attempted and failed is unreachable even
    when it also still sits in the remaining frontier."""
    urls = [f"{BASE}/p{i}" for i in range(1, 4)]
    delta = build_coverage_delta(
        map_block=_map([_page(url) for url in urls]),
        absorbed={urls[0]: "live-1"},
        attempted_failed=[urls[1]],
        frontier_remaining=[urls[1], urls[2]],
    )
    assert delta["unreachable"] == [urls[1]]
    assert [entry["url"] for entry in delta["missing"]] == [urls[2]]


def test_seeded_state_change_is_detected_by_state_id():
    """T-V3: an absorbed page whose live state_id differs from the
    seeded one is changed, with both ids carried; a matching live id
    is present, not changed."""
    urls = [f"{BASE}/p1", f"{BASE}/p2"]
    pages = [_page(urls[0], states=[_state("seed-1")]),
             _page(urls[1], states=[_state("seed-2")])]
    delta = build_coverage_delta(
        map_block=_map(pages),
        absorbed={urls[0]: "live-9", urls[1]: "seed-2"},
        attempted_failed=[], frontier_remaining=[],
    )
    assert delta["changed"] == [{"url": urls[0], "seeded_state_id": "seed-1",
                                  "live_state_id": "live-9"}]
    assert delta["present"] == [urls[1]]
    assert delta["counts"]["changed"] == 1


def test_no_seeded_signatures_means_changed_is_always_empty():
    """T-V4: a pure census map carries only NULL state ids, so no
    absorbed page can ever be reported changed in Phase 1a."""
    urls = [f"{BASE}/p1", f"{BASE}/p2"]
    pages = [_page(url, states=[_state(None)]) for url in urls]
    delta = build_coverage_delta(
        map_block=_map(pages),
        absorbed={urls[0]: "live-1", urls[1]: "live-2"},
        attempted_failed=[], frontier_remaining=[],
    )
    assert delta["changed"] == []
    assert delta["present"] == urls


def test_truncated_snapshot_reports_its_scope_and_the_full_total():
    """T-V5 (decision D9): the delta reconciles against the snapshot's
    set, says so via delta_scope, and still reports the map's full
    expected total."""
    urls = [f"{BASE}/p1", f"{BASE}/p2"]
    delta = build_coverage_delta(
        map_block=_map([_page(url) for url in urls], total=5000, truncated=True),
        absorbed={urls[0]: "live-1"},
        attempted_failed=[], frontier_remaining=[urls[1]],
    )
    assert delta["delta_scope"] == "snapshot_truncated"
    assert delta["map_expected_total"] == 5000
    assert delta["expected_in_snapshot"] == 2


# --- Phase 4: the preflight producer (doc 23 sections 4.2, 6.5; T-PD1 to T-PD4) ---

from markettwin_execution_orchestrator.workflow.coverage_delta import (
    build_preflight_delta,
)


def _pd_map_block() -> dict:
    return {
        "map_id": "map-4",
        "version_number": 4,
        "routes_truncated": False,
        "counts": {"expected": 5},
        "pages": [
            {"url": "https://app.example.com/a", "status": "fetch_ok",
             "states": [{"state_id": "state-a"}]},
            {"url": "https://app.example.com/b", "status": "fetch_ok",
             "states": [{"state_id": "state-b"}]},
            {"url": "https://app.example.com/c", "status": "fetch_ok",
             "states": [{"state_id": "state-c"}]},
            {"url": "https://app.example.com/d", "status": "fetch_ok",
             "states": [{"state_id": "state-d"}]},
            {"url": "https://app.example.com/e", "status": "fetch_ok",
             "states": [{"state_id": "state-e"}]},
        ],
    }


def test_pd1_run_delta_output_is_byte_identical_after_the_refactor():
    # The 1a producer's full payload, pinned literally: the section 6.5
    # refactor must not move a single key or value.
    map_block = {
        "map_id": "map-1",
        "version_number": 2,
        "routes_truncated": False,
        "counts": {"expected": 3},
        "pages": [
            {"url": "https://app.example.com/a", "status": "fetch_ok",
             "states": [{"state_id": "s1"}]},
            {"url": "https://app.example.com/b", "status": "fetch_ok",
             "states": [{"state_id": "s2"}]},
            {"url": "https://app.example.com/c", "status": "blocked_wall",
             "states": []},
        ],
    }
    delta = build_coverage_delta(
        map_block=map_block,
        absorbed={
            "https://app.example.com/a": "s1",
            "https://app.example.com/b": "sX",
            "https://app.example.com/z": "s9",
        },
        attempted_failed=["https://app.example.com/c"],
        frontier_remaining=[],
    )
    assert delta == {
        "map_id": "map-1",
        "map_version": 2,
        "expected_in_snapshot": 3,
        "map_expected_total": 3,
        "delta_scope": "full",
        "present": ["https://app.example.com/a"],
        "present_count": 1,
        "missing": [],
        "unreachable": ["https://app.example.com/c"],
        "changed": [
            {"url": "https://app.example.com/b", "seeded_state_id": "s2",
             "live_state_id": "sX"}
        ],
        "new": ["https://app.example.com/z"],
        "counts": {"present": 1, "missing": 0, "unreachable": 1,
                   "changed": 1, "new": 1},
    }


def test_pd2_preflight_delta_evaluation_order_and_dual_confirmation():
    a, b, c, d, e = (
        f"https://app.example.com/{letter}" for letter in "abcde"
    )
    tier1 = {
        a: {"http_status": 200, "fetch_error": False, "differs": True},
        b: {"http_status": 404, "fetch_error": False, "differs": False},
        c: {"http_status": 404, "fetch_error": False, "differs": False},
        d: {"http_status": None, "fetch_error": True, "differs": False},
        e: {"http_status": 200, "fetch_error": False, "differs": False},
    }
    tier2 = {
        # a is ALSO absent from the recollection with a differing fetch:
        # changed is evaluated first and wins.
        a: {"outcome": "changed", "recorded_state_id": "state-a",
            "live_state_id": "state-a2", "basis": "state"},
    }
    recollected = {a: ("link_graph",), c: ("sitemap",), d: ("sitemap",),
                   e: ("sitemap",), "https://app.example.com/new-page": ("sitemap",)}
    delta = build_preflight_delta(
        map_block=_pd_map_block(), tier1=tier1, tier2=tier2,
        recollected=recollected,
    )
    assert delta["changed"] == [
        {"url": a, "recorded_state_id": "state-a",
         "live_state_id": "state-a2", "basis": "state"}
    ]
    # b: absent from recollection AND 404 -> dual-confirmed missing.
    assert delta["missing"] == [{"url": b, "http_status": 404}]
    # c: 404 but still claimed by the site's sources -> unreachable.
    assert delta["unreachable"] == [
        {"url": c, "reason": "fetch_error"},
        {"url": d, "reason": "fetch_error"},
    ]
    assert delta["present"] == [e]
    assert delta["new"] == [
        {"url": "https://app.example.com/new-page", "source_kinds": ["sitemap"]}
    ]
    assert delta["counts"] == {"present": 1, "missing": 1, "unreachable": 2,
                               "changed": 1, "new": 1}
    assert delta["basis_counts"] == {"state": 1, "html": 0}
    assert delta["html_drift_count"] == 0
    assert delta["delta_scope"] == "full"


def test_pd3_unrendered_difference_is_deferred_not_classified():
    a = "https://app.example.com/a"
    block = _pd_map_block()
    block["pages"] = block["pages"][:1]
    block["counts"] = {"expected": 1}
    delta = build_preflight_delta(
        map_block=block,
        tier1={a: {"http_status": 200, "fetch_error": False, "differs": True}},
        tier2={},
        recollected={a: ("sitemap",)},
    )
    assert delta["present"] == []
    assert delta["changed"] == []
    assert delta["counts"] == {"present": 0, "missing": 0, "unreachable": 0,
                               "changed": 0, "new": 0}
    assert delta["delta_scope"] == "partial_sweep"


def test_pd3_html_drift_counts_and_html_basis():
    a, b = "https://app.example.com/a", "https://app.example.com/b"
    block = _pd_map_block()
    block["pages"] = block["pages"][:2]
    block["counts"] = {"expected": 2}
    delta = build_preflight_delta(
        map_block=block,
        tier1={
            a: {"http_status": 200, "fetch_error": False, "differs": True},
            b: {"http_status": 200, "fetch_error": False, "differs": True},
        },
        tier2={
            a: {"outcome": "present", "html_drift": True},
            b: {"outcome": "changed", "recorded_state_id": None,
                "live_state_id": None, "basis": "html"},
        },
        recollected={a: ("sitemap",), b: ("sitemap",)},
    )
    assert delta["present"] == [a]
    assert delta["html_drift_count"] == 1
    assert delta["changed"] == [
        {"url": b, "recorded_state_id": None, "live_state_id": None,
         "basis": "html"}
    ]
    assert delta["basis_counts"] == {"state": 0, "html": 1}


def test_pd4_no_drifted_vocabulary_anywhere_in_the_delta():
    # Doc 23 section 4.2's five outcomes are the only spellings; the
    # near-miss words appear in no payload and nowhere in freshness code.
    import pathlib

    import markettwin_execution_orchestrator.workflow.coverage_delta as delta_module

    delta = build_preflight_delta(
        map_block=_pd_map_block(), tier1={}, tier2={}, recollected={},
    )
    payload_text = repr(delta)
    for banned in ("drifted", "stale_page", "moved"):
        assert banned not in payload_text
    source = pathlib.Path(delta_module.__file__).read_text(encoding="utf-8")
    for banned in ("drifted", "stale_page", "moved"):
        assert banned not in source
    package_root = pathlib.Path(delta_module.__file__).parents[1]
    freshness_dir = package_root / "freshness"
    if freshness_dir.is_dir():
        for path in freshness_dir.rglob("*.py"):
            text = path.read_text(encoding="utf-8")
            for banned in ("drifted", "stale_page", "moved"):
                assert banned not in text, f"{banned} found in {path.name}"
