from __future__ import annotations

from typing import Generic, TypeVar

from pydantic import BaseModel

T = TypeVar("T")


class CommandResult(BaseModel, Generic[T]):
    success: bool
    data: T | None = None
    error_code: str | None = None
    error_message: str | None = None

    @classmethod
    def ok(cls, data: T | None = None) -> CommandResult[T]:
        return cls(success=True, data=data)

    @classmethod
    def fail(cls, code: str, message: str) -> CommandResult[T]:
        return cls(success=False, error_code=code, error_message=message)
