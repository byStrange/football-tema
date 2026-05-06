import logging
from typing import Any

from db.unit_of_work import UnitOfWork

logger = logging.getLogger(__name__)


class ScreenshotHandler:
    """Handles storing and retrieving Telegram screenshot receipts by file_id."""

    @staticmethod
    async def store_screenshot(participant_id: int, file_id: str) -> None:
        """Persist the Telegram ``file_id`` for a participant's payment screenshot."""
        async with UnitOfWork() as uow:
            participant = await uow.participants.get_by_id(participant_id)
            if participant is None:
                raise ValueError(f"Participant {participant_id} not found.")
            participant.screenshot_file_id = file_id

    @staticmethod
    async def get_screenshot_file_id(participant_id: int) -> str | None:
        """Return the stored Telegram ``file_id`` so the bot can re-send the photo."""
        async with UnitOfWork() as uow:
            participant = await uow.participants.get_by_id(participant_id)
            if participant is None:
                return None
            return getattr(participant, "screenshot_file_id", None)
