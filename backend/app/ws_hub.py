from __future__ import annotations

import asyncio
from dataclasses import dataclass

from fastapi import WebSocket

from .schemas import CandleClosed
from .timeframe import series_id_timeframe, timeframe_to_seconds


@dataclass
class _Subscription:
    series_id: str
    last_sent_time: int | None
    timeframe_s: int
    supports_batch: bool


class CandleHub:
    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._subs_by_ws: dict[WebSocket, dict[str, _Subscription]] = {}

    async def close_all(self, *, code: int = 1001, reason: str = "server_shutdown") -> None:
        """
        Best-effort close all active websocket connections.

        This is mainly used during app shutdown to avoid uvicorn waiting on lingering WS connections.
        """
        async with self._lock:
            targets = list(self._subs_by_ws.keys())
            self._subs_by_ws.clear()

        for ws in targets:
            try:
                await ws.close(code=code, reason=reason)
            except Exception:
                pass

    async def subscribe(self, ws: WebSocket, *, series_id: str, since: int | None, supports_batch: bool = False) -> None:
        timeframe = series_id_timeframe(series_id)
        timeframe_s = timeframe_to_seconds(timeframe)
        sub = _Subscription(
            series_id=series_id,
            last_sent_time=since,
            timeframe_s=timeframe_s,
            supports_batch=bool(supports_batch),
        )
        async with self._lock:
            self._subs_by_ws.setdefault(ws, {})[series_id] = sub

    async def publish_closed_batch(self, *, series_id: str, candles: list[CandleClosed]) -> None:
        if not candles:
            return

        candles_sorted = candles
        if len(candles) > 1:
            candles_sorted = candles[:]
            candles_sorted.sort(key=lambda c: int(c.candle_time))

        async with self._lock:
            targets: list[tuple[WebSocket, _Subscription]] = []
            for ws, subs in self._subs_by_ws.items():
                sub = subs.get(series_id)
                if sub is None:
                    continue
                targets.append((ws, sub))

        for ws, sub in targets:
            try:
                sendable = candles_sorted
                if sub.last_sent_time is not None:
                    last = int(sub.last_sent_time)
                    sendable = [c for c in candles_sorted if int(c.candle_time) > last]
                if not sendable:
                    continue

                expected_next = None
                if sub.last_sent_time is not None:
                    expected_next = int(sub.last_sent_time) + int(sub.timeframe_s)

                first_time = int(sendable[0].candle_time)
                if expected_next is not None and first_time > expected_next:
                    await ws.send_json(
                        {
                            "type": "gap",
                            "series_id": series_id,
                            "expected_next_time": expected_next,
                            "actual_time": first_time,
                        }
                    )

                if sub.supports_batch:
                    await ws.send_json(
                        {
                            "type": "candles_batch",
                            "series_id": series_id,
                            "candles": [c.model_dump() for c in sendable],
                        }
                    )
                    sub.last_sent_time = int(sendable[-1].candle_time)
                    continue

                for candle in sendable:
                    expected_next_one = None
                    if sub.last_sent_time is not None:
                        expected_next_one = int(sub.last_sent_time) + int(sub.timeframe_s)

                    if sub.last_sent_time is not None and int(candle.candle_time) < int(sub.last_sent_time):
                        continue

                    if expected_next_one is not None and int(candle.candle_time) > int(expected_next_one):
                        await ws.send_json(
                            {
                                "type": "gap",
                                "series_id": series_id,
                                "expected_next_time": expected_next_one,
                                "actual_time": int(candle.candle_time),
                            }
                        )

                    await ws.send_json(
                        {
                            "type": "candle_closed",
                            "series_id": series_id,
                            "candle": candle.model_dump(),
                        }
                    )
                    sub.last_sent_time = int(candle.candle_time)
            except Exception:
                await self.remove_ws(ws)

    async def set_last_sent(self, ws: WebSocket, *, series_id: str, candle_time: int) -> None:
        async with self._lock:
            subs = self._subs_by_ws.get(ws)
            if not subs:
                return
            sub = subs.get(series_id)
            if sub is None:
                return
            sub.last_sent_time = candle_time

    async def get_last_sent(self, ws: WebSocket, *, series_id: str) -> int | None:
        async with self._lock:
            subs = self._subs_by_ws.get(ws)
            if not subs:
                return None
            sub = subs.get(series_id)
            if sub is None:
                return None
            return sub.last_sent_time

    async def unsubscribe(self, ws: WebSocket, *, series_id: str) -> None:
        async with self._lock:
            subs = self._subs_by_ws.get(ws)
            if not subs:
                return
            subs.pop(series_id, None)
            if not subs:
                self._subs_by_ws.pop(ws, None)

    async def remove_ws(self, ws: WebSocket) -> None:
        await self.pop_ws(ws)

    async def pop_ws(self, ws: WebSocket) -> list[str]:
        """
        Remove ws from hub and return the subscribed series_ids (best-effort).

        Used to release ondemand ingest refcounts on websocket disconnect.
        """
        async with self._lock:
            subs = self._subs_by_ws.pop(ws, None) or {}
            return list(subs.keys())

    async def publish_closed(self, *, series_id: str, candle: CandleClosed) -> None:
        async with self._lock:
            targets = []
            for ws, subs in self._subs_by_ws.items():
                sub = subs.get(series_id)
                if sub is None:
                    continue
                targets.append((ws, sub))

        for ws, sub in targets:
            try:
                expected_next = None
                if sub.last_sent_time is not None:
                    expected_next = sub.last_sent_time + sub.timeframe_s

                if sub.last_sent_time is not None and candle.candle_time <= sub.last_sent_time:
                    continue

                if expected_next is not None and candle.candle_time > expected_next:
                    await ws.send_json(
                        {
                            "type": "gap",
                            "series_id": series_id,
                            "expected_next_time": expected_next,
                            "actual_time": candle.candle_time,
                        }
                    )

                await ws.send_json(
                    {
                        "type": "candle_closed",
                        "series_id": series_id,
                        "candle": candle.model_dump(),
                    }
                )
                sub.last_sent_time = candle.candle_time
            except Exception:
                await self.remove_ws(ws)

    async def publish_forming(self, *, series_id: str, candle: CandleClosed) -> None:
        async with self._lock:
            targets = []
            for ws, subs in self._subs_by_ws.items():
                sub = subs.get(series_id)
                if sub is None:
                    continue
                targets.append((ws, sub))

        for ws, sub in targets:
            try:
                if sub.last_sent_time is not None and candle.candle_time <= sub.last_sent_time:
                    continue
                await ws.send_json(
                    {
                        "type": "candle_forming",
                        "series_id": series_id,
                        "candle": candle.model_dump(),
                    }
                )
            except Exception:
                await self.remove_ws(ws)

    async def publish_system(self, *, series_id: str, event: str, message: str, data: dict | None = None) -> None:
        async with self._lock:
            targets = []
            for ws, subs in self._subs_by_ws.items():
                if series_id in subs:
                    targets.append(ws)
        payload = {
            "type": "system",
            "series_id": series_id,
            "event": str(event),
            "message": str(message),
            "data": dict(data or {}),
        }
        for ws in targets:
            try:
                await ws.send_json(payload)
            except Exception:
                await self.remove_ws(ws)
