import type { APIRequestContext } from "@playwright/test";
import { expect, test } from "@playwright/test";

import type { GetCandlesResponse } from "../src/widgets/chart/types";

const frontendBase = process.env.E2E_BASE_URL ?? "http://127.0.0.1:5173";
const apiBase =
  process.env.E2E_API_BASE_URL ?? process.env.VITE_API_BASE ?? process.env.VITE_API_BASE_URL ?? "http://127.0.0.1:8000";

function seriesId() {
  // Use a non-default timeframe to avoid cross-test interference in parallel Playwright workers.
  // Must be a timeframe supported by the UI select.
  return "binance:futures:BTC/USDT:5m";
}

const FORMING_SERIES_ID = "binance:futures:SOL/USDT:15m";

async function ingestClosedCandleForSeries(request: APIRequestContext, sid: string, candle_time: number, price: number) {
  const res = await request.post(`${apiBase}/api/market/ingest/candle_closed`, {
    data: {
      series_id: sid,
      candle: {
        candle_time,
        open: price,
        high: price,
        low: price,
        close: price,
        volume: 10
      }
    }
  });
  expect(res.ok()).toBeTruthy();
}

async function ingestClosedCandle(request: APIRequestContext, candle_time: number, price: number) {
  return ingestClosedCandleForSeries(request, seriesId(), candle_time, price);
}

async function ingestFormingCandleForSeries(request: APIRequestContext, sid: string, candle_time: number, price: number) {
  const res = await request.post(`${apiBase}/api/market/ingest/candle_forming`, {
    data: {
      series_id: sid,
      candle: {
        candle_time,
        open: price,
        high: price,
        low: price,
        close: price,
        volume: 10
      }
    }
  });
  expect(res.ok()).toBeTruthy();
}

async function ingestFormingCandle(request: APIRequestContext, candle_time: number, price: number) {
  return ingestFormingCandleForSeries(request, seriesId(), candle_time, price);
}

test("live chart loads catchup and follows WS", async ({ page, request }) => {
  // Ensure persisted UI state doesn't leak between runs, and pin UI to this test's series_id.
  await page.addInitScript(() => {
    localStorage.clear();
    localStorage.setItem(
      "trade-canvas-ui",
      JSON.stringify({
        version: 2,
        state: {
          exchange: "binance",
          market: "futures",
          symbol: "BTC/USDT",
          timeframe: "5m",
          sidebarCollapsed: false,
          sidebarWidth: 280,
          bottomCollapsed: false,
          bottomHeight: 240,
          activeSidebarTab: "Market",
          activeBottomTab: "Ledger"
        }
      })
    );
  });

  // Mock feed → store/API:
  // - default window_major=50
  // - need at least 3 major pivots to confirm 1 pen (A,B confirmed by C)
  // Build an up/down/up/down wave: 4 segments of 60 candles each.
  const base = 300;
  const segment = 60;
  const total = segment * 4;
  for (let i = 0; i < total; i++) {
    const v =
      i < segment
        ? i + 1
        : i < segment * 2
          ? segment - (i - segment)
          : i < segment * 3
            ? i - segment * 2 + 1
            : segment - (i - segment * 3);
    const t = base * (i + 1);
    await ingestClosedCandle(request, t, v);
  }

  // Frontend renders and fetches candles from backend.
  const sidQuery = `series_id=${encodeURIComponent(seriesId())}`;
  const candlesResponsePromise = page.waitForResponse((r) => {
    return (
      r.url().includes("/api/market/candles") &&
      r.url().includes(sidQuery) &&
      r.request().method() === "GET" &&
      r.status() === 200
    );
  });

  await page.goto(`${frontendBase}/live`, { waitUntil: "domcontentloaded" });

  const candlesResp = await candlesResponsePromise;
  const payload = (await candlesResp.json()) as GetCandlesResponse;
  expect(payload.series_id).toBe(seriesId());
  expect(payload.candles?.length).toBeGreaterThanOrEqual(2);

  // Ensure chart area is present (basic UI sanity).
  await expect(page.locator('[data-chart-area="true"]')).toBeVisible();
  await expect(page.locator('[data-chart-area="true"] canvas').first()).toBeVisible();

  // Pivot markers are rendered from backend overlay delta (instruction catalog patch).
  await expect
    .poll(async () => {
      const raw = await page.locator('[data-testid="chart-view"]').getAttribute("data-pivot-count");
      const n = raw ? Number(raw) : 0;
      return Number.isFinite(n) ? n : 0;
    })
    .toBeGreaterThan(0);

  // Pen polyline is rendered from the same overlay delta stream.
  await expect
    .poll(async () => {
      const raw = await page.locator('[data-testid="chart-view"]').getAttribute("data-pen-point-count");
      const n = raw ? Number(raw) : 0;
      return Number.isFinite(n) ? n : 0;
    })
    .toBeGreaterThan(0);

  // Then push a closed candle and ensure the frontend receives it via WS.
  await ingestClosedCandle(request, base * (total + 1), 1);
  const chart = page.locator('[data-testid="chart-view"]');
  await expect(chart).toHaveAttribute("data-last-ws-candle-time", String(base * (total + 1)));
});

