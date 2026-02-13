from __future__ import annotations

import asyncio
from dataclasses import dataclass

from fastapi import WebSocket


@dataclass
class Subscription:
    series_id: str
    last_sent_time: int | None
    timeframe_s: int
    supports_batch: bool


class HubSubscriptionStore:
    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._subs_by_ws: dict[WebSocket, dict[str, Subscription]] = {}

    async def close_all_snapshot(self) -> list[WebSocket]:
        async with self._lock:
            targets = list(self._subs_by_ws.keys())
            self._subs_by_ws.clear()
        return targets

    async def subscribe(self, ws: WebSocket, *, subscription: Subscription) -> None:
        async with self._lock:
            self._subs_by_ws.setdefault(ws, {})[subscription.series_id] = subscription

    async def collect_targets(self, *, series_id: str) -> list[tuple[WebSocket, Subscription]]:
        async with self._lock:
            targets: list[tuple[WebSocket, Subscription]] = []
            for ws, subs in self._subs_by_ws.items():
                sub = subs.get(series_id)
                if sub is None:
                    continue
                targets.append((ws, sub))
        return targets

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

    async def pop_ws(self, ws: WebSocket) -> list[str]:
        async with self._lock:
            subs = self._subs_by_ws.pop(ws, None) or {}
            return list(subs.keys())
