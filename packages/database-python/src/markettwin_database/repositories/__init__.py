"""Shared persistence repositories."""

from .outbox_repository import OutboxRepository
from .processed_message_repository import ProcessedMessageRepository
__all__ = [
    "OutboxRepository",
    "ProcessedMessageRepository",
]