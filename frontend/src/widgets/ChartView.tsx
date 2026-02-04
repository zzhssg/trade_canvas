import {
  LineSeries,
  LineStyle,
  type IChartApi,
  type ISeriesApi,
  type SeriesMarker,
  type Time,
  type UTCTimestamp
} from "lightweight-charts";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import useResizeObserver from "use-resize-observer";

import { apiWsBase } from "../lib/api";
import { logDebugEvent } from "../debug/debug";
import { CENTER_SCROLL_SELECTOR, chartWheelZoomRatio, normalizeWheelDeltaY } from "../lib/wheelContract";
import { FACTOR_CATALOG, getFactorParentsBySubKey } from "../services/factorCatalog";
import { useFactorStore } from "../state/factorStore";
import { useUiStore } from "../state/uiStore";

import {
  fetchCandles,
  fetchDrawDelta,
  fetchFactorSlices,
  fetchOverlayDelta,
  fetchWorldFrameAtTime,
  fetchWorldFrameLive,
  pollWorldDelta
} from "./chart/api";
import { MAX_BAR_SPACING_ON_FIT_CONTENT, clampBarSpacing } from "./chart/barSpacing";
import { mergeCandlesWindow, mergeCandleWindow, toChartCandle } from "./chart/candles";
import { buildSmaLineData, computeSmaAtIndex, isSmaKey } from "./chart/sma";
import type { Candle, OverlayInstructionPatchItemV1, OverlayLikeDeltaV1 } from "./chart/types";
import type { GetFactorSlicesResponseV1, WorldStateV1 } from "./chart/types";
import { timeframeToSeconds } from "./chart/timeframe";
import { useLightweightChart } from "./chart/useLightweightChart";
import { parseMarketWsMessage } from "./chart/ws";

const INITIAL_TAIL_LIMIT = 2000;
const ENABLE_DRAW_DELTA = import.meta.env.VITE_ENABLE_DRAW_DELTA === "1";
const ENABLE_REPLAY_V1 = import.meta.env.VITE_ENABLE_REPLAY_V1 === "1";
const ENABLE_PEN_SEGMENT_COLOR = import.meta.env.VITE_ENABLE_PEN_SEGMENT_COLOR === "1";
// Default to enabled (unless explicitly disabled) to avoid "delta + slices" double-fetch loops in live mode.
const ENABLE_WORLD_FRAME = String(import.meta.env.VITE_ENABLE_WORLD_FRAME ?? "1") === "1";
const PEN_SEGMENT_RENDER_LIMIT = 200;

