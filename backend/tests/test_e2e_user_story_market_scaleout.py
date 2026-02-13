from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from typing import Any
from unittest.mock import patch

from fastapi.testclient import TestClient

from backend.app.main import create_app
from backend.app.schemas import CandleClosed
from backend.app.ws_publishers import WsPubsubConsumer, WsPubsubMessage


class _FakePgRepo:
    def __init__(self, *, pool: Any, schema: str) -> None:
        _ = pool
        _ = schema
        self._rows: dict[str, dict[int, CandleClosed]] = {}

    def _series(self, series_id: str) -> dict[int, CandleClosed]:
        return self._rows.setdefault(str(series_id), {})

    def upsert_closed(self, series_id: str, candle: CandleClosed) -> None:
        self._series(series_id)[int(candle.candle_time)] = candle

    def upsert_many_closed(self, series_id: str, candles: list[CandleClosed]) -> None:
        for candle in candles:
            self.upsert_closed(series_id, candle)

    def delete_closed_times(self, *, series_id: str, candle_times: list[int]) -> int:
        series = self._series(series_id)
        deleted = 0
        for t in candle_times:
            if series.pop(int(t), None) is not None:
                deleted += 1
        return int(deleted)

    def trim_series_to_latest_n(self, *, series_id: str, keep: int) -> int:
        keep_n = max(1, int(keep))
        series = self._series(series_id)
        if len(series) <= keep_n:
            return 0
        times = sorted(series.keys())
        drop = times[: max(0, len(times) - keep_n)]
        for t in drop:
            series.pop(t, None)
        return len(drop)

    def head_time(self, series_id: str) -> int | None:
        series = self._series(series_id)
        if not series:
            return None
        return int(max(series.keys()))

    def first_time(self, series_id: str) -> int | None:
        series = self._series(series_id)
        if not series:
            return None
        return int(min(series.keys()))

    def count_closed_between_times(self, series_id: str, *, start_time: int, end_time: int) -> int:
        series = self._series(series_id)
        return sum(1 for t in series if int(start_time) <= int(t) <= int(end_time))

    def floor_time(self, series_id: str, *, at_time: int) -> int | None:
        series = self._series(series_id)
        candidates = [int(t) for t in series if int(t) <= int(at_time)]
        return None if not candidates else max(candidates)

    def get_closed(self, series_id: str, *, since: int | None, limit: int) -> list[CandleClosed]:
        series = self._series(series_id)
        ordered = sorted(series.keys())
        if since is not None:
            ordered = [t for t in ordered if int(t) > int(since)]
        if len(ordered) > int(limit):
            if since is None:
                ordered = ordered[-int(limit) :]
            else:
                ordered = ordered[: int(limit)]
        return [series[t] for t in ordered]

    def get_closed_between_times(
        self,
        series_id: str,
        *,
        start_time: int,
        end_time: int,
        limit: int = 20000,
    ) -> list[CandleClosed]:
        series = self._series(series_id)
        ordered = [
            t
            for t in sorted(series.keys())
            if int(start_time) <= int(t) <= int(end_time)
        ]
        if len(ordered) > int(limit):
            ordered = ordered[: int(limit)]
        return [series[t] for t in ordered]


class _FakeBus:
    def __init__(self) -> None:
        self.subscribers: list[WsPubsubConsumer] = []
        self.published: list[WsPubsubMessage] = []

    def attach(self, consumer: WsPubsubConsumer) -> None:
        self.subscribers.append(consumer)

    def detach(self, consumer: WsPubsubConsumer) -> None:
        if consumer in self.subscribers:
            self.subscribers.remove(consumer)

    async def publish(self, message: WsPubsubMessage) -> None:
        self.published.append(message)
        for consumer in list(self.subscribers):
            await consumer(message)


class _FakePublisher:
    def __init__(self, *, bus: _FakeBus) -> None:
        self._bus = bus
        self._consumer: WsPubsubConsumer | None = None
        self._started = False

    def set_consumer(self, consumer: WsPubsubConsumer) -> None:
        self._consumer = consumer

    async def start(self) -> None:
        if self._started:
            return
        if self._consumer is None:
            raise RuntimeError("consumer_not_set")
        self._bus.attach(self._consumer)
        self._started = True

    async def publish(self, message: WsPubsubMessage) -> None:
        await self._bus.publish(message)

    async def close(self) -> None:
        if self._consumer is not None:
            self._bus.detach(self._consumer)
        self._started = False


