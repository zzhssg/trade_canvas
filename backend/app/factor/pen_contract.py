from __future__ import annotations

from typing import Any, Mapping, TypedDict

from .pen import ConfirmedPen


class PenPayloadBase(TypedDict):
    start_time: int
    end_time: int
    start_price: float
    end_price: float
    direction: int


class ConfirmedPenPayloadV1(PenPayloadBase):
    visible_time: int
    start_idx: int | None
    end_idx: int | None


class AnchorPenRefV1(TypedDict):
    kind: str
    start_time: int
    end_time: int
    direction: int


class AnchorSwitchPayloadV1(TypedDict):
    switch_time: int
    reason: str
    old_anchor: AnchorPenRefV1 | None
    new_anchor: AnchorPenRefV1
    visible_time: int


def _to_int(value: Any, *, default: int = 0) -> int:
    try:
        return int(value)
    except (ValueError, TypeError):
        return int(default)


def _to_float(value: Any, *, default: float = 0.0) -> float:
    try:
        return float(value)
    except (ValueError, TypeError):
        return float(default)


def _to_optional_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (ValueError, TypeError):
        return None


def normalize_confirmed_pen_payload(payload: Mapping[str, Any]) -> ConfirmedPenPayloadV1:
    return ConfirmedPenPayloadV1(
        start_time=_to_int(payload.get("start_time")),
        end_time=_to_int(payload.get("end_time")),
        start_price=_to_float(payload.get("start_price")),
        end_price=_to_float(payload.get("end_price")),
        direction=_to_int(payload.get("direction")),
        visible_time=_to_int(payload.get("visible_time")),
        start_idx=_to_optional_int(payload.get("start_idx")),
        end_idx=_to_optional_int(payload.get("end_idx")),
    )


def build_confirmed_pen_payload(pen: ConfirmedPen) -> ConfirmedPenPayloadV1:
    return ConfirmedPenPayloadV1(
        start_time=int(pen.start_time),
        end_time=int(pen.end_time),
        start_price=float(pen.start_price),
        end_price=float(pen.end_price),
        direction=int(pen.direction),
        visible_time=int(pen.visible_time),
        start_idx=pen.start_idx,
        end_idx=pen.end_idx,
    )


def build_anchor_pen_ref(payload: Mapping[str, Any], *, kind: str) -> AnchorPenRefV1:
    return AnchorPenRefV1(
        kind=str(kind),
        start_time=_to_int(payload.get("start_time")),
        end_time=_to_int(payload.get("end_time")),
        direction=_to_int(payload.get("direction")),
    )


def anchor_pen_ref_key(value: Mapping[str, Any]) -> tuple[int, int, int] | None:
    start_time = _to_int(value.get("start_time"))
    end_time = _to_int(value.get("end_time"))
    direction = _to_int(value.get("direction"))
    if start_time <= 0 or end_time <= 0 or direction not in {-1, 1}:
        return None
    return (int(start_time), int(end_time), int(direction))


def pen_strength(payload: Mapping[str, Any]) -> float:
    start_price = _to_float(payload.get("start_price"))
    end_price = _to_float(payload.get("end_price"))
    return abs(float(end_price) - float(start_price))


def normalize_anchor_switch_payload(payload: Mapping[str, Any]) -> AnchorSwitchPayloadV1 | None:
    new_anchor_raw = payload.get("new_anchor")
    if not isinstance(new_anchor_raw, dict):
        return None
    new_kind = str(new_anchor_raw.get("kind") or "")
    new_anchor = build_anchor_pen_ref(new_anchor_raw, kind=new_kind)
    if anchor_pen_ref_key(new_anchor) is None:
        return None

    old_anchor_raw = payload.get("old_anchor")
    old_anchor: AnchorPenRefV1 | None = None
    if isinstance(old_anchor_raw, dict):
        old_kind = str(old_anchor_raw.get("kind") or "")
        maybe_old = build_anchor_pen_ref(old_anchor_raw, kind=old_kind)
        if anchor_pen_ref_key(maybe_old) is not None:
            old_anchor = maybe_old

    switch_time = _to_int(payload.get("switch_time"))
    visible_time = _to_int(payload.get("visible_time"))
    if switch_time <= 0:
        switch_time = int(visible_time)
    if visible_time <= 0:
        visible_time = int(switch_time)

    return AnchorSwitchPayloadV1(
        switch_time=int(switch_time),
        reason=str(payload.get("reason") or ""),
        old_anchor=old_anchor,
        new_anchor=new_anchor,
        visible_time=int(visible_time),
    )


def build_anchor_switch_payload(
    *,
    switch_time: int,
    reason: str,
    old_anchor: Mapping[str, Any] | None,
    new_anchor: Mapping[str, Any],
) -> AnchorSwitchPayloadV1:
    normalized_new = build_anchor_pen_ref(new_anchor, kind=str(new_anchor.get("kind") or ""))
    old_ref: AnchorPenRefV1 | None = None
    if isinstance(old_anchor, dict):
        old_ref = build_anchor_pen_ref(old_anchor, kind=str(old_anchor.get("kind") or ""))
        if anchor_pen_ref_key(old_ref) is None:
            old_ref = None
    payload = AnchorSwitchPayloadV1(
        switch_time=int(switch_time),
        reason=str(reason),
        old_anchor=old_ref,
        new_anchor=normalized_new,
        visible_time=int(switch_time),
    )
    return payload
