from __future__ import annotations

import os
import sys
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


def build_backtest_command(
    *,
    userdir: Path | None,
    config_path: Path | None,
    datadir: Path | None,
    strategy_name: str,
    pair: str,
    timeframe: str,
    timerange: str | None,
    strategy_path: Path | None,
    export_dir: Path | None,
    export: str | None,
) -> list[str]:
    command = [sys.executable, "-c", _FREQTRADE_BOOTSTRAP_CODE, "backtesting", "--strategy", strategy_name, "--logfile", "/dev/null", "--no-color", "--timeframe", timeframe, "--pairs", pair]
    if userdir is not None:
        command.extend(["--userdir", str(userdir)])
    if strategy_path is not None:
        command.extend(["--strategy-path", str(strategy_path)])
    if config_path is not None:
        command.extend(["-c", str(config_path)])
    if datadir is not None:
        command.extend(["--datadir", str(datadir)])
    if timerange:
        command.extend(["--timerange", timerange])
    if export:
        command.extend(["--export", export])
    if export_dir is not None:
        command.extend(["--backtest-directory", str(export_dir)])
    return command
