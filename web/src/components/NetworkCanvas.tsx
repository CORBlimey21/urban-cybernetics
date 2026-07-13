import { useEffect, useRef } from "react";
import type { Manifest, ReplayState } from "../lib/contract";
import { presentationMarkers } from "../lib/presentation";

type Props = {
  manifest: Manifest;
  state: ReplayState;
  selectedLinkId: string;
  selectedPacketId: string | null;
  phase: number;
  onSelectLink: (linkId: string) => void;
};

const point = (
  position: readonly [number, number],
  width: number,
  height: number,
): [number, number] => [46 + position[0] * (width - 92), 42 + position[1] * (height - 84)];

const distanceToSegment = (
  px: number,
  py: number,
  x1: number,
  y1: number,
  x2: number,
  y2: number,
) => {
  const dx = x2 - x1;
  const dy = y2 - y1;
  const lengthSquared = dx * dx + dy * dy;
  const t = lengthSquared === 0 ? 0 : Math.max(0, Math.min(1, ((px - x1) * dx + (py - y1) * dy) / lengthSquared));
  return Math.hypot(px - (x1 + t * dx), py - (y1 + t * dy));
};

export function NetworkCanvas({
  manifest,
  state,
  selectedLinkId,
  selectedPacketId,
  phase,
  onSelectLink,
}: Props) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const sizeRef = useRef({ width: 800, height: 480 });

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const resize = () => {
      const bounds = canvas.getBoundingClientRect();
      const ratio = window.devicePixelRatio || 1;
      sizeRef.current = { width: bounds.width, height: bounds.height };
      canvas.width = Math.max(1, Math.floor(bounds.width * ratio));
      canvas.height = Math.max(1, Math.floor(bounds.height * ratio));
      const context = canvas.getContext("2d");
      context?.setTransform(ratio, 0, 0, ratio, 0, 0);
    };
    resize();
    const observer = new ResizeObserver(resize);
    observer.observe(canvas);
    return () => observer.disconnect();
  }, []);

  useEffect(() => {
    const canvas = canvasRef.current;
    const context = canvas?.getContext("2d");
    if (!canvas || !context) return;
    const { width, height } = sizeRef.current;
    context.clearRect(0, 0, width, height);

    context.strokeStyle = "rgba(119, 153, 141, 0.055)";
    context.lineWidth = 1;
    for (let x = 30; x < width; x += 44) {
      context.beginPath(); context.moveTo(x, 0); context.lineTo(x, height); context.stroke();
    }
    for (let y = 24; y < height; y += 44) {
      context.beginPath(); context.moveTo(0, y); context.lineTo(width, y); context.stroke();
    }

    const selectedPacket = state.packets.find((packet) => packet.packet_id === selectedPacketId);
    const selectedRoute = new Set(
      manifest.packets.find((packet) => packet.packet_id === selectedPacketId)?.route_intent ?? [],
    );
    for (const link of manifest.topology.links) {
      const tail = manifest.presentation.node_positions[link.tail_node_id];
      const head = manifest.presentation.node_positions[link.head_node_id];
      const linkState = state.links.find((item) => item.link_id === link.link_id);
      if (!tail || !head || !linkState) continue;
      const [x1, y1] = point(tail, width, height);
      const [x2, y2] = point(head, width, height);
      const selected = link.link_id === selectedLinkId;
      const onSelectedRoute = selectedRoute.has(link.link_id);
      const queued = linkState.queued_packet_ids.length > 0;
      const occupied = linkState.occupancy_packets > 0;
      context.strokeStyle = selected
        ? "#d8ff79"
        : queued
          ? "#ffb55f"
          : occupied
            ? "#5be4bd"
            : onSelectedRoute
              ? "#597c73"
              : "#263d38";
      context.lineWidth = selected ? 5 : occupied || queued ? 3.2 : onSelectedRoute ? 2.5 : 1.8;
      context.beginPath(); context.moveTo(x1, y1); context.lineTo(x2, y2); context.stroke();
      const angle = Math.atan2(y2 - y1, x2 - x1);
      const ax = x1 + (x2 - x1) * 0.78;
      const ay = y1 + (y2 - y1) * 0.78;
      context.fillStyle = context.strokeStyle;
      context.beginPath();
      context.moveTo(ax, ay);
      context.lineTo(ax - 8 * Math.cos(angle - 0.45), ay - 8 * Math.sin(angle - 0.45));
      context.lineTo(ax - 8 * Math.cos(angle + 0.45), ay - 8 * Math.sin(angle + 0.45));
      context.closePath(); context.fill();

      for (const marker of presentationMarkers(link, manifest, state, phase)) {
        const [mx, my] = point([marker.x, marker.y], width, height);
        context.globalAlpha = marker.opacity;
        context.fillStyle = "#afffdd";
        context.beginPath(); context.arc(mx, my, marker.radius, 0, Math.PI * 2); context.fill();
        context.globalAlpha = 1;
      }
      if (selectedPacket?.current_link_id === link.link_id) {
        context.strokeStyle = "#ffffff";
        context.lineWidth = 1;
        context.setLineDash([4, 6]);
        context.beginPath(); context.moveTo(x1, y1); context.lineTo(x2, y2); context.stroke();
        context.setLineDash([]);
      }
      const labelX = (x1 + x2) / 2;
      const labelY = (y1 + y2) / 2 - 9;
      context.font = "600 11px Inter, system-ui, sans-serif";
      context.textAlign = "center";
      context.fillStyle = selected ? "#efffd1" : "#8aa59d";
      context.fillText(`${link.link_id}  ${linkState.occupancy_packets}`, labelX, labelY);
    }

    for (const node of manifest.topology.nodes) {
      const position = manifest.presentation.node_positions[node.node_id];
      if (!position) continue;
      const [x, y] = point(position, width, height);
      context.shadowColor = "rgba(91, 228, 189, .16)";
      context.shadowBlur = 15;
      context.fillStyle = "#0f201c";
      context.strokeStyle = "#739c90";
      context.lineWidth = 1.5;
      context.beginPath(); context.arc(x, y, 13, 0, Math.PI * 2); context.fill(); context.stroke();
      context.shadowBlur = 0;
      context.fillStyle = "#d8e9e3";
      context.font = "650 11px Inter, system-ui, sans-serif";
      context.textAlign = "center";
      context.fillText(node.node_id, x, y + 27);
    }
  }, [manifest, onSelectLink, phase, selectedLinkId, selectedPacketId, state]);

  const selectNearest = (event: React.MouseEvent<HTMLCanvasElement>) => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const rect = canvas.getBoundingClientRect();
    const px = event.clientX - rect.left;
    const py = event.clientY - rect.top;
    let nearest: { id: string; distance: number } | null = null;
    for (const link of manifest.topology.links) {
      const tail = manifest.presentation.node_positions[link.tail_node_id];
      const head = manifest.presentation.node_positions[link.head_node_id];
      if (!tail || !head) continue;
      const [x1, y1] = point(tail, rect.width, rect.height);
      const [x2, y2] = point(head, rect.width, rect.height);
      const distance = distanceToSegment(px, py, x1, y1, x2, y2);
      if (!nearest || distance < nearest.distance) nearest = { id: link.link_id, distance };
    }
    if (nearest && nearest.distance < 22) onSelectLink(nearest.id);
  };

  return (
    <div className="network-frame">
      <canvas
        ref={canvasRef}
        className="network-canvas"
        onClick={selectNearest}
        role="img"
        aria-label={`Directed topology at tick ${state.tick}. Click a link to inspect it.`}
      />
      <div className="canvas-note"><span className="legend-dot interpolation" /> animated dots: presentation only</div>
      <div className="canvas-scale">{manifest.presentation.layout_note}</div>
    </div>
  );
}
