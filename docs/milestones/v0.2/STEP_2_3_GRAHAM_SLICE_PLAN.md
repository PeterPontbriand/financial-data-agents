# Step 2.3 Graham Implementation Slice Plan

**Status:** Working implementation sequence; all changes remain local and uncommitted<br/>
**Governing design:** `docs/milestones/v0.2/STEP_2_3_GRAHAM_DESIGN.md`<br/>
**Scope:** Milestone v0.2, Step 2.3 only<br/>
**Last updated:** 2026-08-21

## 1. Purpose

This document is the concise handoff and execution plan for implementing Step 2.3 with a smaller-context coding model. It supplements, but does not replace, the detailed financial, architectural, temporal, and provenance requirements in `docs/milestones/v0.2/STEP_2_3_GRAHAM_DESIGN.md`.

Each slice must be implemented and reviewed independently. Do not begin Step 2.4, create a durable cache, or commit the accumulated Step 2.3 changes until the final Step 2.3 review is approved.

## 2. Cross-slice rules

The following rules apply to every slice:

1. Use deterministic code only. No LLM participates in calculations, input selection, growth estimation, or fallback behavior.
2. Keep the Graham Number and Graham growth-value method explicitly distinct.
3. Missing inputs never become zero and never silently fall back to semantically different fields.
4. Preserve source, basis, provider field, observation period, availability time, requested `as_of`, retrieval time, resolution time, cache state, and derived lineage as applicable.
5. Historical requests may use only facts knowable on or before the requested `as_of` boundary.
6. `BaseDataClient` remains the historical-price-series boundary. Do not enlarge it with fundamentals, macro-series, valuation-cache, or growth-estimation responsibilities.
7. No live API or network calls are permitted in automated tests.
8. Production provider fields are not guessed. They must pass the provider evidence gate in the governing design.
9. Expected growth remains an explicit user-supplied input for the growth-value method unless a separate growth-estimation policy is approved.
10. Do not commit at the end of an individual slice.

## 3. Coding-model workflow

Use one fresh Cline task per slice or tightly bounded correction. Every prompt should contain:

- a short repository-state handoff;
- the single slice objective;
- exact authorized files or file areas;
- explicit exclusions;
- focused tests and quality gates;
- a requirement to report actual files and symbols present on disk; and
- an instruction not to commit.

Paste the complete prompt before switching Cline to Act mode. Do not switch an existing task to Act mode while it still has pending instructions.

At the end of each slice:

1. Review Cline's report skeptically against the actual diff.
2. Generate a full tracked-and-untracked diff with the local `all_changes.diff.sh` convenience script.
3. Confirm that no unauthorized files or concepts were introduced.
4. Resolve only review findings within that slice before proceeding.
5. Begin the next slice in a fresh Cline task.

## 4. Slice status and scope

| Slice | Scope | Status |
| :--- | :--- | :--- |
| A | Repository reconnaissance only | Complete |
| B | Pure calculators and typed method results | Complete and approved |
| C1 | Provenance models and in-memory cache foundation | Complete and approved |
| C2 | Provider-neutral fact contracts and field-level input resolution | Completed incrementally through C2D-2 and approved |
| D | Deterministic valuation fixtures and fixture adapter | Complete and approved |
| E1 | Production-provider evidence investigation | Next |
| E2 | Implement only provider capabilities accepted after E1 review | Pending |
| F | Unified Graham CLI and CLI tests | Pending |
| G | Documentation synchronization, final cleanup, and full quality gate | Pending |

## 5. Slice details

### Slice A — reconnaissance only

Inspect the current uncommitted implementation and synchronized documentation. Identify reusable code, design conflicts, affected files, existing tests, and uncertain provider fields.

Constraints:

- Make no changes.
- Do not propose production field mappings without evidence.
- Report the exact repository state that later slices must preserve.

Acceptance:

- Current implementation and documentation are reconciled.
- Reusable and conflicting elements are identified.
- Later prompts can rely on an explicit file inventory.

### Slice B — pure calculators and typed results

Implement the two deterministic calculation methods and their typed outcomes:

- Graham Number: `sqrt(22.5 * EPS * BVPS)`;
- Graham growth value: `EPS * (base_pe + growth_multiplier * g) * baseline_aaa_yield / current_aaa_yield`.

This slice owns calculation-only validation, method discriminators, machine-readable statuses, finite-output guards, result invariants, and hand-calculated unit tests.

Constraints:

- No providers, cache, resolver, provenance, CLI, or documentation changes.
- Pure calculators perform no network, filesystem, settings, cache, or clock I/O.

Status: complete and approved.

### Slice C1 — provenance and cache foundation

Implement the immutable provenance and cache primitives required by later resolution work:

- `ValuationSubjectKind`;
- `SourceKind`;
- `ComponentLineage`;
- `ResolvedInput`;
- `ValuationCacheKey`;
- `ValuationCacheEntry`;
- `ValuationCacheProtocol`; and
- `InMemoryValuationCache`.

This slice owns constructor invariants, timezone-aware timestamps, finite values, provider-ID canonicalization, cache-key normalization, key/input coherence, TTL behavior, historical availability checks, schema isolation, and deterministic clock injection.

Constraints:

- Store only original `provider` or `derived` facts.
- Do not cache overrides, cache-sourced results, failures, or non-finite values.
- The cache does not fetch, resolve, relabel, or fall back.
- No live provider, resolver, CLI, or documentation work.

Status: complete and approved.

### Slice C2 — provider-neutral contracts and input resolver

Implement the provider-neutral fact boundary and field-level resolution behavior needed by both Graham methods.

The resolver order is:

```text
explicit override -> valid cache entry -> configured provider -> explicit unavailable/error result
```

