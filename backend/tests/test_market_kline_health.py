from __future__ import annotations

from backend.app.market.kline_health import analyze_series_health
from backend.app.schemas import CandleClosed


def _candle(t: int, price: float) -> CandleClosed:
    return CandleClosed(
        candle_time=int(t),
        open=float(price),
        high=float(price),
        low=float(price),
        close=float(price),
        volume=1.0,
    )


class _StoreWithoutConnect:
    def __init__(self) -> None:
        self._rows: dict[str, list[CandleClosed]] = {}

    def seed(self, *, series_id: str, candle_times: list[int]) -> None:
        self._rows[series_id] = [_candle(t, float(idx + 1)) for idx, t in enumerate(sorted(candle_times))]

    def _series(self, series_id: str) -> list[CandleClosed]:
        return list(self._rows.get(series_id, ()))

    def first_time(self, series_id: str) -> int | None:
        rows = self._series(series_id)
        return None if not rows else int(rows[0].candle_time)

    def head_time(self, series_id: str) -> int | None:
        rows = self._series(series_id)
        return None if not rows else int(rows[-1].candle_time)

    def count_closed_between_times(self, series_id: str, *, start_time: int, end_time: int) -> int:
        rows = self._series(series_id)
        return sum(1 for row in rows if int(start_time) <= int(row.candle_time) <= int(end_time))

    def get_closed(self, series_id: str, *, since: int | None, limit: int) -> list[CandleClosed]:
        rows = self._series(series_id)
        if since is None:
            picked = rows[-int(limit) :]
        else:
            picked = [row for row in rows if int(row.candle_time) > int(since)][: int(limit)]
        return list(picked)

    def get_closed_between_times(
        self,
        series_id: str,
        *,
        start_time: int,
        end_time: int,
        limit: int = 20000,
    ) -> list[CandleClosed]:
        rows = self._series(series_id)
        picked = [row for row in rows if int(start_time) <= int(row.candle_time) <= int(end_time)]
        return list(picked[: int(limit)])


def test_analyze_series_health_does_not_require_raw_sql_connection() -> None:
    store = _StoreWithoutConnect()
    base_series_id = "binance:futures:BTC/USDT:1m"
    derived_series_id = "binance:futures:BTC/USDT:5m"
    store.seed(series_id=base_series_id, candle_times=[300, 360, 420, 540, 600, 660])
    store.seed(series_id=derived_series_id, candle_times=[300, 900])

    payload = analyze_series_health(
        store=store,  # type: ignore[arg-type]
        series_id=derived_series_id,
        now_time=1200,
        max_recent_gaps=3,
        recent_base_buckets=2,
    )

    assert payload["series_id"] == derived_series_id
    assert payload["gap_count"] == 1
    assert payload["max_gap_seconds"] == 600
    assert payload["base_series_id"] == base_series_id
    assert payload["base_bucket_completeness"][-1]["bucket_open_time"] == 600
    assert payload["base_bucket_completeness"][-1]["actual_minutes"] == 2
