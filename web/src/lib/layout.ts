import type { Manifest, NetworkLayout } from "./contract";

const legacyLayout = (manifest: Manifest): NetworkLayout => ({
  schema_version: "uc.visualisation.layout.v1",
  layout_id: `legacy:${manifest.run.topology_id}`,
  label: "Legacy artifact layout",
  kind: manifest.presentation.layout_kind === "synthetic_declared" ? "declared_schematic" : "circular_fallback",
  version: "legacy-adapter-v1",
  preferred: true,
  is_geographic: false,
  coordinate_basis: "legacy normalised canvas",
  coordinate_units: "normalised [0,1]",
  source: "V1 presentation metadata adapter",
  provenance: "Adapted from the persisted V1 node_positions field.",
  origin: manifest.presentation.layout_kind === "synthetic_declared" ? "declared" : "generated",
  generated_by: manifest.presentation.layout_kind === "synthetic_declared" ? null : "legacy-v1-adapter",
  deterministic_seed: manifest.presentation.layout_kind === "synthetic_declared" ? null : 0,
  crs: null,
  node_coordinates: manifest.presentation.node_positions,
  edge_routes: {},
  warnings: [manifest.presentation.layout_note],
  distance_semantics: "Legacy screen distances are presentation-only.",
  angle_semantics: "Legacy screen angles are presentation-only.",
});

export const availableLayouts = (manifest: Manifest): NetworkLayout[] =>
  manifest.presentation.layouts.length > 0
    ? manifest.presentation.layouts
    : [legacyLayout(manifest)];

export const defaultLayout = (manifest: Manifest): NetworkLayout => {
  const layouts = availableLayouts(manifest);
  return layouts.find((layout) => layout.layout_id === manifest.presentation.default_layout_id)
    ?? layouts.find((layout) => layout.preferred)
    ?? layouts[0];
};

export const compatibleLayout = (manifest: Manifest, preferredId: string | null): NetworkLayout => {
  const layouts = availableLayouts(manifest);
  return layouts.find((layout) => layout.layout_id === preferredId) ?? defaultLayout(manifest);
};
