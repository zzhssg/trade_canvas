export const DEFAULT_FIB_LEVELS: number[] = [0, 0.236, 0.382, 0.5, 0.618, 0.786, 1];

function clamp01(value: number): number {
  if (!Number.isFinite(value)) return 0;
  return Math.max(0, Math.min(1, value));
}

export function normalizeFibLevels(levels: number[] | undefined | null): number[] {
  const raw = Array.isArray(levels) && levels.length > 0 ? levels : DEFAULT_FIB_LEVELS;
  const normalized = raw.map((x) => clamp01(Number(x))).filter((x) => Number.isFinite(x));
  const unique = Array.from(new Set(normalized));
  return unique.sort((a, b) => a - b);
}

export function computeFibLevelPrices(params: {
  priceA: number;
  priceB: number;
  levels?: number[] | null;
}): Array<{ ratio: number; price: number }> {
  const priceA = Number(params.priceA);
  const priceB = Number(params.priceB);
  if (!Number.isFinite(priceA) || !Number.isFinite(priceB)) return [];

  const top = Math.max(priceA, priceB);
  const bottom = Math.min(priceA, priceB);
  const span = top - bottom;

  const levels = normalizeFibLevels(params.levels);
  return levels.map((ratio) => ({
    ratio,
    price: top - span * ratio
  }));
}

export function pairFibLevels<T extends { ratio: number }>(levels: T[]): Array<{ from: T; to: T }> {
  if (!Array.isArray(levels) || levels.length < 2) return [];
  const sorted = [...levels].sort((a, b) => a.ratio - b.ratio);
  const out: Array<{ from: T; to: T }> = [];
  for (let i = 0; i < sorted.length - 1; i += 1) {
    out.push({ from: sorted[i]!, to: sorted[i + 1]! });
  }
  return out;
}

