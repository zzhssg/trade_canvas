from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .anchor_semantics import should_append_switch
from .factor_registry import FactorProcessor, ProcessorSpec
from .factor_slices import build_pen_head_candidate
from .factor_store import FactorEventWrite
from .pen import ConfirmedPen, PivotMajorPoint
from .zhongshu import (
    ZhongshuDead,
    build_alive_zhongshu_from_confirmed_pens,
    replay_zhongshu_state,
    replay_zhongshu_state_with_closed_candles,
    update_zhongshu_state,
    update_zhongshu_state_on_closed_candle,
)


@dataclass(frozen=True)
class PivotProcessor:
    spec: ProcessorSpec = ProcessorSpec(factor_name="pivot", depends_on=())

    def compute_major_candidates(
        self,
        *,
        candles: list[Any],
        time_to_idx: dict[int, int],
        pivot_time: int,
        visible_time: int,
        window: int,
    ) -> list[PivotMajorPoint]:
        idx = time_to_idx.get(int(pivot_time))
        if idx is None:
            return []
        w = int(window)
        if idx - w < 0 or idx + w >= len(candles):
            return []
        if int(candles[idx + w].candle_time) != int(visible_time):
            return []

        target_high = float(candles[idx].high)
        is_max_left = all(float(candles[i].high) < target_high for i in range(idx - w, idx))
        is_max_right = all(float(candles[i].high) <= target_high for i in range(idx + 1, idx + w + 1))

        target_low = float(candles[idx].low)
        is_min_left = all(float(candles[i].low) > target_low for i in range(idx - w, idx))
        is_min_right = all(float(candles[i].low) >= target_low for i in range(idx + 1, idx + w + 1))

        out: list[PivotMajorPoint] = []
        if is_max_left and is_max_right:
            out.append(
                PivotMajorPoint(
                    pivot_time=int(pivot_time),
                    pivot_price=float(target_high),
                    direction="resistance",
                    visible_time=int(visible_time),
                    pivot_idx=int(idx),
                )
            )
        if is_min_left and is_min_right:
            out.append(
                PivotMajorPoint(
                    pivot_time=int(pivot_time),
                    pivot_price=float(target_low),
                    direction="support",
                    visible_time=int(visible_time),
                    pivot_idx=int(idx),
                )
            )
        return out

    def compute_minor_candidates(
        self,
        *,
        candles: list[Any],
        time_to_idx: dict[int, int],
        pivot_time: int,
        visible_time: int,
        window: int,
        segment_start_idx: int | None,
    ) -> list[PivotMajorPoint]:
        if segment_start_idx is None:
            return []
        idx = time_to_idx.get(int(pivot_time))
        if idx is None:
            return []
        w = int(window)
        if idx - w < 0 or idx + w >= len(candles):
            return []
        if idx - w < int(segment_start_idx):
            return []
        if int(candles[idx + w].candle_time) != int(visible_time):
            return []

        highs = [float(candles[i].high) for i in range(idx - w, idx + w + 1)]
        lows = [float(candles[i].low) for i in range(idx - w, idx + w + 1)]
        max_high = max(highs) if highs else None
        min_low = min(lows) if lows else None
        if max_high is None or min_low is None:
            return []

        center_high = float(candles[idx].high)
        center_low = float(candles[idx].low)

        out: list[PivotMajorPoint] = []
        if center_high >= float(max_high):
            out.append(
                PivotMajorPoint(
                    pivot_time=int(pivot_time),
                    pivot_price=float(center_high),
                    direction="resistance",
                    visible_time=int(visible_time),
                    pivot_idx=int(idx),
                )
            )
        if center_low <= float(min_low):
            out.append(
                PivotMajorPoint(
                    pivot_time=int(pivot_time),
                    pivot_price=float(center_low),
                    direction="support",
                    visible_time=int(visible_time),
                    pivot_idx=int(idx),
                )
            )
        return out

    def build_major_event(self, *, series_id: str, pivot: PivotMajorPoint, window: int) -> FactorEventWrite:
        key = f"major:{int(pivot.pivot_time)}:{str(pivot.direction)}:{int(window)}"
        return FactorEventWrite(
            series_id=series_id,
            factor_name="pivot",
            candle_time=int(pivot.visible_time),
            kind="pivot.major",
            event_key=key,
            payload={
                "pivot_time": int(pivot.pivot_time),
                "pivot_price": float(pivot.pivot_price),
                "direction": str(pivot.direction),
                "visible_time": int(pivot.visible_time),
                "window": int(window),
                "pivot_idx": int(pivot.pivot_idx) if pivot.pivot_idx is not None else None,
            },
        )

    def build_minor_event(self, *, series_id: str, pivot: PivotMajorPoint, window: int) -> FactorEventWrite:
        key = f"minor:{int(pivot.pivot_time)}:{str(pivot.direction)}:{int(window)}"
        return FactorEventWrite(
            series_id=series_id,
            factor_name="pivot",
            candle_time=int(pivot.visible_time),
            kind="pivot.minor",
            event_key=key,
            payload={
                "pivot_time": int(pivot.pivot_time),
                "pivot_price": float(pivot.pivot_price),
                "direction": str(pivot.direction),
                "visible_time": int(pivot.visible_time),
                "window": int(window),
                "pivot_idx": int(pivot.pivot_idx) if pivot.pivot_idx is not None else None,
            },
        )


