import type { APIRequestContext } from "@playwright/test";
import { expect, test } from "@playwright/test";

import type { GetCandlesResponse } from "../src/widgets/chart/types";
import {
  ingestClosedCandlePrice,
  ingestClosedCandlesWithFallback,
  type CandleSeed,
  uniqueSymbol,
} from "./helpers/marketIngest";
import {
  buildDefaultUiState,
  buildFactorsState,
  initTradeCanvasStorage,
} from "./helpers/localStorage";

const frontendBase = process.env.E2E_BASE_URL ?? "http://127.0.0.1:5173";
const apiBase =
  process.env.E2E_API_BASE_URL ?? process.env.VITE_API_BASE ?? process.env.VITE_API_BASE_URL ?? "http://127.0.0.1:8000";

type FactorSlicesApiResponse = {
  candle_id: string | null;
};

type WorldFrameAtTimeApiResponse = {
  time: {
    candle_id: string;
  };
  factor_slices: {
    candle_id: string | null;
  };
  draw_state: {
    to_candle_time: number | null;
  };
};

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

async function waitSeriesCandlesReady(
  request: APIRequestContext,
  seriesId: string,
  minimumCount: number,
  timeoutMs = 15_000
) {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    const res = await request.get(`${apiBase}/api/market/candles`, {
      params: { series_id: seriesId, limit: 2000 },
    });
    expect(res.ok()).toBeTruthy();
    const payload = (await res.json()) as GetCandlesResponse;
    if ((payload.candles?.length ?? 0) >= minimumCount) return;
    await new Promise((resolve) => setTimeout(resolve, 200));
  }
  throw new Error(`series candles not ready: ${seriesId}`);
}

test("live chart loads catchup and follows WS", async ({ page, request }) => {
  const liveSymbol = uniqueSymbol("TCLIVE");
  const liveSeriesId = `binance:futures:${liveSymbol}:5m`;

  // Ensure persisted UI state doesn't leak between runs, and pin UI to this test's series_id.
  await initTradeCanvasStorage(page, {
    clear: true,
    uiVersion: 2,
    uiState: buildDefaultUiState({ symbol: liveSymbol, timeframe: "5m" }),
    factorsVersion: 1,
    factorsState: buildFactorsState({
      anchor: true,
      "anchor.switch": true,
    }),
  });

  // Mock feed → store/API:
  // - default window_major=50
  // - need at least 3 major pivots to confirm 1 pen (A,B confirmed by C)
  // Build an up/down/up/down wave: 4 segments of 60 candles each.
  const base = 300;
  const segment = 60;
  const total = segment * 4;
  const seedCandles: CandleSeed[] = [];
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
    seedCandles.push({
      candle_time: t,
      open: v,
      high: v,
      low: v,
      close: v,
      volume: 10
    });
  }
  await ingestClosedCandlesWithFallback(request, {
    apiBase,
    seriesId: liveSeriesId,
    candles: seedCandles,
  });

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

  const countCanvasByZIndex = async (zIndex: string) => {
    return page.locator('[data-testid="chart-view"] canvas').evaluateAll((nodes, target) => {
      let count = 0;
      for (const node of nodes) {
        if (window.getComputedStyle(node).zIndex === target) count += 1;
      }
      return count;
    }, zIndex);
  };

  await expect(page.locator('[data-testid="chart-view"]')).toHaveAttribute("data-anchor-top-layer", "1");
  await expect
    .poll(async () => {
      const raw = await page.locator('[data-testid="chart-view"]').getAttribute("data-anchor-top-layer-path-count");
      const n = raw ? Number(raw) : 0;
      return Number.isFinite(n) ? n : 0;
    })
    .toBeGreaterThan(0);
  await expect.poll(() => countCanvasByZIndex("5")).toBeGreaterThan(0);
  await expect.poll(() => countCanvasByZIndex("8")).toBeGreaterThan(0);

  await page.screenshot({ path: "output/playwright/anchor_switch.png", fullPage: false });

  // Then push a closed candle and ensure the frontend receives it via WS.
  await ingestClosedCandlePrice(request, {
    apiBase,
    seriesId: liveSeriesId,
    candleTime: base * (total + 1),
    price: 1,
  });
  const followupTime = base * (total + 1);
  const chart = page.locator('[data-testid="chart-view"]');
  await expect(chart).toHaveAttribute("data-last-ws-candle-time", String(followupTime));

  const factorFirstRes = await request.get(`${apiBase}/api/factor/slices`, {
    params: {
      series_id: liveSeriesId,
      at_time: followupTime,
      window_candles: 2000,
    },
  });
  expect(factorFirstRes.ok()).toBeTruthy();
  const factorFirst = (await factorFirstRes.json()) as FactorSlicesApiResponse;
  expect(factorFirst.candle_id).toBe(`${liveSeriesId}:${followupTime}`);

  const factorSecondRes = await request.get(`${apiBase}/api/factor/slices`, {
    params: {
      series_id: liveSeriesId,
      at_time: followupTime,
      window_candles: 2000,
    },
  });
  expect(factorSecondRes.ok()).toBeTruthy();
  const factorSecond = (await factorSecondRes.json()) as FactorSlicesApiResponse;
  expect(factorSecond).toEqual(factorFirst);

  const worldAtTimeRes = await request.get(`${apiBase}/api/frame/at_time`, {
    params: {
      series_id: liveSeriesId,
      at_time: followupTime,
      window_candles: 2000,
    },
  });
  expect(worldAtTimeRes.ok()).toBeTruthy();
  const worldAtTime = (await worldAtTimeRes.json()) as WorldFrameAtTimeApiResponse;
  expect(worldAtTime.time.candle_id).toBe(`${liveSeriesId}:${followupTime}`);
  expect(worldAtTime.factor_slices.candle_id).toBe(`${liveSeriesId}:${followupTime}`);
  expect(worldAtTime.draw_state.to_candle_time).toBe(followupTime);
});

