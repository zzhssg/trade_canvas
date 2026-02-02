import type { UTCTimestamp } from "lightweight-charts";

import type {
  CandleClosed as ApiCandleClosed,
  FactorMetaV1 as ApiFactorMetaV1,
  FactorSliceV1 as ApiFactorSliceV1,
  GetCandlesResponse as ApiGetCandlesResponse,
  GetFactorSlicesResponseV1 as ApiGetFactorSlicesResponseV1,
  OverlayEventV1 as ApiOverlayEventV1,
  PlotCursorV1 as ApiPlotCursorV1,
  PlotDeltaV1 as ApiPlotDeltaV1
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
export type OverlayEventV1 = ApiOverlayEventV1;
export type PlotCursorV1 = ApiPlotCursorV1;
export type PlotDeltaV1 = ApiPlotDeltaV1;

export type FactorMetaV1 = ApiFactorMetaV1;
export type FactorSliceV1 = ApiFactorSliceV1;
export type GetFactorSlicesResponseV1 = ApiGetFactorSlicesResponseV1;

// NOTE: Overlay delta types are defined locally for now because the repo's OpenAPI TS
// types may lag behind backend additions. Keep these in sync with backend/app/schemas.py.
export type OverlayCursorV1 = {
  version_id: number;
};

export type OverlayInstructionPatchItemV1 = {
  version_id: number;
  instruction_id: string;
  kind: string;
  visible_time: number;
  definition: Record<string, unknown>;
};

export type OverlayDeltaV1 = {
  schema_version: number;
  series_id: string;
  to_candle_id: string | null;
  to_candle_time: number | null;
  active_ids: string[];
  instruction_catalog_patch: OverlayInstructionPatchItemV1[];
  next_cursor: OverlayCursorV1;
};

// NOTE: Draw delta types are defined locally for now because the repo's OpenAPI TS
// types may lag behind backend additions. Keep these in sync with backend/app/schemas.py.
export type DrawCursorV1 = {
  version_id: number;
  point_time?: number | null;
};

export type DrawSeriesPointV1 = {
  time: number;
  value: number;
};

export type DrawDeltaV1 = {
  schema_version: number;
  series_id: string;
  to_candle_id: string | null;
  to_candle_time: number | null;
  active_ids: string[];
  instruction_catalog_patch: OverlayInstructionPatchItemV1[];
  series_points: Record<string, DrawSeriesPointV1[]>;
  next_cursor: DrawCursorV1;
};

// Shared shape ChartView can apply regardless of endpoint (overlay/draw).
export type OverlayLikeDeltaV1 = {
  active_ids: string[];
  instruction_catalog_patch: OverlayInstructionPatchItemV1[];
  next_cursor: { version_id: number };
};
