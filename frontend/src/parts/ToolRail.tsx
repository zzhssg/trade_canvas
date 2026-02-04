import { useMemo, useState } from "react";

type ToolKey =
  | "cursor"
  | "crosshair"
  | "trendline"
  | "brush"
  | "text"
  | "measure"
  | "magnet"
  | "lock"
  | "settings";

export function ToolRail() {
  const [active, setActive] = useState<ToolKey>("cursor");
  const groups = useMemo(
    () =>
      [
        [
          { key: "cursor", label: "Cursor" },
          { key: "crosshair", label: "Crosshair" },
          { key: "trendline", label: "Trend Line" }
        ],
        [
          { key: "brush", label: "Brush" },
          { key: "text", label: "Text" },
          { key: "measure", label: "Measure" }
        ],
        [
          { key: "magnet", label: "Magnet" },
          { key: "lock", label: "Lock" }
        ]
      ] as const,
    []
  );

  return (
    <div className="flex h-full w-full flex-col overflow-visible border-r border-white/10 bg-white/[0.04] backdrop-blur">
      <div className="flex h-14 items-center justify-center border-b border-white/10">
        <div className="grid h-8 w-8 place-items-center rounded-lg border border-white/10 bg-black/35 text-[11px] font-semibold tracking-wide text-white/80 shadow-[0_0_0_1px_rgba(255,255,255,0.03)_inset]">
          TC
        </div>
      </div>

      <div className="flex min-h-0 flex-1 flex-col gap-3 overflow-auto p-2">
        {groups.map((group, idx) => (
          <div key={idx} className="flex flex-col gap-1">
            {group.map((t) => (
              <ToolButton
                key={t.key}
                active={active === t.key}
                label={t.label}
                onClick={() => setActive(t.key)}
                icon={<Icon kind={t.key} />}
              />
            ))}
            {idx < groups.length - 1 ? <Divider /> : null}
          </div>
        ))}
      </div>

      <div className="border-t border-white/10 p-2">
        <ToolButton
          active={active === "settings"}
          label="Settings"
          onClick={() => setActive("settings")}
          icon={<Icon kind="settings" />}
        />
      </div>
    </div>
  );
}

function Divider() {
  return <div className="my-2 h-px w-full bg-white/10" />;
}

function ToolButton({
  icon,
  label,
  active,
  onClick
}: {
  icon: React.ReactNode;
  label: string;
  active: boolean;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      title={label}
      aria-label={label}
      aria-pressed={active}
      onClick={onClick}
      className={[
        "group relative grid h-9 w-full place-items-center rounded-xl border text-white/80 outline-none transition",
        "focus-visible:ring-2 focus-visible:ring-sky-500/60",
        active
          ? "border-sky-500/25 bg-sky-500/10 text-white shadow-[0_0_0_1px_rgba(56,189,248,0.10)_inset]"
          : "border-transparent hover:border-white/10 hover:bg-white/5"
      ].join(" ")}
    >
      <span className={active ? "text-white" : "text-white/75 group-hover:text-white"}>{icon}</span>
      <span className="pointer-events-none absolute left-full top-1/2 z-20 ml-2 hidden -translate-y-1/2 whitespace-nowrap rounded-md border border-white/10 bg-black/80 px-2 py-1 text-[11px] text-white/90 shadow-xl shadow-black/30 backdrop-blur group-hover:block">
        {label}
      </span>
    </button>
  );
}

function Icon({ kind }: { kind: ToolKey }) {
  const cls = "h-4 w-4";
  switch (kind) {
    case "cursor":
      return (
        <svg className={cls} viewBox="0 0 24 24" fill="none" aria-hidden="true">
          <path d="M5 3l14 9-8 2-2 8-4-19z" stroke="currentColor" strokeWidth="1.6" strokeLinejoin="round" />
        </svg>
      );
    case "crosshair":
      return (
        <svg className={cls} viewBox="0 0 24 24" fill="none" aria-hidden="true">
          <circle cx="12" cy="12" r="7" stroke="currentColor" strokeWidth="1.6" />
          <path d="M12 3v4M12 17v4M3 12h4M17 12h4" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
        </svg>
      );
    case "trendline":
      return (
        <svg className={cls} viewBox="0 0 24 24" fill="none" aria-hidden="true">
          <path d="M5 16l6-6 3 3 5-5" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
          <circle cx="5" cy="16" r="1.3" fill="currentColor" />
          <circle cx="11" cy="10" r="1.3" fill="currentColor" />
          <circle cx="14" cy="13" r="1.3" fill="currentColor" />
          <circle cx="19" cy="8" r="1.3" fill="currentColor" />
        </svg>
      );
    case "brush":
      return (
        <svg className={cls} viewBox="0 0 24 24" fill="none" aria-hidden="true">
          <path
            d="M4 20c3 0 5-2 5-5 0-1.5.7-2.6 2-3l8-3-3 8c-.4 1.2-1.6 2-3 2-3 0-4 1.4-4 3.5V20"
            stroke="currentColor"
            strokeWidth="1.6"
            strokeLinejoin="round"
          />
          <path d="M14 5l5 5" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
        </svg>
      );
    case "text":
      return (
        <svg className={cls} viewBox="0 0 24 24" fill="none" aria-hidden="true">
          <path d="M6 6h12M12 6v14M9 20h6" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
        </svg>
      );
    case "measure":
      return (
        <svg className={cls} viewBox="0 0 24 24" fill="none" aria-hidden="true">
          <path d="M7 7l10 10" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
          <path d="M6 10V6h4" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
          <path d="M18 14v4h-4" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
        </svg>
      );
    case "magnet":
      return (
        <svg className={cls} viewBox="0 0 24 24" fill="none" aria-hidden="true">
          <path
            d="M7 4v8a5 5 0 0 0 10 0V4"
            stroke="currentColor"
            strokeWidth="1.6"
            strokeLinecap="round"
          />
          <path d="M7 8h4M13 8h4" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
        </svg>
      );
    case "lock":
      return (
        <svg className={cls} viewBox="0 0 24 24" fill="none" aria-hidden="true">
          <path
            d="M7 11V8a5 5 0 0 1 10 0v3"
            stroke="currentColor"
            strokeWidth="1.6"
            strokeLinecap="round"
          />
          <path
            d="M7 11h10v9H7v-9z"
            stroke="currentColor"
            strokeWidth="1.6"
            strokeLinejoin="round"
          />
        </svg>
      );
    case "settings":
      return (
        <svg className={cls} viewBox="0 0 24 24" fill="none" aria-hidden="true">
          <path
            d="M12 15.5a3.5 3.5 0 1 0 0-7 3.5 3.5 0 0 0 0 7z"
            stroke="currentColor"
            strokeWidth="1.6"
          />
          <path
            d="M19 12a7.2 7.2 0 0 0-.1-1l2-1.6-2-3.4-2.4 1a7.8 7.8 0 0 0-1.7-1L14.5 3h-5L9.2 6a7.8 7.8 0 0 0-1.7 1l-2.4-1-2 3.4 2 1.6a7.2 7.2 0 0 0 0 2L3.1 14.6l2 3.4 2.4-1a7.8 7.8 0 0 0 1.7 1l.3 3h5l.3-3a7.8 7.8 0 0 0 1.7-1l2.4 1 2-3.4-2-1.6c.1-.3.1-.7.1-1z"
            stroke="currentColor"
            strokeWidth="1.2"
            strokeLinejoin="round"
          />
        </svg>
      );
    default:
      return null;
  }
}
