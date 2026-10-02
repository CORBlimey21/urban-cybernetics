// SPDX-License-Identifier: MPL-2.0
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";
import { manifestSchema, networkLayoutSchema } from "../lib/contract";
import { availableLayouts, defaultLayout } from "../lib/layout";
import { directedEdgePath } from "../lib/networkGeometry";
import { stateAtTick } from "../lib/replay";

const fixture = JSON.parse(readFileSync(
  resolve(process.cwd(), "../fixtures/visualisation/v2/v2-sioux-falls-bounded-100-v1/final_bundle.json"),
  "utf8",
));
const manifest = manifestSchema.parse(fixture);

describe("network layouts", () => {
  it("selects the declared Sioux Falls schematic and keeps fallback choices", () => {
    expect(defaultLayout(manifest).layout_id).toBe("sioux_falls_published_schematic_v1");
    expect(availableLayouts(manifest).map((layout) => layout.kind)).toContain("circular_fallback");
  });

  it("separates opposing directed edge paths", () => {
    const forward = directedEdgePath({ x: 10, y: 30 }, { x: 110, y: 30 }, true);
    const reverse = directedEdgePath({ x: 110, y: 30 }, { x: 10, y: 30 }, true);
    expect(forward.start.y).not.toBe(reverse.end.y);
    expect(forward.opposingOffset).toBeGreaterThan(0);
  });

  it("layout choice cannot alter exact replay state", () => {
    const tick = 5;
    const before = stateAtTick(fixture.replay_states, tick);
    for (const layout of availableLayouts(manifest)) {
      expect(Object.keys(layout.node_coordinates).sort()).toEqual(
        manifest.topology.nodes.map((node) => node.node_id).sort(),
      );
      expect(stateAtTick(fixture.replay_states, tick)).toEqual(before);
    }
  });

  it("rejects ambiguous geographic metadata in the browser contract", () => {
    const schematic = defaultLayout(manifest);
    expect(networkLayoutSchema.safeParse({
      ...schematic,
      kind: "geographic",
      is_geographic: true,
      crs: null,
    }).success).toBe(false);
  });
});
