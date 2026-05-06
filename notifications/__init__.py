"""Notification layer for scheduled reminders, live messages, and nudges."""

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class MessageSender(Protocol):
    """Minimal adapter used by the notification layer to talk to Telegram."""

    async def send_message(self, chat_id: int, text: str, **kwargs: Any) -> Any:
        ...

    async def edit_message(self, chat_id: int, message_id: int, text: str, **kwargs: Any) -> Any:
        ...

    async def send_mention(self, chat_id: int, text: str, **kwargs: Any) -> Any:
        ...
