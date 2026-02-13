from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Protocol, cast

from ..debug.hub import DebugHub
from ..factor.graph import FactorGraph, FactorSpec
from ..factor.plugin_registry import FactorPluginRegistry
from ..factor.store import FactorStore
from ..store import CandleStore
from ..timeframe import series_id_timeframe, timeframe_to_seconds
from .ingest_reader import OverlayIngestInput, OverlayIngestReader
from .ingest_writer import OverlayInstructionWriter
from .renderer_plugins import (
    OverlayRenderContext,
    OverlayRenderOutput,
    OverlayRendererPlugin,
    build_default_overlay_render_plugins,
    build_overlay_event_bucket_config,
)
from .store import OverlayStore


@dataclass(frozen=True)
class OverlaySettings:
    ingest_enabled: bool = True
    window_candles: int = 2000


class OverlayIngestReaderLike(Protocol):
    def read(
        self,
        *,
        series_id: str,
        to_time: int,
        tf_s: int,
        window_candles: int,
    ) -> OverlayIngestInput: ...


class OverlayInstructionWriterLike(Protocol):
    def persist(
        self,
        *,
        series_id: str,
        to_time: int,
        marker_defs: list[tuple[str, str, int, dict]],
        polyline_defs: list[tuple[str, int, dict]],
    ) -> int: ...


class OverlayOrchestrator:
    """
    v0 overlay orchestrator:
    - Delegates window/event loading to OverlayIngestReader.
    - Builds overlay instructions via renderer plugins.
    - Persists deduplicated instruction versions via OverlayInstructionWriter.
    - instruction_catalog_patch is derived from version_id cursor.
    """

    def __init__(
        self,
        *,
        candle_store: CandleStore,
        factor_store: FactorStore,
        overlay_store: OverlayStore,
        settings: OverlaySettings | None = None,
        ingest_reader: OverlayIngestReaderLike | None = None,
        instruction_writer: OverlayInstructionWriterLike | None = None,
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
        self._ingest_reader = ingest_reader or OverlayIngestReader(
            candle_store=self._candle_store,
            factor_store=self._factor_store,
            event_bucket_by_kind=self._event_bucket_by_kind,
            event_bucket_sort_keys=self._event_bucket_sort_keys,
            event_bucket_names=self._event_bucket_names,
        )
        self._instruction_writer = instruction_writer or OverlayInstructionWriter(overlay_store=self._overlay_store)

    def set_debug_hub(self, hub: DebugHub | None) -> None:
        self._debug_hub = hub

    def enabled(self) -> bool:
        return bool(self._settings.ingest_enabled)

    def head_time(self, series_id: str) -> int | None:
        return self._overlay_store.head_time(series_id)

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
        ingest_input = self._ingest_reader.read(
            series_id=series_id,
            to_time=int(to_time),
            tf_s=int(tf_s),
            window_candles=int(window_candles),
        )
        rendered = self._run_render_plugins(
            ctx=OverlayRenderContext(
                series_id=series_id,
                to_time=int(to_time),
                cutoff_time=int(ingest_input.cutoff_time),
                window_candles=int(ingest_input.window_candles),
                candles=ingest_input.candles,
                buckets=ingest_input.buckets,
            )
        )
        marker_defs = rendered.marker_defs
        polyline_defs = rendered.polyline_defs
        wrote = self._instruction_writer.persist(
            series_id=series_id,
            to_time=int(to_time),
            marker_defs=marker_defs,
            polyline_defs=polyline_defs,
        )

        if self._debug_hub is not None:
            self._debug_hub.emit(
                pipe="write",
                event="write.overlay.ingest_done",
                series_id=series_id,
                message="overlay ingest done",
                data={
                    "up_to_candle_time": int(to_time),
                    "cutoff_time": int(ingest_input.cutoff_time),
                    "factor_rows": int(len(ingest_input.factor_rows)),
                    "marker_defs": int(len(marker_defs)),
                    "pen_points": int(rendered.pen_points_count),
                    "polyline_defs": int(len(polyline_defs)),
                    "db_changes": int(wrote),
                    "duration_ms": int((time.perf_counter() - t0) * 1000),
                },
            )
