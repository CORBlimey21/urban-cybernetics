# Validation Workbench Lab Bench v1

Status: first focused vertical slice. The Lab Bench is a persisted derivation
surface inside the existing Validation Workbench. It is not a simulator,
notebook kernel, general spreadsheet, or replacement for independently encoded
M8 fixtures.

## Architecture and contracts

The loading kernel remains the owner of physical truth and does not import any
Lab Bench or visualisation module. Lab Bench formulas operate only on typed
literal values, declared case inputs, and finite tables. They cannot call the
loading engine or validation helpers.

Two frozen Pydantic contracts define the scientific state:

- `uc.lab_bench.worksheet.v1` for mutable scratch and candidate worksheets;
- `uc.lab_bench.oracle.v1` for immutable append-only oracle versions.

The React panel is a client of the Python API. Python evaluates expressions,
table formulas, dependency order, units, time alignment, and comparisons. The
browser presents those results and owns only panel geometry, open/minimised
state, selected mode, selected worksheet, and graph selection.

## State lifecycle

The only allowed promotion path is:

```text
scratch -> candidate_reference -> frozen_oracle
```

Scratch and candidate material never participates automatically in validation
pass/fail. A candidate remains editable and all comparisons against it are
labelled informal. Freezing requires a deliberate approval statement and an
associated validation case. Each frozen version is written to a new file and
contains the worksheet snapshot, formulas, units, tick convention, linked and
detached inputs, source classification, notes, limitations, dependency hash,
approval action, artifact hash, and source revision.

UC-observed, UC-derived, presentation-only, model-suggested, and UC-observed
table columns are rejected from oracle freezing. Existing validation fixture
oracles are never overwritten or selected as the primary oracle by this slice.

## Notebook

The notebook stores Markdown and LaTeX source, origin classification, and
optional variable links. It autosaves as scratch/candidate state and supports
explicit append-only revision saves. The first browser renderer handles
headings, lists, paragraphs, and display-equation blocks; it deliberately does
not introduce a notebook kernel or remote rendering dependency.

## Calculator and table evaluator

The expression parser uses Python `ast` with an explicit node allow-list. It
supports numeric literals, declared scalar variables, arithmetic, parentheses,
small integer powers, `min`, `max`, `abs`, `ceil`, `floor`, finite argument
`sum`, comparisons, and `ticks(time, timestep)` / `time(ticks, timestep)`.
Optional output conversion covers the bounded unit vocabulary.

The parser rejects attributes, imports, calls outside the allow-list,
comprehensions, lambdas, strings, dynamic indexing outside table evaluation,
filesystem/network access, and oversized expressions.

Tick tables declare a finite integer range, column kind, units, provenance,
formula text, ascending-tick evaluation order, and explicit out-of-range
values. Formula columns may reference `column[t - lag]`. Python topologically
orders inter-column dependencies, allows declared-lag self-recursion, and
rejects circular dependencies, current/future self-reference, missing initial
conditions, ambiguous non-integer tick references, unknown names, and unit
inconsistency.

## Case linkage and detachment

Case variables include source, units, evidence classification, configuration
identity, and a linked/detached flag. A user may insert a linked name into a
formula or detach that value as a literal. Freezing rechecks every linked
dependency against the current declared case configuration. Changed linked
dependencies block freezing; fully detached literals remain fixed and are
recorded in the oracle.

Changing the selected Workbench case does not silently retarget an existing
worksheet. The UI displays the mismatch and requires the user to create or
select the intended worksheet.

## M8-LINK-01 demonstration

The starter exposes the declared 200 m link, 10 m/s free-flow speed, 10 s
timestep, capacity/storage metadata, lag derivations, demand description, route,
and transition markers. It provides:

- a notebook derivation for free-flow time and lag;
- a manually transcribed `(3, 0, 0, 0)` entry schedule from the declared pulse;
- formula-derived cumulative entries, cumulative exits, and storage;
- line, step, and scatter views with authored transition markers;
- explicit mapping to one chosen UC-observed or existing-fixture series;
- scratch-to-candidate promotion and deliberate versioned freezing.

The starter does not import the fixture's cumulative expected values. Those
values arise only after the bounded table formulas are evaluated.

The de Souza Figure 5 preparation family also has a starter. It exposes both
links' declared physical inputs, the 150 s bounded observation setting, and the
explicit tick-end unit-departure conversion. It does not import published
curves or UC-observed outputs and therefore does not create a paper oracle.

## Known first-slice limits

- The lightweight preview preserves and displays LaTeX source but is not a full
  TeX typesetter.
- Table editing supports finite numeric columns and multi-cell paste into a
  manual column; column creation/removal is not yet exposed in the UI.
- Unit support is deliberately narrow and does not yet cover compound density
  declarations or affine units.
- M8-LINK-01 and the three de Souza preparation timesteps have complete
  starters. Other cases expose their declared variables and can receive future
  case-specific starter templates.
- Frozen Lab Bench oracles can be compared alongside fixtures, but cannot yet
  become a case's formal primary oracle.

The recommended next enhancement is a compact column editor that can add
manual, formula, imported, and case-linked columns while retaining the same
bounded Python evaluator and provenance review.
