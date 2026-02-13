from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from ..overlay_store import OverlayInstructionVersionRow
from ..schemas import DrawCursorV1, DrawDeltaV1, GetFactorSlicesResponseV1
from ..timeframe import series_id_timeframe, timeframe_to_seconds
from .draw_delta_steps import (
    assert_overlay_head_covers,
    build_patch,
    collect_active_ids,
    emit_draw_delta_debug_if_needed,
    ensure_overlay_integrity_if_needed,
    read_slices_for_overlay_if_needed,
    resolve_to_time,
)


class _StoreLike(Protocol):
    def head_time(self, series_id: str) -> int | None: ...

    def floor_time(self, series_id: str, *, at_time: int) -> int | None: ...


class _OverlayStoreLike(Protocol):
    def head_time(self, series_id: str) -> int | None: ...

    def get_latest_defs_up_to_time(self, *, series_id: str, up_to_time: int) -> list[OverlayInstructionVersionRow]: ...

    def get_patch_after_version(
        self,
        *,
        series_id: str,
        after_version_id: int,
        up_to_time: int,
        limit: int = 50000,
    ) -> list[OverlayInstructionVersionRow]: ...

    def last_version_id(self, series_id: str) -> int: ...


class _OverlayOrchestratorLike(Protocol):
    def reset_series(self, *, series_id: str) -> None: ...

    def ingest_closed(self, *, series_id: str, up_to_candle_time: int) -> None: ...


class _FactorReadServiceLike(Protocol):
    @property
    def strict_mode(self) -> bool: ...

    def read_slices(
        self,
        *,
        series_id: str,
        at_time: int,
        window_candles: int,
        aligned_time: int | None = None,
        ensure_fresh: bool = True,
    ) -> GetFactorSlicesResponseV1: ...


class _DebugHubLike(Protocol):
    def emit(
        self,
        *,
        pipe: str,
        event: str,
        level: str = "info",
        message: str,
        series_id: str | None = None,
        data: dict | None = None,
    ) -> None: ...


@dataclass(frozen=True)
class DrawReadService:
    store: _StoreLike
    overlay_store: _OverlayStoreLike
    overlay_orchestrator: _OverlayOrchestratorLike
    factor_read_service: _FactorReadServiceLike
    debug_hub: _DebugHubLike
    debug_api_enabled: bool = False

    def _empty_delta(self, *, series_id: str, cursor_version_id: int) -> DrawDeltaV1:
        return DrawDeltaV1(
            series_id=series_id,
            to_candle_id=None,
            to_candle_time=None,
            active_ids=[],
            instruction_catalog_patch=[],
            series_points={},
            next_cursor=DrawCursorV1(version_id=int(cursor_version_id), point_time=None),
        )

    def _debug_enabled(self) -> bool:
        return bool(self.debug_api_enabled)

    def read_delta(
        self,
        *,
        series_id: str,
        cursor_version_id: int,
        window_candles: int,
        at_time: int | None = None,
    ) -> DrawDeltaV1:
        strict_mode = bool(getattr(self.factor_read_service, "strict_mode", False))
        store_head = self.store.head_time(series_id)
        overlay_head = self.overlay_store.head_time(series_id)
        to_time = resolve_to_time(
            store=self.store,
            series_id=series_id,
            at_time=at_time,
            store_head=store_head,
            overlay_head=overlay_head,
        )
        if to_time is None:
            return self._empty_delta(series_id=series_id, cursor_version_id=int(cursor_version_id))

        to_candle_id = f"{series_id}:{to_time}" if to_time is not None else None

        if strict_mode:
            assert_overlay_head_covers(required_time=int(to_time), overlay_head=overlay_head)

        slices_for_overlay = read_slices_for_overlay_if_needed(
            factor_read_service=self.factor_read_service,
            series_id=series_id,
            cursor_version_id=int(cursor_version_id),
            window_candles=int(window_candles),
            to_time=int(to_time),
        )

        tf_s = timeframe_to_seconds(series_id_timeframe(series_id))
        cutoff_time = max(0, int(to_time) - int(window_candles) * int(tf_s))

        latest_defs = self.overlay_store.get_latest_defs_up_to_time(series_id=series_id, up_to_time=int(to_time))
        ensure_overlay_integrity_if_needed(
            series_id=series_id,
            cursor_version_id=int(cursor_version_id),
            to_time=int(to_time),
            strict_mode=bool(strict_mode),
            latest_defs=latest_defs,
            slices_for_overlay=slices_for_overlay,
            debug_enabled=self._debug_enabled(),
            debug_hub=self.debug_hub,
        )

        active_ids = collect_active_ids(
            latest_defs=latest_defs,
            cutoff_time=int(cutoff_time),
            to_time=int(to_time),
        )
        patch = build_patch(
            overlay_store=self.overlay_store,
            series_id=series_id,
            cursor_version_id=int(cursor_version_id),
            to_time=int(to_time),
        )
        next_version_id = int(self.overlay_store.last_version_id(series_id))
        next_cursor = DrawCursorV1(version_id=int(next_version_id), point_time=None)

        emit_draw_delta_debug_if_needed(
            debug_enabled=self._debug_enabled(),
            debug_hub=self.debug_hub,
            series_id=series_id,
            cursor_version_id=int(cursor_version_id),
            next_version_id=int(next_cursor.version_id),
            to_time=int(to_time),
            patch_len=int(len(patch)),
            active_len=int(len(active_ids)),
            at_time=at_time,
        )
        return DrawDeltaV1(
            series_id=series_id,
            to_candle_id=to_candle_id,
            to_candle_time=int(to_time),
            active_ids=active_ids,
            instruction_catalog_patch=patch,
            series_points={},
            next_cursor=next_cursor,
        )
