import { describe, expect, it } from "vitest";
import { labComparisonResultSchema, labOracleSchema, labWorksheetSchema } from "../lib/contract";

const worksheet = {
  schema_version: "uc.lab_bench.worksheet.v1", worksheet_id: "manual", revision: 1, title: "Manual derivation",
  state: "candidate_reference", case_id: "M8-LINK-01", case_version: "1", case_configuration_hash: "abc", detached: false,
  author_source: "user_hand_derivation", created_at: "2026-07-15T00:00:00Z", updated_at: "2026-07-15T00:00:00Z",
  notebook: { markdown: "# Derivation\n\n$$t_f=L/v_f$$", origin: "user_authored", linked_references: ["length"] },
  variables: [{ variable_id: "length", label: "Length", value: 200, units: "m", source: "declared input", evidence_classification: "configuration_metadata", configuration_identity: "abc", linked: true }],
  table: { tick_start: 0, tick_end: 1, evaluation_order: "ascending_tick_then_declared_column", out_of_range_values: { cumulative: 0 }, columns: [
    { column_id: "arrivals", label: "Arrivals", units: "packets", kind: "manual", provenance: "user_hand_derivation", values: [3, 0], formula: null, source_reference: "declared demand" },
    { column_id: "cumulative", label: "Cumulative", units: "packets", kind: "formula_derived", provenance: "independently_encoded_arithmetic", values: [3, 3], formula: "cumulative[t - 1] + arrivals[t]", source_reference: "reviewed formula" },
  ] },
  mappings: [], assumptions: ["integer ticks"], limitations: ["single case"],
} as const;

describe("Lab Bench browser contracts", () => {
  it("keeps scratch/candidate state and per-column provenance explicit", () => {
    const parsed = labWorksheetSchema.parse(worksheet);
    expect(parsed.state).toBe("candidate_reference");
    expect(parsed.table.columns.map((item) => item.provenance)).toEqual(["user_hand_derivation", "independently_encoded_arithmetic"]);
    expect(parsed.table.columns[1].formula).toContain("t - 1");
  });

  it("distinguishes informal comparisons from formal frozen evidence", () => {
    const comparison = labComparisonResultSchema.parse({ formal: false, label: "Informal comparison — not formal validation evidence.", exact: true, differences: [0, 0], compared_ticks: [0, 1], maximum_absolute_error: 0, mean_absolute_error: 0, first_mismatch_tick: null, tick_offset: 0, cumulative_bound_violations: 0, mismatched_rows: 0, tolerance: 0 });
    expect(comparison.formal).toBe(false);
    expect(comparison.label).toContain("not formal validation evidence");
  });

  it("parses immutable oracle metadata separately from the candidate worksheet", () => {
    const oracle = labOracleSchema.parse({ schema_version: "uc.lab_bench.oracle.v1", oracle_id: "oracle-m8", version: 1, state: "frozen_oracle", associated_case_id: "M8-LINK-01", associated_case_version: "1", author_source: "user_hand_derivation", created_at: "2026-07-15T00:00:00Z", formula_table_provenance: ["cumulative: cumulative[t - 1] + arrivals[t]"], units: ["packets"], tick_convention: "inclusive integer ticks", input_references: ["length"], detached_literal_values: {}, artifact_hash: "a".repeat(64), approval_action: "Reviewed row by row", notes: [], limitations: [], source_worksheet_revision: 1, dependency_hash: "abc", worksheet });
    expect(oracle.state).toBe("frozen_oracle");
    expect(oracle.worksheet.state).toBe("candidate_reference");
    expect(oracle.artifact_hash).toHaveLength(64);
  });
});
