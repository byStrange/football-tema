from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel


class CreateGameCmd(BaseModel):
    admin_id: int
    location: str
    scheduled_at: datetime
    total_cost: Decimal | None = None
    cost_per_player: Decimal | None = None
    max_players: int | None = None
    group_chat_id: int


class JoinGameCmd(BaseModel):
    game_uuid: str
    user_id: int
    chat_id: int


class LeaveGameCmd(BaseModel):
    game_uuid: str
    user_id: int


class AddPlayerCmd(BaseModel):
    game_uuid: str
    admin_id: int
    target_telegram_id: int


class RemovePlayerCmd(BaseModel):
    game_uuid: str
    admin_id: int
    target_user_id: int


class TriggerPaymentCmd(BaseModel):
    game_uuid: str
    admin_id: int
    card_number: str


class PlayerPaidCmd(BaseModel):
    participant_id: int
    user_id: int


class ConfirmPaymentCmd(BaseModel):
    participant_id: int
    admin_id: int
    approved: bool
    reason: str | None = None


class UploadScreenshotCmd(BaseModel):
    participant_id: int
    user_id: int
    file_id: str
