from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from .factor_plugin_contract import FactorCatalogSpec, FactorCatalogSubFeatureSpec
from .factor_registry import ProcessorSpec
from .factor_runtime_contract import FactorRuntimeContext
from .factor_semantics import is_more_extreme_pivot
from .factor_store import FactorEventWrite
from .pen import PivotMajorPoint


class _PivotSettingsLike(Protocol):
    pivot_window_major: int
    pivot_window_minor: int


class _PivotTickState(Protocol):
    visible_time: int
    settings: _PivotSettingsLike
    tf_s: int
    candles: list[Any]
    time_to_idx: dict[int, int]
    major_candidates: list[PivotMajorPoint]
    events: list[FactorEventWrite]
    last_major_idx: int | None


class _PivotBootstrapState(Protocol):
    rebuild_events: dict[str, list[dict[str, Any]]]
    effective_pivots: list[PivotMajorPoint]
    time_to_idx: dict[int, int]
    last_major_idx: int | None


@dataclass(frozen=True)
class PivotProcessor:
    spec: ProcessorSpec = ProcessorSpec(
        factor_name="pivot",
        depends_on=(),
        catalog=FactorCatalogSpec(
            label="Pivot",
            default_visible=True,
            sub_features=(
                FactorCatalogSubFeatureSpec(key="pivot.major", label="Major", default_visible=True),
                FactorCatalogSubFeatureSpec(key="pivot.minor", label="Minor", default_visible=False),
            ),
        ),
    )

    def run_tick(self, *, series_id: str, state: _PivotTickState, runtime: FactorRuntimeContext) -> None:
        _ = runtime
        pivot_time_major = int(state.visible_time) - int(state.settings.pivot_window_major) * int(state.tf_s)
        major_candidates = self.compute_major_candidates(
            candles=state.candles,
            time_to_idx=state.time_to_idx,
            pivot_time=int(pivot_time_major),
            visible_time=int(state.visible_time),
            window=int(state.settings.pivot_window_major),
        )
        major_candidates.sort(key=lambda p: (int(p.pivot_time), str(p.direction)))
        state.major_candidates = major_candidates
        for pivot in major_candidates:
            state.events.append(
                self.build_major_event(
                    series_id=series_id,
                    pivot=pivot,
                    window=int(state.settings.pivot_window_major),
                )
            )
            state.last_major_idx = int(pivot.pivot_idx) if pivot.pivot_idx is not None else state.last_major_idx

        pivot_time_minor = int(state.visible_time) - int(state.settings.pivot_window_minor) * int(state.tf_s)
        minor_candidates = self.compute_minor_candidates(
            candles=state.candles,
            time_to_idx=state.time_to_idx,
            pivot_time=int(pivot_time_minor),
            visible_time=int(state.visible_time),
            window=int(state.settings.pivot_window_minor),
            segment_start_idx=state.last_major_idx,
        )
        minor_candidates.sort(key=lambda p: (int(p.pivot_time), str(p.direction)))
        for pivot in minor_candidates:
            state.events.append(
                self.build_minor_event(
                    series_id=series_id,
                    pivot=pivot,
                    window=int(state.settings.pivot_window_minor),
                )
            )

    def collect_rebuild_event(self, *, kind: str, payload: dict[str, Any], events: list[dict[str, Any]]) -> None:
        if str(kind) != "pivot.major":
            return
        events.append(dict(payload))

    def sort_rebuild_events(self, *, events: list[dict[str, Any]]) -> None:
        events.sort(key=lambda d: (int(d.get("visible_time") or 0), int(d.get("pivot_time") or 0)))

    def rebuild_effective_pivots(self, pivots: list[dict[str, Any]]) -> list[PivotMajorPoint]:
        items: list[PivotMajorPoint] = []
        for payload in pivots:
            try:
                raw_idx = payload.get("pivot_idx")
                pivot_idx = int(raw_idx) if raw_idx is not None else None
                items.append(
                    PivotMajorPoint(
                        pivot_time=int(payload.get("pivot_time") or 0),
                        pivot_price=float(payload.get("pivot_price") or 0.0),
                        direction=str(payload.get("direction") or ""),
                        visible_time=int(payload.get("visible_time") or 0),
                        pivot_idx=pivot_idx,
                    )
                )
            except Exception:
                continue
        items.sort(key=lambda i: (int(i.visible_time), int(i.pivot_time)))

        effective: list[PivotMajorPoint] = []
        for point in items:
            if not effective:
                effective.append(point)
                continue
            last = effective[-1]
            if point.direction == last.direction:
                if is_more_extreme_pivot(last, point):
                    effective[-1] = point
                continue
            effective.append(point)
        return effective

    @staticmethod
    def resolve_last_major_idx(*, effective_pivots: list[PivotMajorPoint], time_to_idx: dict[int, int]) -> int | None:
        if not effective_pivots:
            return None
        last = effective_pivots[-1]
        if last.pivot_idx is not None:
            return int(last.pivot_idx)
        return time_to_idx.get(int(last.pivot_time))

    def bootstrap_from_history(
        self,
        *,
        series_id: str,
        state: _PivotBootstrapState,
        runtime: FactorRuntimeContext,
    ) -> None:
        _ = series_id
        _ = runtime
        events = list(state.rebuild_events.get(self.spec.factor_name) or [])
        state.effective_pivots = self.rebuild_effective_pivots(events)
        state.last_major_idx = self.resolve_last_major_idx(
            effective_pivots=state.effective_pivots,
            time_to_idx=state.time_to_idx,
        )

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
