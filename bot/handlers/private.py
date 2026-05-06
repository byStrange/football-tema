from __future__ import annotations

import logging
from decimal import Decimal
from typing import Any

from telegram import Update
from telegram.ext import CommandHandler, ContextTypes, filters, MessageHandler

from core.services.debt import DebtService
from core.services.game import GameService
from db.models import PaymentStatus
from db.unit_of_work import UnitOfWork
from bot.messages import format_debt_summary, format_dm_payment_prompt

logger = logging.getLogger(__name__)


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message:
        return
    text = (
        "👋 Welcome to the Football Payment Bot!\n\n"
        "I help track attendance and payments for your weekly games.\n"
        "Make sure to join games announced in the group, "
        "and I'll DM you when it's time to pay.\n\n"
        "Commands:\n"
        "/mygames — Your upcoming games\n"
        "/debt — Your balance\n"
        "/pay <game_uuid> — Show payment prompt"
    )
    await update.message.reply_text(text)


async def cmd_mygames(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.effective_user:
        return
    async with UnitOfWork() as uow:
        user = await uow.users.get_by_telegram_id(update.effective_user.id)
        if user is None:
            await update.message.reply_text("Start the bot with /start first.")
            return
        participants = await uow.participants.list_for_game(user.id)
        # This is wrong: list_for_game filters by game_id, not user_id.
        # Need to get upcoming games where user is a participant.
        # Let's query directly.
        from sqlalchemy import select
        from db.models import Game, Participant, GameStatus
        result = await uow.session.execute(
            select(Game)
            .join(Participant)
            .where(
                Participant.user_id == user.id,
                Game.status.in_([GameStatus.announced, GameStatus.payment_open]),
            )
        )
        games = list(result.scalars().all())

    if not games:
        await update.message.reply_text("You have no upcoming games.")
        return

    lines = ["Your upcoming games:"]
    for g in games:
        lines.append(f"• {g.location} — {g.scheduled_at} ({g.game_uuid})")
    await update.message.reply_text("\n".join(lines))


async def cmd_private_debt(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.effective_user:
        return
    async with UnitOfWork() as uow:
        user = await uow.users.get_by_telegram_id(update.effective_user.id)
    if not user:
        await update.message.reply_text("Start with /start")
        return
    debt_svc: DebtService = context.bot_data.get("debt_service")
    if debt_svc is None:
        await update.message.reply_text("Service unavailable.")
        return
    balance = await debt_svc.get_balance(user.id)
    text = format_debt_summary(balance)
    await update.message.reply_text(text, parse_mode="Markdown")


async def cmd_pay(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message or not update.effective_user:
        return
    args = context.args
    if not args:
        await update.message.reply_text("Usage: /pay <game_uuid>")
        return
    game_uuid = args[0]
    async with UnitOfWork() as uow:
        user = await uow.users.get_by_telegram_id(update.effective_user.id)
        if not user:
            await update.message.reply_text("Start with /start")
            return
        game = await uow.games.get_by_uuid(game_uuid)
        if not game:
            await update.message.reply_text("Game not found.")
            return
        participant = await uow.participants.get(game.id, user.id)
        if not participant:
            await update.message.reply_text("You are not in this game.")
            return
        if participant.payment_status == PaymentStatus.paid:
            await update.message.reply_text("You already paid for this game.")
            return
        if participant.amount_due is None:
            await update.message.reply_text("Payments haven't started yet for this game.")
            return

    from bot.keyboards import dm_payment_keyboard
    text = format_dm_payment_prompt(game, participant.amount_due)
    await update.message.reply_text(
        text, reply_markup=dm_payment_keyboard(participant.id), parse_mode="Markdown"
    )


async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message or not update.message.photo or not update.effective_user:
        return
    participant_id = context.user_data.get("awaiting_screenshot_for_participant_id")
    if not participant_id:
        await update.message.reply_text("I wasn't expecting a photo. Use the Upload Screenshot button first.")
        return
    file_id = update.message.photo[-1].file_id
    from core.services.payment import PaymentService
    from core.commands import UploadScreenshotCmd
    payment_svc: PaymentService = context.bot_data["payment_service"]
    async with UnitOfWork() as uow:
        user = await uow.users.get_by_telegram_id(update.effective_user.id)
    if not user:
        return
    result = await payment_svc.upload_screenshot(
        UploadScreenshotCmd(participant_id=participant_id, user_id=user.id, file_id=file_id)
    )
    if result.success:
        await update.message.reply_text("Screenshot received. Admin will review.")
    else:
        await update.message.reply_text(f"Error: {result.error_message}")
    context.user_data.pop("awaiting_screenshot_for_participant_id", None)


private_handlers = [
    CommandHandler("start", cmd_start, filters=filters.ChatType.PRIVATE),
    CommandHandler("mygames", cmd_mygames, filters=filters.ChatType.PRIVATE),
    CommandHandler("debt", cmd_private_debt, filters=filters.ChatType.PRIVATE),
    CommandHandler("pay", cmd_pay, filters=filters.ChatType.PRIVATE),
    MessageHandler(filters.PHOTO, handle_photo),
]
