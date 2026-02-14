from __future__ import annotations

from contextlib import AbstractContextManager
from typing import Any, Protocol, TypeVar

from ..core.schemas import CandleClosed

ConnT = TypeVar("ConnT")
ConnCovT = TypeVar("ConnCovT", covariant=True)


class DbCursor(Protocol):
    rowcount: int

    def fetchone(self) -> Any: ...

    def fetchall(self) -> list[Any]: ...


class DbConnection(Protocol):
    def execute(self, sql: str, params: tuple[Any, ...] | list[Any] = ()) -> DbCursor: ...

    def commit(self) -> None: ...

    def rollback(self) -> None: ...

    def close(self) -> None: ...


class CandleRepository(Protocol[ConnT]):
    def connect(self) -> AbstractContextManager[ConnT]: ...

    def upsert_many_closed_in_conn(self, conn: ConnT, series_id: str, candles: list[CandleClosed]) -> None: ...

    def existing_closed_times_in_conn(self, conn: ConnT, *, series_id: str, candle_times: list[int]) -> set[int]: ...

    def delete_closed_times_in_conn(self, conn: ConnT, *, series_id: str, candle_times: list[int]) -> int: ...

    def head_time(self, series_id: str) -> int | None: ...

    def get_closed(self, series_id: str, *, since: int | None, limit: int) -> list[CandleClosed]: ...

    def get_closed_between_times(
        self,
        series_id: str,
        *,
        start_time: int,
        end_time: int,
        limit: int = 20000,
    ) -> list[CandleClosed]: ...


class FactorRepository(Protocol[ConnCovT]):
    def connect(self) -> AbstractContextManager[ConnCovT]: ...

    def head_time(self, series_id: str) -> int | None: ...


class OverlayRepository(Protocol[ConnCovT]):
    def connect(self) -> AbstractContextManager[ConnCovT]: ...

    def head_time(self, series_id: str) -> int | None: ...
