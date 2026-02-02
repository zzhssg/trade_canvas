from __future__ import annotations

from typing import Any
from typing import Annotated

from pydantic import BaseModel, Field


class CandleClosed(BaseModel):
    candle_time: int = Field(..., description="Unix seconds (candle open time)")
    open: float
    high: float
    low: float
    close: float
    volume: float


class GetCandlesResponse(BaseModel):
    series_id: str
    server_head_time: int | None
    candles: list[CandleClosed]


class IngestCandleClosedRequest(BaseModel):
    series_id: str
    candle: CandleClosed


class IngestCandleClosedResponse(BaseModel):
    ok: bool
    series_id: str
    candle_time: int


class IngestCandleFormingRequest(BaseModel):
    series_id: str
    candle: CandleClosed


class IngestCandleFormingResponse(BaseModel):
    ok: bool
    series_id: str
    candle_time: int


class StrategyListResponse(BaseModel):
    strategies: list[str]


class BacktestRunRequest(BaseModel):
    strategy_name: str = Field(..., min_length=1)
    pair: str = Field(..., min_length=1)
    timeframe: str = Field(..., min_length=1)
    timerange: str | None = None


class BacktestRunResponse(BaseModel):
    ok: bool
    exit_code: int
    duration_ms: int
    command: list[str]
    stdout: str
    stderr: str


LimitQuery = Annotated[int, Field(ge=1, le=5000)]
SinceQuery = Annotated[int | None, Field(None, ge=0)]


class TopMarketItem(BaseModel):
    exchange: str
    market: str
    symbol: str
    symbol_id: str
    base_asset: str
    quote_asset: str
    last_price: float | None = None
    quote_volume: float | None = None
    price_change_percent: float | None = None


class TopMarketsResponse(BaseModel):
    exchange: str
    market: str
    quote_asset: str
    limit: int
    generated_at_ms: int
    cached: bool
    items: list[TopMarketItem]


class PlotLinePointV1(BaseModel):
    time: int = Field(..., description="Unix seconds (candle open time)")
    value: float


class OverlayEventV1(BaseModel):
    id: int
    kind: str
    candle_id: str
    candle_time: int
    payload: dict[str, Any] = Field(default_factory=dict)


class PlotCursorV1(BaseModel):
    candle_time: int | None = Field(default=None, description="Last known plot head candle_time")
    overlay_event_id: int | None = Field(default=None, description="Last seen overlay event id")


class PlotDeltaV1(BaseModel):
    schema_version: int = 1
    series_id: str
    to_candle_id: str | None
    to_candle_time: int | None
    lines: dict[str, list[PlotLinePointV1]] = Field(default_factory=dict)
    overlay_events: list[OverlayEventV1] = Field(default_factory=list)
    next_cursor: PlotCursorV1


class FactorMetaV1(BaseModel):
    series_id: str
    epoch: int = 0
    at_time: int
    candle_id: str
    factor_name: str


class FactorSliceV1(BaseModel):
    schema_version: int = 1
    history: dict[str, Any] = Field(default_factory=dict)
    head: dict[str, Any] = Field(default_factory=dict)
    meta: FactorMetaV1


class GetFactorSlicesResponseV1(BaseModel):
    schema_version: int = 1
    series_id: str
    at_time: int
    candle_id: str | None
    factors: list[str] = Field(default_factory=list)
    snapshots: dict[str, FactorSliceV1] = Field(default_factory=dict)


class OverlayCursorV1(BaseModel):
    version_id: int = Field(0, ge=0)


class OverlayInstructionPatchItemV1(BaseModel):
    version_id: int
    instruction_id: str
    kind: str
    visible_time: int
    definition: dict[str, Any] = Field(default_factory=dict)


class OverlayDeltaV1(BaseModel):
    schema_version: int = 1
    series_id: str
    to_candle_id: str | None
    to_candle_time: int | None
    active_ids: list[str] = Field(default_factory=list)
    instruction_catalog_patch: list[OverlayInstructionPatchItemV1] = Field(default_factory=list)
    next_cursor: OverlayCursorV1


TopMarketsLimitQuery = Annotated[int, Field(ge=1, le=200)]


class DrawCursorV1(BaseModel):
    version_id: int = Field(0, ge=0)
    point_time: int | None = Field(default=None, ge=0, description="Optional cursor for series_points (time-based)")


class DrawDeltaV1(BaseModel):
    schema_version: int = 1
    series_id: str
    to_candle_id: str | None
    to_candle_time: int | None
    active_ids: list[str] = Field(default_factory=list)
    instruction_catalog_patch: list[OverlayInstructionPatchItemV1] = Field(default_factory=list)
    series_points: dict[str, list[PlotLinePointV1]] = Field(default_factory=dict)
    next_cursor: DrawCursorV1
