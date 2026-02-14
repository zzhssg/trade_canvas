import { expect, test, type APIRequestContext } from "@playwright/test"

import { buildSeriesId, ingestClosedCandlePrice, uniqueSymbol } from "./helpers/marketIngest"
import { buildDefaultUiState, initTradeCanvasStorage } from "./helpers/localStorage"

const frontendBase = process.env.E2E_BASE_URL ?? "http://127.0.0.1:5173"
const apiBase =
  process.env.E2E_API_BASE_URL ?? process.env.VITE_API_BASE ?? process.env.VITE_API_BASE_URL ?? "http://127.0.0.1:8000"

type MarketHealthResponse = {
  expected_latest_closed_time: number
}

async function readExpectedLatestClosedTime(request: APIRequestContext, seriesId: string): Promise<number> {
  const res = await request.get(`${apiBase}/api/market/health`, {
    params: { series_id: seriesId },
  })
  expect(res.ok()).toBeTruthy()
  const payload = (await res.json()) as MarketHealthResponse
  return payload.expected_latest_closed_time
}

test("kline health lamp becomes green within 6s after closed candle ingest", async ({ page, request }) => {
  test.setTimeout(60_000)

  const symbol = uniqueSymbol("LAMPTC")
  const timeframe = "1h"
  const seriesId = buildSeriesId(symbol, timeframe)

  await initTradeCanvasStorage(page, {
    clear: true,
    uiVersion: 2,
    uiState: buildDefaultUiState({ symbol, timeframe }),
  })

  await page.goto(`${frontendBase}/live`, { waitUntil: "domcontentloaded" })

  const chart = page.locator('[data-testid="chart-view"]')
  const lamp = page.getByTestId("kline-health-lamp")

  await expect(chart).toHaveAttribute("data-series-id", seriesId, { timeout: 5_000 })
  await expect(lamp).toBeVisible()

  const expectedLatestClosedTime = await readExpectedLatestClosedTime(request, seriesId)
  expect(expectedLatestClosedTime).toBeGreaterThan(0)

  await ingestClosedCandlePrice(request, {
    apiBase,
    seriesId,
    candleTime: expectedLatestClosedTime,
    price: 100,
  })

  await expect(chart).toHaveAttribute("data-last-time", String(expectedLatestClosedTime), { timeout: 3_000 })
  await expect(lamp).toHaveAttribute("data-kline-status", "green", { timeout: 6_000 })
})
