// SPDX-License-Identifier: MPL-2.0
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";
import { finalBundleSchema, movementEvidenceSchema, validationCaseSchema, validationResultSchema } from "../lib/contract";
import { stateAtTick } from "../lib/replay";
import { validationReplayPresentation } from "../lib/validationPresentation";

const root = resolve(process.cwd(), "../fixtures/visualisation/validation");
const validationCase = validationCaseSchema.parse(JSON.parse(readFileSync(resolve(root, "cases/m8-link-03.json"), "utf8")));
const result = validationResultSchema.parse(JSON.parse(readFileSync(resolve(root, "runs/m8-link-03-baseline-v1/result.json"), "utf8")));
const vacancyBundle = finalBundleSchema.parse(JSON.parse(readFileSync(resolve(root, "runs/m8-link-03-baseline-v1/replay_bundle.json"), "utf8")));
const queueCase = validationCaseSchema.parse(JSON.parse(readFileSync(resolve(root, "cases/m8-link-02.json"), "utf8")));
const queueResult = validationResultSchema.parse(JSON.parse(readFileSync(resolve(root, "runs/m8-link-02-baseline-v1/result.json"), "utf8")));
const queueBundle = finalBundleSchema.parse(JSON.parse(readFileSync(resolve(root, "runs/m8-link-02-baseline-v1/replay_bundle.json"), "utf8")));
const siouxRoot = resolve(process.cwd(), "../fixtures/visualisation/v2/v2-sioux-falls-bounded-100-v1");
const siouxBundle = finalBundleSchema.parse(JSON.parse(readFileSync(resolve(siouxRoot, "final_bundle.json"), "utf8")));
const movementTrace = movementEvidenceSchema.parse(JSON.parse(readFileSync(resolve(siouxRoot, "movements/00000005-dc9ae5067ef2.json"), "utf8")));

describe("M8 validation browser contract", () => {
  it("keeps analytical expectations separate from observed Python projections", () => {
    expect(validationCase.schema_version).toBe("uc.validation.case.v1");
    expect(result.schema_version).toBe("uc.validation.result.v1");
    expect(validationCase.expected_series.every((series) => series.evidence_source === "analytical_reference")).toBe(true);
    expect(result.observed_series.every((series) => series.evidence_source !== "analytical_reference")).toBe(true);
  });

  it("provides exact chart-aligned expected, observed, and difference series", () => {
    for (const expected of validationCase.expected_series) {
      const observed = result.observed_series.find((series) => series.series_id === expected.series_id)!;
      const difference = result.difference_series.find((series) => series.series_id === expected.series_id)!;
      expect(observed.ticks).toEqual(expected.ticks);
      expect(difference.values).toEqual(observed.values.map((value, index) => value - expected.values[index]));
    }
  });

  it("labels replay overlays and waiting explanations by evidence source", () => {
    expect(validationCase.overlays.map((overlay) => overlay.evidence_source)).toContain("analytical_reference");
    expect(result.packet_wait_explanations[0].evidence_sources).toEqual(["canonical", "validation_output", "analytical_reference"]);
    expect(result.packet_wait_explanations[0].unavailable_fields).toContain("allocator rejection trace");
  });

  it("builds progressive queue regions from exported validation projections without changing replay", () => {
    const state = stateAtTick(queueBundle.replay_states, 2);
    const before = JSON.stringify(state);
    const presentation = validationReplayPresentation(queueCase, queueResult, state);
    const queue = presentation.links.get("L1");
    expect(queue?.queuePackets).toBe(4);
    expect(queue?.queueFraction).toBe(1);
    expect(queue?.queueSource).toBe("validation output");
    expect(JSON.stringify(state)).toBe(before);
  });

  it("moves the analytical vacancy cue backward while leaving exact state untouched", () => {
    const positions = [1, 2, 3].map((tick) => {
      const state = stateAtTick(vacancyBundle.replay_states, tick);
      const before = JSON.stringify(state);
      const presentation = validationReplayPresentation(validationCase, result, state);
      expect(JSON.stringify(state)).toBe(before);
      expect(presentation.links.get("L2")?.vacancyWaveSource).toBe("analytical reference");
      return presentation.links.get("L2")?.vacancyWavePosition ?? 0;
    });
    expect(positions[0]).toBeGreaterThan(positions[1]);
    expect(positions[1]).toBeGreaterThan(positions[2]);
  });

  it("uses exported movement decisions for transient approval and rejection highlights", () => {
    const state = stateAtTick(siouxBundle.replay_states, movementTrace.tick);
    const presentation = validationReplayPresentation(validationCase, null, state, [movementTrace]);
    const expectedApproved = movementTrace.movements.filter((item) => item.approved_packet_ids.length).map((item) => item.downstream_link_id);
    const expectedRejected = movementTrace.movements.filter((item) => item.rejected_packet_reasons.length).map((item) => item.upstream_link_id);
    expect(expectedApproved.length).toBeGreaterThan(0);
    expect(expectedRejected.length).toBeGreaterThan(0);
    expect([...presentation.approvedLinks]).toEqual(expect.arrayContaining(expectedApproved));
    expect([...presentation.rejectedLinks]).toEqual(expect.arrayContaining(expectedRejected));
  });
});
