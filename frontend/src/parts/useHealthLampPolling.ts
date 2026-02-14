import { useEffect, useMemo, useRef, useState } from "react"
import { subscribeMarketPulse } from "../lib/marketPulse"

type PollingDelays = {
  fastMs: number
  idleMs: number
  pulseThrottleMs: number
}

type UseHealthLampPollingArgs<TPayload, TTone extends string> = {
  seriesId: string
  fetcher: (seriesId: string) => Promise<TPayload>
  toneOf: (payload: TPayload | null, error: string | null) => TTone
  normalizeError?: (cause: unknown) => string
  delays?: Partial<PollingDelays>
  isFastTone?: (tone: TTone) => boolean
  enablePulse?: boolean
}
type UseHealthLampPollingResult<TPayload> = { payload: TPayload | null; error: string | null }
const DEFAULT_DELAYS: PollingDelays = { fastMs: 2_000, idleMs: 5_000, pulseThrottleMs: 600 }

function clampDelay(raw: number, fallback: number): number {
  if (!Number.isFinite(raw)) return fallback
  return Math.max(200, Math.trunc(raw))
}

export function useHealthLampPolling<TPayload, TTone extends string = "green" | "yellow" | "red" | "gray">(
  args: UseHealthLampPollingArgs<TPayload, TTone>
): UseHealthLampPollingResult<TPayload> {
  const [payload, setPayload] = useState<TPayload | null>(null)
  const [error, setError] = useState<string | null>(null)
  const delays = useMemo<PollingDelays>(() => {
    const next = args.delays ?? {}
    return {
      fastMs: clampDelay(next.fastMs ?? DEFAULT_DELAYS.fastMs, DEFAULT_DELAYS.fastMs),
      idleMs: clampDelay(next.idleMs ?? DEFAULT_DELAYS.idleMs, DEFAULT_DELAYS.idleMs),
      pulseThrottleMs: clampDelay(next.pulseThrottleMs ?? DEFAULT_DELAYS.pulseThrottleMs, DEFAULT_DELAYS.pulseThrottleMs),
    }
  }, [args.delays])

  const seriesIdRef = useRef(args.seriesId)
  const fetcherRef = useRef(args.fetcher)
  const toneOfRef = useRef(args.toneOf)
  const normalizeErrorRef = useRef(args.normalizeError)
  const isFastToneRef = useRef(args.isFastTone)
  const delaysRef = useRef(delays)
  const timerRef = useRef<number | null>(null)
  const inFlightRef = useRef(false)
  const pendingForceRef = useRef(false)
  const cancelledRef = useRef(false)
  const lastPulseRefreshAtRef = useRef(0)

  seriesIdRef.current = args.seriesId
  fetcherRef.current = args.fetcher
  toneOfRef.current = args.toneOf
  normalizeErrorRef.current = args.normalizeError
  isFastToneRef.current = args.isFastTone
  delaysRef.current = delays

  useEffect(() => {
    cancelledRef.current = false
    pendingForceRef.current = false
    const clearTimer = () => {
      if (timerRef.current == null) return
      window.clearTimeout(timerRef.current)
      timerRef.current = null
    }
    const resolveFast = (tone: TTone): boolean => {
      const judge = isFastToneRef.current
      if (judge) return judge(tone)
      return tone === "red" || tone === "yellow"
    }
    const normalizeError = (cause: unknown): string => {
      const mapper = normalizeErrorRef.current
      if (mapper) return mapper(cause)
      if (cause instanceof Error && cause.message) return cause.message
      return "load_failed"
    }
    const scheduleNext = (tone: TTone) => {
      clearTimer()
      const currentDelays = delaysRef.current
      const waitMs = resolveFast(tone) ? currentDelays.fastMs : currentDelays.idleMs
      timerRef.current = window.setTimeout(() => {
        void load(false)
      }, waitMs)
    }
    const load = async (force: boolean) => {
      if (cancelledRef.current) return
      if (inFlightRef.current) {
        if (force) pendingForceRef.current = true
        return
      }
      inFlightRef.current = true
      try {
        const next = await fetcherRef.current(seriesIdRef.current)
        if (cancelledRef.current) return
        setPayload(next)
        setError(null)
        const tone = toneOfRef.current(next, null)
        scheduleNext(tone)
      } catch (cause: unknown) {
        if (cancelledRef.current) return
        const message = normalizeError(cause)
        setPayload(null)
        setError(message)
        const tone = toneOfRef.current(null, message)
        scheduleNext(tone)
      } finally {
        inFlightRef.current = false
        if (cancelledRef.current) return
        if (pendingForceRef.current) {
          pendingForceRef.current = false
          clearTimer()
          void load(true)
        }
      }
    }
    const onFocus = () => void load(true)
    const onVisibilityChange = () => {
      if (document.visibilityState !== "visible") return
      void load(true)
    }
    const unsubscribePulse = args.enablePulse === false
      ? () => {}
      : subscribeMarketPulse((pulse) => {
          if (pulse.seriesId !== seriesIdRef.current) return
          const now = Date.now()
          if (now - lastPulseRefreshAtRef.current < delaysRef.current.pulseThrottleMs) return
          lastPulseRefreshAtRef.current = now
          void load(true)
        })
    window.addEventListener("focus", onFocus)
    document.addEventListener("visibilitychange", onVisibilityChange)
    void load(true)
    return () => {
      cancelledRef.current = true
      pendingForceRef.current = false
      unsubscribePulse()
      window.removeEventListener("focus", onFocus)
      document.removeEventListener("visibilitychange", onVisibilityChange)
      clearTimer()
    }
  }, [args.enablePulse, args.seriesId])
  return { payload, error }
}
