"""Coverage limits for the existing three-persona testing planner."""

from typing import Literal

TestingDepth = Literal["low", "medium", "high"]

MISSION_LIMITS: dict[TestingDepth, int] = {"low": 1, "medium": 2, "high": 4}


def mission_limit(depth: TestingDepth) -> int:
    """Bound distinct missions; each mission runs with all three personas."""
    return MISSION_LIMITS[depth]
