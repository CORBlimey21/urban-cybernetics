import type { CanonicalEvent } from "../lib/contract";

export function EventStream({ events, tick, onSelectPacket }: { events: CanonicalEvent[]; tick: number; onSelectPacket: (id: string) => void }) {
  const visible = events.filter((event) => event.physical_tick <= tick).slice(-14);
  return (
    <div className="event-stream">
      <div className="stream-header"><span>Canonical event stream</span><small>sequence order preserved</small></div>
      <div className="event-list">
        {visible.map((event) => (
          <button key={event.sequence_number} onClick={() => onSelectPacket(event.packet_id)}>
            <code>#{String(event.sequence_number).padStart(3, "0")}</code>
            <b>t{event.physical_tick}</b>
            <span className={`event-kind ${event.event_type}`}>{event.event_type.replaceAll("_", " ")}</span>
            <span>{event.packet_id}</span>
            <em>{event.entity_id}</em>
          </button>
        ))}
      </div>
    </div>
  );
}
