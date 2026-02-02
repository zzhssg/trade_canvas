import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useMemo, useState } from "react";

import { apiJson, apiUrl } from "../lib/api";
import type { TopMarketsResponse } from "../contracts/api";

export type MarketMode = "spot" | "futures";

type Params = {
  market: MarketMode;
  quoteAsset?: string;
  limit?: number;
  intervalS?: number;
};

type SseState = "connecting" | "connected";

function buildQueryString(params: Required<Pick<Params, "market" | "quoteAsset" | "limit">> & { force?: boolean }) {
  const qs = new URLSearchParams({
    exchange: "binance",
    market: params.market,
    quote_asset: params.quoteAsset,
    limit: String(params.limit),
    ...(params.force ? { force: "1" } : {})
  });
  return qs.toString();
}

function buildStreamQueryString(params: Required<Pick<Params, "market" | "quoteAsset" | "limit" | "intervalS">>) {
  const qs = new URLSearchParams({
    exchange: "binance",
    market: params.market,
    quote_asset: params.quoteAsset,
    limit: String(params.limit),
    interval_s: String(params.intervalS)
  });
  return qs.toString();
}

export function useTopMarkets(params: Params) {
  const queryClient = useQueryClient();
  const quoteAsset = (params.quoteAsset ?? "USDT").toUpperCase();
  const limit = params.limit ?? 20;
  const intervalS = params.intervalS ?? 2;

  const queryKey = useMemo(() => ["topMarkets", params.market, quoteAsset, limit] as const, [params.market, quoteAsset, limit]);
  const [sseState, setSseState] = useState<SseState>("connecting");

  const query = useQuery({
    queryKey,
    queryFn: async () => {
      const qs = buildQueryString({ market: params.market, quoteAsset, limit });
      return await apiJson<TopMarketsResponse>(`/api/market/top_markets?${qs}`);
    },
    staleTime: 20_000
  });

  useEffect(() => {
    const qs = buildStreamQueryString({ market: params.market, quoteAsset, limit, intervalS });
    const url = apiUrl(`/api/market/top_markets/stream?${qs}`);
    const es = new EventSource(url);

    const onTopMarkets = (evt: Event) => {
      try {
        const data = JSON.parse((evt as MessageEvent).data) as TopMarketsResponse;
        setSseState("connected");
        queryClient.setQueryData(queryKey, data);
      } catch {
        // Ignore parse errors; the HTTP query is the fallback.
      }
    };

    const onError = () => {
      // EventSource will auto-reconnect.
      setSseState("connecting");
    };

    es.addEventListener("top_markets", onTopMarkets);
    es.addEventListener("error", onError);
    return () => es.close();
  }, [intervalS, limit, params.market, queryClient, queryKey, quoteAsset]);

  const refresh = async () => {
    const qs = buildQueryString({ market: params.market, quoteAsset, limit, force: true });
    const data = await apiJson<TopMarketsResponse>(`/api/market/top_markets?${qs}`);
    queryClient.setQueryData(queryKey, data);
    return data;
  };

  return { ...query, sseState, refresh };
}

