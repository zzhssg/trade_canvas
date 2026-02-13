from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    db_path: Path
    postgres_dsn: str
    postgres_schema: str
    postgres_connect_timeout_s: float
    postgres_pool_min_size: int
    postgres_pool_max_size: int
    redis_url: str
    whitelist_path: Path
    freqtrade_root: Path
    freqtrade_userdir: Path | None
    freqtrade_config_path: Path | None
    freqtrade_datadir: Path | None
    freqtrade_bin: str
    freqtrade_strategy_path: Path | None
    cors_origins: list[str]
    market_ws_catchup_limit: int
    market_gap_backfill_read_limit: int
    market_fresh_window_candles: int
    market_stale_window_candles: int


def load_settings() -> Settings:
    root_dir = Path(__file__).resolve().parents[2]

    db_path = Path(os.environ.get("TRADE_CANVAS_DB_PATH", "backend/data/market.db"))
    whitelist_path = Path(os.environ.get("TRADE_CANVAS_WHITELIST_PATH", "backend/config/market_whitelist.json"))

    postgres_dsn = (os.environ.get("TRADE_CANVAS_POSTGRES_DSN") or "").strip()
    postgres_schema = (os.environ.get("TRADE_CANVAS_POSTGRES_SCHEMA") or "public").strip() or "public"
    redis_url = (os.environ.get("TRADE_CANVAS_REDIS_URL") or "").strip()

    def _env_float(name: str, default: float, *, minimum: float) -> float:
        raw = (os.environ.get(name) or "").strip()
        if not raw:
            return max(float(minimum), float(default))
        try:
            return max(float(minimum), float(raw))
        except ValueError:
            return max(float(minimum), float(default))

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

    freqtrade_datadir_raw = os.environ.get("TRADE_CANVAS_FREQTRADE_DATADIR", "").strip()
    freqtrade_datadir = Path(freqtrade_datadir_raw) if freqtrade_datadir_raw else None
    if freqtrade_datadir is not None and not freqtrade_datadir.is_absolute():
        freqtrade_datadir = (freqtrade_root / freqtrade_datadir).resolve()

    # Prefer project venv freqtrade when present to avoid PATH collisions.
    venv_freqtrade = root_dir / ".env" / "bin" / "freqtrade"
    default_freqtrade_bin = str(venv_freqtrade) if venv_freqtrade.exists() else "freqtrade"
    freqtrade_bin = os.environ.get("TRADE_CANVAS_FREQTRADE_BIN", default_freqtrade_bin)

    # Optional: allow strategies to live in a project-local directory (not necessarily inside userdir).
    # This is passed to freqtrade as `--strategy-path`.
    strategy_path_raw = os.environ.get("TRADE_CANVAS_FREQTRADE_STRATEGY_PATH", "").strip()
    if not strategy_path_raw:
        strategy_path_raw = str(root_dir / "Strategy")
    strategy_path = Path(strategy_path_raw)
    if not strategy_path.is_absolute():
        strategy_path = (root_dir / strategy_path).resolve()
    if strategy_path.exists():
        freqtrade_strategy_path: Path | None = strategy_path
    else:
        # Do not fail boot when the directory doesn't exist; just skip passing it.
        freqtrade_strategy_path = None

    cors_origins_raw = os.environ.get(
        "TRADE_CANVAS_CORS_ORIGINS",
        "http://localhost:5173,http://127.0.0.1:5173",
    )
    cors_origins = [o.strip() for o in cors_origins_raw.split(",") if o.strip()]

    def _env_int(name: str, default: int, *, minimum: int) -> int:
        raw = (os.environ.get(name) or "").strip()
        if not raw:
            return max(int(minimum), int(default))
        try:
            return max(int(minimum), int(raw))
        except ValueError:
            return max(int(minimum), int(default))

    market_ws_catchup_limit = _env_int("TRADE_CANVAS_MARKET_WS_CATCHUP_LIMIT", 5000, minimum=100)
    market_gap_backfill_read_limit = _env_int("TRADE_CANVAS_MARKET_GAP_BACKFILL_READ_LIMIT", 5000, minimum=100)
    market_fresh_window_candles = _env_int("TRADE_CANVAS_MARKET_FRESH_WINDOW_CANDLES", 2, minimum=1)
    market_stale_window_candles = _env_int(
        "TRADE_CANVAS_MARKET_STALE_WINDOW_CANDLES",
        5,
        minimum=market_fresh_window_candles + 1,
    )
    postgres_connect_timeout_s = _env_float(
        "TRADE_CANVAS_POSTGRES_CONNECT_TIMEOUT_S",
        5.0,
        minimum=0.1,
    )
    postgres_pool_min_size = _env_int(
        "TRADE_CANVAS_POSTGRES_POOL_MIN_SIZE",
        1,
        minimum=1,
    )
    postgres_pool_max_size = _env_int(
        "TRADE_CANVAS_POSTGRES_POOL_MAX_SIZE",
        10,
        minimum=postgres_pool_min_size,
    )

    return Settings(
        db_path=db_path,
        postgres_dsn=postgres_dsn,
        postgres_schema=postgres_schema,
        postgres_connect_timeout_s=float(postgres_connect_timeout_s),
        postgres_pool_min_size=int(postgres_pool_min_size),
        postgres_pool_max_size=int(postgres_pool_max_size),
        redis_url=redis_url,
        whitelist_path=whitelist_path,
        freqtrade_root=freqtrade_root,
        freqtrade_userdir=freqtrade_userdir,
        freqtrade_config_path=freqtrade_config_path,
        freqtrade_datadir=freqtrade_datadir,
        freqtrade_bin=freqtrade_bin,
        freqtrade_strategy_path=freqtrade_strategy_path,
        cors_origins=cors_origins,
        market_ws_catchup_limit=market_ws_catchup_limit,
        market_gap_backfill_read_limit=market_gap_backfill_read_limit,
        market_fresh_window_candles=market_fresh_window_candles,
        market_stale_window_candles=market_stale_window_candles,
    )
