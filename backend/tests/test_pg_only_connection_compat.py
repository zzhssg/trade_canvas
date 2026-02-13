from __future__ import annotations

from types import SimpleNamespace
from typing import Any, Literal, cast

from backend.app.factor.orchestrator import FactorOrchestrator
from backend.app.factor.store import FactorEventWrite
from backend.app.overlay.ingest_writer import OverlayInstructionWriter


class _ConnWithoutTotalChanges:
    def __init__(self) -> None:
        self.committed = False

    def commit(self) -> None:
        self.committed = True


class _Ctx:
    def __init__(self, conn: Any) -> None:
        self._conn = conn

    def __enter__(self) -> Any:
        return self._conn

    def __exit__(self, exc_type, exc, tb) -> Literal[False]:
        return False


class _FactorStoreWithoutTotalChanges:
    def __init__(self) -> None:
        self.conn = _ConnWithoutTotalChanges()
        self.events: list[FactorEventWrite] = []
        self.head_snapshots: list[tuple[str, str, int]] = []
        self.head_updates: list[tuple[str, int]] = []
        self.fingerprints: list[tuple[str, str]] = []

    def connect(self) -> _Ctx:
        return _Ctx(self.conn)

    def insert_events_in_conn(self, conn: Any, *, events: list[FactorEventWrite]) -> None:
        self.events.extend(list(events))

    def insert_head_snapshot_in_conn(
        self,
        conn: Any,
        *,
        series_id: str,
        factor_name: str,
        candle_time: int,
        head: dict[str, Any],
    ) -> int:
        self.head_snapshots.append((str(series_id), str(factor_name), int(candle_time)))
        return 0

    def upsert_head_time_in_conn(self, conn: Any, *, series_id: str, head_time: int) -> None:
        self.head_updates.append((str(series_id), int(head_time)))

    def upsert_series_fingerprint_in_conn(self, conn: Any, *, series_id: str, fingerprint: str) -> None:
        self.fingerprints.append((str(series_id), str(fingerprint)))


class _OverlayStoreWithoutTotalChanges:
    def __init__(self) -> None:
        self.conn = _ConnWithoutTotalChanges()
        self.latest_by_instruction: dict[str, dict[str, Any]] = {}
        self.head_updates: list[tuple[str, int]] = []
        self.versions: list[str] = []

    def connect(self) -> _Ctx:
        return _Ctx(self.conn)

    def get_latest_def_for_instruction_in_conn(
        self,
        conn: Any,
        *,
        series_id: str,
        instruction_id: str,
    ) -> dict[str, Any] | None:
        return self.latest_by_instruction.get(str(instruction_id))

    def insert_instruction_version_in_conn(
        self,
        conn: Any,
        *,
        series_id: str,
        instruction_id: str,
        kind: str,
        visible_time: int,
        payload: dict[str, Any],
    ) -> int:
        self.latest_by_instruction[str(instruction_id)] = dict(payload)
        self.versions.append(str(instruction_id))
        return len(self.versions)

    def upsert_head_time_in_conn(self, conn: Any, *, series_id: str, head_time: int) -> None:
        self.head_updates.append((str(series_id), int(head_time)))


def test_factor_orchestrator_persist_outputs_supports_connection_without_total_changes() -> None:
    factor_store = _FactorStoreWithoutTotalChanges()
    orchestrator = FactorOrchestrator.__new__(FactorOrchestrator)
    cast(Any, orchestrator)._factor_store = factor_store
    cast(Any, orchestrator)._graph = SimpleNamespace(topo_order=("pivot", "pen"))
    events = [
        FactorEventWrite(
            series_id="binance:futures:BTC/USDT:1m",
            factor_name="pivot",
            candle_time=100,
            kind="pivot.major",
            event_key="pivot:100",
            payload={"candle_time": 100},
        ),
        FactorEventWrite(
            series_id="binance:futures:BTC/USDT:1m",
            factor_name="pen",
            candle_time=100,
            kind="pen.confirmed",
            event_key="pen:100",
            payload={"candle_time": 100},
        ),
    ]

    wrote = orchestrator._persist_ingest_outputs(
        series_id="binance:futures:BTC/USDT:1m",
        up_to=100,
        events=events,
        head_snapshots={"pivot": {"a": 1}, "pen": {"b": 2}},
        auto_rebuild=True,
        fingerprint="fp:v1",
    )

    assert wrote == 6
    assert factor_store.conn.committed is True
    assert len(factor_store.events) == 2
    assert len(factor_store.head_snapshots) == 2
    assert factor_store.head_updates[-1] == ("binance:futures:BTC/USDT:1m", 100)
    assert factor_store.fingerprints[-1] == ("binance:futures:BTC/USDT:1m", "fp:v1")


def test_overlay_instruction_writer_supports_connection_without_total_changes() -> None:
    overlay_store = _OverlayStoreWithoutTotalChanges()
    writer = OverlayInstructionWriter(overlay_store=overlay_store)  # type: ignore[arg-type]

    wrote_first = writer.persist(
        series_id="binance:futures:BTC/USDT:1m",
        to_time=160,
        marker_defs=[("m-1", "marker", 160, {"a": 1})],
        polyline_defs=[("p-1", 160, {"points": [1, 2]})],
    )
    wrote_second = writer.persist(
        series_id="binance:futures:BTC/USDT:1m",
        to_time=220,
        marker_defs=[("m-1", "marker", 220, {"a": 1})],
        polyline_defs=[("p-1", 220, {"points": [1, 2]})],
    )

    assert wrote_first == 3
    assert wrote_second == 1
    assert overlay_store.conn.committed is True
    assert overlay_store.head_updates[-1] == ("binance:futures:BTC/USDT:1m", 220)
