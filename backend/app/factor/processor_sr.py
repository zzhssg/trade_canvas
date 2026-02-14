from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any, Protocol

from .plugin_contract import FactorCatalogSpec, FactorCatalogSubFeatureSpec, FactorPluginSpec
from .runtime_contract import FactorRuntimeContext
from .sr_component import SrParams, build_sr_snapshot
from .store import FactorEventWrite
from .pen import PivotMajorPoint


class _SrTickState(Protocol):
    visible_time: int
    candles: list[Any]
    time_to_idx: dict[int, int]
    major_candidates: list[PivotMajorPoint]
    events: list[FactorEventWrite]
    sr_major_pivots: list[dict[str, Any]]
    sr_snapshot: dict[str, Any]


class _SrBootstrapState(Protocol):
    head_time: int
    candles: list[Any]
    time_to_idx: dict[int, int]
    rebuild_events: dict[str, list[dict[str, Any]]]
    sr_major_pivots: list[dict[str, Any]]
    sr_snapshot: dict[str, Any]


class _SrHeadState(Protocol):
    sr_snapshot: dict[str, Any]


@dataclass(frozen=True)
class SrProcessor:
    spec: FactorPluginSpec = FactorPluginSpec(
        factor_name="sr",
        depends_on=("pivot",),
        catalog=FactorCatalogSpec(
            label="SR",
            default_visible=True,
            sub_features=(
                FactorCatalogSubFeatureSpec(key="sr.active", label="Active", default_visible=True),
                FactorCatalogSubFeatureSpec(key="sr.broken", label="Broken", default_visible=False),
            ),
        ),
    )
    params: SrParams = SrParams()

    def run_tick(self, *, series_id: str, state: _SrTickState, runtime: FactorRuntimeContext) -> None:
        _ = runtime
        new_major_count = self._append_new_major_pivots(
            major_pivots=state.sr_major_pivots,
            major_candidates=state.major_candidates,
        )
        if new_major_count <= 0:
            return

        snapshot = build_sr_snapshot(
            candles=state.candles,
            major_pivots=state.sr_major_pivots,
            time_to_idx=state.time_to_idx,
            params=self.params,
        )
        snapshot_payload = {
            "visible_time": int(state.visible_time),
            "algorithm": str(snapshot.get("algorithm") or ""),
            "levels": list(snapshot.get("levels") or []),
            "pivots": list(snapshot.get("pivots") or []),
        }
        state.sr_snapshot = snapshot_payload
        state.events.append(
            self._build_snapshot_event(
                series_id=series_id,
                visible_time=int(state.visible_time),
                snapshot=snapshot_payload,
            )
        )

    def collect_rebuild_event(self, *, kind: str, payload: dict[str, Any], events: list[dict[str, Any]]) -> None:
        if str(kind) != "sr.snapshot":
            return
        events.append(dict(payload))

    def sort_rebuild_events(self, *, events: list[dict[str, Any]]) -> None:
        events.sort(key=lambda item: int(item.get("visible_time") or 0))

    def bootstrap_from_history(self, *, series_id: str, state: _SrBootstrapState, runtime: FactorRuntimeContext) -> None:
        _ = series_id
        _ = runtime
        state.sr_major_pivots = self._major_pivots_from_rebuild_events(
            pivot_events=list(state.rebuild_events.get("pivot") or []),
            head_time=int(state.head_time),
        )
        snapshot_events = list(state.rebuild_events.get(self.spec.factor_name) or [])
        if snapshot_events:
            state.sr_snapshot = self._normalize_snapshot_payload(snapshot_events[-1])
            return

        if len(state.sr_major_pivots) < 2:
            state.sr_snapshot = {}
            return

        snapshot = build_sr_snapshot(
            candles=state.candles,
            major_pivots=state.sr_major_pivots,
            time_to_idx=state.time_to_idx,
            params=self.params,
        )
        state.sr_snapshot = {
            "visible_time": int(state.head_time),
            "algorithm": str(snapshot.get("algorithm") or ""),
            "levels": list(snapshot.get("levels") or []),
            "pivots": list(snapshot.get("pivots") or []),
        }

    def build_head_snapshot(
        self,
        *,
        series_id: str,
        state: _SrHeadState,
        runtime: FactorRuntimeContext,
    ) -> dict[str, Any] | None:
        _ = series_id
        _ = runtime
        snapshot = dict(state.sr_snapshot or {})
        if not snapshot:
            return None
        return {
            "algorithm": str(snapshot.get("algorithm") or ""),
            "levels": list(snapshot.get("levels") or []),
            "pivots": list(snapshot.get("pivots") or []),
        }

    def _append_new_major_pivots(
        self,
        *,
        major_pivots: list[dict[str, Any]],
        major_candidates: list[PivotMajorPoint],
    ) -> int:
        if not major_candidates:
            return 0
        existing = {
            (
                int(item.get("pivot_time") or 0),
                str(item.get("direction") or ""),
                self._pivot_idx(item) if self._pivot_idx(item) is not None else -1,
            )
            for item in major_pivots
        }
        appended = 0
        for pivot in major_candidates:
            key = (
                int(pivot.pivot_time),
                str(pivot.direction),
                int(pivot.pivot_idx) if pivot.pivot_idx is not None else -1,
            )
            if key in existing:
                continue
            major_pivots.append(
                {
                    "pivot_time": int(pivot.pivot_time),
                    "pivot_price": float(pivot.pivot_price),
                    "direction": str(pivot.direction),
                    "visible_time": int(pivot.visible_time),
                    "pivot_idx": int(pivot.pivot_idx) if pivot.pivot_idx is not None else None,
                }
            )
            existing.add(key)
            appended += 1
        major_pivots.sort(key=lambda item: (int(item.get("visible_time") or 0), int(item.get("pivot_time") or 0)))
        return int(appended)

    def _major_pivots_from_rebuild_events(self, *, pivot_events: list[dict[str, Any]], head_time: int) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for item in pivot_events:
            visible_time = int(item.get("visible_time") or 0)
            if visible_time <= 0 or visible_time > int(head_time):
                continue
            pivot_time = int(item.get("pivot_time") or 0)
            direction = str(item.get("direction") or "")
            if pivot_time <= 0 or direction not in {"support", "resistance"}:
                continue
            pivot_idx = self._pivot_idx(item)
            out.append(
                {
                    "pivot_time": int(pivot_time),
                    "pivot_price": float(item.get("pivot_price") or 0.0),
                    "direction": direction,
                    "visible_time": int(visible_time),
                    "pivot_idx": pivot_idx,
                }
            )
        out.sort(key=lambda row: (int(row.get("visible_time") or 0), int(row.get("pivot_time") or 0)))
        return out

    @staticmethod
    def _pivot_idx(item: dict[str, Any]) -> int | None:
        raw = item.get("pivot_idx")
        if raw is None:
            return None
        try:
            return int(raw)
        except (TypeError, ValueError):
            return None

    def _normalize_snapshot_payload(self, payload: dict[str, Any]) -> dict[str, Any]:
        return {
            "visible_time": int(payload.get("visible_time") or 0),
            "algorithm": str(payload.get("algorithm") or ""),
            "levels": list(payload.get("levels") or []),
            "pivots": list(payload.get("pivots") or []),
        }

    def _build_snapshot_event(self, *, series_id: str, visible_time: int, snapshot: dict[str, Any]) -> FactorEventWrite:
        levels = list(snapshot.get("levels") or [])
        token = ";".join(
            f"{str(level.get('status') or '')}:{str(level.get('type') or '')}:{float(level.get('price') or 0.0):.8f}:"
            f"{int(level.get('last_time') or 0)}"
            for level in levels[:10]
        )
        digest = hashlib.sha1(token.encode("utf-8")).hexdigest()[:12] if token else "none"
        event_key = f"snapshot:{int(visible_time)}:{len(levels)}:{digest}"
        return FactorEventWrite(
            series_id=series_id,
            factor_name=self.spec.factor_name,
            candle_time=int(visible_time),
            kind="sr.snapshot",
            event_key=event_key,
            payload=dict(snapshot),
        )
