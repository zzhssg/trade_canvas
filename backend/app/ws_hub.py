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


class CandleHub:
    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._subs_by_ws: dict[WebSocket, dict[str, _Subscription]] = {}

    async def subscribe(self, ws: WebSocket, *, series_id: str, since: int | None) -> None:
        timeframe = series_id_timeframe(series_id)
        timeframe_s = timeframe_to_seconds(timeframe)
        sub = _Subscription(series_id=series_id, last_sent_time=since, timeframe_s=timeframe_s)
        async with self._lock:
            self._subs_by_ws.setdefault(ws, {})[series_id] = sub

    async def set_last_sent(self, ws: WebSocket, *, series_id: str, candle_time: int) -> None:
        async with self._lock:
            subs = self._subs_by_ws.get(ws)
            if not subs:
                return
            sub = subs.get(series_id)
            if sub is None:
                return
            sub.last_sent_time = candle_time

    async def unsubscribe(self, ws: WebSocket, *, series_id: str) -> None:
        async with self._lock:
            subs = self._subs_by_ws.get(ws)
            if not subs:
                return
            subs.pop(series_id, None)
            if not subs:
                self._subs_by_ws.pop(ws, None)

    async def remove_ws(self, ws: WebSocket) -> None:
        async with self._lock:
            self._subs_by_ws.pop(ws, None)

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

                if sub.last_sent_time is not None and candle.candle_time < sub.last_sent_time:
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
