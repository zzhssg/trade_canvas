export function timeframeToSeconds(timeframe: string): number | null {
  const tf = timeframe.trim();
  const m = tf.match(/^(\d+)([mhdw])$/i);
  if (!m) return null;
  const n = Number(m[1]);
  if (!Number.isFinite(n) || n <= 0) return null;
  const unit = m[2]!.toLowerCase();
  if (unit === "m") return n * 60;
  if (unit === "h") return n * 60 * 60;
  if (unit === "d") return n * 24 * 60 * 60;
  if (unit === "w") return n * 7 * 24 * 60 * 60;
  return null;
}

