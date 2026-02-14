export type MarketPulseType = "candles_batch" | "candle_forming" | "candle_closed" | "gap"

export type MarketPulse = {
  seriesId: string
  type: MarketPulseType
  candleTime: number | null
  emittedAtMs: number
}

const MARKET_PULSE_EVENT_NAME = "trade_canvas:market_pulse"

function toFiniteInt(value: unknown): number | null {
  if (typeof value !== "number" || !Number.isFinite(value)) return null
  return Math.trunc(value)
}

function parsePulseDetail(value: unknown): MarketPulse | null {
  if (typeof value !== "object" || value === null) return null
  const raw = value as Record<string, unknown>
  const seriesId = typeof raw.seriesId === "string" ? raw.seriesId.trim() : ""
  const type = raw.type
  const emittedAtRaw = toFiniteInt(raw.emittedAtMs)
  const candleTimeRaw = raw.candleTime == null ? null : toFiniteInt(raw.candleTime)
  if (!seriesId) return null
  if (type !== "candles_batch" && type !== "candle_forming" && type !== "candle_closed" && type !== "gap") {
    return null
  }
  return {
    seriesId,
    type,
    candleTime: candleTimeRaw,
    emittedAtMs: emittedAtRaw ?? Date.now(),
  }
}

export function emitMarketPulse(args: {
  seriesId: string
  type: MarketPulseType
  candleTime?: number | null
}) {
  if (typeof window === "undefined") return
  const pulse = parsePulseDetail({
    seriesId: args.seriesId,
    type: args.type,
    candleTime: args.candleTime ?? null,
    emittedAtMs: Date.now(),
  })
  if (!pulse) return
  window.dispatchEvent(new CustomEvent<MarketPulse>(MARKET_PULSE_EVENT_NAME, { detail: pulse }))
}

export function subscribeMarketPulse(handler: (pulse: MarketPulse) => void): () => void {
  if (typeof window === "undefined") return () => {}
  const onPulse = (event: Event) => {
    const detail = parsePulseDetail((event as CustomEvent<unknown>).detail)
    if (!detail) return
    handler(detail)
  }
  window.addEventListener(MARKET_PULSE_EVENT_NAME, onPulse)
  return () => {
    window.removeEventListener(MARKET_PULSE_EVENT_NAME, onPulse)
  }
}
