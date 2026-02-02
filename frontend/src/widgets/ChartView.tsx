import {
  LineSeries,
  type IChartApi,
  type ISeriesApi,
  type SeriesMarker,
  type Time,
  type UTCTimestamp
} from "lightweight-charts";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import useResizeObserver from "use-resize-observer";

import { apiWsBase } from "../lib/api";
import { FACTOR_CATALOG, getFactorParentsBySubKey } from "../services/factorCatalog";
import { useFactorStore } from "../state/factorStore";
import { useUiStore } from "../state/uiStore";

import { fetchCandles, fetchDrawDelta, fetchOverlayDelta } from "./chart/api";
import { mergeCandle, toChartCandle } from "./chart/candles";
import { buildSmaLineData, computeSmaAtIndex, isSmaKey } from "./chart/sma";
import type { Candle, OverlayInstructionPatchItemV1, OverlayLikeDeltaV1 } from "./chart/types";
import { useLightweightChart } from "./chart/useLightweightChart";
import { parseMarketWsMessage } from "./chart/ws";

const INITIAL_TAIL_LIMIT = 2000;
const ENABLE_DRAW_DELTA = import.meta.env.VITE_ENABLE_DRAW_DELTA === "1";

export function ChartView() {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const { ref: resizeRef, width, height } = useResizeObserver<HTMLDivElement>();

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

  const penSeriesRef = useRef<ISeriesApi<"Line"> | null>(null);
  const penPointsRef = useRef<Array<{ time: UTCTimestamp; value: number }>>([]);
  const [penPointCount, setPenPointCount] = useState(0);

  const { chartRef, candleSeriesRef: seriesRef, markersApiRef, chartEpoch } = useLightweightChart({
    containerRef,
    width,
    height,
    onCreated: ({ chart, candleSeries }) => {
      const existing = candlesRef.current;
      if (existing.length > 0) {
        candleSeries.setData(existing);
        chart.timeScale().fitContent();
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
      overlayPullInFlightRef.current = false;
      entryEnabledRef.current = false;
      appliedRef.current = { len: 0, lastTime: null };
    }
  });

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
        if (!position || !shape || !color) continue;

        next.push({ time: t as UTCTimestamp, position, color, shape, text });
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
      setPenPointCount(0);
    } else {
      if (!penSeriesRef.current) {
        penSeriesRef.current = chart.addSeries(LineSeries, { color: "#a78bfa", lineWidth: 2 });
      }
      penSeriesRef.current.setData(penPointsRef.current);
      setPenPointCount(penPointsRef.current.length);
    }

    syncMarkers();
  }, [chartEpoch, effectiveVisible, rebuildPivotMarkersFromOverlay, seriesId, syncMarkers, visibleFeatures]);

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
        setPivotCount(0);
        setPenPointCount(0);
        setError(null);
        let cursor = 0;

        // Initial: load tail (latest N).
        const initial = await fetchCandles({ seriesId, limit: INITIAL_TAIL_LIMIT });
        if (!isActive) return;
        if (initial.candles.length > 0) {
          candlesRef.current = initial.candles;
          setCandles(initial.candles);
          cursor = initial.candles[initial.candles.length - 1]!.time as number;
        }

        // No HTTP catchup probe: WS subscribe catchup + gap handling covers the race window.

        // Initial overlay delta (tail window).
        try {
          const delta = await fetchOverlayLikeDelta({ seriesId, cursorVersionId: 0, windowCandles: INITIAL_TAIL_LIMIT });
          if (!isActive) return;
          applyOverlayDelta(delta);
          rebuildPivotMarkersFromOverlay();
          syncMarkers();
          rebuildPenPointsFromOverlay();
          setPenPointCount(penPointsRef.current.length);
          if (effectiveVisible("pen.confirmed") && penSeriesRef.current) {
            penSeriesRef.current.setData(penPointsRef.current);
          }
        } catch {
          // ignore overlay errors (best-effort)
        }

        const wsUrl = `${apiWsBase()}/ws/market`;
        ws = new WebSocket(wsUrl);
        ws.onopen = () => {
          ws?.send(JSON.stringify({ type: "subscribe", series_id: seriesId, since: cursor > 0 ? cursor : null }));
        };
        ws.onmessage = (evt) => {
          const msg = typeof evt.data === "string" ? parseMarketWsMessage(evt.data) : null;
          if (!msg) return;

          if (msg.type === "candle_forming") {
            const next = toChartCandle(msg.candle);
            candlesRef.current = mergeCandle(candlesRef.current, next);
            setCandles((prev) => mergeCandle(prev, next));
            return;
          }

          if (msg.type === "candle_closed") {
            const t = msg.candle.candle_time;
            lastWsCandleTimeRef.current = t;
            setLastWsCandleTime(t);

            const next = toChartCandle(msg.candle);
            candlesRef.current = mergeCandle(candlesRef.current, next);
            setCandles((prev) => mergeCandle(prev, next));

            if (!overlayPullInFlightRef.current) {
              overlayPullInFlightRef.current = true;
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
                  setPenPointCount(penPointsRef.current.length);
                })
                .catch(() => {
                  // ignore
                })
                .finally(() => {
                  overlayPullInFlightRef.current = false;
                });
            }
            return;
          }

          if (msg.type === "gap") {
            const last = candlesRef.current[candlesRef.current.length - 1];
            const fetchParams = last
              ? ({ seriesId, since: last.time as number, limit: 5000 } as const)
              : ({ seriesId, limit: INITIAL_TAIL_LIMIT } as const);

            void fetchCandles(fetchParams).then(({ candles: chunk }) => {
              if (!isActive) return;
              if (chunk.length === 0) return;
              setCandles((prev) => {
                let next = prev;
                for (const c of chunk) next = mergeCandle(next, c);
                candlesRef.current = next;
                return next;
              });
            });

            overlayCatalogRef.current.clear();
            overlayActiveIdsRef.current.clear();
            overlayCursorVersionRef.current = 0;
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
                setPenPointCount(penPointsRef.current.length);
              })
              .catch(() => {
                // ignore
              });
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
      ws?.close();
      setCandles([]);
    };
  }, [
    applyOverlayDelta,
    effectiveVisible,
    fetchOverlayLikeDelta,
    rebuildPenPointsFromOverlay,
    rebuildPivotMarkersFromOverlay,
    seriesId,
    syncMarkers
  ]);

  return (
    <div
      data-testid="chart-view"
      data-series-id={seriesId}
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
