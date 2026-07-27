# Paper 1 explicit lane-group FIFO extension v1

## Version boundary

`paper1-lane-group-extension-v1` is an opt-in allocator and queue-index shell
above `loading-kernel-v1.0.1`. The allocator is injected through the frozen
`node_transfer_policy` interface. `LaneGroupLoadingEngine` subclasses the
frozen engine only to validate an explicit-group queue head and to fold the
upstream queue membership index when a different group bypasses; physical
events, link state, and lifecycle mutation still use the frozen engine
methods. The source files recorded by the v1.0.1 freeze manifest are unchanged,
and disabling the extension constructs the original engine and Stage 2
allocator without any new state or branch.

The old `JunctionSpec.lane_group_ids`,
`MovementSpec.lane_group_ids`, and
`movement_lane_group_mappings` retain their frozen meaning: conjunctive,
junction-local, per-tick service resources. The extension does not reinterpret
them. Explicit mode rejects a configured junction that also uses those legacy
fields, preventing an ambiguous mixed interpretation.

## Scientific representation

The extension is a mesoscopic approach service and queue-partition model. It
does not represent lane geometry, continuous lateral position, gap acceptance,
or lane-changing.

An `ExplicitLaneGroup` declares:

- a stable ID, scoped to one junction;
- the junction and one incoming link to which it is local;
- one or more allowed movement IDs from that incoming link;
- a positive integer service capacity per loading tick; and
- provenance containing source, confidence, declared/inferred status, optional
  fallback reason, and compiler version.

The containing `LaneGroupExtensionConfig` carries
`explicit-lane-groups-v1`, the extension version, the queue representation
mode, and the retained-assignment policy. Its deterministic hash makes the
extension topology/configuration artefact provenance-visible without changing
the frozen canonical topology hash.

No storage or queue-share constraint is included in v1. Link storage remains
the physical storage authority. Adding a second storage ledger would require a
defensible allocation rule and additional conservation semantics; neither is
needed for the service-partition experiment.

## Assignment lifecycle

Assignment occurs when a packet first appears in the frozen engine's transfer
candidate set: the first tick on which it is service-eligible at the downstream
boundary of its current upstream link.

This point was selected because it is the least invasive coherent point:

- route intent and the requested movement are already known;
- upstream sending eligibility has already been computed by the frozen LTM;
- no lane state is invented while the packet travels through the link; and
- a blocked packet remains physically stored on, and attributable to, its
  upstream link.

For a movement with alternative groups, the allocator selects the compatible
group with the shortest effective queue among currently eligible assigned
packets. Ties use declaration order and then stable ID. Candidate processing
uses eligibility tick, eligibility sequence, and packet ID. The assignment is
retained while the packet waits. V1 has no reassignment or dynamic balancing.

## FIFO and service semantics

The ablation switch supports:

1. `shared_link_fifo`: frozen strict upstream-link FIFO;
2. `movement_partial_fifo`: the frozen partial-coupling rule selected without
   mutating `JunctionSpec`; and
3. `explicit_lane_group_fifo`: FIFO independently within each assigned group.

In explicit mode, an unapproved head blocks later assigned packets in the same
group. It does not block a packet assigned to another group. A shared group
therefore reproduces shared blocking, while separated groups permit independent
service. This remains true when both packets have emitted queue-entry events:
the extension validates the selected packet as the head of its assigned group,
removes its membership from the upstream-link queue index, and leaves other
group queues physically stored on the same upstream link.

Every approval remains subject to frozen upstream sending and downstream
receiving, movement declaration, signal and governance gates, declared merge
weights, packet indivisibility, and conflict-resource capacity. Explicit
lane-group capacity is consumed only for the selected alternative group.
Conflict resources remain separate conjunctive junction constraints and can
recouple movements served by different lane groups.

Lane-group assignments and allocation traces are diagnostic allocator state.
They are not appended to the physical event log. Queue entry and exit remain
the frozen packet lifecycle events, and a waiting packet remains on its
upstream link.

## Fixtures and evidence

The canonical fixture artefact is
`fixtures/lane_groups/v1/canonical_lane_group_cases_v1.json`. It declares:

- shared single group;
- separated groups;
- partially shared/alternative service;
- signal interaction;
- downstream blockage; and
- conflict coupling.

The focused test also checks schema failures, deterministic alternative
assignment, retained assignment, per-group FIFO, queue entry/exit order, exact
rerun equality, conservation, event/cache consistency, and cumulative-count
consistency.

`scripts/run_lane_group_ablation.py` runs the same topology, demand, and
controls under all three modes. Its structured output includes throughput,
service-eligible queue-delay packet-ticks, distinct blocked packets,
per-movement service, completion tick, event count, measured runtime,
conservation, replay, event/cache consistency, cumulative-count consistency,
and terminal packet outcomes.

## Limitations

- Groups partition boundary service and FIFO, not physical lane occupancy along
  the link.
- There is no lane-changing, reassignment, continuous balancing, or lateral
  coordinate.
- Service capacity is an integer per loading tick.
- Link storage is shared; no lane-group storage share is claimed.
- Effective queue length considers service-eligible packets at that junction,
  not a spatial lane queue.
- The retained assignment map is allocator evidence, not canonical physical
  truth.
- Provenance fields are ready for a future compiler, but no OSM compiler or
  inference algorithm is implemented here.

## Claims safe for Paper 1 Section 3.4

The implementation supports the following narrow claims:

1. The frozen packetised LTM can be extended, without modifying its physical
   event or count semantics, by a deterministic mesoscopic approach
   queue-partition allocator.
2. Declared lane groups can represent shared, separated, and alternative
   movement service capacity at an incoming link.
3. FIFO blocking is enforced within an assigned group, while packets assigned
   to another group can proceed when their own downstream, signal, governance,
   conflict, merge, and service constraints are feasible.
4. Alternative-group assignment is reproducible, occurs at first service
   eligibility, and is retained thereafter in v1.
5. Controlled fixtures and a three-mode ablation isolate differences among
   strict shared-link FIFO, the existing movement-partial rule, and explicit
   lane-group FIFO while preserving packet indivisibility and all kernel
   integrity gates.

These results do not establish microscopic lane realism, lane-changing
validity, empirical lane-use calibration, or an OSM-derived lane model.
