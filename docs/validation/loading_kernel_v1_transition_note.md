# Loading kernel v1 milestone and transition note

Date: 2026-07-16

Status: base loading-kernel validation phase complete.

The `parity_ltm_v1` base loading kernel is frozen as
`loading-kernel-v1.0.0`. Its current external evidence set comprises de Souza
Figure 5 lane drop, Figure 7 deterministic route-encoded diverge, Figure 8
seeded stochastic diverge ensemble, Figure 9(a–c) equal-priority merge, and
Figure 9(d–f) asymmetric-priority merge with `alpha_1=0.75` and
`x=[0,0,0,1]`.

This milestone closes the base-kernel validation phase; it does not assert
full Sioux Falls parity, empirical city-scale validity, calibrated realism,
advanced traffic mechanics, or production performance. Observational
literature discrepancies and their classifications remain part of the
evidence rather than being tuned away.

Primary subsequent work moves to network compilation, performance engineering,
experiment orchestration, and closed-loop cybernetic experiments. Those layers
may develop independently while they preserve the frozen canonical loading
semantics. Any future kernel-semantic change requires explicit reopening,
first-divergence audit, isolated implementation, affected evidence regeneration,
external revalidation, full regression, claim review, and a new freeze version.

See `docs/architecture/loading_kernel_freeze_contract_v1.md` for the canonical
boundary and `docs/architecture/loading_kernel_capability_statement_v1.md` for
safe and deferred claims.
