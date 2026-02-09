from __future__ import annotations

from datetime import datetime, timezone
from typing import Protocol

from trade_oracle.models import BaziSnapshot, Candle, StrategyMetrics
from trade_oracle.packages.bazi_factors.rules import score_factors

from .walk_forward import build_daily_windows


class CalendarLike(Protocol):
    def convert_utc(self, dt_utc: datetime) -> BaziSnapshot:
        ...


def _empty_metrics(*, threshold: float | None = None, windows: int = 0) -> StrategyMetrics:
    return StrategyMetrics(
        trades=0,
        win_rate=0.0,
        profit_factor=0.0,
        avg_win=0.0,
        avg_loss=0.0,
        expectancy=0.0,
        reward_risk=0.0,
        threshold=threshold,
        windows=windows,
    )


def _metrics_from_returns(returns: list[float], *, threshold: float | None, windows: int) -> StrategyMetrics:
    if not returns:
        return _empty_metrics(threshold=threshold, windows=windows)

    wins = [r for r in returns if r > 0]
    losses = [r for r in returns if r <= 0]
    trades = len(returns)

    gross_profit = sum(wins)
    gross_loss = abs(sum(losses))
    avg_win = gross_profit / len(wins) if wins else 0.0
    avg_loss = abs(sum(losses) / len(losses)) if losses else 0.0
    profit_factor = gross_profit / gross_loss if gross_loss > 1e-12 else float("inf")
    reward_risk = avg_win / avg_loss if avg_loss > 1e-12 else float("inf")

    return StrategyMetrics(
        trades=trades,
        win_rate=len(wins) / trades,
        profit_factor=profit_factor,
        avg_win=avg_win,
        avg_loss=avg_loss,
        expectancy=sum(returns) / trades,
        reward_risk=reward_risk,
        threshold=threshold,
        windows=windows,
    )


def _build_scores(*, candles: list[Candle], natal: BaziSnapshot, calendar: CalendarLike) -> list[float]:
    scores: list[float] = []
    for candle in candles:
        dt_utc = datetime.fromtimestamp(int(candle.candle_time), tz=timezone.utc)
        transit = calendar.convert_utc(dt_utc)
        bundle = score_factors(natal=natal, transit=transit)
        scores.append(bundle.total)
    return scores


def _build_scores_and_layers(
    *, candles: list[Candle], natal: BaziSnapshot, calendar: CalendarLike
) -> tuple[list[float], dict[str, list[float]]]:
    total_scores: list[float] = []
    layer_scores: dict[str, list[float]] = {"year": [], "month": [], "day": []}
    for candle in candles:
        dt_utc = datetime.fromtimestamp(int(candle.candle_time), tz=timezone.utc)
        transit = calendar.convert_utc(dt_utc)
        bundle = score_factors(natal=natal, transit=transit)
        total_scores.append(bundle.total)
        for layer in layer_scores:
            layer_scores[layer].append(float(bundle.layer_scores.get(layer, 0.0)))
    return total_scores, layer_scores


def _returns_for_range(
    *,
    closes: list[float],
    scores: list[float],
    threshold: float,
    start_idx: int,
    end_idx: int,
    fee_rate: float,
) -> list[float]:
    out: list[float] = []
    if end_idx - start_idx < 2:
        return out
    for idx in range(start_idx, end_idx - 1):
        close_now = closes[idx]
        close_next = closes[idx + 1]
        if close_now <= 0:
            continue
        signal = 0
        if scores[idx] > threshold:
            signal = 1
        elif scores[idx] < -threshold:
            signal = -1
        if signal == 0:
            continue
        gross_ret = (close_next - close_now) / close_now
        net_ret = signal * gross_ret - fee_rate
        out.append(net_ret)
    return out


def _safe_num(value: float) -> float | None:
    if value == float("inf") or value == float("-inf"):
        return None
    return float(value)


def _metrics_to_dict(m: StrategyMetrics) -> dict:
    return {
        "trades": int(m.trades),
        "win_rate": float(m.win_rate),
        "profit_factor": _safe_num(m.profit_factor),
        "reward_risk": _safe_num(m.reward_risk),
        "expectancy": float(m.expectancy),
        "avg_win": float(m.avg_win),
        "avg_loss": float(m.avg_loss),
        "threshold": None if m.threshold is None else float(m.threshold),
        "windows": int(m.windows),
    }


