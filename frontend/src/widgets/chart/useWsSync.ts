import { useCallback } from "react";

import { logDebugEvent } from "../../debug/debug";
import { apiWsBase } from "../../lib/api";

import { parseMarketWsMessage, type MarketWsMessage } from "./ws";

type BatchMessage = Extract<MarketWsMessage, { type: "candles_batch" }>;
type SystemMessage = Extract<MarketWsMessage, { type: "system" }>;
type FormingMessage = Extract<MarketWsMessage, { type: "candle_forming" }>;
type ClosedMessage = Extract<MarketWsMessage, { type: "candle_closed" }>;
type GapMessage = Extract<MarketWsMessage, { type: "gap" }>;

type ConnectMarketWsOptions = {
  since: number | null;
  isActive: () => boolean;
  onCandlesBatch: (msg: BatchMessage) => void;
  onSystem: (msg: SystemMessage) => void;
  onCandleForming: (msg: FormingMessage) => void;
  onCandleClosed: (msg: ClosedMessage) => void;
  onGap: (msg: GapMessage) => void;
  onSocketError: () => void;
};

type UseWsSyncArgs = {
  seriesId: string;
};

export function useWsSync({ seriesId }: UseWsSyncArgs) {
  const openMarketWs = useCallback(
    ({
      since,
      isActive,
      onCandlesBatch,
      onSystem,
      onCandleForming,
      onCandleClosed,
      onGap,
      onSocketError
    }: ConnectMarketWsOptions): WebSocket => {
      const ws = new WebSocket(`${apiWsBase()}/ws/market`);
      ws.onopen = () => {
        logDebugEvent({
          pipe: "read",
          event: "read.ws.market_subscribe",
          series_id: seriesId,
          level: "info",
          message: "ws market subscribe",
          data: { since: since ?? null }
        });
        ws.send(JSON.stringify({ type: "subscribe", series_id: seriesId, since, supports_batch: true }));
      };
      ws.onmessage = (evt) => {
        if (!isActive()) return;
        const msg = typeof evt.data === "string" ? parseMarketWsMessage(evt.data) : null;
        if (!msg) return;

        if (msg.type === "candles_batch") {
          onCandlesBatch(msg);
          return;
        }
        if (msg.type === "system") {
          onSystem(msg);
          return;
        }
        if (msg.type === "candle_forming") {
          onCandleForming(msg);
          return;
        }
        if (msg.type === "candle_closed") {
          onCandleClosed(msg);
          return;
        }
        if (msg.type === "gap") {
          onGap(msg);
          return;
        }
      };
      ws.onerror = () => {
        if (!isActive()) return;
        onSocketError();
      };
      return ws;
    },
    [seriesId]
  );

  return { openMarketWs };
}
