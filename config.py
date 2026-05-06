from __future__ import annotations

import os
from dataclasses import dataclass, field
from dotenv import load_dotenv

load_dotenv()


def _parse_int_list(value: str | None) -> list[int]:
    if not value:
        return []
    return [int(x.strip()) for x in value.split(",") if x.strip().isdigit()]


def _resolve_db_url(url: str) -> str:
    """Make relative SQLite paths absolute so the DB file is always in the project root."""
    if not url.startswith("sqlite"):
        return url
    try:
        from urllib.parse import urlparse
        parsed = urlparse(url)
        path = parsed.path
        if not path or path.startswith("/"):
            return url  # already absolute or memory DB
        # Resolve relative to project root (directory containing config.py)
        root = os.path.dirname(os.path.abspath(__file__))
        abs_path = os.path.normpath(os.path.join(root, path))
        return f"{parsed.scheme}://{abs_path}"
    except Exception:
        return url


@dataclass(frozen=True)
class Config:
    TELEGRAM_BOT_TOKEN: str = field(default_factory=lambda: os.getenv("TELEGRAM_BOT_TOKEN", ""))
    DATABASE_URL: str = field(
        default_factory=lambda: _resolve_db_url(os.getenv("DATABASE_URL", "sqlite+aiosqlite:///./football.db"))
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
