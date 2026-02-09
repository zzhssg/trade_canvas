from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone


@dataclass(frozen=True)
class Candle:
    candle_time: int
    open: float
    high: float
    low: float
    close: float
    volume: float


@dataclass(frozen=True)
class GanzhiPillar:
    stem: str
    branch: str

    @property
    def text(self) -> str:
        return f"{self.stem}{self.branch}"


@dataclass(frozen=True)
class BaziSnapshot:
    source: str
    dt_utc: datetime
    year: GanzhiPillar
    month: GanzhiPillar
    day: GanzhiPillar
    hour: GanzhiPillar


@dataclass(frozen=True)
class AssetBirthRecord:
    symbol: str
    name: str
    birth_time_utc: datetime
    source_ref: str


@dataclass(frozen=True)
class FactorScore:
    school: str
    score: float
    direction: str
    reason: str


@dataclass(frozen=True)
class StrategyMetrics:
    trades: int
    win_rate: float
    profit_factor: float
    avg_win: float
    avg_loss: float
    expectancy: float
    reward_risk: float
    threshold: float | None = None
    windows: int = 0


@dataclass(frozen=True)
class AnalysisResult:
    series_id: str
    generated_at_utc: datetime
    birth_bazi: BaziSnapshot
    transit_bazi: BaziSnapshot
    factor_scores: list[FactorScore]
    total_score: float
    bias: str
    confidence: str
    historical_note: str
    strategy_metrics: StrategyMetrics | None
    evidence: dict = field(default_factory=dict)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)