def _is_more_extreme(prev: PivotMajorPoint, cur: PivotMajorPoint) -> bool:
    if cur.direction != prev.direction:
        return False
    if cur.direction == "resistance":
        return float(cur.pivot_price) > float(prev.pivot_price)
    return float(cur.pivot_price) < float(prev.pivot_price)


@dataclass(frozen=True)
class PenProcessor:
    spec: ProcessorSpec = ProcessorSpec(factor_name="pen", depends_on=("pivot",))

    def append_pivot_and_confirm(self, effective: list[PivotMajorPoint], new_pivot: PivotMajorPoint) -> list[ConfirmedPen]:
        if not effective:
            effective.append(new_pivot)
            return []

        last = effective[-1]
        if new_pivot.direction == last.direction:
            if _is_more_extreme(last, new_pivot):
                effective[-1] = new_pivot
            return []

        effective.append(new_pivot)
        if len(effective) < 3:
            return []

        p0 = effective[-3]
        p1 = effective[-2]
        confirmer = effective[-1]
        direction = 1 if float(p1.pivot_price) > float(p0.pivot_price) else -1
        return [
            ConfirmedPen(
                start_time=int(p0.pivot_time),
                end_time=int(p1.pivot_time),
                start_price=float(p0.pivot_price),
                end_price=float(p1.pivot_price),
                direction=int(direction),
                visible_time=int(confirmer.visible_time),
                start_idx=p0.pivot_idx,
                end_idx=p1.pivot_idx,
            )
        ]

    def build_confirmed_event(self, *, series_id: str, pen: ConfirmedPen) -> FactorEventWrite:
        key = f"confirmed:{int(pen.start_time)}:{int(pen.end_time)}:{int(pen.direction)}"
        return FactorEventWrite(
            series_id=series_id,
            factor_name="pen",
            candle_time=int(pen.visible_time),
            kind="pen.confirmed",
            event_key=key,
            payload={
                "start_time": int(pen.start_time),
                "end_time": int(pen.end_time),
                "start_price": float(pen.start_price),
                "end_price": float(pen.end_price),
                "direction": int(pen.direction),
                "visible_time": int(pen.visible_time),
                "start_idx": pen.start_idx,
                "end_idx": pen.end_idx,
            },
        )


@dataclass(frozen=True)
class ZhongshuProcessor:
    spec: ProcessorSpec = ProcessorSpec(factor_name="zhongshu", depends_on=("pen",))

    def build_state(self, *, confirmed_pens: list[dict], candles_up_to_head: list[Any], head_time: int) -> dict[str, Any]:
        if candles_up_to_head and int(head_time) > 0:
            return replay_zhongshu_state_with_closed_candles(
                pens=confirmed_pens,
                candles=candles_up_to_head,
                up_to_visible_time=int(head_time),
            )
        return replay_zhongshu_state(confirmed_pens)

    def update_state_from_pen(self, *, state: dict[str, Any], series_id: str, pen_payload: dict) -> tuple[FactorEventWrite | None, dict | None]:
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

    def build_alive_head(self, *, state: dict[str, Any], confirmed_pens: list[dict], up_to_visible_time: int, candles: list[Any]) -> dict[str, Any]:
        out: dict[str, Any] = {}
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


