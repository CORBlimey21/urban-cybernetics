// SPDX-License-Identifier: MPL-2.0
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";
import {
  contractEnums,
  eventSchema,
  manifestSchema,
  replayStateSchema,
  runStatusSchema,
} from "../lib/contract";

const fixture = JSON.parse(
  readFileSync(
    resolve(process.cwd(), "../fixtures/visualisation/v1/synthetic_strict_fifo_diverge_v1.json"),
    "utf8",
  ),
);

describe("V1 contract", () => {
  it("validates the persisted manifest, events, and replay states", () => {
    const manifest = manifestSchema.parse(fixture);
    expect(manifest.run.topology_hash).toBe(manifest.topology.topology_hash);
    expect(fixture.event_stream.events.map((event: unknown) => eventSchema.parse(event))).toHaveLength(26);
    expect(fixture.replay_states.map((state: unknown) => replayStateSchema.parse(state))).toHaveLength(8);
  });

  it("uses the shared enum artifact", () => {
    expect(runStatusSchema.parse("partial")).toBe("partial");
    expect(contractEnums.packet_replay_status).toContain("cancelled");
  });
});
