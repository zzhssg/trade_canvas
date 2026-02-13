from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Protocol

from .pen_contract import (
    build_anchor_pen_ref,
    normalize_anchor_switch_payload,
    pen_strength as calc_pen_strength,
)
from .plugin_contract import FactorCatalogSpec, FactorCatalogSubFeatureSpec, FactorPluginSpec
from .processor_anchor_switches import (
    apply_strong_pen_switch as apply_strong_pen_switch_impl,
    apply_zhongshu_entry_switch as apply_zhongshu_entry_switch_impl,
    build_confirmed_pen_ref_index as build_confirmed_pen_ref_index_impl,
    build_switch_event as build_switch_event_impl,
    last_confirmed_pen_before_or_at as last_confirmed_pen_before_or_at_impl,
    pen_ref_key_from_ref as pen_ref_key_from_ref_impl,
)
from .runtime_contract import FactorRuntimeContext
from .slices import build_pen_head_candidate
from .store import FactorEventWrite

class _AnchorTickState(Protocol):
    formed_entries: list[dict[str, Any]]
    visible_time: int
    anchor_current_ref: dict[str, Any] | None
    anchor_strength: float | None
    events: list[FactorEventWrite]
    confirmed_pens: list[dict[str, Any]]
    candles: list[Any]
    baseline_anchor_strength: float | None
    best_strong_pen_ref: dict[str, int | str] | None
    best_strong_pen_strength: float | None


class _AnchorBootstrapState(Protocol):
    rebuild_events: dict[str, list[dict[str, Any]]]
    confirmed_pens: list[dict[str, Any]]
    candles: list[Any]
    anchor_current_ref: dict[str, Any] | None
    anchor_strength: float | None


class _AnchorHeadState(Protocol):
    confirmed_pens: list[dict[str, Any]]
    anchor_current_ref: dict[str, Any] | None


