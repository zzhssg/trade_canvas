from __future__ import annotations

import logging
import os
import time
import zipfile
from pathlib import Path
from typing import Awaitable, Callable

from fastapi import HTTPException

from .freqtrade_config import build_backtest_config, load_json, write_temp_config
from .freqtrade_data import check_history_available, list_available_timeframes
from .freqtrade_runner import FreqtradeExecResult, parse_strategy_list, validate_strategy_name
from .schemas import BacktestPairTimeframesResponse, BacktestRunRequest, BacktestRunResponse, StrategyListResponse


class BacktestService:
    def __init__(
        self,
        *,
        settings,
        project_root: Path,
        list_strategies: Callable[..., Awaitable[FreqtradeExecResult]],
        run_backtest: Callable[..., Awaitable[FreqtradeExecResult]],
        require_backtest_trades: Callable[[], bool],
        freqtrade_mock_enabled: Callable[[], bool],
        logger: logging.Logger | None = None,
    ) -> None:
        self._settings = settings
        self._project_root = project_root
        self._list_strategies = list_strategies
        self._run_backtest = run_backtest
        self._require_backtest_trades = require_backtest_trades
        self._freqtrade_mock_enabled = freqtrade_mock_enabled
        self._logger = logger or logging.getLogger(__name__)

    def _backtest_userdir(self) -> Path | None:
        backtest_userdir = self._project_root / "freqtrade_user_data"
        return backtest_userdir if backtest_userdir.exists() else self._settings.freqtrade_userdir

    @staticmethod
    def _extract_total_trades_from_backtest_zip(*, zip_path: Path, strategy_name: str) -> int:
        with zipfile.ZipFile(str(zip_path), "r") as zf:
            candidates = [
                name
                for name in zf.namelist()
                if name.startswith("backtest-result-") and name.endswith(".json") and not name.endswith("_config.json")
            ]
            if not candidates:
                candidates = [name for name in zf.namelist() if name.endswith(".json") and not name.endswith("_config.json")]
            if not candidates:
                raise ValueError("missing backtest stats json in zip")
            raw = zf.read(candidates[0]).decode("utf-8", errors="replace")

        import json

        payload = json.loads(raw)
        strategy_payload = (payload.get("strategy") or {}).get(strategy_name)
        if not isinstance(strategy_payload, dict):
            raise ValueError("missing strategy stats in backtest json")
        total = strategy_payload.get("total_trades")
        if isinstance(total, int):
            return total
        trades = strategy_payload.get("trades")
        if isinstance(trades, list):
            return len(trades)
        raise ValueError("missing total_trades/trades in strategy stats")

    async def get_strategies(self, *, recursive: bool = True) -> StrategyListResponse:
        if self._freqtrade_mock_enabled():
            return StrategyListResponse(strategies=["DemoStrategy"])

        if self._settings.freqtrade_strategy_path is None:
            raise HTTPException(
                status_code=500,
                detail="Strategy directory not configured. Create ./Strategy or set TRADE_CANVAS_FREQTRADE_STRATEGY_PATH.",
            )

        res = await self._list_strategies(
            freqtrade_bin=self._settings.freqtrade_bin,
            userdir=self._backtest_userdir(),
            cwd=self._project_root,
            recursive=recursive,
            strategy_path=self._settings.freqtrade_strategy_path,
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

    async def get_pair_timeframes(self, *, pair: str) -> BacktestPairTimeframesResponse:
        if self._freqtrade_mock_enabled():
            return BacktestPairTimeframesResponse(pair=pair, trading_mode="mock", datadir="", available_timeframes=[])

        if self._settings.freqtrade_config_path is None:
            raise HTTPException(status_code=500, detail="Freqtrade config not configured. Set TRADE_CANVAS_FREQTRADE_CONFIG.")
        if not self._settings.freqtrade_config_path.exists():
            raise HTTPException(status_code=500, detail=f"Freqtrade config not found: {self._settings.freqtrade_config_path}")

        base_cfg = load_json(self._settings.freqtrade_config_path)
        trading_mode = str(base_cfg.get("trading_mode") or "spot")
        stake_currency = str(base_cfg.get("stake_currency") or "USDT")

        datadir_raw = base_cfg.get("datadir")
        datadir_path = Path(datadir_raw) if isinstance(datadir_raw, str) and datadir_raw else Path("user_data/data")
        if not datadir_path.is_absolute():
            datadir_path = (self._settings.freqtrade_config_path.parent / datadir_path).resolve()

        effective_pair = pair
        if trading_mode == "futures" and "/" in effective_pair and ":" not in effective_pair:
            effective_pair = f"{effective_pair}:{stake_currency}"

        available = list_available_timeframes(
            datadir=datadir_path,
            pair=effective_pair,
            trading_mode=trading_mode,
            stake_currency=stake_currency,
        )
        return BacktestPairTimeframesResponse(
            pair=pair,
            trading_mode=trading_mode,
            datadir=str(datadir_path),
            available_timeframes=available,
        )

    async def run(self, *, payload: BacktestRunRequest) -> BacktestRunResponse:
        if not validate_strategy_name(payload.strategy_name):
            raise HTTPException(status_code=400, detail="Invalid strategy_name")

        if self._freqtrade_mock_enabled():
            if payload.strategy_name != "DemoStrategy":
                raise HTTPException(status_code=404, detail="Strategy not found in userdir")
            pair = payload.pair
            command = [
                self._settings.freqtrade_bin,
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

        if self._settings.freqtrade_strategy_path is None:
            raise HTTPException(
                status_code=500,
                detail="Strategy directory not configured. Create ./Strategy or set TRADE_CANVAS_FREQTRADE_STRATEGY_PATH.",
            )
        if self._settings.freqtrade_config_path is None:
            raise HTTPException(status_code=500, detail="Freqtrade config not configured. Set TRADE_CANVAS_FREQTRADE_CONFIG.")
        if not self._settings.freqtrade_config_path.exists():
            raise HTTPException(status_code=500, detail=f"Freqtrade config not found: {self._settings.freqtrade_config_path}")
        if not self._settings.freqtrade_root.exists():
            raise HTTPException(status_code=500, detail=f"Freqtrade root not found: {self._settings.freqtrade_root}")

        userdir = self._backtest_userdir()
        if userdir is not None and not userdir.exists():
            raise HTTPException(status_code=500, detail=f"Freqtrade userdir not found: {userdir}")

        strategies_res = await self._list_strategies(
            freqtrade_bin=self._settings.freqtrade_bin,
            userdir=userdir,
            cwd=self._project_root,
            recursive=True,
            strategy_path=self._settings.freqtrade_strategy_path,
        )
        strategies = set(parse_strategy_list(strategies_res.stdout))
        if payload.strategy_name not in strategies:
            raise HTTPException(status_code=404, detail="Strategy not found in ./Strategy")

        pair = payload.pair
        base_cfg: dict = {}
        try:
            base_cfg = load_json(self._settings.freqtrade_config_path)
            trading_mode = str(base_cfg.get("trading_mode") or "")
            stake_currency = str(base_cfg.get("stake_currency") or "USDT")
            if trading_mode == "futures" and "/" in pair and ":" not in pair:
                pair = f"{pair}:{stake_currency}"
        except Exception:
            pass

        if not base_cfg:
            base_cfg = load_json(self._settings.freqtrade_config_path)

        datadir = base_cfg.get("datadir")
        if isinstance(datadir, str) and datadir:
            datadir_path_raw = Path(datadir)
            if not datadir_path_raw.is_absolute():
                base_cfg["datadir"] = str((self._settings.freqtrade_config_path.parent / datadir_path_raw).resolve())

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
                f"{self._settings.freqtrade_bin} download-data -c {self._settings.freqtrade_config_path} "
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
        tmp_config = write_temp_config(bt_cfg, root_dir=self._project_root / "freqtrade_user_data")
        export_dir = self._project_root / "freqtrade_user_data" / "backtest_results" / f"tc_{int(time.time())}_{os.getpid()}"
        export_dir.mkdir(parents=True, exist_ok=True)
        try:
            res = await self._run_backtest(
                freqtrade_bin=self._settings.freqtrade_bin,
                userdir=userdir,
                cwd=self._project_root,
                config_path=tmp_config,
                datadir=datadir_path,
                strategy_name=payload.strategy_name,
                pair=pair,
                timeframe=payload.timeframe,
                timerange=payload.timerange,
                strategy_path=self._settings.freqtrade_strategy_path,
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
            self._logger.info("freqtrade backtesting stdout:\n%s", res.stdout.rstrip("\n"))
        if res.stderr.strip():
            self._logger.info("freqtrade backtesting stderr:\n%s", res.stderr.rstrip("\n"))

        if res.ok and res.exit_code == 0 and self._require_backtest_trades():
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
                total_trades = self._extract_total_trades_from_backtest_zip(
                    zip_path=zips[0],
                    strategy_name=payload.strategy_name,
                )
            except Exception as exc:
                raise HTTPException(
                    status_code=422,
                    detail={
                        "message": "bad_backtest_export",
                        "export_zip": str(zips[0]),
                        "error": str(exc),
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