Expected responsibilities:

- define the smallest provider-neutral requests and fact payloads required for quote, EPS, BVPS, and AAA-yield inputs;
- resolve each semantic field independently;
- validate provider facts before accepting or caching them;
- enforce requested `as_of` eligibility using `available_at`, not merely a reporting-period end;
- convert cache hits into correctly labeled cache provenance while preserving original provider or derived origin;
- distinguish invalid input, unavailable fact, and provider failure;
- ensure an override prevents provider access for that field;
- preserve optional-quote behavior separately from required valuation inputs; and
- test every branch with fakes and an injected clock.

Constraints:

- No production provider mapping or live calls.
- No deterministic fixture dataset yet beyond small test fakes.
- No CLI or documentation changes.
- No growth estimation.
- Do not redesign the approved C1 models unless a concrete incompatibility is reported and reviewed first.

The exact authorized files should be established in the C2 prompt after inspecting the approved C1 public surface.

### Slice D — deterministic valuation fixtures

Add a deterministic fixture facts provider and realistic fixture data sufficient to exercise both valuation methods without network access.

Fixtures must cover:

- three completed annual EPS observations;
- an explicit TTM EPS observation;
- provider-reported or transparently derived BVPS;
- a quote;
- an identified AAA-yield observation;
- observation/reporting periods and `available_at` timestamps;
- units, currency, retrieval metadata, and exact fixture field identifiers;
- missing, stale, future-published, malformed, and non-finite cases; and
- resolver precedence, cache, lineage, and historical rejection branches.

Constraints:

- No network fallback.
- Fixture capabilities do not imply that a live provider supports the same capabilities.
- No CLI changes unless separately authorized.

### Slice E1 — production-provider evidence investigation

Research and report evidence before implementing any live field mapping. For every candidate capability, record the exact upstream field or series, semantics, units, period, update behavior, availability/publication timestamp, historical support, and licensing considerations required by section 9 of the governing design.

Capabilities requiring evidence:

- annual EPS;
- TTM EPS;
- BVPS or documented derivation components;
- quote;
- AAA corporate yield; and
- historical `as_of` eligibility.

FRED's Moody's Seasoned Aaa Corporate Bond Yield (`AAA`) remains a candidate for investigation, not an automatically approved selection.

Constraints:

- Investigation and report only.
- Make no implementation changes.
- Do not infer field meaning from a convenient name alone.

Stop for architectural review before Slice E2.

### Slice E2 — verified production adapters

Implement only the production capabilities explicitly accepted after reviewing E1.

Rules:

- Unsupported capabilities return explicit unavailability.
- A current snapshot never masquerades as historical evidence.
- One upstream service need not provide every fact; narrow adapters may be composed.
- Provider-specific payload details must not leak into calculators or CLI behavior.
- Tests use mocks or recorded deterministic payloads and perform no live calls.

If E1 does not establish sufficient evidence for a capability, leave that capability unsupported rather than guessing.

### Slice F — unified Graham CLI

Replace the transitional CLI surface with the approved unified `graham` command and explicit method selection.

Expected behavior:

- the Graham Number is the default method;
- method-specific overrides are optional inputs to resolution, not universally required CLI arguments;
- incompatible method/flag combinations produce clear usage errors;
- an EPS override inherits the method's default basis unless `--eps-basis` is supplied, and that assumption appears in provenance;
- optional quote failure preserves the calculated method value while suppressing comparison fields;
- output identifies the method, status, resolved inputs, provenance, and relevant comparison values; and
- CLI tests use deterministic providers only.

Before removing or renaming transitional flags, search all tests and documentation and record the intentional compatibility change.

### Slice G — documentation, final cleanup, and complete gate

Synchronize all user-facing and architectural documentation with the implementation that actually exists. Remove stale descriptions of the transitional CLI and clearly distinguish the Graham Number from the forecast-dependent growth-value method.

Required final documentation cleanup:

- verify `README.md`, `ARCHITECTURE.md`, `DISCOVERY_WORKBOOK.md`, `FINANCE_MATH.md`, `GLOSSARY.md`, `MASTER_PLAN.md`, `milestones/v0.2/IMPLEMENTATION_PLAN.md`, and `milestones/v0.2/STEP_2_3_GRAHAM_DESIGN.md` against the final implementation;
- replace intentional two-space Markdown hard breaks in changed material with explicit `<br/>` breaks;
- search for remaining trailing whitespace, including untracked files;
- confirm commands, flags, defaults, formulas, provenance terminology, growth policy, and current implementation status; and
- ensure no documentation claims an unsupported production-provider capability.

Useful whitespace search:

```bash
rg -n --glob '*.md' '[[:blank:]]+$' docs
```

Run the repository's complete quality gate, including at minimum:

```bash
uv run ruff check .
uv run ruff format --check .
uv run mypy --strict src tests
uv run pytest
git diff --check
git status --short --untracked-files=all
```

Generate and review a final tracked-and-untracked diff. Stop for human review. Do not commit until that review explicitly approves the complete Step 2.3 change set.

## 6. Deferred and out-of-scope work

The following are not part of Step 2.3:

- Step 2.4 Golden Suite, evaluator, or reporting work;
- durable SQLite cache storage, migrations, and eviction policy;
- LLM-generated growth estimates;
- provider or analyst consensus growth without a separately approved policy and evidence review;
- speculative strategy registry or plugin-framework work;
- complete Graham defensive-investor qualification; and
- investment recommendations.

## 7. Final completion condition

Step 2.3 is complete only when every slice through G has passed review, the implementation and documentation agree, all required inputs have explicit provenance and temporal semantics, the complete quality gate is clean, the final diff contains no unauthorized files, and the user has explicitly approved committing the accumulated changes.
