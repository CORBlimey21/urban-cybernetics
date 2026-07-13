import type { LinkRecord, Manifest, ReplayState } from "./contract";

export type PresentationMarker = Readonly<{
  x: number;
  y: number;
  radius: number;
  opacity: number;
}>;

export const presentationMarkers = (
  link: LinkRecord,
  manifest: Manifest,
  state: ReplayState,
  phase: number,
): PresentationMarker[] => {
  const linkState = state.links.find((item) => item.link_id === link.link_id);
  const tail = manifest.presentation.node_positions[link.tail_node_id];
  const head = manifest.presentation.node_positions[link.head_node_id];
  if (!linkState || !tail || !head || linkState.occupancy_packets === 0) return [];
  return Array.from({ length: Math.min(linkState.occupancy_packets, 5) }, (_, index) => {
    const t = (phase + index / Math.max(linkState.occupancy_packets, 1)) % 1;
    return Object.freeze({
      x: tail[0] + (head[0] - tail[0]) * t,
      y: tail[1] + (head[1] - tail[1]) * t,
      radius: 3.2,
      opacity: 0.55 + 0.35 * Math.sin(Math.PI * t),
    });
  });
};
