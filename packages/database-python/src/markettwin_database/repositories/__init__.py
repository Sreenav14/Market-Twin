"""Shared persistence repositories."""

from .outbox_repository import OutboxRepository

__all__ = [
    "OutboxRepository",
]