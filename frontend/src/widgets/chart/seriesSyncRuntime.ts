import { LineSeries, LineStyle, type IChartApi, type ISeriesApi, type SeriesMarker, type Time } from "lightweight-charts";
import type { MutableRefObject } from "react";

import { MAX_BAR_SPACING_ON_FIT_CONTENT, clampBarSpacing } from "./barSpacing";
import { buildSmaLineData, computeSmaAtIndex, isSmaKey } from "./sma";
import type { Candle } from "./types";
import type { PenLinePoint, PenSegment } from "./penAnchorRuntime";

type ReplayPenPreviewFeature = "pen.extending" | "pen.candidate";

type SyncCandlesToSeriesArgs = {
  candles: Candle[];
  series: ISeriesApi<"Candlestick">;
  chart: IChartApi | null;
  appliedRef: MutableRefObject<{ len: number; lastTime: number | null }>;
  lineSeriesByKeyRef: MutableRefObject<Map<string, ISeriesApi<"Line">>>;
  entryEnabledRef: MutableRefObject<boolean>;
  entryMarkersRef: MutableRefObject<Array<SeriesMarker<Time>>>;
  syncMarkers: () => void;
};

export function syncCandlesToSeries(args: SyncCandlesToSeriesArgs) {
  const { candles, series, chart, appliedRef, lineSeriesByKeyRef, entryEnabledRef, entryMarkersRef, syncMarkers } = args;
  if (candles.length === 0) return;

  const last = candles[candles.length - 1]!;
  const previous = appliedRef.current;

  const isAppendOne = previous.len === candles.length - 1 && (previous.lastTime == null || (last.time as number) >= previous.lastTime);
  const isUpdateLast = previous.len === candles.length && previous.lastTime != null && (last.time as number) === previous.lastTime;

  const syncAll = () => {
    series.setData(candles);
    for (const [key, item] of lineSeriesByKeyRef.current.entries()) {
      const period = isSmaKey(key);
      if (period != null) item.setData(buildSmaLineData(candles, period));
    }
    syncMarkers();
  };

  if (previous.len === 0) {
    syncAll();
    chart?.timeScale().fitContent();
    if (chart) {
      const current = chart.timeScale().options().barSpacing;
      const next = clampBarSpacing(current, MAX_BAR_SPACING_ON_FIT_CONTENT);
      if (next !== current) chart.applyOptions({ timeScale: { barSpacing: next } });
    }
  } else if (isAppendOne || isUpdateLast) {
    series.update(last);
    const index = candles.length - 1;
    for (const [key, item] of lineSeriesByKeyRef.current.entries()) {
      const period = isSmaKey(key);
      if (period == null) continue;
      const value = computeSmaAtIndex(candles, index, period);
      if (value == null) continue;
      item.update({ time: last.time, value });
    }

    if (entryEnabledRef.current) {
      const f0 = computeSmaAtIndex(candles, index - 1, 5);
      const s0 = computeSmaAtIndex(candles, index - 1, 20);
      const f1 = computeSmaAtIndex(candles, index, 5);
      const s1 = computeSmaAtIndex(candles, index, 20);
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
}

type SyncOverlayLayersArgs = {
  chart: IChartApi;
  visibleFeatures: Record<string, boolean | undefined>;
  effectiveVisible: (key: string) => boolean;
  candlesRef: MutableRefObject<Candle[]>;
  lineSeriesByKeyRef: MutableRefObject<Map<string, ISeriesApi<"Line">>>;
  entryEnabledRef: MutableRefObject<boolean>;
  entryMarkersRef: MutableRefObject<Array<SeriesMarker<Time>>>;
  rebuildPivotMarkersFromOverlay: () => void;
  rebuildAnchorSwitchMarkersFromOverlay: () => void;
  rebuildOverlayPolylinesFromOverlay: () => void;
  penSeriesRef: MutableRefObject<ISeriesApi<"Line"> | null>;
  penSegmentSeriesByKeyRef: MutableRefObject<Map<string, ISeriesApi<"Line">>>;
  penSegmentsRef: MutableRefObject<PenSegment[]>;
  penPointsRef: MutableRefObject<PenLinePoint[]>;
  anchorPenSeriesRef: MutableRefObject<ISeriesApi<"Line"> | null>;
  anchorPenPointsRef: MutableRefObject<PenLinePoint[] | null>;
  anchorPenIsDashedRef: MutableRefObject<boolean>;
  replayPenPreviewSeriesByFeatureRef: MutableRefObject<Record<ReplayPenPreviewFeature, ISeriesApi<"Line"> | null>>;
  replayPenPreviewPointsRef: MutableRefObject<Record<ReplayPenPreviewFeature, PenLinePoint[]>>;
  enablePenSegmentColor: boolean;
  enableAnchorTopLayer: boolean;
  replayEnabled: boolean;
  setPenPointCount: (value: number) => void;
  syncMarkers: () => void;
};

export function syncOverlayLayers(args: SyncOverlayLayersArgs) {
  const {
    chart,
    visibleFeatures,
    effectiveVisible,
    candlesRef,
    lineSeriesByKeyRef,
    entryEnabledRef,
    entryMarkersRef,
    rebuildPivotMarkersFromOverlay,
    rebuildAnchorSwitchMarkersFromOverlay,
    rebuildOverlayPolylinesFromOverlay,
    penSeriesRef,
    penSegmentSeriesByKeyRef,
    penSegmentsRef,
    penPointsRef,
    anchorPenSeriesRef,
    anchorPenPointsRef,
    anchorPenIsDashedRef,
    replayPenPreviewSeriesByFeatureRef,
    replayPenPreviewPointsRef,
    enablePenSegmentColor,
    enableAnchorTopLayer,
    replayEnabled,
    setPenPointCount,
    syncMarkers
  } = args;

  const visibleSmaKeys = Object.keys(visibleFeatures)
    .filter((key) => isSmaKey(key) != null)
    .filter((key) => effectiveVisible(key));

  const wantSma = new Set(visibleSmaKeys);
  for (const [key, series] of lineSeriesByKeyRef.current.entries()) {
    if (!wantSma.has(key)) {
      chart.removeSeries(series);
      lineSeriesByKeyRef.current.delete(key);
    }
  }

  for (const key of wantSma) {
    const period = isSmaKey(key)!;
    let series = lineSeriesByKeyRef.current.get(key);
    if (!series) {
      const color = key === "sma_5" ? "#60a5fa" : key === "sma_20" ? "#f59e0b" : "#a78bfa";
      series = chart.addSeries(LineSeries, { color, lineWidth: 2 });
      lineSeriesByKeyRef.current.set(key, series);
    }
    if (candlesRef.current.length > 0) series.setData(buildSmaLineData(candlesRef.current, period));
  }

  const showEntry = effectiveVisible("signal.entry");
  if (!showEntry) {
    entryEnabledRef.current = false;
    entryMarkersRef.current = [];
  } else {
    entryEnabledRef.current = true;
    const data = candlesRef.current;
    const nextMarkers: Array<SeriesMarker<Time>> = [];
    for (let index = 0; index < data.length; index += 1) {
      const f0 = computeSmaAtIndex(data, index - 1, 5);
      const s0 = computeSmaAtIndex(data, index - 1, 20);
      const f1 = computeSmaAtIndex(data, index, 5);
      const s1 = computeSmaAtIndex(data, index, 20);
      if (f0 == null || s0 == null || f1 == null || s1 == null) continue;
      if (f0 <= s0 && f1 > s1) {
        nextMarkers.push({
          time: data[index]!.time,
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
  rebuildAnchorSwitchMarkersFromOverlay();
  rebuildOverlayPolylinesFromOverlay();

  const showPenConfirmed = effectiveVisible("pen.confirmed");
  const penPointTotal =
    enablePenSegmentColor && !replayEnabled ? penSegmentsRef.current.length * 2 : penPointsRef.current.length;

  const clearReplayPenPreviewSeries = () => {
    for (const feature of ["pen.extending", "pen.candidate"] as ReplayPenPreviewFeature[]) {
      const series = replayPenPreviewSeriesByFeatureRef.current[feature];
      if (series) chart.removeSeries(series);
      replayPenPreviewSeriesByFeatureRef.current[feature] = null;
    }
  };

  if (!showPenConfirmed) {
    if (penSeriesRef.current) {
      chart.removeSeries(penSeriesRef.current);
      penSeriesRef.current = null;
    }
    for (const series of penSegmentSeriesByKeyRef.current.values()) chart.removeSeries(series);
    penSegmentSeriesByKeyRef.current.clear();
    if (anchorPenSeriesRef.current) {
      chart.removeSeries(anchorPenSeriesRef.current);
      anchorPenSeriesRef.current = null;
    }
    clearReplayPenPreviewSeries();
  } else {
    if (enablePenSegmentColor && !replayEnabled) {
      if (penSeriesRef.current) {
        chart.removeSeries(penSeriesRef.current);
        penSeriesRef.current = null;
      }
      const segments = penSegmentsRef.current;
      const want = new Set(segments.map((segment) => segment.key));
      for (const [key, series] of penSegmentSeriesByKeyRef.current.entries()) {
        if (!want.has(key)) {
          chart.removeSeries(series);
          penSegmentSeriesByKeyRef.current.delete(key);
        }
      }
      for (const segment of segments) {
        const color = segment.highlighted ? "#f59e0b" : "#ffffff";
        let series = penSegmentSeriesByKeyRef.current.get(segment.key);
        if (!series) {
          series = chart.addSeries(LineSeries, {
            color,
            lineWidth: 2,
            lineStyle: LineStyle.Solid,
            priceLineVisible: false,
            lastValueVisible: false
          });
          penSegmentSeriesByKeyRef.current.set(segment.key, series);
        } else {
          series.applyOptions({ color, lineWidth: 2, lineStyle: LineStyle.Solid, priceLineVisible: false, lastValueVisible: false });
        }
        series.setData(segment.points);
      }
    } else {
      for (const series of penSegmentSeriesByKeyRef.current.values()) chart.removeSeries(series);
      penSegmentSeriesByKeyRef.current.clear();
      if (!penSeriesRef.current) {
        penSeriesRef.current = chart.addSeries(LineSeries, {
          color: "#ffffff",
          lineWidth: 2,
          lineStyle: LineStyle.Solid,
          priceLineVisible: false,
          lastValueVisible: false
        });
      }
      penSeriesRef.current.applyOptions({ lineStyle: LineStyle.Solid, priceLineVisible: false, lastValueVisible: false });
      penSeriesRef.current.setData(penPointsRef.current);
    }

    const anchorPoints = anchorPenPointsRef.current;
    if (enableAnchorTopLayer) {
      if (anchorPenSeriesRef.current) {
        chart.removeSeries(anchorPenSeriesRef.current);
        anchorPenSeriesRef.current = null;
      }
    } else if (!anchorPoints || anchorPoints.length < 2) {
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
      anchorPenSeriesRef.current.setData(anchorPoints);
    }

    const previewDefs: Array<{ feature: ReplayPenPreviewFeature; lineStyle: LineStyle }> = [
      { feature: "pen.extending", lineStyle: LineStyle.Dashed },
      { feature: "pen.candidate", lineStyle: LineStyle.Dashed }
    ];

    for (const preview of previewDefs) {
      const points = replayPenPreviewPointsRef.current[preview.feature];
      const shouldShow = replayEnabled && effectiveVisible(preview.feature) && points.length >= 2;
      const existing = replayPenPreviewSeriesByFeatureRef.current[preview.feature];
      if (!shouldShow) {
        if (existing) chart.removeSeries(existing);
        replayPenPreviewSeriesByFeatureRef.current[preview.feature] = null;
        continue;
      }
      if (!existing) {
        replayPenPreviewSeriesByFeatureRef.current[preview.feature] = chart.addSeries(LineSeries, {
          color: "#ffffff",
          lineWidth: 2,
          lineStyle: preview.lineStyle,
          priceLineVisible: false,
          lastValueVisible: false
        });
      } else {
        existing.applyOptions({
          color: "#ffffff",
          lineWidth: 2,
          lineStyle: preview.lineStyle,
          priceLineVisible: false,
          lastValueVisible: false
        });
      }
      replayPenPreviewSeriesByFeatureRef.current[preview.feature]?.setData(points);
    }
  }

  setPenPointCount(penPointTotal);
  syncMarkers();
}
