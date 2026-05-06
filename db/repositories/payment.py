from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import Payment, PaymentAction


class PaymentRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(
        self,
        participant_id: int,
        user_id: int,
        action: PaymentAction,
        amount: Any,
        notes: str | None = None,
    ) -> Payment:
        payment = Payment(
            participant_id=participant_id,
            actor_id=user_id,
            action=action,
            amount=amount,
            notes=notes,
        )
        self._session.add(payment)
        await self._session.flush()
        return payment
