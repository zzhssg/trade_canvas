from __future__ import annotations

import asyncio
import json
import logging
import os
import time
import zipfile
from contextlib import asynccontextmanager
from pathlib import Path
from typing import TextIO

from fastapi import FastAPI, HTTPException, Query, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from starlette.responses import StreamingResponse

from .blocking import run_blocking
from .config import load_settings
from .debug_hub import DebugHub
from .freqtrade_config import build_backtest_config, load_json, write_temp_config
from .freqtrade_data import check_history_available, list_available_timeframes
from .freqtrade_runner import list_strategies, parse_strategy_list, run_backtest, validate_strategy_name
from .ingest_supervisor import IngestSupervisor
from .schemas import (
    BacktestRunRequest,
    BacktestRunResponse,
    BacktestPairTimeframesResponse,
    DevCreateWorktreeRequest,
    DevCreateWorktreeResponse,
    DevDeleteWorktreeRequest,
    DevDeleteWorktreeResponse,
    DevPortAllocationResponse,
    DevServiceState,
    DevServiceStatus,
    DevStartServicesRequest,
    DevStartServicesResponse,
    DevStopServicesResponse,
    DevUpdateMetadataRequest,
    DevUpdateMetadataResponse,
    DevWorktreeInfo,
    DevWorktreeListResponse,
    DevWorktreeMetadata,
    DrawDeltaV1,
    GetCandlesResponse,
    GetFactorSlicesResponseV1,
    IngestCandleClosedRequest,
    IngestCandleClosedResponse,
    IngestCandleFormingRequest,
    IngestCandleFormingResponse,
    LimitQuery,
    SinceQuery,
    ReplayPrepareRequestV1,
    ReplayPrepareResponseV1,
    StrategyListResponse,
    TopMarketsLimitQuery,
    TopMarketsResponse,
    WorldCursorV1,
    WorldDeltaPollResponseV1,
    WorldDeltaRecordV1,
    WorldStateV1,
    WorldTimeV1,
)
from .market_list import BinanceMarketListService, MinIntervalLimiter
from .factor_orchestrator import FactorOrchestrator
from .factor_store import FactorStore
from .overlay_orchestrator import OverlayOrchestrator
from .overlay_store import OverlayStore
from .store import CandleStore
from .timeframe import series_id_timeframe, timeframe_to_seconds
from .whitelist import load_market_whitelist
from .ws_hub import CandleHub
from .worktree_manager import WorktreeManager

logger = logging.getLogger(__name__)

_faulthandler_file: TextIO | None = None


async def list_strategies_async(**kwargs):
    # Keep the event loop responsive: freqtrade runner uses blocking subprocess calls.
    return await run_blocking(list_strategies, **kwargs)


async def run_backtest_async(**kwargs):
    # Keep the event loop responsive: freqtrade runner uses blocking subprocess calls.
    return await run_blocking(run_backtest, **kwargs)


def _require_backtest_trades() -> bool:
    return (os.environ.get("TRADE_CANVAS_BACKTEST_REQUIRE_TRADES") or "").strip() == "1"


def _extract_total_trades_from_backtest_zip(*, zip_path: Path, strategy_name: str) -> int:
    with zipfile.ZipFile(str(zip_path), "r") as zf:
        candidates = [
            n
            for n in zf.namelist()
            if n.startswith("backtest-result-") and n.endswith(".json") and not n.endswith("_config.json")
        ]
        if not candidates:
            candidates = [n for n in zf.namelist() if n.endswith(".json") and not n.endswith("_config.json")]
        if not candidates:
            raise ValueError("missing backtest stats json in zip")

        raw = zf.read(candidates[0]).decode("utf-8", errors="replace")
        payload = json.loads(raw)

    strat = (payload.get("strategy") or {}).get(strategy_name)
    if not isinstance(strat, dict):
        raise ValueError("missing strategy stats in backtest json")
    total = strat.get("total_trades")
    if isinstance(total, int):
        return total
    trades = strat.get("trades")
    if isinstance(trades, list):
        return len(trades)
    raise ValueError("missing total_trades/trades in strategy stats")


def _maybe_enable_faulthandler() -> None:
    """
    Optional: allow dumping stack traces even when Ctrl+C appears stuck.

    Usage (when enabled): `kill -USR1 <pid>` to print all thread tracebacks to stderr.
    """
    if os.environ.get("TRADE_CANVAS_ENABLE_FAULTHANDLER") != "1":
        return
    try:
        import faulthandler
        import signal
        import sys

        file: TextIO = sys.stderr
        path_raw = (os.environ.get("TRADE_CANVAS_FAULTHANDLER_PATH") or "").strip()
        if path_raw:
            p = Path(path_raw).expanduser()
            if not p.is_absolute():
                p = (Path.cwd() / p).resolve()
            p.parent.mkdir(parents=True, exist_ok=True)
            global _faulthandler_file
            _faulthandler_file = p.open("a", encoding="utf-8", buffering=1)
            file = _faulthandler_file

        faulthandler.enable(file=file)
        if hasattr(signal, "SIGUSR1"):
            faulthandler.register(signal.SIGUSR1, file=file, all_threads=True)
    except Exception:
        pass


