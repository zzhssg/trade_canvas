import type { BusinessDay, Time } from "lightweight-charts";

function pad2(n: number): string {
  return String(n).padStart(2, "0");
}

function isBusinessDay(value: unknown): value is BusinessDay {
  if (!value || typeof value !== "object") return false;
  const v = value as Record<string, unknown>;
  return typeof v.year === "number" && typeof v.month === "number" && typeof v.day === "number";
}

export function timeToUnixSeconds(time: Time): number | null {
  if (typeof time === "number") return Number.isFinite(time) ? time : null;
  if (typeof time === "string") {
    // "YYYY-MM-DD" or ISO string; lightweight-charts sometimes uses string in daily charts.
    const ms = Date.parse(time);
    if (!Number.isFinite(ms)) return null;
    return Math.floor(ms / 1000);
  }
  if (isBusinessDay(time)) {
    // Use local timezone to be consistent with existing UI (e.g. FibTool formatting).
    const d = new Date(time.year, time.month - 1, time.day, 0, 0, 0, 0);
    return Math.floor(d.getTime() / 1000);
  }
  return null;
}

export function formatUnixSecondsYmdHm(timeSec: number): string {
  const t = Number(timeSec);
  if (!Number.isFinite(t)) return "--";
  const d = new Date(t * 1000);
  const yyyy = String(d.getFullYear());
  const mm = pad2(d.getMonth() + 1);
  const dd = pad2(d.getDate());
  const hh = pad2(d.getHours());
  const mi = pad2(d.getMinutes());
  return `${yyyy}-${mm}-${dd} ${hh}:${mi}`;
}

export function formatUnixSecondsMdHm(timeSec: number): string {
  const t = Number(timeSec);
  if (!Number.isFinite(t)) return "--";
  const d = new Date(t * 1000);
  const mm = pad2(d.getMonth() + 1);
  const dd = pad2(d.getDate());
  const hh = pad2(d.getHours());
  const mi = pad2(d.getMinutes());
  return `${mm}-${dd} ${hh}:${mi}`;
}

export function formatChartTimeYmdHm(time: Time): string {
  const sec = timeToUnixSeconds(time);
  if (sec == null) return "--";
  return formatUnixSecondsYmdHm(sec);
}
