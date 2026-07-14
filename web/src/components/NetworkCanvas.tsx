import { useEffect, useMemo, useRef, useState } from "react";
import type { Manifest, NetworkLayout, ReplayState, ValidationCase } from "../lib/contract";
import { directedEdgePath, distanceToEdgePath, pointOnQuadratic } from "../lib/networkGeometry";
import { presentationMarkers } from "../lib/presentation";
import { packetVisualEvidence } from "../lib/inspection";

type Props = {
  manifest: Manifest;
  layout: NetworkLayout;
  state: ReplayState;
  selectedLinkId: string;
  selectedNodeId: string | null;
  selectedPacketId: string | null;
  followingPacket: boolean;
  phase: number;
  onSelectLink: (linkId: string) => void;
  onSelectNode: (nodeId: string) => void;
  validationOverlays?: ValidationCase["overlays"];
};

type ViewTransform = Readonly<{ zoom: number; panX: number; panY: number }>;
type Layers = Readonly<{ nodeIds: boolean; linkIds: boolean; activity: boolean }>;
type LayoutBounds = Readonly<{ minX: number; maxX: number; minY: number; maxY: number }>;

const initialView: ViewTransform = { zoom: 1, panX: 0, panY: 0 };
const initialLayers: Layers = { nodeIds: true, linkIds: false, activity: false };

const screenPoint = (
  position: readonly [number, number], bounds: LayoutBounds, width: number, height: number, view: ViewTransform,
) => {
  const rangeX = Math.max(bounds.maxX - bounds.minX, 1e-9);
  const rangeY = Math.max(bounds.maxY - bounds.minY, 1e-9);
  const scale = Math.min((width - 92) / rangeX, (height - 116) / rangeY);
  const baseX = width / 2 + (position[0] - (bounds.minX + bounds.maxX) / 2) * scale;
  const baseY = height / 2 + (position[1] - (bounds.minY + bounds.maxY) / 2) * scale;
  return {
    x: width / 2 + (baseX - width / 2) * view.zoom + view.panX,
    y: height / 2 + (baseY - height / 2) * view.zoom + view.panY,
  };
};

