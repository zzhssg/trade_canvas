from __future__ import annotations

import sqlite3
from typing import Any

from .overlay_store import OverlayStore


class OverlayInstructionWriter:
    def __init__(self, *, overlay_store: OverlayStore) -> None:
        self._overlay_store = overlay_store

    def persist(
        self,
        *,
        series_id: str,
        to_time: int,
        marker_defs: list[tuple[str, str, int, dict[str, Any]]],
        polyline_defs: list[tuple[str, int, dict[str, Any]]],
    ) -> int:
        with self._overlay_store.connect() as conn:
            before_changes = int(conn.total_changes)

            for instruction_id, kind, visible_time, payload in marker_defs:
                if self._is_latest_def_same(
                    conn=conn,
                    series_id=series_id,
                    instruction_id=instruction_id,
                    payload=payload,
                ):
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
                if self._is_latest_def_same(
                    conn=conn,
                    series_id=series_id,
                    instruction_id=instruction_id,
                    payload=payload,
                ):
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
            return int(conn.total_changes) - before_changes

    def _is_latest_def_same(
        self,
        *,
        conn: sqlite3.Connection,
        series_id: str,
        instruction_id: str,
        payload: dict[str, Any],
    ) -> bool:
        prev = self._overlay_store.get_latest_def_for_instruction_in_conn(
            conn,
            series_id=series_id,
            instruction_id=instruction_id,
        )
        return prev == payload
