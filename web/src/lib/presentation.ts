import type { LinkRecord, NetworkLayout, ReplayState } from "./contract";

export type PresentationMarker = Readonly<{
  x: number;
  y: number;
  progress: number;
  radius: number;
  opacity: number;
}>;

export const presentationMarkers = (
  link: LinkRecord,
  layout: NetworkLayout,
  state: ReplayState,
  phase: number,
): PresentationMarker[] => {
  const linkState = state.links.find((item) => item.link_id === link.link_id);
  const tail = layout.node_coordinates[link.tail_node_id];
  const head = layout.node_coordinates[link.head_node_id];
  if (!linkState || !tail || !head || linkState.occupancy_packets === 0) return [];
  return Array.from({ length: Math.min(linkState.occupancy_packets, 5) }, (_, index) => {
    const t = (phase + index / Math.max(linkState.occupancy_packets, 1)) % 1;
    return Object.freeze({
      x: tail[0] + (head[0] - tail[0]) * t,
      y: tail[1] + (head[1] - tail[1]) * t,
      progress: t,
      radius: 3.2,
      opacity: 0.55 + 0.35 * Math.sin(Math.PI * t),
    });
  });
};
