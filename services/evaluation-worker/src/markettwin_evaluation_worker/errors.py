"""Stable failure codes for invalid persisted evaluation input."""


class InvalidEvaluationInput(ValueError):
    """The same execution data cannot be repaired by retrying evaluation."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
