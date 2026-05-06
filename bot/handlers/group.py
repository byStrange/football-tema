from __future__ import annotations

import logging
from datetime import datetime
from decimal import Decimal
from typing import Any

from telegram import Update
from telegram.ext import (
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    filters,
    MessageHandler,
)

from bot.keyboards import admin_game_controls_keyboard, game_announcement_keyboard, payment_board_keyboard
from bot.messages import (
    format_game_announcement,
    format_dm_payment_prompt,
    format_group_payment_summary,
    format_debt_summary,
    format_payment_board,
)
from bot.utils import ensure_user
from core.commands import CreateGameCmd, JoinGameCmd, LeaveGameCmd, UploadScreenshotCmd
from core.services.game import GameService
from core.services.player import PlayerService
from core.services.debt import DebtService
from core.services.payment import PaymentService
from db.unit_of_work import UnitOfWork
from config import config

logger = logging.getLogger(__name__)

LOCATION, DATETIME, COST, MAX_PLAYERS = range(4)


async def _is_admin(user_id: int) -> bool:
    return config.is_admin(user_id)


async def cmd_newgame(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if not update.effective_user or not await _is_admin(update.effective_user.id):
        if update.message:
            await update.message.reply_text("Only admins can create games.")
        return ConversationHandler.END
    if update.message:
        await update.message.reply_text("Where is the game? (Send the location)")
    return LOCATION


async def newgame_location(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if not update.message:
        return ConversationHandler.END
    loc = update.message.location
    if loc:
        context.chat_data["newgame_location"] = {
            "latitude": loc.latitude,
            "longitude": loc.longitude,
            "text": update.message.text or "",
        }
    else:
        context.chat_data["newgame_location"] = {
            "latitude": None,
            "longitude": None,
            "text": update.message.text or "",
        }
    await update.message.reply_text("When is the game? (YYYY-MM-DD HH:MM)")
    return DATETIME


async def newgame_datetime(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if not update.message or not update.message.text:
        return ConversationHandler.END
    try:
        dt = datetime.strptime(update.message.text, "%Y-%m-%d %H:%M")
    except ValueError:
        await update.message.reply_text("Invalid format. Use YYYY-MM-DD HH:MM")
        return DATETIME
    context.chat_data["newgame_datetime"] = dt
    await update.message.reply_text("Enter the total cost:")
    return COST


async def newgame_cost(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if not update.message or not update.message.text:
        return ConversationHandler.END
    try:
        amount = Decimal(update.message.text.strip())
    except Exception:
        await update.message.reply_text("Invalid amount. Enter a number.")
        return COST
    context.chat_data["newgame_total_cost"] = amount
    await update.message.reply_text("Max players? (Send a number or 0 to skip)")
    return MAX_PLAYERS


async def newgame_max_players(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if not update.message or not update.message.text:
        return ConversationHandler.END
    text = update.message.text.strip()
    max_players = int(text) if text.isdigit() and int(text) > 0 else None
    context.chat_data["newgame_max_players"] = max_players

    if not update.effective_user or not update.effective_chat:
        return ConversationHandler.END

    location_data = context.chat_data.get("newgame_location") or {}
    location_text = location_data.get("text") if isinstance(location_data, dict) else str(location_data or "")

    cmd = CreateGameCmd(
        admin_id=update.effective_user.id,
        location=location_text,
        scheduled_at=context.chat_data.get("newgame_datetime", datetime.utcnow()),
        total_cost=context.chat_data.get("newgame_total_cost"),
        cost_per_player=None,
        max_players=max_players,
        group_chat_id=update.effective_chat.id,
    )
    game_svc: GameService = context.bot_data["game_service"]
    result = await game_svc.create_game(cmd)
    if not result.success:
        await update.message.reply_text(f"Error: {result.error_message}")
        return ConversationHandler.END

    game = result.data
    chat_id = update.effective_chat.id

    has_pin = isinstance(location_data, dict) and location_data.get("latitude") is not None and location_data.get("longitude") is not None

    # If coordinates are available, send location pin first
    if has_pin:
        await context.bot.send_location(
            chat_id=chat_id,
            latitude=location_data["latitude"],
            longitude=location_data["longitude"],
        )

    announcement_text = format_game_announcement(game, [], has_location_pin=has_pin)
    keyboard = game_announcement_keyboard(game.game_uuid)
    sent = await context.bot.send_message(
        chat_id=chat_id,
        text=announcement_text,
        reply_markup=keyboard,
        parse_mode="Markdown",
    )
    announcement_message_id = sent.message_id

    # Pin the announcement message
    await context.bot.pin_chat_message(chat_id=chat_id, message_id=announcement_message_id)

    # Store announcement_message_id
    from db.unit_of_work import UnitOfWork
    async with UnitOfWork() as uow:
        db_game = await uow.games.get_by_uuid(game.game_uuid)
        if db_game:
            db_game.announcement_message_id = announcement_message_id

    return ConversationHandler.END


async def newgame_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if update.message:
        await update.message.reply_text("Game creation cancelled.")
    return ConversationHandler.END


newgame_conversation = ConversationHandler(
    entry_points=[CommandHandler("newgame", cmd_newgame, filters=filters.ChatType.GROUPS)],
    states={
        LOCATION: [MessageHandler((filters.TEXT | filters.LOCATION) & ~filters.COMMAND, newgame_location)],
        DATETIME: [MessageHandler(filters.TEXT & ~filters.COMMAND, newgame_datetime)],
        COST: [MessageHandler(filters.TEXT & ~filters.COMMAND, newgame_cost)],
        MAX_PLAYERS: [MessageHandler(filters.TEXT & ~filters.COMMAND, newgame_max_players)],
    },
    fallbacks=[CommandHandler("cancel", newgame_cancel)],
)


async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message:
        return
    args = context.args
    if not args:
        await update.message.reply_text("Usage: /status <game_uuid>")
        return
    game_uuid = args[0]
    from db.unit_of_work import UnitOfWork
    async with UnitOfWork() as uow:
        game = await uow.games.get_by_uuid(game_uuid)
        if game is None:
            await update.message.reply_text("Game not found.")
            return
        participants = await uow.participants.list_for_game(game.id)
    text = format_group_payment_summary(game, participants)
    await update.message.reply_text(text, parse_mode="Markdown")


async def cmd_close(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message or not update.effective_user:
        return
    if not await _is_admin(update.effective_user.id):
        await update.message.reply_text("Admin only.")
        return
    args = context.args
    if not args:
        await update.message.reply_text("Usage: /close <game_uuid>")
        return
    game_uuid = args[0]
    game_svc: GameService = context.bot_data["game_service"]

    from db.unit_of_work import UnitOfWork
    async with UnitOfWork() as uow:
        game = await uow.games.get_by_uuid(game_uuid)
        if game and game.announcement_message_id:
            try:
                await context.bot.unpin_chat_message(chat_id=game.group_chat_id, message_id=game.announcement_message_id)
            except Exception:
                pass

    result = await game_svc.close_game(game_uuid, update.effective_user.id)
    if result.success:
        await update.message.reply_text("Game closed.")
    else:
        await update.message.reply_text(f"Error: {result.error_message}")


async def cmd_cancel_game(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message or not update.effective_user:
        return
    if not await _is_admin(update.effective_user.id):
        await update.message.reply_text("Admin only.")
        return
    args = context.args
    if not args:
        await update.message.reply_text("Usage: /cancel <game_uuid>")
        return
    game_uuid = args[0]
    game_svc: GameService = context.bot_data["game_service"]

    from db.unit_of_work import UnitOfWork
    async with UnitOfWork() as uow:
        game = await uow.games.get_by_uuid(game_uuid)
        if game and game.announcement_message_id:
            try:
                await context.bot.unpin_chat_message(chat_id=game.group_chat_id, message_id=game.announcement_message_id)
            except Exception:
                pass

    result = await game_svc.cancel_game(game_uuid, update.effective_user.id)
    if result.success:
        await update.message.reply_text("Game cancelled.")
    else:
        await update.message.reply_text(f"Error: {result.error_message}")


async def cmd_debt(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message or not update.effective_user:
        return
    user = await ensure_user(update)
    if user is None:
        await update.message.reply_text("Start the bot in DM first: /start")
        return
    debt_svc: DebtService = context.bot_data.get("debt_service")
    if debt_svc is None:
        await update.message.reply_text("Service unavailable.")
        return
    balance = await debt_svc.get_balance(user.id)
    text = format_debt_summary(balance)
    await update.message.reply_text(text, parse_mode="Markdown")


async def cmd_trigger_payment(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Admin command to trigger payment phase."""
    if not update.message or not update.effective_user:
        return
    if not await _is_admin(update.effective_user.id):
        await update.message.reply_text("Admin only.")
        return
    args = context.args
    if not args:
        await update.message.reply_text("Usage: /pay <card_number> or /pay <game_uuid> <card_number>")
        return

    group_chat_id = update.effective_chat.id if update.effective_chat else None
    if len(args) == 1:
        card_number = args[0]
        from db.unit_of_work import UnitOfWork
        async with UnitOfWork() as uow:
            active_games = await uow.games.list_active_for_group(group_chat_id)
        if len(active_games) == 0:
            await update.message.reply_text("No active game found in this group.")
            return
        if len(active_games) > 1:
            await update.message.reply_text("Multiple active games found. Use /pay <game_uuid> <card_number>.")
            return
        game_uuid = active_games[0].game_uuid
    else:
        game_uuid = args[0]
        card_number = args[1]

    from core.services.payment import PaymentService
    from core.commands import TriggerPaymentCmd
    payment_svc: PaymentService = context.bot_data["payment_service"]
    result = await payment_svc.trigger(
        TriggerPaymentCmd(
            game_uuid=game_uuid,
            admin_id=update.effective_user.id,
            card_number=card_number,
        )
    )
    if not result.success:
        await update.message.reply_text(f"Error: {result.error_message}")
        return
    amount = result.data
    async with UnitOfWork() as uow:
        game = await uow.games.get_by_uuid(game_uuid)
        participants = await uow.participants.list_for_game(game.id)
    text = format_payment_board(game, participants, amount_per_player=amount, card_number=card_number)
    keyboard = payment_board_keyboard(game_uuid)
    sent = await update.message.reply_text(text, reply_markup=keyboard, parse_mode="Markdown")
    async with UnitOfWork() as uow:
        db_game = await uow.games.get_by_uuid(game_uuid)
        if db_game:
            db_game.payment_board_message_id = sent.message_id
    try:
        await context.bot.unpin_chat_message(chat_id=game.group_chat_id, message_id=game.announcement_message_id)
    except Exception as exc:
        logger.debug("Could not unpin announcement: %s", exc)
    try:
        await context.bot.pin_chat_message(chat_id=game.group_chat_id, message_id=sent.message_id)
    except Exception as exc:
        logger.debug("Could not pin payment board: %s", exc)


async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message or not update.message.photo or not update.effective_user:
        return
    participant_id = context.chat_data.get("awaiting_cheque_for_participant_id") if context.chat_data else None
    if not participant_id:
        return
    file_id = update.message.photo[-1].file_id
    payment_svc: PaymentService = context.bot_data["payment_service"]
    async with UnitOfWork() as uow:
        user = await uow.users.get_by_telegram_id(update.effective_user.id)
    if not user:
        return
    result = await payment_svc.upload_screenshot(
        UploadScreenshotCmd(participant_id=participant_id, user_id=user.id, file_id=file_id)
    )
    if not result.success:
        await update.message.reply_text(f"Error: {result.error_message}")
        return
    # Refresh board and show admin confirm button
    from bot.handlers.callbacks import _refresh_payment_board
    from bot.keyboards import admin_single_confirm_keyboard
    async with UnitOfWork() as uow:
        participant = await uow.participants.get_by_id(participant_id)
        game = await uow.games.get_by_id(participant.game_id) if participant else None
    if participant and game:
        await update.message.reply_text(
            "Thanks! Confirmation in process ✅",
            reply_markup=admin_single_confirm_keyboard(participant.id),
        )
        await _refresh_payment_board(context, game.game_uuid)
    context.chat_data.pop("awaiting_cheque_for_participant_id", None)


group_handlers = [
    newgame_conversation,
    CommandHandler("status", cmd_status, filters=filters.ChatType.GROUPS),
    CommandHandler("close", cmd_close, filters=filters.ChatType.GROUPS),
    CommandHandler("cancel", cmd_cancel_game, filters=filters.ChatType.GROUPS),
    CommandHandler("debt", cmd_debt, filters=filters.ChatType.GROUPS),
    CommandHandler("pay", cmd_trigger_payment, filters=filters.ChatType.GROUPS),
    MessageHandler(filters.PHOTO & filters.ChatType.GROUPS, handle_photo),
]
