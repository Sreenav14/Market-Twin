import pytest

from markettwin_shared.run_kind import resolve_run_kind, translate_execution_mode


@pytest.mark.parametrize(
    ("mode", "expected"),
    [
        ("explore_test", "explore_test"),
        ("persona", "persona"),
        ("slop", "slop"),
        ("harness_v1", "explore_test"),
        ("discovery_contract_v1", "explore_test"),
        ("deep_feature_v1", "explore_test"),
        ("legacy_persona", "persona"),
        (None, "explore_test"),
        ("", "explore_test"),
        ("some_retired_mode", "explore_test"),
        (42, "explore_test"),
    ],
)
def test_translate_execution_mode(mode: object, expected: str) -> None:
    assert translate_execution_mode(mode) == expected


def test_column_wins_over_snapshot() -> None:
    assert (
        resolve_run_kind(
            run_kind_column="slop",
            configuration_snapshot={"execution_mode": "legacy_persona"},
        )
        == "slop"
    )


def test_snapshot_fallback_when_column_missing() -> None:
    assert (
        resolve_run_kind(
            run_kind_column=None,
            configuration_snapshot={"execution_mode": "legacy_persona"},
        )
        == "persona"
    )
    assert resolve_run_kind(run_kind_column=None, configuration_snapshot={}) == (
        "explore_test"
    )
    assert (
        resolve_run_kind(run_kind_column=None, configuration_snapshot=None)
        == "explore_test"
    )


def test_invalid_column_value_falls_back_to_snapshot() -> None:
    assert (
        resolve_run_kind(
            run_kind_column="bogus",
            configuration_snapshot={"execution_mode": "deep_feature_v1"},
        )
        == "explore_test"
    )
