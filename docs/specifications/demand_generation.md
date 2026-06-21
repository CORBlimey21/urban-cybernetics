# Demand Generation

**Status:** D2 executable specification.
**Scope:** immutable OD demand declarations, deterministic departure schedules, manifest hashing, Sioux Falls OD loading, route resolution, and scheduled loading admission.
**Non-scope:** assignment, route choice behaviour, realistic departure-time choice, calibration, stochastic demand, governance, behavioural churn, Cork demand, OSM demand, plotting, dashboards, and experiment orchestration.

---

### Demand Before Packets

A demand declaration is a pre-physical input record. It says that some unit-packet quantity wants to travel from one canonical origin node to one canonical destination node under an optional cohort or authority label. It has no packet ID, no lifecycle, no storage position, no queue position, and no conservation entry.

Packets begin only when the loading engine admits a scheduled departure onto an origin link. If origin storage is full, the loading-engine admission request remains pending and no packet exists yet. Pending demand is not a half-packet and is not an overflow buffer.

The loading engine remains the only owner of packet identity, packet lifecycle, physical event history, storage, sending, receiving, queues, transfer, and completion.

---

### D1 Artifacts

D1 introduces `urban_cybernetics.demand` with these first-class artifacts:

- `ODDemandDeclaration`: immutable OD demand with `demand_id`, `origin_node_id`, `destination_node_id`, `quantity_packets`, `departure_schedule`, optional `cohort_id`, optional `authority_id`, and optional source-zone provenance.
- `DemandManifest`: immutable, hashable collection of OD demand declarations tied to a `topology_id` and `topology_hash`.
- `DemandManifestSourceMetadata`: source format, source hash, source metadata, interpretation assumptions, and scaling assumptions that affect demand identity.
- `ResolvedDemandManifest`: separate route-resolution artifact mapping raw OD declarations to canonical routes.
- `ScheduledDemandLoader`: adapter that submits due resolved demand to the loading engine as one-unit loading admission requests.

Raw demand declarations deliberately do not contain route IDs, route intents, packet IDs, or loading state.

---

### Departure Schedules

D1/D2 support deterministic schedules only.

`FixedDepartureSchedule(departure_tick=N)` expands every unit in a declaration to tick `N`.

`UniformWindowDepartureSchedule(start_tick=A, end_tick=B)` is declaration-local. It spreads one OD declaration over the inclusive tick window `[A, B]`. The expansion is deterministic: each tick receives the integer base share for that declaration, and any remainder is assigned to earlier ticks. For example, eight units over ticks `[2, 4]` expand to:

`(2, 2, 2, 3, 3, 3, 4, 4)`

`GlobalUniformDepartureSchedule(start_tick=A, end_tick=B)` is manifest-global. It is expanded by `ScheduledDemandLoader` only after the full resolved demand manifest is available. It distributes all unit loading requests across the inclusive tick window `[A, B]`, so the total manifest demand uses the whole window when the total quantity is large enough. Counts per tick differ by at most one under integer constraints.

The global schedule remains pre-packet demand scheduling. It does not instantiate packets, inspect storage, move packets, create queues, or model physical behaviour. Loading remains responsible for admission and movement.

D2 does not implement Poisson processes, day profiles, peak-period calibration, stochastic resampling, or behavioural departure-time choice.

---

### Manifest Hashing

Demand manifests compute deterministic SHA-256 hashes over meaningful demand content:

- declaration IDs and OD endpoints;
- `quantity_packets`;
- schedule type and schedule parameters;
- cohort and authority labels;
- source-zone provenance where present;
- topology ID and topology hash;
- source interpretation assumptions;
- scaling assumptions.

Hashes are stable under irrelevant dictionary ordering. Changing demand quantity, schedule, source assumptions, scaling assumptions, topology hash, or labels changes the manifest hash.

---

### Sioux Falls OD Loader

`load_sioux_falls_demand_manifest` reads the committed TNTP trips file at:

`data/benchmarks/sioux_falls/SiouxFalls_trips.tntp`

The loader:

- parses nonzero OD pairs;
- preserves source origin and destination zone IDs;
- maps source zones to canonical Sioux Falls node IDs through topology node provenance;
- records the trips file hash and TNTP metadata;
- supports `scale_factor`, `max_pairs`, `min_quantity_packets`, and `max_total_quantity_packets`;
- produces a deterministic `DemandManifest`.

Full-matrix loading may be expensive because the matrix declares hundreds of thousands of unit packets before scaling. That is expected useful benchmark information, not a calibration claim.

---

### Route Resolution

Raw demand is OD-only. Routes are introduced only by `resolve_demand_routes`, which creates a `ResolvedDemandManifest`.

The D1 resolver uses the existing deterministic shortest-link-count BFS route constructor over canonical topology. This is a default route resolver, not assignment, route choice, dynamic traffic assignment, UE, SO, or congestion-aware optimisation.

---

### Scheduled Loading

`ScheduledDemandLoader` expands resolved demand into one-unit scheduled loading requests. At each engine tick it submits due, unsubmitted requests to `LoadingEngine.instantiate`.

For declaration-local schedules, each OD declaration expands independently. For `GlobalUniformDepartureSchedule`, the loader expands the whole manifest as one deterministic unit stream before building loading requests.

The adapter does not create packets. It does not append lifecycle events. It does not inspect or mutate storage directly. If the loading engine cannot admit a request because the origin link is full, the engine keeps that loading request pending and retries under the existing L1 origin-blocking semantics.

Packet IDs appear only after the loading engine admits a request.

---

### Explicit Non-Goals

D2 does not implement assignment, route choice behaviour, realistic departure-time choice, calibration, stochastic demand, governance, behavioural churn, authority demand splitting, Cork demand, OSM demand, plotting, dashboards, or a large experiment framework.
