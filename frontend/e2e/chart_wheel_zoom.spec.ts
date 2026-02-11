import type { Page } from "@playwright/test";
import { expect, test } from "@playwright/test";

import {
  buildSeriesId,
  ingestClosedCandle,
  ingestClosedCandlesWithFallback,
  type CandleSeed,
  uniqueSymbol,
} from "./helpers/marketIngest";
import { buildDefaultUiState, initTradeCanvasStorage } from "./helpers/localStorage";

const frontendBase = process.env.E2E_BASE_URL ?? "http://127.0.0.1:5173";
const apiBase =
  process.env.E2E_API_BASE_URL ?? process.env.VITE_API_BASE ?? process.env.VITE_API_BASE_URL ?? "http://127.0.0.1:8000";

function seriesId(symbol: string) {
  return buildSeriesId(symbol, "1m");
}

async function expectChartCanvasVisible(page: Page) {
  await expect(page.locator('[data-chart-area="true"]')).toBeVisible();
  await expect(page.locator('[data-chart-area="true"] canvas').first()).toBeVisible();
}

async function readBarSpacing(page: Page): Promise<number | null> {
  const raw = await page.getByTestId("chart-view").getAttribute("data-bar-spacing");
  if (!raw) return null;
  const n = Number(raw);
  return Number.isFinite(n) ? n : null;
}

test("mouse wheel zoom works and survives live updates", async ({ page, request }) => {
  const symbol = uniqueSymbol("TCWZ");
  await initTradeCanvasStorage(page, {
    clear: true,
    uiVersion: 2,
    uiState: buildDefaultUiState({ symbol, timeframe: "1m" }),
  });

  // Seed enough candles so zooming has a visible effect (fitContent + wheel scale).
  const seedCandles: CandleSeed[] = [];
  for (let i = 1; i <= 180; i++) {
    const t = i * 60;
    seedCandles.push({
      candle_time: t,
      open: 1,
      high: 2,
      low: 0.5,
      close: 1000 + i,
      volume: 10
    });
  }
  await ingestClosedCandlesWithFallback(request, {
    apiBase,
    seriesId: seriesId(symbol),
    candles: seedCandles,
  });

  await page.goto(`${frontendBase}/live`, { waitUntil: "domcontentloaded" });
  await expectChartCanvasVisible(page);

  await expect.poll(() => readBarSpacing(page), { timeout: 10_000 }).not.toBeNull();
  const baseline = (await readBarSpacing(page))!;
  expect(baseline).toBeGreaterThan(0);

  const box = await page.locator('[data-chart-area="true"]').boundingBox();
  expect(box).not.toBeNull();
  await page.mouse.move(box!.x + box!.width / 2, box!.y + box!.height / 2);
  await page.mouse.wheel(0, -600);
  await page.mouse.wheel(0, -600);

  await expect.poll(() => readBarSpacing(page), { timeout: 5_000 }).not.toBeNull();
  const zoomed = (await readBarSpacing(page))!;
  expect(Math.abs(zoomed - baseline)).toBeGreaterThan(1e-3);

  // Ensure a live update doesn't reset the zoom level.
  const nextTime = 181 * 60;
  await ingestClosedCandle(request, {
    apiBase,
    seriesId: seriesId(symbol),
    candle: { candle_time: nextTime, open: 1, high: 2, low: 0.5, close: 999_999, volume: 10 },
  });
  await expect(page.getByTestId("chart-view")).toHaveAttribute("data-last-ws-candle-time", String(nextTime), {
    timeout: 10_000
  });

  await expect.poll(() => readBarSpacing(page), { timeout: 5_000 }).not.toBeNull();
  const afterLiveUpdate = (await readBarSpacing(page))!;
  expect(Math.abs(afterLiveUpdate - baseline)).toBeGreaterThan(1e-3);
});
