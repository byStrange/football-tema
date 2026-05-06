import logging
from decimal import Decimal
from typing import Any

from bot.messages import format_game_announcement
from db.unit_of_work import UnitOfWork

logger = logging.getLogger(__name__)


class LiveMessageManager:
    """Manages the pinned / live-updating group messages for a game."""

    @staticmethod
    async def update_announcement(game_uuid: str, message_sender: Any) -> None:
        """Load the game, re-render the announcement and edit the group message."""
        async with UnitOfWork() as uow:
            game = await uow.games.get_by_uuid(game_uuid)
            if game is None:
                logger.warning("Game %s not found for live announcement update.", game_uuid)
                return
            participants = await uow.participants.list_by_game_uuid(game_uuid)

        if not game.group_chat_id or not game.announcement_message_id:
            logger.warning(
                "Missing group_chat_id or announcement_message_id for game %s", game_uuid
            )
            return

        text, reply_markup = format_game_announcement(game, participants)
        await message_sender.edit_message(
            chat_id=game.group_chat_id,
            message_id=game.announcement_message_id,
            text=text,
            reply_markup=reply_markup,
        )

    @staticmethod
    async def update_payment_summary(game_uuid: str, message_sender: Any) -> None:
        """Re-render the payment summary and edit (or create) the group message."""
        async with UnitOfWork() as uow:
            game = await uow.games.get_by_uuid(game_uuid)
            if game is None:
                logger.warning("Game %s not found for live payment update.", game_uuid)
                return
            participants = await uow.participants.list_by_game_uuid(game_uuid)

        if not game.group_chat_id:
            logger.warning("Missing group_chat_id for game %s", game_uuid)
            return

        text = _render_payment_summary(game, participants)

        if game.payment_message_id:
            await message_sender.edit_message(
                chat_id=game.group_chat_id,
                message_id=game.payment_message_id,
                text=text,
            )
        else:
            sent = await message_sender.send_message(
                chat_id=game.group_chat_id,
                text=text,
            )
            message_id = getattr(sent, "message_id", None)
            if message_id is not None:
                async with UnitOfWork() as uow:
                    game = await uow.games.get_by_uuid(game_uuid)
                    if game is not None:
                        game.payment_message_id = message_id


def _render_payment_summary(game: Any, participants: list[Any]) -> str:
    """Build a plain-text payment summary for a game."""
    paid = [p for p in participants if getattr(p, "payment_status", None) == "paid"]
    unpaid = [p for p in participants if getattr(p, "payment_status", None) != "paid"]

    total_due = sum((getattr(p, "amount_due", None) or Decimal("0") for p in participants), Decimal("0"))
    total_paid = sum((getattr(p, "amount_due", None) or Decimal("0") for p in paid), Decimal("0"))

    lines = [
        f"Payment summary for game {getattr(game, 'game_uuid', 'unknown')}:",
        f"Total due: {total_due}",
        f"Collected: {total_paid} from {len(paid)}/{len(participants)} players",
    ]

    if unpaid:
        lines.append("")
        lines.append("Unpaid players:")
        for p in unpaid:
            user = getattr(p, "user", None)
            name = (
                getattr(user, "username", None)
                or getattr(user, "first_name", None)
                or "Player"
            )
            amount = getattr(p, "amount_due", None) or Decimal("0")
            lines.append(f"- {name}: {amount}")
    else:
        lines.append("All paid up!")

    return "\n".join(lines)
