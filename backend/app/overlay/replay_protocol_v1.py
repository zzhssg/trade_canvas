from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from ..core.schemas import OverlayInstructionPatchItemV1
from ..replay.protocol_shared_v1 import (
    ReplayBuildResponseBaseV1,
    ReplayKlineBarBaseV1,
    ReplayPackageMetadataBaseV1,
    ReplayStatusResponseBaseV1,
    ReplayWindowBoundsV1,
    ReplayWindowRangeV1,
)


class OverlayReplayKlineBarV1(ReplayKlineBarBaseV1):
    """
    Replay K-line bar used by the frontend chart.

    NOTE:
    - Use `time` (not candle_time) to match lightweight-charts conventions.
    - `time` is unix seconds (candle open time), always aligned to closed candles.
    """

class OverlayReplayCheckpointV1(BaseModel):
    at_idx: int = Field(..., ge=0)
    active_ids: list[str] = Field(default_factory=list)


class OverlayReplayDiffV1(BaseModel):
    at_idx: int = Field(..., ge=0)
    add_ids: list[str] = Field(default_factory=list)
    remove_ids: list[str] = Field(default_factory=list)


class OverlayReplayWindowMetaV1(BaseModel):
    window_index: int = Field(..., ge=0)
    start_idx: int = Field(..., ge=0)
    end_idx: int = Field(..., ge=0, description="Exclusive end index")
    start_time: int = Field(..., ge=0)
    end_time: int = Field(..., ge=0)


class OverlayReplayDeltaMetaV1(ReplayWindowRangeV1):
    schema_version: int = 1
    windows: list[OverlayReplayWindowMetaV1] = Field(default_factory=list)
    overlay_store_last_version_id: int = Field(0, ge=0)


class OverlayReplayPackageMetadataV1(ReplayPackageMetadataBaseV1):
    pass


class OverlayReplayWindowV1(ReplayWindowBoundsV1):
    end_idx: int = Field(..., ge=0, description="Exclusive end index")

    # K-line slice for this window (used by the frontend as the "source of truth" bars).
    kline: list[OverlayReplayKlineBarV1] = Field(default_factory=list)

    # Catalog rebuild strategy (window-independent):
    # - catalog_base: full snapshot at window start_time
    # - catalog_patch: versions within this window (apply by visible_time)
    catalog_base: list[OverlayInstructionPatchItemV1] = Field(default_factory=list)
    catalog_patch: list[OverlayInstructionPatchItemV1] = Field(default_factory=list)

    # Active set rebuild (window-independent):
    # - checkpoints: full active_ids snapshots (always includes one at start_idx)
    # - diffs: add/remove deltas (apply in ascending at_idx order)
    checkpoints: list[OverlayReplayCheckpointV1] = Field(default_factory=list)
    diffs: list[OverlayReplayDiffV1] = Field(default_factory=list)

    # Reserved for future (event navigation, explain panel, etc.).
    event_catalog: dict[str, Any] | None = None


class OverlayReplayDeltaPackageV1(BaseModel):
    schema_version: int = 1
    metadata: OverlayReplayPackageMetadataV1
    delta_meta: OverlayReplayDeltaMetaV1

    # Full windows (used for disk cache; API serves slices via /window).
    windows: list[OverlayReplayWindowV1] = Field(default_factory=list)


class ReplayOverlayPackageBuildRequestV1(BaseModel):
    series_id: str = Field(..., min_length=1)
    to_time: int | None = Field(default=None, ge=0, description="Optional upper-bound time (unix seconds)")
    window_candles: int | None = Field(default=None, ge=1, le=2000)
    window_size: int | None = Field(default=None, ge=1, le=2000)
    snapshot_interval: int | None = Field(default=None, ge=1, le=200)


class ReplayOverlayPackageBuildResponseV1(ReplayBuildResponseBaseV1):
    pass


class ReplayOverlayPackageStatusResponseV1(ReplayStatusResponseBaseV1):
    delta_meta: OverlayReplayDeltaMetaV1 | None = None
    # Included only when include_delta_package=1 (first load optimization).
    kline: list[OverlayReplayKlineBarV1] | None = None
    preload_window: OverlayReplayWindowV1 | None = None


class ReplayOverlayPackageWindowResponseV1(BaseModel):
    job_id: str
    window: OverlayReplayWindowV1
