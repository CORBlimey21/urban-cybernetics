import { z } from "zod";
import contractEnums from "../contract-enums.json";
import v2ContractEnums from "../v2-contract-enums.json";

const literalUnion = <T extends readonly [string, ...string[]]>(values: T) =>
  z.enum(values);

export const semanticStatusSchema = literalUnion(
  contractEnums.semantic_status as [string, ...string[]],
);
export const runStatusSchema = literalUnion(
  contractEnums.run_status as [string, ...string[]],
);
export const packetReplayStatusSchema = literalUnion(
  contractEnums.packet_replay_status as [string, ...string[]],
);
export const fieldAvailabilitySchema = literalUnion(
  contractEnums.field_availability as [string, ...string[]],
);

export const descriptorSchema = z.object({
  semantic_status: semanticStatusSchema,
  source: z.string(),
  units: z.string().nullable(),
  time_basis: z.string().nullable(),
  counting_basis: z.string().nullable(),
  boundary_direction: z.string().nullable(),
  aggregation_window_ticks: z.number().int().nullable(),
});

export const runSchema = z.object({
  run_id: z.string(),
  scenario_name: z.string(),
  status: runStatusSchema,
  status_reason: z.string(),
  topology_id: z.string(),
  topology_hash: z.string(),
  configuration_id: z.string(),
  configuration_hash: z.string(),
  model_profile_id: z.string(),
  tick_duration_seconds: z.number().positive(),
  simulation_time_basis: z.literal("integer_physical_tick"),
  start_tick: z.number().int().nonnegative(),
  end_tick: z.number().int().nonnegative(),
  event_count: z.number().int().nonnegative(),
  packet_count: z.number().int().nonnegative(),
  created_at: z.string().nullable(),
});

export const runListSchema = z.array(
  runSchema.extend({
    validation_status: z.enum(["not_run", "passed", "failed"]),
  }),
);

export const linkSchema = z.object({
  link_id: z.string(),
  tail_node_id: z.string(),
  head_node_id: z.string(),
  source_link_id: z.string(),
  length_m: z.number().nullable(),
  lane_count: z.number().int().nullable(),
  free_flow_speed_mps: z.number().nullable(),
  capacity_veh_per_hour_per_lane: z.number().nullable(),
  jam_density_veh_per_km_per_lane: z.number().nullable(),
  backward_wave_speed_mps: z.number().nullable(),
  field_availability: z.record(z.string(), fieldAvailabilitySchema),
});

export const nodeSchema = z.object({
  node_id: z.string(),
  source_node_id: z.string(),
  incoming_link_ids: z.array(z.string()),
  outgoing_link_ids: z.array(z.string()),
  movement_ids: z.array(z.string()),
  fifo_policy: z.string(),
});

export const movementSchema = z.object({
  movement_id: z.string(),
  node_id: z.string(),
  upstream_link_id: z.string(),
  downstream_link_id: z.string(),
  priority_weight: z.number().int(),
  lane_group_ids: z.array(z.string()),
  conflict_resource_ids: z.array(z.string()),
  signal_group_id: z.string().nullable(),
});

export const packetSchema = z.object({
  packet_id: z.string(),
  demand_id: z.string(),
  origin_node_id: z.string().nullable(),
  destination_node_id: z.string().nullable(),
  route_id: z.string().nullable(),
  route_intent: z.array(z.string()),
  cohort_id: z.string().nullable(),
  authority_id: z.string().nullable(),
  packet_unit_weight: z.number().int(),
  field_availability: z.record(z.string(), fieldAvailabilitySchema),
});

export const eventSchema = z.object({
  sequence_number: z.number().int().nonnegative(),
  packet_id: z.string(),
  event_type: z.enum([
    "instantiated",
    "link_entry",
    "link_exit",
    "queue_entry",
    "queue_exit",
    "completed",
    "cancelled",
  ]),
  entity_id: z.string(),
  physical_tick: z.number().int().nonnegative(),
});

export const replayPacketSchema = z.object({
  packet_id: z.string(),
  status: packetReplayStatusSchema,
  current_link_id: z.string().nullable(),
  queue_boundary_id: z.string().nullable(),
  realised_path: z.array(z.string()),
  last_event_sequence: z.number().int().nullable(),
});

