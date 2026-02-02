import { CandlestickSeries, createChart, type IChartApi, type UTCTimestamp } from "lightweight-charts";
import { useEffect, useMemo, useRef } from "react";
import useResizeObserver from "use-resize-observer";

type Candle = {
  time: UTCTimestamp;
  open: number;
  high: number;
  low: number;
  close: number;
};

function makeMockCandles(count: number): Candle[] {
  const now = Math.floor(Date.now() / 1000);
  const start = now - count * 60;
  let price = 100;

  const candles: Candle[] = [];
  for (let i = 0; i < count; i += 1) {
    const open = price;
    const close = open + (Math.random() - 0.5) * 2;
    const high = Math.max(open, close) + Math.random() * 1.2;
    const low = Math.min(open, close) - Math.random() * 1.2;
    price = close;
    candles.push({
      time: (start + i * 60) as UTCTimestamp,
      open,
      high,
      low,
      close
    });
  }
  return candles;
}

export function ChartView() {
  const chartRef = useRef<IChartApi | null>(null);
  const containerRef = useRef<HTMLDivElement | null>(null);
  const { ref: resizeRef, width, height } = useResizeObserver<HTMLDivElement>();

  const data = useMemo(() => makeMockCandles(200), []);

  useEffect(() => {
    if (!containerRef.current) return;
    if (!width || !height) return;
    if (chartRef.current) return;

    const chart = createChart(containerRef.current, {
      width,
      height,
      layout: {
        background: { color: "#0b0f14" },
        textColor: "#c9d1d9"
      },
      grid: {
        vertLines: { color: "rgba(255,255,255,0.05)" },
        horzLines: { color: "rgba(255,255,255,0.05)" }
      },
      rightPriceScale: { borderColor: "rgba(255,255,255,0.15)" },
      timeScale: { borderColor: "rgba(255,255,255,0.15)" },
      crosshair: { mode: 1 }
    });

    const series = chart.addSeries(CandlestickSeries, {
      upColor: "#22c55e",
      downColor: "#ef4444",
      wickUpColor: "#22c55e",
      wickDownColor: "#ef4444",
      borderVisible: false
    });

    series.setData(data);
    chart.timeScale().fitContent();

    chartRef.current = chart;

    return () => {
      chart.remove();
      chartRef.current = null;
    };
  }, [data, width, height]);

  useEffect(() => {
    if (!chartRef.current) return;
    if (!width || !height) return;
    chartRef.current.applyOptions({ width, height });
  }, [width, height]);

  return (
    <div
      ref={(el) => {
        containerRef.current = el;
        resizeRef(el);
      }}
      className="h-full w-full"
    />
  );
}
