from __future__ import annotations

from typing import Any


def normalize_anchor_ref(value: Any) -> dict[str, int | str] | None:
    if not isinstance(value, dict):
        return None
    kind = str(value.get("kind") or "")
    if kind not in {"confirmed", "candidate"}:
        return None
    try:
        start_time = int(value.get("start_time") or 0)
        end_time = int(value.get("end_time") or 0)
        direction = int(value.get("direction") or 0)
    except (ValueError, TypeError):
        return None
    if start_time <= 0 or end_time <= 0:
        return None
    if direction not in {-1, 1}:
        return None
    return {
        "kind": kind,
        "start_time": start_time,
        "end_time": end_time,
        "direction": direction,
    }


def anchor_pointer_id(value: dict[str, Any] | None) -> int | None:
    ref = normalize_anchor_ref(value)
    if ref is None:
        return None
    return int(ref["start_time"])


def should_append_switch(*, old_anchor: dict[str, Any] | None, new_anchor: dict[str, Any] | None) -> bool:
    new_id = anchor_pointer_id(new_anchor)
    if new_id is None:
        return False
    old_id = anchor_pointer_id(old_anchor)
    if old_id is None:
        return True
    if old_id == new_id:
        return False
    return True


def build_anchor_history_from_switches(anchor_switches: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    anchors: list[dict[str, Any]] = []
    switches: list[dict[str, Any]] = []
    # Defensive read-side healing for historical data:
    # if one switch_time has multiple anchor.switch rows, keep the latest row at that time.
    latest_by_switch_time: dict[int, tuple[dict[str, Any], dict[str, int | str]]] = {}
    stable_order: list[int] = []
    seen_switch_times: set[int] = set()
    for sw in anchor_switches:
        if not isinstance(sw, dict):
            continue
        new_anchor = normalize_anchor_ref(sw.get("new_anchor"))
        if new_anchor is None:
            continue
        switch_time = int(sw.get("switch_time") or 0)
        if switch_time <= 0:
            switch_time = int(sw.get("visible_time") or 0)
        if switch_time <= 0:
            continue
        latest_by_switch_time[switch_time] = (sw, new_anchor)
        if switch_time not in seen_switch_times:
            seen_switch_times.add(switch_time)
            stable_order.append(switch_time)

    seen_pointer_ids: set[int] = set()
    for switch_time in stable_order:
        pair = latest_by_switch_time.get(int(switch_time))
        if pair is None:
            continue
        sw, new_anchor = pair
        pointer_id = int(new_anchor["start_time"])
        if pointer_id in seen_pointer_ids:
            continue
        seen_pointer_ids.add(pointer_id)
        switches.append(sw)
        anchors.append(dict(new_anchor))
    return anchors, switches
