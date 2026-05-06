from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from core.commands import ConfirmPaymentCmd, PlayerPaidCmd, TriggerPaymentCmd, UploadScreenshotCmd
from core.events import EventBus, GamePaymentOpened, PaymentConfirmed, PaymentInitiated, PaymentRejected
from core.exceptions import GameNotFound, InvalidStateTransition, NotAuthorized
from core.results import CommandResult
from core.services.debt import DebtService
from db.models import GameStatus, PaymentAction, PaymentStatus
from db.unit_of_work import UnitOfWork
from payment.calculator import PaymentCalculator
from payment.fsm import PaymentFSM


class PaymentService:
    def __init__(self, event_bus: EventBus, debt_service: DebtService) -> None:
        self._event_bus = event_bus
        self._debt_service = debt_service

    async def trigger(self, cmd: TriggerPaymentCmd) -> CommandResult[Decimal]:
        async with UnitOfWork() as uow:
            game = await uow.games.get_by_uuid(cmd.game_uuid)
            if game is None:
                return CommandResult.fail("GAME_NOT_FOUND", "Game not found.")
            admin = await uow.users.get_by_telegram_id(cmd.admin_id)
            if admin is None or game.admin_id != admin.id:
                return CommandResult.fail("NOT_AUTHORIZED", "Only admin can trigger payments.")

            participants = await uow.participants.list_for_game(game.id)
            if not participants:
                return CommandResult.fail("NO_PARTICIPANTS", "No participants in game.")

            amount_per_player = PaymentCalculator.calculate_per_player(game, len(participants))

            for p in participants:
                await uow.participants.update_amount_due(p.id, amount_per_player)

            game.status = GameStatus.payment_open

            await self._event_bus.publish(
                GamePaymentOpened(
                    game_uuid=cmd.game_uuid,
                    card_number=cmd.card_number,
                    amount_per_player=amount_per_player,
                )
            )
            return CommandResult.ok(amount_per_player)

    async def player_paid(self, cmd: PlayerPaidCmd) -> CommandResult[None]:
        async with UnitOfWork() as uow:
            participant = await uow.participants.get_by_id(cmd.participant_id)
            if participant is None:
                return CommandResult.fail("PARTICIPANT_NOT_FOUND", "Participant not found.")

            if participant.payment_status in (
                PaymentStatus.waiting_for_cheque,
                PaymentStatus.pending_confirmation,
                PaymentStatus.paid,
            ):
                return CommandResult.ok(None)

            if not PaymentFSM.can_initiate(participant.payment_status):
                return CommandResult.fail("INVALID_STATE", "Cannot initiate payment from current state.")

            new_status = PaymentFSM.transition(participant.payment_status, PaymentAction.initiated)
            await uow.participants.update_status(participant.id, new_status)

            await uow.payments.create(
                participant_id=participant.id,
                user_id=participant.user_id,
                action=PaymentAction.initiated,
                amount=participant.amount_due,
            )

            game = await uow.games.get_by_id(participant.game_id)
            await self._event_bus.publish(
                PaymentInitiated(
                    game_uuid=game.game_uuid if game else "",
                    user_id=cmd.user_id,
                    amount=participant.amount_due,
                )
            )
            return CommandResult.ok(None)

    async def upload_screenshot(self, cmd: UploadScreenshotCmd) -> CommandResult[None]:
        async with UnitOfWork() as uow:
            participant = await uow.participants.get_by_id(cmd.participant_id)
            if participant is None:
                return CommandResult.fail("PARTICIPANT_NOT_FOUND", "Participant not found.")
            user = await uow.users.get_by_telegram_id(cmd.user_id)
            if user is None or participant.user_id != user.id:
                return CommandResult.fail("NOT_AUTHORIZED", "Cannot upload screenshot for another user.")

            participant.screenshot_file_id = cmd.file_id

            if participant.payment_status == PaymentStatus.waiting_for_cheque:
                new_status = PaymentFSM.transition(participant.payment_status, PaymentAction.initiated)
                await uow.participants.update_status(participant.id, new_status)

            return CommandResult.ok(None)

    async def confirm(self, cmd: ConfirmPaymentCmd) -> CommandResult[None]:
        async with UnitOfWork() as uow:
            participant = await uow.participants.get_by_id(cmd.participant_id)
            if participant is None:
                return CommandResult.fail("PARTICIPANT_NOT_FOUND", "Participant not found.")

            if cmd.approved:
                if not PaymentFSM.can_confirm(participant.payment_status):
                    return CommandResult.fail("INVALID_STATE", "Cannot confirm payment from current state.")

                new_status = PaymentFSM.transition(participant.payment_status, PaymentAction.confirmed)
                await uow.participants.update_status(participant.id, new_status)
                participant.confirmed_by = cmd.admin_id
                participant.confirmed_at = datetime.utcnow()

                await uow.payments.create(
                    participant_id=participant.id,
                    user_id=participant.user_id,
                    action=PaymentAction.confirmed,
                    amount=participant.amount_due,
                )

                await self._debt_service.record_credit(
                    participant.user_id, participant.amount_due, uow=uow
                )

                game = await uow.games.get_by_id(participant.game_id)
                await self._event_bus.publish(
                    PaymentConfirmed(
                        game_uuid=game.game_uuid if game else "",
                        user_id=participant.user_id,
                        amount=participant.amount_due,
                        admin_id=cmd.admin_id,
                    )
                )
            else:
                if not PaymentFSM.can_reject(participant.payment_status):
                    return CommandResult.fail("INVALID_STATE", "Cannot reject payment from current state.")

                new_status = PaymentFSM.transition(participant.payment_status, PaymentAction.rejected)
                await uow.participants.update_status(participant.id, new_status)

                await uow.payments.create(
                    participant_id=participant.id,
                    user_id=participant.user_id,
                    action=PaymentAction.rejected,
                    amount=participant.amount_due,
                )

                game = await uow.games.get_by_id(participant.game_id)
                await self._event_bus.publish(
                    PaymentRejected(
                        game_uuid=game.game_uuid if game else "",
                        user_id=participant.user_id,
                        reason=cmd.reason,
                    )
                )

            return CommandResult.ok(None)
