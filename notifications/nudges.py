import logging
from decimal import Decimal
from typing import Any

from db.unit_of_work import UnitOfWork
from config import config

logger = logging.getLogger(__name__)


class NudgeService:
    """Private DM reminders and optional public group mentions."""

    @staticmethod
    async def send_reminder_dm(
        user_id: int,
        game_uuid: str,
        amount: Decimal,
        message_sender: Any,
    ) -> None:
        """Send a friendly private message reminding the player to pay."""
        text = (
            f"Reminder: you owe {amount} for game {game_uuid}. "
            "Tap 'I Paid' when done."
        )
        try:
            await message_sender.send_message(chat_id=user_id, text=text)
        except Exception:
            logger.exception("Failed to send reminder DM to user %s", user_id)

    @staticmethod
    async def send_strong_nudge_dm(
        user_id: int,
        game_uuid: str,
        amount: Decimal,
        message_sender: Any,
    ) -> None:
        """Send a stronger private nudge after the payment window has been open for a while."""
        text = (
            f"It's been {config.NUDGE_INTERVAL_HOURS} hours — please pay {amount} "
            f"for game {game_uuid}. Don't forget to tap 'I Paid' once transferred."
        )
        try:
            await message_sender.send_message(chat_id=user_id, text=text)
        except Exception:
            logger.exception("Failed to send strong nudge DM to user %s", user_id)

    @staticmethod
    async def mention_unpaid_in_group(
        game_uuid: str,
        message_sender: Any,
    ) -> None:
        """Build a single group message that mentions all unpaid players."""
        async with UnitOfWork() as uow:
            game = await uow.games.get_by_uuid(game_uuid)
            if game is None:
                logger.warning("Game %s not found for group mention.", game_uuid)
                return
            participants = await uow.participants.list_by_game_uuid(game_uuid)

        unpaid = [p for p in participants if getattr(p, "payment_status", None) != "paid"]
        if not unpaid:
            return

        if not game.group_chat_id:
            logger.warning("Game %s has no group_chat_id, cannot send mention.", game_uuid)
            return

        mentions: list[str] = []
        for p in unpaid:
            user = getattr(p, "user", None)
            if user is None:
                mentions.append("Player")
                continue

            username = getattr(user, "username", None)
            telegram_id = getattr(user, "telegram_id", None)
            first_name = getattr(user, "first_name", "Player")

            if username:
                mentions.append(f"@{username}")
            elif telegram_id:
                mentions.append(f"[{first_name}](tg://user?id={telegram_id})")
            else:
                mentions.append(first_name)

        text = (
            "Payment nudge for "
            + ", ".join(mentions)
            + f" — please settle up for game {game_uuid}."
        )

        try:
            await message_sender.send_mention(chat_id=game.group_chat_id, text=text)
        except Exception:
            logger.exception("Failed to send group mention for game %s", game_uuid)
