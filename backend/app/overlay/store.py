from __future__ import annotations

import json
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ..storage.local_store_runtime import (
    LocalConnectionBase,
    MemoryCursor,
    get_or_create_store_state,
    merge_series_head_time,
    read_series_head_time,
)


@dataclass(frozen=True)
class OverlayInstructionVersionRow:
    version_id: int
    series_id: str
    instruction_id: str
    kind: str
    visible_time: int
    payload: dict[str, Any]


@dataclass
class _OverlayStoreState:
    series_head: dict[str, int] = field(default_factory=dict)
    versions: list[OverlayInstructionVersionRow] = field(default_factory=list)
    next_version_id: int = 1


_STORE_STATES: dict[str, _OverlayStoreState] = {}
_STORE_STATES_LOCK = threading.Lock()


def _get_store_state(db_path: Path) -> _OverlayStoreState:
    return get_or_create_store_state(
        store_states=_STORE_STATES,
        lock=_STORE_STATES_LOCK,
        db_path=db_path,
        factory=_OverlayStoreState,
    )


class _OverlayStoreConnection(LocalConnectionBase):
    def __init__(self, state: _OverlayStoreState) -> None:
        super().__init__()
        self._state = state

    def execute(self, sql: str, params: tuple[Any, ...] | list[Any] = ()) -> MemoryCursor:
        normalized = " ".join(str(sql).strip().split()).lower()
        values = tuple(params)

        if normalized.startswith("update overlay_series_state set head_time = ? where series_id = ?"):
            head_time = int(values[0]) if values else 0
            series_id = str(values[1]) if len(values) > 1 else ""
            if series_id not in self._state.series_head:
                return MemoryCursor(rowcount=0)
            self._state.series_head[series_id] = int(head_time)
            self.total_changes += 1
            return MemoryCursor(rowcount=1)

        if normalized.startswith("delete from overlay_instruction_versions where series_id = ? and instruction_id = ?"):
            series_id = str(values[0]) if values else ""
            instruction_id = str(values[1]) if len(values) > 1 else ""
            before = len(self._state.versions)
            self._state.versions = [
                row
                for row in self._state.versions
                if not (str(row.series_id) == series_id and str(row.instruction_id) == instruction_id)
            ]
            deleted = before - len(self._state.versions)
            if deleted > 0:
                self.total_changes += int(deleted)
            return MemoryCursor(rowcount=int(deleted))

        if normalized.startswith("insert into overlay_instruction_versions"):
            if len(values) < 4:
                raise RuntimeError("overlay_insert_invalid_values")
            series_id = str(values[0])
            instruction_id = str(values[1])
            visible_time = int(values[2])
            payload_text = str(values[3])
            try:
                payload = json.loads(payload_text)
            except json.JSONDecodeError:
                payload = {}
            if not isinstance(payload, dict):
                payload = {}
            version_id = int(self._state.next_version_id)
            self._state.next_version_id += 1
            self._state.versions.append(
                OverlayInstructionVersionRow(
                    version_id=version_id,
                    series_id=series_id,
                    instruction_id=instruction_id,
                    kind="polyline",
                    visible_time=int(visible_time),
                    payload=dict(payload),
                )
            )
            self.total_changes += 1
            return MemoryCursor(rowcount=1, lastrowid=version_id)

        raise RuntimeError(f"unsupported_local_store_sql:{sql.strip()[:96]}")


