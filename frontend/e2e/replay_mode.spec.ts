import type { APIRequestContext } from "@playwright/test";
import { expect, test } from "@playwright/test";

const frontendBase = process.env.E2E_BASE_URL ?? "http://127.0.0.1:5173";
const apiBase =
  process.env.E2E_API_BASE_URL ?? process.env.VITE_API_BASE ?? process.env.VITE_API_BASE_URL ?? "http://127.0.0.1:8000";

function seriesId() {
  return "binance:futures:BTC/USDT:5m";
}

async function ingestClosedCandle(request: APIRequestContext, candle_time: number, price: number) {
  const res = await request.post(`${apiBase}/api/market/ingest/candle_closed`, {
    data: {
      series_id: seriesId(),
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

test("replay mode prepares data and plays", async ({ page, request }) => {
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
          bottomCollapsed: true,
          activeSidebarTab: "Replay",
          activeBottomTab: "Ledger"
        }
      })
    );
  });

  const base = 300;
  const total = 40;
  for (let i = 0; i < total; i++) {
    await ingestClosedCandle(request, base * (i + 1), i + 1);
  }

  const preparePromise = page.waitForResponse((r) => {
    return r.url().includes("/api/replay/prepare") && r.request().method() === "POST" && r.status() === 200;
  });

  await page.goto(`${frontendBase}/live`, { waitUntil: "domcontentloaded" });
  await expect(page.locator('[data-chart-area="true"]')).toBeVisible();

  await page.locator('[data-testid="mode-toggle"]').click();
  const prepareResp = await preparePromise;
  const prepareJson = await prepareResp.json();
  expect(prepareJson.aligned_time).toBe(base * total);

  const chart = page.locator('[data-testid="chart-view"]');
  await expect(chart).toHaveAttribute("data-replay-mode", "replay");

  await expect
    .poll(async () => {
      const raw = await chart.getAttribute("data-replay-total");
      return raw ? Number(raw) : 0;
    })
    .toBeGreaterThanOrEqual(total);

  await expect(chart).toHaveAttribute("data-replay-focus-time", String(base * total));

  const targetIndex = 10;
  const targetTime = base * (targetIndex + 1);
  await page.locator('[data-testid="replay-seek"]').evaluate((el, value) => {
    const input = el as HTMLInputElement;
    const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, "value")?.set;
    setter?.call(input, String(value));
    input.dispatchEvent(new Event("input", { bubbles: true }));
    input.dispatchEvent(new Event("change", { bubbles: true }));
  }, targetIndex);

  await expect(chart).toHaveAttribute("data-replay-focus-time", String(targetTime));
  await expect(page.locator('[data-testid="replay-mask"]')).toBeVisible();

  const beforeClick = await chart.getAttribute("data-replay-focus-time");
  const box = await chart.boundingBox();
  if (box) {
    const clickAt = async (ratio: number) => {
      await page.mouse.click(box.x + box.width * ratio, box.y + box.height * 0.3);
      await page.waitForTimeout(120);
      return await chart.getAttribute("data-replay-focus-time");
    };
    let afterClick = await clickAt(0.2);
    if (afterClick === beforeClick) afterClick = await clickAt(0.7);
    expect(afterClick).not.toBe(beforeClick);
  }

  const beforeIndex = Number(await chart.getAttribute("data-replay-index"));
  await page.locator('[data-testid="replay-play"]').click();
  await page.waitForTimeout(350);
  const afterIndex = Number(await chart.getAttribute("data-replay-index"));
  expect(afterIndex).toBeGreaterThan(beforeIndex);
});