export function NetworkCanvas({
  manifest, layout, state, selectedLinkId, selectedNodeId, selectedPacketId, followingPacket, phase, onSelectLink, onSelectNode, validationOverlays = [],
}: Props) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const sizeRef = useRef({ width: 800, height: 480 });
  const dragRef = useRef<{ x: number; y: number; panX: number; panY: number; moved: boolean } | null>(null);
  const [view, setView] = useState<ViewTransform>(initialView);
  const [layers, setLayers] = useState<Layers>(initialLayers);
  const [resizeVersion, setResizeVersion] = useState(0);
  const [hovered, setHovered] = useState<{ kind: "node" | "link"; id: string } | null>(null);
  const bounds = useMemo<LayoutBounds>(() => {
    const coordinates = Object.values(layout.node_coordinates);
    const xs = coordinates.map((point) => point[0]);
    const ys = coordinates.map((point) => point[1]);
    return { minX: Math.min(...xs), maxX: Math.max(...xs), minY: Math.min(...ys), maxY: Math.max(...ys) };
  }, [layout]);

  useEffect(() => setView(initialView), [layout.layout_id]);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const resize = () => {
      const bounds = canvas.getBoundingClientRect();
      const ratio = window.devicePixelRatio || 1;
      sizeRef.current = { width: bounds.width, height: bounds.height };
      canvas.width = Math.max(1, Math.floor(bounds.width * ratio));
      canvas.height = Math.max(1, Math.floor(bounds.height * ratio));
      canvas.getContext("2d")?.setTransform(ratio, 0, 0, ratio, 0, 0);
      setResizeVersion((current) => current + 1);
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

    context.strokeStyle = "rgba(119, 153, 141, 0.045)";
    context.lineWidth = 1;
    for (let x = 30; x < width; x += 44) {
      context.beginPath(); context.moveTo(x, 0); context.lineTo(x, height); context.stroke();
    }
    for (let y = 24; y < height; y += 44) {
      context.beginPath(); context.moveTo(0, y); context.lineTo(width, y); context.stroke();
    }

    const packetEvidence = packetVisualEvidence(manifest, state, selectedPacketId);
    const directionPairs = new Set(manifest.topology.links.map((link) => `${link.tail_node_id}->${link.head_node_id}`));

    for (const link of manifest.topology.links) {
      const tail = layout.node_coordinates[link.tail_node_id];
      const head = layout.node_coordinates[link.head_node_id];
      const linkState = state.links.find((item) => item.link_id === link.link_id);
      if (!tail || !head || !linkState) continue;
      const path = directedEdgePath(
        screenPoint(tail, bounds, width, height, view),
        screenPoint(head, bounds, width, height, view),
        directionPairs.has(`${link.head_node_id}->${link.tail_node_id}`),
      );
      const selected = link.link_id === selectedLinkId;
      const hover = hovered?.kind === "link" && hovered.id === link.link_id;
      const onSelectedRoute = packetEvidence.declaredRoute.has(link.link_id);
      const onRealisedPath = packetEvidence.realisedPath.has(link.link_id);
      const queued = linkState.queued_packet_ids.length > 0;
      const occupied = linkState.occupancy_packets > 0;
      context.strokeStyle = selected ? "#d8ff79" : hover ? "#b8d4cb" : onRealisedPath ? "#9cffd9" : queued ? "#ffb55f" : occupied ? "#5be4bd" : onSelectedRoute ? "#597c73" : "#263d38";
      context.lineWidth = selected ? 4.5 : hover ? 3.2 : onRealisedPath ? 3.6 : occupied || queued ? 3 : onSelectedRoute ? 2.4 : 1.6;
      context.beginPath();
      context.moveTo(path.start.x, path.start.y);
      context.quadraticCurveTo(path.control.x, path.control.y, path.end.x, path.end.y);
      context.stroke();

      const activeValidationOverlays = validationOverlays.filter((overlay) => overlay.link_id === link.link_id && overlay.active_from_tick <= state.tick && state.tick <= overlay.active_through_tick);
      if (activeValidationOverlays.length) {
        const primary = activeValidationOverlays[0];
        context.strokeStyle = primary.kind === "blocked_boundary" ? "#ff8585" : primary.kind === "reference_wave" ? "#b9a4ff" : "#f6c66d";
        context.lineWidth = primary.kind === "queued_region" ? 7 : 3;
        context.globalAlpha = primary.kind === "queued_region" ? 0.32 : 0.82;
        context.setLineDash(primary.evidence_source === "analytical_reference" ? [7, 5] : [3, 4]);
        context.beginPath(); context.moveTo(path.start.x, path.start.y); context.quadraticCurveTo(path.control.x, path.control.y, path.end.x, path.end.y); context.stroke();
        context.setLineDash([]); context.globalAlpha = 1;
        if (primary.direction === "backward") {
          const tip = pointOnQuadratic(path, 0.28); const before = pointOnQuadratic(path, 0.36);
          const angle = Math.atan2(tip.y - before.y, tip.x - before.x);
          context.fillStyle = context.strokeStyle; context.beginPath(); context.moveTo(tip.x, tip.y); context.lineTo(tip.x - 8 * Math.cos(angle - .5), tip.y - 8 * Math.sin(angle - .5)); context.lineTo(tip.x - 8 * Math.cos(angle + .5), tip.y - 8 * Math.sin(angle + .5)); context.closePath(); context.fill();
        }
      }

      const arrow = pointOnQuadratic(path, 0.76);
      const beforeArrow = pointOnQuadratic(path, 0.70);
      const angle = Math.atan2(arrow.y - beforeArrow.y, arrow.x - beforeArrow.x);
      context.fillStyle = context.strokeStyle;
      context.beginPath();
      context.moveTo(arrow.x, arrow.y);
      context.lineTo(arrow.x - 7 * Math.cos(angle - 0.48), arrow.y - 7 * Math.sin(angle - 0.48));
      context.lineTo(arrow.x - 7 * Math.cos(angle + 0.48), arrow.y - 7 * Math.sin(angle + 0.48));
      context.closePath(); context.fill();

      for (const marker of presentationMarkers(link, layout, state, phase)) {
        const markerPathPoint = pointOnQuadratic(path, marker.progress);
        context.globalAlpha = marker.opacity;
        context.fillStyle = "#afffdd";
        context.beginPath(); context.arc(markerPathPoint.x, markerPathPoint.y, marker.radius, 0, Math.PI * 2); context.fill();
        context.globalAlpha = 1;
      }
      if (packetEvidence.currentLinkId === link.link_id) {
        context.strokeStyle = followingPacket ? "#d8ff79" : "#ffffff";
        context.lineWidth = followingPacket ? 2.2 : 1;
        context.setLineDash([4, 6]);
        context.beginPath(); context.moveTo(path.start.x, path.start.y); context.quadraticCurveTo(path.control.x, path.control.y, path.end.x, path.end.y); context.stroke();
        context.setLineDash([]);
      }
      if (selected || layers.linkIds || (layers.activity && linkState.occupancy_packets > 0)) {
        const label = pointOnQuadratic(path, selected ? 0.46 : 0.52);
        context.font = `${selected ? 650 : 560} ${selected ? 10 : 8}px Inter, system-ui, sans-serif`;
        context.textAlign = "center";
        context.fillStyle = selected ? "#efffd1" : "#78948b";
        const text = layers.activity || selected ? `${link.link_id} · ${linkState.occupancy_packets}` : link.link_id;
        context.fillText(text, label.x, label.y - (path.opposingOffset ? 7 : 5));
      }
    }

    for (const node of manifest.topology.nodes) {
      const position = layout.node_coordinates[node.node_id];
      if (!position) continue;
      const { x, y } = screenPoint(position, bounds, width, height, view);
      const selected = node.node_id === selectedNodeId;
      const hover = hovered?.kind === "node" && hovered.id === node.node_id;
      const endpoint = node.node_id === packetEvidence.originNodeId || node.node_id === packetEvidence.destinationNodeId;
      context.shadowColor = "rgba(91, 228, 189, .14)";
      context.shadowBlur = 12;
      context.fillStyle = "#0f201c";
      context.strokeStyle = selected ? "#d8ff79" : hover ? "#e5fff6" : endpoint ? "#9cffd9" : "#739c90";
      context.lineWidth = selected ? 3 : hover ? 2.5 : endpoint ? 2.2 : 1.4;
      context.beginPath(); context.arc(x, y, selected || hover ? 13 : 11, 0, Math.PI * 2); context.fill(); context.stroke();
      context.shadowBlur = 0;
      if (layers.nodeIds) {
        context.fillStyle = "#d8e9e3";
        context.font = "650 8px ui-monospace, monospace";
        context.textAlign = "center";
        context.textBaseline = "middle";
        const compactNodeId = node.node_id.replace(/^N0*/, "") || node.node_id;
        context.fillText(compactNodeId, x, y + 0.5);
        context.textBaseline = "alphabetic";
      }
    }
  }, [bounds, followingPacket, hovered, layers, layout, manifest, phase, resizeVersion, selectedLinkId, selectedNodeId, selectedPacketId, state, validationOverlays, view]);

  const hitTest = (point: { x: number; y: number }, width: number, height: number) => {
    for (const node of manifest.topology.nodes) {
      const position = layout.node_coordinates[node.node_id];
      if (!position) continue;
      const screen = screenPoint(position, bounds, width, height, view);
      if (Math.hypot(point.x - screen.x, point.y - screen.y) <= 17) return { kind: "node" as const, id: node.node_id };
    }
    const directionPairs = new Set(manifest.topology.links.map((link) => `${link.tail_node_id}->${link.head_node_id}`));
    let nearest: { id: string; distance: number } | null = null;
    for (const link of manifest.topology.links) {
      const tail = layout.node_coordinates[link.tail_node_id];
      const head = layout.node_coordinates[link.head_node_id];
      if (!tail || !head) continue;
      const path = directedEdgePath(screenPoint(tail, bounds, width, height, view), screenPoint(head, bounds, width, height, view), directionPairs.has(`${link.head_node_id}->${link.tail_node_id}`));
      const distance = distanceToEdgePath(point, path);
      if (!nearest || distance < nearest.distance) nearest = { id: link.link_id, distance };
    }
    return nearest && nearest.distance < 16 ? { kind: "link" as const, id: nearest.id } : null;
  };

  const selectNearest = (event: React.MouseEvent<HTMLCanvasElement>) => {
    if (dragRef.current?.moved) return;
    const rect = event.currentTarget.getBoundingClientRect();
    const point = { x: event.clientX - rect.left, y: event.clientY - rect.top };
    const target = hitTest(point, rect.width, rect.height);
    if (target?.kind === "node") onSelectNode(target.id);
    if (target?.kind === "link") onSelectLink(target.id);
  };

  const resetView = (resetLayers = false) => {
    setView(initialView);
    if (resetLayers) setLayers(initialLayers);
  };

  return (
    <div className="network-frame">
      <canvas
        ref={canvasRef}
        className="network-canvas"
        onClick={selectNearest}
        onWheel={(event) => {
          event.preventDefault();
          setView((current) => ({ ...current, zoom: Math.max(0.65, Math.min(3.2, current.zoom * (event.deltaY < 0 ? 1.12 : 0.89))) }));
        }}
        style={{ cursor: hovered ? "pointer" : "grab" }}
        onMouseDown={(event) => { dragRef.current = { x: event.clientX, y: event.clientY, panX: view.panX, panY: view.panY, moved: false }; }}
        onMouseMove={(event) => {
          if (!dragRef.current) {
            const rect = event.currentTarget.getBoundingClientRect();
            setHovered(hitTest({ x: event.clientX - rect.left, y: event.clientY - rect.top }, rect.width, rect.height));
            return;
          }
          if (Math.hypot(event.clientX - dragRef.current.x, event.clientY - dragRef.current.y) > 3) dragRef.current.moved = true;
          setView((current) => ({ ...current, panX: dragRef.current!.panX + event.clientX - dragRef.current!.x, panY: dragRef.current!.panY + event.clientY - dragRef.current!.y }));
        }}
        onMouseUp={() => { window.setTimeout(() => { dragRef.current = null; }, 0); }}
        onMouseLeave={() => { dragRef.current = null; setHovered(null); }}
        role="img"
        aria-label={`Directed topology at tick ${state.tick}, layout ${layout.label}. Click a node or directed link to inspect it.`}
      />
      <div className="canvas-tools" aria-label="Network view controls">
        <button onClick={() => resetView(false)}>Fit</button>
        <button onClick={() => resetView(true)}>Reset view</button>
        <label><input type="checkbox" checked={layers.nodeIds} onChange={(event) => setLayers((current) => ({ ...current, nodeIds: event.target.checked }))} /> Nodes</label>
        <label><input type="checkbox" checked={layers.linkIds} onChange={(event) => setLayers((current) => ({ ...current, linkIds: event.target.checked }))} /> Links</label>
        <label><input type="checkbox" checked={layers.activity} onChange={(event) => setLayers((current) => ({ ...current, activity: event.target.checked }))} /> Activity</label>
      </div>
      <div className="canvas-note"><span className="legend-dot interpolation" /> animated dots: presentation only</div>
      <div className="canvas-scale">{layout.is_geographic ? `Geographic · ${layout.crs}` : "Non-geographic · distances and angles are not physical"}</div>
    </div>
  );
}
