# Step 3.3 — Data Quality & Cache Invalidation Contract and Slice Plan

**Status:** Companion plan approved and Step 3.3 implementation explicitly authorized on 2026-09-07. Production implementation has not started. Complete A reconciliation and establish the fresh baseline before production edits; preserve the implementation review gates below.

**Branch:** `feat/step-3.3-data-quality`, verified active at local head `ef60a4b` with a clean working tree before this documentation change.

**Authority:** [Implementation Plan, Step 3.3](../IMPLEMENTATION_PLAN.md#49-step-33--data-quality--cache-invalidation-pipeline). The [Master Plan](../../../MASTER_PLAN.md) supplies roadmap scope; [financial mathematics](../../../../user/FINANCE_MATH.md) remains authoritative for calculation semantics.

**Approval record:** On 2026-09-07 the project owner confirmed that the branch had been created and requested that approval to begin Step 3.3 be recorded and the necessary additional documentation prepared. This confirms the prior next-step authorization following Issue #17 acceptance. That initial request authorized documentation preparation. Subsequently, on 2026-09-07, the project owner stated, “Approved; Step 3.3 implementation authorized. Record & suggest checkpoint commit description.” This approves this companion plan and authorizes implementation within its scope. Complete outstanding A detail and baseline work before production edits; no repeat start/implementation authorization is required within the accepted scope. Implementation review gates and final acceptance remain applicable. This approval does not assert that unfinished reconciliation or implementation has passed verification, authorize later work packages, or request execution of a commit, push, or PR.

## 1. Scope and preservation

Validate incoming historical prices and financial facts, enforce explicit freshness and compatibility decisions before cache writes and downstream use, control refresh/invalidation, and expose quality failures through execution trajectories. Preserve Momentum and each financial strategy's existing mathematics, override precedence, historical `as_of` eligibility, provenance, and classified unavailability.

Reuse the existing clients, resolver, cache contracts, SQLite repositories, settings, reliability limits, and telemetry recorder. Do not introduce a generic validation registry, duplicate cache hierarchy, hidden network retries, schema migration, dependency change, or new CLI surface. Durable instrument profiles belong to P2-Profiles; watchlists and Analysis Runs belong to Step 3.4. Automatic FX conversion, corporate-action reconstruction, new provider mappings, and unattended refresh are not implied.

## 2. Initial source reconciliation

Paths below are repository-relative. This is an initial source inventory; A must finish call-path and test reconciliation before freezing exact interfaces.

| Existing boundary | Observed behavior | Remaining reconciliation/work |
| :--- | :--- | :--- |
| `src/data/cached_client.py` | Validates fetched frames for non-empty Close and finite numeric observations, including storage bypass. Uses exact request keys and injected TTL/clock; no stale error fallback. Current quotes delegate directly to the provider. | Validate cache-hit eligibility against quality policy; add continuity/context rules and explicit decisions without converting historical fetches into quote APIs. |
| `src/data/market_data.py` | Retains optional currency, interval, adjustment basis, observation count, and observation date. | Separate contradictory metadata from absent evidence; do not claim complete calendar or corporate-action validation from these fields alone. |
| `src/data/repositories/market_data.py` | Validates finite persisted observations and provides typed historical storage. | Preserve storage representation checks; keep business quality policy outside SQL encoding. |
| `src/data/financial/cache.py`, `src/data/repositories/resolved_input_cache.py` | Typed identity/period bounds, provenance, TTL and temporal eligibility already exist. Concrete inspection can expose stale/ineligible entries administratively. | Preserve normal read eligibility and distinguish administrative inspection from usable analytical inputs; decide bounded invalidation behavior. |
| `src/data/financial/resolver.py` | Already validates temporal availability and compatibility for selected financial inputs, including currency, period, share-class and split metadata. | Reuse existing checks; audit scalar, derived, and series paths rather than impose one strategy's requirements on every fact. |
| `src/data/financial/production.py` and production composition | Existing provider/cache composition is the integration seam. | Enumerate actual fetch/write paths, TTL configuration owners, bypass paths, and retry ownership before selecting changed files. |
| Trajectory recorder and repository | Existing sanitized, fail-open event persistence; Issue #17 regression coverage is present in local merged commit `ef60a4b` (`#31`). | Select a compatible typed quality-decision payload/event path and prove trace linkage. Local Git history does not independently confirm remote issue closure. |

Relevant existing regression suites include `tests/data/test_cached_client.py`, `tests/data/repositories/test_market_data.py`, `test_resolved_input_cache.py`, `test_series_cache.py`, and `test_persistence_smoke.py` in that repository-test directory. A must enumerate resolver/provider and telemetry tests needed for the selected paths.

## 3. Approved quality contract

Every evaluated rule should produce a typed decision with rule identifier, outcome, reason, affected input/cache identity, and relevant observation/retrieval/analysis timestamps. Distinguish pass, failure, and insufficient evidence. Insufficient evidence must never be labeled a verified pass; whether it blocks a particular use depends on that use's required evidence. Keep secrets and raw provider payloads out of diagnostic metadata.

| Rule family | Approved behavior | Detail to resolve during A |
| :--- | :--- | :--- |
| Structural/numeric validity | Reject empty required series, missing required values, and NaN/Inf before writes and analytical use; never fill missing observations with zero. | Required columns and index invariants per supported payload. |
| Continuity/missing bars | Detect duplicate/out-of-order dates and missing expected observations where a supported session schedule is available. Never infer that every weekday is a trading session or interpolate missing prices silently. | Calendar/evidence source, supported intervals, request endpoints, holidays, suspensions, partial sessions, and unknown-calendar outcome. No new dependency without permission. |
| Currency/units | Reject incompatible currencies or units when combining inputs; retain explicit missing metadata. | Required evidence by operation; CAD/USD mismatch cases; no automatic FX conversion without a separately specified rate/date/provenance contract. |
| Corporate actions | Preserve declared adjustment basis and reject demonstrably incompatible split/share bases. Do not infer a split solely from a large price move or adjust an already adjusted series again. | Supported provider evidence, unknown basis behavior, and adjustment consistency across compared inputs. |
| Financial periods | Preserve existing method-specific duration/instant, fiscal-period, availability, and series compatibility checks. Reject incompatible combinations explicitly. | Scalar/series/derived path coverage, restatements, annual versus interim facts, and historical availability boundaries. |
| Freshness | Separate cache residence age from observation/reporting age and historical analysis eligibility. Refresh an expired eligible request through the existing guarded provider path. | Typed defaults per data capability, equality boundaries, future timestamps/clock skew, market closures, and historical requests. Existing TTL semantics must not change accidentally. |

### Cache and refresh lifecycle

1. Evaluate a candidate cache hit for the requested analytical use; administrative inspection does not establish eligibility.
2. If eligible, preserve the stored evidence and original timestamps. Otherwise record why it cannot be reused and follow the existing guarded fetch path.
3. Validate fetched data before writing or returning it as usable. Invalid refresh output must not replace a valid stored snapshot or cause stale fallback.
4. Prefer logical exclusion and validated replacement over destructive deletion. A must specify how a rejected stored entry stays excluded on later requests and after reopen; do not claim durable invalidation from a transient flag.
5. Keep provider retries within existing timeout/circuit-breaker ownership. Do not add an unbounded quality-triggered re-fetch loop. Classify deterministic incompatibility separately from transient transport failure.
6. Emit quality failures with run/span linkage through the existing sanitized recorder. Telemetry failure must not change the quality decision or business outcome. Direct calls without a recorder still enforce quality rules.

## 4. Approved implementation slices and review gates

The project owner approved this handoff and authorized Step 3.3 implementation on 2026-09-07. The current recording task prepares the documentation checkpoint; execution begins with outstanding A reconciliation and baseline work. Review gates for implemented slices and final acceptance remain in force.

| Slice | Deliverable | Exit gate |
| :--- | :--- | :--- |
| 3.3-A — Reconciliation and contract | Complete fetch/read/write inventory, existing-test mapping, exact typed interfaces/file scope, policy defaults and all review details in section 3; fresh managed baseline before refactoring. | Plan accepted and implementation authorized on 2026-09-07. Finish and record concrete contract details and baseline evidence before B; material scope changes require review. |
| 3.3-B — Rules and focused tests | Implement accepted deterministic rules/configuration and regression tests for boundary conditions; reuse existing checks. | Review bounded diff, focused tests and full managed gate before C. |
| 3.3-C — Cache/refresh and trajectory integration | Apply rules to approved fetch/cache paths, controlled refresh and exclusion, transparent quality failures, and preserved fail-open telemetry. | Review lifecycle, reopen/rollback and reliability evidence plus full managed gate before D. |
| 3.3-D — Acceptance and documentation | Reconcile acceptance evidence and durable behavioral documentation with implemented contracts; final managed gate. | Explicit final acceptance before marking Step 3.3 complete. Later packages remain separate. |

## 5. Verification and acceptance matrix

Use synthetic data, injected clocks, mocked providers/LLMs, and migrated temporary SQLite databases. Never use real user databases, production cache fixtures, or live external calls in deterministic tests.

| Acceptance criterion | Required evidence |
| :--- | :--- |
| Documented quality rules with clear pass/fail behavior | Every accepted rule has valid, invalid, missing-evidence and applicable boundary cases; defaults and temporal conventions match implementation. |
| Stale/invalid data cannot silently become analytical truth | Cache hit/miss/expired/rejected, bypass, fetched-invalid, failed-refresh, historical-as-of, scalar/series/derived input and reopened-database cases. Prove no invalid write, silent zero fill, stale fallback or unbounded re-fetch. |
| Failures appear transparently in trajectories | Rule/reason and affected-input identity linked to the execution; sanitized serialization/readback; recorder failure leaves rejection/refresh outcomes unchanged. |
| Existing behavior remains valid | Momentum and heterogeneous strategy regressions, quote separation, provenance, supported TTL boundaries, repository round trips and reliability limits remain green. |

Complete non-mutating gate from the repository root:

```powershell
& (Join-Path (git rev-parse --show-toplevel) 'scripts/run-quality-gates.ps1')
```

Record revision, date, Ruff/format/mypy results, pytest counts, coverage and ignored artifact location for each implementation gate. No fresh code baseline is claimed by this documentation-only handoff. The accepted predecessor record reports 1,870 tests and 89% coverage; that is historical evidence, not a new run.

## 6. Current handoff

- Start approval and branch: recorded and verified on 2026-09-07.
- Companion plan, rule matrix, slices and verification requirements: approved on 2026-09-07; Step 3.3 implementation authorized.
- Exact interfaces, complete call-path audit, policy details and fresh baseline: outstanding in A under the granted implementation authorization.
- Production code, tests, dependencies, database contents and public behavior: unchanged by this preparation.
- Step 3.3 acceptance checkboxes remain open. Implementation review gates and final acceptance have not been completed.
