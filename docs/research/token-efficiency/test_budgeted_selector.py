"""Offline invariant and exact-oracle checks for the research selector."""

import random

import pytest
from budgeted_selector import Atom, InfeasibleContext, Selector


def cost(atoms: tuple[Atom, ...]) -> int:
    return sum(len(atom.text) for atom in atoms)


def test_mandatory_overflow_is_not_silently_trimmed() -> None:
    with pytest.raises(InfeasibleContext):
        Selector([Atom("policy", "12345", mandatory=True)], {}, 4, cost)


def test_forbidden_mandatory_dependency_is_infeasible() -> None:
    with pytest.raises(InfeasibleContext):
        Selector([
            Atom("goal", "x", requires=frozenset({"secret"}), mandatory=True),
            Atom("secret", "x", allowed=False),
        ], {}, 10, cost)


def test_dependency_and_counterevidence_are_preserved() -> None:
    atoms = [
        Atom("alert", "a", mandatory=True),
        Atom("call", "c"),
        Atom("result", "r", frozenset({"evidence"}), frozenset({"call"})),
        Atom("hidden", "h", frozenset({"bonus"}), allowed=False),
        Atom("stale", "s", frozenset({"bonus"}), valid=False),
    ]
    selector = Selector(atoms, {"evidence": 5, "bonus": 100}, 3, cost)
    assert selector.greedy() == frozenset({"alert", "call", "result"})


def test_redundancy_has_no_second_coverage_reward() -> None:
    selector = Selector([
        Atom("one", "x", frozenset({"target"})),
        Atom("duplicate", "xx", frozenset({"target"})),
    ], {"target": 1}, 10, cost)
    assert selector.greedy() == frozenset({"one"})


def test_available_budget_does_not_force_spending() -> None:
    selector = Selector([Atom("noise", "x" * 50)], {}, 100, cost)
    assert selector.greedy() == frozenset()


def test_missing_dependency_and_duplicate_ids_rejected() -> None:
    with pytest.raises(ValueError):
        Selector([Atom("a", "x", requires=frozenset({"b"}))], {}, 10, cost)
    with pytest.raises(ValueError):
        Selector([Atom("a", "x"), Atom("a", "y")], {}, 10, cost)


def test_cyclic_dependency_terminates_and_is_atomic() -> None:
    selector = Selector([
        Atom("a", "x", frozenset({"target"}), frozenset({"b"})),
        Atom("b", "x", requires=frozenset({"a"})),
    ], {"target": 5}, 2, cost)
    assert selector.greedy() == frozenset({"a", "b"})


def test_random_small_instances_against_exhaustive_oracle() -> None:
    rng = random.Random(17)
    for _ in range(60):
        atoms = [Atom("pin", "x", mandatory=True)]
        for i in range(7):
            atoms.append(Atom(
                str(i), "x" * rng.randint(1, 8),
                frozenset(str(rng.randrange(4)) for _ in range(2)),
                frozenset({str(i - 1)}) if i > 0 and rng.random() < 0.2 else frozenset(),
            ))
        selector = Selector(atoms, {str(i): i + 1 for i in range(4)}, 15, cost)
        selected = selector.greedy()
        exact = selector.exact()
        assert selector.tokens(selected) <= 15
        assert selector.pinned <= selected
        assert selector.closure(selected) == selected
        # The heuristic may be worse; never claim the exact solver proves LLM quality.
        assert selector.objective(selected) <= selector.objective(exact) + 1e-9


@pytest.mark.parametrize("invalid", [float("nan"), float("inf"), -1])
def test_invalid_weights_rejected(invalid: float) -> None:
    with pytest.raises(ValueError):
        Selector([], {"target": invalid}, 10, cost)


@pytest.mark.parametrize("invalid", [-1, 0.5, True])
def test_invalid_cost_oracle_rejected(invalid) -> None:
    with pytest.raises(ValueError):
        Selector([], {}, 10, lambda _: invalid)


def test_greedy_is_demonstrably_not_always_optimal() -> None:
    selector = Selector([
        Atom("a", "x" * 6, frozenset({"a"})),
        Atom("b", "x" * 5, frozenset({"b"})),
        Atom("c", "x" * 5, frozenset({"c"})),
    ], {"a": 12, "b": 9, "c": 9}, 10, cost, penalty=0)
    assert selector.greedy() == frozenset({"a"})
    assert selector.exact() == frozenset({"b", "c"})


def test_cost_is_cached_within_one_selector() -> None:
    calls = []

    def counted(atoms):
        calls.append(atoms)
        return cost(atoms)

    selector = Selector([Atom("pin", "x", mandatory=True)], {}, 10, counted)
    selector.tokens(selector.pinned)
    selector.tokens(selector.pinned)
    assert len(calls) == 1
