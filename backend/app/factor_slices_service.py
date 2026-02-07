from __future__ import annotations

from dataclasses import dataclass

from .anchor_semantics import build_anchor_history_from_switches
from .factor_slices import build_pen_head_preview
from .factor_store import FactorStore
from .schemas import FactorMetaV1, FactorSliceV1, GetFactorSlicesResponseV1
from .store import CandleStore
from .timeframe import series_id_timeframe, timeframe_to_seconds


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

        piv_major: list[dict] = []
        piv_minor: list[dict] = []
        pen_confirmed: list[dict] = []
        zhongshu_dead: list[dict] = []
        anchor_switches: list[dict] = []

        def is_visible(payload: dict, *, at_time: int) -> bool:
            vt = payload.get("visible_time")
            if vt is None:
                return True
            try:
                return int(vt) <= int(at_time)
            except Exception:
                return True

        for r in factor_rows:
            if r.factor_name == "pivot" and r.kind == "pivot.major":
                payload = dict(r.payload or {})
                if is_visible(payload, at_time=int(aligned)):
                    piv_major.append(payload)
            elif r.factor_name == "pivot" and r.kind == "pivot.minor":
                payload = dict(r.payload or {})
                if is_visible(payload, at_time=int(aligned)):
                    piv_minor.append(payload)
            elif r.factor_name == "pen" and r.kind == "pen.confirmed":
                payload = dict(r.payload or {})
                if is_visible(payload, at_time=int(aligned)):
                    pen_confirmed.append(payload)
            elif r.factor_name == "zhongshu" and r.kind == "zhongshu.dead":
                payload = dict(r.payload or {})
                if is_visible(payload, at_time=int(aligned)):
                    zhongshu_dead.append(payload)
            elif r.factor_name == "anchor" and r.kind == "anchor.switch":
                payload = dict(r.payload or {})
                if is_visible(payload, at_time=int(aligned)):
                    anchor_switches.append(payload)

        piv_major.sort(key=lambda d: (int(d.get("visible_time", 0)), int(d.get("pivot_time", 0))))
        pen_confirmed.sort(key=lambda d: (int(d.get("visible_time", 0)), int(d.get("start_time", 0))))
        anchor_switches.sort(key=lambda d: (int(d.get("visible_time", 0)), int(d.get("switch_time", 0))))

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

                alive = build_alive_zhongshu_from_confirmed_pens(pen_confirmed, up_to_visible_time=int(aligned))
            except Exception:
                alive = None
            if alive is not None and int(alive.visible_time) == int(aligned):
                zhongshu_head["alive"] = [
                    {
                        "start_time": int(alive.start_time),
                        "end_time": int(alive.end_time),
                        "zg": float(alive.zg),
                        "zd": float(alive.zd),
                        "formed_time": int(alive.formed_time),
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
        # - head.current_anchor_ref: the latest stable anchor (confirmed) if available
        # - head.reverse_anchor_ref: optional (candidate pen derived from pen head)
        if pen_confirmed or anchor_switches:
            history_anchors, history_switches = build_anchor_history_from_switches(anchor_switches)
            if anchor_head_row is not None:
                anchor_head = dict(anchor_head_row.head or {})
                current_anchor_ref = anchor_head.get("current_anchor_ref")
                reverse_anchor_ref = anchor_head.get("reverse_anchor_ref")
            else:
                current_anchor_ref = None
                if history_switches:
                    cur = history_switches[-1].get("new_anchor")
                    if isinstance(cur, dict):
                        current_anchor_ref = cur
                elif pen_confirmed:
                    last = pen_confirmed[-1]
                    current_anchor_ref = {
                        "kind": "confirmed",
                        "start_time": int(last.get("start_time") or 0),
                        "end_time": int(last.get("end_time") or 0),
                        "direction": int(last.get("direction") or 0),
                    }

                reverse_anchor_ref = None
                try:
                    pen_head_candidate = (snapshots.get("pen").head or {}).get("candidate") if "pen" in snapshots else None
                except Exception:
                    pen_head_candidate = None
                if isinstance(pen_head_candidate, dict):
                    try:
                        reverse_anchor_ref = {
                            "kind": "candidate",
                            "start_time": int(pen_head_candidate.get("start_time") or 0),
                            "end_time": int(pen_head_candidate.get("end_time") or 0),
                            "direction": int(pen_head_candidate.get("direction") or 0),
                        }
                    except Exception:
                        reverse_anchor_ref = None

            factors.append("anchor")
            snapshots["anchor"] = FactorSliceV1(
                history={"anchors": history_anchors, "switches": history_switches},
                head={"current_anchor_ref": current_anchor_ref, "reverse_anchor_ref": reverse_anchor_ref},
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
