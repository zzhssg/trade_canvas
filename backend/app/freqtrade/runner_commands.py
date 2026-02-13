from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path

_FREQTRADE_BOOTSTRAP_CODE = (
    "from trade_canvas.offline_bootstrap import maybe_patch_ccxt; "
    "maybe_patch_ccxt(); from freqtrade import main as _m; _m.main()"
)


def build_runner_env(*, cwd: Path | None, extra_env: dict[str, str] | None) -> dict[str, str]:
    env = os.environ.copy()
    if cwd is not None:
        env["PYTHONPATH"] = f"{cwd}{os.pathsep}{env.get('PYTHONPATH', '')}".rstrip(os.pathsep)
    if extra_env:
        env.update(extra_env)
    return env


def build_list_strategies_command(
    *,
    userdir: Path | None,
    recursive: bool,
    strategy_path: Path | None,
) -> list[str]:
    command = [sys.executable, "-c", _FREQTRADE_BOOTSTRAP_CODE, "list-strategies", "-1", "--logfile", "/dev/null", "--no-color"]
    if userdir is not None:
        command.extend(["--userdir", str(userdir)])
    if strategy_path is not None:
        command.extend(["--strategy-path", str(strategy_path)])
    if recursive:
        command.append("--recursive-strategy-search")
    return command


@dataclass(frozen=True)
class BacktestCommandRequest:
    userdir: Path | None
    config_path: Path | None
    datadir: Path | None
    strategy_name: str
    pair: str
    timeframe: str
    timerange: str | None
    strategy_path: Path | None
    export_dir: Path | None
    export: str | None


def build_backtest_command(request: BacktestCommandRequest) -> list[str]:
    command = [
        sys.executable,
        "-c",
        _FREQTRADE_BOOTSTRAP_CODE,
        "backtesting",
        "--strategy",
        request.strategy_name,
        "--logfile",
        "/dev/null",
        "--no-color",
        "--timeframe",
        request.timeframe,
        "--pairs",
        request.pair,
    ]
    if request.userdir is not None:
        command.extend(["--userdir", str(request.userdir)])
    if request.strategy_path is not None:
        command.extend(["--strategy-path", str(request.strategy_path)])
    if request.config_path is not None:
        command.extend(["-c", str(request.config_path)])
    if request.datadir is not None:
        command.extend(["--datadir", str(request.datadir)])
    if request.timerange:
        command.extend(["--timerange", request.timerange])
    if request.export:
        command.extend(["--export", request.export])
    if request.export_dir is not None:
        command.extend(["--backtest-directory", str(request.export_dir)])
    return command
