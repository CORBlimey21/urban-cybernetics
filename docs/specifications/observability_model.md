**Status:** specification.
**Scope:** defines the pipeline from physical truth to authority-visible information: measurement, observation frames, publication, receipt, delay, aggregation, noise, and the immutability invariant.
**Non-scope:** does not define routing authority decision logic, behavioural update functions, or governance intervention mechanisms.

---

### The Observability Pipeline

The framework treats information as a first-class system variable. Routing authorities do not see physical truth directly. They see a pipeline of sampled, aggregated, delayed, and potentially noisy artifacts derived from physical truth. This pipeline has five stages.

**Physical truth.** The loading engine's canonical physical records: packet lifecycle events, cumulative boundary counts, link storage state, queue state.

**Measurement.** The observability layer samples physical truth at a sensor's scheduled sampling time, applying the sensor's declared aggregation window and counting basis. The result is a raw measurement: a count or aggregate over a defined window and boundary, with a declared measurement_time.

**Observation frame.** The measurement is processed into a structured artifact: noise is applied if declared, metadata is attached, and the frame is sealed. Once sealed, the frame is immutable. The frame is published to the observation buffer at publication_time.

**Receipt.** A routing authority retrieves a frame from the observation buffer. The authority records a receipt event: (authority_id, frame_id, receipt_time). The receipt event is owned by the routing authority, not the observation frame.

**Belief.** The routing authority may process one or more frames into an internal belief state: an estimate of current or future network conditions used to inform routing decisions. Belief state is owned by the routing authority and is not part of the observability model.

The observability model owns stages one through three. Stages four and five belong to routing_authorities.md.

---

### Sensor Configuration

Each sensor has a declared configuration that is part of the experiment run record. Sensor configuration fields:

- sensor_id (canonical, stable within a run)
- observed entity: canonical link ID plus boundary direction (entry or exit), or canonical node ID
- sampling_interval: how often the sensor produces a measurement, in simulation ticks
- aggregation_window: the time window over which counts are accumulated, in simulation ticks
- publication_delay: ticks between measurement_time and publication_time
- noise_model: type (none, additive Gaussian, rounding, dropout) and parameters
- noise_seed: seed registered in the run's seed registry

All sensor configurations are immutable after the run begins. A different sensor configuration produces a different run.

---

### What Is Observed

**Primary observable: boundary crossing count.** The number of packets that crossed a specific link boundary (entry or exit) during a declared aggregation window ending at measurement_time. This is the fundamental observable from which all other link-level quantities are derived.

**Secondary observable: node transfer count.** The number of packets transferred from a specific incoming link to a specific outgoing link at a node during a declared aggregation window.

**Derived observables.** Queue length, occupancy, density, speed, and travel time are derived from primary observables or from combinations of boundary counts across multiple sensors. They may be included in observation frames as pre-computed derived fields, but each derived field must declare its derivation formula and the primary observable inputs it depends on.

Speeds, travel times, and densities must never appear in an observation frame without declaring their derivation basis. An observation frame that reports "average link speed" without specifying the counting method and boundary pair is a specification error under P12.

---

### Observation Frame Structure

Every observation frame must carry the following fields.

**Identity and provenance:** frame_id (stable, unique within a run), sensor_id, run_id.

**Temporal:** measurement_time (end of aggregation window; primary scientific timestamp), aggregation_window (duration in ticks), publication_time (when the frame was sealed and published).

**Observed entity:** canonical link ID and boundary direction, or canonical node ID.

**Primary count:** boundary crossing count over the aggregation window.

**Noise metadata:** noise_model type, noise parameters, noise_seed reference. If no noise was applied, declared as such.

**Derived fields (optional):** any pre-computed derived observable, with derivation formula and input frame IDs declared inline.

Receipt_time is not a field on the observation frame. It is recorded by the consuming authority as a separate receipt event referencing the frame_id.

---

### Immutability Invariant

An observation frame is immutable from the moment it is published. This is P4 of core_principles.md and it is absolute.

If a sensor error, noise calculation bug, or data quality issue is discovered after publication, the response is: create a new corrected frame with a new frame_id and a provenance reference to the erroneous original; annotate the original as superseded in the observation archive. The original frame is preserved. No system may retroactively alter a published frame.

The practical consequence is that routing authority decision logs can always be reconstructed: a decision references a frame_id, and that frame is always available in its original form.

---

### Delayed Observability

Information delay is a first-class feature of the framework, not an implementation nuisance. The effective delay experienced by a routing authority is the sum of:

- the sensor's aggregation window (the observation covers events up to measurement_time, not the present)
- the sensor's publication_delay (ticks between measurement_time and publication_time)
- the authority's receipt delay (ticks between publication_time and receipt_time, declared per authority in routing_authorities.md)

The minimum possible effective delay in the base model is one full timestep phase cycle, as established in timestep_semantics.md.

Delayed observation is not an error condition. An authority operating on a frame from several ticks ago is behaving correctly if that is the frame available to it. The scientific question is what routing decisions such an authority produces under that delay, and how those decisions interact with the decisions of other authorities operating under different delays.

---

### Authority Access Policy

[OPEN] Which observation frames is each authority type permitted to receive? Options include: symmetric access (all authorities see the same sensor outputs), asymmetric access (governance controls which sensors publish to which authorities), and strategic withholding (governance delays or suppresses certain frames as a modelled intervention). The base model should declare a default access policy. → governance_model.md, routing_authorities.md.

---

### Audit Trail

The complete audit trail from a physical event to an authority decision is:

1. Packet crosses boundary: loading engine appends boundary crossing event to packet event log with physical_timestamp.
2. Sensor samples: observability layer reads cumulative count from loading engine at measurement_time; computes aggregated count over aggregation_window; applies noise; seals frame with frame_id, measurement_time, publication_time.
3. Frame enters buffer: available for receipt from publication_time onward.
4. Authority receives: authority appends receipt event (authority_id, frame_id, receipt_time) to its own log.
5. Authority decides: authority appends decision event (decision_id, authority_id, frame_ids_used, route_assignments, decision_time) to its decision log.

Every step is append-only. Given a decision_id, the complete causal chain back to the physical boundary crossing event is recoverable from the run artifact.

---

### Open Questions

- **Observation of governance state.** Can authorities observe current governance state (signal phase, closure status) directly, or only through its effects on measured boundary counts? If direct governance observation is permitted, it requires a separate sensor type and access policy. → governance_model.md.
- **Incident and anomaly detection.** Future extensions may include sensors that report incidents, queue overflow flags, or compliance estimates rather than raw counts. These require new observable types with their own derivation bases. → to be declared as extensions.
- **Noise model calibration.** What real-world noise characteristics should the base noise model reflect? This is a scientific question about sensor fidelity, not an architectural one, but it must be answered before any empirical comparison against count data is attempted. → benchmark_policy.md.

---
