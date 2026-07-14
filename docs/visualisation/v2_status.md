# V2 Simulation Workbench status

## Network-layout milestone

V2 now exposes versioned multi-layout presentation metadata. Sioux Falls uses
the declared `sioux_falls_published_schematic_v1` arrangement by default, with
deterministic generated and circular alternatives. The browser supports layout
selection, non-geographic warnings, opposing-edge separation, label layers,
pan/zoom, fit, and reset without changing replay or scientific state. See
`v2_network_layouts.md` for the integrity boundary and provenance.

## Inspection and packet-following milestone

The network and inspector now support read-only node, directed-link, and packet
inspection. Node panels combine immutable connectivity and movement
specifications with Python-exported allocation traces at the selected tick;
link panels expose replay membership, queues, cumulative counts, lifecycle
events, physical metadata, and explicit unavailable fields. Packet panels
provide OD and route intent, realised path, canonical lifecycle, search, and
navigation to related links and nodes.

Follow packet is presentation state: it highlights declared and realised paths
and updates as exact replay advances, but it does not create packet positions,
change the camera, or affect physical state. Interpolated canvas markers remain
anonymous and are intentionally not treated as selectable packet evidence.

## M8 validation-workbench milestone

The application now includes a Validation mode with a declared three-case M8
analytical library, sanctioned background execution, append-only result
history, expected/observed/difference charts, exact replay, authored physical
explanations, validation overlays, packet waiting evidence, and reference-asset
placeholders. See `m8_validation_workbench_v1.md` for contracts and boundaries.

## Delivered vertical slice

- V1 artifacts remain loadable and appear in the combined artifact library.
- Runtime V2 artifacts are discovered under a declared backend root and can be
  switched without server restart.
- A typed resource catalogue and New Run UI launch sanctioned synthetic or
  bounded Sioux Falls Python runs.
- Lifecycle/progress SSE survives browser disconnects; explicit idempotent
  pause, resume, and cancellation commands act at safe tick boundaries.
- Viewer pause, engine pause, follow-live, behind-live indication, scrubbing,
  and go-live are distinct.
- Canonical chunks, exact checkpoints, lazy event ranges, Python seek, frozen
  provenance, validation, and final V1-compatible bundles are persisted.
- Movement-allocation requests, FIFO order, supply, constraints, approvals,
  rejections/reasons, and resulting canonical sequences are exposed from Python
  traces rather than recomputed in JavaScript.
- Two runs can be pinned for topology/profile/demand compatibility and basic
  outcome comparison.

## Bounded benchmark acceptance artifact

`v2-sioux-falls-bounded-100-v1` contains 100 requested/instantiated/completed
packets, zero unresolved/cancelled packets, 926 canonical events, 32 final ticks,
26 event chunks, seven checkpoints, and 37 movement-allocation records. Core
Python validation and actual exact replay passed. The directory is approximately
2.9 MB. It uses the UC default assumption profile and does not claim empirical
calibration or geographic coordinates.

Local TestClient measurements on the development machine (20 requests, warm
process) were: artifact library 1.05 ms mean / 4.38 ms max; live manifest 6.35
ms / 6.99 ms; exact seek to tick 17 from a checkpoint 5.39 ms / 12.40 ms; and a
100-event range 1.26 ms / 1.51 ms. Event chunks were 621–31,585 bytes (5,874
mean); checkpoints were 42,436–45,071 bytes (44,249 mean). These are local
diagnostic measurements, not cross-platform performance guarantees. Browser
memory was not captured because browser instrumentation was unavailable under
the machine controls used for this run.

## Known limitations

- The local executor is a background thread in the server process, not a
  production process supervisor. It survives browser disconnects, not server
  termination or machine failure.
- Runtime progress recovery is durable JSONL polling behind SSE; it is not a
  high-throughput message broker.
- The committed checkpoint/event format is readable JSON and prioritises auditability
  over minimum size.
- The comparison strip is metadata/outcome-only; synchronised replay and delta
  charts are deferred.
- Movement capacity is shown as unavailable where the existing engine trace does
  not declare a distinct per-movement cap. Zero, unavailable, and not observed
  remain distinct.
- The Canvas uses deterministic diagram layout and viewport drawing, not map
  tiles, lane geometry, or microscopic trajectories.
- The frontend production bundle retains the existing ECharts-driven size
  advisory; route-level code splitting is a later performance task.

## Recommended V3 milestone

Build a scientific comparison laboratory over the existing evidence plane:
synchronised exact replay for two compatible artifacts, Python-derived delta
curves, validation/literature overlays, and the first explicit physical-truth
versus delayed authority-observation frame. Keep authority belief as evidence
with its own time basis; never feed presentation interpolation back into it.
