from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from backend.app.factor.store import FactorEventWrite, FactorStore


class FactorStoreEventsTests(unittest.TestCase):
    def test_get_events_between_times_paged_returns_full_window(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            store = FactorStore(db_path=Path(tmpdir) / "factor.db")
            with store.connect() as conn:
                events = [
                    FactorEventWrite(
                        series_id="s",
                        factor_name="pivot",
                        candle_time=100 + int(i // 2),
                        kind="pivot.major",
                        event_key=f"e:{i}",
                        payload={"i": int(i)},
                    )
                    for i in range(25)
                ]
                store.insert_events_in_conn(conn, events=events)
                conn.commit()

            limited = store.get_events_between_times(
                series_id="s",
                factor_name=None,
                start_candle_time=100,
                end_candle_time=120,
                limit=10,
            )
            self.assertEqual(len(limited), 10)

            paged = store.get_events_between_times_paged(
                series_id="s",
                factor_name=None,
                start_candle_time=100,
                end_candle_time=120,
                page_size=10,
            )
            self.assertEqual(len(paged), 25)
            self.assertEqual(paged[0].event_key, "e:0")
            self.assertEqual(paged[-1].event_key, "e:24")

    def test_get_events_between_times_paged_respects_factor_filter(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            store = FactorStore(db_path=Path(tmpdir) / "factor.db")
            with store.connect() as conn:
                events = []
                for i in range(12):
                    events.append(
                        FactorEventWrite(
                            series_id="s",
                            factor_name="pivot" if i % 2 == 0 else "pen",
                            candle_time=200 + i,
                            kind="pivot.major" if i % 2 == 0 else "pen.confirmed",
                            event_key=f"k:{i}",
                            payload={"i": int(i)},
                        )
                    )
                store.insert_events_in_conn(conn, events=events)
                conn.commit()

            only_pen = store.get_events_between_times_paged(
                series_id="s",
                factor_name="pen",
                start_candle_time=200,
                end_candle_time=220,
                page_size=3,
            )
            self.assertEqual(len(only_pen), 6)
            self.assertTrue(all(r.factor_name == "pen" for r in only_pen))
            self.assertEqual([r.event_key for r in only_pen], ["k:1", "k:3", "k:5", "k:7", "k:9", "k:11"])

    def test_iter_events_between_times_paged_matches_list_variant(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            store = FactorStore(db_path=Path(tmpdir) / "factor.db")
            with store.connect() as conn:
                events = [
                    FactorEventWrite(
                        series_id="s",
                        factor_name="pivot",
                        candle_time=300 + i,
                        kind="pivot.major",
                        event_key=f"it:{i}",
                        payload={"i": int(i)},
                    )
                    for i in range(17)
                ]
                store.insert_events_in_conn(conn, events=events)
                conn.commit()

            as_list = store.get_events_between_times_paged(
                series_id="s",
                factor_name=None,
                start_candle_time=300,
                end_candle_time=400,
                page_size=5,
            )
            as_iter = list(
                store.iter_events_between_times_paged(
                    series_id="s",
                    factor_name=None,
                    start_candle_time=300,
                    end_candle_time=400,
                    page_size=5,
                )
            )
            self.assertEqual([r.event_key for r in as_iter], [r.event_key for r in as_list])


if __name__ == "__main__":
    unittest.main()
