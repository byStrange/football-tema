from __future__ import annotations

from decimal import Decimal
from typing import Any


def escape_md(text: str) -> str:
    """Escape markdown v1 special characters."""
    chars = ["_", "*", "[", "]", "(", ")", "~", "`", ">", "#", "+", "-", "=", "|", "{", "}", ".", "!"]
    for ch in chars:
        text = text.replace(ch, f"\\{ch}")
    return text


def format_game_announcement(game: Any, participants: list[Any], amount_per_player: Decimal | None = None) -> str:
    lines = [
        f"📍 *{escape_md(game.location)}*",
        f"🗓 {escape_md(str(game.scheduled_at))}",
    ]
    if game.max_players:
        lines.append(f"👥 Max players: *{game.max_players}*")
    if amount_per_player:
        lines.append(f"💰 Amount per player: *{amount_per_player}*")
    lines.append("")
    if participants:
        lines.append(f"Players ({len(participants)}):")
        for p in participants:
            user = getattr(p, "user", None)
            name = escape_md(user.first_name or user.username or "Player") if user else "Player"
            lines.append(f"• {name}")
    else:
        lines.append("No players yet. Tap ✅ Join!")
    return "\n".join(lines)


def format_payment_instructions(game: Any, amount_per_player: Decimal, card_number: str) -> str:
    return (
        f"💳 Payment instructions for game *{escape_md(str(game.game_uuid))}*\n\n"
        f"Amount per player: *{escape_md(str(amount_per_player))}*\n"
        f"Card number: `{escape_md(card_number)}`\n\n"
        f"Please check your DMs to confirm payment."
    )


def format_dm_payment_prompt(game: Any, amount: Decimal) -> str:
    return (
        f"You owe *{escape_md(str(amount))}* for game at *{escape_md(game.location)}* "
        f"on {escape_md(str(game.scheduled_at))}.\n\n"
        f"Transfer the money, then tap ✅ *I Paid*."
    )


def format_group_payment_summary(game: Any, participants: list[Any]) -> str:
    paid = [p for p in participants if getattr(p, "payment_status", None) == "paid"]
    pending = [p for p in participants if getattr(p, "payment_status", None) == "pending_confirmation"]
    not_paid = [p for p in participants if getattr(p, "payment_status", None) == "not_paid"]

    total_due = sum((getattr(p, "amount_due", None) or Decimal("0") for p in participants), Decimal("0"))
    collected = sum((getattr(p, "amount_due", None) or Decimal("0") for p in paid), Decimal("0"))

    lines = [f"📊 Payment summary for game *{escape_md(str(game.game_uuid))}*:"]
    lines.append(f"✅ Paid: {len(paid)}   ⏳ Pending: {len(pending)}   ❌ Not paid: {len(not_paid)}")
    lines.append(f"💰 Total due: *{escape_md(str(total_due))}* | Collected: *{escape_md(str(collected))}*")
    return "\n".join(lines)


def format_debt_summary(balance: Decimal) -> str:
    if balance > 0:
        return f"You currently owe *{escape_md(str(balance))}* across games."
    return "You are all settled up. Great job!"


def format_admin_pending_list(participants: list[Any]) -> str:
    lines = ["Pending payments to confirm:"]
    for p in participants:
        user = getattr(p, "user", None)
        name = escape_md(user.first_name or user.username or "Player") if user else "Player"
        lines.append(f"• {name} — {getattr(p, 'amount_due', 'N/A')}")
    return "\n".join(lines)
