import type { CanonicalEvent, CumulativeSeries, Manifest, ReplayState } from "../lib/contract";

const display = (value: string | number | null, status?: string) => {
  if (value !== null) return String(value);
  return status ? `— ${status.replaceAll("_", " ")}` : "— unavailable";
};

const Row = ({ label, value }: { label: string; value: React.ReactNode }) => (
  <div className="inspect-row"><span>{label}</span><strong>{value}</strong></div>
);

export function Inspector({
  manifest,
  state,
  events,
  selectedLinkId,
  selectedPacketId,
  series,
  onSelectPacket,
}: {
  manifest: Manifest;
  state: ReplayState;
  events: CanonicalEvent[];
  selectedLinkId: string;
  selectedPacketId: string | null;
  series: CumulativeSeries;
  onSelectPacket: (packetId: string | null) => void;
}) {
  if (selectedPacketId) {
    const packet = manifest.packets.find((item) => item.packet_id === selectedPacketId);
    const replay = state.packets.find((item) => item.packet_id === selectedPacketId);
    const lifecycle = events.filter((event) => event.packet_id === selectedPacketId);
    if (packet && replay) return (
      <aside className="inspector panel">
        <div className="panel-heading"><div><span className="eyebrow">Packet inspection</span><h2>{packet.packet_id}</h2></div><button className="icon-button" onClick={() => onSelectPacket(null)} aria-label="Close packet inspection">×</button></div>
        <span className={`status-pill packet-${replay.status}`}>{replay.status.replaceAll("_", " ")}</span>
        <div className="inspect-section">
          <Row label="Demand declaration" value={packet.demand_id} />
          <Row label="Origin" value={display(packet.origin_node_id, packet.field_availability.origin_node_id)} />
          <Row label="Destination" value={display(packet.destination_node_id, packet.field_availability.destination_node_id)} />
          <Row label="Route artifact" value={display(packet.route_id, packet.field_availability.route_id)} />
          <Row label="Current link" value={display(replay.current_link_id, replay.status === "not_yet_observed" ? "not yet observed" : undefined)} />
          <Row label="Queue boundary" value={display(replay.queue_boundary_id, replay.status === "queued" ? "unknown" : "not applicable")} />
        </div>
        <div className="inspect-section"><span className="section-label">Declared route intent</span><div className="route-chain">{packet.route_intent.map((link) => <span key={link}>{link}</span>)}</div></div>
        <div className="inspect-section"><span className="section-label">Realised path so far</span><div className="route-chain realised">{replay.realised_path.length ? replay.realised_path.map((link, index) => <span key={`${link}-${index}`}>{link}</span>) : <em>not yet observed</em>}</div></div>
        <div className="inspect-section"><span className="section-label">Canonical lifecycle</span><div className="mini-events">{lifecycle.map((event) => <div key={event.sequence_number}><code>#{event.sequence_number}</code><span>{event.event_type}</span><b>t{event.physical_tick}</b></div>)}</div></div>
        <div className="source-foot">Packet metadata · {manifest.packets_descriptor.semantic_status.replaceAll("_", " ")}</div>
      </aside>
    );
  }

  const link = manifest.topology.links.find((item) => item.link_id === selectedLinkId)!;
  const replay = state.links.find((item) => item.link_id === selectedLinkId)!;
  return (
    <aside className="inspector panel">
      <div className="panel-heading"><div><span className="eyebrow">Link inspection</span><h2>{link.link_id}</h2></div><span className="direction-glyph">{link.tail_node_id} → {link.head_node_id}</span></div>
      <span className={`status-pill ${replay.occupancy_packets ? "active" : "inactive"}`}>{replay.occupancy_packets ? "active" : "unoccupied"}</span>
      <div className="inspect-section">
        <Row label="Replay tick" value={state.tick} />
        <Row label="Occupancy" value={`${replay.occupancy_packets} packets`} />
        <Row label="Queued here" value={`${replay.queued_packet_ids.length} packets`} />
        <Row label="Cumulative entries" value={`${replay.cumulative_entries} packets`} />
        <Row label="Cumulative exits" value={`${replay.cumulative_exits} packets`} />
      </div>
      <div className="inspect-section">
        <span className="section-label">Static physical metadata</span>
        <Row label="Length" value={display(link.length_m === null ? null : `${link.length_m} m`, link.field_availability.length_m)} />
        <Row label="Lanes" value={display(link.lane_count, link.field_availability.lane_count)} />
        <Row label="Free-flow speed" value={display(link.free_flow_speed_mps === null ? null : `${link.free_flow_speed_mps} m/s`, link.field_availability.free_flow_speed_mps)} />
        <Row label="Declared capacity" value={display(link.capacity_veh_per_hour_per_lane === null ? null : `${link.capacity_veh_per_hour_per_lane} veh/h/lane`, link.field_availability.capacity_veh_per_hour_per_lane)} />
      </div>
      <div className="inspect-section"><span className="section-label">Current packet membership</span><div className="packet-chips">{replay.packet_ids.length ? replay.packet_ids.map((id) => <button key={id} onClick={() => onSelectPacket(id)}>{id}</button>) : <em>zero packets</em>}</div></div>
      <div className="inspect-section"><span className="section-label">Curve definition</span><p className="definition">{series.descriptor.counting_basis}. {series.descriptor.boundary_direction}.</p></div>
      <div className="source-foot">State · event-derived scientific projection<br />Topology · immutable metadata</div>
    </aside>
  );
}
