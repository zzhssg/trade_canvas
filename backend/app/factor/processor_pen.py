from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from .head_builder import build_pen_head_snapshot
from .pen_contract import (
    build_confirmed_pen_payload,
    normalize_confirmed_pen_payload,
)
from .plugin_contract import FactorCatalogSpec, FactorCatalogSubFeatureSpec, FactorPluginSpec
from .runtime_contract import FactorRuntimeContext
from .semantics import is_more_extreme_pivot
from .store import FactorEventWrite
from .pen import ConfirmedPen, PivotMajorPoint


class _PenTickState(Protocol):
    major_candidates: list[PivotMajorPoint]
    effective_pivots: list[PivotMajorPoint]
    events: list[FactorEventWrite]
    confirmed_pens: list[dict[str, Any]]
    new_confirmed_pen_payloads: list[dict[str, Any]]
    baseline_anchor_strength: float | None
    best_strong_pen_ref: dict[str, int | str] | None
    best_strong_pen_strength: float | None


class _PenBootstrapState(Protocol):
    rebuild_events: dict[str, list[dict[str, Any]]]
    confirmed_pens: list[dict[str, Any]]


class _PenHeadState(Protocol):
    confirmed_pens: list[dict[str, Any]]
    effective_pivots: list[PivotMajorPoint]
    candles: list[Any]
    up_to: int


@dataclass(frozen=True)
class PenProcessor:
    spec: FactorPluginSpec = FactorPluginSpec(
        factor_name="pen",
        depends_on=("pivot",),
        catalog=FactorCatalogSpec(
            label="Pen",
            default_visible=True,
            sub_features=(
                FactorCatalogSubFeatureSpec(key="pen.confirmed", label="Confirmed", default_visible=True),
                FactorCatalogSubFeatureSpec(key="pen.extending", label="Extending", default_visible=True),
                FactorCatalogSubFeatureSpec(key="pen.candidate", label="Candidate", default_visible=True),
            ),
        ),
    )

    def run_tick(self, *, series_id: str, state: _PenTickState, runtime: FactorRuntimeContext) -> None:
        anchor_processor = runtime.anchor_processor
        for pivot in state.major_candidates:
            confirmed = self.append_pivot_and_confirm(state.effective_pivots, pivot)
            for pen in confirmed:
                pen_payload = dict(build_confirmed_pen_payload(pen))
                pen_event = self.build_confirmed_event(series_id=series_id, pen=pen, payload=pen_payload)
                state.events.append(pen_event)
                state.confirmed_pens.append(pen_payload)
                state.new_confirmed_pen_payloads.append(pen_payload)
                if anchor_processor is None:
                    continue
                state.best_strong_pen_ref, state.best_strong_pen_strength = anchor_processor.maybe_pick_stronger_pen(
                    candidate_pen=pen_payload,
                    kind="confirmed",
                    baseline_anchor_strength=state.baseline_anchor_strength,
                    current_best_ref=state.best_strong_pen_ref,
                    current_best_strength=state.best_strong_pen_strength,
                )

    def collect_rebuild_event(self, *, kind: str, payload: dict[str, Any], events: list[dict[str, Any]]) -> None:
        if str(kind) != "pen.confirmed":
            return
        events.append(dict(payload))

    def sort_rebuild_events(self, *, events: list[dict[str, Any]]) -> None:
        events.sort(key=lambda d: (int(d.get("visible_time") or 0), int(d.get("start_time") or 0)))

    def bootstrap_from_history(self, *, series_id: str, state: _PenBootstrapState, runtime: FactorRuntimeContext) -> None:
        _ = series_id
        _ = runtime
        raw_items = list(state.rebuild_events.get(self.spec.factor_name) or [])
        normalized: list[dict[str, Any]] = []
        for item in raw_items:
            if isinstance(item, dict):
                normalized.append(dict(normalize_confirmed_pen_payload(item)))
        state.confirmed_pens = normalized

    def build_head_snapshot(self, *, series_id: str, state: _PenHeadState, runtime: FactorRuntimeContext) -> dict[str, Any] | None:
        _ = series_id
        _ = runtime
        return build_pen_head_snapshot(
            confirmed_pens=state.confirmed_pens,
            effective_pivots=state.effective_pivots,
            candles=state.candles,
            aligned_time=int(state.up_to),
        )

    def append_pivot_and_confirm(self, effective: list[PivotMajorPoint], new_pivot: PivotMajorPoint) -> list[ConfirmedPen]:
        if not effective:
            effective.append(new_pivot)
            return []

        last = effective[-1]
        if new_pivot.direction == last.direction:
            if is_more_extreme_pivot(last, new_pivot):
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

    def build_confirmed_event(
        self,
        *,
        series_id: str,
        pen: ConfirmedPen,
        payload: dict[str, Any] | None = None,
    ) -> FactorEventWrite:
        pen_payload = payload if payload is not None else dict(build_confirmed_pen_payload(pen))
        key = (
            f"confirmed:{int(pen_payload['start_time'])}:"
            f"{int(pen_payload['end_time'])}:{int(pen_payload['direction'])}"
        )
        return FactorEventWrite(
            series_id=series_id,
            factor_name="pen",
            candle_time=int(pen.visible_time),
            kind="pen.confirmed",
            event_key=key,
            payload=pen_payload,
        )