@dataclass(frozen=True)
class AnchorProcessor:
    spec: ProcessorSpec = ProcessorSpec(factor_name="anchor", depends_on=("pen", "zhongshu"))

    @staticmethod
    def pen_strength(pen: dict[str, Any]) -> float:
        try:
            return abs(float(pen.get("end_price") or 0.0) - float(pen.get("start_price") or 0.0))
        except Exception:
            return -1.0

    @staticmethod
    def beats_anchor_strength(*, candidate_strength: float, baseline_anchor_strength: float | None) -> bool:
        if baseline_anchor_strength is None:
            return True
        return float(candidate_strength) > float(baseline_anchor_strength)

    @staticmethod
    def pen_ref_from_pen(pen: dict[str, Any], *, kind: str) -> dict[str, int | str]:
        return {
            "kind": str(kind),
            "start_time": int(pen.get("start_time") or 0),
            "end_time": int(pen.get("end_time") or 0),
            "direction": int(pen.get("direction") or 0),
        }

    def maybe_pick_stronger_pen(
        self,
        *,
        candidate_pen: dict[str, Any],
        kind: str,
        baseline_anchor_strength: float | None,
        current_best_ref: dict[str, int | str] | None,
        current_best_strength: float | None,
    ) -> tuple[dict[str, int | str] | None, float | None]:
        strength = self.pen_strength(candidate_pen)
        if not self.beats_anchor_strength(
            candidate_strength=float(strength),
            baseline_anchor_strength=baseline_anchor_strength,
        ):
            return current_best_ref, current_best_strength
        if current_best_strength is None or float(strength) > float(current_best_strength):
            return self.pen_ref_from_pen(candidate_pen, kind=kind), float(strength)
        return current_best_ref, current_best_strength

    def restore_anchor_state(
        self,
        *,
        anchor_switches: list[dict[str, Any]],
        confirmed_pens: list[dict[str, Any]],
        candles: list[Any],
    ) -> tuple[dict[str, Any] | None, float | None]:
        anchor_current_ref: dict[str, Any] | None = None
        anchor_strength: float | None = None
        if anchor_switches:
            last_switch = anchor_switches[-1]
            cur = last_switch.get("new_anchor")
            if isinstance(cur, dict):
                anchor_current_ref = dict(cur)
                kind = str(cur.get("kind") or "")
                if kind == "confirmed":
                    match = next(
                        (
                            p
                            for p in reversed(confirmed_pens)
                            if int(p.get("start_time") or 0) == int(cur.get("start_time") or 0)
                            and int(p.get("end_time") or 0) == int(cur.get("end_time") or 0)
                            and int(p.get("direction") or 0) == int(cur.get("direction") or 0)
                        ),
                        None,
                    )
                    if match is not None:
                        anchor_strength = self.pen_strength(match)
                elif kind == "candidate":
                    switch_time = int(last_switch.get("switch_time") or 0)
                    if switch_time > 0:
                        pen_at_time = [p for p in confirmed_pens if int(p.get("visible_time") or 0) <= switch_time]
                        last_pen = pen_at_time[-1] if pen_at_time else None
                        candidate = build_pen_head_candidate(
                            candles=candles,
                            last_confirmed=last_pen,
                            aligned_time=int(switch_time),
                        )
                        if candidate is not None:
                            anchor_strength = self.pen_strength(candidate)

        if anchor_current_ref is None and confirmed_pens:
            last = confirmed_pens[-1]
            anchor_current_ref = self.pen_ref_from_pen(last, kind="confirmed")
            anchor_strength = self.pen_strength(last)

        return anchor_current_ref, anchor_strength

    def build_switch_event(
        self,
        *,
        series_id: str,
        switch_time: int,
        reason: str,
        old_anchor: dict[str, Any] | None,
        new_anchor: dict[str, Any],
    ) -> FactorEventWrite:
        if str(reason) == "zhongshu_entry":
            key_switch = (
                f"zhongshu_entry:{int(switch_time)}:"
                f"{int(new_anchor['start_time'])}:{int(new_anchor['end_time'])}:{int(new_anchor['direction'])}"
            )
        elif str(reason) == "strong_pen":
            key_switch = (
                f"strong_pen:{int(switch_time)}:{str(new_anchor['kind'])}:"
                f"{int(new_anchor['start_time'])}:{int(new_anchor['end_time'])}:{int(new_anchor['direction'])}"
            )
        else:
            key_switch = f"{str(reason)}:{int(switch_time)}"
        return FactorEventWrite(
            series_id=series_id,
            factor_name="anchor",
            candle_time=int(switch_time),
            kind="anchor.switch",
            event_key=key_switch,
            payload={
                "switch_time": int(switch_time),
                "reason": str(reason),
                "old_anchor": dict(old_anchor) if isinstance(old_anchor, dict) else None,
                "new_anchor": dict(new_anchor),
                "visible_time": int(switch_time),
            },
        )

    def apply_zhongshu_entry_switch(
        self,
        *,
        series_id: str,
        formed_entry: dict[str, Any],
        switch_time: int,
        old_anchor: dict[str, Any] | None,
    ) -> tuple[FactorEventWrite | None, dict[str, Any], float]:
        new_ref = self.pen_ref_from_pen(formed_entry, kind="confirmed")
        event: FactorEventWrite | None = None
        if should_append_switch(old_anchor=old_anchor, new_anchor=new_ref):
            event = self.build_switch_event(
                series_id=series_id,
                switch_time=int(switch_time),
                reason="zhongshu_entry",
                old_anchor=old_anchor,
                new_anchor=new_ref,
            )
        return event, new_ref, self.pen_strength(formed_entry)

    def apply_strong_pen_switch(
        self,
        *,
        series_id: str,
        switch_time: int,
        old_anchor: dict[str, Any] | None,
        new_anchor: dict[str, Any],
        new_anchor_strength: float,
    ) -> tuple[FactorEventWrite | None, dict[str, Any], float]:
        event: FactorEventWrite | None = None
        if should_append_switch(old_anchor=old_anchor, new_anchor=new_anchor):
            event = self.build_switch_event(
                series_id=series_id,
                switch_time=int(switch_time),
                reason="strong_pen",
                old_anchor=old_anchor,
                new_anchor=new_anchor,
            )
        return event, new_anchor, float(new_anchor_strength)


