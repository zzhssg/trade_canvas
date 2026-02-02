export type FactorSubFeatureSpec = {
  key: string;
  label: string;
  default_visible?: boolean;
};

export type FactorSpec = {
  key: string;
  label: string;
  default_visible?: boolean;
  sub_features: FactorSubFeatureSpec[];
};

/**
 * Frontend factor catalog (v0):
 * - Mirrors trade_system "overlay_features + sub_features" shape.
 * - v1 should come from backend Factor/Overlay feature endpoints.
 */
export const FACTOR_CATALOG: FactorSpec[] = [
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
    sub_features: [{ key: "pen.confirmed", label: "Confirmed", default_visible: false }]
  },
  {
    key: "sma",
    label: "SMA",
    default_visible: true,
    sub_features: [
      { key: "sma_5", label: "SMA 5", default_visible: true },
      { key: "sma_20", label: "SMA 20", default_visible: true }
    ]
  },
  {
    key: "signal",
    label: "Signals",
    default_visible: true,
    sub_features: [{ key: "signal.entry", label: "Entry", default_visible: true }]
  }
];

export function getFactorParentsBySubKey(factors: FactorSpec[]): Record<string, string> {
  const out: Record<string, string> = {};
  for (const f of factors) {
    for (const sf of f.sub_features) out[sf.key] = f.key;
  }
  return out;
}
