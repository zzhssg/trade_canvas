from __future__ import annotations

import time
from typing import Any

from .store import FactorEventWrite
from ..core.timeframe import series_id_timeframe, timeframe_to_seconds


def ingest_closed(
    orchestrator: Any,
    *,
    result_cls: type[Any],
    series_id: str,
    up_to_candle_time: int,
) -> Any:
    t0 = time.perf_counter()
    if not orchestrator.enabled():
        return result_cls()

    up_to = int(up_to_candle_time or 0)
    if up_to <= 0:
        return result_cls()

    settings = orchestrator._load_settings()
    tf_s = timeframe_to_seconds(series_id_timeframe(series_id))
    max_window = max(int(settings.pivot_window_major), int(settings.pivot_window_minor))
    auto_rebuild = orchestrator._fingerprint_rebuild_enabled()
    current_fingerprint = orchestrator._build_series_fingerprint(series_id=series_id, settings=settings)
    rebuild_outcome = orchestrator._fingerprint_rebuild_coordinator().ensure_series_ready(
        series_id=series_id,
        auto_rebuild=bool(auto_rebuild),
        current_fingerprint=str(current_fingerprint),
    )
    force_rebuild_from_earliest = bool(rebuild_outcome.forced)
    planner = orchestrator._ingest_window_planner()

    head_time = orchestrator._factor_store.head_time(series_id) or 0
    if up_to <= int(head_time):
        return result_cls(rebuilt=bool(force_rebuild_from_earliest), fingerprint=current_fingerprint)

    window_plan = planner.plan_window(
        series_id=series_id,
        up_to=int(up_to),
        head_time=int(head_time),
        tf_s=int(tf_s),
        settings_lookback_candles=int(settings.lookback_candles),
        max_window=int(max_window),
        force_rebuild_from_earliest=bool(force_rebuild_from_earliest),
    )
    if window_plan is None:
        return result_cls(rebuilt=bool(force_rebuild_from_earliest), fingerprint=current_fingerprint)

    candle_batch = planner.load_candle_batch(
        series_id=series_id,
        up_to=int(up_to),
        head_time=int(head_time),
        plan=window_plan,
    )
    if candle_batch is None:
        return result_cls(rebuilt=bool(force_rebuild_from_earliest), fingerprint=current_fingerprint)
    candles = candle_batch.candles
    time_to_idx = candle_batch.time_to_idx
    process_times = candle_batch.process_times

    bootstrap_state = orchestrator._build_incremental_bootstrap_state(
        series_id=series_id,
        head_time=int(head_time),
        lookback_candles=int(window_plan.lookback_candles),
        tf_s=int(tf_s),
        state_rebuild_event_limit=int(settings.state_rebuild_event_limit),
        candles=candles,
        time_to_idx=time_to_idx,
    )
    effective_pivots = bootstrap_state.effective_pivots
    confirmed_pens = bootstrap_state.confirmed_pens
    zhongshu_state = bootstrap_state.zhongshu_state
    last_major_idx = bootstrap_state.last_major_idx
    anchor_current_ref = bootstrap_state.anchor_current_ref
    anchor_strength = bootstrap_state.anchor_strength
    events: list[FactorEventWrite] = []

    tick_result = orchestrator._run_ticks(
        series_id=series_id,
        process_times=process_times,
        tf_s=int(tf_s),
        settings=settings,
        candles=candles,
        time_to_idx=time_to_idx,
        effective_pivots=effective_pivots,
        confirmed_pens=confirmed_pens,
        zhongshu_state=zhongshu_state,
        anchor_current_ref=anchor_current_ref,
        anchor_strength=anchor_strength,
        last_major_idx=last_major_idx,
        events=events,
    )
    effective_pivots = tick_result.effective_pivots
    confirmed_pens = tick_result.confirmed_pens
    zhongshu_state = tick_result.zhongshu_state
    anchor_current_ref = tick_result.anchor_current_ref
    events = tick_result.events

    head_snapshots = orchestrator._build_head_snapshots(
        series_id=series_id,
        confirmed_pens=confirmed_pens,
        effective_pivots=effective_pivots,
        zhongshu_state=zhongshu_state,
        anchor_current_ref=anchor_current_ref,
        candles=candles,
        up_to=int(up_to),
    )
    wrote = orchestrator._persist_ingest_outputs(
        series_id=series_id,
        up_to=int(up_to),
        events=events,
        head_snapshots=head_snapshots,
        auto_rebuild=auto_rebuild,
        fingerprint=current_fingerprint,
    )

    if orchestrator._debug_hub is not None:
        orchestrator._debug_hub.emit(
            pipe="write",
            event="write.factor.ingest_done",
            series_id=series_id,
            message="factor ingest done",
            data={
                "up_to_candle_time": int(up_to),
                "candles_read": int(len(candles)),
                "events_planned": int(len(events)),
                "db_changes": int(wrote),
                "duration_ms": int((time.perf_counter() - t0) * 1000),
            },
        )
    return result_cls(rebuilt=bool(force_rebuild_from_earliest), fingerprint=current_fingerprint)
