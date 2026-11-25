"""Expectation authoring (doc 21 sections 5.2, 5.3, 5.5, 9.1 point 1).

The single write path for grounded expectations. Enforces the
invariants the whole phase hangs on:

- oracle_source, statement and source_ref are write-once (C2) -- this
  module only ever INSERTs new rows; there is no update path.
- Authoring is idempotent per (app_map, subject, assertion signature,
  oracle_source) (section 6.2 stage 4).
- A rejected (subject, assertion signature) is never resurrected
  (section 5.5).
- Grounding never promotes: born statuses come from section 5.1 only
  (documentation/observation/model-draft -> 'unverified'; owner rules
  are born 'owner-confirmed' but those are authored by the owner API,
  not by grounding).
"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from markettwin_database.models.knowledge import AppMap

from .expectations_repository import GroundingRepository, assertion_signature
from .grounding import verify_assertion_against_graph

BORN_STATUS = {
    "documentation": "unverified",
    "owner-rule": "owner-confirmed",
    "observation": "unverified",
    "model-draft": "unverified",
}


@dataclass(frozen=True)
class AuthorOutcome:
    expectation_id: UUID | None
    created: bool
    skipped_reason: str | None  # 'duplicate' | 'rejected' | None


async def author_expectation(
    repository: GroundingRepository,
    app_map: AppMap,
    *,
    subject_kind: str,
    subject_id: UUID,
    statement: str,
    oracle_source: str,
    source_ref: str | None,
    confidence: str,
    assertion: dict[str, object] | None,
    assertion_origin: str | None,
    rejected_keys: set[tuple[str, str, str]],
    events: tuple[tuple[str, dict[str, object]], ...] = (("authored", {}),),
    check_contradiction: bool = False,
    index=None,
) -> AuthorOutcome:
    """Insert one expectation (or report why it was skipped).

    With ``check_contradiction`` (documentation candidates, section
    5.2 step 4 / section 9.1 point 1) the compiled assertion is
    verified against the harvested graph in the same step and a
    contradiction opens a conflict immediately.
    """
    signature = assertion_signature(assertion)
    if (subject_kind, str(subject_id), signature) in rejected_keys:
        return AuthorOutcome(None, False, "rejected")
    existing = await repository.find_expectation(
        app_map.id,
        subject_kind=subject_kind,
        subject_id=subject_id,
        signature=signature,
        oracle_source=oracle_source,
    )
    if existing is not None:
        return AuthorOutcome(existing.id, False, "duplicate")
    row = await repository.insert_expectation(
        app_map,
        subject_kind=subject_kind,
        subject_id=subject_id,
        statement=statement,
        oracle_source=oracle_source,
        source_ref=source_ref,
        confidence=confidence,
        assertion=assertion,
        assertion_origin=assertion_origin,
        status=BORN_STATUS.get(oracle_source, "unverified"),
        events=events,
    )
    if check_contradiction and index is not None:
        verdict = verify_assertion_against_graph(row, index)
        if verdict is not None:
            conflict_kind, observed, observed_subject_id = verdict
            already = await repository.find_open_conflict(
                expectation_id=row.id,
                conflict_kind=conflict_kind,
                observed_subject_id=observed_subject_id,
            )
            if already is None:
                await repository.insert_conflict(
                    app_map,
                    row,
                    conflict_kind=conflict_kind,
                    detection_source="grounding",
                    observed_behaviour=observed,
                    observed_subject_id=observed_subject_id,
                )
    return AuthorOutcome(row.id, True, None)
