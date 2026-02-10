from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from .factor_plugin_contract import FactorCatalogSpec, FactorCatalogSubFeatureSpec
from .factor_registry import ProcessorSpec
from .factor_runtime_contract import FactorRuntimeContext
from .factor_store import FactorEventWrite
from .zhongshu import (
    ZhongshuDead,
    build_alive_zhongshu_from_confirmed_pens,
    replay_zhongshu_state,
    replay_zhongshu_state_with_closed_candles,
    update_zhongshu_state,
    update_zhongshu_state_on_closed_candle,
)


class _CandleLike(Protocol):
    candle_time: int
    high: float
    low: float


class _ZhongshuTickState(Protocol):
    new_confirmed_pen_payloads: list[dict[str, Any]]
    zhongshu_state: dict[str, Any]
    events: list[FactorEventWrite]
    formed_entries: list[dict[str, Any]]
    time_to_idx: dict[int, int]
    visible_time: int
    candles: list[_CandleLike]


class _ZhongshuBootstrapState(Protocol):
    candles: list[_CandleLike]
    head_time: int
    confirmed_pens: list[dict[str, Any]]
    zhongshu_state: dict[str, Any]


class _ZhongshuHeadState(Protocol):
    zhongshu_state: dict[str, Any]
    confirmed_pens: list[dict[str, Any]]
    up_to: int
    candles: list[_CandleLike]


