from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .store import FactorEventWrite, FactorStore
from .pen import PivotMajorPoint


@dataclass
class HeadBuildState:
    up_to: int
    candles: list[Any]
    effective_pivots: list[PivotMajorPoint]
    confirmed_pens: list[dict[str, Any]]
    zhongshu_state: dict[str, Any]
    anchor_current_ref: dict[str, Any] | None
    sr_major_pivots: list[dict[str, Any]] = field(default_factory=list)
    sr_snapshot: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class HeadSnapshotBuildRequest:
    series_id: str
    state: HeadBuildState
    topo_order: list[str]
    registry: Any
    runtime: Any


def connection_total_changes(conn: Any) -> int | None:
    raw = getattr(conn, "total_changes", None)
    if raw is None:
        return None
    try:
        return int(raw)
    except (ValueError, TypeError):
        return None


def build_head_snapshots(
    *,
    request: HeadSnapshotBuildRequest,
) -> dict[str, dict[str, Any]]:
    state = request.state
    out: dict[str, dict[str, Any]] = {}
    for factor_name in request.topo_order:
        plugin = request.registry.require(str(factor_name))
        build_head = getattr(plugin, "build_head_snapshot", None)
        if not callable(build_head):
            continue
        head = build_head(
            series_id=request.series_id,
            state=state,
            runtime=request.runtime,
        )
        if isinstance(head, dict):
            out[str(factor_name)] = head
    return out


def persist_ingest_outputs(
    *,
    factor_store: FactorStore,
    topo_order: list[str],
    series_id: str,
    up_to: int,
    events: list[FactorEventWrite],
    head_snapshots: dict[str, dict[str, Any]],
    auto_rebuild: bool,
    fingerprint: str,
) -> int:
    with factor_store.connect() as conn:
        before_changes = connection_total_changes(conn)
        factor_store.insert_events_in_conn(conn, events=events)
        head_snapshot_attempts = 0
        for factor_name in topo_order:
            head = head_snapshots.get(str(factor_name))
            if not isinstance(head, dict):
                continue
            head_snapshot_attempts += 1
            factor_store.insert_head_snapshot_in_conn(
                conn,
                series_id=series_id,
                factor_name=str(factor_name),
                candle_time=int(up_to),
                head=head,
            )
        factor_store.upsert_head_time_in_conn(conn, series_id=series_id, head_time=int(up_to))
        if auto_rebuild:
            factor_store.upsert_series_fingerprint_in_conn(
                conn,
                series_id=series_id,
                fingerprint=fingerprint,
            )
        conn.commit()
        after_changes = connection_total_changes(conn)
        if before_changes is not None and after_changes is not None:
            return max(0, int(after_changes) - int(before_changes))
        return int(len(events)) + int(head_snapshot_attempts) + 1 + (1 if auto_rebuild else 0)