test("live chart retries initial pull when first payload has only one candle", async ({ page }) => {
  const retrySymbol = uniqueSymbol("TCRETRY");
  const retrySeriesId = `binance:futures:${retrySymbol}:15m`;

  await initTradeCanvasStorage(page, {
    clear: true,
    uiVersion: 2,
    uiState: buildDefaultUiState({ symbol: retrySymbol, timeframe: "15m" }),
  });

  const oneCandlePayload = [
    {
      candle_time: 900,
      open: 1,
      high: 1,
      low: 1,
      close: 1,
      volume: 10,
    },
  ];
  const fullPayload = [
    oneCandlePayload[0],
    {
      candle_time: 1800,
      open: 2,
      high: 2,
      low: 2,
      close: 2,
      volume: 10,
    },
    {
      candle_time: 2700,
      open: 3,
      high: 3,
      low: 3,
      close: 3,
      volume: 10,
    },
  ];

  let noSinceCalls = 0;
  await page.route("**/api/market/candles*", async (route) => {
    const url = new URL(route.request().url());
    if (url.searchParams.get("series_id") !== retrySeriesId) {
      await route.continue();
      return;
    }

    const sinceRaw = url.searchParams.get("since");
    if (!sinceRaw) noSinceCalls += 1;
    const since = sinceRaw ? Number(sinceRaw) : null;

    const candles =
      since == null
        ? noSinceCalls === 1
          ? oneCandlePayload
          : fullPayload
        : fullPayload.filter((item) => item.candle_time > since);

    if (since == null && noSinceCalls === 2) {
      await new Promise((resolve) => setTimeout(resolve, 700));
    }

    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        series_id: retrySeriesId,
        server_head_time: candles.length > 0 ? candles[candles.length - 1]!.candle_time : null,
        candles,
      }),
    });
  });

  await page.goto(`${frontendBase}/live`, { waitUntil: "domcontentloaded" });
  const chart = page.locator('[data-testid="chart-view"]');
  await expect(chart).toBeVisible();
  await expect
    .poll(async () => (await chart.getAttribute("data-live-load-status")) ?? "", { timeout: 600 })
    .toMatch(/loading|backfilling/);
  await expect
    .poll(async () => Number((await chart.getAttribute("data-candles-len")) ?? "0"), { timeout: 600 })
    .toBe(0);

  await expect
    .poll(async () => Number((await chart.getAttribute("data-candles-len")) ?? "0"))
    .toBe(3);
  await expect.poll(() => noSinceCalls).toBeGreaterThanOrEqual(2);
});

