from __future__ import annotations

from decimal import Decimal
from typing import Any

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from db.models import Participant, PaymentStatus


class ParticipantRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, game_id: int, user_id: int) -> Participant | None:
        result = await self._session.scalar(
            select(Participant).where(
                Participant.game_id == game_id,
                Participant.user_id == user_id,
            )
        )
        return result

    async def get_by_id(self, participant_id: int) -> Participant | None:
        result = await self._session.scalar(
            select(Participant)
            .where(Participant.id == participant_id)
            .options(joinedload(Participant.user))
        )
        return result

    async def create(
        self,
        game_id: int,
        user_id: int,
        payment_status: PaymentStatus = PaymentStatus.not_paid,
        is_manual_add: bool = False,
    ) -> Participant:
        participant = Participant(
            game_id=game_id,
            user_id=user_id,
            payment_status=payment_status,
            is_manual_add=is_manual_add,
        )
        self._session.add(participant)
        await self._session.flush()
        return participant

    async def list_for_game(self, game_id: int) -> list[Participant]:
        result = await self._session.execute(
            select(Participant)
            .where(Participant.game_id == game_id)
            .options(joinedload(Participant.user))
        )
        return list(result.scalars().all())

    async def delete(self, game_id: int, user_id: int) -> None:
        participant = await self.get(game_id, user_id)
        if participant:
            await self._session.delete(participant)

    async def count_for_game(self, game_id: int) -> int:
        result = await self._session.scalar(
            select(func.count()).select_from(Participant).where(Participant.game_id == game_id)
        )
        return result or 0

    async def update_status(
        self,
        participant_id: int,
        status: PaymentStatus,
        confirmed_by: int | None = None,
        confirmed_at: Any = None,
        screenshot_file_id: str | None = None,
    ) -> None:
        participant = await self.get_by_id(participant_id)
        if participant is None:
            return
        participant.payment_status = status
        if confirmed_by is not None:
            participant.confirmed_by = confirmed_by
        if confirmed_at is not None:
            participant.confirmed_at = confirmed_at
        if screenshot_file_id is not None:
            participant.screenshot_file_id = screenshot_file_id

    async def update_amount_due(self, participant_id: int, amount: Decimal) -> None:
        participant = await self.get_by_id(participant_id)
        if participant is not None:
            participant.amount_due = amount

    async def list_by_game_uuid(self, game_uuid: str) -> list[Participant]:
        from sqlalchemy.orm import joinedload
        from db.models import Game
        result = await self._session.execute(
            select(Participant)
            .join(Game)
            .where(Game.game_uuid == game_uuid)
            .options(joinedload(Participant.user))
        )
        return list(result.scalars().all())
