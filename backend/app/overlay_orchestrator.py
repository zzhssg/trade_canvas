from __future__ import annotations

import time
from dataclasses import dataclass
from typing import cast

from .debug_hub import DebugHub
from .factor_graph import FactorGraph, FactorSpec
from .factor_plugin_registry import FactorPluginRegistry
from .factor_store import FactorStore
from .overlay_store import OverlayStore
from .overlay_renderer_plugins import (
    OverlayRenderContext,
    OverlayRenderOutput,
    OverlayRendererPlugin,
    build_default_overlay_render_plugins,
    build_overlay_event_bucket_config,
    collect_overlay_event_buckets,
)
from .store import CandleStore
from .timeframe import series_id_timeframe, timeframe_to_seconds


@dataclass(frozen=True)
class OverlaySettings:
    ingest_enabled: bool = True
    window_candles: int = 2000


class OverlayOrchestrator:
    """
    v0 overlay orchestrator:
    - Reads FactorStore (pivot.major/minor, pen.confirmed)
    - Builds overlay instructions and persists them to OverlayStore as versioned defs.
    - instruction_catalog_patch is derived from version_id cursor.
    """

    def __init__(
        self,
        *,
        candle_store: CandleStore,
        factor_store: FactorStore,
        overlay_store: OverlayStore,
        settings: OverlaySettings | None = None,
    ) -> None:
        self._candle_store = candle_store
        self._factor_store = factor_store
        self._overlay_store = overlay_store
        cfg = settings or OverlaySettings()
        self._settings = OverlaySettings(
            ingest_enabled=bool(cfg.ingest_enabled),
            window_candles=max(100, int(cfg.window_candles)),
        )
        self._debug_hub: DebugHub | None = None
        self._renderer_registry = FactorPluginRegistry(list(build_default_overlay_render_plugins()))
        self._renderer_graph = FactorGraph(
            [FactorSpec(factor_name=s.factor_name, depends_on=s.depends_on) for s in self._renderer_registry.specs()]
        )
        self._topo_renderers = tuple(
            cast(OverlayRendererPlugin, self._renderer_registry.require(name)) for name in self._renderer_graph.topo_order
        )
        by_kind, sort_keys, bucket_names = build_overlay_event_bucket_config(self._topo_renderers)
        self._event_bucket_by_kind = by_kind
        self._event_bucket_sort_keys = sort_keys
        self._event_bucket_names = bucket_names

    def set_debug_hub(self, hub: DebugHub | None) -> None:
        self._debug_hub = hub

    def enabled(self) -> bool:
        return bool(self._settings.ingest_enabled)

    def reset_series(self, *, series_id: str) -> None:
        with self._overlay_store.connect() as conn:
            self._overlay_store.clear_series_in_conn(conn, series_id=series_id)
            conn.commit()

    def _load_window_candles(self) -> int:
        return int(self._settings.window_candles)

    def _run_render_plugins(self, *, ctx: OverlayRenderContext) -> OverlayRenderOutput:
        merged = OverlayRenderOutput()
        for plugin in self._topo_renderers:
            rendered = plugin.render(ctx=ctx)
            if rendered.marker_defs:
                merged.marker_defs.extend(rendered.marker_defs)
            if rendered.polyline_defs:
                merged.polyline_defs.extend(rendered.polyline_defs)
            merged.pen_points_count = max(int(merged.pen_points_count), int(rendered.pen_points_count))
        return merged

    def ingest_closed(self, *, series_id: str, up_to_candle_time: int) -> None:
        """
        Build overlay instructions up to `up_to_candle_time` (closed only).
        """
        t0 = time.perf_counter()
        if not self.enabled():
            return

        to_time = int(up_to_candle_time or 0)
        if to_time <= 0:
            return

        tf_s = timeframe_to_seconds(series_id_timeframe(series_id))
        window_candles = self._load_window_candles()
        cutoff_time = max(0, to_time - int(window_candles) * int(tf_s))

        factor_rows = self._factor_store.get_events_between_times(
            series_id=series_id,
            factor_name=None,
            start_candle_time=int(cutoff_time),
            end_candle_time=int(to_time),
            limit=50000,
        )
        buckets = collect_overlay_event_buckets(
            rows=factor_rows,
            event_bucket_by_kind=self._event_bucket_by_kind,
            event_bucket_sort_keys=self._event_bucket_sort_keys,
            event_bucket_names=self._event_bucket_names,
        )

        candles = self._candle_store.get_closed_between_times(
            series_id,
            start_time=int(cutoff_time),
            end_time=int(to_time),
            limit=int(window_candles) + 10,
        )
        rendered = self._run_render_plugins(
            ctx=OverlayRenderContext(
                series_id=series_id,
                to_time=int(to_time),
                cutoff_time=int(cutoff_time),
                window_candles=int(window_candles),
                candles=candles,
                buckets=buckets,
            )
        )
        marker_defs = rendered.marker_defs
        polyline_defs = rendered.polyline_defs

        with self._overlay_store.connect() as conn:
            before_changes = int(conn.total_changes)
            for instruction_id, kind, visible_time, payload in marker_defs:
                prev = self._overlay_store.get_latest_def_for_instruction_in_conn(
                    conn,
                    series_id=series_id,
                    instruction_id=instruction_id,
                )
                if prev == payload:
                    continue
                self._overlay_store.insert_instruction_version_in_conn(
                    conn,
                    series_id=series_id,
                    instruction_id=instruction_id,
                    kind=kind,
                    visible_time=visible_time,
                    payload=payload,
                )

            for instruction_id, visible_time, payload in polyline_defs:
                prev = self._overlay_store.get_latest_def_for_instruction_in_conn(
                    conn,
                    series_id=series_id,
                    instruction_id=instruction_id,
                )
                if prev == payload:
                    continue
                self._overlay_store.insert_instruction_version_in_conn(
                    conn,
                    series_id=series_id,
                    instruction_id=instruction_id,
                    kind="polyline",
                    visible_time=int(visible_time),
                    payload=payload,
                )

            self._overlay_store.upsert_head_time_in_conn(conn, series_id=series_id, head_time=int(to_time))
            conn.commit()
            wrote = int(conn.total_changes) - before_changes

        if self._debug_hub is not None:
            self._debug_hub.emit(
                pipe="write",
                event="write.overlay.ingest_done",
                series_id=series_id,
                message="overlay ingest done",
                data={
                    "up_to_candle_time": int(to_time),
                    "cutoff_time": int(cutoff_time),
                    "factor_rows": int(len(factor_rows)),
                    "marker_defs": int(len(marker_defs)),
                    "pen_points": int(rendered.pen_points_count),
                    "polyline_defs": int(len(polyline_defs)),
                    "db_changes": int(wrote),
                    "duration_ms": int((time.perf_counter() - t0) * 1000),
                },
            )
