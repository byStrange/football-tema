from __future__ import annotations

from abc import ABC, abstractmethod
from decimal import Decimal

from core.events import (
    GamePaymentOpened,
    PaymentConfirmed,
    PaymentInitiated,
    PaymentRejected,
    PlayerJoined,
    PlayerLeft,
    GameClosed,
)
from db.models import PaymentStatus
from db.unit_of_work import UnitOfWork


class MessageSender(ABC):
    @abstractmethod
    async def send_message(self, chat_id: int, text: str) -> None:
        ...

    @abstractmethod
    async def edit_message(self, chat_id: int, message_id: int, text: str) -> None:
        ...

    @abstractmethod
    async def send_photo(self, chat_id: int, photo: str, caption: str | None = None) -> None:
        ...


class NotificationService:
    def __init__(self, message_sender: MessageSender = None) -> None:
        self._message_sender = message_sender

    # -- Event consumers (wired to EventBus) --

    async def on_player_joined(self, event: PlayerJoined) -> None:
        if not self._message_sender:
            return
        async with UnitOfWork() as uow:
            game = await uow.games.get_by_uuid(event.game_uuid)
            if game is None:
                return
            user = await uow.users.get_by_id(event.user_id)
        first_name = getattr(user, "first_name", None) or ""
        username = getattr(user, "username", None)
        if username:
            display = f"{first_name} (@{username})"
        else:
            display = first_name or f"User {event.user_id}"
        text = f"👤 {display} joined. Total: {event.participant_count} players"
        await self._message_sender.send_message(game.group_chat_id, text)

    async def on_player_left(self, event: PlayerLeft) -> None:
        if not self._message_sender:
            return
        async with UnitOfWork() as uow:
            game = await uow.games.get_by_uuid(event.game_uuid)
            if game is None:
                return
            user = await uow.users.get_by_id(event.user_id)
        first_name = getattr(user, "first_name", None) or ""
        username = getattr(user, "username", None)
        if username:
            display = f"{first_name} (@{username})"
        else:
            display = first_name or f"User {event.user_id}"
        text = f"👤 {display} left. Total: {event.participant_count} players"
        await self._message_sender.send_message(game.group_chat_id, text)

    async def on_payment_initiated(self, event: PaymentInitiated) -> None:
        if not self._message_sender:
            return
        async with UnitOfWork() as uow:
            user = await uow.users.get_by_id(event.user_id)
        if not user:
            return
        text = f"Payment {event.amount} initiated. Please send the screenshot."
        await self._message_sender.send_message(user.chat_id or user.telegram_id, text)

    async def on_payment_confirmed(self, event: PaymentConfirmed) -> None:
        if not self._message_sender:
            return
        async with UnitOfWork() as uow:
            user = await uow.users.get_by_id(event.user_id)
        if not user:
            return
        # Skip placeholder/manual users who have no real chat to DM
        if user.chat_id == 0 or user.telegram_id < 0:
            return
        text = f"Your payment of {event.amount} was confirmed."
        try:
            await self._message_sender.send_message(user.chat_id or user.telegram_id, text)
        except Exception:
            pass

    async def on_payment_rejected(self, event: PaymentRejected) -> None:
        if not self._message_sender:
            return
        async with UnitOfWork() as uow:
            user = await uow.users.get_by_id(event.user_id)
        if not user:
            return
        text = f"Your payment was rejected. Reason: {event.reason or 'None given'}."
        await self._message_sender.send_message(user.chat_id or user.telegram_id, text)

    async def on_game_payment_opened(self, event: GamePaymentOpened) -> None:
        if not self._message_sender:
            return
        async with UnitOfWork() as uow:
            game = await uow.games.get_by_uuid(event.game_uuid)
            if game is None:
                return
        text = (
            f"Payments are now open for game {event.game_uuid}.\n"
            f"Amount per player: {event.amount_per_player}\n"
            f"Card number: {event.card_number}"
        )
        await self._message_sender.send_message(game.group_chat_id, text)

    async def on_game_closed(self, event: GameClosed) -> None:
        if not self._message_sender:
            return
        async with UnitOfWork() as uow:
            game = await uow.games.get_by_uuid(event.game_uuid)
            if game is None:
                return
        text = f"Game {event.game_uuid} is now closed."
        await self._message_sender.send_message(game.group_chat_id, text)

    # -- Direct calls from handlers / scheduler --

    async def send_reminder(self, user_id: int, game_uuid: str, amount: Decimal) -> None:
        if not self._message_sender:
            return
        text = f"Reminder: You owe {amount} for game {game_uuid}."
        await self._message_sender.send_message(user_id, text)

    async def update_group_summary(self, game_uuid: str) -> None:
        if not self._message_sender:
            return
        async with UnitOfWork() as uow:
            game = await uow.games.get_by_uuid(game_uuid)
            if game is None or getattr(game, "announcement_message_id", None) is None:
                return
            participants = await uow.participants.list_for_game(game.id)

            paid = [p for p in participants if p.payment_status == PaymentStatus.paid]
            pending = [p for p in participants if p.payment_status == PaymentStatus.pending_confirmation]
            not_paid = [p for p in participants if p.payment_status == PaymentStatus.not_paid]

            total_due = sum((p.amount_due or Decimal("0")) for p in participants)
            collected = sum((p.amount_due or Decimal("0")) for p in paid)

            summary = (
                f"Game {game_uuid} summary\n"
                f"Paid: {len(paid)} | Pending: {len(pending)} | Not paid: {len(not_paid)}\n"
                f"Total due: {total_due} | Collected: {collected}"
            )

            await self._message_sender.edit_message(
                chat_id=game.group_chat_id,
                message_id=game.announcement_message_id,
                text=summary,
            )