@dataclass(frozen=True)
class OverlayStore:
    db_path: Path

    def connect(self) -> _OverlayStoreConnection:
        return _OverlayStoreConnection(_get_store_state(self.db_path))

    def upsert_head_time_in_conn(self, conn: _OverlayStoreConnection, *, series_id: str, head_time: int) -> None:
        merge_series_head_time(
            series_head=conn._state.series_head,
            series_id=series_id,
            head_time=head_time,
        )
        conn.total_changes += 1

    def clear_series_in_conn(self, conn: _OverlayStoreConnection, *, series_id: str) -> None:
        sid = str(series_id)
        before = len(conn._state.versions)
        conn._state.versions = [row for row in conn._state.versions if str(row.series_id) != sid]
        removed = before - len(conn._state.versions)
        if sid in conn._state.series_head:
            conn._state.series_head.pop(sid, None)
            removed += 1
        if removed > 0:
            conn.total_changes += int(removed)

    def head_time(self, series_id: str) -> int | None:
        return read_series_head_time(
            series_head=_get_store_state(self.db_path).series_head,
            series_id=series_id,
        )

    def last_version_id(self, series_id: str) -> int:
        sid = str(series_id)
        versions = [int(row.version_id) for row in _get_store_state(self.db_path).versions if str(row.series_id) == sid]
        return int(max(versions)) if versions else 0

    def insert_instruction_version_in_conn(
        self,
        conn: _OverlayStoreConnection,
        *,
        series_id: str,
        instruction_id: str,
        kind: str,
        visible_time: int,
        payload: dict[str, Any],
    ) -> int:
        version_id = int(conn._state.next_version_id)
        conn._state.next_version_id += 1
        conn._state.versions.append(
            OverlayInstructionVersionRow(
                version_id=version_id,
                series_id=str(series_id),
                instruction_id=str(instruction_id),
                kind=str(kind),
                visible_time=int(visible_time),
                payload=dict(payload or {}),
            )
        )
        conn.total_changes += 1
        return int(version_id)

    def get_latest_defs_up_to_time(
        self,
        *,
        series_id: str,
        up_to_time: int,
    ) -> list[OverlayInstructionVersionRow]:
        sid = str(series_id)
        limit_time = int(up_to_time)
        latest_by_instruction: dict[str, OverlayInstructionVersionRow] = {}
        for row in _get_store_state(self.db_path).versions:
            if str(row.series_id) != sid or int(row.visible_time) > limit_time:
                continue
            prev = latest_by_instruction.get(str(row.instruction_id))
            if prev is None or int(row.version_id) > int(prev.version_id):
                latest_by_instruction[str(row.instruction_id)] = row
        return list(sorted(latest_by_instruction.values(), key=lambda row: int(row.version_id)))

    def get_patch_after_version(
        self,
        *,
        series_id: str,
        after_version_id: int,
        up_to_time: int,
        limit: int = 50000,
    ) -> list[OverlayInstructionVersionRow]:
        sid = str(series_id)
        after = int(after_version_id)
        upper = int(up_to_time)
        rows = [
            row
            for row in _get_store_state(self.db_path).versions
            if str(row.series_id) == sid and int(row.version_id) > after and int(row.visible_time) <= upper
        ]
        rows.sort(key=lambda row: int(row.version_id))
        if int(limit) > 0:
            rows = rows[: int(limit)]
        return rows

    def get_versions_between_times(
        self,
        *,
        series_id: str,
        start_visible_time: int,
        end_visible_time: int,
        limit: int = 200000,
    ) -> list[OverlayInstructionVersionRow]:
        sid = str(series_id)
        start = int(start_visible_time)
        end = int(end_visible_time)
        rows = [
            row
            for row in _get_store_state(self.db_path).versions
            if str(row.series_id) == sid and start <= int(row.visible_time) <= end
        ]
        rows.sort(key=lambda row: (int(row.visible_time), int(row.version_id)))
        if int(limit) > 0:
            rows = rows[: int(limit)]
        return rows

    def get_latest_def_for_instruction_in_conn(
        self,
        conn: _OverlayStoreConnection,
        *,
        series_id: str,
        instruction_id: str,
    ) -> dict[str, Any] | None:
        sid = str(series_id)
        iid = str(instruction_id)
        rows = [
            row
            for row in conn._state.versions
            if str(row.series_id) == sid and str(row.instruction_id) == iid
        ]
        if not rows:
            return None
        rows.sort(key=lambda row: int(row.version_id), reverse=True)
        return dict(rows[0].payload or {})
