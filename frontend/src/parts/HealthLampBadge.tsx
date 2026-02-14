export type HealthLampTone = "green" | "yellow" | "red" | "gray";

export type HealthLampView<TTone extends string = HealthLampTone> = {
  tone: TTone;
  label: string;
  detail: string;
};

function normalizeTone(tone: string): HealthLampTone {
  if (tone === "green" || tone === "yellow" || tone === "red" || tone === "gray") return tone;
  return "gray";
}

function dotClass(tone: HealthLampTone): string {
  if (tone === "green") return "bg-emerald-400 shadow-[0_0_8px_rgba(16,185,129,0.6)]";
  if (tone === "yellow") return "bg-amber-300 shadow-[0_0_8px_rgba(251,191,36,0.6)]";
  if (tone === "red") return "bg-rose-400 shadow-[0_0_8px_rgba(244,63,94,0.55)]";
  return "bg-gray-400 shadow-[0_0_6px_rgba(148,163,184,0.45)]";
}

function textClass(tone: HealthLampTone): string {
  if (tone === "green") return "text-emerald-300";
  if (tone === "yellow") return "text-amber-200";
  if (tone === "red") return "text-rose-300";
  return "text-white/60";
}

type HealthLampBadgeProps<TTone extends string> = {
  view: HealthLampView<TTone>;
  testId: string;
  statusAttrName: string;
};

export function HealthLampBadge<TTone extends string>({ view, testId, statusAttrName }: HealthLampBadgeProps<TTone>) {
  const tone = normalizeTone(view.tone);
  const statusAttr = { [statusAttrName]: view.tone } as Record<string, string>;
  return (
    <div
      className="inline-flex items-center gap-1.5 rounded-md border border-white/10 bg-black/25 px-2 py-1 font-mono text-[11px]"
      title={view.detail}
      data-testid={testId}
      {...statusAttr}
    >
      <span className={["inline-block h-2 w-2 rounded-full", dotClass(tone)].join(" ")} />
      <span className={textClass(tone)}>{view.label}</span>
    </div>
  );
}

export function formatDuration(seconds: number | null): string {
  if (seconds == null || !Number.isFinite(seconds)) return "未知";
  if (seconds <= 0) return "0m";
  const totalMinutes = Math.max(1, Math.ceil(seconds / 60));
  const hours = Math.floor(totalMinutes / 60);
  const minutes = totalMinutes % 60;
  if (hours <= 0) return `${totalMinutes}m`;
  if (minutes <= 0) return `${hours}h`;
  return `${hours}h${minutes}m`;
}