export const replayLinkSchema = z.object({
  link_id: z.string(),
  packet_ids: z.array(z.string()),
  queued_packet_ids: z.array(z.string()),
  occupancy_packets: z.number().int().nonnegative(),
  cumulative_entries: z.number().int().nonnegative(),
  cumulative_exits: z.number().int().nonnegative(),
});

export const replayStateSchema = z.object({
  descriptor: descriptorSchema,
  tick: z.number().int().nonnegative(),
  applied_through_sequence: z.number().int().nullable(),
  packets: z.array(replayPacketSchema),
  links: z.array(replayLinkSchema),
  queues: z.array(z.object({ boundary_id: z.string(), packet_ids: z.array(z.string()) })),
  counts: z.object({
    not_yet_observed: z.number().int().nonnegative(),
    in_transit: z.number().int().nonnegative(),
    queued: z.number().int().nonnegative(),
    completed: z.number().int().nonnegative(),
    cancelled: z.number().int().nonnegative(),
  }),
});

export const manifestSchema = z.object({
  schema_version: z.literal("uc.visualisation.run.v1"),
  run: runSchema,
  provenance: z.object({
    descriptor: descriptorSchema,
    code_version: z.string().nullable(),
    input_artifact_ids: z.array(z.string()),
    source_name: z.string(),
    source_format: z.string(),
    source_file_sha256: z.string(),
    interpretation_assumptions: z.array(z.string()),
    config_snapshot: z.record(z.string(), z.unknown()),
  }),
  topology: z.object({
    descriptor: descriptorSchema,
    topology_id: z.string(),
    topology_hash: z.string(),
    nodes: z.array(nodeSchema),
    links: z.array(linkSchema),
    movements: z.array(movementSchema),
  }),
  packets_descriptor: descriptorSchema,
  packets: z.array(packetSchema),
  validation: z.object({
    descriptor: descriptorSchema,
    overall_status: z.enum(["not_run", "passed", "failed"]),
    checks: z.record(z.string(), z.enum(["not_run", "passed", "failed"])),
    notes: z.array(z.string()),
  }),
  presentation: z.object({
    descriptor: descriptorSchema,
    layout_kind: z.enum(["synthetic_declared", "synthetic_deterministic"]),
    layout_note: z.string(),
    node_positions: z.record(z.string(), z.tuple([z.number(), z.number()])),
    interpolation_note: z.string(),
  }),
});

export const eventsResponseSchema = z.object({
  descriptor: descriptorSchema,
  events: z.array(eventSchema),
  start_sequence: z.number().int(),
  next_sequence: z.number().int().nullable(),
  total_event_count: z.number().int(),
});

export const replayResponseSchema = z.object({
  states: z.array(replayStateSchema),
  start_tick: z.number().int(),
  end_tick: z.number().int(),
  run_end_tick: z.number().int(),
});

export const cumulativeSeriesSchema = z.object({
  descriptor: descriptorSchema,
  link_id: z.string(),
  ticks: z.array(z.number().int()),
  cumulative_entries: z.array(z.number().int()),
  cumulative_exits: z.array(z.number().int()),
  storage_packets: z.array(z.number().int()),
});

export const finalBundleSchema = manifestSchema.extend({
  event_stream: z.object({ descriptor: descriptorSchema, events: z.array(eventSchema) }),
  replay_states: z.array(replayStateSchema),
  cumulative_link_series: z.array(cumulativeSeriesSchema),
});

export const lifecycleStateSchema = literalUnion(v2ContractEnums.run_lifecycle_state as [string, ...string[]]);

export const artifactSchema = z.object({
  artifact_format: literalUnion(v2ContractEnums.artifact_format as [string, ...string[]]),
  run_id: z.string(),
  title: z.string(),
  description: z.string(),
  contract_version: z.string(),
  topology_id: z.string(),
  topology_hash: z.string(),
  physical_profile_id: z.string(),
  profile_hash: z.string(),
  demand_source_id: z.string(),
  demand_hash: z.string(),
  seed: z.number().int(),
  status: z.string(),
  stop_reason: z.string().nullable(),
  created_at: z.string().nullable(),
  updated_at: z.string().nullable(),
  validation_status: z.string(),
  configuration_hash: z.string(),
  event_count: z.number().int().nonnegative(),
  final_tick: z.number().int().nonnegative(),
  counts: z.record(z.string(), z.number().int().nonnegative()),
  assumption_warnings: z.array(z.string()),
});
export const artifactListSchema = z.array(artifactSchema);

