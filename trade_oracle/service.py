from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timezone

from trade_oracle.config import OracleSettings
from trade_oracle.models import BaziSnapshot, Candle, StrategyMetrics
from trade_oracle.market_client import MarketClient
from trade_oracle.packages.asset_registry.registry import get_asset_birth
from trade_oracle.packages.calendar_engine.service import CalendarService
from trade_oracle.packages.reporting.markdown import render_markdown
from trade_oracle.packages.research_engine.analyzer import build_analysis
from trade_oracle.packages.research_engine.backtest import run_layer_segment_backtest, run_walk_forward_backtest


class OracleService:
    def __init__(self, settings: OracleSettings) -> None:
        self.settings = settings
        self.market = MarketClient(base_url=settings.market_api_base)
        self.calendar = CalendarService(
            enable_crosscheck=settings.enable_sx_crosscheck,
            enable_true_solar_time=settings.enable_true_solar_time,
            solar_longitude_deg=settings.solar_longitude_deg,
            solar_tz_offset_hours=settings.solar_tz_offset_hours,
            strict_calendar_lib=settings.strict_calendar_lib,
        )

    def analyze_current(self, *, series_id: str, symbol: str = "BTC") -> tuple[dict, str]:
        candles = self.market.fetch_candles(series_id=series_id, limit=self.settings.market_limit)
        birth = get_asset_birth(symbol)

        birth_bazi = self.calendar.convert_utc(birth.birth_time_utc)
        now_utc = datetime.now(timezone.utc)
        transit_bazi = self.calendar.convert_utc(now_utc)
        strategy_metrics = None
        if self.settings.enable_backtest:
            strategy_metrics = self._run_backtest(candles=candles, birth_bazi=birth_bazi)

        layer_backtest = run_layer_segment_backtest(
            candles=candles,
            natal=birth_bazi,
            calendar=self.calendar,
            fee_rate=self.settings.trade_fee_rate,
        )

        analysis = build_analysis(
            series_id=series_id,
            candles=candles,
            birth_bazi=birth_bazi,
            transit_bazi=transit_bazi,
            strategy_metrics=strategy_metrics,
            layer_backtest=layer_backtest,
        )

        payload = {
            "series_id": analysis.series_id,
            "generated_at_utc": analysis.generated_at_utc.isoformat(),
            "bias": analysis.bias,
            "confidence": analysis.confidence,
            "total_score": analysis.total_score,
            "factor_scores": [asdict(x) for x in analysis.factor_scores],
            "historical_note": analysis.historical_note,
            "birth_ref": birth.source_ref,
            "birth_time_utc": birth.birth_time_utc.isoformat(),
            "birth_bazi": {
                "source": analysis.birth_bazi.source,
                "year": analysis.birth_bazi.year.text,
                "month": analysis.birth_bazi.month.text,
                "day": analysis.birth_bazi.day.text,
                "hour": analysis.birth_bazi.hour.text,
            },
            "transit_bazi": {
                "source": analysis.transit_bazi.source,
                "year": analysis.transit_bazi.year.text,
                "month": analysis.transit_bazi.month.text,
                "day": analysis.transit_bazi.day.text,
                "hour": analysis.transit_bazi.hour.text,
            },
            "strategy_metrics": None if analysis.strategy_metrics is None else asdict(analysis.strategy_metrics),
            "evidence": analysis.evidence,
        }
        report_md = render_markdown(analysis)
        return payload, report_md

    def run_market_backtest(self, *, series_id: str, symbol: str = "BTC") -> dict:
        candles = self.market.fetch_candles(series_id=series_id, limit=self.settings.market_limit)
        birth = get_asset_birth(symbol)
        birth_bazi = self.calendar.convert_utc(birth.birth_time_utc)
        metrics = self._run_backtest(candles=candles, birth_bazi=birth_bazi)
        passed = bool(
            metrics.trades > 0
            and metrics.win_rate >= self.settings.target_win_rate
            and metrics.reward_risk >= self.settings.target_reward_risk
        )
        return {
            "series_id": series_id,
            "symbol": symbol,
            "generated_at_utc": datetime.now(timezone.utc).isoformat(),
            "target": {
                "win_rate": self.settings.target_win_rate,
                "reward_risk": self.settings.target_reward_risk,
            },
            "settings": {
                "market_limit": self.settings.market_limit,
                "wf_train_size": self.settings.wf_train_size,
                "wf_test_size": self.settings.wf_test_size,
                "trade_fee_rate": self.settings.trade_fee_rate,
            },
            "metrics": asdict(metrics),
            "passed": passed,
        }

    def _run_backtest(self, *, candles: list[Candle], birth_bazi: BaziSnapshot) -> StrategyMetrics:
        return run_walk_forward_backtest(
            candles=candles,
            natal=birth_bazi,
            calendar=self.calendar,
            train_size=self.settings.wf_train_size,
            test_size=self.settings.wf_test_size,
            fee_rate=self.settings.trade_fee_rate,
        )
