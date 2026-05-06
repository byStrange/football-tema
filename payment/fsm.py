from __future__ import annotations

from core.exceptions import InvalidStateTransition
from db.models import PaymentAction, PaymentStatus


class PaymentFSM:
    @staticmethod
    def can_initiate(status: PaymentStatus) -> bool:
        return status == PaymentStatus.not_paid

    @staticmethod
    def can_confirm(status: PaymentStatus) -> bool:
        return status == PaymentStatus.pending_confirmation

    @staticmethod
    def can_reject(status: PaymentStatus) -> bool:
        return status == PaymentStatus.pending_confirmation

    @staticmethod
    def transition(status: PaymentStatus, action: PaymentAction) -> PaymentStatus:
        if status == PaymentStatus.not_paid and action == PaymentAction.initiated:
            return PaymentStatus.pending_confirmation
        if status == PaymentStatus.pending_confirmation and action == PaymentAction.confirmed:
            return PaymentStatus.paid
        if status == PaymentStatus.pending_confirmation and action == PaymentAction.rejected:
            return PaymentStatus.not_paid
        raise InvalidStateTransition(f"Cannot transition from {status} via {action}")
