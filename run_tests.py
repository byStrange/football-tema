import asyncio
from decimal import Decimal
from datetime import datetime, timedelta

from db.session import create_tables, engine
from db.unit_of_work import UnitOfWork
from db.models import Base, GameStatus, PaymentStatus
from core.events import EventBus
from core.services.game import GameService
from core.services.player import PlayerService
from core.services.payment import PaymentService
from core.services.debt import DebtService
from core.commands import (
    CreateGameCmd,
    JoinGameCmd,
    LeaveGameCmd,
    TriggerPaymentCmd,
    PlayerPaidCmd,
    ConfirmPaymentCmd,
)


async def setup_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def teardown_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


async def test_create_game(event_bus):
    svc = GameService(event_bus)
    async with UnitOfWork() as uow:
        await uow.users.create(telegram_id=1, chat_id=1)
    cmd = CreateGameCmd(
        admin_id=1,
        location="Pitch A",
        scheduled_at=datetime.utcnow() + timedelta(days=1),
        total_cost=Decimal("100.00"),
        max_players=10,
        group_chat_id=-100123,
    )
    result = await svc.create_game(cmd)
    assert result.success is True
    assert result.data is not None
    assert result.data.location == "Pitch A"
    assert result.data.status == GameStatus.announced
    print("PASS test_create_game")


async def test_join_and_leave(event_bus):
    game_svc = GameService(event_bus)
    player_svc = PlayerService(event_bus)
    async with UnitOfWork() as uow:
        await uow.users.create(telegram_id=1, chat_id=1)
    cmd = CreateGameCmd(
        admin_id=1,
        location="Pitch B",
        scheduled_at=datetime.utcnow() + timedelta(days=1),
        cost_per_player=Decimal("10.00"),
        group_chat_id=-100123,
    )
    r = await game_svc.create_game(cmd)
    game = r.data

    j = await player_svc.join(JoinGameCmd(game_uuid=game.game_uuid, user_id=100, chat_id=100))
    assert j.success is True
    assert j.data is not None
    assert j.data.payment_status == PaymentStatus.not_paid

    j2 = await player_svc.join(JoinGameCmd(game_uuid=game.game_uuid, user_id=100, chat_id=100))
    assert j2.success is True

    l = await player_svc.leave(LeaveGameCmd(game_uuid=game.game_uuid, user_id=100))
    assert l.success is True
    print("PASS test_join_and_leave")


async def test_payment_flow(event_bus):
    game_svc = GameService(event_bus)
    player_svc = PlayerService(event_bus)
    debt_svc = DebtService()
    payment_svc = PaymentService(event_bus, debt_svc)

    async with UnitOfWork() as uow:
        await uow.users.create(telegram_id=1, chat_id=1)
        p1 = await uow.users.create(telegram_id=100, chat_id=100)

    cmd = CreateGameCmd(
        admin_id=1,
        location="Pitch C",
        scheduled_at=datetime.utcnow() + timedelta(days=1),
        total_cost=Decimal("60.00"),
        group_chat_id=-100123,
    )
    r = await game_svc.create_game(cmd)
    game = r.data

    await player_svc.join(JoinGameCmd(game_uuid=game.game_uuid, user_id=100, chat_id=100))

    t = await payment_svc.trigger(TriggerPaymentCmd(game_uuid=game.game_uuid, admin_id=1, card_number="1234"))
    assert t.success is True
    assert t.data == Decimal("60.00")

    async with UnitOfWork() as uow:
        participant = await uow.participants.list_for_game(game.id)
    assert participant[0].amount_due == Decimal("60.00")

    pid = participant[0].id
    pp = await payment_svc.player_paid(PlayerPaidCmd(participant_id=pid, user_id=100))
    assert pp.success is True

    async with UnitOfWork() as uow:
        p = await uow.participants.get_by_id(pid)
    assert p.payment_status == PaymentStatus.waiting_for_cheque

    # Upload screenshot transitions to pending_confirmation
    from core.commands import UploadScreenshotCmd
    ss = await payment_svc.upload_screenshot(UploadScreenshotCmd(participant_id=pid, user_id=100, file_id="fake_file_id"))
    assert ss.success is True

    async with UnitOfWork() as uow:
        p = await uow.participants.get_by_id(pid)
    assert p.payment_status == PaymentStatus.pending_confirmation

    cp = await payment_svc.confirm(ConfirmPaymentCmd(participant_id=pid, admin_id=1, approved=True))
    assert cp.success is True

    async with UnitOfWork() as uow:
        p = await uow.participants.get_by_id(pid)
    assert p.payment_status == PaymentStatus.paid

    bal = await debt_svc.get_balance(p1.id)
    assert bal == Decimal("0.00")
    print("PASS test_payment_flow")


async def test_game_full(event_bus):
    game_svc = GameService(event_bus)
    player_svc = PlayerService(event_bus)
    async with UnitOfWork() as uow:
        await uow.users.create(telegram_id=1, chat_id=1)

    cmd = CreateGameCmd(
        admin_id=1,
        location="Pitch D",
        scheduled_at=datetime.utcnow() + timedelta(days=1),
        cost_per_player=Decimal("5.00"),
        max_players=1,
        group_chat_id=-100123,
    )
    r = await game_svc.create_game(cmd)
    game = r.data

    j1 = await player_svc.join(JoinGameCmd(game_uuid=game.game_uuid, user_id=100, chat_id=100))
    assert j1.success is True

    j2 = await player_svc.join(JoinGameCmd(game_uuid=game.game_uuid, user_id=101, chat_id=101))
    assert j2.success is False
    assert j2.error_code == "GAME_FULL"
    print("PASS test_game_full")


async def main():
    await setup_db()
    event_bus = EventBus()
    try:
        await test_create_game(event_bus)
        await teardown_db()
        await setup_db()

        await test_join_and_leave(event_bus)
        await teardown_db()
        await setup_db()

        await test_payment_flow(event_bus)
        await teardown_db()
        await setup_db()

        await test_game_full(event_bus)
    finally:
        await teardown_db()
    print("\nALL TESTS PASSED")


if __name__ == "__main__":
    asyncio.run(main())
