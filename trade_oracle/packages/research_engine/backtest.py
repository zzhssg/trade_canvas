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
