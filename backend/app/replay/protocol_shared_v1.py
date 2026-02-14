from __future__ import annotations

from pydantic import BaseModel, Field


class ReplayWindowRangeV1(BaseModel):
    series_id: str
    total_candles: int = Field(..., ge=0)
    from_candle_time: int = Field(..., ge=0)
    to_candle_time: int = Field(..., ge=0)
    window_size: int = Field(..., ge=1)
    snapshot_interval: int = Field(..., ge=1)


class ReplayPackageMetadataBaseV1(ReplayWindowRangeV1):
    schema_version: int = 1
    timeframe_s: int = Field(..., ge=1)
    preload_offset: int = Field(0, ge=0)
    idx_to_time: str = "windows[*].kline[idx].time"


class ReplayWindowBoundsV1(BaseModel):
    window_index: int = Field(..., ge=0)
    start_idx: int = Field(..., ge=0)
    end_idx: int = Field(..., ge=0)


class ReplayKlineBarBaseV1(BaseModel):
    time: int = Field(..., ge=0, description="Unix seconds (candle open time)")
    open: float
    high: float
    low: float
    close: float
    volume: float


class ReplayBuildResponseBaseV1(BaseModel):
    status: str = Field(..., description="building | done")
    job_id: str
    cache_key: str


class ReplayJobStatusBaseV1(BaseModel):
    status: str = Field(..., description="building | done | error")
    job_id: str
    error: str | None = None


class ReplayStatusResponseBaseV1(BaseModel):
    status: str = Field(..., description="building | done | error")
    job_id: str
    cache_key: str
    error: str | None = None
