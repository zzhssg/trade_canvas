from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable

from .anchor_semantics import build_anchor_history_from_switches, normalize_anchor_ref
from .factor_processors import build_default_slice_bucket_specs
from .factor_slices import build_pen_head_preview
from .factor_store import FactorStore
from .schemas import FactorMetaV1, FactorSliceV1, GetFactorSlicesResponseV1
from .store import CandleStore
from .timeframe import series_id_timeframe, timeframe_to_seconds


def _build_default_event_bucket_config() -> tuple[dict[tuple[str, str], str], dict[str, tuple[str, str]], tuple[str, ...]]:
    by_kind: dict[tuple[str, str], str] = {}
    sort_keys: dict[str, tuple[str, str]] = {}
    bucket_names: set[str] = set()
    for spec in build_default_slice_bucket_specs():
        bucket_name = str(spec.bucket_name)
        by_kind[(str(spec.factor_name), str(spec.event_kind))] = bucket_name
        bucket_names.add(bucket_name)
        if spec.sort_keys is not None:
            sort_keys[bucket_name] = (str(spec.sort_keys[0]), str(spec.sort_keys[1]))
    return by_kind, sort_keys, tuple(sorted(bucket_names))


_EVENT_BUCKET_BY_KIND, _EVENT_BUCKET_SORT_KEYS, _EVENT_BUCKET_NAMES = _build_default_event_bucket_config()


def _is_visible_payload(payload: dict[str, Any], *, at_time: int) -> bool:
    vt = payload.get("visible_time")
    if vt is None:
        return True
    try:
        return int(vt) <= int(at_time)
    except Exception:
        return True


def _collect_factor_event_buckets(*, rows: Iterable[Any], at_time: int) -> dict[str, list[dict]]:
    buckets: dict[str, list[dict]] = {name: [] for name in _EVENT_BUCKET_NAMES}
    for row in rows:
        bucket = _EVENT_BUCKET_BY_KIND.get((str(row.factor_name), str(row.kind)))
        if bucket is None:
            continue
        payload = dict(row.payload or {})
        if _is_visible_payload(payload, at_time=int(at_time)):
            buckets[bucket].append(payload)

    for bucket, fields in _EVENT_BUCKET_SORT_KEYS.items():
        key_a, key_b = fields
        buckets[bucket].sort(key=lambda d: (int(d.get(key_a, 0)), int(d.get(key_b, 0))))
    return buckets


def _anchor_ref_strength(*, ref: dict[str, int | str] | None, pen_confirmed: list[dict]) -> float:
    if not isinstance(ref, dict):
        return -1.0
    st = int(ref.get("start_time") or 0)
    direction = int(ref.get("direction") or 0)
    if st <= 0 or direction not in {-1, 1}:
        return -1.0
    best = None
    for pen in pen_confirmed:
        if int(pen.get("start_time") or 0) == st and int(pen.get("direction") or 0) == direction:
            if best is None or int(best.get("end_time") or 0) <= int(pen.get("end_time") or 0):
                best = pen
    if best is None:
        return -1.0
    return abs(float(best.get("end_price") or 0.0) - float(best.get("start_price") or 0.0))


def _candidate_anchor_from_pen_head(pen_head_candidate: Any) -> tuple[dict[str, int | str] | None, float]:
    if not isinstance(pen_head_candidate, dict):
        return None, -1.0
    try:
        candidate_ref = normalize_anchor_ref(
            {
                "kind": "candidate",
                "start_time": int(pen_head_candidate.get("start_time") or 0),
                "end_time": int(pen_head_candidate.get("end_time") or 0),
                "direction": int(pen_head_candidate.get("direction") or 0),
            }
        )
        candidate_strength = abs(float(pen_head_candidate.get("end_price") or 0.0) - float(pen_head_candidate.get("start_price") or 0.0))
    except Exception:
        return None, -1.0
    return candidate_ref, float(candidate_strength)


