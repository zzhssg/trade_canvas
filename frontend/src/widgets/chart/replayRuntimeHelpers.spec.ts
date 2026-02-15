import { describe, expect, test, vi } from "vitest";

import type { Candle } from "./types";
import { syncReplayFocusFromIndex } from "./replayRuntimeHelpers";

function buildCandle(time: number): Candle {
  return { time: time as Candle["time"], open: 1, high: 1, low: 1, close: 1 };
}

describe("syncReplayFocusFromIndex", () => {
  test("no-op when focus time is already aligned", () => {
    const setReplayIndex = vi.fn();
    const setReplayFocusTime = vi.fn();

    syncReplayFocusFromIndex({
      replayEnabled: true,
      replayPackageEnabled: false,
      replayIndex: 1,
      replayTotal: 3,
      replayFocusTime: 600,
      replayAllCandlesRef: { current: [buildCandle(300), buildCandle(600), buildCandle(900)] },
      setReplayIndex,
      setReplayFocusTime
    });

    expect(setReplayIndex).not.toHaveBeenCalled();
    expect(setReplayFocusTime).not.toHaveBeenCalled();
  });

  test("clamps out-of-range index before side effects", () => {
    const setReplayIndex = vi.fn();

    syncReplayFocusFromIndex({
      replayEnabled: true,
      replayPackageEnabled: false,
      replayIndex: 99,
      replayTotal: 2,
      replayFocusTime: null,
      replayAllCandlesRef: { current: [buildCandle(300), buildCandle(600)] },
      setReplayIndex,
      setReplayFocusTime: vi.fn()
    });

    expect(setReplayIndex).toHaveBeenCalledTimes(1);
    expect(setReplayIndex).toHaveBeenCalledWith(1);
  });
});
