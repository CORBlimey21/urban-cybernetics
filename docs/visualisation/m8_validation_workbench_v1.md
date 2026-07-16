# M8 Validation Workbench v1

## Architecture

The validation workbench is a third, narrow plane beside V2 evidence and
control. `uc.validation.case.v1` contains authored claims, independent expected
evidence, metrics, tolerances, explanations, overlays, citations, and reference
asset declarations. `uc.validation.result.v1` contains Python-observed evidence,
differences, metric results, provenance, and packet-wait explanations.

The validation runner is outside the loading kernel. It resolves only declared
case IDs, constructs the sanctioned analytical fixture, lets the loading engine
own execution, folds observations from canonical events in Python, compares
them with the authored oracle, and exports an ordinary V replay bundle. The
browser never executes loading mechanics or derives expectations.

The frozen v1 fields retain their original meanings. Scientific claims use
`short_explanation` and `safe_claim`; physical mechanism and diagnostic purpose
use `why_it_matters`; assumptions use `initial_state_reference` and
`reproducibility_notes`. No case-schema extension is required for the expanded
analytical library.

## Analytical case library

- `M8-LINK-01`: exact free-flow pulse translation.
- `M8-LINK-02`: exact capacity-constrained discharge, point queue, and delay.
- `M8-LINK-03`: exact backward-vacancy lag and boundary-queue release.
- `M8-LINK-04`: sustained uncongested cadence.
- `M8-LINK-05`: queue growth, saturated discharge, and clearance.
- `M8-LINK-06`: repeated backward-vacancy releases.
- `M8-LINK-07`: fractional sending-capacity carry.
- `M8-NODE-01-*`: demand-limited, supply-limited, equal, zero-demand,
  zero-supply, reopening, and fractional one-to-one transfers.
- `M8-PUB-DSOUZA-FIG5-DT1`, `DT3`, and `DT6`: evidence-only execution of
  the text-declared Figure 5 lane-drop inputs. These cases intentionally carry
  no paper expected series or comparison metrics.

Expected tables remain literal fixture data. They are duplicated deliberately
between independent external-validation tests and the workbench case contract;
neither is generated from UC projections. Baseline results under
`fixtures/visualisation/validation/` are deterministic reloadable evidence.

Published preparation cases use the same library, replay, inspectors, charts,
and Lab Bench. The chart switches generically to observed-only mode when a case
declares no expected series. Supplemental execution evidence exposes movement
allocation traces and post-run vacancy-wave presentation windows without
case-ID-specific frontend behaviour.

## Evidence semantics

| Display | Status |
| --- | --- |
| packet/link lifecycle and queue events | canonical |
| cumulative counts and realised replay state | event-derived |
| authored expected curves and release ticks | analytical/reference |
| observed-minus-expected series and metric decisions | validation output |
| whole-link queue/wave shading and animation | presentation-only rendering of a declared overlay |

The backward-wave overlay communicates direction and the declared lag interval;
it is not a continuous shock position. Anonymous interpolated packet dots remain
presentation-only. A waiting explanation is shown only when the persisted
validation result identifies its canonical, exported, or analytical sources.

## Consolidated replay visual language

Link width uses declared lane count as a restrained schematic cue. Selected
links expose declared length and lane count, but node placement and screen-edge
length remain layout metadata rather than physical geometry. Occupied links,
declared routes, realised paths, selected links, and current packet links use
separate strokes.

Queue regions fill backward from a link's downstream end. The magnitude comes
from canonical queue membership where available, otherwise from the exported
Python validation series. Its normalized screen extent and boundary marker are
presentation abstractions; the canvas identifies both the scientific source
and this visual-only normalization. A blocked receiving boundary also marks the
transfer node without asserting an unavailable sending or receiving value.

For authored analytical vacancy intervals, a dashed cue moves upstream across
the declared tick window. The timing source remains analytical/reference;
the cue's position between the link endpoints is explicitly presentation-only.
Exported movement traces can highlight approved downstream links and rejected
upstream links without reproducing allocation in JavaScript.

The replay bar advances only between exact persisted ticks. Space toggles viewer
playback and the arrow keys step one exact tick. Playback rate and animation do
not affect simulation evidence. The link inspector groups immutable physical
metadata, event-derived replay values, and declared validation comparisons, and
keeps unavailable storage/supply fields explicit. Chart quantity choices are
remembered per case in local browser presentation state.

## Run and persistence workflow

The browser can run one declared case or the current analytical group. A
background Python thread exposes setup, execution, comparison, persistence, and
terminal stages. Cancellation is accepted between exact ticks and writes a
partial replay result instead of deleting evidence. Browser disconnect does not
own the run.

Runtime results append beneath `outputs/visualisation/validation/runs/`. A new
pass never overwrites an earlier failure or cancellation. Each result freezes
case version, configuration hash, expected-evidence hash, code commit, metrics,
and timestamps. Optional issue/fix-commit fields are reserved in the result
contract.

Regenerate the baseline fixtures with:

```bash
.venv/bin/uc-visualisation export-validation-fixtures
```

## Reference assets

Reference declarations support citation text, section/figure/table/equation,
an allowed local asset path, a digitised-series ID, rights/provenance notes,
transformations, comparison suitability, and missing-input notes. This slice
embeds only repository-authored tables. It neither downloads nor extracts
copyrighted figures.

## Known limitations

- The analytical cases share one declared execution adapter; future published
  cases must declare their own suitable mechanism rather than pretending all M8
  evidence is homogeneous.
- Run-all is limited to the current analytical group.
- Validation progress is polled locally; a separate stream is unnecessary at
  this scale.
- The point queue and vacancy supply are Python validation projections, not new
  engine state.
- Paired timestep-invariance and standalone static triangular-FD Workbench
  cases remain optional analytical follow-ups.
- The de Souza lane-drop input/evidence preparation is now present. Published
  curves, tolerances, errors, and agreement/disagreement remain outside this
  slice.
