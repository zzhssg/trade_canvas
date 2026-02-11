from __future__ import annotations

import unittest
from typing import Any, cast

from backend.app.factor_graph import FactorGraph, FactorSpec
from backend.app.factor_plugin_contract import FactorPluginSpec
from backend.app.factor_plugin_registry import FactorPluginRegistry
from backend.app.factor_processor_slice_buckets import SliceBucketSpec, build_default_slice_bucket_specs
from backend.app.factor_slice_plugins import build_default_factor_slice_plugins
from backend.app.factor_slices_service import FactorSlicesService
from backend.app.schemas import FactorMetaV1, FactorSliceV1


class _FakeCandleStore:
    def floor_time(self, series_id: str, at_time: int) -> int | None:
        return int(at_time)


class _FakeFactorStore:
    def get_events_between_times(
        self,
        *,
        series_id: str,
        factor_name: str | None,
        start_candle_time: int,
        end_candle_time: int,
        limit: int = 20000,
    ) -> list:
        return []

    def get_head_at_or_before(self, *, series_id: str, factor_name: str, candle_time: int):
        return None


class _StubSlicePlugin:
    def __init__(
        self,
        *,
        factor_name: str,
        depends_on: tuple[str, ...] = (),
        calls: list[str] | None = None,
        bucket_specs: tuple[SliceBucketSpec, ...] = (),
    ) -> None:
        self.spec = FactorPluginSpec(factor_name=factor_name, depends_on=depends_on)
        self.bucket_specs = bucket_specs
        self._calls = calls

    def build_snapshot(self, ctx) -> FactorSliceV1 | None:
        if self._calls is not None:
            self._calls.append(self.spec.factor_name)
        return FactorSliceV1(
            history={},
            head={},
            meta=FactorMetaV1(
                series_id=ctx.series_id,
                at_time=int(ctx.aligned_time),
                candle_id=ctx.candle_id,
                factor_name=self.spec.factor_name,
            ),
        )


class FactorSlicePluginsTests(unittest.TestCase):
    def test_default_slice_plugins_are_graph_ready_and_cover_bucket_specs(self) -> None:
        plugins = build_default_factor_slice_plugins()
        registry = FactorPluginRegistry(list(plugins))
        graph = FactorGraph([FactorSpec(factor_name=s.factor_name, depends_on=s.depends_on) for s in registry.specs()])
        self.assertEqual(graph.topo_order, ("pivot", "pen", "zhongshu", "anchor"))

        from_plugins = {
            (spec.factor_name, spec.event_kind, spec.bucket_name)
            for plugin in plugins
            for spec in plugin.bucket_specs
        }
        from_defaults = {
            (spec.factor_name, spec.event_kind, spec.bucket_name) for spec in build_default_slice_bucket_specs()
        }
        self.assertEqual(from_plugins, from_defaults)

    def test_factor_slices_service_runs_plugins_in_topo_order(self) -> None:
        calls: list[str] = []
        plugins = (
            _StubSlicePlugin(factor_name="gamma", depends_on=("beta",), calls=calls),
            _StubSlicePlugin(factor_name="alpha", depends_on=(), calls=calls),
            _StubSlicePlugin(factor_name="beta", depends_on=("alpha",), calls=calls),
        )
        service = FactorSlicesService(
            candle_store=cast(Any, _FakeCandleStore()),
            factor_store=cast(Any, _FakeFactorStore()),
            slice_plugins=plugins,
        )
        payload = service.get_slices_aligned(
            series_id="binance:futures:BTC/USDT:1m",
            aligned_time=180,
            at_time=180,
            window_candles=200,
        )
        self.assertEqual(calls, ["alpha", "beta", "gamma"])
        self.assertEqual(payload.factors, ["alpha", "beta", "gamma"])

    def test_factor_slices_service_rejects_bucket_conflict(self) -> None:
        plugins = (
            _StubSlicePlugin(
                factor_name="pivot",
                bucket_specs=(SliceBucketSpec(factor_name="pivot", event_kind="pivot.major", bucket_name="a"),),
            ),
            _StubSlicePlugin(
                factor_name="pen",
                bucket_specs=(SliceBucketSpec(factor_name="pivot", event_kind="pivot.major", bucket_name="b"),),
            ),
        )
        with self.assertRaises(RuntimeError) as ctx:
            _ = FactorSlicesService(
                candle_store=cast(Any, _FakeCandleStore()),
                factor_store=cast(Any, _FakeFactorStore()),
                slice_plugins=plugins,
            )
        self.assertIn("factor_slice_bucket_conflict:pivot:pivot.major", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