export const catalogueResourceSchema = z.object({
  resource_id: z.string(), kind: z.string(), name: z.string(), description: z.string(),
  provenance: z.string(), classification: z.string(), warnings: z.array(z.string()),
  compatible_topology_ids: z.array(z.string()), compatible_profile_ids: z.array(z.string()),
  parameters: z.array(z.object({
    parameter_id: z.string(), name: z.string(), description: z.string(), units: z.string().nullable(),
    default: z.union([z.string(), z.number(), z.boolean()]).nullable(), minimum: z.number().nullable(), maximum: z.number().nullable(),
  })),
});
export const resourceCatalogueSchema = z.object({
  schema_version: z.literal("uc.visualisation.control.v2"), resources: z.array(catalogueResourceSchema),
});

export const runRequestSchema = z.object({
  schema_version: z.literal("uc.visualisation.control.v2").default("uc.visualisation.control.v2"),
  topology_id: z.string(), physical_profile_id: z.string(), demand_source_id: z.string(),
  requested_packet_count: z.number().int().min(1).max(1000),
  packet_selection_policy_id: z.string().default("canonical_prefix_v1"), seed: z.number().int().nonnegative(),
  tick_policy_id: z.string(), requested_tick_duration_seconds: z.number().positive().nullable(),
  runtime_limit_seconds: z.number().positive(), tick_limit: z.number().int().positive(),
  completion_policy_id: z.string().default("all_instantiated_packets_terminal_v1"),
  stop_policy_id: z.string().default("bounded_tick_or_wall_time_v1"),
  validation_policy_id: z.string().default("core_integrity_v1"), replay_policy_id: z.string().default("exact_if_complete_v1"),
  persistence_policy_id: z.string().default("retain_all_evidence_v1"), run_label: z.string().nullable(), note: z.string().nullable(),
});

export const liveMessageSchema = z.object({
  schema_version: z.literal("uc.visualisation.control.v2"), message_id: z.number().int(), run_id: z.string(),
  message_type: z.string(), occurred_at: z.string(), lifecycle_state: lifecycleStateSchema,
  payload: z.record(z.string(), z.unknown()),
});

export const movementEvidenceSchema = z.object({
  schema_version: z.literal("uc.visualisation.movement-trace.v1"), run_id: z.string(), tick: z.number().int(),
  junction_id: z.string(), allocator_id: z.string(), movement_spec_hash: z.string().nullable(),
  semantic_sources: z.record(z.string(), z.string()),
  movements: z.array(z.object({
    movement_id: z.string(), upstream_link_id: z.string(), downstream_link_id: z.string(),
    request_packet_ids: z.array(z.string()), upstream_fifo_packet_ids: z.array(z.string()), approved_packet_ids: z.array(z.string()),
    rejected_packet_reasons: z.array(z.tuple([z.string(), z.string()])), receiving_supply_packets: z.number().int().nullable(),
    movement_capacity_packets: z.number().int().nullable(), lane_group_constraints: z.record(z.string(), z.number().int()),
    conflict_resource_constraints: z.record(z.string(), z.number().int()), signal_state: z.enum(["open", "closed", "not_declared"]),
    governance_state: z.string().nullable(), resulting_canonical_event_sequences: z.array(z.number().int()),
  })),
});

export type Manifest = z.infer<typeof manifestSchema>;
export type CanonicalEvent = z.infer<typeof eventSchema>;
export type ReplayState = z.infer<typeof replayStateSchema>;
export type LinkRecord = z.infer<typeof linkSchema>;
export type PacketRecord = z.infer<typeof packetSchema>;
export type CumulativeSeries = z.infer<typeof cumulativeSeriesSchema>;
export type ArtifactSummary = z.infer<typeof artifactSchema>;
export type ResourceCatalogue = z.infer<typeof resourceCatalogueSchema>;
export type RunRequest = z.infer<typeof runRequestSchema>;
export type LiveMessage = z.infer<typeof liveMessageSchema>;
export type MovementEvidence = z.infer<typeof movementEvidenceSchema>;

export { contractEnums, v2ContractEnums };