test("rapid timeframe switching keeps backfill and draw callback chain alive", async ({ page, request }) => {
  const switchSymbol = uniqueSymbol("TCSWITCH");
  const series15m = `binance:futures:${switchSymbol}:15m`;
  const series5m = `binance:futures:${switchSymbol}:5m`;

  await initTradeCanvasStorage(page, {
    clear: true,
    uiVersion: 2,
    uiState: buildDefaultUiState({ symbol: switchSymbol, timeframe: "15m" }),
  });

  const base15m = 900;
  const base5m = 300;
  const segment = 60;
  const total = segment * 4;
  const buildWave = (step: number): CandleSeed[] => {
    const candles: CandleSeed[] = [];
    for (let i = 0; i < total; i += 1) {
      const v =
        i < segment
          ? i + 1
          : i < segment * 2
            ? segment - (i - segment)
            : i < segment * 3
              ? i - segment * 2 + 1
              : segment - (i - segment * 3);
      candles.push({
        candle_time: step * (i + 1),
        open: v,
        high: v,
        low: v,
        close: v,
        volume: 10,
      });
    }
    return candles;
  };

  await ingestClosedCandlesWithFallback(request, {
    apiBase,
    seriesId: series15m,
    candles: buildWave(base15m),
  });
  await ingestClosedCandlesWithFallback(request, {
    apiBase,
    seriesId: series5m,
    candles: buildWave(base5m),
  });
  await waitSeriesCandlesReady(request, series15m, 2);
  await waitSeriesCandlesReady(request, series5m, 2);

  let factorCalls15m = 0;
  let factorCalls5m = 0;
  const factorAtTimes5m: number[] = [];

  await page.route("**/api/frame/live*", async (route) => {
    const url = new URL(route.request().url());
    const sid = url.searchParams.get("series_id");
    if (sid === series15m || sid === series5m) {
      await route.fulfill({
        status: 409,
        contentType: "application/json",
        body: JSON.stringify({ detail: "ledger_out_of_sync" }),
      });
      return;
    }
    await route.continue();
  });

  await page.route("**/api/factor/slices*", async (route) => {
    const url = new URL(route.request().url());
    const sid = url.searchParams.get("series_id");
    if (sid === series15m) {
      factorCalls15m += 1;
      if (factorCalls15m === 1) {
        await new Promise((resolve) => setTimeout(resolve, 3000));
      }
    } else if (sid === series5m) {
      factorCalls5m += 1;
      const atTime = Number(url.searchParams.get("at_time") ?? "0");
      if (Number.isFinite(atTime) && atTime > 0) factorAtTimes5m.push(atTime);
    }
    await route.continue();
  });

  await page.goto(`${frontendBase}/live`, { waitUntil: "domcontentloaded" });
  const chart = page.locator('[data-testid="chart-view"]');
  await expect(chart).toBeVisible();
  await expect.poll(() => factorCalls15m).toBeGreaterThanOrEqual(1);

  await page.getByTestId("timeframe-tag-5m").click();
  await expect(chart).toHaveAttribute("data-series-id", series5m);
  const followupTime = base5m * (total + 1);
  await ingestClosedCandlePrice(request, {
    apiBase,
    seriesId: series5m,
    candleTime: followupTime,
    price: 1,
  });
  await page.getByTestId("timeframe-tag-15m").click();
  await expect(chart).toHaveAttribute("data-series-id", series15m);
  await page.getByTestId("timeframe-tag-5m").click();
  await expect(chart).toHaveAttribute("data-series-id", series5m);
  await expect(chart).toHaveAttribute("data-last-time", String(followupTime));
  await expect
    .poll(() => factorCalls5m, { timeout: 10_000 })
    .toBeGreaterThanOrEqual(1);
  await expect
    .poll(() => factorAtTimes5m.includes(followupTime), { timeout: 10_000 })
    .toBeTruthy();
  await expect
    .poll(async () => Number((await chart.getAttribute("data-candles-len")) ?? "0"))
    .toBeGreaterThanOrEqual(2);
  await expect
    .poll(async () => Number((await chart.getAttribute("data-pen-point-count")) ?? "0"), { timeout: 10_000 })
    .toBeGreaterThan(0);
});

