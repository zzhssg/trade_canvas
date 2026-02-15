import type { Dispatch, MutableRefObject, SetStateAction } from "react";
import type { IChartApi, ISeriesApi, SeriesMarker, Time, UTCTimestamp } from "lightweight-charts";

import type {
  Candle,
  GetFactorSlicesResponseV1,
  OverlayInstructionPatchItemV1,
  OverlayLikeDeltaV1,
  WorldStateV1
} from "./types";
import type { MarketWsMessage } from "./ws";

export type ReplayPenPreviewFeature = "pen.extending" | "pen.candidate";
export type LiveLoadStatus = "idle" | "loading" | "backfilling" | "ready" | "empty" | "error";

export type PenLinePoint = { time: UTCTimestamp; value: number };
export type PenSegment = { key: string; points: PenLinePoint[]; highlighted: boolean };

export type BatchMessage = Extract<MarketWsMessage, { type: "candles_batch" }>;
export type SystemMessage = Extract<MarketWsMessage, { type: "system" }>;
export type FormingMessage = Extract<MarketWsMessage, { type: "candle_forming" }>;
export type ClosedMessage = Extract<MarketWsMessage, { type: "candle_closed" }>;
export type GapMessage = Extract<MarketWsMessage, { type: "gap" }>;

export type OpenMarketWs = (options: {
  since: number | null;
  isActive: () => boolean;
  onCandlesBatch: (msg: BatchMessage) => void;
  onSystem: (msg: SystemMessage) => void;
  onCandleForming: (msg: FormingMessage) => void;
  onCandleClosed: (msg: ClosedMessage) => void;
  onGap: (msg: GapMessage) => void;
  onSocketError: () => void;
}) => WebSocket;

export type StartChartLiveSessionArgs = {
  seriesId: string;
  timeframe: string;
  replayEnabled: boolean;
  replayPreparedAlignedTime: number | null;
  windowCandles: number;
  enableWorldFrame: boolean;
  enablePenSegmentColor: boolean;
  openMarketWs: OpenMarketWs;
  chartRef: MutableRefObject<IChartApi | null>;
  seriesRef: MutableRefObject<ISeriesApi<"Candlestick"> | null>;
  candlesRef: MutableRefObject<Candle[]>;
  setCandles: Dispatch<SetStateAction<Candle[]>>;
  setLiveLoadState: (status: LiveLoadStatus, message?: string) => void;
  lastWsCandleTimeRef: MutableRefObject<number | null>;
  setLastWsCandleTime: (value: number | null) => void;
  appliedRef: MutableRefObject<{ len: number; lastTime: number | null }>;
  pivotMarkersRef: MutableRefObject<Array<SeriesMarker<Time>>>;
  anchorSwitchMarkersRef: MutableRefObject<Array<SeriesMarker<Time>>>;
  overlayCatalogRef: MutableRefObject<Map<string, OverlayInstructionPatchItemV1>>;
  overlayActiveIdsRef: MutableRefObject<Set<string>>;
  overlayCursorVersionRef: MutableRefObject<number>;
  overlayPullInFlightRef: MutableRefObject<boolean>;
  overlayPolylineSeriesByIdRef: MutableRefObject<Map<string, ISeriesApi<"Line">>>;
  replayPenPreviewSeriesByFeatureRef: MutableRefObject<Record<ReplayPenPreviewFeature, ISeriesApi<"Line"> | null>>;
  replayPenPreviewPointsRef: MutableRefObject<Record<ReplayPenPreviewFeature, PenLinePoint[]>>;
  followPendingTimeRef: MutableRefObject<number | null>;
  followTimerIdRef: MutableRefObject<number | null>;
  penSegmentsRef: MutableRefObject<PenSegment[]>;
  anchorPenPointsRef: MutableRefObject<PenLinePoint[] | null>;
  factorPullPendingTimeRef: MutableRefObject<number | null>;
  factorPullInFlightRef: MutableRefObject<boolean>;
  lastFactorAtTimeRef: MutableRefObject<number | null>;
  worldFrameHealthyRef: MutableRefObject<boolean>;
  replayAllCandlesRef: MutableRefObject<Array<Candle | null>>;
  penSeriesRef: MutableRefObject<ISeriesApi<"Line"> | null>;
  penPointsRef: MutableRefObject<PenLinePoint[]>;
  effectiveVisible: (key: string) => boolean;
  showToast: (message: string) => void;
  setError: (value: string | null) => void;
  setZhongshuCount: (value: number) => void;
  setAnchorCount: (value: number) => void;
  setAnchorHighlightEpoch: Dispatch<SetStateAction<number>>;
  setPivotCount: (value: number) => void;
  setAnchorSwitchCount: (value: number) => void;
  setPenPointCount: (value: number) => void;
  setReplayTotal: (value: number) => void;
  setReplayPlaying: (value: boolean) => void;
  setReplayIndex: (value: number) => void;
  applyOverlayDelta: (delta: OverlayLikeDeltaV1) => void;
  fetchOverlayLikeDelta: (params: {
    seriesId: string;
    cursorVersionId: number;
    windowCandles: number;
  }) => Promise<OverlayLikeDeltaV1>;
  rebuildPivotMarkersFromOverlay: () => void;
  rebuildAnchorSwitchMarkersFromOverlay: () => void;
  rebuildPenPointsFromOverlay: () => void;
  rebuildOverlayPolylinesFromOverlay: () => void;
  syncMarkers: () => void;
  fetchAndApplyAnchorHighlightAtTime: (time: number) => Promise<void>;
  applyWorldFrame: (frame: WorldStateV1) => void;
  applyPenAndAnchorFromFactorSlices: (slices: GetFactorSlicesResponseV1) => void;
};

export type StartChartLiveSessionOptions = StartChartLiveSessionArgs & {
  isActive: () => boolean;
};
