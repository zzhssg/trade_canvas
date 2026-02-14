import { beforeEach, describe, expect, test } from "vitest";

import type { OverlayInstructionPatchItemV1 } from "../widgets/chart/types";
import { useReplayStore } from "./replayStore";

function makeInstruction(
  instructionId: string,
  versionId: number,
  visibleTime: number
): OverlayInstructionPatchItemV1 {
  return {
    instruction_id: instructionId,
    version_id: versionId,
    visible_time: visibleTime
  } as OverlayInstructionPatchItemV1;
}

describe("replayStore idempotent actions", () => {
  beforeEach(() => {
    useReplayStore.setState(useReplayStore.getInitialState(), true);
  });

  test("setFocusTime skips duplicate state writes", () => {
    let notifications = 0;
    const unsubscribe = useReplayStore.subscribe(() => {
      notifications += 1;
    });
    const actions = useReplayStore.getState();

    actions.setFocusTime(1200);
    actions.setFocusTime(1200);

    unsubscribe();
    expect(useReplayStore.getState().focusTime).toBe(1200);
    expect(notifications).toBe(1);
  });

  test("setCurrentDrawInstructions skips equivalent payload updates", () => {
    let notifications = 0;
    const unsubscribe = useReplayStore.subscribe(() => {
      notifications += 1;
    });
    const actions = useReplayStore.getState();

    actions.setCurrentDrawInstructions([makeInstruction("pen.1", 3, 900)]);
    actions.setCurrentDrawInstructions([makeInstruction("pen.1", 3, 900)]);

    unsubscribe();
    expect(useReplayStore.getState().currentDrawInstructions).toHaveLength(1);
    expect(notifications).toBe(1);
  });
});
