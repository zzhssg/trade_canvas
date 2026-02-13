from __future__ import annotations

from backend.app.ingest_guardrail_registry import IngestGuardrailRegistry


def test_guardrail_registry_disabled_returns_none() -> None:
    registry = IngestGuardrailRegistry(enabled=False)

    assert registry.get("binance:spot:BTC/USDT:1m") is None
    assert registry.enabled is False


def test_guardrail_registry_reuses_guardrail_and_supports_drop() -> None:
    registry = IngestGuardrailRegistry(enabled=True)
    series_id = "binance:spot:BTC/USDT:1m"

    first = registry.get(series_id)
    second = registry.get(series_id)
    assert first is not None
    assert second is first

    registry.drop(series_id)
    third = registry.get(series_id)
    assert third is not None
    assert third is not first
