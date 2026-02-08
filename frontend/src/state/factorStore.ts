import { create } from "zustand";
import { persist } from "zustand/middleware";

import type { FactorSpec } from "../services/factorCatalog";

type FactorState = {
  visibleFeatures: Record<string, boolean>;
  setFeatureVisibility: (key: string, visible: boolean) => void;
  toggleFeatureVisibility: (key: string) => void;
  applyFeatureDefaults: (features: FactorSpec[]) => void;
};

export const useFactorStore = create<FactorState>()(
  persist(
    (set) => ({
      visibleFeatures: {},
      setFeatureVisibility: (key, visible) => set((s) => ({ visibleFeatures: { ...s.visibleFeatures, [key]: visible } })),
      toggleFeatureVisibility: (key) =>
        set((s) => ({ visibleFeatures: { ...s.visibleFeatures, [key]: !(s.visibleFeatures[key] ?? true) } })),
      applyFeatureDefaults: (features) =>
        set((s) => {
          const next = { ...s.visibleFeatures };
          let changed = false;

          const apply = (key?: string, defaultVisible?: boolean) => {
            if (!key) return;
            if (next[key] !== undefined) return;
            next[key] = defaultVisible ?? true;
            changed = true;
          };

          for (const f of features) {
            apply(f.key, f.default_visible);
            for (const sf of f.sub_features ?? []) apply(sf.key, sf.default_visible);
          }

          return changed ? { visibleFeatures: next } : s;
        })
    }),
    {
      name: "trade-canvas-factors",
      version: 2,
      migrate: (persistedState: unknown, version) => {
        const state = (persistedState as { visibleFeatures?: Record<string, boolean> } | undefined) ?? {};
        const visibleFeatures = { ...(state.visibleFeatures ?? {}) };
        if (version < 2) {
          visibleFeatures["zhongshu.dead"] = true;
        }
        return { ...state, visibleFeatures };
      }
    }
  )
);
