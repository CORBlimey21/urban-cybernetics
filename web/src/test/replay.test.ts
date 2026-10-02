// SPDX-License-Identifier: MPL-2.0
import { describe, expect, it } from "vitest";
import type { CanonicalEvent, ReplayState } from "../lib/contract";
import { eventsThroughTick, stateAtTick } from "../lib/replay";
import { presentationMarkers } from "../lib/presentation";
import { eventSchema, manifestSchema, replayStateSchema } from "../lib/contract";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { defaultLayout } from "../lib/layout";

const fixture = JSON.parse(
  readFileSync(resolve(process.cwd(), "../fixtures/visualisation/v1/synthetic_strict_fifo_diverge_v1.json"), "utf8"),
);
const manifest = manifestSchema.parse(fixture);
const states = fixture.replay_states.map((state: unknown) => replayStateSchema.parse(state));
const events = fixture.event_stream.events.map((event: unknown) => eventSchema.parse(event));

describe("viewer replay", () => {
  it("seeks by selecting an exact Python projection", () => {
    expect(stateAtTick(states, 1).counts.queued).toBe(1);
    expect(stateAtTick(states, 7).counts.completed).toBe(3);
    expect(() => stateAtTick(states, 99)).toThrow(/authoritative replay projection/);
  });

  it("filters without reordering same-tick canonical events", () => {
    const visible = eventsThroughTick<CanonicalEvent>(events, 3);
    expect(visible.map((event) => event.sequence_number)).toEqual(
      [...visible].map((event) => event.sequence_number).sort((a, b) => a - b),
    );
  });

  it("keeps presentation interpolation outside scientific state", () => {
    const scientificState = stateAtTick(states, 1);
    const before = JSON.stringify(scientificState);
    const markers = presentationMarkers(manifest.topology.links[0], defaultLayout(manifest), scientificState, 0.42);

    expect(markers.length).toBeGreaterThan(0);
    expect(markers[0]).not.toHaveProperty("packet_id");
    expect(markers[0]).not.toHaveProperty("current_link_id");
    expect(JSON.stringify(scientificState)).toBe(before);
  });

  it("does not permit an unavailable tick to masquerade as state", () => {
    expect(() => stateAtTick([] as ReplayState[], 0)).toThrow();
  });
});
