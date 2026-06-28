# Parity Torture Verification Package

This package is an adversarial verification layer for the current parity kernel,
not a new loading mechanic or an M7/M8 feature surface.

## Scope

The tests live under `tests/parity_torture/` and are organized by intent:

- `test_regression_scenarios.py` contains deterministic synthetic cases for link,
  queue, spillback, and minimal node-family behaviour.
- `test_invariants.py` runs fixed-seed property-style checks over many randomized
  small cases.
- `test_synthetic_stress.py` searches small randomized topologies for impossible
  states such as duplicate packets, terminal queued packets, invalid storage, or
  unexplained lack of progress.
- `test_sioux_falls_regression.py` uses Sioux Falls only as a regression fixture:
  deterministic replay, conservation, cumulative-count consistency, queue sanity,
  and absence of impossible states.
- `test_commodity_parity.py` covers M7 unit-packet commodity evidence, route
  disaggregation, packet ordinal correspondence, route travel-time curves,
  high-commodity fixtures, and legacy-profile non-evidence.
- `helpers.py` contains the shared fixtures, generators, and invariant assertions.

## Extension Rules

Future parity milestones should extend this package rather than scattering
adversarial tests through unrelated files. Add new deterministic fixtures when a
bug is found, widen the randomized generators only when the public parity API can
represent the new behaviour, and keep Sioux Falls claims limited to regression
bookkeeping unless a separate validation artifact supports stronger conclusions.

The package intentionally avoids Hypothesis or network-scale generation so every
failure is reproducible from a seed and can be reduced into a deterministic
regression fixture.
