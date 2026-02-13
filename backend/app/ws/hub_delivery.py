from __future__ import annotations

from typing import Awaitable, Callable

from fastapi import WebSocket

from ..schemas import CandleClosed
from .hub_subscription_store import Subscription
from .protocol import WS_MSG_CANDLE_CLOSED, WS_MSG_CANDLES_BATCH, WS_MSG_GAP


GapBackfillHandler = Callable[[str, int, int], Awaitable[list[CandleClosed]]]


class CandleHubDelivery:
    def __init__(self, *, gap_backfill_handler: GapBackfillHandler | None = None) -> None:
        self._gap_backfill_handler = gap_backfill_handler

    def set_gap_backfill_handler(self, handler: GapBackfillHandler | None) -> None:
        self._gap_backfill_handler = handler

    @staticmethod
    def merge_candles(candles: list[CandleClosed]) -> list[CandleClosed]:
        if not candles:
            return []
        dedup: dict[int, CandleClosed] = {}
        for candle in candles:
            dedup[int(candle.candle_time)] = candle
        ordered = sorted(dedup.items(), key=lambda x: x[0])
        return [c for _, c in ordered]

    async def recover_gap_candles(
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
        return self.merge_candles(out)

    @staticmethod
    def expected_next_time(sub: Subscription) -> int | None:
        if sub.last_sent_time is None:
            return None
        return int(sub.last_sent_time) + int(sub.timeframe_s)

    @staticmethod
    def build_gap_payload(*, series_id: str, expected_next_time: int, actual_time: int) -> dict:
        return {
            "type": WS_MSG_GAP,
            "series_id": series_id,
            "expected_next_time": int(expected_next_time),
            "actual_time": int(actual_time),
        }

    @staticmethod
    def should_skip_candle(*, sub: Subscription, candle_time: int) -> bool:
        if sub.last_sent_time is None:
            return False
        return int(candle_time) <= int(sub.last_sent_time)

    async def send_closed(self, *, ws: WebSocket, series_id: str, candle: CandleClosed) -> None:
        await ws.send_json(
            {
                "type": WS_MSG_CANDLE_CLOSED,
                "series_id": series_id,
                "candle": candle.model_dump(),
            }
        )

    async def prepare_sendable_with_gap(
        self,
        *,
        series_id: str,
        sub: Subscription,
        candles_sorted: list[CandleClosed],
    ) -> tuple[list[CandleClosed], dict | None]:
        sendable = [c for c in candles_sorted if not self.should_skip_candle(sub=sub, candle_time=int(c.candle_time))]
        if not sendable:
            return [], None

        expected_next = self.expected_next_time(sub)
        if expected_next is None:
            return sendable, None

        first_time = int(sendable[0].candle_time)
        if first_time <= int(expected_next):
            return sendable, None

        recovered = await self.recover_gap_candles(
            series_id=series_id,
            expected_next_time=int(expected_next),
            actual_time=first_time,
        )
        if recovered:
            sendable = self.merge_candles([*recovered, *sendable])
            first_time = int(sendable[0].candle_time)

        if first_time > int(expected_next):
            return sendable, self.build_gap_payload(
                series_id=series_id,
                expected_next_time=int(expected_next),
                actual_time=first_time,
            )
        return sendable, None

    async def emit_batch(self, *, ws: WebSocket, sub: Subscription, series_id: str, candles: list[CandleClosed]) -> None:
        await ws.send_json(
            {
                "type": WS_MSG_CANDLES_BATCH,
                "series_id": series_id,
                "candles": [c.model_dump() for c in candles],
            }
        )
        sub.last_sent_time = int(candles[-1].candle_time)

    async def emit_stream(
        self,
        *,
        ws: WebSocket,
        sub: Subscription,
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
            if self.should_skip_candle(sub=sub, candle_time=candle_time):
                continue
            expected_next = self.expected_next_time(sub)
            if expected_next is not None and candle_time > int(expected_next):
                same_gap = bool(gap_emitted and int(expected_next) == int(gap_expected) and candle_time == int(gap_actual))
                if not same_gap:
                    await ws.send_json(
                        self.build_gap_payload(
                            series_id=series_id,
                            expected_next_time=int(expected_next),
                            actual_time=candle_time,
                        )
                    )
            await self.send_closed(ws=ws, series_id=series_id, candle=candle)
            sub.last_sent_time = candle_time

    async def publish_closed_sequence(
        self,
        *,
        ws: WebSocket,
        sub: Subscription,
        series_id: str,
        candles_sorted: list[CandleClosed],
        allow_batch_message: bool,
    ) -> None:
        sendable, initial_gap_payload = await self.prepare_sendable_with_gap(
            series_id=series_id,
            sub=sub,
            candles_sorted=candles_sorted,
        )
        if not sendable:
            return

        if bool(allow_batch_message) and bool(sub.supports_batch):
            if isinstance(initial_gap_payload, dict):
                await ws.send_json(initial_gap_payload)
            await self.emit_batch(ws=ws, sub=sub, series_id=series_id, candles=sendable)
            return

        await self.emit_stream(
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
        timeframe_s: int,
    ) -> tuple[list[CandleClosed], dict | None]:
        if effective_since is None or int(effective_since) <= 0 or not catchup:
            return catchup, None

        expected_next = int(effective_since) + int(timeframe_s)
        first_time = int(catchup[0].candle_time)
        if first_time <= expected_next:
            return catchup, None

        recovered = await self.recover_gap_candles(
            series_id=series_id,
            expected_next_time=expected_next,
            actual_time=first_time,
        )
        merged = self.merge_candles([*recovered, *catchup]) if recovered else catchup
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
