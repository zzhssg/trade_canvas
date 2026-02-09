from __future__ import annotations

from datetime import datetime, timezone

from trade_oracle.models import AssetBirthRecord


_BIRTHS: dict[str, AssetBirthRecord] = {
    "BTC": AssetBirthRecord(
        symbol="BTC",
        name="Bitcoin",
        birth_time_utc=datetime(2009, 1, 3, 18, 15, 5, tzinfo=timezone.utc),
        source_ref="Bitcoin genesis block timestamp",
    ),
}


def get_asset_birth(symbol: str) -> AssetBirthRecord:
    key = symbol.strip().upper()
    if key not in _BIRTHS:
        raise KeyError(f"asset birth not found: {symbol}")
    return _BIRTHS[key]
