from __future__ import annotations


def timeframe_to_seconds(timeframe: str) -> int:
    """
    Parse a minimal subset of ccxt/freqtrade-style timeframe strings.
    Examples: 1m, 5m, 1h, 4h, 1d.
    """
    timeframe = timeframe.strip()
    if not timeframe:
        raise ValueError("empty timeframe")

    unit = timeframe[-1]
    if unit not in ("m", "h", "d"):
        raise ValueError(f"unsupported timeframe unit: {unit!r}")

    try:
        n = int(timeframe[:-1])
    except ValueError as e:
        raise ValueError(f"invalid timeframe: {timeframe!r}") from e

    if n <= 0:
        raise ValueError(f"invalid timeframe: {timeframe!r}")

    if unit == "m":
        return n * 60
    if unit == "h":
        return n * 60 * 60
    return n * 24 * 60 * 60


def expected_latest_closed_time(*, now_time: int, timeframe_seconds: int) -> int:
    tf_s = max(1, int(timeframe_seconds))
    aligned = (int(now_time) // int(tf_s)) * int(tf_s)
    if aligned <= 0:
        return 0
    if aligned >= int(tf_s):
        return int(aligned - int(tf_s))
    return 0


def series_id_timeframe(series_id: str) -> str:
    parts = series_id.split(":")
    if len(parts) < 1:
        raise ValueError("invalid series_id")
    return parts[-1]
