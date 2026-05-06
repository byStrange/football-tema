from __future__ import annotations

from datetime import datetime
from typing import Awaitable, Callable
from uuid import uuid4

from pydantic import BaseModel, Field
from decimal import Decimal


class DomainEvent(BaseModel):
    event_id: str = Field(default_factory=lambda: str(uuid4()))
    occurred_at: datetime = Field(default_factory=datetime.utcnow)


class PlayerJoined(DomainEvent):
    game_uuid: str
    user_id: int
    participant_count: int


class PlayerLeft(DomainEvent):
    game_uuid: str
    user_id: int
    participant_count: int


class PaymentInitiated(DomainEvent):
    game_uuid: str
    user_id: int
    amount: Decimal


class PaymentConfirmed(DomainEvent):
    game_uuid: str
    user_id: int
    amount: Decimal
    admin_id: int


class PaymentRejected(DomainEvent):
    game_uuid: str
    user_id: int
    reason: str | None


class GameClosed(DomainEvent):
    game_uuid: str


class GamePaymentOpened(DomainEvent):
    game_uuid: str
    card_number: str
    amount_per_player: Decimal


class EventBus:
    def __init__(self) -> None:
        self._handlers: dict[type[DomainEvent], list[Callable[..., Awaitable[None]]]] = {}

    def subscribe(self, event_type: type[DomainEvent], handler: Callable[..., Awaitable[None]]) -> None:
        self._handlers.setdefault(event_type, []).append(handler)

    async def publish(self, event: DomainEvent) -> None:
        handlers = self._handlers.get(type(event), [])
        for handler in handlers:
            await handler(event)
