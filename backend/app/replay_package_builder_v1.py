from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .factor_slices_service import FactorSlicesService
from .factor_store import FactorStore
from .overlay_package_builder_v1 import OverlayReplayBuildParamsV1, build_overlay_replay_package_v1
from .overlay_store import OverlayStore
from .replay_package_protocol_v1 import ReplayKlineBarV1
from .sqlite_util import connect as sqlite_connect
from .store import CandleStore
from .timeframe import series_id_timeframe, timeframe_to_seconds


@dataclass(frozen=True)
class ReplayBuildParamsV1:
    series_id: str
    to_candle_time: int
    window_candles: int = 2000
    window_size: int = 500
    snapshot_interval: int = 25
    preload_offset: int = 0


def stable_json_dumps(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def _ensure_schema(conn) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS replay_meta (
          schema_version INTEGER NOT NULL,
          cache_key TEXT NOT NULL,
          series_id TEXT NOT NULL,
          timeframe_s INTEGER NOT NULL,
          total_candles INTEGER NOT NULL,
          from_candle_time INTEGER NOT NULL,
          to_candle_time INTEGER NOT NULL,
          window_size INTEGER NOT NULL,
          snapshot_interval INTEGER NOT NULL,
          preload_offset INTEGER NOT NULL DEFAULT 0,
          idx_to_time TEXT NOT NULL DEFAULT 'replay_kline_bars.candle_time',
          candle_store_head_time INTEGER NOT NULL,
          factor_store_last_event_id INTEGER NOT NULL,
          overlay_store_last_version_id INTEGER NOT NULL,
          created_at_ms INTEGER NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS replay_kline_bars (
          idx INTEGER PRIMARY KEY,
          candle_time INTEGER NOT NULL,
          open REAL NOT NULL,
          high REAL NOT NULL,
          low REAL NOT NULL,
          close REAL NOT NULL,
          volume REAL NOT NULL
        )
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_replay_kline_time ON replay_kline_bars(candle_time);")
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS replay_window_meta (
          window_index INTEGER PRIMARY KEY,
          start_idx INTEGER NOT NULL,
          end_idx INTEGER NOT NULL,
          start_time INTEGER NOT NULL,
          end_time INTEGER NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS replay_factor_history_events (
          event_id INTEGER PRIMARY KEY,
          series_id TEXT NOT NULL,
          factor_name TEXT NOT NULL,
          candle_time INTEGER NOT NULL,
          kind TEXT NOT NULL,
          event_key TEXT NOT NULL,
          payload_json TEXT NOT NULL
        )
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_replay_history_time ON replay_factor_history_events(candle_time);")
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_replay_history_factor_time ON replay_factor_history_events(factor_name, candle_time);"
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS replay_factor_head_snapshots (
          series_id TEXT NOT NULL,
          factor_name TEXT NOT NULL,
          candle_time INTEGER NOT NULL,
          seq INTEGER NOT NULL,
          head_json TEXT NOT NULL,
          PRIMARY KEY (series_id, factor_name, candle_time, seq)
        )
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_replay_head_factor_time ON replay_factor_head_snapshots(factor_name, candle_time, seq);"
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS replay_factor_history_deltas (
          idx INTEGER PRIMARY KEY,
          from_event_id INTEGER NOT NULL,
          to_event_id INTEGER NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS replay_draw_catalog_versions (
          version_id INTEGER PRIMARY KEY,
          instruction_id TEXT NOT NULL,
          kind TEXT NOT NULL,
          visible_time INTEGER NOT NULL,
          definition_json TEXT NOT NULL
        )
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_replay_draw_catalog_visible ON replay_draw_catalog_versions(visible_time);"
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS replay_draw_catalog_window (
          window_index INTEGER NOT NULL,
          scope TEXT NOT NULL,
          version_id INTEGER NOT NULL,
          PRIMARY KEY (window_index, scope, version_id)
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS replay_draw_active_checkpoints (
          window_index INTEGER NOT NULL,
          at_idx INTEGER NOT NULL,
          active_ids_json TEXT NOT NULL,
          PRIMARY KEY (window_index, at_idx)
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS replay_draw_active_diffs (
          window_index INTEGER NOT NULL,
          at_idx INTEGER NOT NULL,
          add_ids_json TEXT NOT NULL,
          remove_ids_json TEXT NOT NULL,
          PRIMARY KEY (window_index, at_idx)
        )
        """
    )
    conn.commit()


def build_replay_package_v1(
    *,
    db_path: Path,
    cache_key: str,
    candle_store: CandleStore,
    factor_store: FactorStore,
    overlay_store: OverlayStore,
    factor_slices_service: FactorSlicesService,
    params: ReplayBuildParamsV1,
) -> None:
    tf_s = timeframe_to_seconds(series_id_timeframe(params.series_id))
    window_candles = max(1, int(params.window_candles))
    window_size = max(1, int(params.window_size))
    snapshot_interval = max(1, int(params.snapshot_interval))

    end_time = int(params.to_candle_time)
    start_time = max(0, end_time - (window_candles - 1) * int(tf_s))

    candles = candle_store.get_closed_between_times(
        params.series_id,
        start_time=int(start_time),
        end_time=int(end_time),
        limit=int(window_candles) + 10,
    )
    kline_all = [
        ReplayKlineBarV1(
            time=int(c.candle_time),
            open=float(c.open),
            high=float(c.high),
            low=float(c.low),
            close=float(c.close),
            volume=float(c.volume),
        )
        for c in candles
    ]
    if kline_all:
        kline_all.sort(key=lambda b: int(b.time))

    total = len(kline_all)
    if total == 0:
        raise ValueError("no_candles")

    from_time = int(kline_all[0].time)
    to_time = int(kline_all[-1].time)

    overlay_pkg = build_overlay_replay_package_v1(
        candle_store=candle_store,
        overlay_store=overlay_store,
        params=OverlayReplayBuildParamsV1(
            series_id=params.series_id,
            to_candle_time=int(to_time),
            window_candles=int(window_candles),
            window_size=int(window_size),
            snapshot_interval=int(snapshot_interval),
            preload_offset=int(params.preload_offset),
        ),
    )

    conn = sqlite_connect(db_path)
    try:
        _ensure_schema(conn)

        conn.execute("DELETE FROM replay_meta")
        conn.execute("DELETE FROM replay_kline_bars")
        conn.execute("DELETE FROM replay_window_meta")
        conn.execute("DELETE FROM replay_factor_history_events")
        conn.execute("DELETE FROM replay_factor_head_snapshots")
        conn.execute("DELETE FROM replay_factor_history_deltas")
        conn.execute("DELETE FROM replay_draw_catalog_versions")
        conn.execute("DELETE FROM replay_draw_catalog_window")
        conn.execute("DELETE FROM replay_draw_active_checkpoints")
        conn.execute("DELETE FROM replay_draw_active_diffs")

        conn.executemany(
            """
            INSERT INTO replay_kline_bars(idx, candle_time, open, high, low, close, volume)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (idx, int(b.time), float(b.open), float(b.high), float(b.low), float(b.close), float(b.volume))
                for idx, b in enumerate(kline_all)
            ],
        )

        window_rows: list[tuple[int, int, int, int, int]] = []
        for w in overlay_pkg.windows:
            if not w.kline:
                continue
            window_rows.append(
                (
                    int(w.window_index),
                    int(w.start_idx),
                    int(w.end_idx),
                    int(w.kline[0].time),
                    int(w.kline[-1].time),
                )
            )
        if window_rows:
            conn.executemany(
                """
                INSERT INTO replay_window_meta(window_index, start_idx, end_idx, start_time, end_time)
                VALUES (?, ?, ?, ?, ?)
                """,
                window_rows,
            )

        events = factor_store.get_events_between_times(
            series_id=params.series_id,
            factor_name=None,
            start_candle_time=int(from_time),
            end_candle_time=int(to_time),
            limit=200000,
        )
        if events:
            conn.executemany(
                """
                INSERT INTO replay_factor_history_events(
                  event_id, series_id, factor_name, candle_time, kind, event_key, payload_json
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        int(e.id),
                        str(e.series_id),
                        str(e.factor_name),
                        int(e.candle_time),
                        str(e.kind),
                        str(e.event_key),
                        stable_json_dumps(e.payload or {}),
                    )
                    for e in events
                ],
            )

        history_deltas: list[tuple[int, int, int]] = []
        last_event_id = 0
        event_idx = 0
        events_sorted = sorted(events, key=lambda r: (int(r.candle_time), int(r.id)))
        for idx, bar in enumerate(kline_all):
            prev_event_id = last_event_id
            while event_idx < len(events_sorted) and int(events_sorted[event_idx].candle_time) <= int(bar.time):
                last_event_id = int(events_sorted[event_idx].id)
                event_idx += 1
            history_deltas.append((int(idx), int(prev_event_id), int(last_event_id)))
        if history_deltas:
            conn.executemany(
                """
                INSERT INTO replay_factor_history_deltas(idx, from_event_id, to_event_id)
                VALUES (?, ?, ?)
                """,
                history_deltas,
            )

        head_rows: list[tuple[str, str, int, int, str]] = []
        for bar in kline_all:
            slices = factor_slices_service.get_slices(
                series_id=params.series_id,
                at_time=int(bar.time),
                window_candles=int(window_candles),
            )
            for factor_name, snapshot in (slices.snapshots or {}).items():
                head_rows.append(
                    (
                        params.series_id,
                        str(factor_name),
                        int(bar.time),
                        0,
                        stable_json_dumps(snapshot.head or {}),
                    )
                )
        if head_rows:
            conn.executemany(
                """
                INSERT INTO replay_factor_head_snapshots(series_id, factor_name, candle_time, seq, head_json)
                VALUES (?, ?, ?, ?, ?)
                """,
                head_rows,
            )

        catalog_map: dict[int, tuple[str, str, int, str]] = {}
        window_catalog_rows: list[tuple[int, str, int]] = []
        checkpoint_rows: list[tuple[int, int, str]] = []
        diff_rows: list[tuple[int, int, str, str]] = []

        for w in overlay_pkg.windows:
            widx = int(w.window_index)
            for item in w.catalog_base:
                version_id = int(item.version_id)
                catalog_map[version_id] = (
                    str(item.instruction_id),
                    str(item.kind),
                    int(item.visible_time),
                    stable_json_dumps(item.definition or {}),
                )
                window_catalog_rows.append((widx, "base", version_id))
            for item in w.catalog_patch:
                version_id = int(item.version_id)
                catalog_map[version_id] = (
                    str(item.instruction_id),
                    str(item.kind),
                    int(item.visible_time),
                    stable_json_dumps(item.definition or {}),
                )
                window_catalog_rows.append((widx, "patch", version_id))
            for cp in w.checkpoints:
                checkpoint_rows.append((widx, int(cp.at_idx), stable_json_dumps(cp.active_ids or [])))
            for df in w.diffs:
                diff_rows.append(
                    (
                        widx,
                        int(df.at_idx),
                        stable_json_dumps(df.add_ids or []),
                        stable_json_dumps(df.remove_ids or []),
                    )
                )

        if catalog_map:
            conn.executemany(
                """
                INSERT INTO replay_draw_catalog_versions(version_id, instruction_id, kind, visible_time, definition_json)
                VALUES (?, ?, ?, ?, ?)
                """,
                [(vid, *vals) for vid, vals in catalog_map.items()],
            )
        if window_catalog_rows:
            conn.executemany(
                """
                INSERT INTO replay_draw_catalog_window(window_index, scope, version_id)
                VALUES (?, ?, ?)
                """,
                window_catalog_rows,
            )
        if checkpoint_rows:
            conn.executemany(
                """
                INSERT INTO replay_draw_active_checkpoints(window_index, at_idx, active_ids_json)
                VALUES (?, ?, ?)
                """,
                checkpoint_rows,
            )
        if diff_rows:
            conn.executemany(
                """
                INSERT INTO replay_draw_active_diffs(window_index, at_idx, add_ids_json, remove_ids_json)
                VALUES (?, ?, ?, ?)
                """,
                diff_rows,
            )

        meta_row = (
            1,
            cache_key,
            params.series_id,
            int(tf_s),
            int(total),
            int(from_time),
            int(to_time),
            int(window_size),
            int(snapshot_interval),
            int(params.preload_offset),
            "replay_kline_bars.candle_time",
            int(candle_store.head_time(params.series_id) or 0),
            int(factor_store.last_event_id(params.series_id)),
            int(overlay_store.last_version_id(params.series_id)),
            int(time.time() * 1000),
        )
        conn.execute(
            """
            INSERT INTO replay_meta(
              schema_version, cache_key, series_id, timeframe_s, total_candles, from_candle_time, to_candle_time,
              window_size, snapshot_interval, preload_offset, idx_to_time, candle_store_head_time,
              factor_store_last_event_id, overlay_store_last_version_id, created_at_ms
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            meta_row,
        )
        conn.commit()
    finally:
        conn.close()