@dataclass(frozen=True)
class FactorSlicesService:
    candle_store: CandleStore
    factor_store: FactorStore

    def get_slices(self, *, series_id: str, at_time: int, window_candles: int = 2000) -> GetFactorSlicesResponseV1:
        aligned = self.candle_store.floor_time(series_id, at_time=int(at_time))
        if aligned is None:
            return GetFactorSlicesResponseV1(series_id=series_id, at_time=int(at_time), candle_id=None)

        tf_s = timeframe_to_seconds(series_id_timeframe(series_id))
        start_time = max(0, int(aligned) - int(window_candles) * int(tf_s))

        factor_rows = self.factor_store.get_events_between_times(
            series_id=series_id,
            factor_name=None,
            start_candle_time=int(start_time),
            end_candle_time=int(aligned),
        )

        buckets = _collect_factor_event_buckets(rows=factor_rows, at_time=int(aligned))
        piv_major = buckets["piv_major"]
        piv_minor = buckets["piv_minor"]
        pen_confirmed = buckets["pen_confirmed"]
        zhongshu_dead = buckets["zhongshu_dead"]
        anchor_switches = buckets["anchor_switches"]

        snapshots: dict[str, FactorSliceV1] = {}
        factors: list[str] = []
        candle_id = f"{series_id}:{int(aligned)}"

        pen_head_row = self.factor_store.get_head_at_or_before(
            series_id=series_id,
            factor_name="pen",
            candle_time=int(aligned),
        )
        zhongshu_head_row = self.factor_store.get_head_at_or_before(
            series_id=series_id,
            factor_name="zhongshu",
            candle_time=int(aligned),
        )
        anchor_head_row = self.factor_store.get_head_at_or_before(
            series_id=series_id,
            factor_name="anchor",
            candle_time=int(aligned),
        )

        if piv_major:
            factors.append("pivot")
            snapshots["pivot"] = FactorSliceV1(
                history={"major": piv_major, "minor": piv_minor},
                head={},
                meta=FactorMetaV1(
                    series_id=series_id,
                    at_time=int(aligned),
                    candle_id=candle_id,
                    factor_name="pivot",
                ),
            )

        if pen_confirmed:
            pen_head: dict = {}
            if pen_head_row is not None:
                pen_head = dict(pen_head_row.head or {})
            else:
                try:
                    candles = self.candle_store.get_closed(series_id, since=int(start_time), limit=int(window_candles) + 5)
                    candles = [c for c in candles if int(c.candle_time) <= int(aligned)]
                except Exception:
                    candles = []
                preview = build_pen_head_preview(candles=candles, major_pivots=piv_major, aligned_time=int(aligned))
                for key in ("extending", "candidate"):
                    v = preview.get(key)
                    if isinstance(v, dict):
                        pen_head[key] = v

            factors.append("pen")
            snapshots["pen"] = FactorSliceV1(
                history={"confirmed": pen_confirmed},
                head=pen_head,
                meta=FactorMetaV1(
                    series_id=series_id,
                    at_time=int(aligned),
                    candle_id=candle_id,
                    factor_name="pen",
                ),
            )

        # Zhongshu head.alive is derived from confirmed pens at t (head-only); dead is append-only history slice.
        zhongshu_head: dict = {}
        if zhongshu_head_row is not None:
            zhongshu_head = dict(zhongshu_head_row.head or {})
        elif pen_confirmed:
            try:
                from .zhongshu import build_alive_zhongshu_from_confirmed_pens

                candles_for_zs = self._candle_store.get_closed_between_times(
                    series_id,
                    start_time=int(start_time),
                    end_time=int(aligned),
                    limit=int(window_candles) + 10,
                )
                alive = build_alive_zhongshu_from_confirmed_pens(
                    pen_confirmed,
                    up_to_visible_time=int(aligned),
                    candles=candles_for_zs,
                )
            except Exception:
                alive = None
            if alive is not None and int(alive.visible_time) == int(aligned):
                zhongshu_head["alive"] = [
                    {
                        "start_time": int(alive.start_time),
                        "end_time": int(alive.end_time),
                        "zg": float(alive.zg),
                        "zd": float(alive.zd),
                        "entry_direction": int(alive.entry_direction),
                        "formed_time": int(alive.formed_time),
                        "formed_reason": str(alive.formed_reason),
                        "death_time": None,
                        "visible_time": int(alive.visible_time),
                    }
                ]

        if zhongshu_dead or zhongshu_head.get("alive"):
            factors.append("zhongshu")
            snapshots["zhongshu"] = FactorSliceV1(
                history={"dead": zhongshu_dead},
                head=zhongshu_head,
                meta=FactorMetaV1(
                    series_id=series_id,
                    at_time=int(aligned),
                    candle_id=candle_id,
                    factor_name="zhongshu",
                ),
            )

        # Anchor snapshot:
        # - history.switches: append-only stable switches from FactorStore
        # - head.current_anchor_ref: the latest anchor ref if available
        if pen_confirmed or anchor_switches:
            history_anchors, history_switches = build_anchor_history_from_switches(anchor_switches)
            pen_head_candidate = None
            if "pen" in snapshots:
                pen_head_candidate = (snapshots["pen"].head or {}).get("candidate")
            if anchor_head_row is not None:
                anchor_head = dict(anchor_head_row.head or {})
                current_anchor_ref = normalize_anchor_ref(anchor_head.get("current_anchor_ref"))
            else:
                current_anchor_ref = None
                if history_switches:
                    cur = history_switches[-1].get("new_anchor")
                    if isinstance(cur, dict):
                        current_anchor_ref = normalize_anchor_ref(cur)
                elif pen_confirmed:
                    last = pen_confirmed[-1]
                    current_anchor_ref = {
                        "kind": "confirmed",
                        "start_time": int(last.get("start_time") or 0),
                        "end_time": int(last.get("end_time") or 0),
                        "direction": int(last.get("direction") or 0),
                    }

            candidate_ref, candidate_strength = _candidate_anchor_from_pen_head(pen_head_candidate)
            current_strength = _anchor_ref_strength(ref=current_anchor_ref, pen_confirmed=pen_confirmed)
            if candidate_ref is not None:
                current_start = int(current_anchor_ref.get("start_time") or 0) if isinstance(current_anchor_ref, dict) else 0
                candidate_start = int(candidate_ref.get("start_time") or 0)
                if current_anchor_ref is None or candidate_start == current_start or candidate_strength > current_strength:
                    current_anchor_ref = dict(candidate_ref)

            factors.append("anchor")
            snapshots["anchor"] = FactorSliceV1(
                history={"anchors": history_anchors, "switches": history_switches},
                head={"current_anchor_ref": current_anchor_ref},
                meta=FactorMetaV1(
                    series_id=series_id,
                    at_time=int(aligned),
                    candle_id=candle_id,
                    factor_name="anchor",
                ),
            )

        return GetFactorSlicesResponseV1(
            series_id=series_id,
            at_time=int(aligned),
            candle_id=candle_id,
            factors=factors,
            snapshots=snapshots,
        )
