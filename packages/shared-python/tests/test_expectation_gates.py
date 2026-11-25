"""Phase 2 expectation eligibility + coverage + gate (doc 21 sections
8.2, 10, 15.1; T-GT1..3, T-BO1 shared half).

The eligibility function, the coverage computation and the gate live
in shared-python so every consumer (Board seeding, snapshot, brief,
panel, audits) shares ONE implementation (spec C3). These tests pin
the section 8.2 rule set exactly and the gate's scope ladder.
"""

from __future__ import annotations

from markettwin_shared.app_map_common import (
    compute_expectation_gate,
    expectation_coverage,
    expectation_verdict_eligible,
)


def _record(**overrides: object) -> dict[str, object]:
    record: dict[str, object] = {
        "oracle_source": "documentation",
        "status": "unverified",
        "assertion": {"kind": "element_state", "subject": {}, "params": {}},
        "assertion_origin": "deterministic",
        "promoted_by": None,
        "superseded_by_id": None,
        "subject_kind": "element",
        "subject_id": "00000000-0000-0000-0000-000000000001",
    }
    record.update(overrides)
    return record


def _coverage(**overrides: object) -> dict[str, object]:
    coverage: dict[str, object] = {
        "journeys_total": 2,
        "journeys_with_expectations": 1,
        "doc_sourced_share": 0.5,
    }
    coverage.update(overrides)
    return coverage


def _counts(**overrides: object) -> dict[str, object]:
    counts: dict[str, object] = {
        "eligible_with_assertion": 1,
        "conflicts_open": 0,
        "taxonomy_violations_open": 0,
        "sweep_violations": 0,
        "grounding_completed": True,
        "accounting_complete": True,
    }
    counts.update(overrides)
    return counts


def test_t_bo1_eligibility_five_rules() -> None:
    """Section 8.2: each rule falsified in turn; all satisfied -> eligible."""
    # A documentation record is verdict grade at birth (Decision 4).
    assert expectation_verdict_eligible(_record()) is True
    assert expectation_verdict_eligible(_record(status="replay-verified")) is True
    assert (
        expectation_verdict_eligible(
            _record(oracle_source="owner-rule", status="owner-confirmed")
        )
        is True
    )
    # Rule 1: source must be documentation/owner-rule, or promoted.
    assert expectation_verdict_eligible(_record(oracle_source="observation")) is False
    assert expectation_verdict_eligible(_record(oracle_source="model-draft")) is False
    assert (
        expectation_verdict_eligible(
            _record(
                oracle_source="observation",
                status="owner-confirmed",
                promoted_by="owner-1",
            )
        )
        is True
    )
    # Rule 2: a conflicted record is evidence of disagreement, not an oracle.
    assert expectation_verdict_eligible(_record(status="conflicted")) is False
    # Rule 3: superseded records are never eligible.
    assert (
        expectation_verdict_eligible(
            _record(superseded_by_id="00000000-0000-0000-0000-000000000009")
        )
        is False
    )
    # Rule 4: an assertion is required; a model-drafted assertion needs
    # its own owner review (promotion) even on a doc-sourced statement.
    assert expectation_verdict_eligible(_record(assertion=None)) is False
    assert (
        expectation_verdict_eligible(_record(assertion_origin="model-drafted"))
        is False
    )
    assert (
        expectation_verdict_eligible(
            _record(
                assertion_origin="model-drafted",
                status="owner-confirmed",
                promoted_by="owner-1",
            )
        )
        is True
    )
    # Rule 5: a future status defaults to ineligible.
    assert expectation_verdict_eligible(_record(status="some-future-status")) is False


def test_t_gt1_gate_scope_ladder() -> None:
    # Grounding never ran / failed -> none.
    assert (
        compute_expectation_gate(_coverage(), _counts(grounding_completed=False))
        .release_scope
        == "none"
    )
    # Full conditions -> expectations.
    result = compute_expectation_gate(_coverage(), _counts())
    assert result.release_scope == "expectations"
    assert result.journeys_total == 2
    assert result.journeys_with_expectations == 1
    assert result.doc_sourced_share == 0.5
    assert result.eligible_with_assertion == 1
    # No journeys judged -> partial.
    assert (
        compute_expectation_gate(
            _coverage(journeys_with_expectations=0), _counts()
        ).release_scope
        == "partial"
    )
    # No eligible assertion -> partial.
    assert (
        compute_expectation_gate(
            _coverage(), _counts(eligible_with_assertion=0)
        ).release_scope
        == "partial"
    )
    # Unreconciled accounting -> partial.
    assert (
        compute_expectation_gate(
            _coverage(), _counts(accounting_complete=False)
        ).release_scope
        == "partial"
    )
    # Open taxonomy violations (audit) -> partial; pre-audit, the
    # grounding sweep's own count governs and is labelled as such.
    audited = compute_expectation_gate(
        _coverage(), _counts(taxonomy_violations_open=2)
    )
    assert audited.release_scope == "partial"
    assert audited.taxonomy_source == "audit"
    swept = compute_expectation_gate(
        _coverage(),
        _counts(taxonomy_violations_open=None, sweep_violations=1),
    )
    assert swept.release_scope == "partial"
    assert swept.taxonomy_source == "grounding_sweep"
    swept_clean = compute_expectation_gate(
        _coverage(),
        _counts(taxonomy_violations_open=None, sweep_violations=0),
    )
    assert swept_clean.release_scope == "expectations"
    metrics = result.metrics()["expectation_gate"]
    assert metrics["release_scope"] == "expectations"
    assert metrics["rule"] == "expectations-2.1"


def test_t_gt3_gate_never_trusted() -> None:
    """C6: no input yields release_state 'trusted' (exhaustive branches)."""

    cases = [
        (_coverage(), _counts()),
        (_coverage(), _counts(grounding_completed=False)),
        (_coverage(journeys_total=0), _counts()),
        (_coverage(), _counts(taxonomy_violations_open=5)),
        (_coverage(), _counts(eligible_with_assertion=99)),
    ]
    for coverage, counts in cases:
        result = compute_expectation_gate(coverage, counts)
        assert result.release_state == "partial"
        assert result.release_scope in {"expectations", "partial", "none"}


def test_coverage_counts_and_journey_traversal() -> None:
    element_id = "00000000-0000-0000-0000-0000000000aa"
    journey_id = "00000000-0000-0000-0000-0000000000bb"
    records = [
        _record(subject_id=element_id),
        _record(
            oracle_source="observation",
            assertion=None,
            assertion_origin=None,
            subject_kind="page",
            subject_id="00000000-0000-0000-0000-0000000000cc",
        ),
        _record(status="conflicted", subject_id=element_id),
    ]
    journeys = [
        {"id": journey_id, "intent": "Buy a plan", "subject_ids": [element_id]},
        {
            "id": "00000000-0000-0000-0000-0000000000dd",
            "intent": "Read the blog",
            "subject_ids": [],
        },
    ]
    block = expectation_coverage(records, journeys)
    assert block["expectations_total"] == 3
    assert block["expectations_by_source"] == {
        "documentation": 2,
        "owner-rule": 0,
        "observation": 1,
        "model-draft": 0,
    }
    assert block["verdict_eligible"] == 1
    assert block["conflicted_open"] == 1
    assert block["doc_sourced_share"] == 2 / 3
    assert block["journeys_total"] == 2
    assert block["journeys_with_expectations"] == 1
    assert block["journeys_without_expectations"] == [
        {"id": "00000000-0000-0000-0000-0000000000dd", "intent": "Read the blog"}
    ]
