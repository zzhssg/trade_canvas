from __future__ import annotations

import time
import unittest

from backend.app.market.series_cooldown_slots import SeriesCooldownSlots


class SeriesCooldownSlotsTests(unittest.TestCase):
    def test_try_acquire_debounces_same_series(self) -> None:
        slots = SeriesCooldownSlots(cooldown_seconds=60.0)
        self.assertTrue(slots.try_acquire(series_id="binance:futures:BTC/USDT:1m"))
        self.assertFalse(slots.try_acquire(series_id="binance:futures:BTC/USDT:1m"))
        self.assertTrue(slots.try_acquire(series_id="binance:futures:ETH/USDT:1m"))
        slots.release(series_id="binance:futures:BTC/USDT:1m")
        self.assertFalse(slots.try_acquire(series_id="binance:futures:BTC/USDT:1m"))

    def test_try_acquire_target_allows_newer_target_immediately(self) -> None:
        slots = SeriesCooldownSlots(cooldown_seconds=60.0)
        series_id = "binance:spot:ETH/USDT:1d"
        self.assertTrue(slots.try_acquire_target(series_id=series_id, target_time=160))
        self.assertFalse(slots.try_acquire_target(series_id=series_id, target_time=160))
        slots.release_target(series_id=series_id, target_time=160)
        self.assertFalse(slots.try_acquire_target(series_id=series_id, target_time=150))
        self.assertTrue(slots.try_acquire_target(series_id=series_id, target_time=220))
        slots.release_target(series_id=series_id, target_time=220)
        self.assertFalse(slots.try_acquire_target(series_id=series_id, target_time=220))

    def test_zero_cooldown_is_clamped(self) -> None:
        slots = SeriesCooldownSlots(cooldown_seconds=0.0)
        series_id = "binance:spot:BTC/USDT:5m"
        self.assertTrue(slots.try_acquire(series_id=series_id))
        slots.release(series_id=series_id)
        self.assertFalse(slots.try_acquire(series_id=series_id))
        time.sleep(0.11)
        self.assertTrue(slots.try_acquire(series_id=series_id))


if __name__ == "__main__":
    unittest.main()
