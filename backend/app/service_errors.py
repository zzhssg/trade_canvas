from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from fastapi import HTTPException


@dataclass(frozen=True)
class ServiceError(RuntimeError):
    status_code: int
    detail: Any
    code: str

    def __post_init__(self) -> None:
        RuntimeError.__init__(self, f"{self.code}:{self.status_code}")


def to_http_exception(error: ServiceError) -> HTTPException:
    return HTTPException(status_code=int(error.status_code), detail=error.detail)
