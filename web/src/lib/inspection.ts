// SPDX-License-Identifier: MPL-2.0
import type { CanonicalEvent, Manifest, MovementEvidence, ReplayState } from "./contract";

export const inspectNode = (manifest: Manifest, evidence: MovementEvidence[], nodeId: string) => {
  const node = manifest.topology.nodes.find((item) => item.node_id === nodeId);
  if (!node) return null;
  return {
    node,
    movements: manifest.topology.movements.filter((movement) => movement.node_id === nodeId),
    traces: evidence.filter((trace) => trace.junction_id === nodeId),
  };
};

export const inspectLink = (manifest: Manifest, state: ReplayState, events: CanonicalEvent[], linkId: string) => {
  const link = manifest.topology.links.find((item) => item.link_id === linkId);
  const replay = state.links.find((item) => item.link_id === linkId);
  if (!link || !replay) return null;
  return { link, replay, lifecycle: events.filter((event) => event.entity_id === linkId && event.physical_tick <= state.tick) };
};

export const inspectPacket = (manifest: Manifest, state: ReplayState, events: CanonicalEvent[], packetId: string) => {
  const packet = manifest.packets.find((item) => item.packet_id === packetId);
  const replay = state.packets.find((item) => item.packet_id === packetId);
  if (!packet || !replay) return null;
  return { packet, replay, lifecycle: events.filter((event) => event.packet_id === packetId) };
};

export const packetVisualEvidence = (manifest: Manifest, state: ReplayState, packetId: string | null) => {
  if (!packetId) return { declaredRoute: new Set<string>(), realisedPath: new Set<string>(), currentLinkId: null, originNodeId: null, destinationNodeId: null };
  const packet = manifest.packets.find((item) => item.packet_id === packetId);
  const replay = state.packets.find((item) => item.packet_id === packetId);
  return {
    declaredRoute: new Set(packet?.route_intent ?? []),
    realisedPath: new Set(replay?.realised_path ?? []),
    currentLinkId: replay?.current_link_id ?? null,
    originNodeId: packet?.origin_node_id ?? null,
    destinationNodeId: packet?.destination_node_id ?? null,
  };
};
