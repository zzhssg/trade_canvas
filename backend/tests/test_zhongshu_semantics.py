from __future__ import annotations

from backend.app.zhongshu import (
    build_alive_zhongshu_from_confirmed_pens,
    build_dead_zhongshus_from_confirmed_pens,
    init_zhongshu_state,
    update_zhongshu_state,
    update_zhongshu_state_on_closed_candle,
)


def _pen(start_time: int, end_time: int, start_price: float, end_price: float, visible_time: int) -> dict:
    return {
        "start_time": int(start_time),
        "end_time": int(end_time),
        "start_price": float(start_price),
        "end_price": float(end_price),
        "visible_time": int(visible_time),
        "direction": 1 if end_price >= start_price else -1,
    }


def test_alive_requires_entry_plus_three_followup_pens() -> None:
    pens = [
        _pen(10, 20, 100, 120, 100),
        _pen(20, 30, 115, 130, 200),
        _pen(30, 40, 118, 126, 300),
    ]

    alive_before = build_alive_zhongshu_from_confirmed_pens(pens, up_to_visible_time=300)
    assert alive_before is None

    pens.append(_pen(40, 50, 110, 119, 400))
    alive_after = build_alive_zhongshu_from_confirmed_pens(pens, up_to_visible_time=400)
    assert alive_after is not None
    assert alive_after.start_time == 10
    assert alive_after.formed_time == 400
    assert alive_after.end_time == 50


def test_dead_formed_time_uses_fourth_confirmed_pen() -> None:
    pens = [
        _pen(10, 20, 100, 120, 100),
        _pen(20, 30, 115, 130, 200),
        _pen(30, 40, 118, 126, 300),
        _pen(40, 50, 110, 119, 400),
        _pen(50, 60, 130, 140, 500),
    ]

    dead = build_dead_zhongshus_from_confirmed_pens(pens)
    assert len(dead) >= 1
    first = dead[0]
    assert first.entry_direction == 1
    assert first.formed_time == 400
    assert first.death_time == 500


def test_zone_uses_last_three_pens_and_stays_fixed_before_death() -> None:
    pens = [
        _pen(10, 20, 90, 110, 100),   # P1 entry
        _pen(20, 30, 100, 130, 200),  # P2
        _pen(30, 40, 105, 125, 300),  # P3
        _pen(40, 50, 102, 140, 400),  # P4 -> formed
        _pen(50, 60, 108, 124, 500),  # extension inside zone
        _pen(60, 70, 130, 150, 600),  # same-side outside -> death
    ]

    alive = build_alive_zhongshu_from_confirmed_pens(pens, up_to_visible_time=500)
    assert alive is not None
    assert alive.entry_direction == 1
    assert alive.zd == 105.0
    assert alive.zg == 125.0
    assert alive.end_time == 60

    dead = build_dead_zhongshus_from_confirmed_pens(pens)
    assert len(dead) >= 1
    first = dead[0]
    assert first.entry_direction == 1
    assert first.zd == 105.0
    assert first.zg == 125.0
    assert first.death_time == 600


def test_down_entry_uses_red_direction_flag() -> None:
    pens = [
        _pen(10, 20, 140, 120, 100),  # P1 entry (down)
        _pen(20, 30, 130, 110, 200),  # P2
        _pen(30, 40, 125, 108, 300),  # P3
        _pen(40, 50, 128, 112, 400),  # P4 -> formed
        _pen(50, 60, 100, 90, 500),   # same-side outside -> death
    ]

    alive = build_alive_zhongshu_from_confirmed_pens(pens, up_to_visible_time=400)
    assert alive is not None
    assert alive.entry_direction == -1

    dead = build_dead_zhongshus_from_confirmed_pens(pens)
    assert len(dead) >= 1
    assert dead[0].entry_direction == -1


def test_form_requires_four_pen_overlap_not_only_last_three() -> None:
    # P1 does not overlap with P2/P3/P4 shared range, so first 4-pen window must not form.
    pens = [
        _pen(10, 20, 100, 90, 100),    # P1 entry
        _pen(20, 30, 110, 130, 200),   # P2
        _pen(30, 40, 115, 125, 300),   # P3
        _pen(40, 50, 116, 126, 400),   # P4 (trio overlaps, but 4-pen overlap is empty)
    ]
    alive_before = build_alive_zhongshu_from_confirmed_pens(pens, up_to_visible_time=400)
    assert alive_before is None

    # Next window P2/P3/P4/P5 has 4-pen overlap and should form from P2 as entry.
    pens.append(_pen(50, 60, 112, 124, 500))  # P5
    alive_after = build_alive_zhongshu_from_confirmed_pens(pens, up_to_visible_time=500)
    assert alive_after is not None
    assert alive_after.start_time == 20
    assert alive_after.entry_direction == 1
    assert alive_after.zd == 116.0
    assert alive_after.zg == 124.0


