**Status:** specification.
**Scope:** records the framework's testable invariants. Each invariant is stated as a falsifiable claim and mapped to the test scenario that verifies it. These invariants must pass before substantive simulator implementation begins.
**Non-scope:** does not define implementation methods for satisfying the invariants. Invariants constrain implementations; they do not specify them.

---

### Purpose

An invariant is a claim that must be true in every compliant implementation under every valid input. If an invariant is violated, the implementation is wrong, not the invariant. Invariants are not aspirational targets or best-practice guidelines. They are hard requirements.

Each invariant below is stated as a claim, paired with a minimal synthetic test scenario sufficient to falsify it. The test scenarios deliberately avoid OSM, OSMnx, and geospatial dependencies. They require only a small synthetic graph (one to five links, two to six nodes) and a small demand manifest.

---

### I1. Packet Identity Stability

**Claim.** A packet's canonical ID does not change at any lifecycle event: link entry, link exit, node transfer, queue entry, queue exit, reroute, completion, or cancellation.

**Test.** Instantiate one packet on a two-link synthetic network. Subject it to a queue event, a reroute event, and completion. Assert that the packet ID in every lifecycle event log entry is identical.

---

### I2. Demand-to-Packet Instantiation Uniqueness

**Claim.** Each demand declaration produces exactly one packet. No demand declaration produces zero packets or more than one packet in the base model.

**Test.** Commit a manifest with ten demand declarations. Run to completion. Assert that the conservation ledger contains exactly ten packets and that each packet references a distinct demand declaration.

---

### I3. Lifecycle Monotonicity

**Claim.** A packet's lifecycle state transitions are monotonic: it never returns to an earlier state. A completed or cancelled packet does not re-enter in-transit or queued state. The only permitted cycle is between in-transit and queued during active traversal.

**Test.** Run a synthetic network with forced queuing and forced rerouting. Assert that no packet event log contains a transition from completed or cancelled back to any active state, and that no packet enters the in-transit state after its completion or cancellation event.

---

### I4. Single-Link Conservation

**Claim.** On a single-link network, cumulative boundary exits never exceed cumulative boundary entries. After all packets have cleared the link, exits equal entries.

**Test.** Single-link network, five packets, no governance interventions. Run to completion. Assert exits ≤ entries at all ticks and exits = entries at final tick.

---

### I5. FIFO on a Homogeneous Link

**Claim.** Two packets entering the same link in order, with identical cohort class and no passing permitted, exit the link in the same order.

**Test.** Single-link network, two packets of identical class, packet A departs before packet B. Assert that packet A's link exit event timestamp is earlier than packet B's link exit event timestamp.

---

### I6. Downstream Receiving Constraint

**Claim.** In a two-link chain, downstream capacity constrains upstream releases. No packet exits the first link into the second link when the second link's receiving capacity is zero. No packets are lost; excess packets queue on the first link.

**Test.** Two-link network, downstream capacity set to zero for a declared interval. Send five packets. Assert that no packet crosses the intermediate boundary during the zero-capacity interval, that all five packets appear in queue state on the first link during that interval, and that all five complete after the interval ends.

---

### I7. Merge Node Conservation

**Claim.** At a merge node with two incoming links and one outgoing link, the total number of packets transferred to the outgoing link plus the total number of packets held in queue on incoming links equals the total number of packets that arrived at the node from all incoming links since the last accounting checkpoint.

**Test.** Two-link merge onto one outgoing link, downstream capacity constrained to create queuing on at least one incoming link. Run for ten ticks. Assert conservation at the node for every tick.

---

### I8. Diverge Node Route-Intent Preservation

**Claim.** At a diverge node with one incoming link and two outgoing links, every packet follows its declared route intent. The sum of packets assigned to outgoing links plus packets remaining queued on the incoming link equals the total packets that arrived at the node.

**Test.** One-link diverge, packets with declared route intent split across both outgoing links. Assert that each packet exits on the outgoing link declared in its route intent, and that node conservation holds at every tick.

---

### I9. Whole-Network Conservation

**Claim.** At all times during a run: total instantiated = in-flight + completed + cancelled + unresolved. At clean termination: in-flight = 0 and unresolved = 0.

**Test.** Five-link synthetic network, twenty packets, mixed completion and explicit cancellation events. Assert the ledger equation at every tick and assert clean termination conditions.

---

### I10. Observation Frame Immutability

**Claim.** A published observation frame cannot be altered. Any frame retrieved from the observation buffer at any tick after its publication_time is byte-identical to the frame at publication_time.

**Test.** Publish one observation frame. Modify the underlying physical state (advance the simulation by five ticks). Retrieve the frame. Assert that all fields of the retrieved frame are identical to the originally published frame.

---

### I11. Delayed Observation Correctness

**Claim.** An authority with a declared receipt delay of D ticks, requesting the most recent available frame at tick k, receives a frame whose publication_time ≤ t_k − D·Δt. The authority does not receive a frame published after that threshold.

**Test.** Declare one authority with receipt delay of three ticks. Publish frames at ticks 1, 2, 3, 4, 5. At tick 5, assert that the authority's most recent available frame has publication_time ≤ t_2.

---

### I12. Benchmark Quarantine

**Claim.** Importing any canonical dynamic package (loading, packets, routing, observability, governance, behaviour, validation) does not transitively import any module under legacy/, bpr_reference/, or static_assignment.

**Test.** For each canonical package, assert that its full transitive import closure contains no module path containing the strings `legacy`, `bpr_reference`, or `static_assignment`.

---

### I13. No Ambiguous Volume Output

**Claim.** No canonical output artifact contains a field named `volume`, `flow`, `occupancy`, `travel_time`, `cost`, or `delay` without accompanying fields declaring aggregation_window, boundary_direction, counting_basis, and units.

**Test.** Run any synthetic experiment. Parse all output artifacts. Assert that none of the listed field names appear without all four qualifier fields present in the same record.

---

### I14. Topology Immutability During Run

**Claim.** The topology hash computed at run start equals the topology hash computed at run end.

**Test.** Run any synthetic experiment including governance interventions (link closure, signal retiming). At run end, recompute the topology hash from the topology record. Assert equality with the hash recorded in the run artifact.

---

### I15. Observation Frame Timestamp Ordering

**Claim.** For every published observation frame, measurement_time ≤ publication_time. Receipt_time (recorded by authority) ≥ publication_time.

**Test.** Publish five frames with varying publication delays and authority receipt delays. Assert the ordering invariant on all frame and receipt records.

---
