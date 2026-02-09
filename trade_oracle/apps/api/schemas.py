from __future__ import annotations

from pydantic import BaseModel, Field


class AnalyzeCurrentResponse(BaseModel):
    series_id: str
    generated_at_utc: str
    bias: str
    confidence: str
    total_score: float
    historical_note: str
    report_markdown: str = Field(..., description="Rendered report markdown")
    evidence: dict
