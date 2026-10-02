// SPDX-License-Identifier: MPL-2.0
import type { ReplayState } from "./contract";

export const stateAtTick = (
  states: readonly ReplayState[],
  tick: number,
): ReplayState => {
  const state = states[tick - (states[0]?.tick ?? 0)];
  if (!state || state.tick !== tick) {
    throw new Error(`No authoritative replay projection for tick ${tick}`);
  }
  return state;
};

export const eventsThroughTick = <T extends { physical_tick: number }>(
  events: readonly T[],
  tick: number,
): T[] => events.filter((event) => event.physical_tick <= tick);
