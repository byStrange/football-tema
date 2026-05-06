from __future__ import annotations

from core.commands import CreateGameCmd
from core.events import EventBus
from core.results import CommandResult
from db.models import Game, GameStatus
from db.unit_of_work import UnitOfWork


class GameService:
    def __init__(self, event_bus: EventBus) -> None:
        self._event_bus = event_bus

    async def create_game(self, cmd: CreateGameCmd) -> CommandResult[Game]:
        if (cmd.total_cost is None and cmd.cost_per_player is None) or (
            cmd.total_cost is not None and cmd.cost_per_player is not None
        ):
            return CommandResult.fail(
                "INVALID_COST", "Specify exactly one of total_cost or cost_per_player."
            )

        async with UnitOfWork() as uow:
            admin = await uow.users.get_by_telegram_id(cmd.admin_id)
            if admin is None:
                return CommandResult.fail("ADMIN_NOT_FOUND", "Admin user not found.")

            game = await uow.games.create(
                admin_id=admin.id,
                location=cmd.location,
                scheduled_at=cmd.scheduled_at,
                total_cost=cmd.total_cost,
                cost_per_player=cmd.cost_per_player,
                max_players=cmd.max_players,
                group_chat_id=cmd.group_chat_id,
            )
            return CommandResult.ok(game)

    async def close_game(self, game_uuid: str, admin_telegram_id: int) -> CommandResult[None]:
        async with UnitOfWork() as uow:
            game = await uow.games.get_by_uuid(game_uuid)
            if game is None:
                return CommandResult.fail("GAME_NOT_FOUND", "Game not found.")
            admin = await uow.users.get_by_telegram_id(admin_telegram_id)
            if admin is None or game.admin_id != admin.id:
                return CommandResult.fail("NOT_AUTHORIZED", "Only the admin can close the game.")

            game.status = GameStatus.completed
            return CommandResult.ok(None)

    async def cancel_game(self, game_uuid: str, admin_telegram_id: int) -> CommandResult[None]:
        async with UnitOfWork() as uow:
            game = await uow.games.get_by_uuid(game_uuid)
            if game is None:
                return CommandResult.fail("GAME_NOT_FOUND", "Game not found.")
            admin = await uow.users.get_by_telegram_id(admin_telegram_id)
            if admin is None or game.admin_id != admin.id:
                return CommandResult.fail("NOT_AUTHORIZED", "Only the admin can cancel the game.")

            game.status = GameStatus.cancelled
            return CommandResult.ok(None)
