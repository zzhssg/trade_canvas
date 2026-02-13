from __future__ import annotations

from types import SimpleNamespace
from typing import Mapping

import pytest

from backend.app.ledger.sync_service import LedgerSyncService
from backend.app.core.service_errors import ServiceError


class _StoreStub:
    def __init__(self, *, head: int | None, aligned: int | None) -> None:
        self._head = head
        self._aligned = aligned

    def head_time(self, series_id: str) -> int | None:  # noqa: ARG002
        return self._head

    def floor_time(self, series_id: str, *, at_time: int) -> int | None:  # noqa: ARG002
        if self._aligned is None:
            return None
        return int(self._aligned) if int(at_time) >= int(self._aligned) else None


class _HeadStoreStub:
    def __init__(self, *, head: int | None) -> None:
        self.head = head

    def head_time(self, series_id: str) -> int | None:  # noqa: ARG002
        return self.head


class _PipelineStub:
    def __init__(self, on_refresh=None) -> None:
        self.calls: list[dict[str, int]] = []
        self._on_refresh = on_refresh

    def refresh_series_sync(self, *, up_to_times: Mapping[str, int]):
        payload = {str(k): int(v) for k, v in up_to_times.items()}
        self.calls.append(payload)
        if self._on_refresh is not None:
            self._on_refresh(payload)
        return SimpleNamespace(steps=(SimpleNamespace(name="factor.ingest_closed:test"),))


def test_refresh_if_needed_skips_when_heads_already_ready() -> None:
    service = LedgerSyncService(
        store=_StoreStub(head=100, aligned=100),
        factor_store=_HeadStoreStub(head=200),
        overlay_store=_HeadStoreStub(head=200),
        ingest_pipeline=_PipelineStub(),
    )

    outcome = service.refresh_if_needed(series_id="binance:futures:BTC/USDT:1m", up_to_time=100)
    assert outcome.refreshed is False
    assert outcome.step_names == tuple()


def test_refresh_if_needed_triggers_pipeline_when_head_lagging() -> None:
    series_id = "binance:futures:BTC/USDT:1m"
    factor = _HeadStoreStub(head=90)
    overlay = _HeadStoreStub(head=90)

    def _promote(payload: dict[str, int]) -> None:
        new_head = int(payload[series_id])
        factor.head = new_head
        overlay.head = new_head

    pipeline = _PipelineStub(on_refresh=_promote)
    service = LedgerSyncService(
        store=_StoreStub(head=120, aligned=120),
        factor_store=factor,
        overlay_store=overlay,
        ingest_pipeline=pipeline,
    )

    outcome = service.refresh_if_needed(series_id=series_id, up_to_time=120)
    assert outcome.refreshed is True
    assert outcome.step_names == ("factor.ingest_closed:test",)
    assert pipeline.calls == [{series_id: 120}]


def test_require_heads_ready_raises_out_of_sync() -> None:
    service = LedgerSyncService(
        store=_StoreStub(head=120, aligned=120),
        factor_store=_HeadStoreStub(head=100),
        overlay_store=_HeadStoreStub(head=120),
        ingest_pipeline=_PipelineStub(),
    )

    with pytest.raises(ServiceError) as ctx:
        service.require_heads_ready(
            series_id="binance:futures:BTC/USDT:1m",
            aligned_time=120,
            factor_out_of_sync_code="factor.out_of_sync",
            overlay_out_of_sync_code="overlay.out_of_sync",
        )
    assert ctx.value.status_code == 409
    assert ctx.value.code == "factor.out_of_sync"
