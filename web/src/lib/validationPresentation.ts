import type { MovementEvidence, ReplayState, ValidationCase, ValidationResult } from "./contract";

export type ValidationLinkVisual = Readonly<{
  linkId: string;
  queuePackets: number;
  queueFraction: number;
  queueSource: string;
  queueLabel: string;
  blockedAtHead: boolean;
  vacancyWavePosition: number | null;
  vacancyWaveSource: string | null;
}>;

export type ValidationReplayPresentation = Readonly<{
  links: ReadonlyMap<string, ValidationLinkVisual>;
  currentPhase: string;
  phaseExplanation: string;
  expectedNextTransition: string;
  approvedLinks: ReadonlySet<string>;
  rejectedLinks: ReadonlySet<string>;
}>;

export const valueAtTick = (
  series: Readonly<{ ticks: number[]; values: number[] }> | undefined,
  tick: number,
): number | null => {
  if (!series) return null;
  const index = series.ticks.indexOf(tick);
  return index < 0 ? null : series.values[index] ?? null;
};

const observedPointQueue = (result: ValidationResult | null, tick: number) => {
  const series = result?.observed_series.find((item) => item.quantity === "point_queue");
  if (!series) return null;
  const value = valueAtTick(series, tick);
  return value === null ? null : { value, maximum: Math.max(1, ...series.values), source: series.evidence_source };
};

export const validationReplayPresentation = (
  validationCase: ValidationCase,
  result: ValidationResult | null,
  state: ReplayState,
  movementEvidence: MovementEvidence[] = [],
): ValidationReplayPresentation => {
  const active = validationCase.overlays.filter(
    (overlay) => overlay.active_from_tick <= state.tick && state.tick <= overlay.active_through_tick,
  );
  const upcoming = validationCase.overlays
    .filter((overlay) => overlay.active_from_tick > state.tick)
    .sort((left, right) => left.active_from_tick - right.active_from_tick)[0];
  const activeQueue = active.find((overlay) => overlay.kind === "queued_region");
  const pointQueue = observedPointQueue(result, state.tick);
  const links = new Map<string, ValidationLinkVisual>();

  for (const linkState of state.links) {
    const blocked = active.find((overlay) => overlay.kind === "blocked_boundary" && overlay.link_id === linkState.link_id);
    const queueOverlay = activeQueue?.link_id === linkState.link_id ? activeQueue : null;
    const canonicalQueue = linkState.queued_packet_ids.length;
    const queuePackets = canonicalQueue || (queueOverlay ? pointQueue?.value ?? 0 : 0);
    const denominator = canonicalQueue
      ? Math.max(linkState.occupancy_packets, canonicalQueue, 1)
      : Math.max(pointQueue?.maximum ?? 1, 1);
    const wave = active.find((overlay) => overlay.kind === "reference_wave" && overlay.link_id === linkState.link_id);
    const duration = wave ? Math.max(1, wave.active_through_tick - wave.active_from_tick) : 1;
    const waveProgress = wave ? Math.max(0, Math.min(1, (state.tick - wave.active_from_tick) / duration)) : null;
    if (queuePackets || blocked || queueOverlay || wave) {
      links.set(linkState.link_id, {
        linkId: linkState.link_id,
        queuePackets,
        queueFraction: Math.max(0, Math.min(1, queuePackets / denominator)),
        queueSource: canonicalQueue ? "canonical queue membership" : pointQueue?.source.replaceAll("_", " ") ?? queueOverlay?.evidence_source.replaceAll("_", " ") ?? "unavailable",
        queueLabel: queueOverlay?.label ?? blocked?.label ?? "Queued region",
        blockedAtHead: Boolean(blocked),
        vacancyWavePosition: waveProgress === null ? null : 0.86 - waveProgress * 0.72,
        vacancyWaveSource: wave?.evidence_source.replaceAll("_", " ") ?? null,
      });
    }
  }

  const traces = movementEvidence.filter((trace) => trace.tick === state.tick);
  const approvedLinks = new Set<string>();
  const rejectedLinks = new Set<string>();
  for (const movement of traces.flatMap((trace) => trace.movements)) {
    if (movement.approved_packet_ids.length) approvedLinks.add(movement.downstream_link_id);
    if (movement.rejected_packet_reasons.length) rejectedLinks.add(movement.upstream_link_id);
  }

  return {
    links,
    currentPhase: active.map((overlay) => overlay.label).join(" · ") || "No authored validation interval active",
    phaseExplanation: active.map((overlay) => overlay.note).join(" ") || "Exact replay remains available; no explanatory overlay is declared for this tick.",
    expectedNextTransition: upcoming ? `tick ${upcoming.active_from_tick}: ${upcoming.label}` : "No later authored transition in this case.",
    approvedLinks,
    rejectedLinks,
  };
};
