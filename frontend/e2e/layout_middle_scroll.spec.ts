import { expect, test } from "@playwright/test";

const frontendBase = process.env.E2E_BASE_URL ?? "http://127.0.0.1:5173";

test("middle area scrolls and bottom tabs can be reached @smoke", async ({ page }) => {
  // Ensure persisted UI state doesn't leak between runs.
  await page.addInitScript(() => localStorage.clear());

  await page.goto(`${frontendBase}/live`, { waitUntil: "domcontentloaded" });

  const middle = page.getByTestId("middle-scroll");
  const bottom = page.getByTestId("bottom-tabs");
  await expect(middle).toBeVisible();
  await expect(bottom).toBeVisible();

  // Push bottom tabs further down to guarantee it is out of viewport at start.
  await page.evaluate(() => {
    const el = document.querySelector('[data-testid="middle-scroll"]') as HTMLElement | null;
    if (!el) throw new Error("missing middle-scroll container");
    const spacer = document.createElement("div");
    spacer.setAttribute("data-testid", "e2e-scroll-spacer");
    spacer.style.height = "2600px";
    spacer.style.pointerEvents = "none";
    el.insertBefore(spacer, el.firstChild);
  });

  await expect(bottom).not.toBeInViewport();

  // Scroll within the middle area and verify it reaches bottom tabs.
  const scrolled = await page.evaluate(() => {
    const el = document.querySelector('[data-testid="middle-scroll"]') as HTMLElement | null;
    if (!el) return { ok: false, scrollTop: 0, scrollHeight: 0, clientHeight: 0 };
    el.scrollTop = el.scrollHeight;
    return { ok: true, scrollTop: el.scrollTop, scrollHeight: el.scrollHeight, clientHeight: el.clientHeight };
  });
  expect(scrolled.ok).toBeTruthy();
  expect(scrolled.scrollHeight).toBeGreaterThan(scrolled.clientHeight);
  expect(scrolled.scrollTop).toBeGreaterThan(0);
  await expect(bottom).toBeInViewport();
});
