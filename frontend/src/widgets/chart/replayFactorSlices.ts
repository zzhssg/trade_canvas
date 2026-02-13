/**
 * 回放因子切片构建 — 纯函数，从 history events + head snapshots 重建 GetFactorSlicesResponseV1。
 *
 * 无组件状态依赖，可在任意上下文调用。
 */
import type {
  GetFactorSlicesResponseV1,
  ReplayFactorHeadSnapshotV1,
  ReplayHistoryEventV1
} from "./types";

/** 二分查找 historyEvents 中 event_id <= toEventId 的子集 */
export function sliceHistoryEventsById(events: ReplayHistoryEventV1[], toEventId: number): ReplayHistoryEventV1[] {
  if (!events.length || toEventId <= 0) return [];
  let lo = 0;
  let hi = events.length - 1;
  let idx = -1;
  while (lo <= hi) {
    const mid = Math.floor((lo + hi) / 2);
    const v = events[mid]!.event_id;
    if (v <= toEventId) {
      idx = mid;
      lo = mid + 1;
    } else {
      hi = mid - 1;
    }
  }
  if (idx < 0) return [];
  return events.slice(0, idx + 1);
}

/** 从 replay history events + head snapshots 构建完整的 factor slices 响应 */
export function buildReplayFactorSlices(params: {
  seriesId: string;
  atTime: number;
  toEventId: number;
  historyEvents: ReplayHistoryEventV1[];
  headByTime: Record<number, Record<string, ReplayFactorHeadSnapshotV1>>;
}): GetFactorSlicesResponseV1 {
  const { seriesId } = params;
  const aligned = Math.max(0, Math.floor(params.atTime));
  const candleId = `${seriesId}:${aligned}`;
  const historySlice = sliceHistoryEventsById(params.historyEvents, params.toEventId);
  const headForTime = params.headByTime[aligned] ?? {};
  const pivotMajor: Record<string, unknown>[] = [];
  const pivotMinor: Record<string, unknown>[] = [];
  const penConfirmed: Record<string, unknown>[] = [];
  const zhongshuDead: Record<string, unknown>[] = [];
  const anchorSwitches: Record<string, unknown>[] = [];

  for (const ev of historySlice) {
    const payload = ev.payload && typeof ev.payload === "object" ? (ev.payload as Record<string, unknown>) : {};
    if (ev.factor_name === "pivot" && ev.kind === "pivot.major") {
      pivotMajor.push(payload);
    } else if (ev.factor_name === "pivot" && ev.kind === "pivot.minor") {
      pivotMinor.push(payload);
    } else if (ev.factor_name === "pen" && ev.kind === "pen.confirmed") {
      penConfirmed.push(payload);
    } else if (ev.factor_name === "zhongshu" && ev.kind === "zhongshu.dead") {
      zhongshuDead.push(payload);
    } else if (ev.factor_name === "anchor" && ev.kind === "anchor.switch") {
      anchorSwitches.push(payload);
    }
  }

  const makeMeta = (factorName: string) => ({
    series_id: seriesId,
    epoch: 0,
    at_time: aligned,
    candle_id: candleId,
    factor_name: factorName
  });

  const snapshots: Record<string, { schema_version: number; history: Record<string, unknown>; head: Record<string, unknown>; meta: any }> =
    {};
  const factors: string[] = [];

  const pivotHead = headForTime["pivot"]?.head ?? {};
  if (pivotMajor.length || pivotMinor.length || (pivotHead && Object.keys(pivotHead).length)) {
    snapshots["pivot"] = {
      schema_version: 1,
      history: { major: pivotMajor, minor: pivotMinor },
      head: pivotHead,
      meta: makeMeta("pivot")
    };
    factors.push("pivot");
  }

  const penHead = headForTime["pen"]?.head ?? {};
  if (penConfirmed.length || (penHead && Object.keys(penHead).length)) {
    snapshots["pen"] = {
      schema_version: 1,
      history: { confirmed: penConfirmed },
      head: penHead,
      meta: makeMeta("pen")
    };
    factors.push("pen");
  }

  const zhongshuHead = headForTime["zhongshu"]?.head ?? {};
  if (zhongshuDead.length || (zhongshuHead && Object.keys(zhongshuHead).length)) {
    snapshots["zhongshu"] = {
      schema_version: 1,
      history: { dead: zhongshuDead },
      head: zhongshuHead,
      meta: makeMeta("zhongshu")
    };
    factors.push("zhongshu");
  }

  const anchorHead = headForTime["anchor"]?.head ?? {};
  if (anchorSwitches.length || (anchorHead && Object.keys(anchorHead).length)) {
    snapshots["anchor"] = {
      schema_version: 1,
      history: { switches: anchorSwitches },
      head: anchorHead,
      meta: makeMeta("anchor")
    };
    factors.push("anchor");
  }

  return {
    schema_version: 1,
    series_id: seriesId,
    at_time: aligned,
    candle_id: candleId,
    factors,
    snapshots: snapshots as GetFactorSlicesResponseV1["snapshots"]
  };
}