def build_default_factor_processors() -> list[FactorProcessor]:
    return [PivotProcessor(), PenProcessor(), ZhongshuProcessor(), AnchorProcessor()]


@dataclass(frozen=True)
class SliceBucketSpec:
    factor_name: str
    event_kind: str
    bucket_name: str
    sort_keys: tuple[str, str] | None = None


def build_default_slice_bucket_specs() -> tuple[SliceBucketSpec, ...]:
    return (
        SliceBucketSpec(
            factor_name="pivot",
            event_kind="pivot.major",
            bucket_name="piv_major",
            sort_keys=("visible_time", "pivot_time"),
        ),
        SliceBucketSpec(
            factor_name="pivot",
            event_kind="pivot.minor",
            bucket_name="piv_minor",
        ),
        SliceBucketSpec(
            factor_name="pen",
            event_kind="pen.confirmed",
            bucket_name="pen_confirmed",
            sort_keys=("visible_time", "start_time"),
        ),
        SliceBucketSpec(
            factor_name="zhongshu",
            event_kind="zhongshu.dead",
            bucket_name="zhongshu_dead",
        ),
        SliceBucketSpec(
            factor_name="anchor",
            event_kind="anchor.switch",
            bucket_name="anchor_switches",
            sort_keys=("visible_time", "switch_time"),
        ),
    )
