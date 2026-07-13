import type { MovementEvidence } from "../lib/contract";

export function MovementPanel({ evidence, tick }: { evidence: MovementEvidence[]; tick: number }) {
  const first = evidence[0];
  return <section className="movement-panel panel">
    <div className="panel-heading compact"><div><span className="eyebrow">Python allocation evidence · t{tick}</span><h2>Movement allocation</h2></div><span className="source-chip">not frontend-calculated</span></div>
    {!first ? <div className="empty-evidence"><b>Not observed at this tick</b><span>No persisted allocation trace is available; this is distinct from zero requests.</span></div> : <div className="movement-content">
      <div className="movement-meta"><span>junction <b>{first.junction_id}</b></span><span>allocator <b>{first.allocator_id}</b></span></div>
      {first.movements.map((movement) => <article key={movement.movement_id}><header><strong>{movement.movement_id}</strong><span>{movement.upstream_link_id} → {movement.downstream_link_id}</span></header><div><span>requests <b>{movement.request_packet_ids.length}</b></span><span>approved <b className="lime">{movement.approved_packet_ids.length}</b></span><span>receiving supply <b>{movement.receiving_supply_packets ?? "unavailable"}</b></span><span>signal <b>{movement.signal_state}</b></span></div>{movement.rejected_packet_reasons.length > 0 && <small>rejected: {movement.rejected_packet_reasons.map(([packet, reason]) => `${packet} · ${reason}`).join(", ")}</small>}</article>)}
    </div>}
  </section>;
}
