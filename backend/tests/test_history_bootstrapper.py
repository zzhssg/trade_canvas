from __future__ import annotations

from pathlib import Path

import pandas as pd

from backend.app.history_bootstrapper import maybe_bootstrap_from_freqtrade
from backend.app.store import CandleStore


def _write_feather(path: Path, *, n: int) -> None:
    start = pd.Timestamp("2024-01-01T00:00:00Z")
    dates = pd.date_range(start=start, periods=n, freq="1min", tz="UTC")
    df = pd.DataFrame(
        {
            "date": dates,
            "open": [1.0 + i for i in range(n)],
            "high": [1.1 + i for i in range(n)],
            "low": [0.9 + i for i in range(n)],
            "close": [1.05 + i for i in range(n)],
            "volume": [100.0 + i for i in range(n)],
        }
    )
    df.to_feather(path)


def test_bootstrap_from_freqtrade_datadir_env(tmp_path, monkeypatch) -> None:
    datadir = tmp_path / "datadir"
    datadir.mkdir(parents=True, exist_ok=True)
    _write_feather(datadir / "BTC_USDT-1m.feather", n=10)

    monkeypatch.setenv("TRADE_CANVAS_MARKET_HISTORY_SOURCE", "freqtrade")
    monkeypatch.setenv("TRADE_CANVAS_FREQTRADE_DATADIR", str(datadir))

    db_path = tmp_path / "market.db"
    store = CandleStore(db_path=db_path)
    series_id = "binance:spot:BTC/USDT:1m"

    wrote = maybe_bootstrap_from_freqtrade(store, series_id=series_id, limit=2000)
    assert wrote == 10

    head = store.head_time(series_id)
    assert head is not None

    candles = store.get_closed(series_id, since=None, limit=2000)
    assert len(candles) == 10
    times = [c.candle_time for c in candles]
    assert times == sorted(times)
    assert times[-1] == head


def test_bootstrap_skips_when_disabled(tmp_path, monkeypatch) -> None:
    monkeypatch.delenv("TRADE_CANVAS_MARKET_HISTORY_SOURCE", raising=False)
    monkeypatch.delenv("TRADE_CANVAS_FREQTRADE_DATADIR", raising=False)

    db_path = tmp_path / "market.db"
    store = CandleStore(db_path=db_path)
    wrote = maybe_bootstrap_from_freqtrade(store, series_id="binance:spot:BTC/USDT:1m", limit=10)
    assert wrote == 0


def test_bootstrap_futures_accepts_freqtrade_usdt_suffix_filename(tmp_path, monkeypatch) -> None:
    datadir = tmp_path / "datadir" / "futures"
    datadir.mkdir(parents=True, exist_ok=True)
    _write_feather(datadir / "BTC_USDT_USDT-5m-futures.feather", n=12)

    monkeypatch.setenv("TRADE_CANVAS_MARKET_HISTORY_SOURCE", "freqtrade")
    monkeypatch.setenv("TRADE_CANVAS_FREQTRADE_DATADIR", str(tmp_path / "datadir"))

    db_path = tmp_path / "market.db"
    store = CandleStore(db_path=db_path)
    series_id = "binance:futures:BTC/USDT:5m"

    wrote = maybe_bootstrap_from_freqtrade(store, series_id=series_id, limit=2000)
    assert wrote == 12
    assert store.head_time(series_id) is not None
