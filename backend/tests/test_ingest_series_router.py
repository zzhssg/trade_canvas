from __future__ import annotations

import pytest

from backend.app.ingest_series_router import IngestSeriesRouter, IngestSeriesRouterConfig
from backend.app.ingest_source_registry import IngestSourceBinding, IngestSourceRegistry


def _build_router() -> IngestSeriesRouter:
    async def _fake_ingest_fn(**kwargs) -> None:  # noqa: ANN003
        _ = kwargs

    source_registry = IngestSourceRegistry(
        bindings={
            "binance": IngestSourceBinding(
                source="binance_ws",
                get_ingest_fn=lambda: _fake_ingest_fn,
            )
        }
    )
    return IngestSeriesRouter(
        source_registry=source_registry,
        config=IngestSeriesRouterConfig(
            derived_enabled=True,
            derived_base_timeframe="1m",
            derived_timeframes=("5m",),
        ),
    )


def test_series_router_normalize_maps_derived_to_base() -> None:
    router = _build_router()

    normalized = router.normalize("binance:spot:BTC/USDT:5m")

    assert normalized == "binance:spot:BTC/USDT:1m"


def test_series_router_resolve_source_uses_series_exchange() -> None:
    router = _build_router()

    source_binding = router.resolve_source(series_id="binance:spot:BTC/USDT:1m")

    assert source_binding.source == "binance_ws"


def test_series_router_resolve_source_raises_for_unsupported_exchange() -> None:
    router = _build_router()

    with pytest.raises(ValueError, match="unsupported exchange for realtime ingest"):
        router.resolve_source(series_id="kraken:spot:BTC/USD:1m")
