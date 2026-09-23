# ESC-D — Existing-analysis renewal plan

Defines scope, sequencing and acceptance for the renewed full audit-matrix pass required
before Existing-analysis renewal (ESC-D) can be marked complete and accepted.

Local sequence and status: [companion plan](EXISTING_STRATEGY_CORRECTNESS_PLAN.md#sequence-and-status).

## 1. Why a renewal, and why a full re-run

ESC-C's acceptance (`ESC_C_FINAL_ACCEPTANCE.md`) is pinned to commit `634164b` (2026-09-11/12,
2,054 tests, 89% coverage). Six commits have landed on `main` since that baseline:

| Commit | Summary |
| :--- | :--- |
| `ae62c98` | Step 3.3A — database readiness |
| `60eb555` | Docs consolidation |
| `a12b790` | Step 3.4 — local research workspace (new `src/workspace/*` execution adapters, `--save-run`, Analysis Run persistence/replay) |
| `ac4a9e0` | Project rebrand |
| `eaef8ab` | P2-Profiles — durable instrument-profile cache, `DataQualityError` hierarchy |
| `866c0ab` | AGENTS.md attribution guardrail (doc-only) |

`git diff 634164b..main -- 'src/*'` touches 39 files (6,141 insertions / 203 deletions),
including `src/cli.py`, both audited presenters (`src/reporting/graham.py`,
`src/reporting/momentum.py`), the historical-data quality/cache layer
(`src/data/cached_client.py`, `src/data/quality.py`), and thirteen new
`src/workspace/*` files that now sit between the CLI and the four analyzers for every
direct command.

Per the plan's own renewal requirement (§4: "Renewal reviews accumulated changes, lifecycle
behavior, output examples and freshness on the actual proposed starting revision"), this is
not a rubber stamp. Reconnaissance already surfaced one confirmed, previously-undecided
regression — **ESC-18** (`ESC_A_DEFECT_LEDGER.md`): P2-Profiles' `DataQualityError`
reclassification silently changed Momentum's provider-error message and JSON `reason_code`
for one failure scenario, because the CLI's `execution_errors()` boundary was never updated
to recognize the new exception type. ESC-18 has been logged and repaired (full gate: 3,124
passed, 91% coverage) ahead of this plan, since its disposition was already decided.

Given that a targeted-inspection pass already found one live, unreviewed regression, and per
the project owner's explicit direction, ESC-D re-runs the **complete** audit matrix from
`EXISTING_STRATEGY_CORRECTNESS_PLAN.md` §3 — all seven dimensions across all four analyses —
on the current revision, rather than limiting re-verification to the files the diff makes
look safe by inspection.

## 2. Scope

In scope: the four existing public analyses (Graham Number, Graham Growth, Momentum,
FCF/Earnings Growth) exactly as ESC-A defined them, re-verified end-to-end (provider adapters
through cache, resolution, calculations, classification, service results, CLI/orchestrator
composition, all presentation modes) on the current revision. This explicitly includes the
new surface introduced since ESC-C that participates in those paths: the `workspace/*`
execution adapters, `--save-run` / Analysis Run persistence and replay (`project_run()`),
and the durable instrument-profile cache's effect on identity/kind resolution for all four
analyses.

Out of scope, per the existing plan and prior explicit decisions: new strategies/algorithms,
speculative architecture rewrites, new persistence schemas, universal provider coverage,
automatic currency/ADR/split conversions, and the deferred orchestrator-trajectory-formatting
distinction for `DataQualityError` (Issue #40 — explicitly not to be implemented here).

## 3. Sequencing

Each slice ends with the managed quality gate and is gated by explicit authorization before
the next begins, matching the project's established slice convention (P2-Profiles Slices
B–G). A ledger entry (`ESC_A_DEFECT_LEDGER.md`) is opened for every new discrepancy found in
any slice, with disposition decided before that slice is considered done.

| Slice | Scope |
| :--- | :--- |
| ESC-D.1 | Cross-cutting composition/public-contracts re-verification: `workspace/*` execution adapters preserve the pre-Step-3.4 typed semantics for all four analyses; `--save-run`/Analysis Run persistence and `project_run()` replay never alter a direct command's own reported output; durable instrument-profile cache wiring preserves prior identity/kind resolution behavior on the default (non-cached) path. |
| ESC-D.2 | Graham Number — full seven-dimension matrix on current revision. |
| ESC-D.3 | Graham Growth — full seven-dimension matrix on current revision. |
| ESC-D.4 | Momentum — full seven-dimension matrix on current revision, with particular attention to the historical-data quality/error-boundary path (source of ESC-18) and the new `use_captured_spread` replay field. |
| ESC-D.5 | FCF/Earnings Growth — full seven-dimension matrix on current revision. |
| ESC-D.6 | Reconciliation, dated live checks across all four analyses, complete managed gate, and final ESC-D acceptance record (mirroring `ESC_C_FINAL_ACCEPTANCE.md`). |

