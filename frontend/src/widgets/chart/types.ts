import type { UTCTimestamp } from "lightweight-charts";

import type {
  CandleClosed as ApiCandleClosed,
  DrawCursorV1 as ApiDrawCursorV1,
  DrawDeltaV1 as ApiDrawDeltaV1,
  FactorMetaV1 as ApiFactorMetaV1,
  FactorSliceV1 as ApiFactorSliceV1,
  GetCandlesResponse as ApiGetCandlesResponse,
  GetFactorSlicesResponseV1 as ApiGetFactorSlicesResponseV1,
  OverlayInstructionPatchItemV1 as ApiOverlayInstructionPatchItemV1,
  PlotLinePointV1 as ApiPlotLinePointV1,
  ReplayBuildRequestV1 as ApiReplayBuildRequestV1,
  ReplayBuildResponseV1 as ApiReplayBuildResponseV1,
  ReplayCoverageStatusResponseV1 as ApiReplayCoverageStatusResponseV1,
  ReplayCoverageV1 as ApiReplayCoverageV1,
  ReplayEnsureCoverageRequestV1 as ApiReplayEnsureCoverageRequestV1,
  ReplayEnsureCoverageResponseV1 as ApiReplayEnsureCoverageResponseV1,
  ReplayFactorHeadSnapshotV1 as ApiReplayFactorHeadSnapshotV1,
  ReplayHistoryDeltaV1 as ApiReplayHistoryDeltaV1,
  ReplayHistoryEventV1 as ApiReplayHistoryEventV1,
  ReplayKlineBarV1 as ApiReplayKlineBarV1,
  ReplayPackageMetadataV1 as ApiReplayPackageMetadataV1,
  ReplayReadOnlyResponseV1 as ApiReplayReadOnlyResponseV1,
  ReplayStatusResponseV1 as ApiReplayStatusResponseV1,
  ReplayWindowResponseV1 as ApiReplayWindowResponseV1,
  ReplayWindowV1 as ApiReplayWindowV1,
  WorldCursorV1 as ApiWorldCursorV1,
  WorldDeltaPollResponseV1 as ApiWorldDeltaPollResponseV1,
  WorldDeltaRecordV1 as ApiWorldDeltaRecordV1,
  WorldStateV1 as ApiWorldStateV1,
  WorldTimeV1 as ApiWorldTimeV1
} from "../../contracts/api";

export type Candle = {
  time: UTCTimestamp;
  open: number;
  high: number;
  low: number;
  close: number;
};

export type CandleClosed = ApiCandleClosed;
export type GetCandlesResponse = ApiGetCandlesResponse;

export type FactorMetaV1 = ApiFactorMetaV1;
export type FactorSliceV1 = ApiFactorSliceV1;
export type GetFactorSlicesResponseV1 = ApiGetFactorSlicesResponseV1;

export type PlotLinePointV1 = ApiPlotLinePointV1;
export type OverlayInstructionPatchItemV1 = ApiOverlayInstructionPatchItemV1;

export type DrawCursorV1 = ApiDrawCursorV1;
export type DrawDeltaV1 = ApiDrawDeltaV1;

export type ReplayBuildRequestV1 = ApiReplayBuildRequestV1;
export type ReplayBuildResponseV1 = ApiReplayBuildResponseV1;
export type ReplayCoverageStatusResponseV1 = ApiReplayCoverageStatusResponseV1;
export type ReplayCoverageV1 = ApiReplayCoverageV1;
export type ReplayEnsureCoverageRequestV1 = ApiReplayEnsureCoverageRequestV1;
export type ReplayEnsureCoverageResponseV1 = ApiReplayEnsureCoverageResponseV1;
export type ReplayFactorHeadSnapshotV1 = ApiReplayFactorHeadSnapshotV1;
export type ReplayHistoryDeltaV1 = ApiReplayHistoryDeltaV1;
export type ReplayHistoryEventV1 = ApiReplayHistoryEventV1;
export type ReplayKlineBarV1 = ApiReplayKlineBarV1;
export type ReplayPackageMetadataV1 = ApiReplayPackageMetadataV1;
export type ReplayReadOnlyResponseV1 = ApiReplayReadOnlyResponseV1;
export type ReplayStatusResponseV1 = ApiReplayStatusResponseV1;
export type ReplayWindowResponseV1 = ApiReplayWindowResponseV1;
export type ReplayWindowV1 = ApiReplayWindowV1;

// Shared shape ChartView can apply regardless of endpoint (overlay/draw).
export type OverlayLikeDeltaV1 = {
  active_ids: string[];
  instruction_catalog_patch: OverlayInstructionPatchItemV1[];
  next_cursor: { version_id: number };
};

export type WorldTimeV1 = ApiWorldTimeV1;
export type WorldStateV1 = ApiWorldStateV1;
export type WorldCursorV1 = ApiWorldCursorV1;
export type WorldDeltaRecordV1 = ApiWorldDeltaRecordV1;
export type WorldDeltaPollResponseV1 = ApiWorldDeltaPollResponseV1;
