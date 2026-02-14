import type { UTCTimestamp } from "lightweight-charts";

import type { GetFactorSlicesResponseV1 } from "./types";

export type PenLinePoint = { time: UTCTimestamp; value: number };

export type PenSegment = {
  key: string;
  points: PenLinePoint[];
  highlighted: boolean;
};

type AnchorRef = {
  kind: "candidate" | "confirmed";
  start_time: number;
  end_time: number;
  direction: number;
};

type HeadPen = {
  start_time: number;
  end_time: number;
  direction: number;
  points: PenLinePoint[];
};

export type PenAnchorRuntimeState = {
  penSegments: PenSegment[];
  replayPenPoints: PenLinePoint[];
  replayPenPreviewPoints: Record<"pen.extending" | "pen.candidate", PenLinePoint[]>;
  anchorHighlightPoints: PenLinePoint[] | null;
  anchorHighlightDashed: boolean;
};

function pickAnchorRef(value: unknown): AnchorRef | null {
  if (!value || typeof value !== "object") return null;
  const data = value as Record<string, unknown>;
  const kind = data["kind"] === "candidate" || data["kind"] === "confirmed" ? (data["kind"] as "candidate" | "confirmed") : null;
  const startTime = Number(data["start_time"]);
  const endTime = Number(data["end_time"]);
  const direction = Number(data["direction"]);
  if (!kind || !Number.isFinite(startTime) || !Number.isFinite(endTime) || !Number.isFinite(direction)) return null;
  return {
    kind,
    start_time: Math.floor(startTime),
    end_time: Math.floor(endTime),
    direction: Math.floor(direction)
  };
}

function pickHeadPen(
  value: unknown,
  minTime: number | null,
  maxTime: number | null,
  candleTimeSet: Set<number>
): HeadPen | null {
  if (!value || typeof value !== "object") return null;
  const data = value as Record<string, unknown>;
  const startTime = Math.floor(Number(data["start_time"]));
  const endTime = Math.floor(Number(data["end_time"]));
  const startPrice = Number(data["start_price"]);
  const endPrice = Number(data["end_price"]);
  const direction = Math.floor(Number(data["direction"]));
  if (!Number.isFinite(startTime) || !Number.isFinite(endTime) || !Number.isFinite(startPrice) || !Number.isFinite(endPrice) || !Number.isFinite(direction)) return null;
  if (startTime <= 0 || endTime <= 0 || startTime >= endTime) return null;
  if (minTime != null && maxTime != null && (startTime < minTime || endTime > maxTime)) return null;
  if (!candleTimeSet.has(startTime) || !candleTimeSet.has(endTime)) return null;
  return {
    start_time: startTime,
    end_time: endTime,
    direction,
    points: [
      { time: startTime as UTCTimestamp, value: startPrice },
      { time: endTime as UTCTimestamp, value: endPrice }
    ]
  };
}

