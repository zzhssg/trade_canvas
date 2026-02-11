from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from .schemas import OverlayInstructionPatchItemV1
from .overlay_replay_protocol_v1 import OverlayReplayCheckpointV1, OverlayReplayDiffV1


class ReplayCoverageV1(BaseModel):
    required_candles: int = Field(..., ge=1)
    candles_ready: int = Field(..., ge=0)
    from_time: int | None = Field(default=None, ge=0)
    to_time: int | None = Field(default=None, ge=0)


class ReplayPackageMetadataV1(BaseModel):
    schema_version: int = 1
    series_id: str
    timeframe_s: int = Field(..., ge=1)
    total_candles: int = Field(..., ge=0)
    from_candle_time: int = Field(..., ge=0)
    to_candle_time: int = Field(..., ge=0)
    window_size: int = Field(..., ge=1)
    snapshot_interval: int = Field(..., ge=1)
    preload_offset: int = Field(0, ge=0)
    idx_to_time: str = "replay_kline_bars.candle_time"

class ReplayEnsureCoverageRequestV1(BaseModel):
    series_id: str = Field(..., min_length=1)
    target_candles: int = Field(2000, ge=1, le=5000)
    to_time: int | None = Field(default=None, ge=0)


class ReplayEnsureCoverageResponseV1(BaseModel):
    status: str = Field(..., description="building | done | error")
    job_id: str
    error: str | None = None


class ReplayCoverageStatusResponseV1(BaseModel):
    status: str = Field(..., description="building | done | error")
    job_id: str
    candles_ready: int = Field(..., ge=0)
    required_candles: int = Field(..., ge=1)
    head_time: int | None = Field(default=None, ge=0)
    error: str | None = None


class ReplayBuildRequestV1(BaseModel):
    series_id: str = Field(..., min_length=1)
    to_time: int | None = Field(default=None, ge=0)
    window_candles: int | None = Field(default=None, ge=1, le=5000)
    window_size: int | None = Field(default=None, ge=1, le=2000)
    snapshot_interval: int | None = Field(default=None, ge=1, le=200)


class ReplayBuildResponseV1(BaseModel):
    status: str = Field(..., description="building | done")
    job_id: str
    cache_key: str


class ReplayKlineBarV1(BaseModel):
    time: int = Field(..., ge=0, description="Unix seconds (candle open time)")
    open: float
    high: float
    low: float
    close: float
    volume: float


class ReplayWindowV1(BaseModel):
    window_index: int = Field(..., ge=0)
    start_idx: int = Field(..., ge=0)
    end_idx: int = Field(..., ge=0)
    kline: list[ReplayKlineBarV1] = Field(default_factory=list)
    draw_catalog_base: list[OverlayInstructionPatchItemV1] = Field(default_factory=list)
    draw_catalog_patch: list[OverlayInstructionPatchItemV1] = Field(default_factory=list)
    draw_active_checkpoints: list[OverlayReplayCheckpointV1] = Field(default_factory=list)
    draw_active_diffs: list[OverlayReplayDiffV1] = Field(default_factory=list)


class ReplayHistoryEventV1(BaseModel):
    event_id: int = Field(..., ge=0)
    factor_name: str
    candle_time: int = Field(..., ge=0)
    kind: str
    event_key: str
    payload: dict[str, Any] = Field(default_factory=dict)


class ReplayHistoryDeltaV1(BaseModel):
    idx: int = Field(..., ge=0)
    from_event_id: int = Field(..., ge=0)
    to_event_id: int = Field(..., ge=0)


class ReplayFactorHeadSnapshotV1(BaseModel):
    factor_name: str
    candle_time: int = Field(..., ge=0)
    seq: int = Field(..., ge=0)
    head: dict[str, Any] = Field(default_factory=dict)


class ReplayWindowResponseV1(BaseModel):
    job_id: str
    window: ReplayWindowV1
    factor_head_snapshots: list[ReplayFactorHeadSnapshotV1] = Field(default_factory=list)
    history_deltas: list[ReplayHistoryDeltaV1] = Field(default_factory=list)


class ReplayStatusResponseV1(BaseModel):
    status: str = Field(..., description="building | done | error")
    job_id: str
    cache_key: str
    error: str | None = None
    metadata: ReplayPackageMetadataV1 | None = None
    preload_window: ReplayWindowV1 | None = None
    history_events: list[ReplayHistoryEventV1] | None = None
