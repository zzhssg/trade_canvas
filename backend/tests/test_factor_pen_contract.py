from __future__ import annotations

from backend.app.factor_pen_contract import (
    anchor_pen_ref_key,
    build_anchor_pen_ref,
    build_confirmed_pen_payload,
    normalize_confirmed_pen_payload,
    pen_strength,
)
from backend.app.pen import ConfirmedPen


def test_build_confirmed_pen_payload_from_dataclass() -> None:
    pen = ConfirmedPen(
        start_time=120,
        end_time=180,
        start_price=100.5,
        end_price=103.0,
        direction=1,
        visible_time=240,
        start_idx=10,
        end_idx=20,
    )
    payload = build_confirmed_pen_payload(pen)
    assert payload["start_time"] == 120
    assert payload["end_time"] == 180
    assert payload["direction"] == 1
    assert payload["start_idx"] == 10
    assert payload["end_idx"] == 20


def test_normalize_confirmed_pen_payload_is_tolerant_to_raw_types() -> None:
    payload = normalize_confirmed_pen_payload(
        {
            "start_time": "120",
            "end_time": 180.2,
            "start_price": "99.5",
            "end_price": "101.0",
            "direction": "-1",
            "visible_time": "240",
            "start_idx": "15",
            "end_idx": "bad",
        }
    )
    assert payload["start_time"] == 120
    assert payload["end_time"] == 180
    assert payload["start_price"] == 99.5
    assert payload["end_price"] == 101.0
    assert payload["direction"] == -1
    assert payload["visible_time"] == 240
    assert payload["start_idx"] == 15
    assert payload["end_idx"] is None


def test_anchor_pen_ref_helpers_and_strength() -> None:
    ref = build_anchor_pen_ref(
        {"start_time": "60", "end_time": 120, "direction": "1"},
        kind="confirmed",
    )
    assert ref == {"kind": "confirmed", "start_time": 60, "end_time": 120, "direction": 1}
    assert anchor_pen_ref_key(ref) == (60, 120, 1)
    assert pen_strength({"start_price": 90.0, "end_price": 120.0}) == 30.0
