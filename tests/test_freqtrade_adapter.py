from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path


class TestFreqtradeAdapter(unittest.TestCase):
    def test_annotate_sma_cross_smoke(self) -> None:
        try:
            import pandas as pd  # type: ignore
        except Exception:
            self.skipTest("pandas not installed")

        from trade_canvas.freqtrade_adapter import annotate_sma_cross

        fixture = Path(__file__).resolve().parents[1] / "fixtures" / "klines_mock_BTCUSDT_1m_60.jsonl"
        rows = []
        for line in fixture.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            obj = json.loads(line)
            rows.append(
                {
                    "date": pd.to_datetime(int(obj["open_time"]), unit="s", utc=True),
                    "open": float(obj["open"]),
                    "high": float(obj["high"]),
                    "low": float(obj["low"]),
                    "close": float(obj["close"]),
                    "volume": float(obj["volume"]),
                }
            )
        df = pd.DataFrame(rows)
        self.assertFalse(df.empty)

        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "strategy.db"
            res = annotate_sma_cross(
                df,
                pair="BTC/USDT",
                timeframe="1m",
                fast=5,
                slow=20,
                db_path=db_path,
            )
            self.assertTrue(res.ok, res.reason)
            out = res.dataframe
            for col in ("tc_ok", "tc_sma_fast", "tc_sma_slow", "tc_open_long"):
                self.assertIn(col, out.columns)

            # With this fixture, we expect at least one cross.
            self.assertGreaterEqual(int(out["tc_open_long"].sum()), 1)
