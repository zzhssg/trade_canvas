export const MAX_BAR_SPACING_ON_FIT_CONTENT = 20;

export function clampBarSpacing(current: number, max: number): number {
  if (!Number.isFinite(current)) return max;
  if (!Number.isFinite(max) || max <= 0) return current;
  return current > max ? max : current;
}

