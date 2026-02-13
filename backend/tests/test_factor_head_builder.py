from __future__ import annotations

from backend.app.factor.head_builder import build_pen_head_snapshot, build_zhongshu_alive_head
from backend.app.schemas import CandleClosed


def _candles() -> list[CandleClosed]:
    return [
        CandleClosed(candle_time=60, open=1.0, high=2.0, low=0.5, close=1.5, volume=1.0),
        CandleClosed(candle_time=120, open=1.5, high=3.0, low=1.0, close=2.5, volume=1.0),
        CandleClosed(candle_time=180, open=2.5, high=2.8, low=1.8, close=2.0, volume=1.0),
        CandleClosed(candle_time=240, open=2.0, high=3.2, low=1.9, close=3.0, volume=1.0),
    ]


def test_build_pen_head_snapshot_accepts_dict_pivots() -> None:
    out = build_pen_head_snapshot(
        confirmed_pens=[{"start_time": 60, "end_time": 120, "direction": 1}],
        effective_pivots=[
            {
                "pivot_time": 60,
                "pivot_price": 0.5,
                "direction": "support",
                "visible_time": 120,
            },
            {
                "pivot_time": 120,
                "pivot_price": 3.0,
                "direction": "resistance",
                "visible_time": 180,
            },
        ],
        candles=_candles(),
        aligned_time=240,
    )
    assert isinstance(out, dict)


def test_build_pen_head_snapshot_requires_confirmed_pens() -> None:
    out = build_pen_head_snapshot(
        confirmed_pens=[],
        effective_pivots=[],
        candles=_candles(),
        aligned_time=240,
    )
    assert out is None


def test_build_zhongshu_alive_head_from_state_dict() -> None:
    out = build_zhongshu_alive_head(
        zhongshu_state={
            "alive": {
                "start_time": 60,
                "end_time": 120,
                "zg": 3.0,
                "zd": 2.0,
                "entry_direction": 1,
                "formed_time": 120,
                "formed_reason": "pen_confirmed",
            }
        },
        confirmed_pens=[],
        candles=[],
        aligned_time=240,
    )
    assert out["alive"][0]["visible_time"] == 240
    assert out["alive"][0]["start_time"] == 60


def test_build_zhongshu_alive_head_from_state_list() -> None:
    out = build_zhongshu_alive_head(
        zhongshu_state={"alive": [{"start_time": 60, "end_time": 120, "visible_time": 240}]},
        confirmed_pens=[],
        candles=[],
        aligned_time=240,
    )
    assert out == {"alive": [{"start_time": 60, "end_time": 120, "visible_time": 240}]}
