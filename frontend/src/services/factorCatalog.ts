import { useEffect, useState } from "react";

import { apiUrl } from "../lib/api";

export type FactorSubFeatureSpec = {
  key: string;
  label: string;
  default_visible: boolean;
};

export type FactorSpec = {
  key: string;
  label: string;
  default_visible: boolean;
  sub_features: FactorSubFeatureSpec[];
};

const FALLBACK_FACTOR_CATALOG: FactorSpec[] = [
  {
    key: "pivot",
    label: "Pivot",
    default_visible: true,
    sub_features: [
      { key: "pivot.major", label: "Major", default_visible: true },
      { key: "pivot.minor", label: "Minor", default_visible: false }
    ]
  },
  {
    key: "pen",
    label: "Pen",
    default_visible: true,
    sub_features: [
      { key: "pen.confirmed", label: "Confirmed", default_visible: true },
      { key: "pen.extending", label: "Extending", default_visible: true },
      { key: "pen.candidate", label: "Candidate", default_visible: true }
    ]
  },
  {
    key: "zhongshu",
    label: "Zhongshu",
    default_visible: true,
    sub_features: [
      { key: "zhongshu.alive", label: "Alive", default_visible: true },
      { key: "zhongshu.dead", label: "Dead", default_visible: true }
    ]
  },
  {
    key: "anchor",
    label: "Anchor",
    default_visible: true,
    sub_features: [
      { key: "anchor.current", label: "Current", default_visible: true },
      { key: "anchor.history", label: "History", default_visible: true },
      { key: "anchor.switch", label: "Switches", default_visible: true }
    ]
  },
  {
    key: "sr",
    label: "SR",
    default_visible: true,
    sub_features: [
      { key: "sr.active", label: "Active", default_visible: true },
      { key: "sr.broken", label: "Broken", default_visible: false }
    ]
  },
  {
    key: "sma",
    label: "SMA",
    default_visible: false,
    sub_features: [
      { key: "sma_5", label: "SMA 5", default_visible: false },
      { key: "sma_20", label: "SMA 20", default_visible: false }
    ]
  },
  {
    key: "signal",
    label: "Signals",
    default_visible: false,
    sub_features: [{ key: "signal.entry", label: "Entry", default_visible: false }]
  }
];

let cachedCatalog: FactorSpec[] | null = null;
let inflightCatalog: Promise<FactorSpec[]> | null = null;

function normalizeFactorSpec(raw: unknown): FactorSpec | null {
  if (!raw || typeof raw !== "object") return null;
  const item = raw as Record<string, unknown>;
  const key = String(item.key ?? "").trim();
  if (!key) return null;
  const label = String(item.label ?? key).trim() || key;
  const defaultVisibleRaw = item.default_visible;
  const defaultVisible = typeof defaultVisibleRaw === "boolean" ? defaultVisibleRaw : true;
  const rawSubs = Array.isArray(item.sub_features) ? item.sub_features : [];
  const subFeatures: FactorSubFeatureSpec[] = [];
  for (const entry of rawSubs) {
    if (!entry || typeof entry !== "object") continue;
    const sub = entry as Record<string, unknown>;
    const subKey = String(sub.key ?? "").trim();
    if (!subKey) continue;
    const subLabel = String(sub.label ?? subKey).trim() || subKey;
    const subDefaultRaw = sub.default_visible;
    const subDefault = typeof subDefaultRaw === "boolean" ? subDefaultRaw : true;
    subFeatures.push({
      key: subKey,
      label: subLabel,
      default_visible: subDefault
    });
  }
  return {
    key,
    label,
    default_visible: defaultVisible,
    sub_features: subFeatures
  };
}

function normalizeCatalogPayload(raw: unknown): FactorSpec[] | null {
  if (!raw || typeof raw !== "object") return null;
  const payload = raw as Record<string, unknown>;
  const factors = Array.isArray(payload.factors) ? payload.factors : null;
  if (!factors) return null;
  const normalized = factors
    .map((entry) => normalizeFactorSpec(entry))
    .filter((entry): entry is FactorSpec => entry !== null);
  if (normalized.length === 0) return null;
  return normalized;
}

export async function fetchFactorCatalog(): Promise<FactorSpec[]> {
  if (cachedCatalog) return cachedCatalog;
  if (inflightCatalog) return inflightCatalog;
  inflightCatalog = (async () => {
    try {
      const res = await fetch(apiUrl("/api/factor/catalog"));
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const payload = await res.json();
      const normalized = normalizeCatalogPayload(payload);
      if (normalized && normalized.length > 0) {
        cachedCatalog = normalized;
        return normalized;
      }
    } catch {
      // fallback to local defaults
    }
    cachedCatalog = FALLBACK_FACTOR_CATALOG;
    return FALLBACK_FACTOR_CATALOG;
  })();
  const result = await inflightCatalog;
  inflightCatalog = null;
  return result;
}

export function useFactorCatalog(): FactorSpec[] {
  const [factors, setFactors] = useState<FactorSpec[]>(cachedCatalog ?? FALLBACK_FACTOR_CATALOG);
  useEffect(() => {
    let alive = true;
    fetchFactorCatalog()
      .then((next) => {
        if (!alive) return;
        setFactors(next);
      })
      .catch(() => {
        if (!alive) return;
        setFactors(FALLBACK_FACTOR_CATALOG);
      });
    return () => {
      alive = false;
    };
  }, []);
  return factors;
}

export function getFactorParentsBySubKey(factors: FactorSpec[]): Record<string, string> {
  const out: Record<string, string> = {};
  for (const factor of factors) {
    for (const subFeature of factor.sub_features) out[subFeature.key] = factor.key;
  }
  return out;
}
