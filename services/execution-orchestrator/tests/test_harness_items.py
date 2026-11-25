"""Unnamed controls (doc 24 section 6.2, W4-P5-12): a control with
no accessible name forms a Board item on structural identity —
counted in the denominator, accounted could_not_check with the
reason ``unnamed_control``, never silently skipped and never
executed (every frozen locator strategy targets by accessible
name, and there is no ordinal channel in the frozen schemas).
"""

from markettwin_execution_orchestrator.workflow.harness_items import (
    NOT_CHECKED_UNNAMED_CONTROL,
    case_for_item,
    ingest_page_index,
    structural_reason,
)
from markettwin_execution_orchestrator.workflow.harness_state import (
    HarnessState,
)

_URL = "https://app.example.test/form"
_START = "https://app.example.test/"


def _entry(role: str, name: str, ordinal: int) -> dict[str, object]:
    return {
        "role": role, "name": name, "ordinal": ordinal,
        "name_source": "playwright",
    }


def test_unnamed_control_forms_a_structural_item() -> None:
    """T-P5-H3: the unnamed control forms an item keyed by structural
    identity; its case builds (inert — the gate closes it before
    execution); the named control beside it is untouched."""
    state = HarnessState()
    items = ingest_page_index(
        state, url=_URL,
        entries=[
            _entry("button", "", 0),
            _entry("button", "Save", 1),
        ],
    )
    assert len(items) == 2
    assert len(state.items) == 2  # both are in the denominator

    unnamed = next(item for item in items if not item.name)
    named = next(item for item in items if item.name)
    assert unnamed.locator["structural_identity"] is True
    assert unnamed.locator["ordinal"] == 0
    assert structural_reason(unnamed) == NOT_CHECKED_UNNAMED_CONTROL
    assert structural_reason(unnamed) == "unnamed_control"
    assert "structural_identity" not in named.locator
    assert structural_reason(named) is None

    # The case builds without a name target anywhere: one navigate
    # step, one target-less URL assertion. It is never executed —
    # the harness gate closes the item as could_not_check first.
    case = case_for_item(
        item=unnamed, state_url=_URL, feature_key="form",
        start_url=_START,
    )
    assert [step.action for step in case.steps] == ["navigate"]
    assert all(a.target is None for a in case.expected)

    named_case = case_for_item(
        item=named, state_url=_URL, feature_key="form",
        start_url=_START,
    )
    assert any(
        a.target is not None and a.target.name == "Save"
        for a in named_case.expected
    )


def test_mixed_index_counts_every_control_exactly_once() -> None:
    """T-P5-H4: a mixed fixture — named, unnamed (two of one role,
    told apart by occurrence), and a non-action role that is not a
    control at all — counts every control exactly once, and
    re-ingesting the same index adds nothing."""
    state = HarnessState()
    entries = [
        _entry("link", "Home", 0),
        _entry("button", "", 1),
        _entry("button", "", 2),
        _entry("textbox", "", 3),
        _entry("heading", "Welcome", 4),  # not an actionable role
    ]
    items = ingest_page_index(state, url=_URL, entries=entries)
    assert len(items) == 4
    assert len(state.items) == 4

    structural = [i for i in items if structural_reason(i) is not None]
    assert len(structural) == 3
    keys = {
        (i.role, i.occurrence_index) for i in structural
    }
    assert keys == {("button", 0), ("button", 1), ("textbox", 0)}

    again = ingest_page_index(state, url=_URL, entries=entries)
    assert again == []
    assert len(state.items) == 4
