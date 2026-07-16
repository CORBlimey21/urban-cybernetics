# M8 de Souza Figure 7 Preparation v1

Status: declared source inputs externally checked; UC observables generated;
Figure 7(a) DT1 observational comparison complete; DT3 reference values pending.

Follow-up: the DT1 numerical comparison is documented in
`m8_desouza_figure7a_dt1_comparison_v1.md`. This preparation remains the
pre-comparison input and UC-evidence baseline.

## Source and claim boundary

Section 4.2, Equation 14, and the Figure 7 caption of de Souza et al., *A
Mesoscopic Link-Transmission-Model Able to Track Individual Vehicles*, declare
the diverge parameters, deterministic route order, timesteps, and plotted
quantities used here. No plotted ordinate was digitised or used as a target.

This fixture therefore validates the source transcription and UC's internal
invariants. It does not yet claim numerical agreement with Figure 7. When
reference values are supplied, comparison begins with a read-only
first-divergence audit; parameters and the frozen kernel are not tuned.

## Exact fixture

| Quantity | Declaration |
| --- | --- |
| topology | one 150 m upstream link diverging to two 150 m downstream links |
| free-flow speed | 30 m/s on all links |
| backward-wave speed | 6 m/s on all links |
| jam density | upstream 0.2 veh/m; downstream 0.1 veh/m each |
| derived capacity | upstream 1.0 veh/s; downstream 0.5 veh/s each |
| packet routes | repeating `L1→L2, L1→L2, L1→L2, L1→L3` |
| demand | 0.8 veh/s for `t<50 s`; 0.4 veh/s for `50<t<=120 s` |
| timesteps | 1 s and 3 s |
| bounded demand | 68 unit vehicles through 120 s |

The source's “downstream link 1” and “downstream link 2” are represented as UC
links `L2` and `L3`; this avoids colliding with upstream UC link `L1`.

Explicit implementation assumptions are one lane per link, empty initial
links, free terminal sinks, tick-end admission of the floored integrated
demand, and a bounded observation ending at 120 s. Strict FIFO, packet
identity, event ordering, capacity credit, and travel-lag conventions are the
existing `parity_ltm_v1` semantics.

## Figure 7 observables

Both runs export exactly:

- upstream cumulative outflow;
- cumulative inflow to each downstream link;
- upstream outflow per tick;
- inflow per tick to each downstream link.

The cumulative and per-tick quantities are folded from canonical link events.
At every tick, upstream cumulative outflow equals the sum of downstream
cumulative inflows. Focused tests also require exact 3:1 route identity,
strict-FIFO transfer order, conservation, event-cache/count consistency, and
exact deterministic replay.

## Artifacts

- machine-readable declaration: `m8_desouza_figure7_preparation_v1.json`;
- later-comparison manifest:
  `data/validation/desouza_figure7_comparison_manifest_v1.json`;
- long-form UC observations:
  `data/validation/desouza_figure7_uc_observables_v1.csv`;
- replay cases/runs under `fixtures/visualisation/validation/`;
- deterministic exporter: `scripts/export_desouza_figure7_observables.py`.

The current bounded observations are 66 upstream transfers at 1 s (50 to L2,
16 to L3) and 65 at 3 s (49 to L2, 16 to L3). These are frozen UC outputs, not
paper-reference values or agreement findings.
