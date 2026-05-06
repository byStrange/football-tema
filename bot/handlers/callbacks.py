from __future__ import annotations

import logging
from typing import Any

from telegram import Update
from telegram.ext import CallbackQueryHandler, ContextTypes

from bot.keyboards import admin_confirm_keyboard, dm_payment_keyboard
from bot.messages import format_group_payment_summary, format_dm_payment_prompt
from bot.utils import ensure_user
from core.commands import (
    ConfirmPaymentCmd,
    JoinGameCmd,
    LeaveGameCmd,
    PlayerPaidCmd,
    TriggerPaymentCmd,
)
from core.services.game import GameService
from core.services.player import PlayerService
from core.services.payment import PaymentService
from core.services.notification import NotificationService
from db.unit_of_work import UnitOfWork

logger = logging.getLogger(__name__)


async def route_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if not query or not query.data:
        return
    await query.answer()

    user = update.effective_user
    if not user:
        return

    parts = query.data.split(":", 1)
    if len(parts) != 2:
        return
    action, value = parts

    if action == "join":
        await _handle_join(query, context, user.id, value)
    elif action == "decline":
        await _handle_decline(query, context, user.id, value)
    elif action == "paid":
        await _handle_paid(query, context, user.id, int(value))
    elif action == "screenshot":
        await _handle_screenshot_prompt(query, context, int(value))
    elif action == "confirm":
        await _handle_confirm(query, context, user.id, int(value))
    elif action == "reject":
        await _handle_reject(query, context, user.id, int(value))
    elif action == "trigger_payment":
        await _handle_trigger_payment(query, context, user.id, value)
    elif action == "close_game":
        await _handle_close_game(query, context, user.id, value)
    else:
        logger.warning("Unknown callback action: %s", action)


async def _handle_join(query: Any, context: ContextTypes.DEFAULT_TYPE, telegram_id: int, game_uuid: str) -> None:
    player_svc: PlayerService = context.bot_data["player_service"]
    result = await player_svc.join(
        JoinGameCmd(game_uuid=game_uuid, user_id=telegram_id, chat_id=query.from_user.id)
    )
    if not result.success:
        await query.answer(result.error_message or "Could not join", show_alert=True)
        return
    await _refresh_announcement(query, context, game_uuid)


async def _handle_decline(query: Any, context: ContextTypes.DEFAULT_TYPE, telegram_id: int, game_uuid: str) -> None:
    player_svc: PlayerService = context.bot_data["player_service"]
    result = await player_svc.leave(LeaveGameCmd(game_uuid=game_uuid, user_id=telegram_id))
    if not result.success:
        await query.answer(result.error_message or "Could not leave", show_alert=True)
        return
    await _refresh_announcement(query, context, game_uuid)


async def _handle_paid(query: Any, context: ContextTypes.DEFAULT_TYPE, telegram_id: int, participant_id: int) -> None:
    payment_svc: PaymentService = context.bot_data["payment_service"]
    result = await payment_svc.player_paid(PlayerPaidCmd(participant_id=participant_id, user_id=telegram_id))
    if result.success:
        await query.answer("Payment marked as pending confirmation.")
        # DM admin
        async with UnitOfWork() as uow:
            participant = await uow.participants.get_by_id(participant_id)
            if participant and participant.user:
                game = await uow.games.get_by_id(participant.game_id)
                if game:
                    await context.bot.send_message(
                        chat_id=game.created_by,
                        text=f"Player {participant.user.first_name or participant.user.username} marked payment as pending for game {game.game_uuid}.",
                    )
                    await context.bot.send_message(
                        chat_id=game.created_by,
                        text="Tap to confirm or reject:",
                        reply_markup=admin_confirm_keyboard(participant_id),
                    )
    else:
        await query.answer(result.error_message or "Error", show_alert=True)


async def _handle_screenshot_prompt(query: Any, context: ContextTypes.DEFAULT_TYPE, participant_id: int) -> None:
    context.user_data["awaiting_screenshot_for_participant_id"] = participant_id
    await query.answer("Send the screenshot now.")
    await context.bot.send_message(
        chat_id=query.from_user.id,
        text="Please send the payment screenshot.",
    )


async def _handle_confirm(query: Any, context: ContextTypes.DEFAULT_TYPE, admin_telegram_id: int, participant_id: int) -> None:
    from config import config
    if not config.is_admin(admin_telegram_id):
        await query.answer("Admin only.", show_alert=True)
        return
    payment_svc: PaymentService = context.bot_data["payment_service"]
    result = await payment_svc.confirm(
        ConfirmPaymentCmd(participant_id=participant_id, admin_id=admin_telegram_id, approved=True)
    )
    if result.success:
        await query.answer("Payment confirmed.")
        await _refresh_payment_summary(query, context, participant_id)
    else:
        await query.answer(result.error_message or "Error", show_alert=True)


