import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";
import { validationCaseSchema, validationResultSchema } from "../lib/contract";

const root = resolve(process.cwd(), "../fixtures/visualisation/validation");
const validationCase = validationCaseSchema.parse(JSON.parse(readFileSync(resolve(root, "cases/m8-link-03.json"), "utf8")));
const result = validationResultSchema.parse(JSON.parse(readFileSync(resolve(root, "runs/m8-link-03-baseline-v1/result.json"), "utf8")));

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
});
