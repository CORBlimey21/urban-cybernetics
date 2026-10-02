// SPDX-License-Identifier: MPL-2.0
import { useMemo, useState } from "react";
import type { ResourceCatalogue, RunRequest } from "../lib/contract";

type Props = { catalogue: ResourceCatalogue; onClose: () => void; onSubmit: (request: RunRequest) => Promise<void> };

const presets = {
  synthetic: {
    topology_id: "uc_synthetic_diverge_v1", physical_profile_id: "UCSyntheticPhysicalProfile_v1",
    demand_source_id: "uc_synthetic_alternating_demand_v1", tick_policy_id: "synthetic_one_second_v1", packetCount: 24,
  },
  sioux: {
    topology_id: "sioux_falls_tntp_v1", physical_profile_id: "SiouxFallsPhysicalProfile_UC_Default_v1",
    demand_source_id: "sioux_falls_canonical_od_v1", tick_policy_id: "sioux_profile_default_v1", packetCount: 100,
  },
} as const;

export function NewRunDrawer({ catalogue, onClose, onSubmit }: Props) {
  const [preset, setPreset] = useState<keyof typeof presets>("synthetic");
  const [packetCount, setPacketCount] = useState(24);
  const [seed, setSeed] = useState(0);
  const [tickLimit, setTickLimit] = useState(600);
  const [runtimeLimit, setRuntimeLimit] = useState(60);
  const [label, setLabel] = useState("");
  const [advanced, setAdvanced] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const selected = presets[preset];
  const resources = useMemo(() => new Map(catalogue.resources.map((item) => [item.resource_id, item])), [catalogue]);
  const warnings = [selected.topology_id, selected.physical_profile_id, selected.demand_source_id].flatMap((id) => resources.get(id)?.warnings ?? []);
  const submit = async () => {
    setSubmitting(true);
    try {
      await onSubmit({ schema_version: "uc.visualisation.control.v2", ...selected, requested_packet_count: packetCount,
        packet_selection_policy_id: "canonical_prefix_v1", seed, requested_tick_duration_seconds: null,
        runtime_limit_seconds: runtimeLimit, tick_limit: tickLimit, completion_policy_id: "all_instantiated_packets_terminal_v1",
        stop_policy_id: "bounded_tick_or_wall_time_v1", validation_policy_id: "core_integrity_v1",
        replay_policy_id: "exact_if_complete_v1", persistence_policy_id: "retain_all_evidence_v1", run_label: label || null, note: null });
    } finally { setSubmitting(false); }
  };
  return <div className="drawer-backdrop" role="presentation"><aside className="new-run-drawer" role="dialog" aria-label="New sanctioned run">
    <div className="drawer-heading"><div><span className="eyebrow">Control plane · v2</span><h2>New sanctioned run</h2></div><button onClick={onClose}>×</button></div>
    <p className="drawer-intro">Select only backend-declared resources. Python resolves and freezes the scientific configuration before execution.</p>
    <label className="field"><span>Run family</span><select value={preset} onChange={(event) => { const next = event.target.value as keyof typeof presets; setPreset(next); setPacketCount(presets[next].packetCount); }}><option value="synthetic">Deterministic synthetic</option><option value="sioux">Bounded Sioux Falls</option></select></label>
    <div className="resource-summary">
      {(["topology_id", "physical_profile_id", "demand_source_id"] as const).map((key) => <div key={key}><span>{key.replaceAll("_", " ")}</span><strong>{resources.get(selected[key])?.name}</strong><small>{resources.get(selected[key])?.classification}</small></div>)}
    </div>
    {warnings.length > 0 && <div className="assumption-warning"><b>Assumption / source notes</b>{warnings.map((warning) => <span key={warning}>{warning}</span>)}</div>}
    <div className="form-grid"><label className="field"><span>Packet count · unit packets</span><input type="number" min={1} max={1000} value={packetCount} onChange={(event) => setPacketCount(Number(event.target.value))} /></label><label className="field"><span>Seed</span><input type="number" min={0} value={seed} onChange={(event) => setSeed(Number(event.target.value))} /></label></div>
    <label className="field"><span>Optional run label</span><input value={label} maxLength={120} onChange={(event) => setLabel(event.target.value)} placeholder="e.g. bounded inspection run" /></label>
    <button className="advanced-toggle" onClick={() => setAdvanced((value) => !value)}>{advanced ? "▾" : "▸"} Advanced stop policy</button>
    {advanced && <div className="form-grid"><label className="field"><span>Tick limit · ticks</span><input type="number" value={tickLimit} onChange={(event) => setTickLimit(Number(event.target.value))} /></label><label className="field"><span>Wall limit · seconds</span><input type="number" value={runtimeLimit} onChange={(event) => setRuntimeLimit(Number(event.target.value))} /></label></div>}
    <div className="resolved-summary"><span className="eyebrow">Resolved request preview</span><code>{selected.topology_id}</code><code>{selected.physical_profile_id}</code><code>{selected.demand_source_id}</code><small>No scientifically meaningful value is silently coerced.</small></div>
    <div className="drawer-actions"><button onClick={onClose}>Cancel</button><button className="launch-button" disabled={submitting || packetCount < 1 || packetCount > 1000} onClick={() => void submit()}>{submitting ? "Freezing request…" : "Launch Python run"}</button></div>
  </aside></div>;
}
