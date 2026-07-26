# Loading kernel v1.0.1 hardening evidence

Date: 2026-07-26

Status: exact non-semantic hardening closure.

Implementation commit:
`1fd8884c69c82e6d53ed1b4801a9d1672f38e6ef`.

Baseline commit:
`7ca4f4b5f7e6dd4a42a4f41cf6dd7751d5e03390`.

## Scope

This patch hardens the frozen unit-packet kernel without changing validated
traffic-flow semantics. It adds:

- complete pre-execution validation for ordinary and queued link transfers,
  with reuse of the prevalidated upstream membership index during
  `LINK_EXIT`;
- a complete active-packet cancellation operation;
- stricter event-fold validation for completion and cancellation;
- an explicit consolidated canonical-validation report with optional exact
  deterministic rerun;
- focused transfer, completion, cancellation, spatial-uniqueness, validation,
  and exact-rerun regressions.

The canonical event types are unchanged. Ordinary transfer remains
`LINK_EXIT`, `LINK_ENTRY`; queued transfer remains `QUEUE_EXIT`, `LINK_EXIT`,
`LINK_ENTRY`; completion remains `LINK_EXIT`, `COMPLETED`. Cancellation uses
the existing events: `LINK_EXIT`, `CANCELLED` for in-transit packets and
`QUEUE_EXIT`, `LINK_EXIT`, `CANCELLED` for queued packets.

## Exact semantic comparison

Pre-change and hardened snapshots were captured outside the repository for the
task audit. The following durable evidence is exactly unchanged:

| Case | Event-log SHA-256 | Allocation-trace SHA-256 | Completed | Tick |
| --- | --- | --- | ---: | ---: |
| M8-COMP-NET-01 | `303ed012177ca54cee9e6969515c1f5f97320112fa146de5bb795af430a31de4` | not separately frozen | 8 | 10 |
| Figure 9 equal | `1adff762616503f666490d4aade1294c140aad63a9c2f41d87da4945898267e2` | `9214a21bb7d8e6ff5e4d4abe5327c4a18cfce9fec009f94e05955919536acea7` | 50 | 120 |
| Figure 9 asymmetric | `479b6999ef6a74b9ee8be495793817cb5f09cb1b5d84cbb807935d620c92665a` | `c144ddc606ac5da3e17890d96dbd6a4203df7dfd106f2a375652b00bd3c44b9c` | 50 | 120 |

Packet-outcome hashes, conservation summaries, event/cache results,
cumulative-count consistency reports, terminal ticks, and pending-demand
counts are also exactly equal. The four frozen comparison-summary files retain
their prior SHA-256 values. Consequently all Figure 8 RMSE values, Figure 9
RMSE values, endpoints, queue maxima, and validation gates are byte-identical.

## Runtime comparison

Repeated runs used an archived copy of the baseline commit and the same Python
3.13.3 environment. The 10-tick composition median was approximately
0.818 ms before and 0.837 ms after hardening. The complete 100-seed Figure 8
ensemble median was approximately 1.282 s before and 1.304 s after hardening.
The observed change is about 19 microseconds for the small case and 1.7% for
the medium case. This is the bounded cost of transfer prevalidation; the
consolidated validation and exact rerun paths are explicit and are never
invoked by `LoadingEngine.step()`.

## Cancellation contract and limitations

`LoadingEngine.cancel_packet(packet_id)` accepts only instantiated active
packets. Pending demand remains pre-packet state. Completed and already
cancelled packets are rejected without event or state changes. Cancellation
removes live queue and link membership before emitting `CANCELLED`; cancelled
packets remain in conservation.

The event schema still has no cancellation-reason field. Cancellation reason
codes remain a deferred provenance extension. Weighted packets, splitting,
merging, dynamic rerouting, and automatic per-tick full validation remain
outside the frozen base-kernel contract.

## Closure commands

- `python scripts/verify_loading_kernel_freeze.py`: five regeneration
  commands, 64 recorded-file hashes, four comparison summaries, 65 text
  artifacts, and 101 focused tests passed in 4.85 seconds wall time.
- `python -m pytest -q`: 693 tests and 88 subtests passed in 16.67 seconds,
  with the one existing FastAPI `TestClient` deprecation warning.
- `git diff --check`: passed.
