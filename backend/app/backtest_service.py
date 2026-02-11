from __future__ import annotations

import logging
import os
import time
import zipfile
from pathlib import Path
from typing import Awaitable, Callable

from .freqtrade_config import build_backtest_config, load_json, write_temp_config
from .freqtrade_data import check_history_available, list_available_timeframes
from .freqtrade_runner import FreqtradeExecResult, parse_strategy_list, validate_strategy_name
from .schemas import BacktestPairTimeframesResponse, BacktestRunRequest, BacktestRunResponse, StrategyListResponse
from .service_errors import ServiceError


class BacktestService:
    def __init__(
        self,
        *,
        settings,
        project_root: Path,
        list_strategies: Callable[..., Awaitable[FreqtradeExecResult]],
        run_backtest: Callable[..., Awaitable[FreqtradeExecResult]],
        require_backtest_trades: bool = False,
        freqtrade_mock_enabled: bool = False,
        logger: logging.Logger | None = None,
    ) -> None:
        self._settings = settings
        self._project_root = project_root
        self._list_strategies = list_strategies
        self._run_backtest = run_backtest
        self._require_backtest_trades = bool(require_backtest_trades)
        self._freqtrade_mock_enabled = bool(freqtrade_mock_enabled)
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
        if self._freqtrade_mock_enabled:
            return StrategyListResponse(strategies=["DemoStrategy"])

        if self._settings.freqtrade_strategy_path is None:
            raise ServiceError(
                status_code=500,
                detail="Strategy directory not configured. Create ./Strategy or set TRADE_CANVAS_FREQTRADE_STRATEGY_PATH.",
                code="backtest.strategy_path_missing",
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
            raise ServiceError(
                status_code=500,
                detail={
                    "message": "freqtrade list-strategies failed",
                    "exit_code": res.exit_code,
                    "stderr": res.stderr,
                },
                code="backtest.list_strategies_failed",
            )
        return StrategyListResponse(strategies=strategies)

    async def get_pair_timeframes(self, *, pair: str) -> BacktestPairTimeframesResponse:
        if self._freqtrade_mock_enabled:
            return BacktestPairTimeframesResponse(pair=pair, trading_mode="mock", datadir="", available_timeframes=[])

        if self._settings.freqtrade_config_path is None:
            raise ServiceError(
                status_code=500,
                detail="Freqtrade config not configured. Set TRADE_CANVAS_FREQTRADE_CONFIG.",
                code="backtest.config_missing",
            )
        if not self._settings.freqtrade_config_path.exists():
            raise ServiceError(
                status_code=500,
                detail=f"Freqtrade config not found: {self._settings.freqtrade_config_path}",
                code="backtest.config_not_found",
            )

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

    def _run_mock_backtest(self, *, payload: BacktestRunRequest) -> BacktestRunResponse:
        if payload.strategy_name != "DemoStrategy":
            raise ServiceError(status_code=404, detail="Strategy not found in userdir", code="backtest.mock_strategy_not_found")
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

    def _ensure_run_prerequisites(self) -> Path | None:
        if self._settings.freqtrade_strategy_path is None:
            raise ServiceError(
                status_code=500,
                detail="Strategy directory not configured. Create ./Strategy or set TRADE_CANVAS_FREQTRADE_STRATEGY_PATH.",
                code="backtest.strategy_path_missing",
            )
        if self._settings.freqtrade_config_path is None:
            raise ServiceError(
                status_code=500,
                detail="Freqtrade config not configured. Set TRADE_CANVAS_FREQTRADE_CONFIG.",
                code="backtest.config_missing",
            )
        if not self._settings.freqtrade_config_path.exists():
            raise ServiceError(
                status_code=500,
                detail=f"Freqtrade config not found: {self._settings.freqtrade_config_path}",
                code="backtest.config_not_found",
            )
        if not self._settings.freqtrade_root.exists():
            raise ServiceError(
                status_code=500,
                detail=f"Freqtrade root not found: {self._settings.freqtrade_root}",
                code="backtest.root_not_found",
            )

        userdir = self._backtest_userdir()
        if userdir is not None and not userdir.exists():
            raise ServiceError(
                status_code=500,
                detail=f"Freqtrade userdir not found: {userdir}",
                code="backtest.userdir_not_found",
            )
        return userdir

    async def _load_available_strategy_names(self, *, userdir: Path | None) -> set[str]:
        strategies_res = await self._list_strategies(
            freqtrade_bin=self._settings.freqtrade_bin,
            userdir=userdir,
            cwd=self._project_root,
            recursive=True,
            strategy_path=self._settings.freqtrade_strategy_path,
        )
        return set(parse_strategy_list(strategies_res.stdout))

    def _load_base_backtest_config(self) -> dict:
        config_path = self._settings.freqtrade_config_path
        if config_path is None:
            raise ServiceError(
                status_code=500,
                detail="Freqtrade config not configured. Set TRADE_CANVAS_FREQTRADE_CONFIG.",
                code="backtest.config_missing",
            )
        base_cfg = load_json(config_path)
        datadir = base_cfg.get("datadir")
        if isinstance(datadir, str) and datadir:
            datadir_path_raw = Path(datadir)
            if not datadir_path_raw.is_absolute():
                base_cfg["datadir"] = str((config_path.parent / datadir_path_raw).resolve())
        return base_cfg

    @staticmethod
    def _resolve_pair_for_trading_mode(*, pair: str, trading_mode: str, stake_currency: str) -> str:
        normalized = str(pair)
        if trading_mode == "futures" and "/" in normalized and ":" not in normalized:
            normalized = f"{normalized}:{stake_currency}"
        return normalized

    def _ensure_history_available(
        self,
        *,
        userdir: Path | None,
        datadir_path: Path,
        pair: str,
        timeframe: str,
        trading_mode: str,
        stake_currency: str,
    ) -> None:
        availability = check_history_available(
            datadir=datadir_path,
            pair=pair,
            timeframe=timeframe,
            trading_mode=trading_mode,
            stake_currency=stake_currency,
        )
        if availability.ok:
            return
        expected = [str(p) for p in availability.expected_paths]
        cmd = (
            f"{self._settings.freqtrade_bin} download-data -c {self._settings.freqtrade_config_path} "
            f"--userdir {userdir} --pairs {pair} --timeframes {timeframe}"
            + (" --trading-mode futures" if trading_mode == "futures" else "")
        )
        raise ServiceError(
            status_code=422,
            detail={
                "message": "no_ohlcv_history",
                "pair": pair,
                "timeframe": timeframe,
                "trading_mode": trading_mode,
                "datadir": str(datadir_path),
                "expected_paths": expected,
                "available_timeframes": availability.available_timeframes,
                "hint": "Download the missing timeframe data into datadir, or switch to an available timeframe.",
                "download_data_cmd": cmd,
            },
            code="backtest.history_missing",
        )

    async def _execute_backtest(
        self,
        *,
        payload: BacktestRunRequest,
        base_cfg: dict,
        userdir: Path | None,
        datadir_path: Path,
        pair: str,
    ) -> tuple[FreqtradeExecResult, Path]:
        bt_cfg = build_backtest_config(base_cfg, pair=pair, timeframe=payload.timeframe)
        tmp_config = write_temp_config(bt_cfg, root_dir=self._project_root / "freqtrade_user_data")
        export_dir = self._project_root / "freqtrade_user_data" / "backtest_results" / f"tc_{int(time.time())}_{os.getpid()}"
        export_dir.mkdir(parents=True, exist_ok=True)
        try:
            result = await self._run_backtest(
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
        return result, export_dir

    def _log_backtest_stdio(self, *, result: FreqtradeExecResult) -> None:
        if result.stdout.strip():
            self._logger.info("freqtrade backtesting stdout:\n%s", result.stdout.rstrip("\n"))
        if result.stderr.strip():
            self._logger.info("freqtrade backtesting stderr:\n%s", result.stderr.rstrip("\n"))

    def _ensure_backtest_trades(self, *, result: FreqtradeExecResult, export_dir: Path, strategy_name: str) -> None:
        if not (result.ok and result.exit_code == 0 and self._require_backtest_trades):
            return

        zips = sorted(export_dir.glob("*.zip"), key=lambda p: p.stat().st_mtime, reverse=True)
        if not zips:
            raise ServiceError(
                status_code=422,
                detail={
                    "message": "no_backtest_export",
                    "export_dir": str(export_dir),
                    "hint": "Expected freqtrade to export backtest results but no zip was found.",
                },
                code="backtest.export_missing",
            )
        try:
            total_trades = self._extract_total_trades_from_backtest_zip(
                zip_path=zips[0],
                strategy_name=strategy_name,
            )
        except Exception as exc:
            raise ServiceError(
                status_code=422,
                detail={
                    "message": "bad_backtest_export",
                    "export_zip": str(zips[0]),
                    "error": str(exc),
                },
                code="backtest.export_bad",
            )
        if total_trades <= 0:
            raise ServiceError(
                status_code=422,
                detail={
                    "message": "no_trades",
                    "strategy": strategy_name,
                    "total_trades": int(total_trades),
                    "export_zip": str(zips[0]),
                    "stdout_tail": (result.stdout or "")[-2000:],
                },
                code="backtest.no_trades",
            )

    async def run(self, *, payload: BacktestRunRequest) -> BacktestRunResponse:
        if not validate_strategy_name(payload.strategy_name):
            raise ServiceError(status_code=400, detail="Invalid strategy_name", code="backtest.strategy_name_invalid")

        if self._freqtrade_mock_enabled:
            return self._run_mock_backtest(payload=payload)

        userdir = self._ensure_run_prerequisites()
        strategies = await self._load_available_strategy_names(userdir=userdir)
        if payload.strategy_name not in strategies:
            raise ServiceError(status_code=404, detail="Strategy not found in ./Strategy", code="backtest.strategy_not_found")

        base_cfg = self._load_base_backtest_config()
        trading_mode = str(base_cfg.get("trading_mode") or "spot")
        stake_currency = str(base_cfg.get("stake_currency") or "USDT")
        pair = self._resolve_pair_for_trading_mode(
            pair=payload.pair,
            trading_mode=trading_mode,
            stake_currency=stake_currency,
        )
        datadir_path = Path(str(base_cfg.get("datadir") or ""))
        self._ensure_history_available(
            userdir=userdir,
            datadir_path=datadir_path,
            pair=pair,
            timeframe=payload.timeframe,
            trading_mode=trading_mode,
            stake_currency=stake_currency,
        )
        res, export_dir = await self._execute_backtest(
            payload=payload,
            base_cfg=base_cfg,
            userdir=userdir,
            datadir_path=datadir_path,
            pair=pair,
        )
        self._log_backtest_stdio(result=res)
        self._ensure_backtest_trades(
            result=res,
            export_dir=export_dir,
            strategy_name=payload.strategy_name,
        )

        return BacktestRunResponse(
            ok=res.ok,
            exit_code=res.exit_code,
            duration_ms=res.duration_ms,
            command=res.command,
            stdout=res.stdout,
            stderr=res.stderr,
        )
