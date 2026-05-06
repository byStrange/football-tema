from __future__ import annotations

import logging
from typing import Any

from telegram import Update

from db.unit_of_work import UnitOfWork

logger = logging.getLogger(__name__)


async def user_registration_middleware(update: Update, context: Any) -> None:
    """Ensure users exist in DB before handlers run (private or group)."""
    if not update.effective_user:
        return
    user = update.effective_user
    chat = update.effective_chat
    chat_type = chat.type if chat else "private"
    # Accept private, group, supergroup. Skip channels.
    if chat_type not in ("private", "group", "supergroup"):
        return

    async with UnitOfWork() as uow:
        db_user = await uow.users.get_by_telegram_id(user.id)
        if db_user is None:
            db_user = await uow.users.create(
                telegram_id=user.id,
                chat_id=chat.id if chat else user.id,
                username=user.username,
                first_name=user.first_name,
                last_name=user.last_name,
            )
        context.user_data["db_user_id"] = db_user.id
