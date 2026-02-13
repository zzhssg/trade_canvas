from __future__ import annotations

import pytest

from backend.app.ingest.source_registry import IngestSourceBinding, IngestSourceRegistry


def test_source_registry_resolves_normalized_exchange() -> None:
    async def _fake_ingest_fn(**kwargs) -> None:  # noqa: ANN003
        _ = kwargs

    registry = IngestSourceRegistry(
        bindings={
            "binance": IngestSourceBinding(
                source="binance_ws",
                get_ingest_fn=lambda: _fake_ingest_fn,
            )
        }
    )

    binding = registry.resolve(exchange=" Binance ")
    assert binding.source == "binance_ws"
    assert binding.get_ingest_fn() is _fake_ingest_fn


def test_source_registry_raises_for_unsupported_exchange() -> None:
    registry = IngestSourceRegistry(bindings={})

    with pytest.raises(ValueError, match="unsupported exchange for realtime ingest"):
        registry.resolve(exchange="kraken")
