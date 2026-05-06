from __future__ import annotations

from telegram import Update
from telegram.ext import Application, TypeHandler

from config import config as bot_config
from db.session import create_tables
from core.events import EventBus, PlayerJoined, PlayerLeft, PaymentInitiated, PaymentConfirmed, PaymentRejected, GamePaymentOpened, GameClosed
from core.services.game import GameService
from core.services.player import PlayerService
from core.services.payment import PaymentService
from core.services.debt import DebtService
from core.services.notification import NotificationService
from notifications.scheduler import start_scheduler

from bot.handlers.callbacks import callback_router
from bot.handlers.group import group_handlers
from bot.handlers.private import private_handlers
from bot.middleware import user_registration_middleware


class _BotMessageSender:
    """Adapter wrapping telegram.ext.ExtBot for the NotificationService."""

    def __init__(self, bot) -> None:
        self._bot = bot

    async def send_message(self, chat_id: int, text: str) -> None:
        await self._bot.send_message(chat_id=chat_id, text=text)

    async def edit_message(self, chat_id: int, message_id: int, text: str) -> None:
        await self._bot.edit_message_text(chat_id=chat_id, message_id=message_id, text=text)

    async def send_photo(self, chat_id: int, photo: str, caption: str | None = None) -> None:
        await self._bot.send_photo(chat_id=chat_id, photo=photo, caption=caption)


def build_application() -> Application:
    application = (
        Application.builder()
        .token(bot_config.TELEGRAM_BOT_TOKEN)
        .build()
    )

    # Wire services
    event_bus = EventBus()
    debt_service = DebtService()
    payment_service = PaymentService(event_bus, debt_service)
    player_service = PlayerService(event_bus)
    game_service = GameService(event_bus)

    message_sender = _BotMessageSender(application.bot)
    notification_service = NotificationService(message_sender)

    # Wire notification consumers to event bus
    event_bus.subscribe(PlayerJoined, notification_service.on_player_joined)
    event_bus.subscribe(PlayerLeft, notification_service.on_player_left)
    event_bus.subscribe(PaymentInitiated, notification_service.on_payment_initiated)
    event_bus.subscribe(PaymentConfirmed, notification_service.on_payment_confirmed)
    event_bus.subscribe(PaymentRejected, notification_service.on_payment_rejected)
    event_bus.subscribe(GamePaymentOpened, notification_service.on_game_payment_opened)
    event_bus.subscribe(GameClosed, notification_service.on_game_closed)

    application.bot_data["event_bus"] = event_bus
    application.bot_data["debt_service"] = debt_service
    application.bot_data["payment_service"] = payment_service
    application.bot_data["player_service"] = player_service
    application.bot_data["game_service"] = game_service
    application.bot_data["notification_service"] = notification_service

    # Register handlers (group handlers first so ConversationHandler catches /newgame)
    for handler in group_handlers:
        application.add_handler(handler)
    for handler in private_handlers:
        application.add_handler(handler)
    application.add_handler(callback_router)

    # Middleware runs on all updates before regular handlers
    async def _middleware(update: Update, context) -> None:
        await user_registration_middleware(update, context)

    application.add_handler(TypeHandler(Update, _middleware), group=-1)

    # Startup / shutdown
    async def _startup(app: Application) -> None:
        await create_tables()
        start_scheduler(app.bot, notification_service)

    async def _shutdown(app: Application) -> None:
        pass

    application.post_init = _startup
    application.post_shutdown = _shutdown
    return application


if __name__ == "__main__":
    import logging

    logging.basicConfig(level=bot_config.LOG_LEVEL)
    app = build_application()
    app.run_polling(allowed_updates=Update.ALL_TYPES)
