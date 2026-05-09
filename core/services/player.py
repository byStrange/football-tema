from __future__ import annotations

from core.commands import AddPlayerCmd, JoinGameCmd, LeaveGameCmd, RemovePlayerCmd
from core.events import EventBus, PlayerJoined, PlayerLeft
from core.exceptions import GameFull, GameNotFound, NotAuthorized, PlayerNotFound
from core.results import CommandResult
from db.models import GameStatus, PaymentStatus, User
from db.unit_of_work import UnitOfWork


class PlayerService:
    def __init__(self, event_bus: EventBus) -> None:
        self._event_bus = event_bus

    async def join(self, cmd: JoinGameCmd) -> CommandResult[Participant]:
        async with UnitOfWork() as uow:
            game = await uow.games.get_by_uuid(cmd.game_uuid)
            if game is None:
                return CommandResult.fail("GAME_NOT_FOUND", "Game not found.")
            if game.status in (GameStatus.completed, GameStatus.cancelled):
                return CommandResult.fail("GAME_CLOSED", "This game is already closed.")

            user = await uow.users.get_by_telegram_id(cmd.user_id)
            if user is None:
                user = await uow.users.create(telegram_id=cmd.user_id, chat_id=cmd.chat_id)

            existing = await uow.participants.get(game.id, user.id)
            if existing is not None:
                return CommandResult.ok(existing)

            count = await uow.participants.count_for_game(game.id)
            if game.max_players is not None and count >= game.max_players:
                return CommandResult.fail("GAME_FULL", "Game is full.")

            participant = await uow.participants.create(
                game_id=game.id,
                user_id=user.id,
                payment_status=PaymentStatus.not_paid,
            )

            total_count = await uow.participants.count_for_game(game.id)
            await self._event_bus.publish(
                PlayerJoined(
                    game_uuid=cmd.game_uuid,
                    user_id=cmd.user_id,
                    participant_count=total_count,
                )
            )
            return CommandResult.ok(participant)

    async def leave(self, cmd: LeaveGameCmd) -> CommandResult[None]:
        async with UnitOfWork() as uow:
            game = await uow.games.get_by_uuid(cmd.game_uuid)
            if game is None:
                return CommandResult.fail("GAME_NOT_FOUND", "Game not found.")

            user = await uow.users.get_by_telegram_id(cmd.user_id)
            if user is None:
                return CommandResult.ok(None)

            participant = await uow.participants.get(game.id, user.id)
            if participant is None:
                return CommandResult.ok(None)

            await uow.participants.delete(game.id, user.id)

            total_count = await uow.participants.count_for_game(game.id)
            await self._event_bus.publish(
                PlayerLeft(
                    game_uuid=cmd.game_uuid,
                    user_id=cmd.user_id,
                    participant_count=total_count,
                )
            )
            return CommandResult.ok(None)

    async def add_manually(self, cmd: AddPlayerCmd) -> CommandResult[Participant]:
        async with UnitOfWork() as uow:
            game = await uow.games.get_by_uuid(cmd.game_uuid)
            if game is None:
                return CommandResult.fail("GAME_NOT_FOUND", "Game not found.")
            admin = await uow.users.get_by_telegram_id(cmd.admin_id)
            if admin is None or game.admin_id != admin.id:
                return CommandResult.fail("NOT_AUTHORIZED", "Only admin can add players.")

            if cmd.target_telegram_id:
                user = await uow.users.get_by_telegram_id(cmd.target_telegram_id)
                if user is None:
                    user = await uow.users.create(telegram_id=cmd.target_telegram_id, chat_id=0)
            elif cmd.target_username:
                user = await uow.users.get_by_username(cmd.target_username)
                if user is None:
                    # Generate a unique negative placeholder telegram_id
                    from sqlalchemy import select
                    result = await uow.session.execute(
                        select(User.telegram_id).where(User.telegram_id < 0).order_by(User.telegram_id)
                    )
                    min_id = result.scalar()
                    placeholder_id = (min_id or 0) - 1
                    user = await uow.users.create(telegram_id=placeholder_id, chat_id=0, username=cmd.target_username)
            else:
                return CommandResult.fail("MISSING_TARGET", "Provide target_telegram_id or target_username.")

            participant = await uow.participants.create(
                game_id=game.id,
                user_id=user.id,
                payment_status=PaymentStatus.not_paid,
                is_manual_add=True,
            )
            # If payment phase is already open, set the amount due for this new player
            if game.status == GameStatus.payment_open and game.cost_per_player is not None:
                await uow.participants.update_amount_due(participant.id, game.cost_per_player)
            return CommandResult.ok(participant)

    async def remove_manually(self, cmd: RemovePlayerCmd) -> CommandResult[None]:
        async with UnitOfWork() as uow:
            game = await uow.games.get_by_uuid(cmd.game_uuid)
            if game is None:
                return CommandResult.fail("GAME_NOT_FOUND", "Game not found.")
            admin = await uow.users.get_by_telegram_id(cmd.admin_id)
            if admin is None or game.admin_id != admin.id:
                return CommandResult.fail("NOT_AUTHORIZED", "Only admin can remove players.")

            participant = await uow.participants.get(game.id, cmd.target_user_id)
            if participant is None:
                return CommandResult.fail("PLAYER_NOT_FOUND", "Player not found in game.")

            await uow.participants.delete(game.id, cmd.target_user_id)
            return CommandResult.ok(None)