test("live chart loads history once and forming candle jumps", async ({ page, request }) => {
  await page.addInitScript(() => {
    localStorage.clear();
    localStorage.setItem(
      "trade-canvas-ui",
      JSON.stringify({
        version: 2,
        state: {
          exchange: "binance",
          market: "futures",
          symbol: "SOL/USDT",
          timeframe: "15m",
          sidebarCollapsed: false,
          sidebarWidth: 280,
          bottomCollapsed: false,
          bottomHeight: 240,
          activeSidebarTab: "Market",
          activeBottomTab: "Ledger"
        }
      })
    );
  });

  await ingestClosedCandleForSeries(request, FORMING_SERIES_ID, 900, 1);
  await ingestClosedCandleForSeries(request, FORMING_SERIES_ID, 1800, 2);

  const sent: string[] = [];
  page.on("websocket", (ws) => {
    if (!ws.url().includes("/ws/market")) return;
    ws.on("framesent", (evt) => sent.push(evt.payload));
  });

  let candleGets = 0;
  const sidQuery = `series_id=${encodeURIComponent(FORMING_SERIES_ID)}`;
  page.on("request", (r) => {
    if (!r.url().includes("/api/market/candles")) return;
    if (!r.url().includes(sidQuery)) return;
    if (r.method() !== "GET") return;
    candleGets += 1;
  });

  const candlesResponsePromise = page.waitForResponse((r) => {
    return r.url().includes("/api/market/candles") && r.url().includes(sidQuery) && r.request().method() === "GET" && r.status() === 200;
  });

  await page.goto(`${frontendBase}/live`, { waitUntil: "domcontentloaded" });
  await candlesResponsePromise;

  await expect
    .poll(() => sent.some((f) => f.includes('"type":"subscribe"') && f.includes(FORMING_SERIES_ID)), { timeout: 10_000 })
    .toBeTruthy();

  const chart = page.locator('[data-testid="chart-view"]');
  await expect(chart).toHaveAttribute("data-series-id", FORMING_SERIES_ID);
  await expect(chart).toHaveAttribute("data-last-time", "1800");
  expect(candleGets).toBe(1);

  await ingestFormingCandleForSeries(request, FORMING_SERIES_ID, 2700, 10);
  await expect(chart).toHaveAttribute("data-last-time", "2700");
  await expect(chart).toHaveAttribute("data-last-close", "10");

  await ingestFormingCandleForSeries(request, FORMING_SERIES_ID, 2700, 11);
  await expect(chart).toHaveAttribute("data-last-time", "2700");
  await expect(chart).toHaveAttribute("data-last-close", "11");

  await ingestFormingCandleForSeries(request, FORMING_SERIES_ID, 2700, 12);
  await expect(chart).toHaveAttribute("data-last-time", "2700");
  await expect(chart).toHaveAttribute("data-last-close", "12");

  await ingestClosedCandleForSeries(request, FORMING_SERIES_ID, 2700, 13);
  await expect(chart).toHaveAttribute("data-last-ws-candle-time", "2700");
  await expect(chart).toHaveAttribute("data-last-close", "13");

  expect(candleGets).toBe(1);
});
