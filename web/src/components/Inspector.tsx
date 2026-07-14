import { useMemo, useState } from "react";
import type { CanonicalEvent, CumulativeSeries, Manifest, MovementEvidence, ReplayState } from "../lib/contract";
import { inspectLink, inspectNode, inspectPacket } from "../lib/inspection";

const display = (value: string | number | null, status?: string) => {
  if (value !== null) return String(value);
  return status ? `— ${status.replaceAll("_", " ")}` : "— unavailable";
};

const Row = ({ label, value }: { label: string; value: React.ReactNode }) => (
  <div className="inspect-row"><span>{label}</span><strong>{value}</strong></div>
);

type Props = {
  manifest: Manifest;
  state: ReplayState;
  events: CanonicalEvent[];
  movementEvidence: MovementEvidence[];
  selectedLinkId: string;
  selectedNodeId: string | null;
  selectedPacketId: string | null;
  followingPacket: boolean;
  series: CumulativeSeries;
  onSelectPacket: (packetId: string | null) => void;
  onSelectLink: (linkId: string) => void;
  onSelectNode: (nodeId: string) => void;
  onToggleFollow: () => void;
  onNavigateEvent: (event: CanonicalEvent) => void;
};

const EvidenceLink = ({ id, onSelect }: { id: string; onSelect: (id: string) => void }) => <button className="evidence-link" onClick={() => onSelect(id)}>{id}</button>;

