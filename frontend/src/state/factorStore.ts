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
      version: 4,
      migrate: (persistedState: unknown, version) => {
        const state = (persistedState as { visibleFeatures?: Record<string, boolean> } | undefined) ?? {};
        const visibleFeatures = { ...(state.visibleFeatures ?? {}) };
        if (version < 2) {
          visibleFeatures["zhongshu.dead"] = true;
        }
        if (version < 3) {
          Object.assign(visibleFeatures, {
            pivot: true,
            "pivot.major": true,
            "pivot.minor": false,
            pen: true,
            "pen.confirmed": true,
            "pen.extending": true,
            "pen.candidate": true,
            zhongshu: true,
            "zhongshu.alive": true,
            "zhongshu.dead": true,
            anchor: true,
            "anchor.current": true,
            "anchor.history": true,
            "anchor.switch": true,
            sma: false,
            sma_5: false,
            sma_20: false,
            signal: false,
            "signal.entry": false
          });
        }
        if (version < 4) {
          delete visibleFeatures["anchor.reverse"];
        }
        return { ...state, visibleFeatures };
      }
    }
  )
);
