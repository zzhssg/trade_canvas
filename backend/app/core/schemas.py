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


class IngestCandlesClosedBatchRequest(BaseModel):
    series_id: str
    candles: list[CandleClosed] = Field(default_factory=list, min_length=1, max_length=20000)
    publish_ws: bool = False


class IngestCandlesClosedBatchResponse(BaseModel):
    ok: bool
    series_id: str
    count: int
    first_candle_time: int | None
    last_candle_time: int | None


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


class BacktestPairTimeframesResponse(BaseModel):
    pair: str
    trading_mode: str
    datadir: str
    available_timeframes: list[str]


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


class MarketBackfillStatusResponse(BaseModel):
    state: str
    progress_pct: float | None
    started_at: int | None
    updated_at: int | None
    reason: str | None = None
    note: str | None = None
    error: str | None = None
    recent: bool = False
    start_missing_seconds: int = 0
    start_missing_candles: int = 0
    current_missing_seconds: int = 0
    current_missing_candles: int = 0


class MarketHealthResponse(BaseModel):
    series_id: str
    timeframe_seconds: int
    now_time: int
    expected_latest_closed_time: int
    head_time: int | None
    lag_seconds: int | None
    missing_seconds: int | None
    missing_candles: int | None
    status: str
    status_reason: str
    backfill: MarketBackfillStatusResponse


class PlotLinePointV1(BaseModel):
    time: int = Field(..., description="Unix seconds (candle open time)")
    value: float


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


class FactorCatalogSubFeatureV1(BaseModel):
    key: str
    label: str
    default_visible: bool = True


class FactorCatalogItemV1(BaseModel):
    key: str
    label: str
    default_visible: bool = True
    sub_features: list[FactorCatalogSubFeatureV1] = Field(default_factory=list)


class GetFactorCatalogResponseV1(BaseModel):
    schema_version: int = 1
    factors: list[FactorCatalogItemV1] = Field(default_factory=list)


class GetFactorSlicesResponseV1(BaseModel):
    schema_version: int = 1
    series_id: str
    at_time: int
    candle_id: str | None
    factors: list[str] = Field(default_factory=list)
    snapshots: dict[str, FactorSliceV1] = Field(default_factory=dict)


class ReplayPrepareRequestV1(BaseModel):
    series_id: str = Field(..., min_length=1)
    to_time: int | None = Field(default=None, ge=0)
    window_candles: int | None = Field(default=None, ge=1, le=5000)


class ReplayPrepareResponseV1(BaseModel):
    ok: bool
    series_id: str
    requested_time: int
    aligned_time: int
    window_candles: int
    factor_head_time: int | None
    overlay_head_time: int | None
    computed: bool


class RepairOverlayRequestV1(BaseModel):
    series_id: str = Field(..., min_length=1)
    to_time: int | None = Field(default=None, ge=0)


class RepairOverlayResponseV1(BaseModel):
    ok: bool
    series_id: str
    requested_time: int
    aligned_time: int
    factor_head_time: int | None
    overlay_head_time: int | None
    refreshed: bool
    steps: list[str] = Field(default_factory=list)


class OverlayInstructionPatchItemV1(BaseModel):
    version_id: int
    instruction_id: str
    kind: str
    visible_time: int
    definition: dict[str, Any] = Field(default_factory=dict)


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


class WorldTimeV1(BaseModel):
    at_time: int = Field(..., ge=0, description="Requested time (unix seconds)")
    aligned_time: int = Field(..., ge=0, description="Aligned closed candle_time (floor)")
    candle_id: str = Field(..., min_length=1)


class WorldStateV1(BaseModel):
    schema_version: int = 1
    series_id: str
    time: WorldTimeV1
    factor_slices: GetFactorSlicesResponseV1
    draw_state: DrawDeltaV1


class WorldCursorV1(BaseModel):
    id: int = Field(0, ge=0)


class WorldDeltaRecordV1(BaseModel):
    id: int = Field(..., ge=0)
    series_id: str
    to_candle_id: str
    to_candle_time: int = Field(..., ge=0)
    draw_delta: DrawDeltaV1
    factor_slices: GetFactorSlicesResponseV1 | None = None


class WorldDeltaPollResponseV1(BaseModel):
    schema_version: int = 1
    series_id: str
    records: list[WorldDeltaRecordV1] = Field(default_factory=list)
    next_cursor: WorldCursorV1


# ============ Dev Panel / Worktree Management ============


class DevServiceState(BaseModel):
    running: bool
    port: int
    pid: int | None = None
    url: str | None = None


class DevServiceStatus(BaseModel):
    backend: DevServiceState
    frontend: DevServiceState


class DevWorktreeMetadata(BaseModel):
    description: str
    plan_path: str | None = None
    created_at: str = ""
    owner: str | None = None
    ports: dict[str, int] = Field(default_factory=dict)


class DevWorktreeInfo(BaseModel):
    id: str
    path: str
    branch: str
    commit: str
    is_detached: bool
    is_main: bool
    metadata: DevWorktreeMetadata | None = None
    services: DevServiceStatus | None = None


class DevWorktreeListResponse(BaseModel):
    worktrees: list[DevWorktreeInfo]


class DevCreateWorktreeRequest(BaseModel):
    branch: str = Field(..., min_length=1)
    description: str = Field(..., min_length=20)
    plan_path: str | None = None
    base_branch: str = "main"


class DevCreateWorktreeResponse(BaseModel):
    ok: bool
    worktree: DevWorktreeInfo | None = None
    error: str | None = None


class DevStartServicesRequest(BaseModel):
    backend_port: int | None = None
    frontend_port: int | None = None


class DevStartServicesResponse(BaseModel):
    ok: bool
    services: DevServiceStatus | None = None
    error: str | None = None


class DevStopServicesResponse(BaseModel):
    ok: bool
    error: str | None = None


class DevDeleteWorktreeRequest(BaseModel):
    force: bool = False


class DevDeleteWorktreeResponse(BaseModel):
    ok: bool
    error: str | None = None


class DevPortAllocationResponse(BaseModel):
    backend_port: int
    frontend_port: int


class DevUpdateMetadataRequest(BaseModel):
    description: str | None = None
    plan_path: str | None = None


class DevUpdateMetadataResponse(BaseModel):
    ok: bool
    metadata: DevWorktreeMetadata | None = None
    error: str | None = None
