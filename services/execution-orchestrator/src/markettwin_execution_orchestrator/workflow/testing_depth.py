"""Coverage limits for the existing three-persona testing planner."""

from typing import Literal

TestingDepth = Literal["low", "medium", "high"]

MISSION_LIMITS: dict[TestingDepth, int] = {"low": 1, "medium": 2, "high": 4}
FEATURE_CASE_LIMITS: dict[TestingDepth, int] = {"low": 3, "medium": 6, "high": 8}


def mission_limit(depth: TestingDepth) -> int:
    """Bound distinct missions; each mission runs with all three personas."""
    return MISSION_LIMITS[depth]


def feature_case_limit(depth: TestingDepth) -> int:
    """Bound feature cases using the same user-selected coverage depth."""
    return FEATURE_CASE_LIMITS[depth]