test("timeframe switch clears previous draw instructions before next timeframe factor is ready", async ({ page, request }) => {
  const staleSymbol = uniqueSymbol("TCSTALE");
  const series15m = `binance:futures:${staleSymbol}:15m`;
  const series5m = `binance:futures:${staleSymbol}:5m`;

  await initTradeCanvasStorage(page, {
    clear: true,
    uiVersion: 2,
    uiState: buildDefaultUiState({ symbol: staleSymbol, timeframe: "15m" }),
  });

  const buildWave = (step: number): CandleSeed[] => {
    const segment = 60;
    const total = segment * 4;
    const candles: CandleSeed[] = [];
    for (let i = 0; i < total; i += 1) {
      const v =
        i < segment
          ? i + 1
          : i < segment * 2
            ? segment - (i - segment)
            : i < segment * 3
              ? i - segment * 2 + 1
              : segment - (i - segment * 3);
      candles.push({
        candle_time: step * (i + 1),
        open: v,
        high: v,
        low: v,
        close: v,
        volume: 10,
      });
    }
    return candles;
  };

  await ingestClosedCandlesWithFallback(request, {
    apiBase,
    seriesId: series15m,
    candles: buildWave(900),
  });
  await ingestClosedCandlesWithFallback(request, {
    apiBase,
    seriesId: series5m,
    candles: [
      { candle_time: 300, open: 1, high: 1, low: 1, close: 1, volume: 10 },
      { candle_time: 600, open: 2, high: 2, low: 2, close: 2, volume: 10 },
      { candle_time: 900, open: 3, high: 3, low: 3, close: 3, volume: 10 },
    ],
  });

  await page.route("**/api/frame/live*", async (route) => {
    const url = new URL(route.request().url());
    const sid = url.searchParams.get("series_id");
    if (sid === series15m || sid === series5m) {
      await route.fulfill({
        status: 409,
        contentType: "application/json",
        body: JSON.stringify({ detail: "ledger_out_of_sync" }),
      });
      return;
    }
    await route.continue();
  });

  let factorCalls5m = 0;
  await page.route("**/api/factor/slices*", async (route) => {
    const url = new URL(route.request().url());
    const sid = url.searchParams.get("series_id");
    if (sid === series5m) {
      factorCalls5m += 1;
      if (factorCalls5m === 1) {
        await new Promise((resolve) => setTimeout(resolve, 2500));
      }
    }
    await route.continue();
  });

  await page.goto(`${frontendBase}/live`, { waitUntil: "domcontentloaded" });
  const chart = page.locator('[data-testid="chart-view"]');
  await expect(chart).toBeVisible();
  await expect
    .poll(async () => Number((await chart.getAttribute("data-pen-point-count")) ?? "0"), { timeout: 10_000 })
    .toBeGreaterThan(0);

  await page.getByTestId("timeframe-tag-5m").click();
  await expect(chart).toHaveAttribute("data-series-id", series5m);
  await expect
    .poll(async () => Number((await chart.getAttribute("data-pen-point-count")) ?? "0"), { timeout: 1_500 })
    .toBe(0);
  await expect(chart).toHaveAttribute("data-anchor-highlight-point-count", "0");
  await expect.poll(() => factorCalls5m, { timeout: 10_000 }).toBeGreaterThanOrEqual(1);
});

