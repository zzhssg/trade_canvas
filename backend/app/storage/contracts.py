from __future__ import annotations

from typing import Any, Protocol

from ..core.schemas import CandleClosed


class CandleRepository(Protocol):
    def connect(self) -> Any: ...

    def upsert_many_closed_in_conn(self, conn: Any, series_id: str, candles: list[CandleClosed]) -> None: ...

    def existing_closed_times_in_conn(self, conn: Any, *, series_id: str, candle_times: list[int]) -> set[int]: ...

    def delete_closed_times_in_conn(self, conn: Any, *, series_id: str, candle_times: list[int]) -> int: ...

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


class FactorRepository(Protocol):
    def connect(self) -> Any: ...

    def head_time(self, series_id: str) -> int | None: ...


class OverlayRepository(Protocol):
    def connect(self) -> Any: ...

    def head_time(self, series_id: str) -> int | None: ...
