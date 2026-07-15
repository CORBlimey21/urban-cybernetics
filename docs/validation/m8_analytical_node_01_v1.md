# M8 Analytical NODE-01 v1

Status: independently authored one-upstream/one-downstream analytical family,
executable in the Validation Workbench. This is internal analytical evidence,
not a published numerical reproduction.

## Independent Oracle

For one admissible movement and unit packets, the expected transfer count at
each tick is authored from:

```text
F(t) = min(D(t), S(t))
D(t+1) = D(t) - F(t)
Q(t) = D(t) - F(t)
```

No allocator helper constructs expected values. Python reads candidates,
approvals, rejections, and residual receiving slots from immutable allocation
traces. It folds L2 entries and boundary queue state from canonical events,
then builds expected, observed, and difference series. All comparisons have
zero-packet and zero-tick tolerance because the oracle is exact integer
arithmetic.

## Cases

| Case | Initial demand | Supply sequence | Expected approvals | Claim |
| --- | ---: | --- | --- | --- |
| M8-NODE-01-DEMAND | 1 | `(3,3)` | `(1,0)` | demand-limited transfer |
| M8-NODE-01-SUPPLY | 3 | `(1,1,1)` | `(1,1,1)` | supply-limited transfer and queue clearance |
| M8-NODE-01-EQUAL | 2 | `(2,2)` | `(2,0)` | equality boundary |
| M8-NODE-01-ZERO-DEMAND | 0 | `(3)` | `(0)` | no phantom movement |
| M8-NODE-01-ZERO-SUPPLY | 2 | `(0,0)` | `(0,0)` | complete downstream blockage |
| M8-NODE-01-REOPEN | 2 | `(0,2,2)` | `(0,2,0)` | release when receiving reopens |
| M8-NODE-01-FRACTIONAL | 6 | `(1,2,1,2)` | `(1,2,1,2)` | fractional receiving carry |

Without changing the frozen v1 schema, each case records its scientific claim
in `short_explanation` and `safe_claim`, its physical mechanism in
`why_it_matters`, and its assumptions in `initial_state_reference` and
`reproducibility_notes`. Expected physical sequence, numerical outputs, exact
tolerances and justification, provenance, and limits are also authored. Movement
approvals are engine-exported evidence; transfer timing and queue state remain
canonical or event-derived evidence. No replay mechanics were added.

## Preparation for Published Reproduction

NODE-01 isolates the elementary `min(demand, supply)` boundary used by the
planned de Souza lane-drop reproduction. It does not validate merge priority,
diverge FIFO, multi-input/multi-output allocation, or any published figure.
