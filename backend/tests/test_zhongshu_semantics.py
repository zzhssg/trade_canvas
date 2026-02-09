from __future__ import annotations

from backend.app.zhongshu import build_alive_zhongshu_from_confirmed_pens, build_dead_zhongshus_from_confirmed_pens


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