test("factor data auto recovers without timeframe switch after delayed ledger warmup", async ({ page, request }) => {
  const recoverSymbol = uniqueSymbol("TCRECOVER");
  const recoverSeriesId = `binance:futures:${recoverSymbol}:15m`;

  await initTradeCanvasStorage(page, {
    clear: true,
    uiVersion: 2,
    uiState: buildDefaultUiState({ symbol: recoverSymbol, timeframe: "15m" }),
  });

  await ingestClosedCandlesWithFallback(request, {
    apiBase,
    seriesId: recoverSeriesId,
    candles: [
      { candle_time: 900, open: 1, high: 1, low: 1, close: 1, volume: 10 },
      { candle_time: 1800, open: 2, high: 2, low: 2, close: 2, volume: 10 },
      { candle_time: 2700, open: 3, high: 3, low: 3, close: 3, volume: 10 },
    ],
  });

  await page.route("**/api/frame/live*", async (route) => {
    const url = new URL(route.request().url());
    if (url.searchParams.get("series_id") === recoverSeriesId) {
      await route.fulfill({
        status: 409,
        contentType: "application/json",
        body: JSON.stringify({ detail: "ledger_out_of_sync" }),
      });
      return;
    }
    await route.continue();
  });

  await page.route("**/api/draw/delta*", async (route) => {
    const url = new URL(route.request().url());
    if (url.searchParams.get("series_id") === recoverSeriesId) {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          active_ids: [],
          instruction_catalog_patch: [],
          next_cursor: { version_id: 0 },
        }),
      });
      return;
    }
    await route.continue();
  });

  let factorCalls = 0;
  await page.route("**/api/factor/slices*", async (route) => {
    const url = new URL(route.request().url());
    if (url.searchParams.get("series_id") !== recoverSeriesId) {
      await route.continue();
      return;
    }
    factorCalls += 1;
    const atTime = Number(url.searchParams.get("at_time") ?? "0");
    const candleId = `${recoverSeriesId}:${atTime}`;
    if (factorCalls <= 12) {
      await route.fulfill({
        status: 409,
        contentType: "application/json",
        body: JSON.stringify({ detail: "ledger_out_of_sync:factor" }),
      });
      return;
    }
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        schema_version: 1,
        series_id: recoverSeriesId,
        at_time: atTime,
        candle_id: candleId,
        snapshots: {
          anchor: {
            schema_version: 1,
            meta: {
              series_id: recoverSeriesId,
              epoch: factorCalls,
              at_time: atTime,
              candle_id: candleId,
              factor_name: "anchor",
            },
            head: {
              current_anchor_ref: {
                kind: "candidate",
                start_time: 1800,
                end_time: atTime,
                direction: 1,
              },
            },
            history: {},
          },
          pen: {
            schema_version: 1,
            meta: {
              series_id: recoverSeriesId,
              epoch: factorCalls,
              at_time: atTime,
              candle_id: candleId,
              factor_name: "pen",
            },
            head: {
              candidate: {
                start_time: 1800,
                end_time: atTime,
                start_price: 2,
                end_price: 3,
                direction: 1,
              },
            },
            history: { confirmed: [] },
          },
        },
      }),
    });
  });

  await page.goto(`${frontendBase}/live`, { waitUntil: "domcontentloaded" });
  const chart = page.locator('[data-testid="chart-view"]');
  await expect(chart).toBeVisible();
  await expect(chart).toHaveAttribute("data-anchor-highlight-point-count", "0");
  await expect.poll(() => factorCalls, { timeout: 15_000 }).toBeGreaterThan(12);
  await expect(chart).toHaveAttribute("data-anchor-highlight-point-count", "2", { timeout: 15_000 });
  await expect(chart).toHaveAttribute("data-anchor-highlight-start-time", "1800");
  await expect(chart).toHaveAttribute("data-anchor-highlight-end-time", "2700");
});

