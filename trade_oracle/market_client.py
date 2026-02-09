from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlencode
from urllib.request import urlopen

from .models import Candle


@dataclass(frozen=True)
class MarketClient:
    base_url: str
    timeout_s: float = 15.0

    def fetch_candles(self, *, series_id: str, limit: int = 2000, since: int | None = None) -> list[Candle]:
        query: dict[str, Any] = {"series_id": series_id, "limit": int(limit)}
        if since is not None:
            query["since"] = int(since)
        url = f"{self.base_url}/api/market/candles?{urlencode(query)}"
        with urlopen(url, timeout=self.timeout_s) as resp:  # nosec B310
            payload = json.loads(resp.read().decode("utf-8"))
        rows = payload.get("candles") or []
        return [
            Candle(
                candle_time=int(it["candle_time"]),
                open=float(it["open"]),
                high=float(it["high"]),
                low=float(it["low"]),
                close=float(it["close"]),
                volume=float(it["volume"]),
            )
            for it in rows
        ]
