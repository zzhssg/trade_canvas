from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Awaitable, Callable

from fastapi import WebSocket

from .ws_protocol import (
    WS_MSG_CANDLE_CLOSED,
    WS_MSG_CANDLES_BATCH,
    WS_MSG_CANDLE_FORMING,
    WS_MSG_GAP,
    WS_MSG_SYSTEM,
)
from .schemas import CandleClosed
from .timeframe import series_id_timeframe, timeframe_to_seconds


@dataclass
class _Subscription:
    series_id: str
    last_sent_time: int | None
    timeframe_s: int
    supports_batch: bool


GapBackfillHandler = Callable[[str, int, int], Awaitable[list[CandleClosed]]]


class CandleHub:
    def __init__(self, *, gap_backfill_handler: GapBackfillHandler | None = None) -> None:
        self._lock = asyncio.Lock()
        self._subs_by_ws: dict[WebSocket, dict[str, _Subscription]] = {}
        self._gap_backfill_handler = gap_backfill_handler

    def set_gap_backfill_handler(self, handler: GapBackfillHandler | None) -> None:
        self._gap_backfill_handler = handler

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

    async def _collect_targets(self, *, series_id: str) -> list[tuple[WebSocket, _Subscription]]:
        async with self._lock:
            targets: list[tuple[WebSocket, _Subscription]] = []
            for ws, subs in self._subs_by_ws.items():
                sub = subs.get(series_id)
                if sub is None:
                    continue
                targets.append((ws, sub))
        return targets

    @staticmethod
    def _merge_candles(candles: list[CandleClosed]) -> list[CandleClosed]:
        if not candles:
            return []
        dedup: dict[int, CandleClosed] = {}
        for candle in candles:
            dedup[int(candle.candle_time)] = candle
        ordered = sorted(dedup.items(), key=lambda x: x[0])
        return [c for _, c in ordered]

    async def _recover_gap_candles(
        self,
        *,
        series_id: str,
        expected_next_time: int,
        actual_time: int,
    ) -> list[CandleClosed]:
        handler = self._gap_backfill_handler
        if handler is None:
            return []
        try:
            recovered = await handler(str(series_id), int(expected_next_time), int(actual_time))
        except Exception:
            return []
        out: list[CandleClosed] = []
        for candle in recovered:
            t = int(candle.candle_time)
            if t < int(expected_next_time):
                continue
            if t >= int(actual_time):
                continue
            out.append(candle)
        return self._merge_candles(out)

    @staticmethod
    def _expected_next_time(sub: _Subscription) -> int | None:
        if sub.last_sent_time is None:
            return None
        return int(sub.last_sent_time) + int(sub.timeframe_s)

    @staticmethod
    def _build_gap_payload(*, series_id: str, expected_next_time: int, actual_time: int) -> dict:
        return {
            "type": WS_MSG_GAP,
            "series_id": series_id,
            "expected_next_time": int(expected_next_time),
            "actual_time": int(actual_time),
        }

    async def _send_gap(
        self,
        *,
        ws: WebSocket,
        series_id: str,
        expected_next_time: int,
        actual_time: int,
    ) -> None:
        await ws.send_json(
            self._build_gap_payload(
                series_id=series_id,
                expected_next_time=int(expected_next_time),
                actual_time=int(actual_time),
            )
        )

    @staticmethod
    def _should_skip_candle(*, sub: _Subscription, candle_time: int) -> bool:
        if sub.last_sent_time is None:
            return False
        return int(candle_time) <= int(sub.last_sent_time)

    async def _send_closed(self, *, ws: WebSocket, series_id: str, candle: CandleClosed) -> None:
        await ws.send_json(
            {
                "type": WS_MSG_CANDLE_CLOSED,
                "series_id": series_id,
                "candle": candle.model_dump(),
            }
        )

    async def _prepare_sendable_with_gap(
        self,
        *,
        series_id: str,
        sub: _Subscription,
        candles_sorted: list[CandleClosed],
    ) -> tuple[list[CandleClosed], dict | None]:
        sendable = [c for c in candles_sorted if not self._should_skip_candle(sub=sub, candle_time=int(c.candle_time))]
        if not sendable:
            return [], None

        expected_next = self._expected_next_time(sub)
        if expected_next is None:
            return sendable, None

        first_time = int(sendable[0].candle_time)
        if first_time <= int(expected_next):
            return sendable, None

        recovered = await self._recover_gap_candles(
            series_id=series_id,
            expected_next_time=int(expected_next),
            actual_time=first_time,
        )
        if recovered:
            sendable = self._merge_candles([*recovered, *sendable])
            first_time = int(sendable[0].candle_time)

        if first_time > int(expected_next):
            return sendable, self._build_gap_payload(
                series_id=series_id,
                expected_next_time=int(expected_next),
                actual_time=first_time,
            )
        return sendable, None

    async def _emit_batch(self, *, ws: WebSocket, sub: _Subscription, series_id: str, candles: list[CandleClosed]) -> None:
        await ws.send_json(
            {
                "type": WS_MSG_CANDLES_BATCH,
                "series_id": series_id,
                "candles": [c.model_dump() for c in candles],
            }
        )
        sub.last_sent_time = int(candles[-1].candle_time)

    async def _emit_stream(
        self,
        *,
        ws: WebSocket,
        sub: _Subscription,
        series_id: str,
        candles: list[CandleClosed],
        initial_gap_payload: dict | None,
    ) -> None:
        gap_emitted = False
        gap_expected = 0
        gap_actual = 0
        if isinstance(initial_gap_payload, dict):
            await ws.send_json(initial_gap_payload)
            gap_emitted = True
            gap_expected = int(initial_gap_payload.get("expected_next_time") or 0)
            gap_actual = int(initial_gap_payload.get("actual_time") or 0)

        for candle in candles:
            candle_time = int(candle.candle_time)
            if self._should_skip_candle(sub=sub, candle_time=candle_time):
                continue
            expected_next = self._expected_next_time(sub)
            if expected_next is not None and candle_time > int(expected_next):
                same_gap = bool(gap_emitted and int(expected_next) == int(gap_expected) and candle_time == int(gap_actual))
                if not same_gap:
                    await self._send_gap(
                        ws=ws,
                        series_id=series_id,
                        expected_next_time=int(expected_next),
                        actual_time=candle_time,
                    )
            await self._send_closed(ws=ws, series_id=series_id, candle=candle)
            sub.last_sent_time = candle_time

    async def _publish_closed_sequence(
        self,
        *,
        ws: WebSocket,
        sub: _Subscription,
        series_id: str,
        candles_sorted: list[CandleClosed],
        allow_batch_message: bool,
    ) -> None:
        sendable, initial_gap_payload = await self._prepare_sendable_with_gap(
            series_id=series_id,
            sub=sub,
            candles_sorted=candles_sorted,
        )
        if not sendable:
            return

        if bool(allow_batch_message) and bool(sub.supports_batch):
            if isinstance(initial_gap_payload, dict):
                await ws.send_json(initial_gap_payload)
            await self._emit_batch(
                ws=ws,
                sub=sub,
                series_id=series_id,
                candles=sendable,
            )
            return

        await self._emit_stream(
            ws=ws,
            sub=sub,
            series_id=series_id,
            candles=sendable,
            initial_gap_payload=initial_gap_payload,
        )

    async def heal_catchup_gap(
        self,
        *,
        series_id: str,
        effective_since: int | None,
        catchup: list[CandleClosed],
    ) -> tuple[list[CandleClosed], dict | None]:
        if effective_since is None or int(effective_since) <= 0 or not catchup:
            return catchup, None

        tf_s = timeframe_to_seconds(series_id_timeframe(series_id))
        expected_next = int(effective_since) + int(tf_s)
        first_time = int(catchup[0].candle_time)
        if first_time <= expected_next:
            return catchup, None

        recovered = await self._recover_gap_candles(
            series_id=series_id,
            expected_next_time=expected_next,
            actual_time=first_time,
        )
        merged = self._merge_candles([*recovered, *catchup]) if recovered else catchup
        if merged:
            first_time = int(merged[0].candle_time)
        if first_time > expected_next:
            return (
                merged,
                {
                    "type": WS_MSG_GAP,
                    "series_id": series_id,
                    "expected_next_time": expected_next,
                    "actual_time": first_time,
                },
            )
        return merged, None

    async def publish_closed_batch(self, *, series_id: str, candles: list[CandleClosed]) -> None:
        if not candles:
            return

        candles_sorted = candles
        if len(candles) > 1:
            candles_sorted = candles[:]
            candles_sorted.sort(key=lambda c: int(c.candle_time))

        targets = await self._collect_targets(series_id=series_id)

        for ws, sub in targets:
            try:
                await self._publish_closed_sequence(
                    ws=ws,
                    sub=sub,
                    series_id=series_id,
                    candles_sorted=candles_sorted,
                    allow_batch_message=True,
                )
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
        targets = await self._collect_targets(series_id=series_id)

        for ws, sub in targets:
            try:
                await self._publish_closed_sequence(
                    ws=ws,
                    sub=sub,
                    series_id=series_id,
                    candles_sorted=[candle],
                    allow_batch_message=False,
                )
            except Exception:
                await self.remove_ws(ws)

    async def publish_forming(self, *, series_id: str, candle: CandleClosed) -> None:
        targets = await self._collect_targets(series_id=series_id)

        for ws, sub in targets:
            try:
                if sub.last_sent_time is not None and candle.candle_time <= sub.last_sent_time:
                    continue
                await ws.send_json(
                    {
                        "type": WS_MSG_CANDLE_FORMING,
                        "series_id": series_id,
                        "candle": candle.model_dump(),
                    }
                )
            except Exception:
                await self.remove_ws(ws)

    async def publish_system(self, *, series_id: str, event: str, message: str, data: dict | None = None) -> None:
        targets = [ws for ws, _ in await self._collect_targets(series_id=series_id)]
        payload = {
            "type": WS_MSG_SYSTEM,
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
