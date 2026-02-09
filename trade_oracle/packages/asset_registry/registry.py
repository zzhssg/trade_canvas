from __future__ import annotations

from datetime import datetime, timezone

from trade_oracle.models import AssetBirthRecord


_BIRTHS: dict[str, AssetBirthRecord] = {
    "BTC": AssetBirthRecord(
        symbol="BTC",
        name="Bitcoin",
        birth_time_utc=datetime(2009, 1, 3, 16, 15, 0, tzinfo=timezone.utc),
        source_ref="Bitcoin genesis block at 2009-01-03 18:15 GMT+2 (converted to UTC)",
    ),
}


def get_asset_birth(symbol: str) -> AssetBirthRecord:
    key = symbol.strip().upper()
    if key not in _BIRTHS:
        raise KeyError(f"asset birth not found: {symbol}")
    return _BIRTHS[key]
