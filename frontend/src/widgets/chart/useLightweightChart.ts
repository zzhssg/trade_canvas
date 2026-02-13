import {
  CandlestickSeries,
  createChart,
  createSeriesMarkers,
  type IChartApi,
  type ISeriesApi,
  type ISeriesMarkersPluginApi,
  type Time
} from "lightweight-charts";
import { useEffect, useRef, useState } from "react";

import { formatChartTimeYmdHm } from "./timeFormat";

type Params = {
  containerRef: React.RefObject<HTMLDivElement | null>;
  width?: number;
  height?: number;
  onCreated?: (ctx: {
    chart: IChartApi;
    candleSeries: ISeriesApi<"Candlestick">;
    markersApi: ISeriesMarkersPluginApi<Time>;
  }) => void;
  onCleanup?: () => void;
};

/**
 * lightweight-charts 实例管理 hook。
 *
 * 创建暗色主题 chart + CandlestickSeries + markers plugin。
 * chartEpoch 每次 chart 重建时递增, 下游 effect 可依赖它感知图表就绪。
 * onCreated/onCleanup 通过 callback ref 保持引用稳定, 不触发 effect 重跑。
 */
export function useLightweightChart({ containerRef, width, height, onCreated, onCleanup }: Params) {
  const chartRef = useRef<IChartApi | null>(null);
  const candleSeriesRef = useRef<ISeriesApi<"Candlestick"> | null>(null);
  const markersApiRef = useRef<ISeriesMarkersPluginApi<Time> | null>(null);
  /** 每次 chart 实例重建递增, 用于通知下游 effect 图表已就绪 */
  const [chartEpoch, setChartEpoch] = useState(0);

  const onCreatedRef = useRef<Params["onCreated"]>(onCreated);
  const onCleanupRef = useRef<Params["onCleanup"]>(onCleanup);

  useEffect(() => {
    onCreatedRef.current = onCreated;
  }, [onCreated]);

  useEffect(() => {
    onCleanupRef.current = onCleanup;
  }, [onCleanup]);

  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;
    if (chartRef.current) return;

    const rect = container.getBoundingClientRect();
    const initialWidth = Math.max(1, Math.floor(rect.width));
    const initialHeight = Math.max(1, Math.floor(rect.height));

    const chart = createChart(container, {
      width: initialWidth,
      height: initialHeight,
      layout: {
        background: { color: "#0b0f14" },
        textColor: "#c9d1d9"
      },
      localization: {
        // Crosshair time label formatting (time axis label), keep ticks unchanged.
        timeFormatter: formatChartTimeYmdHm
      },
      grid: {
        vertLines: { color: "rgba(255,255,255,0.05)" },
        horzLines: { color: "rgba(255,255,255,0.05)" }
      },
      rightPriceScale: { borderColor: "rgba(255,255,255,0.15)" },
      timeScale: { borderColor: "rgba(255,255,255,0.15)" },
      crosshair: {
        mode: 0,
        horzLine: {
          labelVisible: true
        }
      },
      handleScroll: {
        mouseWheel: false,
        pressedMouseMove: true,
        horzTouchDrag: true,
        vertTouchDrag: true
      },
      handleScale: {
        mouseWheel: false,
        pinch: true,
        axisPressedMouseMove: true
      }
    });

    const series = chart.addSeries(CandlestickSeries, {
      upColor: "#22c55e",
      downColor: "#ef4444",
      wickUpColor: "#22c55e",
      wickDownColor: "#ef4444",
      borderVisible: false
    });

    const markersApi = createSeriesMarkers(series);

    chartRef.current = chart;
    candleSeriesRef.current = series;
    markersApiRef.current = markersApi;
    setChartEpoch((e) => e + 1);
    onCreatedRef.current?.({ chart, candleSeries: series, markersApi });

    return () => {
      try {
        markersApi.detach();
      } catch {
        // ignore detach errors on fast remount/unmount (StrictMode)
      }
      markersApiRef.current = null;

      try {
        chart.remove();
      } catch {
        // ignore remove errors on fast remount/unmount (StrictMode)
      }
      chartRef.current = null;
      candleSeriesRef.current = null;
      onCleanupRef.current?.();
    };
  }, [containerRef]);

  useEffect(() => {
    const chart = chartRef.current;
    if (!chart) return;
    if (!width || !height) return;
    chart.applyOptions({ width, height });
  }, [width, height, chartEpoch]);

  return { chartRef, candleSeriesRef, markersApiRef, chartEpoch };
}
