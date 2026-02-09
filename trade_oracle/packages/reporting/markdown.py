from __future__ import annotations

from datetime import timezone

from trade_oracle.models import AnalysisResult


def render_markdown(result: AnalysisResult) -> str:
    ts = result.generated_at_utc.astimezone(timezone.utc).isoformat()
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
        "## 三流派评分",
    ]

    for score in result.factor_scores:
        lines.append(f"- {score.school}: {score.score:.2f} ({score.direction}) - {score.reason}")

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
