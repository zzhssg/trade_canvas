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


def _to_int(value: Any, *, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return int(default)


def _to_float(value: Any, *, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return float(default)


def _to_optional_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except Exception:
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
