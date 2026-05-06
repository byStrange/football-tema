from __future__ import annotations

import enum
from datetime import datetime
from decimal import Decimal
from typing import List
from uuid import uuid4

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Numeric,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class GameStatus(str, enum.Enum):
    announced = "announced"
    payment_open = "payment_open"
    completed = "completed"
    cancelled = "cancelled"


class PaymentStatus(str, enum.Enum):
    not_paid = "not_paid"
    waiting_for_cheque = "waiting_for_cheque"
    pending_confirmation = "pending_confirmation"
    paid = "paid"


class PaymentAction(str, enum.Enum):
    initiated = "initiated"
    confirmed = "confirmed"
    rejected = "rejected"


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    telegram_id: Mapped[int] = mapped_column(BigInteger, unique=True, nullable=False)
    chat_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    username: Mapped[str | None] = mapped_column(String(255), nullable=True)
    first_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    last_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    games: Mapped[List["Participant"]] = relationship(
        "Participant", back_populates="user", foreign_keys="Participant.user_id"
    )
    balances: Mapped[List["UserBalance"]] = relationship(back_populates="user")


class Game(Base):
    __tablename__ = "games"

    id: Mapped[int] = mapped_column(primary_key=True)
    game_uuid: Mapped[str] = mapped_column(
        String(36), unique=True, nullable=False, default=lambda: str(uuid4())
    )
    admin_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    location: Mapped[str] = mapped_column(String(500), nullable=False)
    scheduled_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    total_cost: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), nullable=True)
    cost_per_player: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), nullable=True)
    max_players: Mapped[int | None] = mapped_column(nullable=True)
    status: Mapped[GameStatus] = mapped_column(
        default=GameStatus.announced
    )
    group_chat_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    announcement_message_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    payment_message_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    payment_board_message_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    participants: Mapped[List["Participant"]] = relationship(
        back_populates="game", cascade="all, delete-orphan"
    )

    __table_args__ = (
        CheckConstraint(
            "(total_cost IS NOT NULL) OR (cost_per_player IS NOT NULL)",
            name="ck_games_cost",
        ),
    )


class Participant(Base):
    __tablename__ = "participants"
    __table_args__ = (
        UniqueConstraint("game_id", "user_id", name="uq_participants_game_user"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    game_id: Mapped[int] = mapped_column(ForeignKey("games.id"), nullable=False)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    joined_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    payment_status: Mapped[PaymentStatus] = mapped_column(
        default=PaymentStatus.not_paid
    )
    amount_due: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), nullable=True)
    confirmed_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    screenshot_file_id: Mapped[str | None] = mapped_column(String(500), nullable=True)
    is_manual_add: Mapped[bool] = mapped_column(Boolean, default=False)

    game: Mapped["Game"] = relationship(back_populates="participants")
    user: Mapped["User"] = relationship(
        "User", foreign_keys=[user_id], back_populates="games"
    )
    payment_records: Mapped[List["Payment"]] = relationship(
        back_populates="participant", cascade="all, delete-orphan"
    )


class Payment(Base):
    __tablename__ = "payments"

    id: Mapped[int] = mapped_column(primary_key=True)
    participant_id: Mapped[int] = mapped_column(
        ForeignKey("participants.id"), nullable=False
    )
    action: Mapped[PaymentAction] = mapped_column(nullable=False)
    actor_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    notes: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    participant: Mapped["Participant"] = relationship(back_populates="payment_records")


class UserBalance(Base):
    __tablename__ = "user_balances"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), unique=True, nullable=False)
    amount_owed: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=Decimal("0.00"))
    last_updated: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    user: Mapped["User"] = relationship(back_populates="balances")
