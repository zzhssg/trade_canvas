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
    except Exception:
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


def should_append_switch(*, old_anchor: dict[str, Any] | None, new_anchor: dict[str, Any] | None) -> bool:
    old_ref = normalize_anchor_ref(old_anchor)
    new_ref = normalize_anchor_ref(new_anchor)
    if new_ref is None:
        return False
    if old_ref is None:
        return True
    if old_ref["start_time"] == new_ref["start_time"]:
        return False
    return True


def build_anchor_history_from_switches(anchor_switches: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    anchors: list[dict[str, Any]] = []
    switches: list[dict[str, Any]] = []
    for sw in anchor_switches:
        if not isinstance(sw, dict):
            continue
        new_anchor = normalize_anchor_ref(sw.get("new_anchor"))
        if new_anchor is None:
            continue
        switches.append(sw)
        anchors.append(dict(new_anchor))
    return anchors, switches