class MarketScaleoutE2EUserStoryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmpdir = tempfile.TemporaryDirectory()
        root = Path(self.tmpdir.name)
        self.db_path = root / "market.db"
        self.whitelist_path = root / "whitelist.json"
        self.whitelist_path.write_text('{"series_ids":[]}', encoding="utf-8")
        os.environ["TRADE_CANVAS_DB_PATH"] = str(self.db_path)
        os.environ["TRADE_CANVAS_WHITELIST_PATH"] = str(self.whitelist_path)

    def tearDown(self) -> None:
        self.tmpdir.cleanup()
        for key in (
            "TRADE_CANVAS_DB_PATH",
            "TRADE_CANVAS_WHITELIST_PATH",
            "TRADE_CANVAS_ENABLE_DEBUG_API",
            "TRADE_CANVAS_ENABLE_PG_STORE",
            "TRADE_CANVAS_ENABLE_DUAL_WRITE",
            "TRADE_CANVAS_ENABLE_PG_READ",
            "TRADE_CANVAS_ENABLE_WS_PUBSUB",
            "TRADE_CANVAS_POSTGRES_DSN",
            "TRADE_CANVAS_REDIS_URL",
        ):
            os.environ.pop(key, None)

    def test_dual_write_and_pg_read_consistency_under_scaleout_mode(self) -> None:
        os.environ["TRADE_CANVAS_ENABLE_DEBUG_API"] = "1"
        os.environ["TRADE_CANVAS_ENABLE_PG_STORE"] = "1"
        os.environ["TRADE_CANVAS_ENABLE_DUAL_WRITE"] = "1"
        os.environ["TRADE_CANVAS_ENABLE_PG_READ"] = "1"
        os.environ["TRADE_CANVAS_POSTGRES_DSN"] = "postgresql://tc:tc@127.0.0.1:5432/tc"

        series_id = "binance:futures:BTC/USDT:1m"
        with (
            patch("backend.app.container._maybe_bootstrap_postgres", return_value=object()),
            patch("backend.app.container.PostgresCandleRepository", _FakePgRepo),
        ):
            with TestClient(create_app()) as client:
                for candle_time in (1700000000, 1700000060, 1700000120):
                    response = client.post(
                        "/api/market/ingest/candle_closed",
                        json={
                            "series_id": series_id,
                            "candle": {
                                "candle_time": candle_time,
                                "open": 100.0,
                                "high": 103.0,
                                "low": 99.0,
                                "close": 102.4,
                                "volume": 12.0,
                            },
                        },
                    )
                    self.assertEqual(response.status_code, 200, response.text)

                candles_resp = client.get(
                    "/api/market/candles",
                    params={"series_id": series_id, "since": 1700000060, "limit": 10},
                )
                self.assertEqual(candles_resp.status_code, 200, candles_resp.text)
                candles = candles_resp.json().get("candles", [])
                self.assertEqual([int(c["candle_time"]) for c in candles], [1700000120])
                app = client.app
                container = app.state.container
                store = container.store
                self.assertEqual(int(store.head_time(series_id) or 0), 1700000120)
                self.assertIsNotNone(getattr(store, "mirror_repository", None))

    def test_multi_instance_ws_pubsub_delivers_closed_to_remote_subscribers(self) -> None:
        os.environ["TRADE_CANVAS_ENABLE_WS_PUBSUB"] = "1"
        os.environ["TRADE_CANVAS_REDIS_URL"] = "redis://127.0.0.1:6379/0"

        bus = _FakeBus()

        def _fake_build_ws_publisher(*, settings, runtime_flags):  # noqa: ANN001
            _ = settings
            if not bool(runtime_flags.enable_ws_pubsub):
                return None
            return _FakePublisher(bus=bus)

        series_id = "binance:futures:BTC/USDT:1m"
        with patch("backend.app.market_runtime_builder._build_ws_publisher", side_effect=_fake_build_ws_publisher):
            client_a = TestClient(create_app())
            client_b = TestClient(create_app())
            try:
                with client_a, client_b:
                    with client_b.websocket_connect("/ws/market") as ws_b:
                        ws_b.send_json({"type": "subscribe", "series_id": series_id, "since": 1700000060})

                        response = client_a.post(
                            "/api/market/ingest/candle_closed",
                            json={
                                "series_id": series_id,
                                "candle": {
                                    "candle_time": 1700000120,
                                    "open": 101.2,
                                    "high": 103.0,
                                    "low": 101.0,
                                    "close": 102.4,
                                    "volume": 12.0,
                                },
                            },
                        )
                        self.assertEqual(response.status_code, 200, response.text)

                        msg = ws_b.receive_json()
                        self.assertEqual(msg["type"], "candle_closed")
                        self.assertEqual(int(msg["candle"]["candle_time"]), 1700000120)
                        closed_messages = [m for m in bus.published if str(m.event_type) == "candle_closed"]
                        self.assertEqual(len(closed_messages), 1)
            finally:
                client_a.close()
                client_b.close()


if __name__ == "__main__":
    unittest.main()
