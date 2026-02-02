from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    db_path: Path
    whitelist_path: Path
    freqtrade_root: Path
    freqtrade_userdir: Path | None
    freqtrade_config_path: Path | None
    freqtrade_bin: str
    freqtrade_strategy_path: Path | None
    cors_origins: list[str]


def load_settings() -> Settings:
    root_dir = Path(__file__).resolve().parents[2]

    db_path = Path(os.environ.get("TRADE_CANVAS_DB_PATH", "backend/data/market.db"))
    whitelist_path = Path(os.environ.get("TRADE_CANVAS_WHITELIST_PATH", "backend/config/market_whitelist.json"))

    # Defaults: prefer sibling ../trade_system when present (dev convenience),
    # otherwise fall back to in-repo user_data_test.
    sibling_trade_system = (root_dir / ".." / "trade_system").resolve()
    default_freqtrade_root = root_dir
    default_userdir: Path | None = root_dir / "user_data_test"
    default_config: Path | None = None

    # If trade_system is available, prefer its project-root layout:
    # - cwd/root is ../trade_system
    # - userdir is implicit (default "user_data" inside cwd)
    if sibling_trade_system.exists() and (sibling_trade_system / "user_data").exists():
        default_freqtrade_root = sibling_trade_system
        default_userdir = None
        if (sibling_trade_system / "config.json").exists():
            default_config = sibling_trade_system / "config.json"

    freqtrade_root = Path(os.environ.get("TRADE_CANVAS_FREQTRADE_ROOT", str(default_freqtrade_root)))
    if not freqtrade_root.is_absolute():
        freqtrade_root = (root_dir / freqtrade_root).resolve()

    freqtrade_userdir_raw = os.environ.get(
        "TRADE_CANVAS_FREQTRADE_USERDIR",
        str(default_userdir) if default_userdir is not None else "",
    ).strip()
    freqtrade_userdir = Path(freqtrade_userdir_raw) if freqtrade_userdir_raw else None
    if freqtrade_userdir is not None and not freqtrade_userdir.is_absolute():
        freqtrade_userdir = (freqtrade_root / freqtrade_userdir).resolve()

    freqtrade_config_raw = os.environ.get(
        "TRADE_CANVAS_FREQTRADE_CONFIG",
        str(default_config) if default_config else "",
    ).strip()
    freqtrade_config_path = Path(freqtrade_config_raw) if freqtrade_config_raw else None
    if freqtrade_config_path is not None and not freqtrade_config_path.is_absolute():
        freqtrade_config_path = (freqtrade_root / freqtrade_config_path).resolve()

    # Prefer project venv freqtrade when present to avoid PATH collisions.
    venv_freqtrade = root_dir / ".env" / "bin" / "freqtrade"
    default_freqtrade_bin = str(venv_freqtrade) if venv_freqtrade.exists() else "freqtrade"
    freqtrade_bin = os.environ.get("TRADE_CANVAS_FREQTRADE_BIN", default_freqtrade_bin)

    # Optional: allow strategies to live in a project-local directory (not necessarily inside userdir).
    # This is passed to freqtrade as `--strategy-path`.
    strategy_path_raw = os.environ.get("TRADE_CANVAS_FREQTRADE_STRATEGY_PATH", "").strip()
    if not strategy_path_raw:
        strategy_path_raw = str(root_dir / "Strategy")
    freqtrade_strategy_path = Path(strategy_path_raw)
    if not freqtrade_strategy_path.is_absolute():
        freqtrade_strategy_path = (root_dir / freqtrade_strategy_path).resolve()
    if not freqtrade_strategy_path.exists():
        # Do not fail boot when the directory doesn't exist; just skip passing it.
        freqtrade_strategy_path = None

    cors_origins_raw = os.environ.get(
        "TRADE_CANVAS_CORS_ORIGINS",
        "http://localhost:5173,http://127.0.0.1:5173",
    )
    cors_origins = [o.strip() for o in cors_origins_raw.split(",") if o.strip()]

    return Settings(
        db_path=db_path,
        whitelist_path=whitelist_path,
        freqtrade_root=freqtrade_root,
        freqtrade_userdir=freqtrade_userdir,
        freqtrade_config_path=freqtrade_config_path,
        freqtrade_bin=freqtrade_bin,
        freqtrade_strategy_path=freqtrade_strategy_path,
        cors_origins=cors_origins,
    )
