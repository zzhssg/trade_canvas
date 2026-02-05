import type { IChartApi, ISeriesApi } from "lightweight-charts";

export function normalizeTimeToSec(timeRaw: unknown): number | null {
  if (typeof timeRaw === "number") {
    return timeRaw > 1e12 ? Math.floor(timeRaw / 1000) : timeRaw;
  }

  if (typeof timeRaw === "string") {
    const parsed = new Date(timeRaw).getTime();
    if (Number.isNaN(parsed)) return null;
    return Math.floor(parsed / 1000);
  }

  if (timeRaw && typeof timeRaw === "object" && "year" in (timeRaw as Record<string, unknown>)) {
    const t = timeRaw as { year: number; month: number; day: number };
    if (!Number.isFinite(t.year) || !Number.isFinite(t.month) || !Number.isFinite(t.day)) return null;
    return Math.floor(Date.UTC(t.year, t.month - 1, t.day) / 1000);
  }

  return null;
}

export function sortAndDeduplicateTimes(timesSec: number[]): number[] {
  return Array.from(new Set(timesSec.map((t) => Number(t)).filter((t) => Number.isFinite(t)))).sort((a, b) => a - b);
}

export function estimateTimeStep(timesSec: number[]): number {
  if (timesSec.length >= 2) {
    for (let i = timesSec.length - 1; i > 0; i -= 1) {
      const diff = Number(timesSec[i]!) - Number(timesSec[i - 1]!);
      if (diff > 0) return diff;
    }
    const fallback = Number(timesSec[1]!) - Number(timesSec[0]!);
    if (fallback > 0) return fallback;
  }
  return 60;
}

export function resolveTimeFromX(params: { chart: IChartApi; x: number; candleTimesSec: number[] }): number | null {
  const { chart, x, candleTimesSec } = params;
  const timeScale = chart.timeScale();

  const timeScaleAny = timeScale as unknown as {
    coordinateToLogical?: (coord: number) => number | null;
  };

  const logical =
    typeof timeScaleAny.coordinateToLogical === "function" ? timeScaleAny.coordinateToLogical(x) : null;

  if (logical != null && Number.isFinite(Number(logical))) {
    const logicalNum = Number(logical);
    const firstIdx = 0;
    const lastIdx = candleTimesSec.length - 1;
    const firstTime = candleTimesSec[firstIdx];
    const lastTime = candleTimesSec[lastIdx];
    const stepSec = estimateTimeStep(candleTimesSec);

    if (candleTimesSec.length > 0 && firstTime != null && lastTime != null) {
      if (logicalNum >= firstIdx && logicalNum <= lastIdx) {
        const idx = Math.max(firstIdx, Math.min(lastIdx, Math.round(logicalNum)));
        return Number(candleTimesSec[idx]!);
      }
      if (logicalNum > lastIdx) return Number(lastTime) + (logicalNum - lastIdx) * stepSec;
      return Number(firstTime) - (firstIdx - logicalNum) * stepSec;
    }
  }

  const raw = timeScale.coordinateToTime(x);
  const t = normalizeTimeToSec(raw) ?? (typeof raw === "number" ? raw : null);
  if (t == null || !Number.isFinite(t)) return null;
  return Number(t);
}

export function getBarSpacingPx(timeScale: ReturnType<IChartApi["timeScale"]>, candleTimesSec: number[]): number | null {
  try {
    const opts = timeScale.options();
    const bs = (opts as unknown as { barSpacing?: unknown })?.barSpacing;
    if (typeof bs === "number" && Number.isFinite(bs) && bs > 0) return bs;
  } catch {
    // ignore
  }

  if (candleTimesSec.length >= 2) {
    const lastIdx = candleTimesSec.length - 1;
    for (let i = lastIdx; i > 0; i -= 1) {
      const t0 = candleTimesSec[i - 1]!;
      const t1 = candleTimesSec[i]!;
      const c0 = timeScale.timeToCoordinate(t0 as any);
      const c1 = timeScale.timeToCoordinate(t1 as any);
      if (c0 != null && c1 != null) {
        const d = Number(c1) - Number(c0);
        if (Number.isFinite(d) && Math.abs(d) > 1e-9) return d;
      }
    }
  }

  return null;
}

export function timeToCoordinateContinuous(params: {
  timeScale: ReturnType<IChartApi["timeScale"]>;
  candleTimesSec: number[];
  timeSec: number;
}): number | null {
  const { timeScale, candleTimesSec } = params;
  const timeSec = normalizeTimeToSec(params.timeSec) ?? params.timeSec;
  if (!Number.isFinite(timeSec)) return null;

  const times = candleTimesSec;
  const coordAt = (t: number): number | null => {
    const c = timeScale.timeToCoordinate(t as any);
    return c == null ? null : Number(c);
  };

  if (times.length === 0) return coordAt(timeSec);

  const lastIdx = times.length - 1;
  const first = Number(times[0]!);
  const last = Number(times[lastIdx]!);
  const stepSec = estimateTimeStep(times);
  const spacing = getBarSpacingPx(timeScale, times);

  if (timeSec <= first) {
    const cFirst = coordAt(first);
    if (cFirst == null || spacing == null || stepSec <= 0) return cFirst;
    return cFirst + ((timeSec - first) / stepSec) * spacing;
  }
  if (timeSec >= last) {
    const cLast = coordAt(last);
    if (cLast == null || spacing == null || stepSec <= 0) return cLast;
    return cLast + ((timeSec - last) / stepSec) * spacing;
  }

  let lo = 0;
  let hi = lastIdx;
  while (lo < hi) {
    const mid = Math.floor((lo + hi) / 2);
    if (Number(times[mid]!) < timeSec) lo = mid + 1;
    else hi = mid;
  }

  const i = lo;
  const t1 = Number(times[i]!);
  if (t1 === timeSec) return coordAt(t1);
  const t0 = Number(times[i - 1]!);

  const c0 = coordAt(t0);
  const c1 = coordAt(t1);
  if (c0 != null && c1 != null) {
    const denom = (t1 - t0) || stepSec;
    const frac = denom !== 0 ? (timeSec - t0) / denom : 0;
    return c0 + (c1 - c0) * frac;
  }
  if (c0 != null && spacing != null && stepSec > 0) {
    return c0 + ((timeSec - t0) / stepSec) * spacing;
  }
  if (c1 != null && spacing != null && stepSec > 0) {
    return c1 - ((t1 - timeSec) / stepSec) * spacing;
  }
  return c0 ?? c1;
}

export function resolvePointFromClient(params: {
  chart: IChartApi;
  series: ISeriesApi<"Candlestick">;
  container: HTMLDivElement;
  clientX: number;
  clientY: number;
  candleTimesSec: number[];
}): { time: number; price: number; x: number; y: number } | null {
  const { chart, series, container, clientX, clientY, candleTimesSec } = params;
  const rect = container.getBoundingClientRect();
  const x = clientX - rect.left;
  const y = clientY - rect.top;
  if (!Number.isFinite(x) || !Number.isFinite(y)) return null;

  const time = resolveTimeFromX({ chart, x, candleTimesSec });
  if (time == null || !Number.isFinite(time)) return null;
  const price = series.coordinateToPrice(y);
  if (price == null || !Number.isFinite(Number(price))) return null;

  return { time: Number(time), price: Number(price), x: Number(x), y: Number(y) };
}

