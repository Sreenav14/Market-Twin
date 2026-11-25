"""Changes to execution behavior must change a task contract's identity."""

from copy import deepcopy

import pytest
from markettwin_shared.task_skill import task_contract_digest, validate_task_skill


@pytest.mark.parametrize("field,value", [
    ("success_assertion", {"url": "https://example.com/different"}),
    ("locator_bindings", [{"order": 1, "locators": [{"kind": "label", "value": "Other"}]}]),
    ("safety", "changed"),
])
def test_execution_fields_change_digest(field, value):
    original = {"feature_key": "agents", "task": {}, "steps": [], "expected": []}
    changed = deepcopy(original)
    changed[field] = value
    assert task_contract_digest(original) != task_contract_digest(changed)


@pytest.mark.parametrize("field,value", [
    ("kind", "secret_ref"), ("required", False), ("disposable", True),
    ("generator", "unique_email"),
])
def test_input_contract_changes_digest(field, value):
    original = {"feature_key": "agents", "task": {"inputs": [{"key": "name", "kind": "text"}]}}
    changed = deepcopy(original)
    changed["task"]["inputs"][0][field] = value
    assert task_contract_digest(original) != task_contract_digest(changed)


def test_cleanup_and_wait_changes_digest():
    original = {"task": {}, "steps": [{"action": "wait", "milliseconds": 100}]}
    changed = deepcopy(original)
    changed["steps"][0]["milliseconds"] = 2000
    assert task_contract_digest(original) != task_contract_digest(changed)
    changed = deepcopy(original)
    changed["task"]["cleanup"] = {"steps": [{"action": "click"}]}
    assert task_contract_digest(original) != task_contract_digest(changed)


def test_task_without_outcomes_cannot_validate():
    assert "uncheckable_outcome" in validate_task_skill({
        "task": {"source": {"kind": "run_execution"}}, "steps": [], "expected": [],
    })
