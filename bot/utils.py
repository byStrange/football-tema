from __future__ import annotations

from typing import Any

from telegram import Update

from db.models import User
from db.unit_of_work import UnitOfWork
import logging

logger = logging.getLogger(__name__)


async def ensure_user(update: Update) -> User | None:
    user = update.effective_user
    chat = update.effective_chat
    if not user:
        return None
    async with UnitOfWork() as uow:
        db_user = await uow.users.get_by_telegram_id(user.id)
        if db_user is None:
            # Check if a placeholder exists for this username
            if user.username:
                placeholder = await uow.users.get_by_username(user.username)
                if placeholder and placeholder.telegram_id < 0:
                    placeholder.telegram_id = user.id
                    placeholder.chat_id = chat.id if chat and chat.type == "private" else user.id
                    placeholder.first_name = user.first_name
                    placeholder.last_name = user.last_name
                    db_user = placeholder
            if db_user is None and chat and chat.type == "private":
                db_user = await uow.users.create(
                    telegram_id=user.id,
                    chat_id=chat.id,
                    username=user.username,
                    first_name=user.first_name,
                    last_name=user.last_name,
                )
        return db_user


async def resolve_user_id(telegram_id: int) -> int | None:
    async with UnitOfWork() as uow:
        user = await uow.users.get_by_telegram_id(telegram_id)
        return user.id if user else None


async def game_context(update: Update, context: Any, require_admin: bool = False) -> tuple[Any, Any, Any, Any] | None:
    """Resolve game from args or active game in group. Returns (game, participants, uow) or None.
    Must be called inside an existing UnitOfWork context if *uow* is passed, but here we open our own."""
    raise NotImplementedError("Use inline resolution in handlers instead.")