def _segment_ranges(total: int) -> list[tuple[str, int, int]]:
    if total < 3:
        return []
    cut1 = max(1, total // 3)
    cut2 = max(cut1 + 1, (total * 2) // 3)
    cut2 = min(cut2, total - 1)
    return [
        ("early", 0, cut1),
        ("mid", cut1, cut2),
        ("recent", cut2, total),
    ]


def run_layer_segment_backtest(
    *,
    candles: list[Candle],
    natal: BaziSnapshot,
    calendar: CalendarLike,
    fee_rate: float = 0.0008,
    layer_threshold: float = 0.35,
    segment_threshold: float = 0.6,
) -> dict:
    if len(candles) < 30:
        return {
            "layer_performance": {},
            "time_segments": [],
            "config": {
                "layer_threshold": layer_threshold,
                "segment_threshold": segment_threshold,
            },
        }

    closes = [float(c.close) for c in candles]
    total_scores, layer_scores = _build_scores_and_layers(candles=candles, natal=natal, calendar=calendar)

    layer_perf: dict[str, dict] = {}
    for layer, scores in layer_scores.items():
        returns = _returns_for_range(
            closes=closes,
            scores=scores,
            threshold=layer_threshold,
            start_idx=0,
            end_idx=len(candles),
            fee_rate=fee_rate,
        )
        metrics = _metrics_from_returns(returns, threshold=layer_threshold, windows=1)
        layer_perf[layer] = {
            **_metrics_to_dict(metrics),
            "direction_bias": "bullish" if metrics.expectancy > 0 else ("bearish" if metrics.expectancy < 0 else "neutral"),
        }

    segments: list[dict] = []
    for label, start_idx, end_idx in _segment_ranges(len(candles)):
        returns = _returns_for_range(
            closes=closes,
            scores=total_scores,
            threshold=segment_threshold,
            start_idx=start_idx,
            end_idx=end_idx,
            fee_rate=fee_rate,
        )
        metrics = _metrics_from_returns(returns, threshold=segment_threshold, windows=1)

        start_close = closes[start_idx]
        end_close = closes[end_idx - 1]
        market_return = 0.0 if start_close <= 0 else (end_close - start_close) / start_close

        segments.append(
            {
                "label": label,
                "start_time": int(candles[start_idx].candle_time),
                "end_time": int(candles[end_idx - 1].candle_time),
                "candles": int(end_idx - start_idx),
                "market_return": float(market_return),
                "strategy": _metrics_to_dict(metrics),
            }
        )

    return {
        "layer_performance": layer_perf,
        "time_segments": segments,
        "config": {
            "layer_threshold": layer_threshold,
            "segment_threshold": segment_threshold,
        },
    }


def run_walk_forward_backtest(
    *,
    candles: list[Candle],
    natal: BaziSnapshot,
    calendar: CalendarLike,
    train_size: int = 90,
    test_size: int = 30,
    fee_rate: float = 0.0008,
) -> StrategyMetrics:
    if len(candles) < max(30, train_size + test_size):
        return _empty_metrics()

    windows = build_daily_windows(candles, train_size=train_size, test_size=test_size)
    if not windows:
        return _empty_metrics()

    closes = [float(c.close) for c in candles]
    scores = _build_scores(candles=candles, natal=natal, calendar=calendar)

    threshold_grid = [0.4, 0.6, 0.8, 1.0, 1.2, 1.4]
    all_test_returns: list[float] = []
    selected_thresholds: list[float] = []

    for w in windows:
        best_threshold = threshold_grid[0]
        best_metrics = _empty_metrics(threshold=best_threshold, windows=1)

        for th in threshold_grid:
            train_returns = _returns_for_range(
                closes=closes,
                scores=scores,
                threshold=th,
                start_idx=w.train_start_idx,
                end_idx=w.train_end_idx + 1,
                fee_rate=fee_rate,
            )
            cur = _metrics_from_returns(train_returns, threshold=th, windows=1)
            cur_pf = cur.profit_factor if cur.profit_factor != float("inf") else 9999.0
            best_pf = best_metrics.profit_factor if best_metrics.profit_factor != float("inf") else 9999.0
            if (cur_pf, cur.expectancy, cur.win_rate) > (best_pf, best_metrics.expectancy, best_metrics.win_rate):
                best_metrics = cur
                best_threshold = th

        selected_thresholds.append(best_threshold)
        test_returns = _returns_for_range(
            closes=closes,
            scores=scores,
            threshold=best_threshold,
            start_idx=w.test_start_idx,
            end_idx=w.test_end_idx + 1,
            fee_rate=fee_rate,
        )
        all_test_returns.extend(test_returns)

    avg_threshold = sum(selected_thresholds) / len(selected_thresholds)
    return _metrics_from_returns(all_test_returns, threshold=avg_threshold, windows=len(windows))
