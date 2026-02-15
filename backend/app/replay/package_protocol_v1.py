from __future__ import annotations

from pydantic import BaseModel, Field

from ..overlay.replay_protocol_v1 import OverlayReplayCheckpointV1, OverlayReplayDiffV1
from ..core.schemas import FactorSliceV1, OverlayInstructionPatchItemV1
from .protocol_shared_v1 import (
    ReplayBuildResponseBaseV1,
    ReplayJobStatusBaseV1,
    ReplayKlineBarBaseV1,
    ReplayPackageMetadataBaseV1,
    ReplayStatusResponseBaseV1,
    ReplayWindowBoundsV1,
)


class ReplayCoverageV1(BaseModel):
    required_candles: int = Field(..., ge=1)
    candles_ready: int = Field(..., ge=0)
    from_time: int | None = Field(default=None, ge=0)
    to_time: int | None = Field(default=None, ge=0)


class ReplayFactorSchemaV1(BaseModel):
    factor_name: str
    history_keys: list[str] = Field(default_factory=list)
    head_keys: list[str] = Field(default_factory=list)


class ReplayPackageMetadataV1(ReplayPackageMetadataBaseV1):
    factor_schema: list[ReplayFactorSchemaV1] = Field(default_factory=list)

class ReplayEnsureCoverageRequestV1(BaseModel):
    series_id: str = Field(..., min_length=1)
    target_candles: int = Field(2000, ge=1, le=5000)
    to_time: int | None = Field(default=None, ge=0)


class ReplayEnsureCoverageResponseV1(ReplayJobStatusBaseV1):
    pass


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


class ReplayBuildResponseV1(ReplayBuildResponseBaseV1):
    pass


class ReplayKlineBarV1(ReplayKlineBarBaseV1):
    pass


class ReplayWindowV1(ReplayWindowBoundsV1):
    kline: list[ReplayKlineBarV1] = Field(default_factory=list)
    draw_catalog_base: list[OverlayInstructionPatchItemV1] = Field(default_factory=list)
    draw_catalog_patch: list[OverlayInstructionPatchItemV1] = Field(default_factory=list)
    draw_active_checkpoints: list[OverlayReplayCheckpointV1] = Field(default_factory=list)
    draw_active_diffs: list[OverlayReplayDiffV1] = Field(default_factory=list)


class ReplayFactorSnapshotV1(BaseModel):
    factor_name: str
    candle_time: int = Field(..., ge=0)
    snapshot: FactorSliceV1


class ReplayWindowResponseV1(BaseModel):
    job_id: str
    window: ReplayWindowV1
    factor_snapshots: list[ReplayFactorSnapshotV1] = Field(default_factory=list)


class ReplayStatusResponseV1(ReplayStatusResponseBaseV1):
    metadata: ReplayPackageMetadataV1 | None = None
    preload_window: ReplayWindowV1 | None = None