test("history backfill ignores off-axis factor pen and recovers on latest candle", async ({ page, request }) => {
  const axisSymbol = uniqueSymbol("TCAXIS");
  const axisSeriesId = `binance:futures:${axisSymbol}:15m`;

  await initTradeCanvasStorage(page, {
    clear: true,
    uiVersion: 2,
    uiState: buildDefaultUiState({ symbol: axisSymbol, timeframe: "15m" }),
  });

  const base = 900;
  const seedCandles: CandleSeed[] = [1, 2, 3].map((value) => ({
    candle_time: base * value,
    open: value,
    high: value,
    low: value,
    close: value,
    volume: 10,
  }));
  await ingestClosedCandlesWithFallback(request, {
    apiBase,
    seriesId: axisSeriesId,
    candles: seedCandles,
  });

  await page.route("**/api/frame/live*", async (route) => {
    const url = new URL(route.request().url());
    if (url.searchParams.get("series_id") === axisSeriesId) {
      await route.fulfill({
        status: 409,
        contentType: "application/json",
        body: JSON.stringify({ detail: "ledger_out_of_sync" }),
      });
      return;
    }
    await route.continue();
  });

  await page.route("**/api/draw/delta*", async (route) => {
    const url = new URL(route.request().url());
    if (url.searchParams.get("series_id") === axisSeriesId) {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          active_ids: ["anchor.current"],
          instruction_catalog_patch: [
            {
              instruction_id: "anchor.current",
              version_id: 1,
              visible_time: base * 3,
              kind: "polyline",
              definition: {
                type: "polyline",
                feature: "anchor.current",
                color: "#f59e0b",
                lineWidth: 2,
                lineStyle: "dashed",
                points: [
                  { time: 0, value: 1 },
                  { time: base * 3, value: 2 },
                ],
              },
            },
          ],
          next_cursor: { version_id: 1 },
        }),
      });
      return;
    }
    await route.continue();
  });

  let factorCalls = 0;
  const factorAtTimes: number[] = [];
  await page.route("**/api/factor/slices*", async (route) => {
    const url = new URL(route.request().url());
    if (url.searchParams.get("series_id") !== axisSeriesId) {
      await route.continue();
      return;
    }

    factorCalls += 1;
    const atTime = Number(url.searchParams.get("at_time") ?? "0");
    if (Number.isFinite(atTime) && atTime > 0) factorAtTimes.push(atTime);

    const invalidAxis = factorCalls === 1;
    const startTime = invalidAxis ? 1200 : 1800;
    const endTime = invalidAxis ? 2400 : Math.max(3600, atTime);
    const candleId = `${axisSeriesId}:${atTime}`;
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        schema_version: 1,
        series_id: axisSeriesId,
        at_time: atTime,
        candle_id: candleId,
        snapshots: {
          anchor: {
            schema_version: 1,
            meta: {
              series_id: axisSeriesId,
              epoch: factorCalls,
              at_time: atTime,
              candle_id: candleId,
              factor_name: "anchor",
            },
            head: {
              current_anchor_ref: {
                kind: "candidate",
                start_time: startTime,
                end_time: endTime,
                direction: 1,
              },
            },
            history: {},
          },
          pen: {
            schema_version: 1,
            meta: {
              series_id: axisSeriesId,
              epoch: factorCalls,
              at_time: atTime,
              candle_id: candleId,
              factor_name: "pen",
            },
            head: {
              candidate: {
                start_time: startTime,
                end_time: endTime,
                start_price: 1,
                end_price: 2,
                direction: 1,
              },
            },
            history: { confirmed: [] },
          },
        },
      }),
    });
  });

  await page.goto(`${frontendBase}/live`, { waitUntil: "domcontentloaded" });
  const chart = page.locator('[data-testid="chart-view"]');
  await expect(chart).toBeVisible();
  await expect
    .poll(async () => Number((await chart.getAttribute("data-candles-len")) ?? "0"))
    .toBe(3);
  await expect(chart).toHaveAttribute("data-anchor-top-layer-path-count", "1");
  await expect.poll(() => factorCalls).toBeGreaterThanOrEqual(1);
  await expect(chart).toHaveAttribute("data-anchor-highlight-point-count", "0");
  await expect(chart).toHaveAttribute("data-anchor-highlight-start-time", "");
  await expect(chart).toHaveAttribute("data-anchor-highlight-end-time", "");

  const followupTime = 3600;
  await ingestClosedCandlePrice(request, {
    apiBase,
    seriesId: axisSeriesId,
    candleTime: followupTime,
    price: 4,
  });
  await expect(chart).toHaveAttribute("data-last-time", String(followupTime));
  await expect
    .poll(() => factorCalls, { timeout: 10_000 })
    .toBeGreaterThanOrEqual(2);
  await expect(chart).toHaveAttribute("data-anchor-highlight-point-count", "2", { timeout: 10_000 });
  await expect(chart).toHaveAttribute("data-anchor-highlight-start-time", "1800");
  await expect(chart).toHaveAttribute("data-anchor-highlight-end-time", String(followupTime));
  await expect(chart).toHaveAttribute("data-anchor-highlight-dashed", "1");
  await expect
    .poll(() => factorAtTimes.includes(followupTime), { timeout: 10_000 })
    .toBeTruthy();
  await page.screenshot({ path: "output/playwright/history_backfill_axis_guard.png", fullPage: false });
});

