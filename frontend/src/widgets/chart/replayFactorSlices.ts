/**
 * 回放因子切片构建 — 纯函数。
 *
 * 输入 replay package 的 factor snapshot 增量，输出当前帧的 GetFactorSlicesResponseV1。
 */
import type {
  FactorSliceV1,
  GetFactorSlicesResponseV1,
  ReplayFactorSchemaV1,
  ReplayFactorSnapshotV1
} from "./types";

function sortedSnapshotTimes(
  snapshotByTime: Record<number, Record<string, ReplayFactorSnapshotV1>>
): number[] {
  const out: number[] = [];
  for (const key of Object.keys(snapshotByTime)) {
    const parsed = Number(key);
    if (!Number.isFinite(parsed)) continue;
    out.push(Math.floor(parsed));
  }
  out.sort((a, b) => a - b);
  return out;
}

function resolveLatestSnapshots(
  atTime: number,
  snapshotByTime: Record<number, Record<string, ReplayFactorSnapshotV1>>
): Record<string, ReplayFactorSnapshotV1> {
  const latestByFactor: Record<string, ReplayFactorSnapshotV1> = {};
  const times = sortedSnapshotTimes(snapshotByTime);
  for (const t of times) {
    if (t > atTime) break;
    const rows = snapshotByTime[t] ?? {};
    for (const [factorName, row] of Object.entries(rows)) {
      latestByFactor[factorName] = row;
    }
  }
  return latestByFactor;
}

function normalizeSnapshotForTime(
  seriesId: string,
  aligned: number,
  candleId: string,
  factorName: string,
  source: FactorSliceV1
): FactorSliceV1 {
  return {
    schema_version: source.schema_version ?? 1,
    history: source.history ?? {},
    head: source.head ?? {},
    meta: {
      series_id: seriesId,
      epoch: source.meta?.epoch ?? 0,
      at_time: aligned,
      candle_id: candleId,
      factor_name: factorName
    }
  };
}

/** 从 replay factor snapshots 构建完整的 factor slices 响应 */
export function buildReplayFactorSlices(params: {
  seriesId: string;
  atTime: number;
  factorSchema: ReplayFactorSchemaV1[];
  factorSnapshotByTime: Record<number, Record<string, ReplayFactorSnapshotV1>>;
}): GetFactorSlicesResponseV1 {
  const { seriesId } = params;
  const aligned = Math.max(0, Math.floor(params.atTime));
  const candleId = `${seriesId}:${aligned}`;
  const latestByFactor = resolveLatestSnapshots(aligned, params.factorSnapshotByTime);

  const orderedFactors: string[] = [];
  const seen = new Set<string>();
  for (const item of params.factorSchema ?? []) {
    const factorName = String(item.factor_name || "").trim();
    if (!factorName || seen.has(factorName)) continue;
    if (!latestByFactor[factorName]) continue;
    seen.add(factorName);
    orderedFactors.push(factorName);
  }
  for (const factorName of Object.keys(latestByFactor).sort()) {
    if (seen.has(factorName)) continue;
    seen.add(factorName);
    orderedFactors.push(factorName);
  }

  const snapshots: Record<string, FactorSliceV1> = {};
  for (const factorName of orderedFactors) {
    const row = latestByFactor[factorName];
    if (!row?.snapshot) continue;
    snapshots[factorName] = normalizeSnapshotForTime(seriesId, aligned, candleId, factorName, row.snapshot);
  }

  return {
    schema_version: 1,
    series_id: seriesId,
    at_time: aligned,
    candle_id: candleId,
    factors: orderedFactors,
    snapshots
  };
}
