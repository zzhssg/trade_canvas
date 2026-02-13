from __future__ import annotations

from typing import Any

from ..schemas import CandleClosed
from ..store import CandleStore


class DualWriteCandleRepository(CandleStore):
    def __init__(
        self,
        *,
        primary: CandleStore,
        mirror: Any | None = None,
        enable_dual_write: bool = False,
        enable_pg_read: bool = False,
    ) -> None:
        super().__init__(db_path=primary.db_path)
        object.__setattr__(self, "_primary", primary)
        object.__setattr__(self, "_mirror", mirror)
        object.__setattr__(self, "_enable_dual_write", bool(enable_dual_write))
        object.__setattr__(self, "_enable_pg_read", bool(enable_pg_read))

    @property
    def _read_backend(self) -> Any:
        mirror = getattr(self, "_mirror")
        if mirror is not None and bool(getattr(self, "_enable_pg_read")):
            return mirror
        return getattr(self, "_primary")

    @property
    def primary_repository(self) -> CandleStore:
        return getattr(self, "_primary")

    @property
    def mirror_repository(self) -> Any | None:
        return getattr(self, "_mirror")

    @property
    def dual_write_enabled(self) -> bool:
        return bool(getattr(self, "_enable_dual_write"))

    @property
    def pg_read_enabled(self) -> bool:
        return bool(getattr(self, "_enable_pg_read"))

    def _mirror_write(self, method: str, *args: Any, **kwargs: Any) -> None:
        mirror = getattr(self, "_mirror")
        if mirror is None:
            return
        if not bool(getattr(self, "_enable_dual_write")):
            return
        fn = getattr(mirror, method)
        fn(*args, **kwargs)

    def connect(self):  # type: ignore[override]
        return getattr(self, "_primary").connect()

    def upsert_closed_in_conn(self, conn: Any, series_id: str, candle: CandleClosed) -> None:  # type: ignore[override]
        getattr(self, "_primary").upsert_closed_in_conn(conn, series_id, candle)
        self._mirror_write("upsert_closed", series_id, candle)

    def upsert_many_closed_in_conn(self, conn: Any, series_id: str, candles: list[CandleClosed]) -> None:  # type: ignore[override]
        getattr(self, "_primary").upsert_many_closed_in_conn(conn, series_id, candles)
        self._mirror_write("upsert_many_closed", series_id, candles)

    def existing_closed_times_in_conn(self, conn: Any, *, series_id: str, candle_times: list[int]) -> set[int]:  # type: ignore[override]
        return getattr(self, "_primary").existing_closed_times_in_conn(
            conn,
            series_id=series_id,
            candle_times=candle_times,
        )

    def delete_closed_times_in_conn(self, conn: Any, *, series_id: str, candle_times: list[int]) -> int:  # type: ignore[override]
        deleted = int(
            getattr(self, "_primary").delete_closed_times_in_conn(
                conn,
                series_id=series_id,
                candle_times=candle_times,
            )
        )
        self._mirror_write("delete_closed_times", series_id=series_id, candle_times=candle_times)
        return deleted

    def upsert_closed(self, series_id: str, candle: CandleClosed) -> None:  # type: ignore[override]
        getattr(self, "_primary").upsert_closed(series_id, candle)
        self._mirror_write("upsert_closed", series_id, candle)

    def upsert_many_closed(self, series_id: str, candles: list[CandleClosed]) -> None:
        with self.connect() as conn:
            self.upsert_many_closed_in_conn(conn, series_id, candles)
            conn.commit()

    def delete_closed_times(self, *, series_id: str, candle_times: list[int]) -> int:
        with self.connect() as conn:
            deleted = self.delete_closed_times_in_conn(
                conn,
                series_id=series_id,
                candle_times=candle_times,
            )
            conn.commit()
        return int(deleted)

    def head_time(self, series_id: str) -> int | None:  # type: ignore[override]
        return self._read_backend.head_time(series_id)

    def first_time(self, series_id: str) -> int | None:  # type: ignore[override]
        return self._read_backend.first_time(series_id)

    def count_closed_between_times(self, series_id: str, *, start_time: int, end_time: int) -> int:  # type: ignore[override]
        return int(
            self._read_backend.count_closed_between_times(
                series_id,
                start_time=int(start_time),
                end_time=int(end_time),
            )
        )

    def trim_series_to_latest_n_in_conn(self, conn: Any, *, series_id: str, keep: int) -> int:  # type: ignore[override]
        trimmed = int(
            getattr(self, "_primary").trim_series_to_latest_n_in_conn(
                conn,
                series_id=series_id,
                keep=int(keep),
            )
        )
        self._mirror_write("trim_series_to_latest_n", series_id=series_id, keep=int(keep))
        return trimmed

    def trim_series_to_latest_n(self, *, series_id: str, keep: int) -> int:
        with self.connect() as conn:
            trimmed = self.trim_series_to_latest_n_in_conn(conn, series_id=series_id, keep=int(keep))
            conn.commit()
        return int(trimmed)

    def floor_time(self, series_id: str, *, at_time: int) -> int | None:  # type: ignore[override]
        return self._read_backend.floor_time(series_id, at_time=int(at_time))

    def get_closed(self, series_id: str, *, since: int | None, limit: int):  # type: ignore[override]
        return self._read_backend.get_closed(series_id, since=since, limit=int(limit))

    def get_closed_between_times(
        self,
        series_id: str,
        *,
        start_time: int,
        end_time: int,
        limit: int = 20000,
    ):  # type: ignore[override]
        return self._read_backend.get_closed_between_times(
            series_id,
            start_time=int(start_time),
            end_time=int(end_time),
            limit=int(limit),
        )
