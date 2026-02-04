from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class DataAvailability:
    ok: bool
    trading_mode: str
    datadir: Path
    pair: str
    timeframe: str
    expected_paths: list[Path]
    available_timeframes: list[str]


def _pair_parts(pair: str) -> tuple[str, str, str | None]:
    """
    Pair formats we may see:
    - spot: "BTC/USDT"
    - futures: "BTC/USDT:USDT"  (pair:margin)
    """
    s = pair.strip()
    margin = None
    if ":" in s:
        s, margin = s.split(":", 1)
        margin = margin.strip() or None
    if "/" not in s:
        raise ValueError(f"Invalid pair: {pair!r}")
    base, quote = s.split("/", 1)
    base = base.strip()
    quote = quote.strip()
    if not base or not quote:
        raise ValueError(f"Invalid pair: {pair!r}")
    return base, quote, margin


def _pair_prefix(*, pair: str, trading_mode: str, stake_currency: str | None) -> str:
    base, quote, margin = _pair_parts(pair)
    if trading_mode == "futures":
        # freqtrade futures filenames include margin currency (usually stake_currency).
        m = margin or stake_currency or quote
        return f"{base}_{quote}_{m}"
    return f"{base}_{quote}"


def _candidate_suffixes() -> list[str]:
    # Keep small; these are the common local formats.
    return [".feather", ".parquet"]


def expected_history_paths(
    *,
    datadir: Path,
    pair: str,
    timeframe: str,
    trading_mode: str,
    stake_currency: str | None,
) -> list[Path]:
    prefix = _pair_prefix(pair=pair, trading_mode=trading_mode, stake_currency=stake_currency)
    if trading_mode == "futures":
        base = datadir / "futures" / f"{prefix}-{timeframe}-futures"
    else:
        base = datadir / f"{prefix}-{timeframe}"
    return [Path(str(base) + suf) for suf in _candidate_suffixes()]


def list_available_timeframes(
    *,
    datadir: Path,
    pair: str,
    trading_mode: str,
    stake_currency: str | None,
) -> list[str]:
    prefix = _pair_prefix(pair=pair, trading_mode=trading_mode, stake_currency=stake_currency)
    out: set[str] = set()
    if trading_mode == "futures":
        root = datadir / "futures"
        patterns = [f"{prefix}-*-futures{suf}" for suf in _candidate_suffixes()]
        for pat in patterns:
            for p in root.glob(pat):
                name = p.name
                # {prefix}-{tf}-futures{ext}
                tf = name.removeprefix(prefix + "-")
                tf = tf.split("-futures", 1)[0]
                if tf:
                    out.add(tf)
    else:
        root = datadir
        patterns = [f"{prefix}-*{suf}" for suf in _candidate_suffixes()]
        for pat in patterns:
            for p in root.glob(pat):
                name = p.name
                # {prefix}-{tf}{ext}
                tf = name.removeprefix(prefix + "-")
                for suf in _candidate_suffixes():
                    if tf.endswith(suf):
                        tf = tf[: -len(suf)]
                        break
                if tf:
                    out.add(tf)
    return sorted(out)


def check_history_available(
    *,
    datadir: Path,
    pair: str,
    timeframe: str,
    trading_mode: str,
    stake_currency: str | None,
) -> DataAvailability:
    expected = expected_history_paths(
        datadir=datadir,
        pair=pair,
        timeframe=timeframe,
        trading_mode=trading_mode,
        stake_currency=stake_currency,
    )
    ok = any(p.exists() for p in expected)
    available = list_available_timeframes(datadir=datadir, pair=pair, trading_mode=trading_mode, stake_currency=stake_currency)
    return DataAvailability(
        ok=ok,
        trading_mode=trading_mode,
        datadir=datadir,
        pair=pair,
        timeframe=timeframe,
        expected_paths=expected,
        available_timeframes=available,
    )

