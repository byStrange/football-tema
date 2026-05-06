from __future__ import annotations

from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import Game, GameStatus


class GameRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_uuid(self, game_uuid: str) -> Game | None:
        result = await self._session.scalar(select(Game).where(Game.game_uuid == game_uuid))
        return result

    async def get_by_id(self, game_id: int) -> Game | None:
        result = await self._session.scalar(select(Game).where(Game.id == game_id))
        return result

    async def create(
        self,
        admin_id: int,
        location: str,
        scheduled_at: Any,
        total_cost: Decimal | None = None,
        cost_per_player: Decimal | None = None,
        max_players: int | None = None,
        group_chat_id: int = 0,
    ) -> Game:
        game = Game(
            admin_id=admin_id,
            location=location,
            scheduled_at=scheduled_at,
            total_cost=total_cost,
            cost_per_player=cost_per_player,
            max_players=max_players,
            group_chat_id=group_chat_id,
        )
        self._session.add(game)
        await self._session.flush()
        return game

    async def list_active_for_group(self, group_chat_id: int) -> list[Game]:
        result = await self._session.execute(
            select(Game).where(
                Game.group_chat_id == group_chat_id,
                Game.status.in_([GameStatus.announced, GameStatus.payment_open]),
            )
        )
        return list(result.scalars().all())

    async def list_upcoming(self) -> list[Game]:
        from datetime import datetime
        result = await self._session.execute(
            select(Game).where(
                Game.scheduled_at >= datetime.utcnow(),
                Game.status.in_([GameStatus.announced, GameStatus.payment_open]),
            )
        )
        return list(result.scalars().all())
