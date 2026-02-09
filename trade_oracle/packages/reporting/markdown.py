from __future__ import annotations

from datetime import datetime, timezone

from trade_oracle.models import AnalysisResult


def _fmt_ts(ts: int | None) -> str:
    if ts is None:
        return "N/A"
    return datetime.fromtimestamp(int(ts), tz=timezone.utc).date().isoformat()


def render_markdown(result: AnalysisResult) -> str:
    ts = result.generated_at_utc.astimezone(timezone.utc).isoformat()
    evidence = result.evidence or {}
    layer_attr = evidence.get("layer_attribution", {})
    layer_backtest = evidence.get("layer_backtest", {})

    lines: list[str] = [
        "# BTC 八字走势分析报告（MVP）",
        "",
        f"- 生成时间(UTC): {ts}",
        f"- 序列: `{result.series_id}`",
        f"- 方向判断: **{result.bias}**",
        f"- 置信度: **{result.confidence}**",
        "",
        "## 原局与流时",
        f"- BTC 原局（创世块）: 年{result.birth_bazi.year.text} 月{result.birth_bazi.month.text} 日{result.birth_bazi.day.text} 时{result.birth_bazi.hour.text}",
        f"- 当前流时: 年{result.transit_bazi.year.text} 月{result.transit_bazi.month.text} 日{result.transit_bazi.day.text} 时{result.transit_bazi.hour.text}",
        "",
        "## 流年/流月/流日分层归因",
    ]

    layers = layer_attr.get("layers", []) if isinstance(layer_attr, dict) else []
    if layers:
        lines.append(f"- 日主五行: {layer_attr.get('day_master', 'N/A')}")
        for item in layers:
            lines.append(
                f"- {item.get('label', item.get('layer', 'N/A'))}: {float(item.get('score', 0.0)):+.2f} ({item.get('direction', 'neutral')})"
            )
    else:
        lines.append("- 暂无分层归因数据")

    lines.extend(["", "## 三流派评分"])
    for score in result.factor_scores:
        lines.append(f"- {score.school}: {score.score:.2f} ({score.direction}) - {score.reason}")

    lines.extend(
        [
            "",
            "## 历史分段回测",
        ]
    )

    time_segments = layer_backtest.get("time_segments", []) if isinstance(layer_backtest, dict) else []
    if time_segments:
        for seg in time_segments:
            strategy = seg.get("strategy", {})
            lines.append(
                "- {label} [{start} ~ {end}] candles={candles} "
                "market={market:+.2%} strategy_wr={wr:.2%} strategy_rr={rr:.2f}".format(
                    label=seg.get("label", "N/A"),
                    start=_fmt_ts(seg.get("start_time")),
                    end=_fmt_ts(seg.get("end_time")),
                    candles=int(seg.get("candles", 0)),
                    market=float(seg.get("market_return", 0.0)),
                    wr=float(strategy.get("win_rate", 0.0)),
                    rr=float(strategy.get("reward_risk") or 0.0),
                )
            )
    else:
        lines.append("- 暂无分段回测数据")

    layer_perf = layer_backtest.get("layer_performance", {}) if isinstance(layer_backtest, dict) else {}
    if layer_perf:
        lines.append("- 分层策略表现：")
        for key in ("year", "month", "day"):
            item = layer_perf.get(key)
            if not item:
                continue
            lines.append(
                "  - {layer}: trades={trades} wr={wr:.2%} rr={rr:.2f} expectancy={exp:+.4f} bias={bias}".format(
                    layer=key,
                    trades=int(item.get("trades", 0)),
                    wr=float(item.get("win_rate", 0.0)),
                    rr=float(item.get("reward_risk") or 0.0),
                    exp=float(item.get("expectancy", 0.0)),
                    bias=item.get("direction_bias", "neutral"),
                )
            )

    lines.extend(
        [
            "",
            f"## 综合结论\n- 总评分: {result.total_score:.2f}",
            f"- 历史依据摘要: {result.historical_note}",
            "",
        ]
    )

    if result.strategy_metrics is not None:
        m = result.strategy_metrics
        lines.extend(
            [
                "## 策略统计（实验）",
                f"- 交易次数: {m.trades}",
                f"- 胜率: {m.win_rate:.2%}",
                f"- 盈亏比: {m.reward_risk:.2f}",
                f"- Profit Factor: {m.profit_factor:.2f}",
                f"- Walk-forward 窗口: {m.windows}",
                f"- 平均阈值: {m.threshold:.2f}" if m.threshold is not None else "- 平均阈值: N/A",
                "",
            ]
        )

    lines.extend(
        [
            "## 免责声明",
            "- 本报告仅用于研究与框架验证，不构成投资建议。",
            "",
        ]
    )
    return "\n".join(lines)
