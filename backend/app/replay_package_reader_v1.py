from __future__ import annotations

import json
from pathlib import Path

from .overlay_replay_protocol_v1 import OverlayReplayCheckpointV1, OverlayReplayDiffV1
from .replay_package_protocol_v1 import (
    ReplayCoverageV1,
    ReplayFactorHeadSnapshotV1,
    ReplayHistoryDeltaV1,
    ReplayHistoryEventV1,
    ReplayKlineBarV1,
    ReplayPackageMetadataV1,
    ReplayWindowV1,
)
from .schemas import OverlayInstructionPatchItemV1
from .service_errors import ServiceError
from .sqlite_util import connect as sqlite_connect
from .store import CandleStore
from .timeframe import series_id_timeframe, timeframe_to_seconds


class ReplayPackageReaderV1:
    def __init__(self, *, candle_store: CandleStore, root_dir: Path) -> None:
        self._candle_store = candle_store
        self._root_dir = Path(root_dir)

    def cache_dir(self, cache_key: str) -> Path:
        return self._root_dir / str(cache_key)

    def db_path(self, cache_key: str) -> Path:
        return self.cache_dir(cache_key) / "replay.sqlite"

    def cache_exists(self, cache_key: str) -> bool:
        return self.db_path(cache_key).exists()

    def resolve_to_time(self, series_id: str, to_time: int | None) -> int:
        store_head = self._candle_store.head_time(series_id)
        if store_head is None and to_time is None:
            raise ServiceError(status_code=404, detail="no_data", code="replay.no_data")
        requested = int(to_time) if to_time is not None else int(store_head or 0)
        aligned = self._candle_store.floor_time(series_id, at_time=int(requested))
        if aligned is None:
            raise ServiceError(status_code=404, detail="no_data", code="replay.no_data")
        return int(aligned)

    def coverage(
        self,
        *,
        series_id: str,
        to_time: int,
        target_candles: int,
    ) -> ReplayCoverageV1:
        tf_s = timeframe_to_seconds(series_id_timeframe(series_id))
        start_time = max(0, int(to_time) - (int(target_candles) - 1) * int(tf_s))
        candles = self._candle_store.get_closed_between_times(
            series_id,
            start_time=int(start_time),
            end_time=int(to_time),
            limit=int(target_candles),
        )
        from_time = int(candles[0].candle_time) if candles else None
        return ReplayCoverageV1(
            required_candles=int(target_candles),
            candles_ready=int(len(candles)),
            from_time=from_time,
            to_time=int(to_time),
        )

    def read_meta(self, cache_key: str) -> ReplayPackageMetadataV1:
        db_path = self.db_path(cache_key)
        conn = sqlite_connect(db_path)
        try:
            row = conn.execute(
                """
                SELECT schema_version, series_id, timeframe_s, total_candles, from_candle_time, to_candle_time,
                       window_size, snapshot_interval, preload_offset, idx_to_time
                FROM replay_meta
                LIMIT 1
                """
            ).fetchone()
            if row is None:
                raise RuntimeError("missing replay_meta")
            return ReplayPackageMetadataV1(
                schema_version=int(row["schema_version"]),
                series_id=str(row["series_id"]),
                timeframe_s=int(row["timeframe_s"]),
                total_candles=int(row["total_candles"]),
                from_candle_time=int(row["from_candle_time"]),
                to_candle_time=int(row["to_candle_time"]),
                window_size=int(row["window_size"]),
                snapshot_interval=int(row["snapshot_interval"]),
                preload_offset=int(row["preload_offset"]),
                idx_to_time=str(row["idx_to_time"]),
            )
        finally:
            conn.close()

    def read_history_events(self, cache_key: str) -> list[ReplayHistoryEventV1]:
        db_path = self.db_path(cache_key)
        conn = sqlite_connect(db_path)
        try:
            rows = conn.execute(
                """
                SELECT event_id, factor_name, candle_time, kind, event_key, payload_json
                FROM replay_factor_history_events
                ORDER BY event_id ASC
                """
            ).fetchall()
            out: list[ReplayHistoryEventV1] = []
            for r in rows:
                try:
                    payload = json.loads(r["payload_json"])
                except Exception:
                    payload = {}
                if not isinstance(payload, dict):
                    payload = {}
                out.append(
                    ReplayHistoryEventV1(
                        event_id=int(r["event_id"]),
                        factor_name=str(r["factor_name"]),
                        candle_time=int(r["candle_time"]),
                        kind=str(r["kind"]),
                        event_key=str(r["event_key"]),
                        payload=payload,
                    )
                )
            return out
        finally:
            conn.close()

    def read_window(self, cache_key: str, *, target_idx: int) -> ReplayWindowV1:
        db_path = self.db_path(cache_key)
        conn = sqlite_connect(db_path)
        try:
            meta = conn.execute(
                "SELECT total_candles, window_size FROM replay_meta LIMIT 1"
            ).fetchone()
            if meta is None:
                raise ServiceError(status_code=404, detail="not_found", code="replay.window.not_found")
            total = int(meta["total_candles"])
            window_size = int(meta["window_size"])
            idx = int(target_idx)
            if idx < 0 or idx >= total:
                raise ServiceError(
                    status_code=422,
                    detail="target_idx_out_of_range",
                    code="replay.window.target_idx_out_of_range",
                )
            window_index = idx // window_size
            w = conn.execute(
                """
                SELECT window_index, start_idx, end_idx
                FROM replay_window_meta
                WHERE window_index = ?
                """,
                (int(window_index),),
            ).fetchone()
            if w is None:
                raise ServiceError(status_code=404, detail="not_found", code="replay.window.not_found")
            start_idx = int(w["start_idx"])
            end_idx = int(w["end_idx"])

            kline_rows = conn.execute(
                """
                SELECT idx, candle_time, open, high, low, close, volume
                FROM replay_kline_bars
                WHERE idx >= ? AND idx < ?
                ORDER BY idx ASC
                """,
                (int(start_idx), int(end_idx)),
            ).fetchall()
            kline = [
                ReplayKlineBarV1(
                    time=int(r["candle_time"]),
                    open=float(r["open"]),
                    high=float(r["high"]),
                    low=float(r["low"]),
                    close=float(r["close"]),
                    volume=float(r["volume"]),
                )
                for r in kline_rows
            ]

            catalog_rows = conn.execute(
                """
                SELECT w.scope, v.version_id, v.instruction_id, v.kind, v.visible_time, v.definition_json
                FROM replay_draw_catalog_window w
                JOIN replay_draw_catalog_versions v ON v.version_id = w.version_id
                WHERE w.window_index = ?
                ORDER BY v.version_id ASC
                """,
                (int(window_index),),
            ).fetchall()
            base: list[OverlayInstructionPatchItemV1] = []
            patch: list[OverlayInstructionPatchItemV1] = []
            for r in catalog_rows:
                try:
                    definition = json.loads(r["definition_json"])
                except Exception:
                    definition = {}
                item = OverlayInstructionPatchItemV1(
                    version_id=int(r["version_id"]),
                    instruction_id=str(r["instruction_id"]),
                    kind=str(r["kind"]),
                    visible_time=int(r["visible_time"]),
                    definition=definition if isinstance(definition, dict) else {},
                )
                if str(r["scope"]) == "base":
                    base.append(item)
                else:
                    patch.append(item)

            checkpoint_rows = conn.execute(
                """
                SELECT at_idx, active_ids_json
                FROM replay_draw_active_checkpoints
                WHERE window_index = ?
                ORDER BY at_idx ASC
                """,
                (int(window_index),),
            ).fetchall()
            checkpoints = []
            for r in checkpoint_rows:
                try:
                    active_ids = json.loads(r["active_ids_json"])
                except Exception:
                    active_ids = []
                checkpoints.append(
                    OverlayReplayCheckpointV1(at_idx=int(r["at_idx"]), active_ids=active_ids or [])
                )

            diff_rows = conn.execute(
                """
                SELECT at_idx, add_ids_json, remove_ids_json
                FROM replay_draw_active_diffs
                WHERE window_index = ?
                ORDER BY at_idx ASC
                """,
                (int(window_index),),
            ).fetchall()
            diffs = []
            for r in diff_rows:
                try:
                    add_ids = json.loads(r["add_ids_json"])
                except Exception:
                    add_ids = []
                try:
                    remove_ids = json.loads(r["remove_ids_json"])
                except Exception:
                    remove_ids = []
                diffs.append(
                    OverlayReplayDiffV1(
                        at_idx=int(r["at_idx"]),
                        add_ids=add_ids or [],
                        remove_ids=remove_ids or [],
                    )
                )

            return ReplayWindowV1(
                window_index=int(window_index),
                start_idx=int(start_idx),
                end_idx=int(end_idx),
                kline=kline,
                draw_catalog_base=base,
                draw_catalog_patch=patch,
                draw_active_checkpoints=checkpoints,
                draw_active_diffs=diffs,
            )
        finally:
            conn.close()

    def read_window_extras(
        self,
        *,
        cache_key: str,
        window: ReplayWindowV1,
    ) -> tuple[list[ReplayFactorHeadSnapshotV1], list[ReplayHistoryDeltaV1]]:
        db_path = self.db_path(cache_key)
        conn = sqlite_connect(db_path)
        try:
            start_idx = int(window.start_idx)
            end_idx = int(window.end_idx)
            rows = conn.execute(
                """
                SELECT candle_time
                FROM replay_kline_bars
                WHERE idx >= ? AND idx < ?
                ORDER BY idx ASC
                """,
                (int(start_idx), int(end_idx)),
            ).fetchall()
            times = [int(r["candle_time"]) for r in rows]
            head_rows: list[ReplayFactorHeadSnapshotV1] = []
            if times:
                q = """
                SELECT factor_name, candle_time, seq, head_json
                FROM replay_factor_head_snapshots
                WHERE candle_time >= ? AND candle_time <= ?
                ORDER BY candle_time ASC, factor_name ASC, seq ASC
                """
                for r in conn.execute(q, (int(times[0]), int(times[-1]))).fetchall():
                    try:
                        head = json.loads(r["head_json"])
                    except Exception:
                        head = {}
                    head_rows.append(
                        ReplayFactorHeadSnapshotV1(
                            factor_name=str(r["factor_name"]),
                            candle_time=int(r["candle_time"]),
                            seq=int(r["seq"]),
                            head=head if isinstance(head, dict) else {},
                        )
                    )

            delta_rows = conn.execute(
                """
                SELECT idx, from_event_id, to_event_id
                FROM replay_factor_history_deltas
                WHERE idx >= ? AND idx < ?
                ORDER BY idx ASC
                """,
                (int(start_idx), int(end_idx)),
            ).fetchall()
            deltas = [
                ReplayHistoryDeltaV1(
                    idx=int(r["idx"]),
                    from_event_id=int(r["from_event_id"]),
                    to_event_id=int(r["to_event_id"]),
                )
                for r in delta_rows
            ]
            return (head_rows, deltas)
        finally:
            conn.close()

    def read_preload_window(self, cache_key: str, meta: ReplayPackageMetadataV1) -> ReplayWindowV1 | None:
        if meta.total_candles <= 0:
            return None
        target_idx = max(0, int(meta.total_candles) - 1 - int(meta.preload_offset))
        return self.read_window(cache_key, target_idx=int(target_idx))
