// SPDX-License-Identifier: MPL-2.0
import { describe, expect, it } from "vitest";
import {
  artifactSchema, lifecycleStateSchema, resourceCatalogueSchema, runRequestSchema,
  v2ContractEnums,
} from "../lib/contract";

describe("V2 control and evidence boundary", () => {
  it("validates every shared lifecycle enum", () => {
    expect(v2ContractEnums.run_lifecycle_state.map((state) => lifecycleStateSchema.parse(state))).toEqual(v2ContractEnums.run_lifecycle_state);
  });

  it("rejects arbitrary control-plane fields", () => {
    expect(() => runRequestSchema.strict().parse({
      topology_id: "uc_synthetic_diverge_v1", physical_profile_id: "UCSyntheticPhysicalProfile_v1",
      demand_source_id: "uc_synthetic_alternating_demand_v1", requested_packet_count: 2,
      seed: 0, tick_policy_id: "synthetic_one_second_v1", requested_tick_duration_seconds: null,
      runtime_limit_seconds: 10, tick_limit: 10, run_label: null, note: null, shell_command: "rm -rf /",
    })).toThrow();
  });

  it("keeps catalogue and artifact status explicitly typed", () => {
    expect(resourceCatalogueSchema.safeParse({ schema_version: "uc.visualisation.control.v2", resources: [] }).success).toBe(true);
    expect(artifactSchema.shape.artifact_format.parse("v2_chunked")).toBe("v2_chunked");
  });
});
