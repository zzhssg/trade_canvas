from __future__ import annotations

from datetime import datetime, timezone

from trade_oracle.models import AnalysisResult, BaziSnapshot, Candle, StrategyMetrics
from trade_oracle.packages.bazi_factors.rules import LAYER_LABELS, score_factors


def _confidence_from_score(total_score: float) -> str:
    score_abs = abs(total_score)
    if score_abs >= 2.4:
        return "high"
    if score_abs >= 1.2:
        return "medium"
    return "low"


def _bias_from_score(total_score: float) -> str:
    if total_score > 0.6:
        return "bullish"
    if total_score < -0.6:
        return "bearish"
    return "neutral"


def _score_direction(score: float) -> str:
    if score > 0.35:
        return "bullish"
    if score < -0.35:
        return "bearish"
    return "neutral"


def _layer_attribution(bundle) -> dict:
    layers = []
    for layer in ("year", "month", "day"):
        score = float(bundle.layer_scores.get(layer, 0.0))
        layers.append(
            {
                "layer": layer,
                "label": LAYER_LABELS.get(layer, layer),
                "score": score,
                "direction": _score_direction(score),
            }
        )
    return {
        "day_master": bundle.day_master,
        "layers": layers,
    }


def _build_hist_note(
    *,
    daily_ret: float,
    total: float,
    bias: str,
    confidence: str,
    layer_attr: dict,
    layer_backtest: dict | None,
) -> str:
    layers = layer_attr.get("layers", [])
    dominant = max(layers, key=lambda x: abs(float(x.get("score", 0.0)))) if layers else None
    dominant_text = ""
    if dominant is not None:
        dominant_text = f"主导项={dominant['label']}({dominant['score']:+.2f})"

    segment_text = ""
    if layer_backtest:
        segments = layer_backtest.get("time_segments", [])
        if segments:
            recent = segments[-1]
            stg = recent.get("strategy", {})
            segment_text = (
                f"，最近分段={recent.get('label')} 胜率={float(stg.get('win_rate', 0.0)):.2%} "
                f"盈亏比={float(stg.get('reward_risk') or 0.0):.2f}"
            )

    base = f"最近一日收益={daily_ret:.4f}，总评分={total:.2f}，方向={bias}，置信度={confidence}"
    if dominant_text:
        base = f"{base}，{dominant_text}"
    return f"{base}{segment_text}。"


def build_analysis(
    *,
    series_id: str,
    candles: list[Candle],
    birth_bazi: BaziSnapshot,
    transit_bazi: BaziSnapshot,
    strategy_metrics: StrategyMetrics | None,
    layer_backtest: dict | None = None,
) -> AnalysisResult:
    bundle = score_factors(natal=birth_bazi, transit=transit_bazi)
    total = bundle.total
    bias = _bias_from_score(total)
    confidence = _confidence_from_score(total)

    last_close = candles[-1].close if candles else 0.0
    prev_close = candles[-2].close if len(candles) > 1 else last_close
    daily_ret = 0.0
    if prev_close > 0:
        daily_ret = (last_close - prev_close) / prev_close

    layer_attr = _layer_attribution(bundle)
    hist_note = _build_hist_note(
        daily_ret=daily_ret,
        total=total,
        bias=bias,
        confidence=confidence,
        layer_attr=layer_attr,
        layer_backtest=layer_backtest,
    )

    evidence = {
        "candles": {
            "count": len(candles),
            "first_time": candles[0].candle_time if candles else None,
            "last_time": candles[-1].candle_time if candles else None,
            "last_close": last_close,
        },
        "scoring": {
            "total_score": total,
            "school_scores": [
                {
                    "school": s.school,
                    "score": s.score,
                    "direction": s.direction,
                }
                for s in bundle.scores
            ],
        },
        "layer_attribution": layer_attr,
    }

    if strategy_metrics is not None:
        evidence["strategy"] = {
            "trades": strategy_metrics.trades,
            "win_rate": strategy_metrics.win_rate,
            "profit_factor": strategy_metrics.profit_factor,
            "reward_risk": strategy_metrics.reward_risk,
            "threshold": strategy_metrics.threshold,
            "windows": strategy_metrics.windows,
        }

    if layer_backtest is not None:
        evidence["layer_backtest"] = layer_backtest

    return AnalysisResult(
        series_id=series_id,
        generated_at_utc=datetime.now(timezone.utc),
        birth_bazi=birth_bazi,
        transit_bazi=transit_bazi,
        factor_scores=bundle.scores,
        total_score=total,
        bias=bias,
        confidence=confidence,
        historical_note=hist_note,
        strategy_metrics=strategy_metrics,
        evidence=evidence,
    )
