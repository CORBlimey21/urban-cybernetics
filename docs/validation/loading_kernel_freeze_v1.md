# Base loading-kernel freeze v1

Status: superseded on 2026-07-16 by the canonical, versioned contract at
`docs/architecture/loading_kernel_freeze_contract_v1.md`. This file preserves
the original M8 freeze decision and records its completed external-evidence
closure.

## Frozen boundary

The following Urban Cybernetics loading semantics are validated and frozen:

- the base unit-packet LTM loading kernel;
- sending and receiving, including bounded fractional credit;
- finite storage and backward-wave spillback;
- strict FIFO and declared partial-FIFO movement handling;
- one-to-one, merge, diverge, and general movement allocation;
- packet identity and lifecycle event ordering;
- cumulative boundary counts, storage identities, conservation, and exact
  deterministic replay.

Frozen means that these behaviours are the compatibility baseline for future
work. It does not mean that every possible network, node model, discretisation,
or external implementation has been validated.

## Outside this milestone

This freeze does not validate OSM import correctness, large-network
performance, routing-policy validity, behavioural models, observability
experiments, governance mechanisms, optimisation, or future cybernetic
extensions. Each requires focused validation when introduced and must not
silently alter the frozen loading kernel.

## Change-control rule

Any future modification to a validated loading semantic requires all four of
the following:

1. an explicit technical or scientific reason;
2. focused regression evidence for the affected mechanism;
3. a rerun of the complete loading-kernel validation matrix;
4. documentation of every intentional change to a prior result, fixture,
   comparison metric, or safe claim.

A feature outside the frozen boundary must integrate through declared public
interfaces. It must not reinterpret canonical events, packet identity,
ordering, FIFO, counts, storage, or conservation without following this rule.

## External evidence closure

This original freeze preceded the completed de Souza comparisons. Figures 5,
7, 8, 9(a–c), and 9(d–f) now form the accepted observational evidence set.
Figure 9(d–f) explicitly resolves the paper inconsistency as `alpha_1=0.75`,
`x=[0,0,0,1]`. Remaining unselected external matrix groups stay deferred and
do not prevent the named base-kernel v1 boundary.
