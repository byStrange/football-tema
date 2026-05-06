from __future__ import annotations

from decimal import Decimal
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import UserBalance


class UserBalanceRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_user_id(self, user_id: int) -> UserBalance | None:
        result = await self._session.scalar(
            select(UserBalance).where(UserBalance.user_id == user_id)
        )
        return result

    async def create(
        self,
        user_id: int,
        amount_owed: Decimal = Decimal("0.00"),
    ) -> UserBalance:
        balance = UserBalance(user_id=user_id, amount_owed=amount_owed)
        self._session.add(balance)
        await self._session.flush()
        return balance
