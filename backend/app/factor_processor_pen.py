from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from .factor_plugin_contract import FactorCatalogSpec, FactorCatalogSubFeatureSpec
from .factor_registry import ProcessorSpec
from .factor_runtime_contract import FactorRuntimeContext
from .factor_semantics import is_more_extreme_pivot
from .factor_slices import build_pen_head_preview
from .factor_store import FactorEventWrite
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
    spec: ProcessorSpec = ProcessorSpec(
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
                pen_event = self.build_confirmed_event(series_id=series_id, pen=pen)
                pen_payload = dict(pen_event.payload)
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
        state.confirmed_pens = list(state.rebuild_events.get(self.spec.factor_name) or [])

    def build_head_snapshot(self, *, series_id: str, state: _PenHeadState, runtime: FactorRuntimeContext) -> dict[str, Any] | None:
        _ = series_id
        _ = runtime
        if not state.confirmed_pens:
            return None
        major_for_head = [
            {
                "pivot_time": int(p.pivot_time),
                "pivot_price": float(p.pivot_price),
                "direction": str(p.direction),
                "visible_time": int(p.visible_time),
            }
            for p in state.effective_pivots
        ]
        preview = build_pen_head_preview(
            candles=state.candles,
            major_pivots=major_for_head,
            aligned_time=int(state.up_to),
        )
        pen_head: dict[str, Any] = {}
        for key in ("extending", "candidate"):
            value = preview.get(key)
            if isinstance(value, dict):
                pen_head[key] = value
        return pen_head

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