def create_app() -> FastAPI:
    _maybe_enable_faulthandler()
    settings = load_settings()
    project_root = Path(__file__).resolve().parents[2]
    store = CandleStore(db_path=settings.db_path)
    factor_store = FactorStore(db_path=settings.db_path)
    factor_orchestrator = FactorOrchestrator(candle_store=store, factor_store=factor_store)
    overlay_store = OverlayStore(db_path=settings.db_path)
    overlay_orchestrator = OverlayOrchestrator(candle_store=store, factor_store=factor_store, overlay_store=overlay_store)
    debug_hub = DebugHub()
    factor_orchestrator.set_debug_hub(debug_hub)
    overlay_orchestrator.set_debug_hub(debug_hub)
    hub = CandleHub()
    whitelist = load_market_whitelist(settings.whitelist_path)
    market_list = BinanceMarketListService()
    force_limiter = MinIntervalLimiter(min_interval_s=2.0)

    idle_ttl_s = 60
    idle_ttl_raw = os.environ.get("TRADE_CANVAS_ONDEMAND_IDLE_TTL_S", "").strip()
    if idle_ttl_raw:
        try:
            idle_ttl_s = max(1, int(idle_ttl_raw))
        except ValueError:
            idle_ttl_s = 60

    supervisor = IngestSupervisor(
        store=store,
        hub=hub,
        factor_orchestrator=factor_orchestrator,
        overlay_orchestrator=overlay_orchestrator,
        whitelist_series_ids=whitelist.series_ids,
        ondemand_idle_ttl_s=idle_ttl_s,
    )

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        if os.environ.get("TRADE_CANVAS_ENABLE_WHITELIST_INGEST") == "1":
            await supervisor.start_whitelist()

        if os.environ.get("TRADE_CANVAS_ENABLE_ONDEMAND_INGEST") == "1":
            await supervisor.start_reaper()

        try:
            yield
        finally:
            # Close websockets first so uvicorn doesn't wait on them.
            try:
                await hub.close_all()
            except Exception:
                pass
            await supervisor.close()

    app = FastAPI(title="trade_canvas API", version="0.1.0", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.state.store = store
    app.state.hub = hub
    app.state.factor_store = factor_store
    app.state.factor_orchestrator = factor_orchestrator
    app.state.overlay_store = overlay_store
    app.state.overlay_orchestrator = overlay_orchestrator
    app.state.whitelist = whitelist
    app.state.market_list = market_list
    app.state.force_limiter = force_limiter
    app.state.ingest_supervisor = supervisor
    app.state.debug_hub = debug_hub

    # Initialize worktree manager
    worktree_manager = WorktreeManager(repo_root=project_root)
    app.state.worktree_manager = worktree_manager

    @app.get("/api/market/candles", response_model=GetCandlesResponse)
    def get_market_candles(
        series_id: str = Query(..., min_length=1),
        since: SinceQuery = None,
        limit: LimitQuery = 500,
    ) -> GetCandlesResponse:
        candles = store.get_closed(series_id, since=since, limit=limit)
        head_time = store.head_time(series_id)
        if os.environ.get("TRADE_CANVAS_ENABLE_DEBUG_API") == "1" and candles:
            last_time = int(candles[-1].candle_time)
            app.state.debug_hub.emit(
                pipe="read",
                event="read.http.market_candles",
                series_id=series_id,
                message="get market candles",
                data={
                    "since": None if since is None else int(since),
                    "limit": int(limit),
                    "count": int(len(candles)),
                    "last_time": int(last_time),
                    "server_head_time": None if head_time is None else int(head_time),
                },
            )
        return GetCandlesResponse(series_id=series_id, server_head_time=head_time, candles=candles)

    @app.post("/api/market/ingest/candle_closed", response_model=IngestCandleClosedResponse)
    async def ingest_candle_closed(req: IngestCandleClosedRequest) -> IngestCandleClosedResponse:
        # IMPORTANT: keep the asyncio event loop responsive.
        # SQLite writes and factor/overlay computation are sync and may take seconds for large bursts.
        t0 = time.perf_counter()
        if os.environ.get("TRADE_CANVAS_ENABLE_DEBUG_API") == "1":
            app.state.debug_hub.emit(
                pipe="write",
                event="write.http.ingest_candle_closed_start",
                series_id=req.series_id,
                message="ingest candle_closed start",
                data={"candle_time": int(req.candle.candle_time)},
            )

        steps: list[dict] = []

        def _persist_and_sidecars() -> None:
            t_step = time.perf_counter()
            store.upsert_closed(req.series_id, req.candle)
            steps.append(
                {
                    "name": "store.upsert_closed",
                    "ok": True,
                    "duration_ms": int((time.perf_counter() - t_step) * 1000),
                }
            )

            try:
                t_step = time.perf_counter()
                app.state.factor_orchestrator.ingest_closed(
                    series_id=req.series_id, up_to_candle_time=req.candle.candle_time
                )
                steps.append(
                    {
                        "name": "factor.ingest_closed",
                        "ok": True,
                        "duration_ms": int((time.perf_counter() - t_step) * 1000),
                    }
                )
            except Exception:
                steps.append(
                    {
                        "name": "factor.ingest_closed",
                        "ok": False,
                        "duration_ms": int((time.perf_counter() - t_step) * 1000),
                    }
                )

            try:
                t_step = time.perf_counter()
                app.state.overlay_orchestrator.ingest_closed(
                    series_id=req.series_id, up_to_candle_time=req.candle.candle_time
                )
                steps.append(
                    {
                        "name": "overlay.ingest_closed",
                        "ok": True,
                        "duration_ms": int((time.perf_counter() - t_step) * 1000),
                    }
                )
            except Exception:
                steps.append(
                    {
                        "name": "overlay.ingest_closed",
                        "ok": False,
                        "duration_ms": int((time.perf_counter() - t_step) * 1000),
                    }
                )

        await run_blocking(_persist_and_sidecars)
        await hub.publish_closed(series_id=req.series_id, candle=req.candle)

        if os.environ.get("TRADE_CANVAS_ENABLE_DEBUG_API") == "1":
            app.state.debug_hub.emit(
                pipe="write",
                event="write.http.ingest_candle_closed_done",
                series_id=req.series_id,
                message="ingest candle_closed done",
                data={
                    "candle_time": int(req.candle.candle_time),
                    "steps": list(steps),
                    "duration_ms": int((time.perf_counter() - t0) * 1000),
                },
            )

        return IngestCandleClosedResponse(ok=True, series_id=req.series_id, candle_time=req.candle.candle_time)

    @app.post("/api/market/ingest/candle_forming", response_model=IngestCandleFormingResponse)
    async def ingest_candle_forming(req: IngestCandleFormingRequest) -> IngestCandleFormingResponse:
        if os.environ.get("TRADE_CANVAS_ENABLE_DEBUG_API") != "1":
            raise HTTPException(status_code=404, detail="not_found")
        await hub.publish_forming(series_id=req.series_id, candle=req.candle)
        return IngestCandleFormingResponse(ok=True, series_id=req.series_id, candle_time=req.candle.candle_time)

    @app.get("/api/draw/delta", response_model=DrawDeltaV1)
    def get_draw_delta(
        series_id: str = Query(..., min_length=1),
        cursor_version_id: int = Query(0, ge=0),
        window_candles: LimitQuery = 2000,
        at_time: int | None = Query(default=None, ge=0, description="Optional replay upper-bound (Unix seconds)"),
    ) -> DrawDeltaV1:
        """
        Unified draw delta (v1 base):
        - instruction_catalog_patch + active_ids (overlay instructions)
        - series_points (indicator line points; v0 returns empty for now)
        """
        from .schemas import DrawCursorV1, DrawDeltaV1, OverlayInstructionPatchItemV1

        store_head = store.head_time(series_id)
        overlay_head = app.state.overlay_store.head_time(series_id)

        if at_time is not None:
            aligned = store.floor_time(series_id, at_time=int(at_time))
            if aligned is None:
                return DrawDeltaV1(
                    series_id=series_id,
                    to_candle_id=None,
                    to_candle_time=None,
                    active_ids=[],
                    instruction_catalog_patch=[],
                    series_points={},
                    next_cursor=DrawCursorV1(version_id=int(cursor_version_id), point_time=None),
                )
            # Replay/point-query semantics must be fail-safe: draw output cannot claim it is aligned to t
            # unless the overlay store has actually been built up to that aligned time.
            if overlay_head is None or int(overlay_head) < int(aligned):
                raise HTTPException(status_code=409, detail="ledger_out_of_sync:overlay")
            to_time = int(aligned)
        else:
            to_time = overlay_head if overlay_head is not None else store_head
        to_candle_id = f"{series_id}:{to_time}" if to_time is not None else None

        if to_time is None:
            return DrawDeltaV1(
                series_id=series_id,
                to_candle_id=None,
                to_candle_time=None,
                active_ids=[],
                instruction_catalog_patch=[],
                series_points={},
                next_cursor=DrawCursorV1(version_id=int(cursor_version_id), point_time=None),
            )

        tf_s = timeframe_to_seconds(series_id_timeframe(series_id))
        cutoff_time = max(0, int(to_time) - int(window_candles) * int(tf_s))

        latest_defs = app.state.overlay_store.get_latest_defs_up_to_time(series_id=series_id, up_to_time=int(to_time))
        active_ids: list[str] = []
        for d in latest_defs:
            if d.kind == "marker":
                t = d.payload.get("time")
                try:
                    pivot_time = int(t)
                except Exception:
                    continue
                if pivot_time < cutoff_time or pivot_time > int(to_time):
                    continue
                active_ids.append(str(d.instruction_id))
            elif d.kind == "polyline":
                pts = d.payload.get("points")
                if not isinstance(pts, list) or not pts:
                    continue
                ok = False
                for p in pts:
                    if not isinstance(p, dict):
                        continue
                    tt = p.get("time")
                    try:
                        pt = int(tt)
                    except Exception:
                        continue
                    if cutoff_time <= pt <= int(to_time):
                        ok = True
                        break
                if ok:
                    active_ids.append(str(d.instruction_id))

        patch_rows = app.state.overlay_store.get_patch_after_version(
            series_id=series_id,
            after_version_id=int(cursor_version_id),
            up_to_time=int(to_time),
        )
        patch = [
            OverlayInstructionPatchItemV1(
                version_id=r.version_id,
                instruction_id=r.instruction_id,
                kind=r.kind,
                visible_time=r.visible_time,
                definition=r.payload,
            )
            for r in patch_rows
        ]
        next_cursor = DrawCursorV1(version_id=int(app.state.overlay_store.last_version_id(series_id)), point_time=None)

        active_ids.sort()
        if os.environ.get("TRADE_CANVAS_ENABLE_DEBUG_API") == "1" and (patch or int(next_cursor.version_id) > int(cursor_version_id)):
            app.state.debug_hub.emit(
                pipe="read",
                event="read.http.draw_delta",
                series_id=series_id,
                message="get draw delta",
                data={
                    "cursor_version_id": int(cursor_version_id),
                    "next_version_id": int(next_cursor.version_id),
                    "to_time": None if to_time is None else int(to_time),
                    "patch_len": int(len(patch)),
                    "active_len": int(len(active_ids)),
                    "at_time": None if at_time is None else int(at_time),
                },
            )
        return DrawDeltaV1(
            series_id=series_id,
            to_candle_id=to_candle_id,
            to_candle_time=int(to_time),
            active_ids=active_ids,
            instruction_catalog_patch=patch,
            series_points={},
            next_cursor=next_cursor,
        )

    @app.get("/api/factor/slices", response_model=GetFactorSlicesResponseV1)
    def get_factor_slices(
        series_id: str = Query(..., min_length=1),
        at_time: int = Query(..., ge=0),
        window_candles: LimitQuery = 2000,
    ) -> GetFactorSlicesResponseV1:
        """
        v0 debug endpoint to inspect which factor snapshots are available at time t.

        Note: v0 supports:
        - pivot: history.major from factor events, head.minor computed on the fly
        - pen: history.confirmed from factor events
        """
        from .schemas import FactorMetaV1, FactorSliceV1

        aligned = store.floor_time(series_id, at_time=int(at_time))
        if aligned is None:
            return GetFactorSlicesResponseV1(series_id=series_id, at_time=int(at_time), candle_id=None)

        tf_s = timeframe_to_seconds(series_id_timeframe(series_id))
        start_time = max(0, int(aligned) - int(window_candles) * int(tf_s))

        factor_rows = app.state.factor_store.get_events_between_times(
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
            # Candidate pen (head-only): from last confirmed pen end_time to the most extreme point
            # in the reverse direction within the current tail window.
            pen_head: dict = {}
            try:
                candles = store.get_closed(series_id, since=int(start_time), limit=int(window_candles) + 5)
                candles = [c for c in candles if int(c.candle_time) <= int(aligned)]
            except Exception:
                candles = []

            last = pen_confirmed[-1]
            try:
                last_end_time = int(last.get("end_time") or 0)
                last_end_price = float(last.get("end_price") or 0.0)
                last_dir = int(last.get("direction") or 0)
            except Exception:
                last_end_time = 0
                last_end_price = 0.0
                last_dir = 0

            if candles and last_end_time > 0 and last_dir in (-1, 1):
                tail = [c for c in candles if int(c.candle_time) > int(last_end_time) and int(c.candle_time) <= int(aligned)]
                if tail:
                    if last_dir == 1:
                        # Last confirmed pen was up; candidate is down to min(low).
                        best = min(tail, key=lambda c: float(c.low))
                        pen_head["candidate"] = {
                            "start_time": int(last_end_time),
                            "end_time": int(best.candle_time),
                            "start_price": float(last_end_price),
                            "end_price": float(best.low),
                            "direction": -1,
                        }
                    else:
                        # Last confirmed pen was down; candidate is up to max(high).
                        best = max(tail, key=lambda c: float(c.high))
                        pen_head["candidate"] = {
                            "start_time": int(last_end_time),
                            "end_time": int(best.candle_time),
                            "start_price": float(last_end_price),
                            "end_price": float(best.high),
                            "direction": 1,
                        }

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
        if pen_confirmed:
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
            current_anchor_ref = None
            if anchor_switches:
                cur = anchor_switches[-1].get("new_anchor")
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
                history={"switches": anchor_switches},
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

    @app.post("/api/replay/prepare", response_model=ReplayPrepareResponseV1)
    def prepare_replay(req: ReplayPrepareRequestV1) -> ReplayPrepareResponseV1:
        """
        Replay prepare:
        - Ensures factor/overlay ledgers are computed up to aligned time.
        - Returns aligned_time for replay loading.
        """
        series_id = req.series_id
        store_head = store.head_time(series_id)
        if store_head is None:
            raise HTTPException(status_code=404, detail="no_data")
        requested_time = int(req.to_time) if req.to_time is not None else int(store_head)
        aligned = store.floor_time(series_id, at_time=int(requested_time))
        if aligned is None:
            raise HTTPException(status_code=404, detail="no_data")

        window_candles = int(req.window_candles or 2000)
        window_candles = min(5000, max(100, window_candles))

        computed = False
        factor_head = app.state.factor_store.head_time(series_id)
        overlay_head = app.state.overlay_store.head_time(series_id)

        if factor_head is None or int(factor_head) < int(aligned):
            app.state.factor_orchestrator.ingest_closed(series_id=series_id, up_to_candle_time=int(aligned))
            factor_head = app.state.factor_store.head_time(series_id)
            computed = True

        if overlay_head is None or int(overlay_head) < int(aligned):
            app.state.overlay_orchestrator.ingest_closed(series_id=series_id, up_to_candle_time=int(aligned))
            overlay_head = app.state.overlay_store.head_time(series_id)
            computed = True

        if factor_head is None or int(factor_head) < int(aligned):
            raise HTTPException(status_code=409, detail="ledger_out_of_sync:factor")
        if overlay_head is None or int(overlay_head) < int(aligned):
            raise HTTPException(status_code=409, detail="ledger_out_of_sync:overlay")

        if os.environ.get("TRADE_CANVAS_ENABLE_DEBUG_API") == "1":
            app.state.debug_hub.emit(
                pipe="read",
                event="read.http.replay_prepare",
                series_id=series_id,
                message="prepare replay",
                data={
                    "requested_time": int(requested_time),
                    "aligned_time": int(aligned),
                    "window_candles": int(window_candles),
                    "factor_head_time": int(factor_head),
                    "overlay_head_time": int(overlay_head),
                    "computed": bool(computed),
                },
            )

        return ReplayPrepareResponseV1(
            ok=True,
            series_id=series_id,
            requested_time=int(requested_time),
            aligned_time=int(aligned),
            window_candles=int(window_candles),
            factor_head_time=int(factor_head) if factor_head is not None else None,
            overlay_head_time=int(overlay_head) if overlay_head is not None else None,
            computed=bool(computed),
        )

    @app.get("/api/frame/live", response_model=WorldStateV1)
    def get_world_frame_live(
        series_id: str = Query(..., min_length=1),
        window_candles: LimitQuery = 2000,
    ) -> WorldStateV1:
        """
        Unified world frame (live): latest aligned world state.
        v1 implementation is a projection of existing factor_slices + draw/delta.
        """
        store_head = store.head_time(series_id)
        if store_head is None:
            raise HTTPException(status_code=404, detail="no_data")
        aligned = store.floor_time(series_id, at_time=int(store_head))
        if aligned is None:
            raise HTTPException(status_code=404, detail="no_data")

        factor_slices = get_factor_slices(series_id=series_id, at_time=int(aligned), window_candles=window_candles)
        draw_state = get_draw_delta(series_id=series_id, cursor_version_id=0, window_candles=window_candles, at_time=int(aligned))
        candle_id = f"{series_id}:{int(aligned)}"
        if factor_slices.candle_id != candle_id or draw_state.to_candle_id != candle_id:
            raise HTTPException(status_code=409, detail="ledger_out_of_sync")
        if os.environ.get("TRADE_CANVAS_ENABLE_DEBUG_API") == "1":
            app.state.debug_hub.emit(
                pipe="read",
                event="read.http.world_frame_live",
                series_id=series_id,
                message="get world frame live",
                data={"at_time": int(store_head), "aligned_time": int(aligned), "candle_id": str(candle_id)},
            )
        return WorldStateV1(
            series_id=series_id,
            time=WorldTimeV1(at_time=int(store_head), aligned_time=int(aligned), candle_id=candle_id),
            factor_slices=factor_slices,
            draw_state=draw_state,
        )

    @app.get("/api/frame/at_time", response_model=WorldStateV1)
    def get_world_frame_at_time(
        series_id: str = Query(..., min_length=1),
        at_time: int = Query(..., ge=0),
        window_candles: LimitQuery = 2000,
    ) -> WorldStateV1:
        """
        Unified world frame (replay point query): aligned world state at time t.
        """
        aligned = store.floor_time(series_id, at_time=int(at_time))
        if aligned is None:
            raise HTTPException(status_code=404, detail="no_data")

        factor_slices = get_factor_slices(series_id=series_id, at_time=int(aligned), window_candles=window_candles)
        draw_state = get_draw_delta(series_id=series_id, cursor_version_id=0, window_candles=window_candles, at_time=int(aligned))
        candle_id = f"{series_id}:{int(aligned)}"
        if factor_slices.candle_id != candle_id or draw_state.to_candle_id != candle_id:
            raise HTTPException(status_code=409, detail="ledger_out_of_sync")
        if os.environ.get("TRADE_CANVAS_ENABLE_DEBUG_API") == "1":
            app.state.debug_hub.emit(
                pipe="read",
                event="read.http.world_frame_live",
                series_id=series_id,
                message="get world frame live",
                data={"at_time": int(store_head), "aligned_time": int(aligned), "candle_id": str(candle_id)},
            )
        return WorldStateV1(
            series_id=series_id,
            time=WorldTimeV1(at_time=int(at_time), aligned_time=int(aligned), candle_id=candle_id),
            factor_slices=factor_slices,
            draw_state=draw_state,
        )

    @app.get("/api/delta/poll", response_model=WorldDeltaPollResponseV1)
    def poll_world_delta(
        series_id: str = Query(..., min_length=1),
        after_id: int = Query(0, ge=0),
        limit: LimitQuery = 2000,
        window_candles: LimitQuery = 2000,
    ) -> WorldDeltaPollResponseV1:
        """
        v1 world delta (live):
        - Uses draw/delta cursor as the minimal incremental source (compat projection).
        - Emits at most 1 record per poll (if cursor advances); otherwise returns empty records.
        """
        _ = int(limit)  # reserved for future multi-record batching (delta ledger)
        draw = get_draw_delta(series_id=series_id, cursor_version_id=int(after_id), window_candles=window_candles, at_time=None)
        next_id = int(draw.next_cursor.version_id or 0)
        if draw.to_candle_id is None or draw.to_candle_time is None:
            return WorldDeltaPollResponseV1(series_id=series_id, records=[], next_cursor=WorldCursorV1(id=int(after_id)))

        if next_id <= int(after_id):
            return WorldDeltaPollResponseV1(series_id=series_id, records=[], next_cursor=WorldCursorV1(id=int(after_id)))

        rec = WorldDeltaRecordV1(
            id=int(next_id),
            series_id=series_id,
            to_candle_id=str(draw.to_candle_id),
            to_candle_time=int(draw.to_candle_time),
            draw_delta=draw,
            factor_slices=get_factor_slices(
                series_id=series_id,
                at_time=int(draw.to_candle_time),
                window_candles=window_candles,
            ),
        )
        if os.environ.get("TRADE_CANVAS_ENABLE_DEBUG_API") == "1":
            app.state.debug_hub.emit(
                pipe="read",
                event="read.http.world_delta_poll",
                series_id=series_id,
                message="poll world delta",
                data={
                    "after_id": int(after_id),
                    "next_id": int(next_id),
                    "to_candle_time": int(draw.to_candle_time),
                    "to_candle_id": str(draw.to_candle_id),
                },
            )
        return WorldDeltaPollResponseV1(series_id=series_id, records=[rec], next_cursor=WorldCursorV1(id=int(next_id)))

    @app.get("/api/market/whitelist")
    def get_market_whitelist() -> dict[str, list[str]]:
        return {"series_ids": list(whitelist.series_ids)}

    @app.get("/api/market/debug/ingest_state")
    async def get_market_ingest_state() -> dict:
        if os.environ.get("TRADE_CANVAS_ENABLE_DEBUG_API") != "1":
            raise HTTPException(status_code=404, detail="not_found")
        return await app.state.ingest_supervisor.debug_snapshot()

    @app.get("/api/market/top_markets", response_model=TopMarketsResponse)
    def get_top_markets(
        request: Request,
        exchange: str = Query("binance", min_length=1),
        market: str = Query(..., pattern="^(spot|futures)$"),
        quote_asset: str = Query("USDT", min_length=1, max_length=12),
        limit: TopMarketsLimitQuery = 20,
        force: bool = False,
    ) -> TopMarketsResponse:
        if exchange != "binance":
            raise HTTPException(status_code=400, detail="unsupported exchange")
        if force:
            ip = request.client.host if request.client else "unknown"
            if not app.state.force_limiter.allow(key=f"{ip}:{market}"):
                raise HTTPException(status_code=429, detail="rate_limited")
        try:
            items, cached = app.state.market_list.get_top_markets(
                market=market, quote_asset=quote_asset, limit=limit, force_refresh=force
            )
        except Exception as e:
            raise HTTPException(status_code=502, detail=f"upstream_error:{e}") from e

        return TopMarketsResponse(
            exchange="binance",
            market=market,
            quote_asset=quote_asset.upper(),
            limit=int(limit),
            generated_at_ms=int(time.time() * 1000),
            cached=bool(cached),
            items=[
                {
                    "exchange": m.exchange,
                    "market": m.market,
                    "symbol": m.symbol,
                    "symbol_id": m.symbol_id,
                    "base_asset": m.base_asset,
                    "quote_asset": m.quote_asset,
                    "last_price": m.last_price,
                    "quote_volume": m.quote_volume,
                    "price_change_percent": m.price_change_percent,
                }
                for m in items
            ],
        )

    @app.get("/api/market/top_markets/stream")
    async def stream_top_markets(
        request: Request,
        exchange: str = Query("binance", min_length=1),
        market: str = Query(..., pattern="^(spot|futures)$"),
        quote_asset: str = Query("USDT", min_length=1, max_length=12),
        limit: TopMarketsLimitQuery = 20,
        interval_s: float = Query(2.0, ge=0.2, le=30.0),
        max_events: int = Query(0, ge=0, le=1000),
    ) -> StreamingResponse:
        if exchange != "binance":
            raise HTTPException(status_code=400, detail="unsupported exchange")

        async def make_payload() -> dict:
            import anyio
            import functools

            fn = functools.partial(
                app.state.market_list.get_top_markets,
                market=market,
                quote_asset=quote_asset,
                limit=limit,
                force_refresh=False,
            )
            items, cached = await anyio.to_thread.run_sync(fn)
            return {
                "exchange": "binance",
                "market": market,
                "quote_asset": quote_asset.upper(),
                "limit": int(limit),
                "generated_at_ms": int(time.time() * 1000),
                "cached": bool(cached),
                "items": [
                    {
                        "exchange": m.exchange,
                        "market": m.market,
                        "symbol": m.symbol,
                        "symbol_id": m.symbol_id,
                        "base_asset": m.base_asset,
                        "quote_asset": m.quote_asset,
                        "last_price": m.last_price,
                        "quote_volume": m.quote_volume,
                        "price_change_percent": m.price_change_percent,
                    }
                    for m in items
                ],
            }

        async def event_stream():
            import json
            import anyio

            last_fingerprint: str | None = None
            emitted = 0

            while True:
                if await request.is_disconnected():
                    return

                try:
                    payload = await make_payload()
                    # Fingerprint ignores timestamps so we can suppress duplicates.
                    fingerprint = json.dumps(
                        payload.get("items", []),
                        separators=(",", ":"),
                        sort_keys=True,
                    )
                    if last_fingerprint != fingerprint:
                        last_fingerprint = fingerprint
                        data = json.dumps(payload, separators=(",", ":"), sort_keys=True)
                        event_id = str(payload["generated_at_ms"])
                        yield f"id: {event_id}\nevent: top_markets\ndata: {data}\n\n".encode("utf-8")
                        emitted += 1
                        if max_events and emitted >= max_events:
                            return
                except Exception as e:
                    err = {"type": "error", "message": str(e), "at_ms": int(time.time() * 1000)}
                    data = json.dumps(err, separators=(",", ":"), sort_keys=True)
                    yield f"event: error\ndata: {data}\n\n".encode("utf-8")
                    emitted += 1
                    if max_events and emitted >= max_events:
                        return

                # Keep-alive comment (some proxies close idle streams).
                yield f": ping {int(time.time())}\n\n".encode("utf-8")
                await anyio.sleep(float(interval_s))

        return StreamingResponse(
            event_stream(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    @app.get("/api/backtest/strategies", response_model=StrategyListResponse)
    async def get_backtest_strategies(recursive: bool = True) -> StrategyListResponse:
        if os.environ.get("TRADE_CANVAS_FREQTRADE_MOCK") == "1":
            return StrategyListResponse(strategies=["DemoStrategy"])

        if settings.freqtrade_strategy_path is None:
            raise HTTPException(
                status_code=500,
                detail="Strategy directory not configured. Create ./Strategy or set TRADE_CANVAS_FREQTRADE_STRATEGY_PATH.",
            )

        # Backtest: only read strategies from this repo's Strategy/ directory.
        # Freqtrade still expects a userdir to exist; prefer a repo-local empty userdir when available.
        backtest_userdir = project_root / "freqtrade_user_data"
        userdir = backtest_userdir if backtest_userdir.exists() else settings.freqtrade_userdir

        res = await list_strategies_async(
            freqtrade_bin=settings.freqtrade_bin,
            userdir=userdir,
            cwd=project_root,
            recursive=recursive,
            strategy_path=settings.freqtrade_strategy_path,
            extra_env={"TRADE_CANVAS_FREQTRADE_OFFLINE_MARKETS_PAIRS": "BTC/USDT"},
        )
        strategies = parse_strategy_list(res.stdout)
        if not res.ok and not strategies:
            raise HTTPException(
                status_code=500,
                detail={
                    "message": "freqtrade list-strategies failed",
                    "exit_code": res.exit_code,
                    "stderr": res.stderr,
                },
            )
        return StrategyListResponse(strategies=strategies)

    @app.get("/api/backtest/pair_timeframes", response_model=BacktestPairTimeframesResponse)
    async def get_backtest_pair_timeframes(pair: str = Query(..., min_length=1)) -> BacktestPairTimeframesResponse:
        if os.environ.get("TRADE_CANVAS_FREQTRADE_MOCK") == "1":
            return BacktestPairTimeframesResponse(pair=pair, trading_mode="mock", datadir="", available_timeframes=[])

        if settings.freqtrade_config_path is None:
            raise HTTPException(status_code=500, detail="Freqtrade config not configured. Set TRADE_CANVAS_FREQTRADE_CONFIG.")
        if not settings.freqtrade_config_path.exists():
            raise HTTPException(status_code=500, detail=f"Freqtrade config not found: {settings.freqtrade_config_path}")

        base_cfg = load_json(settings.freqtrade_config_path)
        trading_mode = str(base_cfg.get("trading_mode") or "spot")
        stake_currency = str(base_cfg.get("stake_currency") or "USDT")

        datadir_raw = base_cfg.get("datadir")
        datadir_path = Path(datadir_raw) if isinstance(datadir_raw, str) and datadir_raw else Path("user_data/data")
        if not datadir_path.is_absolute():
            datadir_path = (settings.freqtrade_config_path.parent / datadir_path).resolve()

        # Mirror the pair normalization in /api/backtest/run.
        eff_pair = pair
        if trading_mode == "futures" and "/" in eff_pair and ":" not in eff_pair:
            eff_pair = f"{eff_pair}:{stake_currency}"

        available = list_available_timeframes(
            datadir=datadir_path,
            pair=eff_pair,
            trading_mode=trading_mode,
            stake_currency=stake_currency,
        )
        return BacktestPairTimeframesResponse(
            pair=pair,
            trading_mode=trading_mode,
            datadir=str(datadir_path),
            available_timeframes=available,
        )

    @app.post("/api/backtest/run", response_model=BacktestRunResponse)
    async def run_backtest_job(payload: BacktestRunRequest) -> BacktestRunResponse:
        if not validate_strategy_name(payload.strategy_name):
            raise HTTPException(status_code=400, detail="Invalid strategy_name")

        if os.environ.get("TRADE_CANVAS_FREQTRADE_MOCK") == "1":
            if payload.strategy_name != "DemoStrategy":
                raise HTTPException(status_code=404, detail="Strategy not found in userdir")
            pair = payload.pair
            command = [
                settings.freqtrade_bin,
                "backtesting",
                "--strategy",
                payload.strategy_name,
                "--timeframe",
                payload.timeframe,
                "--pairs",
                pair,
            ]
            if payload.timerange:
                command.extend(["--timerange", payload.timerange])
            stdout = "\n".join(
                [
                    "TRADE_CANVAS MOCK BACKTEST",
                    f"strategy={payload.strategy_name}",
                    f"pair={pair}",
                    f"timeframe={payload.timeframe}",
                    f"timerange={payload.timerange or ''}",
                    "result=ok",
                ]
            )
            return BacktestRunResponse(
                ok=True,
                exit_code=0,
                duration_ms=1,
                command=command,
                stdout=stdout,
                stderr="",
            )

        if settings.freqtrade_strategy_path is None:
            raise HTTPException(
                status_code=500,
                detail="Strategy directory not configured. Create ./Strategy or set TRADE_CANVAS_FREQTRADE_STRATEGY_PATH.",
            )

        if settings.freqtrade_config_path is None:
            raise HTTPException(
                status_code=500,
                detail="Freqtrade config not configured. Set TRADE_CANVAS_FREQTRADE_CONFIG.",
            )
        if not settings.freqtrade_config_path.exists():
            raise HTTPException(
                status_code=500,
                detail=f"Freqtrade config not found: {settings.freqtrade_config_path}",
            )
        if not settings.freqtrade_root.exists():
            raise HTTPException(
                status_code=500,
                detail=f"Freqtrade root not found: {settings.freqtrade_root}",
            )

        backtest_userdir = project_root / "freqtrade_user_data"
        userdir = backtest_userdir if backtest_userdir.exists() else settings.freqtrade_userdir
        if userdir is not None and not userdir.exists():
            raise HTTPException(status_code=500, detail=f"Freqtrade userdir not found: {userdir}")

        strategies_res = await list_strategies_async(
            freqtrade_bin=settings.freqtrade_bin,
            userdir=userdir,
            cwd=project_root,
            recursive=True,
            strategy_path=settings.freqtrade_strategy_path,
        )
        strategies = set(parse_strategy_list(strategies_res.stdout))
        if payload.strategy_name not in strategies:
            raise HTTPException(status_code=404, detail="Strategy not found in ./Strategy")

        pair = payload.pair
        base_cfg: dict = {}
        try:
            base_cfg = load_json(settings.freqtrade_config_path)
            trading_mode = str(base_cfg.get("trading_mode") or "")
            stake_currency = str(base_cfg.get("stake_currency") or "USDT")
            if trading_mode == "futures" and "/" in pair and ":" not in pair:
                pair = f"{pair}:{stake_currency}"
        except Exception:
            pass

        if not base_cfg:
            base_cfg = load_json(settings.freqtrade_config_path)

        # Normalize datadir to an absolute path so subprocess `cwd` is irrelevant.
        datadir = base_cfg.get("datadir")
        if isinstance(datadir, str) and datadir:
            p = Path(datadir)
            if not p.is_absolute():
                base_cfg["datadir"] = str((settings.freqtrade_config_path.parent / p).resolve())

        trading_mode = str(base_cfg.get("trading_mode") or "spot")
        stake_currency = str(base_cfg.get("stake_currency") or "USDT")
        datadir_path = Path(str(base_cfg.get("datadir") or ""))

        availability = check_history_available(
            datadir=datadir_path,
            pair=pair,
            timeframe=payload.timeframe,
            trading_mode=trading_mode,
            stake_currency=stake_currency,
        )
        if not availability.ok:
            expected = [str(p) for p in availability.expected_paths]
            cmd = (
                f"{settings.freqtrade_bin} download-data -c {settings.freqtrade_config_path} "
                f"--userdir {userdir} --pairs {pair} --timeframes {payload.timeframe}"
                + (" --trading-mode futures" if trading_mode == "futures" else "")
            )
            raise HTTPException(
                status_code=422,
                detail={
                    "message": "no_ohlcv_history",
                    "pair": pair,
                    "timeframe": payload.timeframe,
                    "trading_mode": trading_mode,
                    "datadir": str(datadir_path),
                    "expected_paths": expected,
                    "available_timeframes": availability.available_timeframes,
                    "hint": "Download the missing timeframe data into datadir, or switch to an available timeframe.",
                    "download_data_cmd": cmd,
                },
            )
        bt_cfg = build_backtest_config(base_cfg, pair=pair, timeframe=payload.timeframe)
        tmp_config = write_temp_config(bt_cfg, root_dir=project_root / "freqtrade_user_data")
        export_dir = project_root / "freqtrade_user_data" / "backtest_results" / f"tc_{int(time.time())}_{os.getpid()}"
        export_dir.mkdir(parents=True, exist_ok=True)
        try:
            res = await run_backtest_async(
                freqtrade_bin=settings.freqtrade_bin,
                userdir=userdir,
                cwd=project_root,
                config_path=tmp_config,
                datadir=datadir_path,
                strategy_name=payload.strategy_name,
                pair=pair,
                timeframe=payload.timeframe,
                timerange=payload.timerange,
                strategy_path=settings.freqtrade_strategy_path,
                export="trades",
                export_dir=export_dir,
                extra_env={
                    "TRADE_CANVAS_FREQTRADE_OFFLINE_MARKETS_PAIRS": pair.split(":", 1)[0],
                },
            )
        finally:
            try:
                tmp_config.unlink(missing_ok=True)
            except Exception:
                pass

        # Requirement: print freqtrade backtest results.
        # Keep stdout/stderr separated but both are printed for convenience.
        if res.stdout.strip():
            logger.info("freqtrade backtesting stdout:\n%s", res.stdout.rstrip("\n"))
        if res.stderr.strip():
            logger.info("freqtrade backtesting stderr:\n%s", res.stderr.rstrip("\n"))

        if res.ok and res.exit_code == 0 and _require_backtest_trades():
            zips = sorted(export_dir.glob("*.zip"), key=lambda p: p.stat().st_mtime, reverse=True)
            if not zips:
                raise HTTPException(
                    status_code=422,
                    detail={
                        "message": "no_backtest_export",
                        "export_dir": str(export_dir),
                        "hint": "Expected freqtrade to export backtest results but no zip was found.",
                    },
                )
            try:
                total_trades = _extract_total_trades_from_backtest_zip(
                    zip_path=zips[0], strategy_name=payload.strategy_name
                )
            except Exception as e:
                raise HTTPException(
                    status_code=422,
                    detail={
                        "message": "bad_backtest_export",
                        "export_zip": str(zips[0]),
                        "error": str(e),
                    },
                )
            if total_trades <= 0:
                raise HTTPException(
                    status_code=422,
                    detail={
                        "message": "no_trades",
                        "strategy": payload.strategy_name,
                        "total_trades": int(total_trades),
                        "export_zip": str(zips[0]),
                        "stdout_tail": (res.stdout or "")[-2000:],
                    },
                )

        return BacktestRunResponse(
            ok=res.ok,
            exit_code=res.exit_code,
            duration_ms=res.duration_ms,
            command=res.command,
            stdout=res.stdout,
            stderr=res.stderr,
        )

    @app.websocket("/ws/market")
    async def ws_market(ws: WebSocket) -> None:
        await ws.accept()
        subscribed_series: list[str] = []
        try:
            while True:
                msg = await ws.receive_json()
                msg_type = msg.get("type")
                if msg_type == "subscribe":
                    series_id = msg.get("series_id")
                    if not isinstance(series_id, str) or not series_id:
                        await ws.send_json({"type": "error", "code": "bad_request", "message": "missing series_id"})
                        continue
                    since = msg.get("since")
                    if since is not None and not isinstance(since, int):
                        await ws.send_json({"type": "error", "code": "bad_request", "message": "invalid since"})
                        continue
                    supports_batch = msg.get("supports_batch")
                    if supports_batch is not None and not isinstance(supports_batch, bool):
                        await ws.send_json(
                            {"type": "error", "code": "bad_request", "message": "invalid supports_batch"}
                        )
                        continue

                    if os.environ.get("TRADE_CANVAS_ENABLE_ONDEMAND_INGEST") == "1":
                        ok = await ws.app.state.ingest_supervisor.subscribe(series_id)
                        if not ok:
                            await ws.send_json(
                                {
                                    "type": "error",
                                    "code": "capacity",
                                    "message": "ondemand_ingest_capacity",
                                    "series_id": series_id,
                                }
                            )
                            continue

                    await hub.subscribe(ws, series_id=series_id, since=since, supports_batch=bool(supports_batch))
                    if series_id not in subscribed_series:
                        subscribed_series.append(series_id)

                    catchup = store.get_closed(series_id, since=since, limit=5000)
                    if bool(supports_batch) and catchup:
                        await ws.send_json(
                            {
                                "type": "candles_batch",
                                "series_id": series_id,
                                "candles": [c.model_dump() for c in catchup],
                            }
                        )
                        await hub.set_last_sent(ws, series_id=series_id, candle_time=int(catchup[-1].candle_time))
                    else:
                        for candle in catchup:
                            await ws.send_json(
                                {"type": "candle_closed", "series_id": series_id, "candle": candle.model_dump()}
                            )
                            await hub.set_last_sent(ws, series_id=series_id, candle_time=candle.candle_time)

                elif msg_type == "unsubscribe":
                    series_id = msg.get("series_id")
                    if isinstance(series_id, str) and series_id:
                        if os.environ.get("TRADE_CANVAS_ENABLE_ONDEMAND_INGEST") == "1":
                            await ws.app.state.ingest_supervisor.unsubscribe(series_id)
                        await hub.unsubscribe(ws, series_id=series_id)
                        subscribed_series = [s for s in subscribed_series if s != series_id]
                else:
                    await ws.send_json({"type": "error", "code": "bad_request", "message": "unknown message type"})
        except WebSocketDisconnect:
            pass
        finally:
            # Ensure that an abrupt disconnect releases ondemand ingest refcounts.
            try:
                hub_series = await hub.pop_ws(ws)
            except Exception:
                hub_series = []
            for series_id in set(subscribed_series) | set(hub_series):
                if os.environ.get("TRADE_CANVAS_ENABLE_ONDEMAND_INGEST") == "1":
                    try:
                        await ws.app.state.ingest_supervisor.unsubscribe(series_id)
                    except Exception:
                        pass
            try:
                await ws.close(code=1001)
            except Exception:
                pass


    @app.websocket("/ws/debug")
    async def ws_debug(ws: WebSocket) -> None:
        if os.environ.get("TRADE_CANVAS_ENABLE_DEBUG_API") != "1":
            try:
                await ws.close(code=1008, reason="debug_api_disabled")
            except Exception:
                pass
            return

        await ws.accept()
        app.state.debug_hub.register(ws, loop=asyncio.get_running_loop())
        try:
            await ws.send_json({"type": "debug_snapshot", "events": app.state.debug_hub.snapshot()})
            while True:
                msg = await ws.receive_json()
                if isinstance(msg, dict) and msg.get("type") == "subscribe":
                    await ws.send_json({"type": "debug_snapshot", "events": app.state.debug_hub.snapshot()})
        except WebSocketDisconnect:
            pass
        finally:
            app.state.debug_hub.unregister(ws)
            try:
                await ws.close(code=1001)
            except Exception:
                pass

    # ============ Dev Panel / Worktree Management API ============

    def _worktree_to_response(wt) -> DevWorktreeInfo:
        """Convert internal WorktreeInfo to response model."""
        metadata = None
        if wt.metadata:
            metadata = DevWorktreeMetadata(
                description=wt.metadata.description,
                plan_path=wt.metadata.plan_path,
                created_at=wt.metadata.created_at,
                owner=wt.metadata.owner,
                ports=wt.metadata.ports,
            )
        services = None
        if wt.services:
            services = DevServiceStatus(
                backend=DevServiceState(
                    running=wt.services.backend.running,
                    port=wt.services.backend.port,
                    pid=wt.services.backend.pid,
                    url=wt.services.backend.url,
                ),
                frontend=DevServiceState(
                    running=wt.services.frontend.running,
                    port=wt.services.frontend.port,
                    pid=wt.services.frontend.pid,
                    url=wt.services.frontend.url,
                ),
            )
        return DevWorktreeInfo(
            id=wt.id,
            path=wt.path,
            branch=wt.branch,
            commit=wt.commit,
            is_detached=wt.is_detached,
            is_main=wt.is_main,
            metadata=metadata,
            services=services,
        )

    @app.get("/api/dev/worktrees", response_model=DevWorktreeListResponse)
    def list_worktrees() -> DevWorktreeListResponse:
        """List all worktrees with metadata and service status."""
        worktrees = worktree_manager.list_worktrees()
        return DevWorktreeListResponse(
            worktrees=[_worktree_to_response(wt) for wt in worktrees]
        )

    @app.get("/api/dev/worktrees/{worktree_id}", response_model=DevWorktreeInfo)
    def get_worktree(worktree_id: str) -> DevWorktreeInfo:
        """Get a specific worktree by ID."""
        wt = worktree_manager.get_worktree(worktree_id)
        if wt is None:
            raise HTTPException(status_code=404, detail="worktree_not_found")
        return _worktree_to_response(wt)

    @app.post("/api/dev/worktrees", response_model=DevCreateWorktreeResponse)
    def create_worktree(req: DevCreateWorktreeRequest) -> DevCreateWorktreeResponse:
        """Create a new worktree with metadata."""
        try:
            wt = worktree_manager.create_worktree(
                branch=req.branch,
                description=req.description,
                plan_path=req.plan_path,
                base_branch=req.base_branch,
            )
            return DevCreateWorktreeResponse(ok=True, worktree=_worktree_to_response(wt))
        except ValueError as e:
            return DevCreateWorktreeResponse(ok=False, error=str(e))
        except Exception as e:
            logger.exception("Failed to create worktree")
            return DevCreateWorktreeResponse(ok=False, error=str(e))

    @app.post("/api/dev/worktrees/{worktree_id}/start", response_model=DevStartServicesResponse)
    def start_worktree_services(
        worktree_id: str, req: DevStartServicesRequest
    ) -> DevStartServicesResponse:
        """Start frontend + backend services for a worktree."""
        try:
            status = worktree_manager.start_services(
                worktree_id=worktree_id,
                backend_port=req.backend_port,
                frontend_port=req.frontend_port,
            )
            return DevStartServicesResponse(
                ok=True,
                services=DevServiceStatus(
                    backend=DevServiceState(
                        running=status.backend.running,
                        port=status.backend.port,
                        pid=status.backend.pid,
                        url=status.backend.url,
                    ),
                    frontend=DevServiceState(
                        running=status.frontend.running,
                        port=status.frontend.port,
                        pid=status.frontend.pid,
                        url=status.frontend.url,
                    ),
                ),
            )
        except ValueError as e:
            return DevStartServicesResponse(ok=False, error=str(e))
        except Exception as e:
            logger.exception("Failed to start services")
            return DevStartServicesResponse(ok=False, error=str(e))

    @app.post("/api/dev/worktrees/{worktree_id}/stop", response_model=DevStopServicesResponse)
    def stop_worktree_services(worktree_id: str) -> DevStopServicesResponse:
        """Stop services for a worktree."""
        try:
            ok = worktree_manager.stop_services(worktree_id)
            return DevStopServicesResponse(ok=ok)
        except Exception as e:
            logger.exception("Failed to stop services")
            return DevStopServicesResponse(ok=False, error=str(e))

    @app.delete("/api/dev/worktrees/{worktree_id}", response_model=DevDeleteWorktreeResponse)
    def delete_worktree(
        worktree_id: str, req: DevDeleteWorktreeRequest
    ) -> DevDeleteWorktreeResponse:
        """Delete a worktree and archive its metadata."""
        try:
            ok = worktree_manager.delete_worktree(worktree_id, force=req.force)
            return DevDeleteWorktreeResponse(ok=ok)
        except ValueError as e:
            return DevDeleteWorktreeResponse(ok=False, error=str(e))
        except Exception as e:
            logger.exception("Failed to delete worktree")
            return DevDeleteWorktreeResponse(ok=False, error=str(e))

    @app.get("/api/dev/ports/allocate", response_model=DevPortAllocationResponse)
    def allocate_ports_endpoint() -> DevPortAllocationResponse:
        """Get next available port pair."""
        from .port_allocator import allocate_ports as do_allocate

        index = worktree_manager._read_index()
        used_backend = {v.get("backend_port", 0) for v in index.get("allocations", {}).values()}
        used_frontend = {v.get("frontend_port", 0) for v in index.get("allocations", {}).values()}
        backend_port, frontend_port = do_allocate(used_backend, used_frontend)
        return DevPortAllocationResponse(backend_port=backend_port, frontend_port=frontend_port)

    @app.patch("/api/dev/worktrees/{worktree_id}/metadata", response_model=DevUpdateMetadataResponse)
    def update_worktree_metadata(
        worktree_id: str, req: DevUpdateMetadataRequest
    ) -> DevUpdateMetadataResponse:
        """Update worktree metadata."""
        try:
            metadata = worktree_manager.update_metadata(
                worktree_id=worktree_id,
                description=req.description,
                plan_path=req.plan_path,
            )
            if metadata is None:
                return DevUpdateMetadataResponse(ok=False, error="worktree_not_found")
            return DevUpdateMetadataResponse(
                ok=True,
                metadata=DevWorktreeMetadata(
                    description=metadata.description,
                    plan_path=metadata.plan_path,
                    created_at=metadata.created_at,
                    owner=metadata.owner,
                    ports=metadata.ports,
                ),
            )
        except Exception as e:
            logger.exception("Failed to update metadata")
            return DevUpdateMetadataResponse(ok=False, error=str(e))

    return app


app = create_app()
