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
