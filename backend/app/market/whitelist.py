from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class MarketWhitelist:
    series_ids: tuple[str, ...]


def load_market_whitelist(path: Path) -> MarketWhitelist:
    if not path.exists():
        return MarketWhitelist(series_ids=())

    data = json.loads(path.read_text(encoding="utf-8"))
    raw = data.get("series_ids", [])
    if not isinstance(raw, list):
        raise ValueError("whitelist series_ids must be a list")

    series_ids: list[str] = []
    for item in raw:
        if not isinstance(item, str) or not item.strip():
            continue
        series_ids.append(item.strip())

    # De-dup while preserving order.
    seen: set[str] = set()
    unique: list[str] = []
    for sid in series_ids:
        if sid in seen:
            continue
        seen.add(sid)
        unique.append(sid)

    return MarketWhitelist(series_ids=tuple(unique))

