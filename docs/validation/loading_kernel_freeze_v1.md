# Base loading-kernel freeze v1

Status: frozen after the canonical loading-kernel validation matrix passes.

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

## External evidence still pending

One further de Souza merge or diverge benchmark is reserved in the external
validation matrix. It is blocked until the exact figure, declared input text,
and digitised numerical data are supplied. No parameters, routes, priorities,
FIFO convention, or expected values will be invented to fill that gap.
