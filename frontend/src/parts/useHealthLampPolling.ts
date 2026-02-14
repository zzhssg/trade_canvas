import { useCallback, useEffect, useMemo, useRef, useState } from "react"
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
  const {
    seriesId,
    fetcher,
    toneOf,
    normalizeError,
    delays: customDelays,
    isFastTone,
    enablePulse = true,
  } = args
  const [payload, setPayload] = useState<TPayload | null>(null)
  const [error, setError] = useState<string | null>(null)
  const timerRef = useRef<number | null>(null)
  const inFlightRef = useRef(false)
  const cancelledRef = useRef(false)
  const lastPulseRefreshAtRef = useRef(0)

  const delays = useMemo<PollingDelays>(() => {
    const next = customDelays ?? {}
    return {
      fastMs: clampDelay(next.fastMs ?? DEFAULT_DELAYS.fastMs, DEFAULT_DELAYS.fastMs),
      idleMs: clampDelay(next.idleMs ?? DEFAULT_DELAYS.idleMs, DEFAULT_DELAYS.idleMs),
      pulseThrottleMs: clampDelay(next.pulseThrottleMs ?? DEFAULT_DELAYS.pulseThrottleMs, DEFAULT_DELAYS.pulseThrottleMs),
    }
  }, [customDelays])
  const isFast = useCallback(
    (tone: TTone): boolean => {
      if (isFastTone) return isFastTone(tone)
      return tone === "red" || tone === "yellow"
    },
    [isFastTone]
  )

  const clearTimer = useCallback(() => {
    if (timerRef.current == null) return
    window.clearTimeout(timerRef.current)
    timerRef.current = null
  }, [])

  const load = useCallback(
    async (force: boolean) => {
      if (cancelledRef.current) return
      if (inFlightRef.current) {
        if (!force) return
        return
      }
      inFlightRef.current = true
      try {
        const next = await fetcher(seriesId)
        if (cancelledRef.current) return
        setPayload(next)
        setError(null)
        const tone = toneOf(next, null)
        clearTimer()
        const waitMs = isFast(tone) ? delays.fastMs : delays.idleMs
        timerRef.current = window.setTimeout(() => {
          void load(false)
        }, waitMs)
      } catch (cause: unknown) {
        if (cancelledRef.current) return
        const message = normalizeError ? normalizeError(cause) : cause instanceof Error ? cause.message : "load_failed"
        setError(message)
        setPayload(null)
        const tone = toneOf(null, message)
        clearTimer()
        const waitMs = isFast(tone) ? delays.fastMs : delays.idleMs
        timerRef.current = window.setTimeout(() => {
          void load(false)
        }, waitMs)
      } finally {
        inFlightRef.current = false
      }
    },
    [clearTimer, delays.fastMs, delays.idleMs, fetcher, isFast, normalizeError, seriesId, toneOf]
  )

  useEffect(() => {
    cancelledRef.current = false
    void load(true)
    return () => {
      cancelledRef.current = true
      clearTimer()
    }
  }, [clearTimer, load, seriesId])

  useEffect(() => {
    if (!enablePulse) return
    return subscribeMarketPulse((pulse) => {
      if (pulse.seriesId !== seriesId) return
      const now = Date.now()
      if (now - lastPulseRefreshAtRef.current < delays.pulseThrottleMs) return
      lastPulseRefreshAtRef.current = now
      void load(true)
    })
  }, [delays.pulseThrottleMs, enablePulse, load, seriesId])

  useEffect(() => {
    const onFocus = () => void load(true)
    const onVisibilityChange = () => {
      if (document.visibilityState !== "visible") return
      void load(true)
    }
    window.addEventListener("focus", onFocus)
    document.addEventListener("visibilitychange", onVisibilityChange)
    return () => {
      window.removeEventListener("focus", onFocus)
      document.removeEventListener("visibilitychange", onVisibilityChange)
    }
  }, [load])

  return { payload, error }
}
