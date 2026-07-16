# M8 de Souza Figure 5 Preparation v1

Status: UC evidence generated; published numerical comparison deliberately
withheld.

Follow-up: the first observational comparison for Figure 5(a), DT=1 is now
documented in `docs/validation/m8_desouza_figure5a_dt1_comparison_v1.md`. The
preparation bundle remains unchanged as the pre-comparison evidence baseline.

## Source Boundary

The input transcription uses only the text of Section 4.1 and Equation 13 of
de Souza et al., *A Mesoscopic Link-Transmission-Model Able to Track Individual
Vehicles* (preprint dated 4 June 2025). The source PDF has SHA-256
`ae898b06f336e78b17d53edab7326cd1346863ff3328cdf86952886852a0c903`.

Figure 5 curves, plotted values, errors, and numerical outcomes were not
inspected, digitised, encoded, or used as implementation targets.

The machine-readable register is
`docs/validation/m8_desouza_figure5_preparation_v1.json`.

## Declared Inputs

| Quantity | Paper declaration |
| --- | --- |
| topology | two successive links, L1 upstream of lower-capacity L2 |
| length | L1 = L2 = 150 m |
| free-flow speed | V1 = V2 = 30 m/s |
| backward/shock-wave speed | W1 = W2 = 6 m/s |
| jam density | K1 = 0.2 veh/m; K2 = 0.1 veh/m |
| capacity | C1 = 1.0 veh/s; C2 = 0.5 veh/s |
| upstream demand | 1.0 veh/s for t <= 50 s; 0.2 veh/s for 50 s < t <= 150 s |
| discrete timesteps | 1 s, 3 s, and 6 s |
| continuous reference timestep | 1 s; recorded as reference metadata only and not run or compared here |

The relevant paper-wide modelling declarations are a triangular fundamental
diagram with `C=K*V*W/(V+W)`, integer node flows in the proposed model, FIFO
vehicle association, the one-to-one `min(demand,supply)` node rule, and the CFL
condition `max(V,W)*dt <= L`.

## Derived Quantities

- The declared triangular-FD parameters reproduce 1.0 and 0.5 veh/s.
- Under the explicit one-lane UC metadata mapping, L1 and L2 storage are 30 and
  15 unit packets.
- Integrated demand through 150 s is 70 vehicles.
- Free-flow travel time is 5 s and backward-wave travel time is 25 s on each
  link.
- UC's current positive ceiling-rounded lags are `(5,25)`, `(2,9)`, and `(1,5)`
  ticks for 1 s, 3 s, and 6 s respectively.
- A 150 s observation boundary is used because that is the end of the declared
  demand support. The paper does not explicitly declare a simulation stop rule.
- The declared 6 s timestep violates the paper's stated CFL condition because
  `30 m/s * 6 s > 150 m`. UC still runs it unchanged and preserves the static
  physical-ineligibility output.

## Explicit Implementation Assumptions

- one UC lane per link;
- empty links before the first departure;
- fixed route `L1 -> L2` for every packet;
- a free terminal sink after L2 under current UC completion semantics;
- integrated demand is floored at tick endpoints and newly resolved unit
  packets are scheduled at that endpoint tick;
- current UC ceiling-rounded positive travel lags, FIFO, movement allocation,
  fractional carry, and same-tick event ordering are used unchanged;
- execution stops at the bounded 150 s observation boundary.

## Unknown or Ambiguous

The paper does not explicitly declare lane count, initial occupancy or packet
placement, downstream sink behaviour, a route rule beyond the unique two-link
topology, departure packetisation, tick-boundary ordering, tie-breaking, or a
simulation stop/clearance rule. Published outputs and tolerances remain blocked
by policy for this preparation slice.

## Implemented Case Family

- `M8-PUB-DSOUZA-FIG5-DT1` - 1 s, 150 ticks;
- `M8-PUB-DSOUZA-FIG5-DT3` - 3 s, 50 ticks;
- `M8-PUB-DSOUZA-FIG5-DT6` - 6 s, 25 ticks.

All three use `parity_ltm_v1`. No loading-kernel file or simulator behaviour is
changed by the case adapter.

## Exported Evidence

Each persisted baseline contains:

- the versioned case contract;
- canonical packet lifecycle events;
- every-tick replay states/checkpoints and queue membership;
- topology, packet metadata, and provenance/configuration snapshots;
- cumulative inflow, cumulative outflow, and storage for both links;
- canonical boundary-queue entries, exits, and occupancy;
- per-link sending/receiving integer budgets and fractional carry;
- one-to-one movement allocation requests, approvals, rejections, receiving
  supply, and resulting canonical event sequences;
- event-derived vacancy-wave presentation windows based on actual L2 exits and
  UC's declared backward-wave lag;
- conservation, event-cache consistency, cumulative-count consistency, exact
  deterministic rerun, and static physical-eligibility outputs.

The generated bounded baselines contain the following UC observations. These
are an inventory of exported evidence, not a comparison or interpretation.

| dt | packets | completed at 150 s | canonical events | final L1 storage | final L2 storage | final canonical boundary queue | internal validation |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| 1 s | 70 | 68 | 540 | 1 | 1 | 0 | core checks and physical eligibility passed; paper comparison not run |
| 3 s | 70 | 62 | 514 | 6 | 2 | 2 | core checks and physical eligibility passed; paper comparison not run |
| 6 s | 70 | 60 | 500 | 10 | 0 | 6 | core checks passed; static physical eligibility failed; paper comparison not run |

The Validation Workbench consumes the same generic replay, packet, link, node,
movement, queue, chart, and inspector paths as the analytical library. The Lab
Bench starter exposes the declared inputs and explicit demand conversion but no
published output.

## Claim Boundary

This slice supports only the claim that UC executed the declared physical
scenario plus the listed assumptions and exported internally checked evidence.
It makes no claim of agreement or disagreement with Figure 5 and computes no
paper-referenced error.