export function ChartView() {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const { ref: resizeRef, width, height } = useResizeObserver<HTMLDivElement>();
  const wheelGuardRef = useRef<HTMLDivElement | null>(null);

  const [candles, setCandles] = useState<Candle[]>([]);
  const [barSpacing, setBarSpacing] = useState<number | null>(null);
  const candlesRef = useRef<Candle[]>([]);
  const lastWsCandleTimeRef = useRef<number | null>(null);
  const [lastWsCandleTime, setLastWsCandleTime] = useState<number | null>(null);
  const appliedRef = useRef<{ len: number; lastTime: number | null }>({ len: 0, lastTime: null });
  const [error, setError] = useState<string | null>(null);
  const { exchange, market, symbol, timeframe } = useUiStore();
  const seriesId = useMemo(() => `${exchange}:${market}:${symbol}:${timeframe}`, [exchange, market, symbol, timeframe]);

  const { visibleFeatures } = useFactorStore();
  const visibleFeaturesRef = useRef(visibleFeatures);
  const parentBySubKey = useMemo(() => getFactorParentsBySubKey(FACTOR_CATALOG), []);
  const lineSeriesByKeyRef = useRef<Map<string, ISeriesApi<"Line">>>(new Map());
  const entryMarkersRef = useRef<Array<SeriesMarker<Time>>>([]);
  const pivotMarkersRef = useRef<Array<SeriesMarker<Time>>>([]);
  const overlayCatalogRef = useRef<Map<string, OverlayInstructionPatchItemV1>>(new Map());
  const overlayActiveIdsRef = useRef<Set<string>>(new Set());
  const overlayCursorVersionRef = useRef<number>(0);
  const overlayPullInFlightRef = useRef(false);
  const entryEnabledRef = useRef<boolean>(false);
  const [pivotCount, setPivotCount] = useState(0);
  const [replayEnabled, setReplayEnabled] = useState<boolean>(ENABLE_REPLAY_V1);
  const [replayPlaying, setReplayPlaying] = useState<boolean>(ENABLE_REPLAY_V1);
  const [replayIndex, setReplayIndex] = useState<number>(0);
  const [replaySpeedMs, setReplaySpeedMs] = useState<number>(200);
  const replayAllCandlesRef = useRef<Candle[]>([]);
  const replayPatchRef = useRef<OverlayInstructionPatchItemV1[]>([]);
  const replayPatchAppliedIdxRef = useRef<number>(0);
  const followPendingTimeRef = useRef<number | null>(null);
  const followTimerIdRef = useRef<number | null>(null);

  const penSeriesRef = useRef<ISeriesApi<"Line"> | null>(null);
  const penPointsRef = useRef<Array<{ time: UTCTimestamp; value: number }>>([]);
  const [penPointCount, setPenPointCount] = useState(0);
  const [anchorHighlightEpoch, setAnchorHighlightEpoch] = useState(0);

  const penSegmentSeriesByKeyRef = useRef<Map<string, ISeriesApi<"Line">>>(new Map());
  const penSegmentsRef = useRef<
    Array<{
      key: string;
      points: Array<{ time: UTCTimestamp; value: number }>;
      highlighted: boolean;
    }>
  >([]);

  const anchorPenSeriesRef = useRef<ISeriesApi<"Line"> | null>(null);
  const anchorPenPointsRef = useRef<Array<{ time: UTCTimestamp; value: number }> | null>(null);
  const anchorPenIsDashedRef = useRef<boolean>(false);
  const factorPullInFlightRef = useRef(false);
  const lastFactorAtTimeRef = useRef<number | null>(null);

  const { chartRef, candleSeriesRef: seriesRef, markersApiRef, chartEpoch } = useLightweightChart({
    containerRef,
    width,
    height,
    onCreated: ({ chart, candleSeries }) => {
      const existing = candlesRef.current;
      if (existing.length > 0) {
        candleSeries.setData(existing);
        chart.timeScale().fitContent();
        const cur = chart.timeScale().options().barSpacing;
        const next = clampBarSpacing(cur, MAX_BAR_SPACING_ON_FIT_CONTENT);
        if (next !== cur) chart.applyOptions({ timeScale: { barSpacing: next } });
        const last = existing[existing.length - 1]!;
        appliedRef.current = { len: existing.length, lastTime: last.time as number };
      }
    },
    onCleanup: () => {
      lineSeriesByKeyRef.current.clear();
      entryMarkersRef.current = [];
      pivotMarkersRef.current = [];
      overlayCatalogRef.current.clear();
      overlayActiveIdsRef.current.clear();
      overlayCursorVersionRef.current = 0;
      penPointsRef.current = [];
      penSeriesRef.current = null;
      anchorPenPointsRef.current = null;
      anchorPenIsDashedRef.current = false;
      anchorPenSeriesRef.current = null;
      for (const s of penSegmentSeriesByKeyRef.current.values()) chartRef.current?.removeSeries(s);
      penSegmentSeriesByKeyRef.current.clear();
      penSegmentsRef.current = [];
      overlayPullInFlightRef.current = false;
      factorPullInFlightRef.current = false;
      lastFactorAtTimeRef.current = null;
      entryEnabledRef.current = false;
      appliedRef.current = { len: 0, lastTime: null };
    }
  });

  useEffect(() => {
    const el = wheelGuardRef.current;
    if (!el) return;
    const onWheel = (event: WheelEvent) => {
      const chart = chartRef.current;
      if (!chart) return;
      if (event.deltaY === 0) return;

      const center = el.closest(CENTER_SCROLL_SELECTOR) as HTMLElement | null;
      if (center) {
        const oy = window.getComputedStyle(center).overflowY;
        if (oy !== "hidden") return;
      }

      // UX rule:
      // - wheel inside chart => horizontal zoom (barSpacing)
      // - do NOT scroll the surrounding container while hovering the chart
      const cur = chart.timeScale().options().barSpacing;
      const dy = normalizeWheelDeltaY(event);
      const ratio = chartWheelZoomRatio(dy);
      if (!ratio) return;
      const next = clampBarSpacing(cur * ratio, MAX_BAR_SPACING_ON_FIT_CONTENT);
      if (next !== cur) {
        chart.applyOptions({ timeScale: { barSpacing: next } });
        setBarSpacing((prev) => (prev === next ? prev : next));
      }

      event.preventDefault();
      event.stopPropagation();
    };
    el.addEventListener("wheel", onWheel, { passive: false });
    return () => el.removeEventListener("wheel", onWheel as EventListener);
  }, [chartEpoch]);

  useEffect(() => {
    visibleFeaturesRef.current = visibleFeatures;
  }, [visibleFeatures]);

  useEffect(() => {
    const chart = chartRef.current;
    if (!chart) return;
    const timeScale = chart.timeScale();

    const update = () => {
      const spacing = timeScale.options().barSpacing;
      setBarSpacing((prev) => (prev === spacing ? prev : spacing));
    };

    update();
    const handler = () => update();
    timeScale.subscribeVisibleLogicalRangeChange(handler);
    return () => timeScale.unsubscribeVisibleLogicalRangeChange(handler);
  }, [chartEpoch]);

  const effectiveVisible = useCallback(
    (key: string): boolean => {
      const features = visibleFeaturesRef.current;
      const direct = features[key];
      const visible = direct === undefined ? true : direct;
      const parentKey = parentBySubKey[key];
      if (!parentKey) return visible;
      const parentVisible = features[parentKey];
      return (parentVisible === undefined ? true : parentVisible) && visible;
    },
    [parentBySubKey]
  );

  const syncMarkers = useCallback(() => {
    const markers = [...pivotMarkersRef.current, ...entryMarkersRef.current];
    markersApiRef.current?.setMarkers(markers);
    setPivotCount(pivotMarkersRef.current.length);
  }, []);

  const applyOverlayDelta = useCallback((delta: OverlayLikeDeltaV1) => {
    const patch = Array.isArray(delta.instruction_catalog_patch) ? delta.instruction_catalog_patch : [];
    for (const p of patch) {
      if (!p || typeof p !== "object") continue;
      if (typeof p.instruction_id !== "string" || !p.instruction_id) continue;
      overlayCatalogRef.current.set(p.instruction_id, p);
    }
    overlayActiveIdsRef.current = new Set(Array.isArray(delta.active_ids) ? delta.active_ids : []);

    const nextVersion =
      delta.next_cursor && typeof delta.next_cursor.version_id === "number" && Number.isFinite(delta.next_cursor.version_id)
        ? Math.max(0, Math.floor(delta.next_cursor.version_id))
        : null;
    if (nextVersion != null) overlayCursorVersionRef.current = nextVersion;
  }, []);

  const fetchOverlayLikeDelta = useCallback(
    async (params: { seriesId: string; cursorVersionId: number; windowCandles: number }): Promise<OverlayLikeDeltaV1> => {
      if (ENABLE_DRAW_DELTA) {
        const delta = await fetchDrawDelta(params);
        return {
          active_ids: delta.active_ids,
          instruction_catalog_patch: delta.instruction_catalog_patch,
          next_cursor: { version_id: delta.next_cursor?.version_id ?? 0 }
        };
      }
      const delta = await fetchOverlayDelta(params);
      return {
        active_ids: delta.active_ids,
        instruction_catalog_patch: delta.instruction_catalog_patch,
        next_cursor: { version_id: delta.next_cursor?.version_id ?? 0 }
      };
    },
    []
  );

  const rebuildPivotMarkersFromOverlay = useCallback(() => {
    const showPivotMajor = effectiveVisible("pivot.major");
    const showPivotMinor = effectiveVisible("pivot.minor");
    const want = new Set<string>();
    if (showPivotMajor) want.add("pivot.major");
    if (showPivotMinor) want.add("pivot.minor");

    const range = candlesRef.current;
    const minTime = range.length > 0 ? (range[0]!.time as number) : null;
    const maxTime = range.length > 0 ? (range[range.length - 1]!.time as number) : null;

    const next: Array<SeriesMarker<Time>> = [];
    if (minTime != null && maxTime != null && want.size > 0) {
      const ids = Array.from(overlayActiveIdsRef.current);
      for (const id of ids) {
        const item = overlayCatalogRef.current.get(id);
        if (!item || item.kind !== "marker") continue;

        const def = item.definition && typeof item.definition === "object" ? (item.definition as Record<string, unknown>) : {};
        const feature = String(def["feature"] ?? "");
        if (!want.has(feature)) continue;

        const t = Number(def["time"]);
        if (!Number.isFinite(t)) continue;
        if (t < minTime || t > maxTime) continue;

        const position = def["position"] === "aboveBar" || def["position"] === "belowBar" ? def["position"] : null;
        const shape =
          def["shape"] === "circle" ||
          def["shape"] === "square" ||
          def["shape"] === "arrowUp" ||
          def["shape"] === "arrowDown"
            ? def["shape"]
            : null;
        const color = typeof def["color"] === "string" ? def["color"] : null;
        const text = typeof def["text"] === "string" ? def["text"] : "";
        const sizeDefault = feature === "pivot.minor" ? 0.6 : 1.0;
        const sizeRaw = Number(def["size"]);
        const size = Number.isFinite(sizeRaw) && sizeRaw > 0 ? sizeRaw : sizeDefault;
        if (!position || !shape || !color) continue;

        next.push({ time: t as UTCTimestamp, position, color, shape, text, size });
      }
    }

    next.sort((a, b) => Number(a.time) - Number(b.time));
    pivotMarkersRef.current = next;
  }, [effectiveVisible]);

  const rebuildPenPointsFromOverlay = useCallback(() => {
    if (!overlayActiveIdsRef.current.has("pen.confirmed")) {
      penPointsRef.current = [];
      return;
    }
    const item = overlayCatalogRef.current.get("pen.confirmed");
    if (!item || item.kind !== "polyline") {
      penPointsRef.current = [];
      return;
    }

    const def = item.definition && typeof item.definition === "object" ? (item.definition as Record<string, unknown>) : {};
    const points = def["points"];
    if (!Array.isArray(points) || points.length === 0) {
      penPointsRef.current = [];
      return;
    }

    const range = candlesRef.current;
    const minTime = range.length > 0 ? (range[0]!.time as number) : null;
    const maxTime = range.length > 0 ? (range[range.length - 1]!.time as number) : null;

    const out: Array<{ time: UTCTimestamp; value: number }> = [];
    for (const p of points) {
      if (!p || typeof p !== "object") continue;
      const rec = p as Record<string, unknown>;
      const t = Number(rec["time"]);
      const v = Number(rec["value"]);
      if (!Number.isFinite(t) || !Number.isFinite(v)) continue;
      if (minTime != null && maxTime != null && (t < minTime || t > maxTime)) continue;
      out.push({ time: t as UTCTimestamp, value: v });
    }
    penPointsRef.current = out;
  }, []);

  const applyPenAndAnchorFromFactorSlices = useCallback(
    (slices: GetFactorSlicesResponseV1) => {
      const anchor = slices.snapshots?.["anchor"];
      const pen = slices.snapshots?.["pen"];
      const candlesRange = candlesRef.current;
      const minTime = candlesRange.length > 0 ? (candlesRange[0]!.time as number) : null;
      const maxTime = candlesRange.length > 0 ? (candlesRange[candlesRange.length - 1]!.time as number) : null;

      const head = (anchor?.head ?? {}) as Record<string, unknown>;
      const cur = head["current_anchor_ref"];
      const rev = head["reverse_anchor_ref"];

      const pickRef = (v: unknown) => {
        if (!v || typeof v !== "object") return null;
        const d = v as Record<string, unknown>;
        const kind = d["kind"] === "candidate" || d["kind"] === "confirmed" ? (d["kind"] as string) : null;
        const st = Number(d["start_time"]);
        const et = Number(d["end_time"]);
        const dir = Number(d["direction"]);
        if (!kind || !Number.isFinite(st) || !Number.isFinite(et) || !Number.isFinite(dir)) return null;
        return { kind, start_time: Math.floor(st), end_time: Math.floor(et), direction: Math.floor(dir) };
      };

      const setHighlight = (pts: Array<{ time: UTCTimestamp; value: number }> | null, opts?: { dashed?: boolean }) => {
        anchorPenPointsRef.current = pts;
        anchorPenIsDashedRef.current = Boolean(opts?.dashed);
      };

      const curRef = pickRef(cur);
      const revRef = pickRef(rev);

      // Segment coloring: highlight the stable confirmed anchor when available.
      const confirmedHighlightKey =
        curRef?.kind === "confirmed" ? `pen:${curRef.start_time}:${curRef.end_time}:${curRef.direction}` : null;

      const confirmedPens = (pen?.history as Record<string, unknown> | undefined)?.["confirmed"];
      const segments: Array<{ key: string; points: Array<{ time: UTCTimestamp; value: number }>; highlighted: boolean }> =
        [];
      if (Array.isArray(confirmedPens)) {
        const tail = confirmedPens.slice(Math.max(0, confirmedPens.length - PEN_SEGMENT_RENDER_LIMIT));
        for (const item of tail) {
          if (!item || typeof item !== "object") continue;
          const p = item as Record<string, unknown>;
          const st = Math.floor(Number(p["start_time"]));
          const et = Math.floor(Number(p["end_time"]));
          const sp = Number(p["start_price"]);
          const ep = Number(p["end_price"]);
          const dir = Math.floor(Number(p["direction"]));
          if (!Number.isFinite(st) || !Number.isFinite(et) || !Number.isFinite(sp) || !Number.isFinite(ep) || !Number.isFinite(dir))
            continue;
          if (st <= 0 || et <= 0 || st >= et) continue;
          if (minTime != null && maxTime != null && (st < minTime || et > maxTime)) continue;
          const key = `pen:${st}:${et}:${dir}`;
          segments.push({
            key,
            points: [
              { time: st as UTCTimestamp, value: sp },
              { time: et as UTCTimestamp, value: ep }
            ],
            highlighted: confirmedHighlightKey != null && key === confirmedHighlightKey
          });
        }
      }
      penSegmentsRef.current = segments;

      // Candidate highlight: prefer reverse_anchor_ref when it's a candidate; draw it as a separate segment.
      if (revRef?.kind === "candidate") {
        const ph = (pen?.head ?? {}) as Record<string, unknown>;
        const cand = ph["candidate"];
        if (
          cand &&
          typeof cand === "object" &&
          revRef.start_time > 0 &&
          revRef.end_time > revRef.start_time &&
          (minTime == null || maxTime == null || (revRef.start_time >= minTime && revRef.end_time <= maxTime))
        ) {
          const c = cand as Record<string, unknown>;
          const sp = Number(c["start_price"]);
          const ep = Number(c["end_price"]);
          if (Number.isFinite(sp) && Number.isFinite(ep)) {
            setHighlight(
              [
                { time: revRef.start_time as UTCTimestamp, value: sp },
                { time: revRef.end_time as UTCTimestamp, value: ep }
              ],
              { dashed: true }
            );
          } else {
            setHighlight(null);
          }
        } else {
          setHighlight(null);
        }
      } else {
        // Confirmed anchor highlight: only draw a separate segment when we're NOT doing segmented pen coloring.
        if (!ENABLE_PEN_SEGMENT_COLOR && confirmedHighlightKey) {
          const hit = segments.find((s) => s.key === confirmedHighlightKey);
          if (hit) setHighlight(hit.points, { dashed: false });
          else setHighlight(null);
        } else {
          setHighlight(null);
        }
      }

      setAnchorHighlightEpoch((v) => v + 1);
    },
    [setAnchorHighlightEpoch]
  );

  const fetchAndApplyAnchorHighlightAtTime = useCallback(
    async (t: number) => {
      const at = Math.max(0, Math.floor(t));
      if (at <= 0) return;
      if (factorPullInFlightRef.current) return;
      if (lastFactorAtTimeRef.current === at) return;
      factorPullInFlightRef.current = true;
      try {
        const slices = await fetchFactorSlices({ seriesId, atTime: at, windowCandles: INITIAL_TAIL_LIMIT });
        lastFactorAtTimeRef.current = at;
        applyPenAndAnchorFromFactorSlices(slices);
      } catch {
        // ignore (best-effort)
      } finally {
        factorPullInFlightRef.current = false;
      }
    },
    [applyPenAndAnchorFromFactorSlices, seriesId]
  );

  const applyWorldFrame = useCallback(
    (frame: WorldStateV1) => {
      overlayCatalogRef.current.clear();
      overlayActiveIdsRef.current.clear();
      overlayCursorVersionRef.current = 0;

      const draw = frame.draw_state;
      applyOverlayDelta({
        active_ids: draw.active_ids ?? [],
        instruction_catalog_patch: draw.instruction_catalog_patch ?? [],
        next_cursor: { version_id: draw.next_cursor?.version_id ?? 0 }
      });

      rebuildPivotMarkersFromOverlay();
      syncMarkers();
      rebuildPenPointsFromOverlay();
      setPenPointCount(ENABLE_PEN_SEGMENT_COLOR ? penSegmentsRef.current.length * 2 : penPointsRef.current.length);
      if (effectiveVisible("pen.confirmed") && penSeriesRef.current) {
        penSeriesRef.current.setData(penPointsRef.current);
      }

      applyPenAndAnchorFromFactorSlices(frame.factor_slices);
    },
    [
      applyOverlayDelta,
      applyPenAndAnchorFromFactorSlices,
      effectiveVisible,
      rebuildPenPointsFromOverlay,
      rebuildPivotMarkersFromOverlay,
      syncMarkers
    ]
  );

  const recomputeActiveIdsFromCatalog = useCallback((params: { cutoffTime: number; toTime: number }): string[] => {
    const out: string[] = [];
    for (const [id, item] of overlayCatalogRef.current.entries()) {
      if (!item) continue;
      if (item.kind === "marker") {
        const def = item.definition && typeof item.definition === "object" ? (item.definition as Record<string, unknown>) : {};
        const t = Number(def["time"]);
        if (!Number.isFinite(t)) continue;
        if (t < params.cutoffTime || t > params.toTime) continue;
        out.push(id);
        continue;
      }
      if (item.kind === "polyline") {
        const def = item.definition && typeof item.definition === "object" ? (item.definition as Record<string, unknown>) : {};
        const pts = def["points"];
        if (!Array.isArray(pts) || pts.length === 0) continue;
        let ok = false;
        for (const p of pts) {
          if (!p || typeof p !== "object") continue;
          const t = Number((p as Record<string, unknown>)["time"]);
          if (!Number.isFinite(t)) continue;
          if (params.cutoffTime <= t && t <= params.toTime) {
            ok = true;
            break;
          }
        }
        if (!ok) continue;
        out.push(id);
      }
    }
    out.sort();
    return out;
  }, []);

  const applyReplayOverlayAtTime = useCallback(
    (toTime: number) => {
      const patch = replayPatchRef.current;
      let i = replayPatchAppliedIdxRef.current;
      for (; i < patch.length; i++) {
        const p = patch[i]!;
        if (p.visible_time > toTime) break;
        overlayCatalogRef.current.set(p.instruction_id, p);
      }
      replayPatchAppliedIdxRef.current = i;

      const tfSeconds = timeframeToSeconds(timeframe);
      const cutoffTime = tfSeconds ? Math.max(0, Math.floor(toTime - INITIAL_TAIL_LIMIT * tfSeconds)) : 0;
      overlayActiveIdsRef.current = new Set(recomputeActiveIdsFromCatalog({ cutoffTime, toTime }));

      rebuildPivotMarkersFromOverlay();
      rebuildPenPointsFromOverlay();
      if (effectiveVisible("pen.confirmed") && penSeriesRef.current) {
        penSeriesRef.current.setData(penPointsRef.current);
      }
      setPenPointCount(penPointsRef.current.length);
      syncMarkers();
    },
    [effectiveVisible, recomputeActiveIdsFromCatalog, rebuildPenPointsFromOverlay, rebuildPivotMarkersFromOverlay, syncMarkers, timeframe]
  );

  const setReplayIndexAndCandles = useCallback(
    (nextIndex: number, opts?: { pause?: boolean }) => {
      const all = replayAllCandlesRef.current;
      if (all.length === 0) return;
      const clamped = Math.max(0, Math.min(nextIndex, all.length - 1));
      if (opts?.pause) setReplayPlaying(false);
      setReplayIndex(clamped);
      setCandles((prev) => {
        // Append-only fast-path for smooth playback.
        const next =
          clamped === prev.length && clamped < all.length ? [...prev, all[clamped]!] : all.slice(0, clamped + 1);
        candlesRef.current = next;
        return next;
      });
      applyReplayOverlayAtTime(all[clamped]!.time as number);
    },
    [applyReplayOverlayAtTime]
  );

  useEffect(() => {
    const series = seriesRef.current;
    if (!series) return;
    if (candles.length === 0) return;
    const last = candles[candles.length - 1]!;
    const prev = appliedRef.current;

    const isAppendOne = prev.len === candles.length - 1 && (prev.lastTime == null || (last.time as number) >= prev.lastTime);
    const isUpdateLast = prev.len === candles.length && prev.lastTime != null && (last.time as number) === prev.lastTime;

    const syncAll = () => {
      series.setData(candles);
      for (const [key, s] of lineSeriesByKeyRef.current.entries()) {
        const period = isSmaKey(key);
        if (period != null) s.setData(buildSmaLineData(candles, period));
      }
      syncMarkers();
    };

    if (prev.len === 0) {
      syncAll();
      chartRef.current?.timeScale().fitContent();
      const chart = chartRef.current;
      if (chart) {
        const cur = chart.timeScale().options().barSpacing;
        const next = clampBarSpacing(cur, MAX_BAR_SPACING_ON_FIT_CONTENT);
        if (next !== cur) chart.applyOptions({ timeScale: { barSpacing: next } });
      }
    } else if (isAppendOne || isUpdateLast) {
      series.update(last);
      // Incremental SMA update.
      const idx = candles.length - 1;
      for (const [key, s] of lineSeriesByKeyRef.current.entries()) {
        const period = isSmaKey(key);
        if (period == null) continue;
        const v = computeSmaAtIndex(candles, idx, period);
        if (v == null) continue;
        s.update({ time: last.time, value: v });
      }
      // Incremental entry marker update (derived from SMA 5/20).
      if (entryEnabledRef.current) {
        const f0 = computeSmaAtIndex(candles, idx - 1, 5);
        const s0 = computeSmaAtIndex(candles, idx - 1, 20);
        const f1 = computeSmaAtIndex(candles, idx, 5);
        const s1 = computeSmaAtIndex(candles, idx, 20);
        if (f0 != null && s0 != null && f1 != null && s1 != null && f0 <= s0 && f1 > s1) {
          entryMarkersRef.current = [
            ...entryMarkersRef.current,
            { time: last.time, position: "belowBar", color: "#22c55e", shape: "arrowUp", text: "ENTRY" }
          ];
          syncMarkers();
        }
      }
    } else {
      syncAll();
    }

    appliedRef.current = { len: candles.length, lastTime: last.time as number };
  }, [candles, chartEpoch]);

  useEffect(() => {
    candlesRef.current = candles;
  }, [candles]);

  useEffect(() => {
    const chart = chartRef.current;
    const candleSeries = seriesRef.current;
    if (!chart || !candleSeries) return;

    // --- SMA line series (toggle -> create/remove) ---
    const visibleSmaKeys = Object.keys(visibleFeatures)
      .filter((k) => isSmaKey(k) != null)
      .filter((k) => effectiveVisible(k));

    const want = new Set(visibleSmaKeys);
    for (const [key, s] of lineSeriesByKeyRef.current.entries()) {
      if (!want.has(key)) {
        chart.removeSeries(s);
        lineSeriesByKeyRef.current.delete(key);
      }
    }

    for (const key of want) {
      const period = isSmaKey(key)!;
      let s = lineSeriesByKeyRef.current.get(key);
      if (!s) {
        const color = key === "sma_5" ? "#60a5fa" : key === "sma_20" ? "#f59e0b" : "#a78bfa";
        s = chart.addSeries(LineSeries, { color, lineWidth: 2 });
        lineSeriesByKeyRef.current.set(key, s);
      }
      if (candlesRef.current.length > 0) s.setData(buildSmaLineData(candlesRef.current, period));
    }

    // --- Entry markers (toggle -> recompute/clear) ---
    const showEntry = effectiveVisible("signal.entry");
    if (!showEntry) {
      entryEnabledRef.current = false;
      entryMarkersRef.current = [];
    } else {
      entryEnabledRef.current = true;
      const data = candlesRef.current;
      const nextMarkers: Array<SeriesMarker<Time>> = [];
      for (let i = 0; i < data.length; i++) {
        const f0 = computeSmaAtIndex(data, i - 1, 5);
        const s0 = computeSmaAtIndex(data, i - 1, 20);
        const f1 = computeSmaAtIndex(data, i, 5);
        const s1 = computeSmaAtIndex(data, i, 20);
        if (f0 == null || s0 == null || f1 == null || s1 == null) continue;
        if (f0 <= s0 && f1 > s1) {
          nextMarkers.push({
            time: data[i]!.time,
            position: "belowBar",
            color: "#22c55e",
            shape: "arrowUp",
            text: "ENTRY"
          });
        }
      }
      entryMarkersRef.current = nextMarkers;
    }

    rebuildPivotMarkersFromOverlay();

    // --- Pen confirmed line (toggle -> create/remove) ---
    const showPenConfirmed = effectiveVisible("pen.confirmed");
    if (!showPenConfirmed) {
      if (penSeriesRef.current) {
        chart.removeSeries(penSeriesRef.current);
        penSeriesRef.current = null;
      }
      for (const s of penSegmentSeriesByKeyRef.current.values()) chart.removeSeries(s);
      penSegmentSeriesByKeyRef.current.clear();
      if (anchorPenSeriesRef.current) {
        chart.removeSeries(anchorPenSeriesRef.current);
        anchorPenSeriesRef.current = null;
      }
      setPenPointCount(0);
    } else {
      if (ENABLE_PEN_SEGMENT_COLOR && !replayEnabled) {
        if (penSeriesRef.current) {
          chart.removeSeries(penSeriesRef.current);
          penSeriesRef.current = null;
        }
        const segs = penSegmentsRef.current;
        const want = new Set(segs.map((s) => s.key));
        for (const [k, s] of penSegmentSeriesByKeyRef.current.entries()) {
          if (!want.has(k)) {
            chart.removeSeries(s);
            penSegmentSeriesByKeyRef.current.delete(k);
          }
        }
        for (const seg of segs) {
          const color = seg.highlighted ? "#f59e0b" : "#a78bfa";
          const lineWidth = 2;
          let s = penSegmentSeriesByKeyRef.current.get(seg.key);
          if (!s) {
            s = chart.addSeries(LineSeries, {
              color,
              lineWidth,
              lineStyle: LineStyle.Solid,
              priceLineVisible: false,
              lastValueVisible: false
            });
            penSegmentSeriesByKeyRef.current.set(seg.key, s);
          } else {
            s.applyOptions({ color, lineWidth, lineStyle: LineStyle.Solid, priceLineVisible: false, lastValueVisible: false });
          }
          s.setData(seg.points);
        }
        setPenPointCount(segs.length * 2);
      } else {
        for (const s of penSegmentSeriesByKeyRef.current.values()) chart.removeSeries(s);
        penSegmentSeriesByKeyRef.current.clear();
        if (!penSeriesRef.current) {
          penSeriesRef.current = chart.addSeries(LineSeries, { color: "#a78bfa", lineWidth: 2, lineStyle: LineStyle.Solid });
        }
        penSeriesRef.current.applyOptions({ lineStyle: LineStyle.Solid });
        penSeriesRef.current.setData(penPointsRef.current);
        setPenPointCount(penPointsRef.current.length);
      }

      const anchorPts = anchorPenPointsRef.current;
      if (!anchorPts || anchorPts.length < 2) {
        if (anchorPenSeriesRef.current) {
          chart.removeSeries(anchorPenSeriesRef.current);
          anchorPenSeriesRef.current = null;
        }
      } else {
        const lineStyle = anchorPenIsDashedRef.current ? LineStyle.Dashed : LineStyle.Solid;
        if (!anchorPenSeriesRef.current) {
          anchorPenSeriesRef.current = chart.addSeries(LineSeries, {
            color: "#f59e0b",
            lineWidth: 2,
            lineStyle,
            priceLineVisible: false,
            lastValueVisible: false
          });
        } else {
          anchorPenSeriesRef.current.applyOptions({ color: "#f59e0b", lineWidth: 2, lineStyle });
        }
        anchorPenSeriesRef.current.setData(anchorPts);
      }
    }

    syncMarkers();
  }, [anchorHighlightEpoch, chartEpoch, effectiveVisible, rebuildPivotMarkersFromOverlay, seriesId, syncMarkers, visibleFeatures]);

  useEffect(() => {
    let isActive = true;
    let ws: WebSocket | null = null;

    async function run() {
      try {
        setCandles([]);
        candlesRef.current = [];
        lastWsCandleTimeRef.current = null;
        setLastWsCandleTime(null);
        appliedRef.current = { len: 0, lastTime: null };
        pivotMarkersRef.current = [];
        overlayCatalogRef.current.clear();
        overlayActiveIdsRef.current.clear();
        overlayCursorVersionRef.current = 0;
        overlayPullInFlightRef.current = false;
        followPendingTimeRef.current = null;
        if (followTimerIdRef.current != null) {
          window.clearTimeout(followTimerIdRef.current);
          followTimerIdRef.current = null;
        }
        penSegmentsRef.current = [];
        anchorPenPointsRef.current = null;
        lastFactorAtTimeRef.current = null;
        setAnchorHighlightEpoch((v) => v + 1);
        setPivotCount(0);
        setPenPointCount(0);
        setError(null);
        let cursor = 0;

        // Initial: load tail (latest N).
        const initial = await fetchCandles({ seriesId, limit: INITIAL_TAIL_LIMIT });
        if (!isActive) return;
        logDebugEvent({
          pipe: "read",
          event: "read.http.market_candles_result",
          series_id: seriesId,
          level: "info",
          message: "initial candles loaded",
          data: { count: initial.candles.length }
        });
        if (initial.candles.length > 0) {
          if (replayEnabled) {
            logDebugEvent({
              pipe: "read",
              event: "read.replay.load_initial",
              series_id: seriesId,
              level: "info",
              message: "replay initial load",
              data: { count: initial.candles.length }
            });
            replayAllCandlesRef.current = initial.candles;
            replayPatchRef.current = [];
            replayPatchAppliedIdxRef.current = 0;
            setReplayIndex(0);
            setReplayPlaying(true);

            const endTime = initial.candles[initial.candles.length - 1]!.time as number;
            try {
              const draw = await fetchDrawDelta({ seriesId, cursorVersionId: 0, windowCandles: INITIAL_TAIL_LIMIT, atTime: endTime });
              if (!isActive) return;
              const raw = Array.isArray(draw.instruction_catalog_patch) ? draw.instruction_catalog_patch : [];
              replayPatchRef.current = raw
                .slice()
                .sort((a, b) => (a.visible_time - b.visible_time !== 0 ? a.visible_time - b.visible_time : a.version_id - b.version_id));
            } catch {
              replayPatchRef.current = [];
            }

            overlayCatalogRef.current.clear();
            overlayActiveIdsRef.current.clear();
            overlayCursorVersionRef.current = 0;

            const first = initial.candles[0]!;
            candlesRef.current = [first];
            setCandles([first]);
            applyReplayOverlayAtTime(first.time as number);
            return;
          }

          candlesRef.current = initial.candles;
          setCandles(initial.candles);
          cursor = initial.candles[initial.candles.length - 1]!.time as number;
        }

        // No HTTP catchup probe: WS subscribe catchup + gap handling covers the race window.

        // Initial world frame (preferred) or overlay delta (legacy).
        try {
          if (ENABLE_WORLD_FRAME && !replayEnabled) {
            const frame = await fetchWorldFrameLive({ seriesId, windowCandles: INITIAL_TAIL_LIMIT });
            if (!isActive) return;
            applyWorldFrame(frame);
          } else {
            const delta = await fetchOverlayLikeDelta({ seriesId, cursorVersionId: 0, windowCandles: INITIAL_TAIL_LIMIT });
            if (!isActive) return;
            applyOverlayDelta(delta);
            rebuildPivotMarkersFromOverlay();
            syncMarkers();
            rebuildPenPointsFromOverlay();
            setPenPointCount(ENABLE_PEN_SEGMENT_COLOR ? penSegmentsRef.current.length * 2 : penPointsRef.current.length);
            if (effectiveVisible("pen.confirmed") && penSeriesRef.current) {
              penSeriesRef.current.setData(penPointsRef.current);
            }
            if (cursor > 0) {
              void fetchAndApplyAnchorHighlightAtTime(cursor);
            }
          }
        } catch {
          // ignore overlay/frame errors (best-effort)
        }

        const wsUrl = `${apiWsBase()}/ws/market`;
        ws = new WebSocket(wsUrl);
        ws.onopen = () => {
          logDebugEvent({
            pipe: "read",
            event: "read.ws.market_subscribe",
            series_id: seriesId,
            level: "info",
            message: "ws market subscribe",
            data: { since: cursor > 0 ? cursor : null }
          });
          ws?.send(
            JSON.stringify({ type: "subscribe", series_id: seriesId, since: cursor > 0 ? cursor : null, supports_batch: true })
          );
        };

        const FOLLOW_DEBOUNCE_MS = 1000;

        function scheduleOverlayFollow(t: number) {
          followPendingTimeRef.current = Math.max(followPendingTimeRef.current ?? 0, t);
          if (!isActive) return;
          if (overlayPullInFlightRef.current) return;
          if (followTimerIdRef.current != null) return;
          followTimerIdRef.current = window.setTimeout(() => {
            followTimerIdRef.current = null;
            const next = followPendingTimeRef.current;
            followPendingTimeRef.current = null;
            if (next == null || !isActive) return;
            runOverlayFollowNow(next);
          }, FOLLOW_DEBOUNCE_MS);
        }

        function runOverlayFollowNow(t: number) {
          if (!isActive) return;
          if (overlayPullInFlightRef.current) {
            followPendingTimeRef.current = Math.max(followPendingTimeRef.current ?? 0, t);
            return;
          }
          overlayPullInFlightRef.current = true;

          if (ENABLE_WORLD_FRAME && !replayEnabled) {
            const afterId = overlayCursorVersionRef.current;
            void pollWorldDelta({ seriesId, afterId, windowCandles: INITIAL_TAIL_LIMIT })
              .then((resp) => {
                if (!isActive) return;
                const rec = resp.records?.[0];
                if (rec?.draw_delta) {
                  applyOverlayDelta({
                    active_ids: rec.draw_delta.active_ids ?? [],
                    instruction_catalog_patch: rec.draw_delta.instruction_catalog_patch ?? [],
                    next_cursor: { version_id: rec.draw_delta.next_cursor?.version_id ?? afterId }
                  });
                  rebuildPivotMarkersFromOverlay();
                  syncMarkers();
                  rebuildPenPointsFromOverlay();
                  setPenPointCount(ENABLE_PEN_SEGMENT_COLOR ? penSegmentsRef.current.length * 2 : penPointsRef.current.length);
                  if (effectiveVisible("pen.confirmed") && penSeriesRef.current) {
                    penSeriesRef.current.setData(penPointsRef.current);
                  }
                }
                if (rec?.factor_slices) {
                  applyPenAndAnchorFromFactorSlices(rec.factor_slices);
                } else {
                  void fetchAndApplyAnchorHighlightAtTime(t);
                }
              })
              .catch(() => {
                // ignore
              })
              .finally(() => {
                overlayPullInFlightRef.current = false;
                const pending = followPendingTimeRef.current;
                followPendingTimeRef.current = null;
                if (pending != null && isActive) scheduleOverlayFollow(pending);
              });
            return;
          }

          const cur = overlayCursorVersionRef.current;
          void fetchOverlayLikeDelta({ seriesId, cursorVersionId: cur, windowCandles: INITIAL_TAIL_LIMIT })
            .then((delta) => {
              if (!isActive) return;
              applyOverlayDelta(delta);
              rebuildPivotMarkersFromOverlay();
              syncMarkers();
              rebuildPenPointsFromOverlay();
              if (effectiveVisible("pen.confirmed") && penSeriesRef.current) {
                penSeriesRef.current.setData(penPointsRef.current);
              }
              setPenPointCount(ENABLE_PEN_SEGMENT_COLOR ? penSegmentsRef.current.length * 2 : penPointsRef.current.length);
            })
            .catch(() => {
              // ignore
            })
            .finally(() => {
              overlayPullInFlightRef.current = false;
              const pending = followPendingTimeRef.current;
              followPendingTimeRef.current = null;
              if (pending != null && isActive) scheduleOverlayFollow(pending);
            });

          void fetchAndApplyAnchorHighlightAtTime(t);
        }

        ws.onmessage = (evt) => {
          const msg = typeof evt.data === "string" ? parseMarketWsMessage(evt.data) : null;
          if (!msg) return;

          if (msg.type === "candles_batch") {
            const last = msg.candles.length > 0 ? msg.candles[msg.candles.length - 1] : null;
            const t = last ? last.candle_time : null;
            if (t != null) {
              lastWsCandleTimeRef.current = t;
              setLastWsCandleTime(t);
            }

            setCandles((prev) => {
              const next = mergeCandlesWindow(prev, msg.candles.map(toChartCandle), INITIAL_TAIL_LIMIT);
              candlesRef.current = next;
              return next;
            });

            if (t != null) {
              logDebugEvent({
                pipe: "read",
                event: "read.ws.market_candles_batch",
                series_id: seriesId,
                level: "info",
                message: "ws candles batch",
                data: { count: msg.candles.length, last_time: t }
              });
            }

            if (t != null) {
              logDebugEvent({
                pipe: "read",
                event: "read.ws.market_candle_closed",
                series_id: seriesId,
                level: "info",
                message: "ws candle_closed",
                data: { candle_time: t }
              });
              scheduleOverlayFollow(t);
            }
            return;
          }

          if (msg.type === "candle_forming") {
            const next = toChartCandle(msg.candle);
            candlesRef.current = mergeCandleWindow(candlesRef.current, next, INITIAL_TAIL_LIMIT);
            setCandles((prev) => mergeCandleWindow(prev, next, INITIAL_TAIL_LIMIT));
            return;
          }

          if (msg.type === "candle_closed") {
            const t = msg.candle.candle_time;
            lastWsCandleTimeRef.current = t;
            setLastWsCandleTime(t);

            const next = toChartCandle(msg.candle);
            candlesRef.current = mergeCandleWindow(candlesRef.current, next, INITIAL_TAIL_LIMIT);
            setCandles((prev) => mergeCandleWindow(prev, next, INITIAL_TAIL_LIMIT));
            logDebugEvent({
              pipe: "read",
              event: "read.ws.market_candle_closed",
              series_id: seriesId,
              level: "info",
              message: "ws candle_closed",
              data: { candle_time: t }
            });
            scheduleOverlayFollow(t);
            return;
          }

          if (msg.type === "gap") {
            logDebugEvent({
              pipe: "read",
              event: "read.ws.market_gap",
              series_id: seriesId,
              level: "warn",
              message: "ws gap",
              data: {
                expected_next_time: msg.expected_next_time ?? null,
                actual_time: msg.actual_time ?? null
              }
            });
            const last = candlesRef.current[candlesRef.current.length - 1];
            const fetchParams = last
              ? ({ seriesId, since: last.time as number, limit: 5000 } as const)
              : ({ seriesId, limit: INITIAL_TAIL_LIMIT } as const);

            void fetchCandles(fetchParams).then(({ candles: chunk }) => {
              if (!isActive) return;
              if (chunk.length === 0) return;
              setCandles((prev) => {
                const next = mergeCandlesWindow(prev, chunk, INITIAL_TAIL_LIMIT);
                candlesRef.current = next;
                return next;
              });
            });

            overlayCatalogRef.current.clear();
            overlayActiveIdsRef.current.clear();
            overlayCursorVersionRef.current = 0;
            anchorPenPointsRef.current = null;
            setAnchorHighlightEpoch((v) => v + 1);
            lastFactorAtTimeRef.current = null;
            if (ENABLE_WORLD_FRAME && !replayEnabled) {
              void fetchWorldFrameLive({ seriesId, windowCandles: INITIAL_TAIL_LIMIT })
                .then((frame) => {
                  if (!isActive) return;
                  applyWorldFrame(frame);
                })
                .catch(() => {
                  // ignore
                });
            } else {
              void fetchOverlayLikeDelta({ seriesId, cursorVersionId: 0, windowCandles: INITIAL_TAIL_LIMIT })
                .then((delta) => {
                  if (!isActive) return;
                  applyOverlayDelta(delta);
                  rebuildPivotMarkersFromOverlay();
                  syncMarkers();
                  rebuildPenPointsFromOverlay();
                  if (effectiveVisible("pen.confirmed") && penSeriesRef.current) {
                    penSeriesRef.current.setData(penPointsRef.current);
                  }
                  setPenPointCount(
                    ENABLE_PEN_SEGMENT_COLOR ? penSegmentsRef.current.length * 2 : penPointsRef.current.length
                  );
                })
                .catch(() => {
                  // ignore
                });
              if (last && last.time != null) {
                void fetchAndApplyAnchorHighlightAtTime(last.time as number);
              }
            }
          }
        };
        ws.onerror = () => {
          if (!isActive) return;
          setError("WS error");
        };
      } catch (e: unknown) {
        if (!isActive) return;
        setError(e instanceof Error ? e.message : "Failed to load market candles");
      }
    }

    void run();

    return () => {
      isActive = false;
      if (followTimerIdRef.current != null) {
        window.clearTimeout(followTimerIdRef.current);
        followTimerIdRef.current = null;
      }
      ws?.close();
      setCandles([]);
    };
  }, [
    applyOverlayDelta,
    applyReplayOverlayAtTime,
    applyWorldFrame,
    effectiveVisible,
    fetchAndApplyAnchorHighlightAtTime,
    fetchOverlayLikeDelta,
    fetchWorldFrameAtTime,
    fetchWorldFrameLive,
    rebuildPenPointsFromOverlay,
    rebuildPivotMarkersFromOverlay,
    replayEnabled,
    seriesId,
    syncMarkers
  ]);

  useEffect(() => {
    if (!replayEnabled) return;
    if (!replayPlaying) return;
    const all = replayAllCandlesRef.current;
    if (all.length === 0) return;
    if (replayIndex >= all.length - 1) return;
    const id = window.setTimeout(() => {
      setReplayIndexAndCandles(replayIndex + 1);
    }, replaySpeedMs);
    return () => window.clearTimeout(id);
  }, [replayEnabled, replayIndex, replayPlaying, replaySpeedMs, setReplayIndexAndCandles]);

  return (
    <div
      ref={wheelGuardRef}
      data-testid="chart-view"
      data-series-id={seriesId}
      data-candles-len={String(candles.length)}
      data-last-time={candles.length ? String(candles[candles.length - 1]!.time) : ""}
      data-last-open={candles.length ? String(candles[candles.length - 1]!.open) : ""}
      data-last-high={candles.length ? String(candles[candles.length - 1]!.high) : ""}
      data-last-low={candles.length ? String(candles[candles.length - 1]!.low) : ""}
      data-last-close={candles.length ? String(candles[candles.length - 1]!.close) : ""}
      data-last-ws-candle-time={lastWsCandleTime != null ? String(lastWsCandleTime) : ""}
      data-chart-epoch={String(chartEpoch)}
      data-bar-spacing={barSpacing != null ? String(barSpacing) : ""}
      data-pivot-count={String(pivotCount)}
      data-pen-point-count={String(penPointCount)}
      className="relative h-full w-full"
      title={error ?? undefined}
    >
      {ENABLE_REPLAY_V1 ? (
        <div className="absolute right-2 top-2 z-20 flex items-center gap-2 rounded border border-white/10 bg-black/40 px-2 py-1 text-[11px] text-white/80">
          <button
            className="rounded bg-white/10 px-2 py-1 text-white/90 hover:bg-white/15"
            onClick={() => {
              setReplayEnabled((v) => {
                const next = !v;
                setReplayPlaying(next);
                return next;
              });
            }}
          >
            Replay {replayEnabled ? "ON" : "OFF"}
          </button>
          {replayEnabled ? (
            <>
              <button
                className="rounded bg-white/10 px-2 py-1 text-white/90 hover:bg-white/15"
                onClick={() => setReplayPlaying((v) => !v)}
              >
                {replayPlaying ? "Pause" : "Play"}
              </button>
              <select
                className="rounded bg-white/10 px-2 py-1 text-white/90"
                value={replaySpeedMs}
                onChange={(e) => setReplaySpeedMs(Number(e.target.value))}
                title="Replay speed"
              >
                <option value={50}>20x</option>
                <option value={100}>10x</option>
                <option value={200}>5x</option>
                <option value={400}>2x</option>
                <option value={800}>1x</option>
              </select>
              <input
                className="w-56"
                type="range"
                min={0}
                max={Math.max(0, replayAllCandlesRef.current.length - 1)}
                value={replayIndex}
                onChange={(e) => setReplayIndexAndCandles(Number(e.target.value), { pause: true })}
                title="Seek"
              />
              <span className="font-mono text-white/70" title="index / total">
                {replayAllCandlesRef.current.length ? `${replayIndex + 1}/${replayAllCandlesRef.current.length}` : "0/0"}
              </span>
            </>
          ) : null}
        </div>
      ) : null}

      <div
        ref={(el) => {
          containerRef.current = el;
          resizeRef(el);
        }}
        className="h-full w-full"
      />

      {error ? (
        <div className="pointer-events-none absolute left-2 top-2 rounded border border-red-500/30 bg-red-950/60 px-2 py-1 text-[11px] text-red-200">
          {error}
        </div>
      ) : candles.length === 0 ? (
        <div className="pointer-events-none absolute left-2 top-2 rounded border border-white/10 bg-black/40 px-2 py-1 text-[11px] text-white/70">
          Loading candles…
        </div>
      ) : null}
    </div>
  );
}
