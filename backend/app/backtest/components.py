from __future__ import annotations

import json
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Awaitable, Callable

from ..freqtrade.config import load_json
from ..freqtrade.data import check_history_available
from ..freqtrade.runner import FreqtradeExecResult, parse_strategy_list
from ..core.service_errors import ServiceError


@dataclass(frozen=True)
class BacktestRunContext:
    userdir: Path | None
    base_cfg: dict[str, Any]
    trading_mode: str
    stake_currency: str
    pair: str
    datadir_path: Path


class BacktestPreflight:
    def __init__(
        self,
        *,
        settings: Any,
        project_root: Path,
        list_strategies: Callable[..., Awaitable[FreqtradeExecResult]],
        backtest_userdir_resolver: Callable[[], Path | None],
    ) -> None:
        self._settings = settings
        self._project_root = project_root
        self._list_strategies = list_strategies
        self._backtest_userdir_resolver = backtest_userdir_resolver

    def ensure_run_prerequisites(self) -> Path | None:
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

        userdir = self._backtest_userdir_resolver()
        if userdir is not None and not userdir.exists():
            raise ServiceError(
                status_code=500,
                detail=f"Freqtrade userdir not found: {userdir}",
                code="backtest.userdir_not_found",
            )
        return userdir

    async def load_available_strategy_names(self, *, userdir: Path | None) -> set[str]:
        strategies_res = await self._list_strategies(
            freqtrade_bin=self._settings.freqtrade_bin,
            userdir=userdir,
            cwd=self._project_root,
            recursive=True,
            strategy_path=self._settings.freqtrade_strategy_path,
        )
        return set(parse_strategy_list(strategies_res.stdout))

    def load_base_backtest_config(self) -> dict[str, Any]:
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
    def resolve_pair_for_trading_mode(*, pair: str, trading_mode: str, stake_currency: str) -> str:
        normalized = str(pair)
        if trading_mode == "futures" and "/" in normalized and ":" not in normalized:
            normalized = f"{normalized}:{stake_currency}"
        return normalized

    def ensure_history_available(
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

    async def prepare_run(
        self,
        *,
        strategy_name: str,
        pair: str,
        timeframe: str,
    ) -> BacktestRunContext:
        userdir = self.ensure_run_prerequisites()
        strategies = await self.load_available_strategy_names(userdir=userdir)
        if strategy_name not in strategies:
            raise ServiceError(status_code=404, detail="Strategy not found in ./Strategy", code="backtest.strategy_not_found")

        base_cfg = self.load_base_backtest_config()
        trading_mode = str(base_cfg.get("trading_mode") or "spot")
        stake_currency = str(base_cfg.get("stake_currency") or "USDT")
        resolved_pair = self.resolve_pair_for_trading_mode(
            pair=pair,
            trading_mode=trading_mode,
            stake_currency=stake_currency,
        )
        datadir_path = Path(str(base_cfg.get("datadir") or ""))
        self.ensure_history_available(
            userdir=userdir,
            datadir_path=datadir_path,
            pair=resolved_pair,
            timeframe=timeframe,
            trading_mode=trading_mode,
            stake_currency=stake_currency,
        )
        return BacktestRunContext(
            userdir=userdir,
            base_cfg=base_cfg,
            trading_mode=trading_mode,
            stake_currency=stake_currency,
            pair=resolved_pair,
            datadir_path=datadir_path,
        )


class BacktestResultInspector:
    def __init__(self, *, require_backtest_trades: bool) -> None:
        self._require_backtest_trades = bool(require_backtest_trades)

    @staticmethod
    def extract_total_trades_from_backtest_zip(*, zip_path: Path, strategy_name: str) -> int:
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

    def ensure_trades(self, *, result: FreqtradeExecResult, export_dir: Path, strategy_name: str) -> None:
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
            total_trades = self.extract_total_trades_from_backtest_zip(
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
