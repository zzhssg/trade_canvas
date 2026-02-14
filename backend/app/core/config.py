from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class PostgresSettings:
    dsn: str
    schema: str
    connect_timeout_s: float
    pool_min_size: int
    pool_max_size: int


@dataclass(frozen=True)
class StorageSettings:
    db_path: Path
    redis_url: str
    postgres: PostgresSettings


@dataclass(frozen=True)
class FreqtradeSettings:
    root: Path
    userdir: Path | None
    config_path: Path | None
    datadir: Path | None
    bin: str
    strategy_path: Path | None


@dataclass(frozen=True)
class MarketSettings:
    whitelist_path: Path
    ws_catchup_limit: int
    gap_backfill_read_limit: int
    fresh_window_candles: int
    stale_window_candles: int


@dataclass(frozen=True)
class HttpSettings:
    cors_origins: list[str]


@dataclass(frozen=True)
class Settings:
    storage: StorageSettings
    freqtrade: FreqtradeSettings
    market: MarketSettings
    http: HttpSettings

    @property
    def db_path(self) -> Path:
        return self.storage.db_path

    @property
    def postgres_dsn(self) -> str:
        return self.storage.postgres.dsn

    @property
    def postgres_schema(self) -> str:
        return self.storage.postgres.schema

    @property
    def postgres_connect_timeout_s(self) -> float:
        return self.storage.postgres.connect_timeout_s

    @property
    def postgres_pool_min_size(self) -> int:
        return self.storage.postgres.pool_min_size

    @property
    def postgres_pool_max_size(self) -> int:
        return self.storage.postgres.pool_max_size

    @property
    def redis_url(self) -> str:
        return self.storage.redis_url

    @property
    def whitelist_path(self) -> Path:
        return self.market.whitelist_path

    @property
    def freqtrade_root(self) -> Path:
        return self.freqtrade.root

    @property
    def freqtrade_userdir(self) -> Path | None:
        return self.freqtrade.userdir

    @property
    def freqtrade_config_path(self) -> Path | None:
        return self.freqtrade.config_path

    @property
    def freqtrade_datadir(self) -> Path | None:
        return self.freqtrade.datadir

    @property
    def freqtrade_bin(self) -> str:
        return self.freqtrade.bin

    @property
    def freqtrade_strategy_path(self) -> Path | None:
        return self.freqtrade.strategy_path

    @property
    def cors_origins(self) -> list[str]:
        return list(self.http.cors_origins)

    @property
    def market_ws_catchup_limit(self) -> int:
        return self.market.ws_catchup_limit

    @property
    def market_gap_backfill_read_limit(self) -> int:
        return self.market.gap_backfill_read_limit

    @property
    def market_fresh_window_candles(self) -> int:
        return self.market.fresh_window_candles

    @property
    def market_stale_window_candles(self) -> int:
        return self.market.stale_window_candles


def load_settings() -> Settings:
    root_dir = Path(__file__).resolve().parents[3]

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

    sibling_trade_system = (root_dir / ".." / "trade_system").resolve()
    default_freqtrade_root = root_dir
    default_userdir: Path | None = root_dir / "user_data_test"
    default_config: Path | None = None

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

    venv_freqtrade = root_dir / ".env" / "bin" / "freqtrade"
    default_freqtrade_bin = str(venv_freqtrade) if venv_freqtrade.exists() else "freqtrade"
    freqtrade_bin = os.environ.get("TRADE_CANVAS_FREQTRADE_BIN", default_freqtrade_bin)

    strategy_path_raw = os.environ.get("TRADE_CANVAS_FREQTRADE_STRATEGY_PATH", "").strip()
    if not strategy_path_raw:
        strategy_path_raw = str(root_dir / "Strategy")
    strategy_path = Path(strategy_path_raw)
    if not strategy_path.is_absolute():
        strategy_path = (root_dir / strategy_path).resolve()
    if strategy_path.exists():
        freqtrade_strategy_path: Path | None = strategy_path
    else:
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
        storage=StorageSettings(
            db_path=db_path,
            redis_url=redis_url,
            postgres=PostgresSettings(
                dsn=postgres_dsn,
                schema=postgres_schema,
                connect_timeout_s=float(postgres_connect_timeout_s),
                pool_min_size=int(postgres_pool_min_size),
                pool_max_size=int(postgres_pool_max_size),
            ),
        ),
        freqtrade=FreqtradeSettings(
            root=freqtrade_root,
            userdir=freqtrade_userdir,
            config_path=freqtrade_config_path,
            datadir=freqtrade_datadir,
            bin=freqtrade_bin,
            strategy_path=freqtrade_strategy_path,
        ),
        market=MarketSettings(
            whitelist_path=whitelist_path,
            ws_catchup_limit=market_ws_catchup_limit,
            gap_backfill_read_limit=market_gap_backfill_read_limit,
            fresh_window_candles=market_fresh_window_candles,
            stale_window_candles=market_stale_window_candles,
        ),
        http=HttpSettings(cors_origins=cors_origins),
    )