async def _handle_reject(query: Any, context: ContextTypes.DEFAULT_TYPE, admin_telegram_id: int, participant_id: int) -> None:
    from config import config
    if not config.is_admin(admin_telegram_id):
        await query.answer("Admin only.", show_alert=True)
        return
    payment_svc: PaymentService = context.bot_data["payment_service"]
    result = await payment_svc.confirm(
        ConfirmPaymentCmd(participant_id=participant_id, admin_id=admin_telegram_id, approved=False)
    )
    if result.success:
        await query.answer("Payment rejected.")
        await _refresh_payment_summary(query, context, participant_id)
    else:
        await query.answer(result.error_message or "Error", show_alert=True)


async def _handle_trigger_payment(query: Any, context: ContextTypes.DEFAULT_TYPE, admin_telegram_id: int, game_uuid: str) -> None:
    from config import config
    if not config.is_admin(admin_telegram_id):
        await query.answer("Admin only.", show_alert=True)
        return
    payment_svc: PaymentService = context.bot_data["payment_service"]
    # Card number is hardcoded here for simplicity; ideally ask via conversation.
    result = await payment_svc.trigger(
        TriggerPaymentCmd(game_uuid=game_uuid, admin_id=admin_telegram_id, card_number="1234-5678-9012-3456")
    )
    if result.success:
        amount = result.data
        async with UnitOfWork() as uow:
            game = await uow.games.get_by_uuid(game_uuid)
            participants = await uow.participants.list_for_game(game.id)
        text = format_group_payment_summary(game, participants)
        await query.edit_message_text(text, parse_mode="Markdown")
        # DM each participant
        for p in participants:
            user = getattr(p, "user", None)
            if user and user.chat_id:
                await context.bot.send_message(
                    chat_id=user.chat_id,
                    text=format_dm_payment_prompt(game, amount),
                    reply_markup=dm_payment_keyboard(p.id),
                    parse_mode="Markdown",
                )
    else:
        await query.answer(result.error_message or "Error", show_alert=True)


async def _handle_close_game(query: Any, context: ContextTypes.DEFAULT_TYPE, admin_telegram_id: int, game_uuid: str) -> None:
    from config import config
    if not config.is_admin(admin_telegram_id):
        await query.answer("Admin only.", show_alert=True)
        return
    game_svc: GameService = context.bot_data["game_service"]
    result = await game_svc.close_game(game_uuid, admin_telegram_id)
    if result.success:
        await query.answer("Game closed.")
        await query.edit_message_reply_markup(reply_markup=None)
    else:
        await query.answer(result.error_message or "Error", show_alert=True)


async def _refresh_announcement(query: Any, context: ContextTypes.DEFAULT_TYPE, game_uuid: str) -> None:
    async with UnitOfWork() as uow:
        game = await uow.games.get_by_uuid(game_uuid)
        if not game or not game.announcement_message_id:
            return
        participants = await uow.participants.list_for_game(game.id)
    from bot.messages import format_game_announcement
    from bot.keyboards import game_announcement_keyboard
    text = format_game_announcement(game, participants)
    try:
        await context.bot.edit_message_text(
            chat_id=game.group_chat_id,
            message_id=game.announcement_message_id,
            text=text,
            reply_markup=game_announcement_keyboard(game_uuid),
            parse_mode="Markdown",
        )
    except Exception as exc:
        logger.debug("Could not edit announcement: %s", exc)


async def _refresh_payment_summary(query: Any, context: ContextTypes.DEFAULT_TYPE, participant_id: int) -> None:
    async with UnitOfWork() as uow:
        participant = await uow.participants.get_by_id(participant_id)
        if not participant:
            return
        game = await uow.games.get_by_id(participant.game_id)
        if not game:
            return
        participants = await uow.participants.list_for_game(game.id)
    text = format_group_payment_summary(game, participants)
    try:
        if game.payment_message_id:
            await context.bot.edit_message_text(
                chat_id=game.group_chat_id,
                message_id=game.payment_message_id,
                text=text,
                parse_mode="Markdown",
            )
    except Exception as exc:
        logger.debug("Could not edit payment summary: %s", exc)


callback_router = CallbackQueryHandler(route_callback)
