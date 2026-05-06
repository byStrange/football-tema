from __future__ import annotations

from contextlib import AbstractAsyncContextManager
from typing import Self

from sqlalchemy.ext.asyncio import AsyncSession

from db.repositories.game import GameRepository
from db.repositories.participant import ParticipantRepository
from db.repositories.user import UserRepository
from db.repositories.user_balance import UserBalanceRepository
from db.repositories.payment import PaymentRepository
from db.session import async_session


class UnitOfWork(AbstractAsyncContextManager):
    def __init__(self) -> None:
        self.session: AsyncSession | None = None
        self.users: UserRepository | None = None
        self.games: GameRepository | None = None
        self.participants: ParticipantRepository | None = None
        self.payments: PaymentRepository | None = None
        self.user_balances: UserBalanceRepository | None = None

    async def __aenter__(self) -> Self:
        self.session = async_session()
        self.users = UserRepository(self.session)
        self.games = GameRepository(self.session)
        self.participants = ParticipantRepository(self.session)
        self.payments = PaymentRepository(self.session)
        self.user_balances = UserBalanceRepository(self.session)
        return self

    async def __aexit__(self, exc_type, exc, tb) -> bool | None:
        if self.session is None:
            return None
        if exc:
            await self.session.rollback()
        else:
            await self.session.commit()
        await self.session.close()
        return None

    async def commit(self) -> None:
        if self.session:
            await self.session.commit()
