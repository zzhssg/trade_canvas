from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class OracleSettings:
    market_api_base: str
    enable_sx_crosscheck: bool
    enable_strategy_search: bool
    enable_backtest: bool
    market_limit: int
    wf_train_size: int
    wf_test_size: int
    trade_fee_rate: float
    target_win_rate: float
    target_reward_risk: float


def _truthy(raw: str | None) -> bool:
    if raw is None:
        return False
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def load_settings() -> OracleSettings:
    market_limit_raw = (os.environ.get("TRADE_ORACLE_MARKET_LIMIT") or "2000").strip()
    try:
        market_limit = max(100, min(5000, int(market_limit_raw)))
    except ValueError:
        market_limit = 2000

    wf_train_raw = (os.environ.get("TRADE_ORACLE_WF_TRAIN_SIZE") or "90").strip()
    wf_test_raw = (os.environ.get("TRADE_ORACLE_WF_TEST_SIZE") or "30").strip()
    fee_raw = (os.environ.get("TRADE_ORACLE_TRADE_FEE_RATE") or "0.0008").strip()
    try:
        wf_train_size = max(30, min(2000, int(wf_train_raw)))
    except ValueError:
        wf_train_size = 90
    try:
        wf_test_size = max(10, min(500, int(wf_test_raw)))
    except ValueError:
        wf_test_size = 30
    try:
        trade_fee_rate = max(0.0, min(0.02, float(fee_raw)))
    except ValueError:
        trade_fee_rate = 0.0008
    target_wr_raw = (os.environ.get("TRADE_ORACLE_TARGET_WIN_RATE") or "0.5").strip()
    target_rr_raw = (os.environ.get("TRADE_ORACLE_TARGET_REWARD_RISK") or "2.0").strip()
    try:
        target_win_rate = max(0.0, min(1.0, float(target_wr_raw)))
    except ValueError:
        target_win_rate = 0.5
    try:
        target_reward_risk = max(0.1, min(20.0, float(target_rr_raw)))
    except ValueError:
        target_reward_risk = 2.0

    return OracleSettings(
        market_api_base=(os.environ.get("TRADE_ORACLE_MARKET_API_BASE") or "http://127.0.0.1:8000").rstrip("/"),
        enable_sx_crosscheck=_truthy(os.environ.get("TRADE_ORACLE_ENABLE_SX_CROSSCHECK")),
        enable_strategy_search=_truthy(os.environ.get("TRADE_ORACLE_ENABLE_STRATEGY_SEARCH")),
        enable_backtest=_truthy(os.environ.get("TRADE_ORACLE_ENABLE_BACKTEST")),
        market_limit=market_limit,
        wf_train_size=wf_train_size,
        wf_test_size=wf_test_size,
        trade_fee_rate=trade_fee_rate,
        target_win_rate=target_win_rate,
        target_reward_risk=target_reward_risk,
    )
