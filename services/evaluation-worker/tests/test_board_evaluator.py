from markettwin_evaluation_worker.board_evaluator import compute_board_verdict


def _board(statuses: list[str]) -> dict[str, object]:
    return {
        "items": {
            f"item_{n}": {
                "item_id": f"item_{n}",
                "case_id": f"case_{n}",
                "role": "button",
                "name": f"B{n}",
                "status": status,
                "blocker": None,
            }
            for n, status in enumerate(statuses)
        }
    }


def _events(statuses: list[str]) -> dict[str, dict[str, object]]:
    return {
        f"item_{n}": {
            "board_item_id": f"item_{n}",
            "board_status": status,
            "assertions": [],
            "evidence_refs": [],
        }
        for n, status in enumerate(statuses)
    }


def test_ready_when_all_checked_and_none_broken() -> None:
    board = _board(["worked", "worked", "not_checked"])
    result = compute_board_verdict(board_document=board, board_results=_events(
        ["worked", "worked", "not_checked"]))
    assert result["verdict"] == "Ready"
    coverage = result["coverage"]
    assert coverage["checked"] == 2
    assert coverage["denominator"] == 3


def test_not_ready_when_any_item_broken() -> None:
    board = _board(["worked", "broken"])
    result = compute_board_verdict(board_document=board, board_results=_events(
        ["worked", "broken"]))
    assert result["verdict"] == "Not ready yet"


def test_cant_tell_below_half_coverage() -> None:
    board = _board(["worked", "could_not_check", "could_not_check"])
    result = compute_board_verdict(board_document=board, board_results=_events(
        ["worked", "could_not_check", "could_not_check"]))
    assert result["verdict"] == "Can't tell yet"


def test_owner_disabled_leaves_the_denominator() -> None:
    board = _board(["worked", "owner_disabled"])
    result = compute_board_verdict(board_document=board, board_results=_events(
        ["worked", "owner_disabled"]))
    assert result["coverage"]["denominator"] == 1
    assert result["verdict"] == "Ready"


def test_owner_disabled_without_event_still_leaves_the_denominator() -> None:
    # Audit fix (F4): a disabled item whose result event is missing
    # must not be reclassified could_not_check — that kept it in the
    # denominator and understated coverage.
    board = _board(["worked", "owner_disabled"])
    events = _events(["worked", "owner_disabled"])
    del events["item_1"]
    result = compute_board_verdict(board_document=board, board_results=events)
    assert result["coverage"]["denominator"] == 1
    assert result["coverage"]["missing_result_events"] == 0
    assert result["verdict"] == "Ready"
    rows = {row["board_item_id"]: row for row in result["items"]}
    assert rows["item_1"]["effective_status"] == "owner_disabled"
    assert rows["item_1"]["missing_result_event"] is False


def test_missing_event_for_terminal_item_is_a_per_item_gap() -> None:
    board = _board(["worked", "broken"])
    events = _events(["worked", "broken"])
    del events["item_1"]
    result = compute_board_verdict(board_document=board, board_results=events)
    rows = {row["board_item_id"]: row for row in result["items"]}
    assert rows["item_1"]["missing_result_event"] is True
    assert rows["item_1"]["effective_status"] == "could_not_check"
    assert result["coverage"]["missing_result_events"] == 1
    # The gap lowers coverage; it never fails the whole evaluation.
    assert result["verdict"] in {"Ready", "Not ready yet", "Can't tell yet"}


def test_empty_board_cant_tell() -> None:
    result = compute_board_verdict(board_document={"items": {}}, board_results={})
    assert result["verdict"] == "Can't tell yet"