export function derivePenAnchorStateFromSlices(params: {
  slices: GetFactorSlicesResponseV1;
  minTime: number | null;
  maxTime: number | null;
  candleTimes: number[];
  replayEnabled: boolean;
  enablePenSegmentColor: boolean;
  segmentRenderLimit: number;
}): PenAnchorRuntimeState {
  const { slices, minTime, maxTime, candleTimes, replayEnabled, enablePenSegmentColor, segmentRenderLimit } = params;
  const candleTimeSet = new Set(
    (candleTimes ?? [])
      .map((value) => Math.floor(Number(value)))
      .filter((value) => Number.isFinite(value) && value > 0)
  );
  const anchor = slices.snapshots?.["anchor"];
  const pen = slices.snapshots?.["pen"];

  const head = (anchor?.head ?? {}) as Record<string, unknown>;
  const currentRef = pickAnchorRef(head["current_anchor_ref"]);
  const confirmedHighlightKey =
    currentRef?.kind === "confirmed" ? `pen:${currentRef.start_time}:${currentRef.end_time}:${currentRef.direction}` : null;

  const confirmedPensRaw = (pen?.history as Record<string, unknown> | undefined)?.["confirmed"];
  const confirmedPens = Array.isArray(confirmedPensRaw)
    ? confirmedPensRaw.slice().sort((a, b) => {
        const left = a && typeof a === "object" ? (a as Record<string, unknown>) : {};
        const right = b && typeof b === "object" ? (b as Record<string, unknown>) : {};
        const leftStart = Math.floor(Number(left["start_time"]));
        const rightStart = Math.floor(Number(right["start_time"]));
        if (leftStart !== rightStart) return leftStart - rightStart;
        return Math.floor(Number(left["end_time"])) - Math.floor(Number(right["end_time"]));
      })
    : [];

  const confirmedLinePoints: PenLinePoint[] = [];
  const segments: PenSegment[] = [];

  for (const item of confirmedPens) {
    if (!item || typeof item !== "object") continue;
    const penItem = item as Record<string, unknown>;
    const startTime = Math.floor(Number(penItem["start_time"]));
    const endTime = Math.floor(Number(penItem["end_time"]));
    const startPrice = Number(penItem["start_price"]);
    const endPrice = Number(penItem["end_price"]);
    const direction = Math.floor(Number(penItem["direction"]));
    if (!Number.isFinite(startTime) || !Number.isFinite(endTime) || !Number.isFinite(startPrice) || !Number.isFinite(endPrice) || !Number.isFinite(direction)) continue;
    if (startTime <= 0 || endTime <= 0 || startTime >= endTime) continue;
    if (minTime != null && maxTime != null && (startTime < minTime || endTime > maxTime)) continue;
    if (!candleTimeSet.has(startTime) || !candleTimeSet.has(endTime)) continue;

    const startPoint: PenLinePoint = { time: startTime as UTCTimestamp, value: startPrice };
    const endPoint: PenLinePoint = { time: endTime as UTCTimestamp, value: endPrice };
    if (!confirmedLinePoints.length || Number(confirmedLinePoints[confirmedLinePoints.length - 1]!.time) !== startTime) {
      confirmedLinePoints.push(startPoint);
    }
    confirmedLinePoints.push(endPoint);

    const key = `pen:${startTime}:${endTime}:${direction}`;
    segments.push({
      key,
      points: [startPoint, endPoint],
      highlighted: confirmedHighlightKey != null && key === confirmedHighlightKey
    });
  }

  const penHead = (pen?.head ?? {}) as Record<string, unknown>;
  const extendingPen = pickHeadPen(penHead["extending"], minTime, maxTime, candleTimeSet);
  const candidatePen = pickHeadPen(penHead["candidate"], minTime, maxTime, candleTimeSet);

  let anchorHighlightPoints: PenLinePoint[] | null = null;
  let anchorHighlightDashed = false;

  if (currentRef?.kind === "candidate" && candidatePen) {
    if (
      candidatePen.start_time === currentRef.start_time &&
      candidatePen.end_time === currentRef.end_time &&
      candidatePen.direction === currentRef.direction
    ) {
      anchorHighlightPoints = candidatePen.points;
      anchorHighlightDashed = true;
    }
  } else if (!enablePenSegmentColor && confirmedHighlightKey) {
    const hit = segments.find((segment) => segment.key === confirmedHighlightKey);
    if (hit) {
      anchorHighlightPoints = hit.points;
      anchorHighlightDashed = false;
    }
  }

  return {
    penSegments: segments.slice(Math.max(0, segments.length - segmentRenderLimit)),
    replayPenPoints: replayEnabled ? confirmedLinePoints : [],
    replayPenPreviewPoints: {
      "pen.extending": replayEnabled && extendingPen ? extendingPen.points : [],
      "pen.candidate": replayEnabled && candidatePen ? candidatePen.points : []
    },
    anchorHighlightPoints,
    anchorHighlightDashed
  };
}
