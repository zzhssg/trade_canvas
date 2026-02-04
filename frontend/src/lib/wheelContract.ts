/**
 * Wheel / scroll interaction contract (UI SoT)
 *
 * Rules:
 * 1) When the chart area is hovered, the center scroll container is "locked" (overflow-y: hidden),
 *    and the wheel is used for chart horizontal zoom (barSpacing).
 * 2) When the chart area is NOT hovered, the center scroll container is scrollable (overflow-y: auto),
 *    and the wheel scrolls the page (native browser scrolling).
 *
 * This module centralizes the constants + math to avoid behavior drifting across refactors.
 */

export const CENTER_SCROLL_SELECTOR = '[data-center-scroll="true"]';

export const WHEEL_DELTA_LINE_PX = 16;

export function normalizeWheelDeltaY(event: WheelEvent): number {
  const factor = event.deltaMode === 1 ? WHEEL_DELTA_LINE_PX : event.deltaMode === 2 ? Math.max(1, window.innerHeight) : 1;
  return event.deltaY * factor;
}

export const CHART_WHEEL_ZOOM_MAGNITUDE_CAP = 1.5;
export const CHART_WHEEL_ZOOM_MAGNITUDE_DENOM = 240;
export const CHART_WHEEL_ZOOM_STEP_MAX = 0.08;
export const CHART_WHEEL_ZOOM_STEP_MIN = 0.03;

export function chartWheelZoomRatio(normalizedDeltaY: number): number | null {
  const dir = Math.sign(normalizedDeltaY);
  if (dir === 0) return null;
  const magnitude = Math.min(CHART_WHEEL_ZOOM_MAGNITUDE_CAP, Math.abs(normalizedDeltaY) / CHART_WHEEL_ZOOM_MAGNITUDE_DENOM);
  const step = Math.max(CHART_WHEEL_ZOOM_STEP_MIN, CHART_WHEEL_ZOOM_STEP_MAX * magnitude);
  return dir > 0 ? 1 - step : 1 + step;
}
