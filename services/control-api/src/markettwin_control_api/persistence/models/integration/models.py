"""Compatibility exports for shared integration models."""

from markettwin_database.models.integration import (
    OutboxEvent,
    ProcessedMessage,
)

__all__ = [
    "OutboxEvent",
    "ProcessedMessage",
]