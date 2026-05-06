from __future__ import annotations

import os
from dataclasses import dataclass, field
from dotenv import load_dotenv

load_dotenv()


def _parse_int_list(value: str | None) -> list[int]:
    if not value:
        return []
    return [int(x.strip()) for x in value.split(",") if x.strip().isdigit()]


@dataclass(frozen=True)
class Config:
    TELEGRAM_BOT_TOKEN: str = field(default_factory=lambda: os.getenv("TELEGRAM_BOT_TOKEN", ""))
    DATABASE_URL: str = field(
        default_factory=lambda: os.getenv("DATABASE_URL", "sqlite+aiosqlite:///./football.db")
    )
    REMINDER_INTERVAL_HOURS: int = field(
        default_factory=lambda: int(os.getenv("REMINDER_INTERVAL_HOURS", "24"))
    )
    NUDGE_INTERVAL_HOURS: int = field(
        default_factory=lambda: int(os.getenv("NUDGE_INTERVAL_HOURS", "48"))
    )
    ADMIN_TELEGRAM_IDS: list[int] = field(
        default_factory=lambda: _parse_int_list(os.getenv("ADMIN_TELEGRAM_IDS"))
    )
    LOG_LEVEL: str = field(default_factory=lambda: os.getenv("LOG_LEVEL", "INFO"))

    def is_admin(self, telegram_id: int) -> bool:
        return telegram_id in self.ADMIN_TELEGRAM_IDS


config = Config()