def test_price_cross_confirms_alive_before_p3_confirmed() -> None:
    # entry up, then P1 down, P2 up; P3 extends down and first crosses P1.end on candle_time=350.
    p0 = _pen(10, 20, 100, 130, 100)
    p1 = _pen(20, 30, 130, 110, 200)
    p2 = _pen(30, 40, 110, 125, 300)

    state = init_zhongshu_state()
    update_zhongshu_state(state, p0)
    update_zhongshu_state(state, p1)
    update_zhongshu_state(state, p2)

    formed_entry = update_zhongshu_state_on_closed_candle(
        state,
        {"candle_time": 350, "high": 124.0, "low": 109.0},
    )
    assert formed_entry is not None
    alive = state.get("alive")
    assert isinstance(alive, dict)
    assert int(alive.get("formed_time") or 0) == 350
    assert str(alive.get("formed_reason") or "") == "price_cross"
    assert float(alive.get("zd") or 0.0) == 110.0
    assert float(alive.get("zg") or 0.0) == 125.0


def test_build_alive_with_candles_uses_price_cross_formed_time() -> None:
    pens = [
        _pen(10, 20, 100, 130, 100),  # entry
        _pen(20, 30, 130, 110, 200),  # P1
        _pen(30, 40, 110, 125, 300),  # P2
        _pen(40, 50, 125, 108, 500),  # P3 confirmed later
    ]

    class _C:
        def __init__(self, candle_time: int, high: float, low: float) -> None:
            self.candle_time = candle_time
            self.high = high
            self.low = low

    candles = [
        _C(300, 126.0, 120.0),
        _C(330, 124.0, 114.0),
        _C(350, 123.0, 109.0),  # first cross below P1.end_price=110
        _C(400, 121.0, 108.0),
        _C(500, 119.0, 107.0),
    ]

    alive = build_alive_zhongshu_from_confirmed_pens(
        pens,
        up_to_visible_time=500,
        candles=candles,
    )
    assert alive is not None
    assert alive.formed_time == 350
    assert alive.formed_reason == "price_cross"


def test_build_dead_with_candles_keeps_price_cross_formed_reason() -> None:
    pens = [
        _pen(10, 20, 100, 130, 100),  # entry
        _pen(20, 30, 130, 110, 200),  # P1
        _pen(30, 40, 110, 125, 300),  # P2
        _pen(40, 50, 125, 108, 500),  # P3 confirmed later
        _pen(50, 60, 108, 90, 700),   # death pen (fully below ZD=110)
    ]

    class _C:
        def __init__(self, candle_time: int, high: float, low: float) -> None:
            self.candle_time = candle_time
            self.high = high
            self.low = low

    candles = [
        _C(300, 126.0, 120.0),
        _C(330, 124.0, 114.0),
        _C(350, 123.0, 109.0),  # first cross below P1.end_price=110
        _C(500, 119.0, 107.0),
        _C(700, 100.0, 89.0),
    ]

    dead = build_dead_zhongshus_from_confirmed_pens(pens, candles=candles, up_to_visible_time=700)
    assert len(dead) >= 1
    first = dead[0]
    assert first.formed_reason == "price_cross"
    assert first.formed_time == 350
    assert first.death_time == 700


def test_death_reseed_uses_p0_floor_and_waits_until_overlap() -> None:
    # First zhongshu forms on pens[0..3], then dies at pens[4].
    pens = [
        _pen(10, 20, 90, 120, 100),
        _pen(20, 30, 120, 100, 200),
        _pen(30, 40, 100, 115, 300),
        _pen(40, 50, 115, 105, 400),  # p0 for reseed after death
        _pen(50, 60, 116, 130, 500),  # death pen (p1)
    ]

    state = init_zhongshu_state()
    for idx, p in enumerate(pens[:4]):
        dead, formed_entry = update_zhongshu_state(state, p)
        assert dead is None
        if idx < 3:
            assert formed_entry is None
        else:
            assert formed_entry is not None

    alive_before_death = state.get("alive")
    assert isinstance(alive_before_death, dict)
    assert int(alive_before_death.get("start_time") or 0) == 10

    dead_event, formed_entry = update_zhongshu_state(state, pens[4])
    assert dead_event is not None
    assert formed_entry is None
    assert state.get("alive") is None
    # With p0 floor enabled, immediate reseed cannot use pens before p0.
    assert state.get("pending") is None
    assert int(state.get("reseed_floor_start_time") or 0) == 40

    # Build pending from p0/p1/p2.
    p2 = _pen(60, 70, 130, 120, 600)
    dead_event, formed_entry = update_zhongshu_state(state, p2)
    assert dead_event is None
    assert formed_entry is None
    pending = state.get("pending")
    assert isinstance(pending, dict)
    assert int((pending.get("entry_pen") or {}).get("start_time") or 0) == 40

    # First p3 attempt has no 4-pen overlap from p0, so no alive yet.
    p3_no_overlap = _pen(70, 80, 120, 128, 700)
    dead_event, formed_entry = update_zhongshu_state(state, p3_no_overlap)
    assert dead_event is None
    assert formed_entry is None
    assert state.get("alive") is None

    # Keep scanning forward; once overlap exists, new zhongshu forms.
    p3_overlap = _pen(80, 90, 128, 127, 800)
    dead_event, formed_entry = update_zhongshu_state(state, p3_overlap)
    assert dead_event is None
    assert formed_entry is not None
    alive_after = state.get("alive")
    assert isinstance(alive_after, dict)
    assert int(alive_after.get("start_time") or 0) == 50
    assert int(alive_after.get("entry_direction") or 0) == 1
