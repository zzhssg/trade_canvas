import { useCallback, useEffect, useRef, useState } from "react";

import type { LiveLoadStatus } from "./liveSessionRuntimeTypes";
import type { Candle } from "./types";

export function useChartViewState(liveLoadLabels: Record<LiveLoadStatus, string>) {
  const [candles, setCandles] = useState<Candle[]>([]);
  const [barSpacing, setBarSpacing] = useState<number | null>(null);
  const [lastWsCandleTime, setLastWsCandleTime] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [liveLoadStatus, setLiveLoadStatus] = useState<LiveLoadStatus>("idle");
  const [liveLoadMessage, setLiveLoadMessage] = useState<string>(liveLoadLabels.idle);
  const [toastMessage, setToastMessage] = useState<string | null>(null);
  const [replayMaskX, setReplayMaskX] = useState<number | null>(null);
  const toastTimerRef = useRef<number | null>(null);

  const showToast = useCallback((message: string) => {
    setToastMessage(message);
    if (toastTimerRef.current != null) window.clearTimeout(toastTimerRef.current);
    toastTimerRef.current = window.setTimeout(() => {
      setToastMessage(null);
      toastTimerRef.current = null;
    }, 3200);
  }, []);

  const updateLiveLoadState = useCallback(
    (status: LiveLoadStatus, message?: string) => {
      setLiveLoadStatus(status);
      if (typeof message === "string" && message.trim().length > 0) {
        setLiveLoadMessage(message.trim());
        return;
      }
      setLiveLoadMessage(liveLoadLabels[status]);
    },
    [liveLoadLabels]
  );

  useEffect(() => {
    return () => {
      if (toastTimerRef.current != null) {
        window.clearTimeout(toastTimerRef.current);
        toastTimerRef.current = null;
      }
    };
  }, []);

  return {
    candles,
    setCandles,
    barSpacing,
    setBarSpacing,
    lastWsCandleTime,
    setLastWsCandleTime,
    error,
    setError,
    liveLoadStatus,
    liveLoadMessage,
    updateLiveLoadState,
    toastMessage,
    showToast,
    replayMaskX,
    setReplayMaskX
  };
}
