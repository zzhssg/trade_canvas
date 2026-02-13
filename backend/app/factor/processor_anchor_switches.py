from __future__ import annotations

from bisect import bisect_right
from typing import Any, Callable, Mapping

from .anchor_semantics import should_append_switch
from .pen_contract import anchor_pen_ref_key, build_anchor_switch_payload
from .store import FactorEventWrite


def pen_ref_key_from_ref(ref: Mapping[str, Any]) -> tuple[int, int, int] | None:
    return anchor_pen_ref_key(ref)


def build_confirmed_pen_ref_index(
    confirmed_pens: list[dict[str, Any]],
) -> dict[tuple[int, int, int], dict[str, Any]]:
    out: dict[tuple[int, int, int], dict[str, Any]] = {}
    for pen in confirmed_pens:
        key = pen_ref_key_from_ref(pen)
        if key is not None:
            out[key] = pen
    return out


def last_confirmed_pen_before_or_at(
    *,
    confirmed_pens: list[dict[str, Any]],
    switch_time: int,
    visible_times: list[int] | None = None,
) -> dict[str, Any] | None:
    if not confirmed_pens:
        return None
    vt = visible_times if visible_times is not None else [int(p.get("visible_time") or 0) for p in confirmed_pens]
    idx = bisect_right(vt, int(switch_time)) - 1
    if idx < 0:
        return None
    return confirmed_pens[int(idx)]


def build_switch_event(
    *,
    series_id: str,
    switch_time: int,
    reason: str,
    old_anchor: dict[str, Any] | None,
    new_anchor: dict[str, Any],
) -> FactorEventWrite:
    if str(reason) == "zhongshu_entry":
        key_switch = (
            f"zhongshu_entry:{int(switch_time)}:"
            f"{int(new_anchor['start_time'])}:{int(new_anchor['end_time'])}:{int(new_anchor['direction'])}"
        )
    elif str(reason) == "strong_pen":
        key_switch = (
            f"strong_pen:{int(switch_time)}:{str(new_anchor['kind'])}:"
            f"{int(new_anchor['start_time'])}:{int(new_anchor['end_time'])}:{int(new_anchor['direction'])}"
        )
    else:
        key_switch = f"{str(reason)}:{int(switch_time)}"
    return FactorEventWrite(
        series_id=series_id,
        factor_name="anchor",
        candle_time=int(switch_time),
        kind="anchor.switch",
        event_key=key_switch,
        payload=dict(
            build_anchor_switch_payload(
                switch_time=int(switch_time),
                reason=str(reason),
                old_anchor=old_anchor,
                new_anchor=new_anchor,
            )
        ),
    )


def apply_zhongshu_entry_switch(
    *,
    series_id: str,
    formed_entry: Mapping[str, Any],
    switch_time: int,
    old_anchor: dict[str, Any] | None,
    pen_ref_from_pen: Callable[[Mapping[str, Any], str], dict[str, int | str]],
    pen_strength: Callable[[Mapping[str, Any]], float],
) -> tuple[FactorEventWrite | None, dict[str, Any], float]:
    new_ref = pen_ref_from_pen(formed_entry, "confirmed")
    event: FactorEventWrite | None = None
    if should_append_switch(old_anchor=old_anchor, new_anchor=new_ref):
        event = build_switch_event(
            series_id=series_id,
            switch_time=int(switch_time),
            reason="zhongshu_entry",
            old_anchor=old_anchor,
            new_anchor=new_ref,
        )
    return event, new_ref, float(pen_strength(formed_entry))


def apply_strong_pen_switch(
    *,
    series_id: str,
    switch_time: int,
    old_anchor: dict[str, Any] | None,
    new_anchor: dict[str, Any],
    new_anchor_strength: float,
) -> tuple[FactorEventWrite | None, dict[str, Any], float]:
    event: FactorEventWrite | None = None
    if should_append_switch(old_anchor=old_anchor, new_anchor=new_anchor):
        event = build_switch_event(
            series_id=series_id,
            switch_time=int(switch_time),
            reason="strong_pen",
            old_anchor=old_anchor,
            new_anchor=new_anchor,
        )
    return event, new_anchor, float(new_anchor_strength)