@dataclass(frozen=True)
class AnchorProcessor:
    spec: FactorPluginSpec = FactorPluginSpec(
        factor_name="anchor",
        depends_on=("pen", "zhongshu"),
        catalog=FactorCatalogSpec(
            label="Anchor",
            default_visible=True,
            sub_features=(
                FactorCatalogSubFeatureSpec(key="anchor.current", label="Current", default_visible=True),
                FactorCatalogSubFeatureSpec(key="anchor.history", label="History", default_visible=True),
                FactorCatalogSubFeatureSpec(key="anchor.switch", label="Switches", default_visible=True),
            ),
        ),
    )

    def run_tick(self, *, series_id: str, state: _AnchorTickState, runtime: FactorRuntimeContext) -> None:
        _ = runtime
        for formed_entry in state.formed_entries:
            switch_event, state.anchor_current_ref, state.anchor_strength = self.apply_zhongshu_entry_switch(
                series_id=series_id,
                formed_entry=formed_entry,
                switch_time=int(state.visible_time),
                old_anchor=state.anchor_current_ref,
            )
            if switch_event is not None:
                state.events.append(switch_event)

        last_pen = state.confirmed_pens[-1] if state.confirmed_pens else None
        candidate = build_pen_head_candidate(
            candles=state.candles,
            last_confirmed=last_pen,
            aligned_time=int(state.visible_time),
        )
        if candidate is not None:
            state.best_strong_pen_ref, state.best_strong_pen_strength = self.maybe_pick_stronger_pen(
                candidate_pen=candidate,
                kind="candidate",
                baseline_anchor_strength=state.baseline_anchor_strength,
                current_best_ref=state.best_strong_pen_ref,
                current_best_strength=state.best_strong_pen_strength,
            )

        if state.best_strong_pen_ref is None or state.best_strong_pen_strength is None:
            return
        switch_event, state.anchor_current_ref, state.anchor_strength = self.apply_strong_pen_switch(
            series_id=series_id,
            switch_time=int(state.visible_time),
            old_anchor=state.anchor_current_ref,
            new_anchor=state.best_strong_pen_ref,
            new_anchor_strength=float(state.best_strong_pen_strength),
        )
        if switch_event is not None:
            state.events.append(switch_event)

    def collect_rebuild_event(self, *, kind: str, payload: dict[str, Any], events: list[dict[str, Any]]) -> None:
        if str(kind) != "anchor.switch":
            return
        normalized = normalize_anchor_switch_payload(payload)
        events.append(dict(normalized) if normalized is not None else dict(payload))

    def sort_rebuild_events(self, *, events: list[dict[str, Any]]) -> None:
        events.sort(key=lambda d: (int(d.get("visible_time") or 0), int(d.get("switch_time") or 0)))

    def bootstrap_from_history(
        self,
        *,
        series_id: str,
        state: _AnchorBootstrapState,
        runtime: FactorRuntimeContext,
    ) -> None:
        _ = series_id
        _ = runtime
        anchor_current_ref, anchor_strength = self.restore_anchor_state(
            anchor_switches=list(state.rebuild_events.get(self.spec.factor_name) or []),
            confirmed_pens=state.confirmed_pens,
            candles=state.candles,
        )
        state.anchor_current_ref = anchor_current_ref
        state.anchor_strength = anchor_strength

    def build_head_snapshot(
        self,
        *,
        series_id: str,
        state: _AnchorHeadState,
        runtime: FactorRuntimeContext,
    ) -> dict[str, Any] | None:
        _ = series_id
        _ = runtime
        if not state.confirmed_pens and state.anchor_current_ref is None:
            return None
        return {"current_anchor_ref": state.anchor_current_ref}

    @staticmethod
    def pen_strength(pen: Mapping[str, Any]) -> float:
        return float(calc_pen_strength(pen))

    @staticmethod
    def beats_anchor_strength(*, candidate_strength: float, baseline_anchor_strength: float | None) -> bool:
        if baseline_anchor_strength is None:
            return True
        return float(candidate_strength) > float(baseline_anchor_strength)

    @staticmethod
    def pen_ref_from_pen(pen: Mapping[str, Any], *, kind: str) -> dict[str, int | str]:
        ref = build_anchor_pen_ref(pen, kind=kind)
        return {
            "kind": str(ref["kind"]),
            "start_time": int(ref["start_time"]),
            "end_time": int(ref["end_time"]),
            "direction": int(ref["direction"]),
        }

    def _build_confirmed_pen_ref_index(
        self,
        confirmed_pens: list[dict[str, Any]],
    ) -> dict[tuple[int, int, int], dict[str, Any]]:
        return build_confirmed_pen_ref_index_impl(confirmed_pens)

    def _last_confirmed_pen_before_or_at(
        self,
        *,
        confirmed_pens: list[dict[str, Any]],
        switch_time: int,
        visible_times: list[int] | None = None,
    ) -> dict[str, Any] | None:
        return last_confirmed_pen_before_or_at_impl(
            confirmed_pens=confirmed_pens,
            switch_time=int(switch_time),
            visible_times=visible_times,
        )

    def maybe_pick_stronger_pen(
        self,
        *,
        candidate_pen: Mapping[str, Any],
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
        confirmed_pen_ref_index: dict[tuple[int, int, int], dict[str, Any]] | None = None
        confirmed_visible_times: list[int] | None = None
        if anchor_switches:
            normalized_switch = normalize_anchor_switch_payload(anchor_switches[-1])
            if normalized_switch is not None:
                cur = normalized_switch["new_anchor"]
                anchor_current_ref = self.pen_ref_from_pen(cur, kind=str(cur.get("kind") or ""))
                kind = str(cur.get("kind") or "")
                if kind == "confirmed":
                    if confirmed_pen_ref_index is None:
                        confirmed_pen_ref_index = build_confirmed_pen_ref_index_impl(confirmed_pens)
                    key = pen_ref_key_from_ref_impl(cur)
                    match = confirmed_pen_ref_index.get(key) if key is not None else None
                    if match is not None:
                        anchor_strength = self.pen_strength(match)
                elif kind == "candidate":
                    switch_time = int(normalized_switch["switch_time"])
                    if switch_time > 0:
                        if confirmed_visible_times is None:
                            confirmed_visible_times = [int(p.get("visible_time") or 0) for p in confirmed_pens]
                        last_pen = last_confirmed_pen_before_or_at_impl(
                            confirmed_pens=confirmed_pens,
                            switch_time=int(switch_time),
                            visible_times=confirmed_visible_times,
                        )
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
        return build_switch_event_impl(
            series_id=series_id,
            switch_time=int(switch_time),
            reason=str(reason),
            old_anchor=old_anchor,
            new_anchor=new_anchor,
        )

    def apply_zhongshu_entry_switch(
        self,
        *,
        series_id: str,
        formed_entry: dict[str, Any],
        switch_time: int,
        old_anchor: dict[str, Any] | None,
    ) -> tuple[FactorEventWrite | None, dict[str, Any], float]:
        return apply_zhongshu_entry_switch_impl(
            series_id=series_id,
            formed_entry=formed_entry,
            switch_time=int(switch_time),
            old_anchor=old_anchor,
            pen_ref_from_pen=lambda pen, kind: self.pen_ref_from_pen(pen, kind=kind),
            pen_strength=self.pen_strength,
        )

    def apply_strong_pen_switch(
        self,
        *,
        series_id: str,
        switch_time: int,
        old_anchor: dict[str, Any] | None,
        new_anchor: dict[str, Any],
        new_anchor_strength: float,
    ) -> tuple[FactorEventWrite | None, dict[str, Any], float]:
        return apply_strong_pen_switch_impl(
            series_id=series_id,
            switch_time=int(switch_time),
            old_anchor=old_anchor,
            new_anchor=new_anchor,
            new_anchor_strength=float(new_anchor_strength),
        )
