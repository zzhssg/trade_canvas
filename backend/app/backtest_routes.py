from __future__ import annotations

import logging
import os
import time
import zipfile
from pathlib import Path

from fastapi import APIRouter, FastAPI, HTTPException, Query, Request

from .blocking import run_blocking
from .freqtrade_config import build_backtest_config, load_json, write_temp_config
from .freqtrade_data import check_history_available, list_available_timeframes
from .freqtrade_runner import list_strategies, parse_strategy_list, run_backtest, validate_strategy_name
from .schemas import BacktestPairTimeframesResponse, BacktestRunRequest, BacktestRunResponse, StrategyListResponse

router = APIRouter()
logger = logging.getLogger(__name__)


async def list_strategies_async(**kwargs):
    return await run_blocking(list_strategies, **kwargs)


async def run_backtest_async(**kwargs):
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

    import json

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


def _settings(request: Request):
    settings = request.app.state.settings
    if settings is None:
        raise HTTPException(status_code=500, detail="settings_not_ready")
    return settings


def _project_root(request: Request) -> Path:
    project_root = request.app.state.project_root
    if not isinstance(project_root, Path):
        raise HTTPException(status_code=500, detail="project_root_not_ready")
    return project_root


@router.get("/api/backtest/strategies", response_model=StrategyListResponse)
async def get_backtest_strategies(request: Request, recursive: bool = True) -> StrategyListResponse:
    if os.environ.get("TRADE_CANVAS_FREQTRADE_MOCK") == "1":
        return StrategyListResponse(strategies=["DemoStrategy"])

    settings = _settings(request)
    project_root = _project_root(request)

    if settings.freqtrade_strategy_path is None:
        raise HTTPException(
            status_code=500,
            detail="Strategy directory not configured. Create ./Strategy or set TRADE_CANVAS_FREQTRADE_STRATEGY_PATH.",
        )

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


@router.get("/api/backtest/pair_timeframes", response_model=BacktestPairTimeframesResponse)
async def get_backtest_pair_timeframes(request: Request, pair: str = Query(..., min_length=1)) -> BacktestPairTimeframesResponse:
    if os.environ.get("TRADE_CANVAS_FREQTRADE_MOCK") == "1":
        return BacktestPairTimeframesResponse(pair=pair, trading_mode="mock", datadir="", available_timeframes=[])

    settings = _settings(request)

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


@router.post("/api/backtest/run", response_model=BacktestRunResponse)
async def run_backtest_job(request: Request, payload: BacktestRunRequest) -> BacktestRunResponse:
    if not validate_strategy_name(payload.strategy_name):
        raise HTTPException(status_code=400, detail="Invalid strategy_name")

    settings = _settings(request)
    project_root = _project_root(request)

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


def register_backtest_routes(app: FastAPI) -> None:
    app.include_router(router)
