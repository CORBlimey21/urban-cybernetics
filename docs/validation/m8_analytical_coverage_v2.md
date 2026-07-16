# M8 Analytical Coverage v2

Status: historical readiness report for the pre-publication link and NODE-01
analytical slice. The subsequent Figure 5 DT1 observational comparison and
base-kernel closure are documented in the canonical validation dossier.

## Before This Slice

| Elementary mechanism | Classification | Evidence |
| --- | --- | --- |
| finite free-flow translation | Validated analytically | M8-LINK-01 |
| capacity-limited pulse discharge and finite queue clearance | Validated analytically | M8-LINK-02 |
| one backward vacancy release from full storage | Validated analytically | M8-LINK-03 |
| sustained sub-capacity flow | Implemented but not independently validated | kernel/regression tests only |
| queue growth under continued excess demand | Implemented but not independently validated | kernel/regression tests only |
| repeated vacancy releases | Implemented but not independently validated | kernel/regression tests only |
| fractional sending/receiving carry | Implemented but not independently validated | kernel unit tests only |
| one-to-one node demand/supply arithmetic | Implemented but not independently validated | allocator unit tests only |

## After This Slice

| Elementary mechanism | Classification | Evidence or blocker |
| --- | --- | --- |
| free-flow pulse and sustained uncongested translation | Validated analytically | M8-LINK-01, M8-LINK-04 |
| saturated link discharge | Validated analytically | M8-LINK-02, M8-LINK-05 |
| queue formation, growth, and clearance | Validated analytically | M8-LINK-02, M8-LINK-05 |
| finite storage and single/repeated backward vacancy timing | Validated analytically | M8-LINK-03, M8-LINK-06 |
| fractional sending capacity over a multi-tick horizon | Validated analytically | M8-LINK-07 |
| one-to-one demand-limited, supply-limited, equal, and zero boundaries | Validated analytically | NODE-01 family |
| reopening after downstream blockage | Validated analytically | M8-NODE-01-REOPEN |
| fractional one-to-one receiving transfer | Validated analytically | M8-NODE-01-FRACTIONAL |
| triangular-FD parameter report and storage derivation | Implemented but not independently validated as a Workbench case | static physical-parameter tests exist |
| timestep invariance across two discretisations | Implemented but not independently validated | no paired M8 oracle yet |
| merge priority | Implemented but not independently validated | future analytical node family |
| strict/partial FIFO diverge | Implemented but not independently validated | future analytical node family |
| general MIMO node allocation | Implemented but not independently validated | future analytical node family |
| unsupported adaptive node control | Not yet implemented | explicitly rejected by current contracts |
| published lane-drop scenario preparation | UC evidence generated | de Souza Figure 5 text inputs instantiated at 1 s, 3 s, and 6 s |
| published lane-drop observational comparison | DT1 inflow, outflow, and storage measured | fixed digitised references; no calibration or agreement threshold |
| Yperman and cross-implementation agreement | Future published reproduction | deliberately untouched |

No elementary analytical mechanism in the first lane-drop dependency set is
currently classified as blocked. The remaining gaps above are either
implemented-but-unvalidated follow-ups, explicitly unsupported features, or
future published evidence.

## Readiness Boundary

The elementary link dynamics and one-to-one node boundary needed to start the
first lane-drop reproduction have isolated analytical evidence. The later
composition case and internal node-family suite extend the frozen-kernel
boundary; external merge/diverge reproduction remains a separate evidence gap.
