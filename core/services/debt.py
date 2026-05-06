from __future__ import annotations

from decimal import Decimal

from db.unit_of_work import UnitOfWork


class DebtService:
    async def get_balance(self, user_id: int, uow: UnitOfWork | None = None) -> Decimal:
        if uow is not None:
            return await self._get_balance(uow, user_id)
        async with UnitOfWork() as uow:
            return await self._get_balance(uow, user_id)

    async def _get_balance(self, uow: UnitOfWork, user_id: int) -> Decimal:
        balance = await uow.user_balances.get_by_user_id(user_id)
        if balance is None:
            return Decimal("0")
        return balance.amount_owed

    async def record_credit(self, user_id: int, amount: Decimal, uow: UnitOfWork | None = None) -> None:
        if uow is not None:
            await self._record_credit(uow, user_id, amount)
        else:
            async with UnitOfWork() as uow:
                await self._record_credit(uow, user_id, amount)

    async def _record_credit(self, uow: UnitOfWork, user_id: int, amount: Decimal) -> None:
        balance = await uow.user_balances.get_by_user_id(user_id)
        if balance is None:
            balance = await uow.user_balances.create(user_id=user_id, amount_owed=Decimal("0"))
        balance.amount_owed = max(Decimal("0"), balance.amount_owed - amount)

    async def record_debt(self, user_id: int, amount: Decimal, uow: UnitOfWork | None = None) -> None:
        if uow is not None:
            await self._record_debt(uow, user_id, amount)
        else:
            async with UnitOfWork() as uow:
                await self._record_debt(uow, user_id, amount)

    async def _record_debt(self, uow: UnitOfWork, user_id: int, amount: Decimal) -> None:
        balance = await uow.user_balances.get_by_user_id(user_id)
        if balance is None:
            balance = await uow.user_balances.create(user_id=user_id, amount_owed=Decimal("0"))
        balance.amount_owed += amount