@dataclass(frozen=True)
class ZhongshuProcessor:
    spec: ProcessorSpec = ProcessorSpec(
        factor_name="zhongshu",
        depends_on=("pen",),
        catalog=FactorCatalogSpec(
            label="Zhongshu",
            default_visible=True,
            sub_features=(
                FactorCatalogSubFeatureSpec(key="zhongshu.alive", label="Alive", default_visible=True),
                FactorCatalogSubFeatureSpec(key="zhongshu.dead", label="Dead", default_visible=True),
            ),
        ),
    )

    def run_tick(self, *, series_id: str, state: _ZhongshuTickState, runtime: FactorRuntimeContext) -> None:
        _ = runtime
        for pen_payload in state.new_confirmed_pen_payloads:
            dead_event, formed_entry = self.update_state_from_pen(
                state=state.zhongshu_state,
                series_id=series_id,
                pen_payload=pen_payload,
            )
            if dead_event is not None:
                state.events.append(dead_event)
            if formed_entry is not None:
                state.formed_entries.append(formed_entry)

        idx_now = state.time_to_idx.get(int(state.visible_time))
        if idx_now is None:
            return
        candle = state.candles[int(idx_now)]
        formed_entry_on_candle = self.update_state_from_closed_candle(
            state=state.zhongshu_state,
            candle_time=int(candle.candle_time),
            high=float(candle.high),
            low=float(candle.low),
        )
        if formed_entry_on_candle is not None:
            state.formed_entries.append(formed_entry_on_candle)

    def bootstrap_from_history(
        self,
        *,
        series_id: str,
        state: _ZhongshuBootstrapState,
        runtime: FactorRuntimeContext,
    ) -> None:
        _ = series_id
        _ = runtime
        candles_up_to_head = [c for c in state.candles if int(c.candle_time) <= int(state.head_time)]
        state.zhongshu_state = self.build_state(
            confirmed_pens=state.confirmed_pens,
            candles_up_to_head=candles_up_to_head,
            head_time=int(state.head_time),
        )

    def build_state(self, *, confirmed_pens: list[dict], candles_up_to_head: list[Any], head_time: int) -> dict[str, Any]:
        if candles_up_to_head and int(head_time) > 0:
            return replay_zhongshu_state_with_closed_candles(
                pens=confirmed_pens,
                candles=candles_up_to_head,
                up_to_visible_time=int(head_time),
            )
        return replay_zhongshu_state(confirmed_pens)

    def update_state_from_pen(
        self, *, state: dict[str, Any], series_id: str, pen_payload: dict
    ) -> tuple[FactorEventWrite | None, dict | None]:
        dead_event, formed_entry = update_zhongshu_state(state, pen_payload)
        if dead_event is None:
            return None, formed_entry
        return self.build_dead_event(series_id=series_id, dead_event=dead_event), formed_entry

    def update_state_from_closed_candle(self, *, state: dict[str, Any], candle_time: int, high: float, low: float) -> dict | None:
        return update_zhongshu_state_on_closed_candle(
            state,
            {
                "candle_time": int(candle_time),
                "high": float(high),
                "low": float(low),
            },
        )

    def build_dead_event(self, *, series_id: str, dead_event: ZhongshuDead) -> FactorEventWrite:
        key_dead = (
            f"dead:{int(dead_event.start_time)}:{int(dead_event.formed_time)}:{int(dead_event.death_time)}:"
            f"{float(dead_event.zg):.8f}:{float(dead_event.zd):.8f}:{str(dead_event.formed_reason)}"
        )
        return FactorEventWrite(
            series_id=series_id,
            factor_name="zhongshu",
            candle_time=int(dead_event.visible_time),
            kind="zhongshu.dead",
            event_key=key_dead,
            payload={
                "start_time": int(dead_event.start_time),
                "end_time": int(dead_event.end_time),
                "zg": float(dead_event.zg),
                "zd": float(dead_event.zd),
                "entry_direction": int(dead_event.entry_direction),
                "formed_time": int(dead_event.formed_time),
                "death_time": int(dead_event.death_time),
                "visible_time": int(dead_event.visible_time),
                "formed_reason": str(dead_event.formed_reason),
            },
        )

    def build_alive_head(
        self, *, state: dict[str, Any], confirmed_pens: list[dict], up_to_visible_time: int, candles: list[Any]
    ) -> dict[str, Any]:
        out: dict[str, Any] = {}
        if confirmed_pens:
            out["alive"] = []

        alive_state = state.get("alive")
        if isinstance(alive_state, dict):
            out["alive"] = [
                {
                    "start_time": int(alive_state.get("start_time") or 0),
                    "end_time": int(alive_state.get("end_time") or 0),
                    "zg": float(alive_state.get("zg") or 0.0),
                    "zd": float(alive_state.get("zd") or 0.0),
                    "entry_direction": int(alive_state.get("entry_direction") or 1),
                    "formed_time": int(alive_state.get("formed_time") or 0),
                    "formed_reason": str(alive_state.get("formed_reason") or "pen_confirmed"),
                    "death_time": None,
                    "visible_time": int(up_to_visible_time),
                }
            ]
            return out

        if not confirmed_pens:
            return out

        alive = build_alive_zhongshu_from_confirmed_pens(
            confirmed_pens,
            up_to_visible_time=int(up_to_visible_time),
            candles=candles,
        )
        if alive is None or int(alive.visible_time) != int(up_to_visible_time):
            return out
        out["alive"] = [
            {
                "start_time": int(alive.start_time),
                "end_time": int(alive.end_time),
                "zg": float(alive.zg),
                "zd": float(alive.zd),
                "entry_direction": int(alive.entry_direction),
                "formed_time": int(alive.formed_time),
                "formed_reason": str(alive.formed_reason),
                "death_time": None,
                "visible_time": int(alive.visible_time),
            }
        ]
        return out

    def build_head_snapshot(
        self,
        *,
        series_id: str,
        state: _ZhongshuHeadState,
        runtime: FactorRuntimeContext,
    ) -> dict[str, Any] | None:
        _ = series_id
        _ = runtime
        out = self.build_alive_head(
            state=state.zhongshu_state,
            confirmed_pens=state.confirmed_pens,
            up_to_visible_time=int(state.up_to),
            candles=state.candles,
        )
        if "alive" not in out:
            return None
        return out
