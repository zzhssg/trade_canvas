from __future__ import annotations

from dataclasses import dataclass

import pytest

from backend.app.read_models import FactorReadService
from backend.app.core.schemas import GetFactorSlicesResponseV1
from backend.app.core.service_errors import ServiceError


class _Store:
    def __init__(self, *, aligned: int | None) -> None:
        self.aligned = aligned
        self.floor_calls: list[tuple[str, int]] = []

    def floor_time(self, series_id: str, *, at_time: int) -> int | None:
        self.floor_calls.append((str(series_id), int(at_time)))
        return self.aligned


@dataclass(frozen=True)
class _FactorStore:
    head: int | None

    def head_time(self, series_id: str) -> int | None:
        _ = series_id
        return self.head


class _Slices:
    def __init__(self) -> None:
        self.calls: list[tuple[str, int | None, int, int]] = []

    def get_slices_aligned(
        self,
        *,
        series_id: str,
        aligned_time: int | None,
        at_time: int,
        window_candles: int,
    ) -> GetFactorSlicesResponseV1:
        self.calls.append((str(series_id), aligned_time, int(at_time), int(window_candles)))
        candle_id = f"{series_id}:{int(aligned_time)}" if aligned_time is not None else None
        return GetFactorSlicesResponseV1(
            series_id=str(series_id),
            at_time=int(at_time),
            candle_id=candle_id,
        )


def test_factor_read_service_strict_mode_rejects_stale_factor() -> None:
    slices = _Slices()
    service = FactorReadService(
        store=_Store(aligned=300),
        factor_store=_FactorStore(head=240),
        factor_slices_service=slices,
        strict_mode=True,
    )

    with pytest.raises(ServiceError) as exc:
        service.read_slices(series_id="s", at_time=300, window_candles=50, ensure_fresh=True)

    assert exc.value.status_code == 409
    assert "ledger_out_of_sync:factor" in str(exc.value.detail)
    assert slices.calls == []


def test_factor_read_service_can_skip_freshness_check_explicitly() -> None:
    slices = _Slices()
    service = FactorReadService(
        store=_Store(aligned=300),
        factor_store=_FactorStore(head=0),
        factor_slices_service=slices,
        strict_mode=True,
    )

    out = service.read_slices(
        series_id="s",
        at_time=300,
        aligned_time=300,
        window_candles=20,
        ensure_fresh=False,
    )

    assert slices.calls == [("s", 300, 300, 20)]
    assert out.candle_id == "s:300"


def test_factor_read_service_default_is_strict() -> None:
    slices = _Slices()
    service = FactorReadService(
        store=_Store(aligned=180),
        factor_store=_FactorStore(head=100),
        factor_slices_service=slices,
    )

    with pytest.raises(ServiceError):
        service.read_slices(series_id="s", at_time=200, window_candles=100, ensure_fresh=True)
