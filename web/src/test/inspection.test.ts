// SPDX-License-Identifier: MPL-2.0
import { readFileSync, readdirSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";
import { eventSchema, manifestSchema, movementEvidenceSchema, replayStateSchema } from "../lib/contract";
import { inspectLink, inspectNode, inspectPacket, packetVisualEvidence } from "../lib/inspection";
import { availableLayouts } from "../lib/layout";
import { stateAtTick } from "../lib/replay";

const root = resolve(process.cwd(), "../fixtures/visualisation/v2/v2-sioux-falls-bounded-100-v1");
const fixture = JSON.parse(readFileSync(resolve(root, "final_bundle.json"), "utf8"));
const manifest = manifestSchema.parse(fixture);
const events = fixture.event_stream.events.map((event: unknown) => eventSchema.parse(event));
const states = fixture.replay_states.map((state: unknown) => replayStateSchema.parse(state));
const movementFiles = readdirSync(resolve(root, "movements"));
const movementEvidence = movementFiles.map((file) => movementEvidenceSchema.parse(JSON.parse(readFileSync(resolve(root, "movements", file), "utf8"))));

describe("scientific evidence inspection", () => {
  it("returns declared node connectivity and only matching exported allocation traces", () => {
    const trace = movementEvidence[0];
    const inspection = inspectNode(manifest, movementEvidence.filter((item) => item.tick === trace.tick), trace.junction_id);
    expect(inspection?.node.node_id).toBe(trace.junction_id);
    expect(inspection?.movements.every((movement) => movement.node_id === trace.junction_id)).toBe(true);
    expect(inspection?.traces.every((item) => item.junction_id === trace.junction_id)).toBe(true);
  });

  it("returns exact link membership and canonical link events at the replay tick", () => {
    const state = stateAtTick(states, 5);
    const linkId = manifest.topology.links[0].link_id;
    const inspection = inspectLink(manifest, state, events, linkId);
    expect(inspection?.replay).toEqual(state.links.find((link) => link.link_id === linkId));
    expect(inspection?.lifecycle.every((event) => event.entity_id === linkId && event.physical_tick <= 5)).toBe(true);
  });

  it("updates followed packet visual evidence without mutating scientific replay", () => {
    const packetId = manifest.packets[0].packet_id;
    const early = stateAtTick(states, 0);
    const late = stateAtTick(states, manifest.run.end_tick);
    const before = JSON.stringify(late);
    const earlyVisual = packetVisualEvidence(manifest, early, packetId);
    const lateVisual = packetVisualEvidence(manifest, late, packetId);
    expect(earlyVisual.declaredRoute).toEqual(lateVisual.declaredRoute);
    expect(lateVisual.realisedPath.size).toBeGreaterThanOrEqual(earlyVisual.realisedPath.size);
    expect(JSON.stringify(late)).toBe(before);
  });

  it("preserves packet and replay evidence across every presentation layout", () => {
    const state = stateAtTick(states, 5);
    const packetId = manifest.packets[0].packet_id;
    const expected = inspectPacket(manifest, state, events, packetId);
    for (const layout of availableLayouts(manifest)) {
      expect(layout.node_coordinates[manifest.topology.nodes[0].node_id]).toBeDefined();
      expect(inspectPacket(manifest, state, events, packetId)).toEqual(expected);
    }
  });
});
