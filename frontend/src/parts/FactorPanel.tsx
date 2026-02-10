import { useEffect, useRef, useState } from "react";

import { type FactorSpec, useFactorCatalog } from "../services/factorCatalog";
import { useFactorStore } from "../state/factorStore";

export function FactorPanel() {
  const { visibleFeatures, toggleFeatureVisibility, applyFeatureDefaults, setFeatureVisibility } = useFactorStore();
  const factors = useFactorCatalog();

  useEffect(() => {
    applyFeatureDefaults(factors);
  }, [applyFeatureDefaults, factors]);

  return (
    <div className="relative z-20 rounded-xl border border-white/10 bg-white/5 px-3 py-2 shadow-[0_0_0_1px_rgba(255,255,255,0.03)_inset] backdrop-blur">
      <div className="flex items-center justify-between gap-3">
        <div className="text-[11px] font-semibold uppercase tracking-wider text-white/60">Factors</div>
        <div className="text-[11px] text-white/40">feature → sub_feature (visibility)</div>
      </div>

      <div className="mt-2 flex flex-wrap items-center gap-2">
        {factors.map((f) => (
          <FactorChip
            key={f.key}
            factor={f}
            visibleFeatures={visibleFeatures}
            onToggle={(key) => {
              toggleFeatureVisibility(key);
            }}
            onToggleSub={(subKey) => {
              const parentChecked = visibleFeatures[f.key] ?? f.default_visible ?? true;
              const subChecked = visibleFeatures[subKey] ?? true;
              const enabling = !subChecked;
              if (enabling && !parentChecked) setFeatureVisibility(f.key, true);
              toggleFeatureVisibility(subKey);
            }}
          />
        ))}
      </div>
    </div>
  );
}

function FactorChip({
  factor,
  visibleFeatures,
  onToggle,
  onToggleSub
}: {
  factor: FactorSpec;
  visibleFeatures: Record<string, boolean>;
  onToggle: (key: string) => void;
  onToggleSub: (key: string) => void;
}) {
  const [open, setOpen] = useState(false);
  const closeTimerRef = useRef<number | null>(null);
  const checked = visibleFeatures[factor.key] ?? factor.default_visible ?? true;
  const hasSubs = (factor.sub_features ?? []).length > 0;
  const clearCloseTimer = () => {
    if (closeTimerRef.current !== null) {
      window.clearTimeout(closeTimerRef.current);
      closeTimerRef.current = null;
    }
  };
  const scheduleClose = () => {
    clearCloseTimer();
    closeTimerRef.current = window.setTimeout(() => {
      setOpen(false);
      closeTimerRef.current = null;
    }, 140);
  };

  useEffect(() => () => clearCloseTimer(), []);

  return (
    <div className="relative" onMouseEnter={clearCloseTimer} onMouseLeave={scheduleClose}>
      <button
        type="button"
        onClick={() => onToggle(factor.key)}
        onMouseEnter={() => hasSubs && setOpen(true)}
        className={[
          "flex items-center gap-2 rounded-md border px-2 py-1 text-[11px] transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-sky-500/60",
          checked
            ? "border-emerald-500/30 bg-emerald-500/15 text-emerald-200 shadow-[0_0_0_1px_rgba(16,185,129,0.10)_inset]"
            : "border-white/10 bg-black/20 text-white/70 hover:bg-white/10"
        ].join(" ")}
      >
        <span className="font-semibold">{factor.label}</span>
        <span className="text-white/40">{hasSubs ? `${factor.sub_features.length}` : ""}</span>
      </button>

      {open && hasSubs ? (
        <div
          className="absolute left-0 top-[calc(100%-1px)] z-50 min-w-[180px] rounded-xl border border-white/10 bg-[#0d1422]/95 p-2 shadow-xl shadow-black/30 backdrop-blur"
          onMouseEnter={clearCloseTimer}
        >
          <div className="mb-1 text-[10px] font-semibold uppercase tracking-wider text-white/40">Sub Features</div>
          <div className="flex flex-col gap-1">
            {factor.sub_features.map((sf) => {
              const sfChecked = visibleFeatures[sf.key] ?? sf.default_visible ?? true;
              return (
                <label
                  key={sf.key}
                  className="flex cursor-pointer items-center gap-2 rounded px-2 py-1 text-[11px] hover:bg-white/5"
                >
                  <input
                    type="checkbox"
                    checked={sfChecked}
                    onChange={() => onToggleSub(sf.key)}
                    className="h-3 w-3 rounded border-white/20 bg-black/30 accent-emerald-500"
                  />
                  <span className={sfChecked ? "text-white/80" : "text-white/40"}>{sf.label}</span>
                </label>
              );
            })}
          </div>
        </div>
      ) : null}
    </div>
  );
}
