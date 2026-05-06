import logging
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from telegram.ext import ExtBot

from core.services.notification import NotificationService
from db.unit_of_work import UnitOfWork
from notifications import MessageSender
from notifications.nudges import NudgeService

from config import config

logger = logging.getLogger(__name__)

REMINDER_INTERVAL_HOURS: int = config.REMINDER_INTERVAL_HOURS
NUDGE_INTERVAL_HOURS: int = config.NUDGE_INTERVAL_HOURS

_scheduler: AsyncIOScheduler | None = None
_notification_service: NotificationService | None = None
_bot: ExtBot | None = None


def start_scheduler(bot: ExtBot, notification_service: NotificationService) -> AsyncIOScheduler:
    """Create scheduler, start it, and store reference in ``bot_data``."""
    global _scheduler, _notification_service, _bot
    _scheduler = AsyncIOScheduler()
    _scheduler.start()
    _notification_service = notification_service
    _bot = bot
    return _scheduler


def schedule_pre_game_reminder(game_uuid: str, scheduled_at: datetime) -> None:
    """Schedule a reminder to be sent ``REMINDER_INTERVAL_HOURS`` before the game."""
    if _scheduler is None:
        raise RuntimeError("Scheduler has not been started. Call start_scheduler first.")

    trigger_time = scheduled_at - timedelta(hours=REMINDER_INTERVAL_HOURS)
    if _is_past(trigger_time):
        logger.debug("Reminder trigger time is in the past for game %s, skipping.", game_uuid)
        return

    job_id = f"game_{game_uuid}_pre_game_reminder"
    _scheduler.add_job(
        _fire_pre_game_reminder,
        trigger="date",
        run_date=trigger_time,
        id=job_id,
        args=[game_uuid],
        replace_existing=True,
    )


def schedule_payment_nudge(game_uuid: str, opened_at: datetime) -> None:
    """Schedule a stronger nudge to be sent ``NUDGE_INTERVAL_HOURS`` after payments opened."""
    if _scheduler is None:
        raise RuntimeError("Scheduler has not been started. Call start_scheduler first.")

    trigger_time = opened_at + timedelta(hours=NUDGE_INTERVAL_HOURS)
    if _is_past(trigger_time):
        logger.debug("Nudge trigger time is in the past for game %s, skipping.", game_uuid)
        return

    job_id = f"game_{game_uuid}_payment_nudge"
    _scheduler.add_job(
        _fire_payment_nudge,
        trigger="date",
        run_date=trigger_time,
        id=job_id,
        args=[game_uuid],
        replace_existing=True,
    )


def unschedule_game_jobs(game_uuid: str) -> None:
    """Remove all jobs related to a game by job ID prefix."""
    if _scheduler is None:
        return

    prefix = f"game_{game_uuid}_"
    for job in _scheduler.get_jobs():
        if job.id.startswith(prefix):
            _scheduler.remove_job(job.id)
            logger.debug("Removed job %s", job.id)


async def _fire_pre_game_reminder(game_uuid: str) -> None:
    """Send a reminder DM to all unpaid participants."""
    if _notification_service is None or _bot is None:
        return

    try:
        async with UnitOfWork() as uow:
            game = await uow.games.get_by_uuid(game_uuid)
            participants = await uow.participants.list_by_game_uuid(game_uuid)

        if game is None:
            return

        unpaid = [p for p in participants if getattr(p, "payment_status", None) != "paid"]
        if not unpaid:
            return

        sender = _BotMessageSender(_bot)
        for p in unpaid:
            amount = getattr(p, "amount_due", None) or Decimal("0")
            user_id = _telegram_chat_id(p)
            if user_id is None:
                continue
            await _notification_service.send_reminder(
                user_id=user_id,
                game_uuid=game_uuid,
                amount=amount,
                message_sender=sender,
            )
    except Exception:
        logger.exception("Failed to fire pre-game reminder for game %s", game_uuid)


async def _fire_payment_nudge(game_uuid: str) -> None:
    """Send a strong nudge DM to unpaid participants and optionally mention them in the group."""
    if _bot is None:
        return

    try:
        async with UnitOfWork() as uow:
            game = await uow.games.get_by_uuid(game_uuid)
            participants = await uow.participants.list_by_game_uuid(game_uuid)

        if game is None:
            return

        unpaid = [p for p in participants if getattr(p, "payment_status", None) != "paid"]
        if not unpaid:
            return

        sender = _BotMessageSender(_bot)
        for p in unpaid:
            amount = getattr(p, "amount_due", None) or Decimal("0")
            user_id = _telegram_chat_id(p)
            if user_id is None:
                continue
            await NudgeService.send_strong_nudge_dm(
                user_id=user_id,
                game_uuid=game_uuid,
                amount=amount,
                message_sender=sender,
            )

        await NudgeService.mention_unpaid_in_group(
            game_uuid=game_uuid,
            message_sender=sender,
        )
    except Exception:
        logger.exception("Failed to fire payment nudge for game %s", game_uuid)


def _is_past(dt: datetime) -> bool:
    """Return ``True`` if *dt* is in the past (naive or aware)."""
    now = datetime.now(tz=timezone.utc) if dt.tzinfo else datetime.utcnow()
    return dt <= now


def _telegram_chat_id(participant: Any) -> int | None:
    """Resolve a participant's private DM chat id (telegram_id or chat_id)."""
    user = getattr(participant, "user", None)
    if user is None:
        return getattr(participant, "user_id", None)
    return getattr(user, "chat_id", None) or getattr(user, "telegram_id", None)


class _BotMessageSender:
    """Minimal adapter wrapping ``ExtBot`` for the notification layer."""

    def __init__(self, bot: ExtBot) -> None:
        self._bot = bot

    async def send_message(self, chat_id: int, text: str, **kwargs: Any) -> Any:
        return await self._bot.send_message(chat_id=chat_id, text=text, **kwargs)

    async def edit_message(self, chat_id: int, message_id: int, text: str, **kwargs: Any) -> Any:
        return await self._bot.edit_message_text(
            chat_id=chat_id, message_id=message_id, text=text, **kwargs
        )

    async def send_mention(self, chat_id: int, text: str, **kwargs: Any) -> Any:
        return await self._bot.send_message(
            chat_id=chat_id, text=text, parse_mode="Markdown", **kwargs
        )