Each of ESC-D.2–D.5 reuses ESC-C's accepted findings and regression tests as the starting
baseline for that analysis; the work is to re-verify them against current behavior and extend
coverage to any new call paths, not to re-derive them from nothing.

## 4. Acceptance criteria

- No unresolved entry in the defect ledger for any of the seven dimensions, across all four
  analyses, on the current revision.
- Independent arithmetic re-verification where accumulated changes touch a calculation or
  input-resolution path (informed by, not limited to, what the diff shows as touched).
- Dated representative live checks for all four analyses on the current revision.
- The complete managed gate (`scripts/run-quality-gates.ps1` / `.sh`), ≥85% coverage.
- An `ESC_D_FINAL_ACCEPTANCE.md` record analogous to `ESC_C_FINAL_ACCEPTANCE.md`, including
  any limits explicitly retained for acceptance.

## 5. Open question for review

ESC-D.1 (cross-cutting adapters/persistence/cache) is placed first because every other slice's
findings depend on trusting that layer. If review disagrees with that ordering, or wants any
slice split further (e.g., separating Analysis Run replay from `--save-run` itself), say so
before ESC-D.1 begins.

**Resolved 2026-09-23:** ESC-D.1 stays as one slice; project owner authorized proceeding.

## 6. ESC-D.1 evidence — cross-cutting adapters, persistence, replay, and profile cache

Verified by direct diff against the ESC-C baseline (`634164b`) and by reading the current
implementation, not by trusting adapter docstrings:

- **All four method adapters** (`src/workspace/graham_number_execution.py`,
  `graham_growth_execution.py`, `fcf_growth_execution.py`, `momentum_execution.py`) preserve the
  baseline's exact profile-composition-then-analyzer-invocation sequence on the default (no
  `profile_cache`, no `--save-run`) path. Confirmed line-for-line against baseline's
  `_run_graham_number`, `_run_graham_growth`, the inline `fcf-growth` command body, and the
  inline `momentum` command body. FCF's documented asymmetry — it never reads
  `result.instrument_profile` back after the analyzer call, unlike Graham Number/Growth's
  `analysis.instrument_profile or composed_profile` fallback — is confirmed genuine baseline
  behavior, not an adapter-introduced bug.
- **`compose_graham_profile`** (`src/workspace/graham_shared.py`) reproduces baseline's
  `_compose_analysis_profile` byte-for-byte on its default path; the new `profile_cache`
  parameter only changes behavior when a caller explicitly supplies one (`--save-run` and
  refresh), never on the plain direct-command path.
- **`_maybe_save_run`/`execute()`** (`src/cli.py`, `src/workspace/execution.py`) call the same
  adapter function exactly once and reuse its own return value (`holder[0]`) for rendering;
  persistence never substitutes a different value than what the non-saving path would have
  rendered, and a capture/storage exception propagates uncaught rather than being converted
  into a fabricated stored record.
- **Replay purity** (`src/reporting/analysis_runs.py::project_run`): Momentum's replay sets
  `use_captured_spread=True` and reads `sma_spread`/`sma_spread_percent` from the run's own
  stored `presentation_inputs`, with type-checked validation on reopened rows, never
  recomputing from `evidence.metrics`. Graham Number/Growth replay applies the same
  `friendly_graham_failure`/`*_with_public_quote_reason` helpers used by the direct commands to
  the run's own stored `assembly`, not to a freshly computed one.
- **`friendly_graham_failure`, `*_with_public_quote_reason`, `_public_quote_reason`**
  (`src/reporting/graham.py`): confirmed byte-for-byte relocations of baseline's private
  `_friendly_graham_failure`/`_*_with_public_quote_reason`/`_public_quote_reason` functions from
  `src/cli.py`, made public (no leading underscore) so `analysis_runs.py` can reuse them for
  replay. No logic changed in the move.
- **`MomentumPresentation`'s new fields** (`use_captured_spread`, `captured_sma_spread`,
  `captured_sma_spread_percent`, `src/reporting/momentum.py`) default to `False`/`None`, so
  every existing direct-command call site computes the spread from `metrics` exactly as before;
  only `project_run` sets them.
- Refresh/watchlist's own use of the profile cache is not re-verified here: its
  concurrency-safety was already established and tested under P2-Profiles (Slice D, the
  per-ticker locking fix and its `ThreadPoolExecutor` regression test), which ESC-D treats as
  standing evidence rather than repeating.

No new discrepancy was found in this slice beyond ESC-18 (already logged and repaired ahead of
this plan). ESC-D.1 is complete; proceeding to ESC-D.2 (Graham Number, full seven-dimension
matrix) next.