test("@smoke live backfill burst does not hammer delta/slices", async ({ page, request }) => {
  const burstSymbol = uniqueSymbol("TCBURST");
  const burstSeriesId = `binance:futures:${burstSymbol}:15m`;
  await initTradeCanvasStorage(page, {
    clear: true,
    uiVersion: 2,
    uiState: buildDefaultUiState({ symbol: burstSymbol, timeframe: "15m" }),
  });

  const base = 900;
  const warmupCandles: CandleSeed[] = [];
  for (let i = 0; i < 20; i++) {
    const price = i + 1;
    warmupCandles.push({
      candle_time: base * (i + 1),
      open: price,
      high: price,
      low: price,
      close: price,
      volume: 10
    });
  }
  await ingestClosedCandlesWithFallback(request, {
    apiBase,
    seriesId: burstSeriesId,
    candles: warmupCandles,
  });

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
    tasks.push(
      ingestClosedCandlePrice(request, {
        apiBase,
        seriesId: burstSeriesId,
        candleTime: t,
        price: 1,
      })
    );
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

  await initTradeCanvasStorage(page, {
    clear: true,
    uiVersion: 2,
    uiState: buildDefaultUiState({ symbol: formingSymbol, timeframe: "15m" }),
  });

  await ingestClosedCandlePrice(request, {
    apiBase,
    seriesId: formingSeriesId,
    candleTime: 900,
    price: 1,
  });
  await ingestClosedCandlePrice(request, {
    apiBase,
    seriesId: formingSeriesId,
    candleTime: 1800,
    price: 2,
  });

  const sent: string[] = [];
  const received: string[] = [];
  page.on("websocket", (ws) => {
    if (!ws.url().includes("/ws/market")) return;
    ws.on("framesent", (evt) => sent.push(evt.payload));
    ws.on("framereceived", (evt) => received.push(String(evt.payload)));
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
  await expect
    .poll(
      () => received.some((f) => f.includes('"type":"candle_forming"') && f.includes(formingSeriesId) && f.includes('"candle_time":2700')),
      { timeout: 10_000 }
    )
    .toBeTruthy();

  await ingestFormingCandleForSeries(request, formingSeriesId, 2700, 11);
  await expect(chart).toHaveAttribute("data-last-time", "2700");
  await expect(chart).toHaveAttribute("data-last-close", "11");

  await ingestFormingCandleForSeries(request, formingSeriesId, 2700, 12);
  await expect(chart).toHaveAttribute("data-last-time", "2700");
  await expect(chart).toHaveAttribute("data-last-close", "12");

  await ingestClosedCandlePrice(request, {
    apiBase,
    seriesId: formingSeriesId,
    candleTime: 2700,
    price: 13,
  });
  await expect(chart).toHaveAttribute("data-last-ws-candle-time", "2700");
  await expect(chart).toHaveAttribute("data-last-close", "13");
  await expect
    .poll(
      () => received.some((f) => f.includes('"type":"candle_closed"') && f.includes(formingSeriesId) && f.includes('"candle_time":2700')),
      { timeout: 10_000 }
    )
    .toBeTruthy();

  expect(candleGets).toBe(1);
});
