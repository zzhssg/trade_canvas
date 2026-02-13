from __future__ import annotations

import unittest

from backend.app.runtime.metrics import RuntimeMetrics


class RuntimeMetricsTests(unittest.TestCase):
    def test_metrics_noop_when_disabled(self) -> None:
        metrics = RuntimeMetrics(enabled=False)
        metrics.incr("ingest_total")
        metrics.observe_ms("ingest_duration_ms", duration_ms=12.5)
        metrics.set_gauge("lag_seconds", value=3.0)
        snapshot = metrics.snapshot()
        self.assertFalse(snapshot["enabled"])
        self.assertEqual(snapshot["counters"], {})
        self.assertEqual(snapshot["timers"], {})
        self.assertEqual(snapshot["gauges"], {})

    def test_metrics_collect_counter_timer_and_gauge(self) -> None:
        metrics = RuntimeMetrics(enabled=True)
        metrics.incr("ingest_total", labels={"result": "ok"})
        metrics.incr("ingest_total", labels={"result": "ok"})
        metrics.observe_ms("ingest_duration_ms", duration_ms=10.0, labels={"result": "ok"})
        metrics.observe_ms("ingest_duration_ms", duration_ms=20.0, labels={"result": "ok"})
        metrics.set_gauge("head_lag_seconds", value=5.0, labels={"series_id": "binance:futures:BTC/USDT:1m"})

        snapshot = metrics.snapshot()
        self.assertTrue(snapshot["enabled"])
        self.assertEqual(snapshot["counters"]["ingest_total{result=ok}"], 2.0)
        timer = snapshot["timers"]["ingest_duration_ms{result=ok}"]
        self.assertEqual(timer["count"], 2.0)
        self.assertEqual(timer["total_ms"], 30.0)
        self.assertEqual(timer["max_ms"], 20.0)
        self.assertEqual(timer["avg_ms"], 15.0)
        self.assertEqual(
            snapshot["gauges"]["head_lag_seconds{series_id=binance:futures:BTC/USDT:1m}"],
            5.0,
        )


if __name__ == "__main__":
    unittest.main()
