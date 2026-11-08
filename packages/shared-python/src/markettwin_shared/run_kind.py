"""Unified run kinds and legacy execution-mode translation (U-P0-04).

One resolver shared by every reader of a test run's type (orchestrator
run_request, evaluation workflow, control-api responses). The unified
engine knows exactly three kinds; rows created before it carry a legacy
``execution_mode`` string in their configuration snapshot (or no key at
all) and are translated at read time — stored history is never rewritten.
"""

from __future__ import annotations

from typing import Literal

RunKind = Literal["explore_test", "persona", "slop"]

RUN_KINDS: tuple[str, ...] = ("explore_test", "persona", "slop")

_LEGACY_MODE_TO_KIND: dict[str, RunKind] = {
    "harness_v1": "explore_test",
    "discovery_contract_v1": "explore_test",
    "deep_feature_v1": "explore_test",
    "legacy_persona": "persona",
}


def translate_execution_mode(mode: object) -> RunKind:
    """Map any stored execution_mode value (or its absence) to a kind.

    A value that is already a kind passes through. Unknown strings fall
    back to explore_test: the legacy readers disagreed on defaults
    (legacy_persona vs discovery_contract_v1); the unified default is
    the core testing kind, and an unknown value can only come from a
    retired or corrupt snapshot, never from a unified writer.
    """

    if isinstance(mode, str):
        if mode in RUN_KINDS:
            return mode  # type: ignore[return-value]
        translated = _LEGACY_MODE_TO_KIND.get(mode)
        if translated is not None:
            return translated
    return "explore_test"


def resolve_run_kind(
    *,
    run_kind_column: object,
    configuration_snapshot: object,
) -> RunKind:
    """Resolve a run's kind: the column wins; the snapshot is the fallback."""

    if isinstance(run_kind_column, str) and run_kind_column in RUN_KINDS:
        return run_kind_column  # type: ignore[return-value]
    mode: object = None
    if isinstance(configuration_snapshot, dict):
        mode = configuration_snapshot.get("execution_mode")
    return translate_execution_mode(mode)
