from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from typing import Any, cast

from fastapi.testclient import TestClient

from backend.app.container import AppContainer
from backend.app.main import create_app


class DrawDeltaApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmpdir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tmpdir.name) / "market.db"
        os.environ["TRADE_CANVAS_DB_PATH"] = str(self.db_path)
        os.environ["TRADE_CANVAS_ENABLE_FACTOR_INGEST"] = "1"
        os.environ["TRADE_CANVAS_ENABLE_OVERLAY_INGEST"] = "1"
        os.environ["TRADE_CANVAS_PIVOT_WINDOW_MAJOR"] = "2"
        os.environ["TRADE_CANVAS_PIVOT_WINDOW_MINOR"] = "1"
        os.environ["TRADE_CANVAS_FACTOR_LOOKBACK_CANDLES"] = "5000"
        os.environ["TRADE_CANVAS_ENABLE_READ_REPAIR_API"] = "1"
        self.client = TestClient(create_app())
        self.series_id = "binance:futures:BTC/USDT:1m"

    def tearDown(self) -> None:
        self.tmpdir.cleanup()
        for k in (
            "TRADE_CANVAS_DB_PATH",
            "TRADE_CANVAS_ENABLE_FACTOR_INGEST",
            "TRADE_CANVAS_ENABLE_OVERLAY_INGEST",
            "TRADE_CANVAS_PIVOT_WINDOW_MAJOR",
            "TRADE_CANVAS_PIVOT_WINDOW_MINOR",
            "TRADE_CANVAS_FACTOR_LOOKBACK_CANDLES",
            "TRADE_CANVAS_ENABLE_READ_REPAIR_API",
        ):
            os.environ.pop(k, None)

    def _ingest(self, t: int, price: float) -> None:
        res = self.client.post(
            "/api/market/ingest/candle_closed",
            json={
                "series_id": self.series_id,
                "candle": {"candle_time": t, "open": price, "high": price, "low": price, "close": price, "volume": 1},
            },
        )
        self.assertEqual(res.status_code, 200, res.text)

    def _recreate_client(self) -> None:
        try:
            self.client.close()
        except Exception:
            pass
        self.client = TestClient(create_app())

    def _repair_overlay(self, *, to_time: int | None = None) -> None:
        payload: dict[str, object] = {"series_id": self.series_id}
        if to_time is not None:
            payload["to_time"] = int(to_time)
        repaired = self.client.post("/api/dev/repair/overlay", json=payload)
        self.assertEqual(repaired.status_code, 200, repaired.text)

    def _container(self) -> AppContainer:
        app = cast(Any, self.client.app)
        return cast(AppContainer, app.state.container)

    def test_draw_delta_is_overlay_compatible_and_cursor_idempotent(self) -> None:
        base = 60
        prices = [1, 2, 5, 2, 1, 2, 5, 2, 1]
        times = [base * (i + 1) for i in range(len(prices))]
        for t, p in zip(times, prices, strict=True):
            self._ingest(t, float(p))

        res_draw = self.client.get("/api/draw/delta", params={"series_id": self.series_id, "cursor_version_id": 0})
        self.assertEqual(res_draw.status_code, 200, res_draw.text)
        draw = res_draw.json()

        self.assertEqual(draw["series_id"], self.series_id)
        self.assertEqual(draw["to_candle_time"], times[-1])
        self.assertIn("series_points", draw)
        self.assertEqual(draw["series_points"], {})

        def pick_marker_defs(feature: str) -> list[dict]:
            out: list[dict] = []
            for item in draw.get("instruction_catalog_patch") or []:
                if not isinstance(item, dict) or item.get("kind") != "marker":
                    continue
                d = item.get("definition")
                if not isinstance(d, dict):
                    continue
                if d.get("feature") == feature:
                    out.append(d)
            return out

        def pick_polyline_defs(feature: str) -> list[dict]:
            out: list[dict] = []
            for item in draw.get("instruction_catalog_patch") or []:
                if not isinstance(item, dict) or item.get("kind") != "polyline":
                    continue
                d = item.get("definition")
                if not isinstance(d, dict):
                    continue
                if d.get("feature") == feature:
                    out.append(d)
            return out

        majors = pick_marker_defs("pivot.major")
        minors = pick_marker_defs("pivot.minor")
        self.assertTrue(majors, "expected at least one pivot.major marker in patch")
        self.assertTrue(minors, "expected at least one pivot.minor marker in patch")
        self.assertEqual(str(majors[0].get("shape")), "circle")
        self.assertEqual(str(minors[0].get("shape")), "circle")
        major_size = majors[0].get("size")
        minor_size = minors[0].get("size")
        self.assertIsInstance(major_size, (int, float))
        self.assertIsInstance(minor_size, (int, float))
        self.assertAlmostEqual(float(cast(int | float, major_size)), 1.0, places=6)
        self.assertAlmostEqual(float(cast(int | float, minor_size)), 0.5, places=6)
        # Regression: keep `text` field but should be blank.
        self.assertIn("text", majors[0])
        self.assertEqual(str(majors[0].get("text")), "")

        pens = pick_polyline_defs("pen.confirmed")
        self.assertTrue(pens, "expected pen.confirmed polyline")
        self.assertEqual(str(pens[0].get("color")), "#ffffff")
        self.assertEqual(str(pens[0].get("lineStyle") or "solid"), "solid")

        extending = pick_polyline_defs("pen.extending")
        candidate = pick_polyline_defs("pen.candidate")
        self.assertTrue(extending, "expected pen.extending polyline")
        self.assertTrue(candidate, "expected pen.candidate polyline")
        self.assertEqual(str(extending[0].get("color")), "#ffffff")
        self.assertEqual(str(candidate[0].get("color")), "#ffffff")
        self.assertEqual(str(extending[0].get("lineStyle")), "dashed")
        self.assertEqual(str(candidate[0].get("lineStyle")), "dashed")

        next_version = int(draw["next_cursor"]["version_id"])
        self.assertGreater(next_version, 0)

        res2 = self.client.get(
            "/api/draw/delta",
            params={"series_id": self.series_id, "cursor_version_id": next_version},
        )
        self.assertEqual(res2.status_code, 200, res2.text)
        payload2 = res2.json()
        self.assertEqual(int(payload2["next_cursor"]["version_id"]), next_version)
        self.assertEqual(payload2["instruction_catalog_patch"], [])
        self.assertEqual(payload2["series_points"], {})

    def test_draw_delta_supports_at_time_and_fails_when_overlay_lags(self) -> None:
        base = 60
        prices = [1, 2, 5, 2, 1, 2, 5, 2, 1]
        times = [base * (i + 1) for i in range(len(prices))]
        for t, p in zip(times, prices, strict=True):
            self._ingest(t, float(p))

        # at_time clamps the upper-bound to an aligned closed candle_time.
        t_mid = times[4]
        res_mid = self.client.get(
            "/api/draw/delta",
            params={"series_id": self.series_id, "cursor_version_id": 0, "at_time": t_mid},
        )
        self.assertEqual(res_mid.status_code, 200, res_mid.text)
        payload_mid = res_mid.json()
        self.assertEqual(payload_mid["to_candle_time"], t_mid)
        self.assertEqual(payload_mid["to_candle_id"], f"{self.series_id}:{t_mid}")

        # Force overlay head_time to lag behind, then requesting a later at_time must fail-safe.
        overlay_store = self._container().overlay_store
        with overlay_store.connect() as conn:
            conn.execute(
                "UPDATE overlay_series_state SET head_time = ? WHERE series_id = ?",
                (int(t_mid), self.series_id),
            )
            conn.commit()

        res_late = self.client.get(
            "/api/draw/delta",
            params={"series_id": self.series_id, "cursor_version_id": 0, "at_time": times[-1]},
        )
        self.assertEqual(res_late.status_code, 409, res_late.text)
        self.assertIn("ledger_out_of_sync", res_late.text)

    def test_draw_delta_live_strict_mode_rejects_when_overlay_head_stale(self) -> None:
        base = 60
        prices = [1, 2, 5, 2, 1, 2, 5, 2, 1]
        times = [base * (i + 1) for i in range(len(prices))]
        for t, p in zip(times, prices, strict=True):
            self._ingest(t, float(p))

        # Warm once so overlay rows exist.
        warm = self.client.get("/api/draw/delta", params={"series_id": self.series_id, "cursor_version_id": 0})
        self.assertEqual(warm.status_code, 200, warm.text)
        self.assertEqual(int(warm.json()["to_candle_time"]), int(times[-1]))

        # Simulate stale overlay head_time; strict read should fail fast.
        overlay_store = self._container().overlay_store
        with overlay_store.connect() as conn:
            conn.execute(
                "UPDATE overlay_series_state SET head_time = ? WHERE series_id = ?",
                (int(times[1]), self.series_id),
            )
            conn.commit()

        res_live = self.client.get("/api/draw/delta", params={"series_id": self.series_id, "cursor_version_id": 0})
        self.assertEqual(res_live.status_code, 409, res_live.text)
        self.assertIn("ledger_out_of_sync:overlay", res_live.text)

    def test_anchor_history_polyline_uses_blue_color(self) -> None:
        base = 60
        prices = [
            1,
            2,
            10,
            2,
            1,
            2,
            9,
            2,
            1,
            2,
            8,
            2,
            1,
            20,
            22,
            20,
            15,
            20,
            23,
            20,
            16,
            20,
            24,
            20,
            17,
            20,
            25,
            20,
            18,
            20,
        ]
        times = [base * (i + 1) for i in range(len(prices))]
        for t, p in zip(times, prices, strict=True):
            self._ingest(t, float(p))

        res_draw = self.client.get("/api/draw/delta", params={"series_id": self.series_id, "cursor_version_id": 0})
        self.assertEqual(res_draw.status_code, 200, res_draw.text)
        draw = res_draw.json()

        anchor_history: list[dict] = []
        for item in draw.get("instruction_catalog_patch") or []:
            if not isinstance(item, dict) or item.get("kind") != "polyline":
                continue
            definition = item.get("definition")
            if not isinstance(definition, dict):
                continue
            if definition.get("feature") == "anchor.history":
                anchor_history.append(definition)

        self.assertTrue(anchor_history, "expected anchor.history polyline in draw delta")
        self.assertEqual(str(anchor_history[0].get("color")), "rgba(59,130,246,0.55)")

    def test_anchor_history_does_not_duplicate_current_pointer(self) -> None:
        base = 60
        prices = [
            1,
            2,
            10,
            2,
            1,
            2,
            9,
            2,
            1,
            2,
            8,
            2,
            1,
            20,
            22,
            20,
            15,
            20,
            23,
            20,
            16,
            20,
            24,
            20,
            17,
            20,
            25,
            20,
            18,
            20,
        ]
        times = [base * (i + 1) for i in range(len(prices))]
        for t, p in zip(times, prices, strict=True):
            self._ingest(t, float(p))

        res_draw = self.client.get("/api/draw/delta", params={"series_id": self.series_id, "cursor_version_id": 0})
        self.assertEqual(res_draw.status_code, 200, res_draw.text)
        draw = res_draw.json()

        current_points: list[dict] | None = None
        history_points: list[list[dict]] = []
        for item in draw.get("instruction_catalog_patch") or []:
            if not isinstance(item, dict) or item.get("kind") != "polyline":
                continue
            definition = item.get("definition")
            if not isinstance(definition, dict):
                continue
            feature = definition.get("feature")
            if feature == "anchor.current":
                current_points = definition.get("points")
            elif feature == "anchor.history":
                history_points.append(definition.get("points") or [])

        self.assertIsNotNone(current_points, "expected anchor.current polyline")
        self.assertTrue(history_points, "expected anchor.history polylines")
        self.assertNotIn(current_points, history_points, "history should not duplicate current anchor pointer")

    def test_old_plot_and_overlay_delta_endpoints_are_removed(self) -> None:
        res_plot = self.client.get("/api/plot/delta", params={"series_id": self.series_id})
        self.assertEqual(res_plot.status_code, 404, res_plot.text)

        res_overlay = self.client.get("/api/overlay/delta", params={"series_id": self.series_id, "cursor_version_id": 0})
        self.assertEqual(res_overlay.status_code, 404, res_overlay.text)

    def test_draw_delta_requires_explicit_repair_when_anchor_current_missing(self) -> None:
        base = 60
        prices = [
            1,
            2,
            10,
            2,
            1,
            2,
            9,
            2,
            1,
            2,
            8,
            2,
            1,
            20,
            22,
            20,
            15,
            20,
            23,
            20,
            16,
            20,
            24,
            20,
            17,
            20,
            25,
            20,
            18,
            20,
        ]
        times = [base * (i + 1) for i in range(len(prices))]
        for t, p in zip(times, prices, strict=True):
            self._ingest(t, float(p))

        first = self.client.get("/api/draw/delta", params={"series_id": self.series_id, "cursor_version_id": 0})
        self.assertEqual(first.status_code, 200, first.text)
        self.assertIn("anchor.current", first.json().get("active_ids") or [])

        overlay_store = self._container().overlay_store
        with overlay_store.connect() as conn:
            conn.execute(
                "DELETE FROM overlay_instruction_versions WHERE series_id = ? AND instruction_id = ?",
                (self.series_id, "anchor.current"),
            )
            conn.commit()

        out_of_sync = self.client.get("/api/draw/delta", params={"series_id": self.series_id, "cursor_version_id": 0})
        self.assertEqual(out_of_sync.status_code, 409, out_of_sync.text)
        self.assertIn("ledger_out_of_sync:overlay", out_of_sync.text)
        self._repair_overlay(to_time=times[-1])
        repaired = self.client.get("/api/draw/delta", params={"series_id": self.series_id, "cursor_version_id": 0})
        self.assertEqual(repaired.status_code, 200, repaired.text)
        self.assertIn("anchor.current", repaired.json().get("active_ids") or [])

    def test_draw_delta_requires_explicit_repair_when_zhongshu_presence_mismatched(self) -> None:
        base = 60
        prices = [
            1,
            2,
            10,
            2,
            1,
            2,
            9,
            2,
            1,
            2,
            8,
            2,
            1,
            20,
            22,
            20,
            15,
            20,
            23,
            20,
            16,
            20,
            24,
            20,
            17,
            20,
            25,
            20,
            18,
            20,
        ]
        times = [base * (i + 1) for i in range(len(prices))]
        for t, p in zip(times, prices, strict=True):
            self._ingest(t, float(p))

        first = self.client.get("/api/draw/delta", params={"series_id": self.series_id, "cursor_version_id": 0})
        self.assertEqual(first.status_code, 200, first.text)
        first_ids = first.json().get("active_ids") or []
        self.assertTrue(any(str(i).startswith("zhongshu.") for i in first_ids), "expected zhongshu instructions before tampering")

        factor_store = self._container().factor_store
        with factor_store.connect() as conn:
            factor_store.clear_series_in_conn(conn, series_id=self.series_id)
            conn.commit()

        os.environ["TRADE_CANVAS_ENABLE_FACTOR_INGEST"] = "0"
        self._recreate_client()
        try:
            out_of_sync = self.client.get("/api/draw/delta", params={"series_id": self.series_id, "cursor_version_id": 0})
            self.assertEqual(out_of_sync.status_code, 409, out_of_sync.text)
            self.assertIn("ledger_out_of_sync", out_of_sync.text)
        finally:
            os.environ["TRADE_CANVAS_ENABLE_FACTOR_INGEST"] = "1"
            self._recreate_client()
        self._repair_overlay(to_time=times[-1])
        repaired = self.client.get("/api/draw/delta", params={"series_id": self.series_id, "cursor_version_id": 0})
        self.assertEqual(repaired.status_code, 200, repaired.text)

        zhongshu_patch_defs: list[dict] = []
        for item in repaired.json().get("instruction_catalog_patch") or []:
            if not isinstance(item, dict):
                continue
            instruction_id = str(item.get("instruction_id") or "")
            definition = item.get("definition")
            if instruction_id.startswith("zhongshu.") and isinstance(definition, dict):
                zhongshu_patch_defs.append(definition)
        self.assertTrue(zhongshu_patch_defs)

    def test_draw_delta_requires_explicit_repair_when_zhongshu_signature_mismatched(self) -> None:
        base = 60
        prices = [
            1,
            2,
            10,
            2,
            1,
            2,
            9,
            2,
            1,
            2,
            8,
            2,
            1,
            20,
            22,
            20,
            15,
            20,
            23,
            20,
            16,
            20,
            24,
            20,
            17,
            20,
            25,
            20,
            18,
            20,
        ]
        times = [base * (i + 1) for i in range(len(prices))]
        for t, p in zip(times, prices, strict=True):
            self._ingest(t, float(p))

        first = self.client.get("/api/draw/delta", params={"series_id": self.series_id, "cursor_version_id": 0})
        self.assertEqual(first.status_code, 200, first.text)
        first_ids = first.json().get("active_ids") or []
        self.assertTrue(any(str(i).startswith("zhongshu.") for i in first_ids), "expected zhongshu instructions before tampering")

        bogus_payload = {
            "type": "polyline",
            "feature": "zhongshu.dead",
            "points": [{"time": 1, "value": 1.0}, {"time": 2, "value": 1.0}],
            "color": "rgba(74,222,128,0.58)",
            "lineWidth": 2,
            "entryDirection": 1,
        }
        overlay_store = self._container().overlay_store
        with overlay_store.connect() as conn:
            conn.execute(
                """
                INSERT INTO overlay_instruction_versions(series_id, instruction_id, kind, visible_time, def_json, created_at_ms)
                VALUES (?, ?, 'polyline', ?, ?, 0)
                """,
                (
                    self.series_id,
                    "zhongshu.dead:bogus:top",
                    int(times[-1]),
                    json.dumps(bogus_payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True),
                ),
            )
            conn.commit()

        out_of_sync = self.client.get("/api/draw/delta", params={"series_id": self.series_id, "cursor_version_id": 0})
        self.assertEqual(out_of_sync.status_code, 409, out_of_sync.text)
        self.assertIn("ledger_out_of_sync:overlay", out_of_sync.text)
        self._repair_overlay(to_time=times[-1])
        repaired = self.client.get("/api/draw/delta", params={"series_id": self.series_id, "cursor_version_id": 0})
        self.assertEqual(repaired.status_code, 200, repaired.text)
        repaired_ids = repaired.json().get("active_ids") or []
        self.assertNotIn("zhongshu.dead:bogus:top", repaired_ids)

    def test_draw_delta_infers_dead_entry_direction_when_payload_missing(self) -> None:
        base = 60
        prices = [
            1,
            2,
            10,
            2,
            1,
            2,
            9,
            2,
            1,
            2,
            8,
            2,
            1,
            20,
            22,
            20,
            15,
            20,
            23,
            20,
            16,
            20,
            24,
            20,
            17,
            20,
            25,
            20,
            18,
            20,
        ]
        times = [base * (i + 1) for i in range(len(prices))]
        for t, p in zip(times, prices, strict=True):
            self._ingest(t, float(p))

        factor_store = self._container().factor_store
        overlay_store = self._container().overlay_store

        expected_by_start: dict[int, int] = {}
        with factor_store.connect() as conn:
            pen_rows = conn.execute(
                "SELECT payload_json FROM factor_events WHERE series_id = ? AND factor_name = 'pen' AND kind = 'pen.confirmed'",
                (self.series_id,),
            ).fetchall()
            for row in pen_rows:
                try:
                    payload = json.loads(row["payload_json"] or "{}")
                except Exception:
                    payload = {}
                if not isinstance(payload, dict):
                    continue
                try:
                    st = int(payload.get("start_time") or 0)
                    d = int(payload.get("direction") or 0)
                except Exception:
                    continue
                if st > 0 and d in {-1, 1}:
                    expected_by_start[st] = d

            dead_rows = conn.execute(
                "SELECT id, payload_json FROM factor_events WHERE series_id = ? AND factor_name = 'zhongshu' AND kind = 'zhongshu.dead'",
                (self.series_id,),
            ).fetchall()
            self.assertTrue(dead_rows, "expected zhongshu.dead rows for fallback test")
            for row in dead_rows:
                try:
                    payload = json.loads(row["payload_json"] or "{}")
                except Exception:
                    payload = {}
                if not isinstance(payload, dict):
                    continue
                payload.pop("entry_direction", None)
                conn.execute(
                    "UPDATE factor_events SET payload_json = ? WHERE id = ?",
                    (json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True), int(row["id"])),
                )
            conn.commit()

        with overlay_store.connect() as conn:
            overlay_store.clear_series_in_conn(conn, series_id=self.series_id)
            conn.commit()

        out_of_sync = self.client.get("/api/draw/delta", params={"series_id": self.series_id, "cursor_version_id": 0})
        self.assertEqual(out_of_sync.status_code, 409, out_of_sync.text)
        self.assertIn("ledger_out_of_sync:overlay", out_of_sync.text)
        self._repair_overlay(to_time=times[-1])
        repaired = self.client.get("/api/draw/delta", params={"series_id": self.series_id, "cursor_version_id": 0})
        self.assertEqual(repaired.status_code, 200, repaired.text)

        checked = 0
        for item in repaired.json().get("instruction_catalog_patch") or []:
            if not isinstance(item, dict):
                continue
            instruction_id = str(item.get("instruction_id") or "")
            if not instruction_id.startswith("zhongshu.dead:"):
                continue
            parts = instruction_id.split(":")
            self.assertGreaterEqual(len(parts), 6)
            start_time = int(parts[1])
            definition = item.get("definition")
            if not isinstance(definition, dict):
                continue
            direction = int(definition.get("entryDirection") or 0)
            expected = expected_by_start.get(start_time)
            if expected is None:
                continue
            self.assertEqual(direction, expected)
            checked += 1

        self.assertGreater(checked, 0, "expected at least one zhongshu.dead instruction to validate direction fallback")


if __name__ == "__main__":
    unittest.main()
