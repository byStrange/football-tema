from __future__ import annotations

from typing import Any
from decimal import Decimal

from telegram import InlineKeyboardButton, InlineKeyboardMarkup


def game_announcement_keyboard(game_uuid: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("✅ Join", callback_data=f"join:{game_uuid}"),
                InlineKeyboardButton("❌ Decline", callback_data=f"decline:{game_uuid}"),
            ]
        ]
    )


def dm_payment_keyboard(participant_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("✅ I Paid", callback_data=f"paid:{participant_id}"),
            ],
            [
                InlineKeyboardButton("📷 Upload Screenshot", callback_data=f"screenshot:{participant_id}"),
            ],
        ]
    )


def payment_board_keyboard(game_uuid: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("💰 I Paid", callback_data=f"board_paid:{game_uuid}"),
            ]
        ]
    )


def admin_confirm_keyboard(participant_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("✅ Confirm", callback_data=f"confirm:{participant_id}"),
                InlineKeyboardButton("❌ Reject", callback_data=f"reject:{participant_id}"),
            ]
        ]
    )


def admin_single_confirm_keyboard(participant_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("✅ Confirm", callback_data=f"admin_confirm:{participant_id}"),
            ]
        ]
    )


def admin_game_controls_keyboard(game_uuid: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("💰 Start Payment", callback_data=f"trigger_payment:{game_uuid}"),
                InlineKeyboardButton("🔒 Close Game", callback_data=f"close_game:{game_uuid}"),
            ]
        ]
    )
