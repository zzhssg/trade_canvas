from __future__ import annotations

import logging
import os
import time
from pathlib import Path
from typing import Awaitable, Callable

from .components import BacktestPreflight, BacktestResultInspector
from ..freqtrade.config import build_backtest_config, load_json, write_temp_config
from ..freqtrade.data import list_available_timeframes
from ..freqtrade.runner import FreqtradeExecResult, parse_strategy_list, validate_strategy_name
from ..core.schemas import BacktestPairTimeframesResponse, BacktestRunRequest, BacktestRunResponse, StrategyListResponse
from ..core.service_errors import ServiceError


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
        self._freqtrade_mock_enabled = bool(freqtrade_mock_enabled)
        self._logger = logger or logging.getLogger(__name__)
        self._preflight = BacktestPreflight(
            settings=settings,
            project_root=project_root,
            list_strategies=self._list_strategies_proxy,
            backtest_userdir_resolver=self._backtest_userdir,
        )
        self._result_inspector = BacktestResultInspector(require_backtest_trades=bool(require_backtest_trades))

    async def _list_strategies_proxy(self, **kwargs) -> FreqtradeExecResult:  # type: ignore[no-untyped-def]
        return await self._list_strategies(**kwargs)

    def _backtest_userdir(self) -> Path | None:
        backtest_userdir = self._project_root / "freqtrade_user_data"
        return backtest_userdir if backtest_userdir.exists() else self._settings.freqtrade_userdir

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

    async def run(self, *, payload: BacktestRunRequest) -> BacktestRunResponse:
        if not validate_strategy_name(payload.strategy_name):
            raise ServiceError(status_code=400, detail="Invalid strategy_name", code="backtest.strategy_name_invalid")

        if self._freqtrade_mock_enabled:
            return self._run_mock_backtest(payload=payload)

        run_context = await self._preflight.prepare_run(
            strategy_name=payload.strategy_name,
            pair=payload.pair,
            timeframe=payload.timeframe,
        )
        res, export_dir = await self._execute_backtest(
            payload=payload,
            base_cfg=run_context.base_cfg,
            userdir=run_context.userdir,
            datadir_path=run_context.datadir_path,
            pair=run_context.pair,
        )
        self._log_backtest_stdio(result=res)
        self._result_inspector.ensure_trades(
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