export function Inspector(props: Props) {
  const { manifest, state, events, movementEvidence, selectedLinkId, selectedNodeId, selectedPacketId, followingPacket, series, onSelectPacket, onSelectLink, onSelectNode, onToggleFollow, onNavigateEvent } = props;
  const [packetQuery, setPacketQuery] = useState("");
  const packetMatches = useMemo(() => {
    const query = packetQuery.trim().toLowerCase();
    if (!query) return [];
    return manifest.packets.filter((packet) => packet.packet_id.toLowerCase().includes(query) || packet.demand_id.toLowerCase().includes(query)).slice(0, 8);
  }, [manifest, packetQuery]);

  const finder = <div className="packet-finder"><label htmlFor="packet-search">Find packet</label><input id="packet-search" value={packetQuery} onChange={(event) => setPacketQuery(event.target.value)} placeholder="Packet or demand ID" />{packetMatches.length > 0 && <div className="packet-search-results">{packetMatches.map((packet) => <button key={packet.packet_id} onClick={() => { onSelectPacket(packet.packet_id); setPacketQuery(""); }}>{packet.packet_id}<small>{packet.demand_id}</small></button>)}</div>}</div>;

  if (selectedPacketId) {
    const inspection = inspectPacket(manifest, state, events, selectedPacketId);
    if (inspection) {
      const { packet, replay, lifecycle } = inspection;
      return <aside className="inspector panel">
        <div className="panel-heading"><div><span className="eyebrow">Packet inspection</span><h2>{packet.packet_id}</h2></div><button className="icon-button" onClick={() => onSelectPacket(null)} aria-label="Close packet inspection">×</button></div>
        <div className="inspection-actions"><span className={`status-pill packet-${replay.status}`}>{replay.status.replaceAll("_", " ")}</span><button className={followingPacket ? "follow-button following" : "follow-button"} aria-pressed={followingPacket} onClick={onToggleFollow}>{followingPacket ? "Stop following" : "Follow packet"}</button></div>
        <div className="inspect-section">
          <Row label="Demand declaration" value={packet.demand_id} />
          <Row label="OD pair" value={`${display(packet.origin_node_id, packet.field_availability.origin_node_id)} → ${display(packet.destination_node_id, packet.field_availability.destination_node_id)}`} />
          <Row label="Origin" value={packet.origin_node_id ? <EvidenceLink id={packet.origin_node_id} onSelect={onSelectNode} /> : display(null, packet.field_availability.origin_node_id)} />
          <Row label="Destination" value={packet.destination_node_id ? <EvidenceLink id={packet.destination_node_id} onSelect={onSelectNode} /> : display(null, packet.field_availability.destination_node_id)} />
          <Row label="Route artifact" value={display(packet.route_id, packet.field_availability.route_id)} />
          <Row label="Authority" value={display(packet.authority_id, packet.field_availability.authority_id)} />
          <Row label="Cohort" value={display(packet.cohort_id, packet.field_availability.cohort_id)} />
          <Row label="Current link" value={replay.current_link_id ? <EvidenceLink id={replay.current_link_id} onSelect={onSelectLink} /> : display(null, replay.status === "not_yet_observed" ? "not yet instantiated" : "not applicable")} />
          <Row label="Queue boundary" value={display(replay.queue_boundary_id, replay.status === "queued" ? "unknown" : "not applicable")} />
        </div>
        <div className="inspect-section"><span className="section-label">Declared route intent · packet metadata</span><div className="route-chain">{packet.route_intent.length ? packet.route_intent.map((link) => <EvidenceLink key={link} id={link} onSelect={onSelectLink} />) : <em>unavailable</em>}</div></div>
        <div className="inspect-section"><span className="section-label">Realised path · event-derived</span><div className="route-chain realised">{replay.realised_path.length ? replay.realised_path.map((link, index) => <EvidenceLink key={`${link}-${index}`} id={link} onSelect={onSelectLink} />) : <em>not yet observed</em>}</div></div>
        <div className="inspect-section"><span className="section-label">Complete canonical lifecycle</span><div className="mini-events">{lifecycle.map((event) => <button key={event.sequence_number} onClick={() => onNavigateEvent(event)}><code>#{event.sequence_number}</code><span>{event.event_type}</span><b>t{event.physical_tick}</b></button>)}</div></div>
        {finder}<div className="source-foot">Metadata · {manifest.packets_descriptor.semantic_status.replaceAll("_", " ")}<br />Status and realised path · event-derived scientific projection<br />Follow highlight · presentation only</div>
      </aside>;
    }
  }

  if (selectedNodeId) {
    const inspection = inspectNode(manifest, movementEvidence, selectedNodeId);
    if (inspection) return <aside className="inspector panel">
      <div className="panel-heading"><div><span className="eyebrow">Node inspection</span><h2>{inspection.node.node_id}</h2></div><span className="direction-glyph">tick {state.tick}</span></div>
      <div className="inspect-section"><Row label="Canonical node ID" value={inspection.node.node_id} /><Row label="Source node ID" value={inspection.node.source_node_id} /><Row label="FIFO policy" value={inspection.node.fifo_policy} /></div>
      <div className="inspect-section"><span className="section-label">Incoming links · immutable topology</span><div className="packet-chips">{inspection.node.incoming_link_ids.map((id) => <EvidenceLink key={id} id={id} onSelect={onSelectLink} />)}</div></div>
      <div className="inspect-section"><span className="section-label">Outgoing links · immutable topology</span><div className="packet-chips">{inspection.node.outgoing_link_ids.map((id) => <EvidenceLink key={id} id={id} onSelect={onSelectLink} />)}</div></div>
      <div className="inspect-section"><span className="section-label">Declared movement specifications</span>{inspection.movements.length ? inspection.movements.map((movement) => <div className="movement-inspection" key={movement.movement_id}><strong>{movement.movement_id}</strong><div><EvidenceLink id={movement.upstream_link_id} onSelect={onSelectLink} /> → <EvidenceLink id={movement.downstream_link_id} onSelect={onSelectLink} /></div><small>priority {movement.priority_weight} · lanes {movement.lane_group_ids.join(", ") || "not declared"} · conflicts {movement.conflict_resource_ids.join(", ") || "not declared"} · signal {movement.signal_group_id ?? "not declared"}</small></div>) : <em>Not applicable: no declared movements</em>}</div>
      <div className="inspect-section"><span className="section-label">Allocation evidence at tick {state.tick}</span>{inspection.traces.length ? inspection.traces.flatMap((trace) => trace.movements.map((movement) => <div className="movement-inspection trace" key={`${trace.tick}-${movement.movement_id}`}><strong>{movement.movement_id}</strong><Row label="Requests" value={movement.request_packet_ids.length ? movement.request_packet_ids.map((id) => <EvidenceLink key={id} id={id} onSelect={onSelectPacket} />) : "zero"} /><Row label="Approved" value={movement.approved_packet_ids.length ? movement.approved_packet_ids.map((id) => <EvidenceLink key={id} id={id} onSelect={onSelectPacket} />) : "zero"} /><Row label="Rejected" value={movement.rejected_packet_reasons.length ? movement.rejected_packet_reasons.map(([id, reason]) => <span key={id}><EvidenceLink id={id} onSelect={onSelectPacket} /> · {reason}</span>) : "zero"} /><Row label="Receiving supply" value={display(movement.receiving_supply_packets, "unavailable")} /><Row label="Movement capacity" value={display(movement.movement_capacity_packets, "unavailable")} /><Row label="Signal state" value={movement.signal_state.replaceAll("_", " ")} /><Row label="Governance state" value={display(movement.governance_state, "not declared")} /></div>)) : <p className="definition">Not observed at this tick in the exported movement trace. This does not mean zero allocation.</p>}</div>
      {finder}<div className="source-foot">Connectivity and movement specification · immutable topology metadata<br />Allocation decision details · engine-exported materialised trace<br />Missing trace · unavailable, not zero</div>
    </aside>;
  }

  const inspection = inspectLink(manifest, state, events, selectedLinkId);
  if (!inspection) return null;
  const { link, replay, lifecycle } = inspection;
  return <aside className="inspector panel">
    <div className="panel-heading"><div><span className="eyebrow">Link inspection</span><h2>{link.link_id}</h2></div><span className="direction-glyph"><EvidenceLink id={link.tail_node_id} onSelect={onSelectNode} /> → <EvidenceLink id={link.head_node_id} onSelect={onSelectNode} /></span></div>
    <span className={`status-pill ${replay.occupancy_packets ? "active" : "inactive"}`}>{replay.occupancy_packets ? "active" : "unoccupied"}</span>
    <div className="inspect-section"><Row label="Canonical link ID" value={link.link_id} /><Row label="Replay tick" value={state.tick} /><Row label="Occupancy / storage" value={`${replay.occupancy_packets} packets`} /><Row label="Cumulative entries" value={`${replay.cumulative_entries} packets`} /><Row label="Cumulative exits" value={`${replay.cumulative_exits} packets`} /></div>
    <div className="inspect-section"><span className="section-label">Static physical metadata</span><Row label="Length" value={display(link.length_m === null ? null : `${link.length_m} m`, link.field_availability.length_m)} /><Row label="Lanes" value={display(link.lane_count, link.field_availability.lane_count)} /><Row label="Free-flow speed" value={display(link.free_flow_speed_mps === null ? null : `${link.free_flow_speed_mps} m/s`, link.field_availability.free_flow_speed_mps)} /><Row label="Capacity" value={display(link.capacity_veh_per_hour_per_lane === null ? null : `${link.capacity_veh_per_hour_per_lane} veh/h/lane`, link.field_availability.capacity_veh_per_hour_per_lane)} /><Row label="Jam density" value={display(link.jam_density_veh_per_km_per_lane === null ? null : `${link.jam_density_veh_per_km_per_lane} veh/km/lane`, link.field_availability.jam_density_veh_per_km_per_lane)} /><Row label="Backward wave" value={display(link.backward_wave_speed_mps === null ? null : `${link.backward_wave_speed_mps} m/s`, link.field_availability.backward_wave_speed_mps)} /></div>
    <div className="inspect-section"><span className="section-label">Current packet membership</span><div className="packet-chips">{replay.packet_ids.length ? replay.packet_ids.map((id) => <EvidenceLink key={id} id={id} onSelect={onSelectPacket} />) : <em>zero packets</em>}</div></div>
    <div className="inspect-section"><span className="section-label">Queued packets</span><div className="packet-chips">{replay.queued_packet_ids.length ? replay.queued_packet_ids.map((id) => <EvidenceLink key={id} id={id} onSelect={onSelectPacket} />) : <em>zero packets</em>}</div></div>
    <div className="inspect-section"><span className="section-label">Sending / receiving</span><p className="definition">Unavailable in this artifact. Cumulative counts are not presented as sending or receiving supply.</p></div>
    <div className="inspect-section"><span className="section-label">Profile and provenance</span><Row label="Model profile" value={manifest.run.model_profile_id} />{manifest.provenance.interpretation_assumptions.map((assumption, index) => <p className="definition" key={index}>{assumption}</p>)}</div>
    <div className="inspect-section"><span className="section-label">Canonical link-boundary events through tick {state.tick}</span><div className="mini-events">{lifecycle.length ? lifecycle.slice(-12).map((event) => <button key={event.sequence_number} onClick={() => onNavigateEvent(event)}><code>#{event.sequence_number}</code><span>{event.event_type} · {event.packet_id}</span><b>t{event.physical_tick}</b></button>) : <em>not yet observed</em>}</div></div>
    <div className="inspect-section"><span className="section-label">Curve definition</span><p className="definition">{series.descriptor.counting_basis}. {series.descriptor.boundary_direction}.</p></div>
    {finder}<div className="source-foot">Replay state · event-derived scientific projection<br />Topology and physical profile · immutable declared metadata<br />Sending/receiving · unavailable in this artifact</div>
  </aside>;
}
