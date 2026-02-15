import type { components } from "./openapi";

export type CandleClosed = components["schemas"]["CandleClosed"];
export type GetCandlesResponse = components["schemas"]["GetCandlesResponse"];

export type PlotLinePointV1 = components["schemas"]["PlotLinePointV1"];

export type OverlayInstructionPatchItemV1 = components["schemas"]["OverlayInstructionPatchItemV1"];

export type DrawCursorV1 = components["schemas"]["DrawCursorV1"];
export type DrawDeltaV1 = components["schemas"]["DrawDeltaV1"];

export type FactorMetaV1 = components["schemas"]["FactorMetaV1"];
export type FactorSliceV1 = components["schemas"]["FactorSliceV1"];
export type GetFactorSlicesResponseV1 = components["schemas"]["GetFactorSlicesResponseV1-Output"];

export type ReplayBuildRequestV1 = components["schemas"]["ReplayBuildRequestV1"];
export type ReplayBuildResponseV1 = components["schemas"]["ReplayBuildResponseV1"];
export type ReplayCoverageStatusResponseV1 = components["schemas"]["ReplayCoverageStatusResponseV1"];
export type ReplayCoverageV1 = {
  required_candles: number;
  candles_ready: number;
  from_time: number | null;
  to_time: number | null;
};
export type ReplayEnsureCoverageRequestV1 = components["schemas"]["ReplayEnsureCoverageRequestV1"];
export type ReplayEnsureCoverageResponseV1 = components["schemas"]["ReplayEnsureCoverageResponseV1"];
export type ReplayFactorSchemaV1 = components["schemas"]["ReplayFactorSchemaV1"];
export type ReplayFactorSnapshotV1 = components["schemas"]["ReplayFactorSnapshotV1-Output"];
export type ReplayKlineBarV1 = components["schemas"]["ReplayKlineBarV1"];
export type ReplayPackageMetadataV1 = components["schemas"]["ReplayPackageMetadataV1"];
export type ReplayStatusResponseV1 = components["schemas"]["ReplayStatusResponseV1"];
export type ReplayWindowResponseV1 = components["schemas"]["ReplayWindowResponseV1"];
export type ReplayWindowV1 = components["schemas"]["ReplayWindowV1"];

export type TopMarketItem = components["schemas"]["TopMarketItem"];
export type TopMarketsResponse = components["schemas"]["TopMarketsResponse"];

export type WorldTimeV1 = components["schemas"]["WorldTimeV1"];
export type WorldStateV1 = components["schemas"]["WorldStateV1"];
export type WorldCursorV1 = components["schemas"]["WorldCursorV1"];
export type WorldDeltaRecordV1 = components["schemas"]["WorldDeltaRecordV1-Output"];
export type WorldDeltaPollResponseV1 = components["schemas"]["WorldDeltaPollResponseV1"];
