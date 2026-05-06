import asyncio
import os

import pytest
import pytest_asyncio

# Force tests to use a temp SQLite DB before any module imports create the engine
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///./tests/test.db")
os.environ.setdefault("TELEGRAM_BOT_TOKEN", "test-token")

from decimal import Decimal
from datetime import datetime, timedelta

from core.commands import CreateGameCmd, JoinGameCmd, LeaveGameCmd, TriggerPaymentCmd, PlayerPaidCmd, ConfirmPaymentCmd
from core.events import EventBus
from core.services.game import GameService
from core.services.player import PlayerService
from core.services.payment import PaymentService
from core.services.debt import DebtService
from db.session import create_tables, engine
from db.unit_of_work import UnitOfWork
from db.models import GameStatus, PaymentStatus


@pytest_asyncio.fixture(autouse=True)
async def setup_db():
    """Create tables before each test and drop after."""
    await create_tables()
    yield
    from db.models import Base
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest.fixture
def event_bus():
    return EventBus()


@pytest.fixture
def debt_service():
    return DebtService()


@pytest.fixture
def game_service(event_bus):
    return GameService(event_bus)


@pytest.fixture
def player_service(event_bus):
    return PlayerService(event_bus)


@pytest.fixture
def payment_service(event_bus, debt_service):
    return PaymentService(event_bus, debt_service)


@pytest.mark.asyncio
async def test_create_game(game_service):
    async with UnitOfWork() as uow:
        admin = await uow.users.create(telegram_id=1, chat_id=1)
    cmd = CreateGameCmd(
        admin_id=1,
        location="Pitch A",
        scheduled_at=datetime.utcnow() + timedelta(days=1),
        total_cost=Decimal("100.00"),
        max_players=10,
        group_chat_id=-100123,
    )
    result = await game_service.create_game(cmd)
    assert result.success is True
    assert result.data is not None
    assert result.data.location == "Pitch A"
    assert result.data.status == GameStatus.announced


@pytest.mark.asyncio
async def test_join_and_leave(game_service, player_service):
    async with UnitOfWork() as uow:
        admin = await uow.users.create(telegram_id=1, chat_id=1)
    cmd = CreateGameCmd(
        admin_id=1,
        location="Pitch B",
        scheduled_at=datetime.utcnow() + timedelta(days=1),
        cost_per_player=Decimal("10.00"),
        group_chat_id=-100123,
    )
    r = await game_service.create_game(cmd)
    game = r.data

    j = await player_service.join(JoinGameCmd(game_uuid=game.game_uuid, user_id=100, chat_id=100))
    assert j.success is True
    assert j.data is not None
    assert j.data.payment_status == PaymentStatus.not_paid

    # Idempotent join
    j2 = await player_service.join(JoinGameCmd(game_uuid=game.game_uuid, user_id=100, chat_id=100))
    assert j2.success is True

    l = await player_service.leave(LeaveGameCmd(game_uuid=game.game_uuid, user_id=100))
    assert l.success is True


@pytest.mark.asyncio
async def test_payment_flow(game_service, player_service, payment_service, debt_service):
    async with UnitOfWork() as uow:
        admin = await uow.users.create(telegram_id=1, chat_id=1)
        p1 = await uow.users.create(telegram_id=100, chat_id=100)

    cmd = CreateGameCmd(
        admin_id=1,
        location="Pitch C",
        scheduled_at=datetime.utcnow() + timedelta(days=1),
        total_cost=Decimal("60.00"),
        group_chat_id=-100123,
    )
    r = await game_service.create_game(cmd)
    game = r.data

    await player_service.join(JoinGameCmd(game_uuid=game.game_uuid, user_id=100, chat_id=100))

    t = await payment_service.trigger(TriggerPaymentCmd(game_uuid=game.game_uuid, admin_id=1, card_number="1234"))
    assert t.success is True
    assert t.data == Decimal("60.00")

    async with UnitOfWork() as uow:
        participant = await uow.participants.list_for_game(game.id)
    assert participant[0].amount_due == Decimal("60.00")

    pid = participant[0].id
    pp = await payment_service.player_paid(PlayerPaidCmd(participant_id=pid, user_id=100))
    assert pp.success is True

    async with UnitOfWork() as uow:
        p = await uow.participants.get_by_id(pid)
    assert p.payment_status == PaymentStatus.pending_confirmation

    cp = await payment_service.confirm(ConfirmPaymentCmd(participant_id=pid, admin_id=1, approved=True))
    assert cp.success is True

    async with UnitOfWork() as uow:
        p = await uow.participants.get_by_id(pid)
    assert p.payment_status == PaymentStatus.paid

    bal = await debt_service.get_balance(p1.id)
    assert bal == Decimal("0.00")


@pytest.mark.asyncio
async def test_game_full(game_service, player_service):
    async with UnitOfWork() as uow:
        admin = await uow.users.create(telegram_id=1, chat_id=1)

    cmd = CreateGameCmd(
        admin_id=1,
        location="Pitch D",
        scheduled_at=datetime.utcnow() + timedelta(days=1),
        cost_per_player=Decimal("5.00"),
        max_players=1,
        group_chat_id=-100123,
    )
    r = await game_service.create_game(cmd)
    game = r.data

    j1 = await player_service.join(JoinGameCmd(game_uuid=game.game_uuid, user_id=100, chat_id=100))
    assert j1.success is True

    j2 = await player_service.join(JoinGameCmd(game_uuid=game.game_uuid, user_id=101, chat_id=101))
    assert j2.success is False
    assert j2.error_code == "GAME_FULL"
