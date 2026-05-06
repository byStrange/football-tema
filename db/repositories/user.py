from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import User


class UserRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_telegram_id(self, telegram_id: int) -> User | None:
        result = await self._session.scalar(select(User).where(User.telegram_id == telegram_id))
        return result

    async def get_by_id(self, user_id: int) -> User | None:
        result = await self._session.scalar(select(User).where(User.id == user_id))
        return result

    async def get_by_username(self, username: str) -> User | None:
        result = await self._session.scalar(
            select(User).where(User.username.ilike(username))
        )
        return result

    async def create(
        self,
        telegram_id: int,
        chat_id: int,
        username: str | None = None,
        first_name: str | None = None,
        last_name: str | None = None,
    ) -> User:
        user = User(
            telegram_id=telegram_id,
            chat_id=chat_id,
            username=username,
            first_name=first_name,
            last_name=last_name,
        )
        self._session.add(user)
        await self._session.flush()
        return user

    async def list_active(self) -> list[User]:
        result = await self._session.execute(select(User).where(User.is_active.is_(True)))
        return list(result.scalars().all())
