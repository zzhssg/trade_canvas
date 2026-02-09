from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import urlopen

from .models import Candle


class MarketClientError(RuntimeError):
    pass


class MarketSourceUnavailableError(MarketClientError):
    pass


class MarketResponseError(MarketClientError):
    pass


@dataclass(frozen=True)
class MarketClient:
    base_url: str
    timeout_s: float = 15.0

    def fetch_candles(self, *, series_id: str, limit: int = 2000, since: int | None = None) -> list[Candle]:
        query: dict[str, Any] = {"series_id": series_id, "limit": int(limit)}
        if since is not None:
            query["since"] = int(since)
        url = f"{self.base_url}/api/market/candles?{urlencode(query)}"
        try:
            with urlopen(url, timeout=self.timeout_s) as resp:  # nosec B310
                payload = json.loads(resp.read().decode("utf-8"))
        except HTTPError as exc:
            raise MarketResponseError(f"http_status={exc.code}") from exc
        except URLError as exc:
            reason = getattr(exc, "reason", exc)
            raise MarketSourceUnavailableError(f"market_api_unreachable:{reason}") from exc
        except TimeoutError as exc:
            raise MarketSourceUnavailableError("market_api_timeout") from exc
        except json.JSONDecodeError as exc:
            raise MarketResponseError("market_api_invalid_json") from exc

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
