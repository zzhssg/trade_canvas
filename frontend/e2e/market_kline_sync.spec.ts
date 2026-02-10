import type { APIRequestContext } from "@playwright/test";
import { expect, test } from "@playwright/test";

import type { GetCandlesResponse } from "../src/widgets/chart/types";

const frontendBase = process.env.E2E_BASE_URL ?? "http://127.0.0.1:5173";
const apiBase =
  process.env.E2E_API_BASE_URL ?? process.env.VITE_API_BASE ?? process.env.VITE_API_BASE_URL ?? "http://127.0.0.1:8000";

function uniqueSymbol(prefix: string): string {
  const ts = Date.now().toString(36).toUpperCase();
  const rand = Math.floor(Math.random() * 1_000_000)
    .toString(36)
    .toUpperCase();
  return `${prefix}${ts}${rand}/USDT`;
}

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

test("live chart loads catchup and follows WS", async ({ page, request }) => {
  const liveSymbol = uniqueSymbol("TCLIVE");
  const liveSeriesId = `binance:futures:${liveSymbol}:5m`;

  // Ensure persisted UI state doesn't leak between runs, and pin UI to this test's series_id.
  await page.addInitScript(({ symbol }) => {
    localStorage.clear();
    localStorage.setItem(
      "trade-canvas-ui",
      JSON.stringify({
        version: 2,
        state: {
          exchange: "binance",
          market: "futures",
          symbol,
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
    localStorage.setItem(
      "trade-canvas-factors",
      JSON.stringify({
        version: 1,
        state: {
          visibleFeatures: {
            "anchor": true,
            "anchor.switch": true
          }
        }
      })
    );
  }, { symbol: liveSymbol });

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
    await ingestClosedCandleForSeries(request, liveSeriesId, t, v);
  }

  // Frontend renders and fetches candles from backend.
  const sidQuery = `series_id=${encodeURIComponent(liveSeriesId)}`;
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
  expect(payload.series_id).toBe(liveSeriesId);
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

  // Anchor switch markers are rendered from overlay delta (sub_feature enabled).
  await expect
    .poll(async () => {
      const raw = await page.locator('[data-testid="chart-view"]').getAttribute("data-anchor-switch-count");
      const n = raw ? Number(raw) : 0;
      return Number.isFinite(n) ? n : 0;
    })
    .toBeGreaterThan(0);

  await expect(page.locator('[data-testid="chart-view"]')).toHaveAttribute("data-anchor-top-layer", "1");
  await expect
    .poll(async () => {
      const raw = await page.locator('[data-testid="chart-view"]').getAttribute("data-anchor-top-layer-path-count");
      const n = raw ? Number(raw) : 0;
      return Number.isFinite(n) ? n : 0;
    })
    .toBeGreaterThan(0);

  await page.screenshot({ path: "output/playwright/anchor_switch.png", fullPage: false });

  // Then push a closed candle and ensure the frontend receives it via WS.
  await ingestClosedCandleForSeries(request, liveSeriesId, base * (total + 1), 1);
  const chart = page.locator('[data-testid="chart-view"]');
  await expect(chart).toHaveAttribute("data-last-ws-candle-time", String(base * (total + 1)));
});

test("@smoke live backfill burst does not hammer delta/slices", async ({ page, request }) => {
  const burstSymbol = uniqueSymbol("TCBURST");
  const burstSeriesId = `binance:futures:${burstSymbol}:15m`;
  await page.addInitScript(({ symbol }) => {
    localStorage.clear();
    localStorage.setItem(
      "trade-canvas-ui",
      JSON.stringify({
        version: 2,
        state: {
          exchange: "binance",
          market: "futures",
          symbol,
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
  }, { symbol: burstSymbol });

  const base = 900;
  for (let i = 0; i < 20; i++) {
    await ingestClosedCandleForSeries(request, burstSeriesId, base * (i + 1), i + 1);
  }

  let deltaGets = 0;
  let slicesGets = 0;
  page.on("request", (r) => {
    if (r.method() !== "GET") return;
    const url = r.url();
    if (url.includes("/api/") && url.includes("/delta")) deltaGets += 1;
    if (url.includes("/api/factor/slices")) slicesGets += 1;
  });

  // Set up cold-start probe before navigation so we don't miss the first fast response.
  const sidQuery = `series_id=${encodeURIComponent(burstSeriesId)}`;
  const frameRespPromise = page.waitForResponse(
    (r) => r.url().includes("/api/frame/live") && r.url().includes(sidQuery) && r.request().method() === "GET" && r.status() === 200
  );

  await page.goto(`${frontendBase}/live`, { waitUntil: "domcontentloaded" });
  await expect(page.locator('[data-chart-area="true"]')).toBeVisible();

  // Wait for the cold-start world frame pull so we don't count it in the burst window.
  await frameRespPromise;

  // Reset counters after cold-start.
  deltaGets = 0;
  slicesGets = 0;

  // Burst-ingest many candles in parallel to simulate "fresh-db backfill" behavior.
  const start = 20;
  const count = 120;
  const tasks: Array<Promise<void>> = [];
  for (let i = 0; i < count; i++) {
    const t = base * (start + i + 1);
    tasks.push(ingestClosedCandleForSeries(request, burstSeriesId, t, 1));
  }
  await Promise.all(tasks);

  const lastTime = base * (start + count);
  const chart = page.locator('[data-testid="chart-view"]');
  await expect(chart).toHaveAttribute("data-last-ws-candle-time", String(lastTime), { timeout: 20_000 });

  // Guardrail (world-frame default): at most one cold-start /api/factor/slices probe; deltas are coalesced.
  expect(slicesGets).toBeLessThanOrEqual(1);
  expect(deltaGets).toBeLessThan(15);
});

test("live chart loads history once and forming candle jumps", async ({ page, request }) => {
  const formingSymbol = uniqueSymbol("TCFORM");
  const formingSeriesId = `binance:futures:${formingSymbol}:15m`;

  await page.addInitScript(
    ({ symbol }) => {
      localStorage.clear();
      localStorage.setItem(
        "trade-canvas-ui",
        JSON.stringify({
          version: 2,
          state: {
            exchange: "binance",
            market: "futures",
            symbol,
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
    },
    { symbol: formingSymbol }
  );

  await ingestClosedCandleForSeries(request, formingSeriesId, 900, 1);
  await ingestClosedCandleForSeries(request, formingSeriesId, 1800, 2);

  const sent: string[] = [];
  page.on("websocket", (ws) => {
    if (!ws.url().includes("/ws/market")) return;
    ws.on("framesent", (evt) => sent.push(evt.payload));
  });

  let candleGets = 0;
  const sidQuery = `series_id=${encodeURIComponent(formingSeriesId)}`;
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
    .poll(() => sent.some((f) => f.includes('"type":"subscribe"') && f.includes(formingSeriesId)), { timeout: 10_000 })
    .toBeTruthy();

  const chart = page.locator('[data-testid="chart-view"]');
  await expect(chart).toHaveAttribute("data-series-id", formingSeriesId);
  await expect(chart).toHaveAttribute("data-last-time", "1800");
  expect(candleGets).toBe(1);

  await ingestFormingCandleForSeries(request, formingSeriesId, 2700, 10);
  await expect(chart).toHaveAttribute("data-last-time", "2700");
  await expect(chart).toHaveAttribute("data-last-close", "10");

  await ingestFormingCandleForSeries(request, formingSeriesId, 2700, 11);
  await expect(chart).toHaveAttribute("data-last-time", "2700");
  await expect(chart).toHaveAttribute("data-last-close", "11");

  await ingestFormingCandleForSeries(request, formingSeriesId, 2700, 12);
  await expect(chart).toHaveAttribute("data-last-time", "2700");
  await expect(chart).toHaveAttribute("data-last-close", "12");

  await ingestClosedCandleForSeries(request, formingSeriesId, 2700, 13);
  await expect(chart).toHaveAttribute("data-last-ws-candle-time", "2700");
  await expect(chart).toHaveAttribute("data-last-close", "13");

  expect(candleGets).toBe(1);
});
