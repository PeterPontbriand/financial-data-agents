# Step 2.3 Design: Dual-Method Graham Valuation

**Status:** Approved design; implementation is local and uncommitted  
**Last updated:** 2026-08-20  
**Scope:** Milestone v0.2, Step 2.3 only  
**Review gate:** Do not commit Step 2.3 or begin Step 2.4 until the completed diff is reviewed

---

## 1. Purpose and authority

This is the compact implementation specification for Step 2.3. It converts the approved milestone direction into contracts small enough to implement and review without reopening the whole architecture.

Document precedence for this step is:

1. `milestones/v0.2/IMPLEMENTATION_PLAN.md` — scope, acceptance criteria, and review gates;
2. this document — Step 2.3 method, input, CLI, fixture, and implementation contracts;
3. `FINANCE_MATH.md` — formula definitions and financial semantics;
4. `ARCHITECTURE.md` — component boundaries;
5. `DISCOVERY_WORKBOOK.md` — rationale and decisions;
6. `MASTER_PLAN.md` — milestone ordering and broader direction.

If two documents conflict, stop and surface the conflict. Do not silently combine incompatible instructions.

---

## 2. Starting point

The local worktree already contains uncommitted Graham growth-formula calculation, validation, quote retrieval, fixtures, CLI, and tests. The current CLI still requires EPS, expected growth, and AAA yield.

That code is evidence and reusable work, but it is not a compatibility contract. Step 2.3 must be revised before commit to add:

- two explicitly named Graham methods;
- field-level input resolution;
- provider and cache seams;
- overrides and provenance;
- point-in-time `as_of` behavior;
- deterministic fixtures;
- an explicit growth policy; and
- synchronized user and developer documentation.

Step 2.4 remains out of scope.

---

## 3. Locked decisions

| Area | Approved decision |
| :--- | :--- |
| Default method | `graham_number` |
| Secondary method | `graham_growth_value`, selected explicitly |
| Graham Number meaning | Maximum indicated price / screening ceiling, not a complete intrinsic-value conclusion |
| Graham Number EPS default | Average of three completed fiscal-year EPS observations |
| Graham Number variation | TTM EPS only when explicitly selected and labeled |
| Growth policy | `explicit_override`; no LLM estimate and no silent default |
| Provider architecture | Option A: keep `BaseDataClient` historical-price focused; add a valuation-facts boundary |
| Resolution order | Explicit override → valid cache → configured provider → unavailable |
| Time policy | Requested `as_of` is a hard no-look-ahead boundary |
| Cache scope | Minimal in-memory/fixture seam in Step 2.3; durable SQLite cache in Step 3.1 |
| CLI target | One `graham` command with an explicit method discriminator; omitted method means Graham Number |
| Test data | Deterministic fixtures only; no live provider or LLM calls |
| Commit gate | Stop after quality checks and diff review; do not commit automatically |

---

## 4. Financial methods

### 4.1 Graham Number — default

```text
maximum_indicated_price = sqrt(22.5 × EPS × BVPS)
```

`22.5 = 15 × 1.5`, combining the traditional defensive-investor P/E and P/B ceilings.

Required inputs:

- EPS on the selected basis; and
- book value per common share (BVPS).

Default EPS basis:

```text
three_year_average_eps =
    (completed_fiscal_eps_1 + completed_fiscal_eps_2 + completed_fiscal_eps_3) / 3
```

Rules:

- retain the three component periods in derived-input lineage;
- retain basic/diluted basis and split adjustments when known;
- do not mix incompatible share classes or silently substitute TTM EPS;
- a provider-reported BVPS is acceptable only with its definition and source field retained;
- derived BVPS uses common shareholders' equity divided by period-end common shares; and
- EPS ≤ 0 or BVPS ≤ 0 returns `not_applicable`.

The result field is `maximum_indicated_price`. User-facing text must call it a screening ceiling or maximum indicated price, not an unqualified intrinsic value.

### 4.2 Graham growth value — explicit secondary method

```text
growth_value = normalized_eps
    × (base_pe + growth_multiplier × g)
    × baseline_aaa_yield / current_aaa_yield
```

Initial configurable convention:

```text
base_pe = 8.5
growth_multiplier = 2.0
baseline_aaa_yield = 4.4
```

Required inputs:

- normalized EPS with an explicit basis;
- expected annual growth `g`, supplied by the user in percentage points; and
- current AAA corporate-bond yield from a documented series, also in percentage points.

`6.5` means 6.5%, not `0.065`. Both AAA-yield values must be strictly positive.

Initial growth policy is `explicit_override`. Absence of a growth override returns `input_unavailable`. The LLM, provider adapter, and resolver must not invent, infer, clip, cap, floor, or silently annualize growth.

The exact production AAA series is not yet selected. A production adapter cannot be declared complete until the evidence gate in section 9 is satisfied.

### 4.3 Optional quote comparison

A current or point-in-time quote is optional for calculating either method but required for price comparison:

```text
margin_of_safety_percent =
    (reference_value - current_price) / reference_value × 100
```

The reference value is `maximum_indicated_price` for the Graham Number and `growth_value` for the growth method. If quote resolution fails, return the calculated method value with `current_price = None` and `margin_of_safety_percent = None` rather than discarding a valid calculation.

---

## 5. Target CLI contract

```text
financial-agents graham TICKER [--method number|growth] [options]
```

`--method` defaults to `number`. The CLI must print the selected method, result meaning, input basis, analysis `as_of`, and provenance summary.

Common options:

- `--as-of DATE_OR_TIMESTAMP`
- `--data-provider PROVIDER_ID`
- `--no-cache`
- `--eps VALUE`
- `--eps-basis BASIS`
- `--quote VALUE`

Number-specific options:

- `--bvps VALUE`
- `--eps-basis three_year_average|ttm` (default: `three_year_average`)

Growth-specific options:

- `--expected-growth-rate PERCENTAGE_POINTS`
- `--aaa-yield PERCENTAGE_POINTS`
- the normalized EPS bases actually supported by the implementation

Method-incompatible flags must produce a clear usage error. An EPS override inherits the method's default basis unless `--eps-basis` is supplied, and that assumption is recorded in provenance.

This is the target interface, not a claim about the current uncommitted CLI. Remove or deprecate obsolete flags only after searching tests and documentation and recording the intentional compatibility change.

---

## 6. Component boundaries

### Pure calculators

Pure functions perform validation and arithmetic only. They receive resolved numeric values, return typed method-specific results, and perform no network, cache, filesystem, settings, or clock I/O.

### `BaseDataClient`

Remains the existing historical-price-series boundary used by Momentum. Step 2.3 does not add fundamentals, macro series, valuation-cache policy, or synthetic one-day quote retrieval to it.

### `ValuationFactsProvider`

A provider-neutral boundary supplies or composes only the valuation facts needed by this step:

- quotes;
- completed annual EPS observations and/or a documented TTM EPS fact;
- provider-reported BVPS or the documented components needed to derive it; and
- macro observations for a specifically identified AAA-yield series.

The boundary may be a façade over narrower quote, fundamentals, and macro capabilities. No design assumes that one upstream service provides every fact.

### `InputResolver`

Resolves each field independently:

```text
override → temporally and structurally valid cache entry → provider → unavailable
```

The resolver owns precedence, validation, `as_of` eligibility, provider fallback, transformations, and provenance assembly. Calculators never invoke it.

### Valuation cache seam

Step 2.3 needs a small `get`/`put` abstraction and an in-memory implementation sufficient to test:

- hit and miss behavior;
- disabled-cache behavior;
- schema/version invalidation;
- staleness and temporal eligibility;
- non-finite value rejection; and
- preservation of provenance.

The cache must not fetch data. The resolver owns fallback. Durable storage, migrations, eviction policy, and SQLite integration are Step 3.1 work.

---

## 7. Resolution and provenance contract

Every method input is classified as required or optional before resolution. Required unresolved facts fail explicitly; optional quote failure only suppresses comparison fields.

Every resolved input contains:

- numeric value;
- semantic field name;
- units and currency when applicable;
- source kind: `override`, `cache`, `provider`, or `derived`;
- provider identifier plus exact source field or series identifier when applicable;
- reporting or observation period;
- filing, publication, or `available_at` time when supplied;
- requested analysis `as_of`;
- retrieval/resolution time;
- accounting basis or measurement basis;
- transformations and component lineage;
- cache state and schema version when applicable; and
- override state.

Provider facts must be finite and semantically compatible with the requested field before use. Missing facts never become zero.

An override is an explicit user assertion for the requested analysis boundary. It bypasses provider lookup for that field but remains visibly labeled `override`; it must not be presented as provider-verified historical evidence.

### Point-in-time rule

A fact is eligible only when it was knowable on or before the requested `as_of`. A fiscal period end alone is insufficient if the filing or publication occurred later.

If a provider exposes only a current snapshot and cannot establish historical availability safely, a historical request returns unavailable. It must not silently substitute today's value.

---

## 8. Result and error semantics

Use typed, machine-readable statuses:

- `ok` — required inputs resolved and calculation completed;
- `not_applicable` — inputs are valid but the selected method is inapplicable, including non-positive EPS or BVPS for the Graham Number;
- `input_unavailable` — a required input could not be resolved under the requested time boundary;
- `invalid_input` — supplied value, unit, basis, or method/flag combination is invalid; and
- `provider_error` — the configured provider failed in a way that should be distinguished from an absent fact.

No path returns NaN, infinity, a complex number, or a silent zero. Errors identify the field and resolution attempts without leaking secrets.

Method-specific result types or a discriminated union are both acceptable. Invalid cross-method combinations must not be representable, and every result identifies its method.

---

## 9. Provider evidence gate

Before coding a production field mapping, record evidence for each capability:

| Capability | Evidence required before acceptance |
| :--- | :--- |
| Annual EPS | Exact field(s), annual periods, basic/diluted meaning, restatement/split behavior, availability timestamp, units |
| TTM EPS | Exact field, trailing window, basic/diluted meaning, update behavior, availability timestamp |
| BVPS | Exact field and definition, common-vs-total equity, share class, period end, units/currency; or documented derivation components |
| Quote | Exact field, exchange/currency, market/session semantics, observation timestamp, historical support |
| AAA yield | Exact series identifier, rating/issuer/maturity scope, frequency, units, observation and publication dates, retrieval method, licensing |
| Historical `as_of` | Proof that the capability can reject facts published after the boundary; otherwise declare it unsupported |

FRED's Moody's Seasoned Aaa Corporate Bond Yield (`AAA`) is a candidate for investigation, not an approved production selection. An arbitrary finance ticker is not accepted as an undocumented substitute.

If no single provider passes all rows, compose narrow adapters. Deterministic fixtures may model all capabilities without implying that a live provider has them.

---

## 10. Deterministic fixtures and tests

Fixtures must include realistic values and metadata for:

- three completed annual EPS observations;
- an explicit TTM EPS observation;
- direct or derived BVPS;
- a quote;
- an AAA-yield observation;
- reporting/observation and `available_at` timestamps;
- retrieval metadata and units; and
- missing, stale, future-published, malformed, and non-finite cases.

Required test groups:

1. both formulas against hand-calculated values;
2. default three-year-average EPS and explicit TTM selection;
3. non-positive EPS/BVPS → `not_applicable`;
4. CLI override wins without provider access;
5. valid cache hit wins over provider;
6. cache miss/stale/schema-invalid/non-finite entry falls through safely;
7. provider success and provider/missing-fact failure;
8. requested `as_of` rejects later or not-yet-published facts;
9. provenance completeness and derived lineage;
10. absent growth override → `input_unavailable`;
11. optional quote failure preserves the method value and suppresses comparison;
12. CLI default and explicit method dispatch plus incompatible-flag validation; and
13. no live network or LLM calls.

Use the repository's existing quality commands and coverage threshold from the active milestone plan. Do not weaken existing tests merely to accommodate the redesign.

---

## 11. Implementation sequence for a smaller-context coding model

Give the coding model one bounded prompt at a time. At the end of each slice, require a short diff summary and focused tests; do not ask it to redesign later slices.

### Slice A — reconnaissance only

Inspect the current uncommitted Step 2.3 code and synchronized documentation. Report reusable pieces, conflicts with this design, exact affected files, and any uncertain provider fields. Make no changes.

### Slice B — pure methods and typed results

Implement/refactor the two pure calculators, method-specific validation/statuses, result models, and unit tests. No provider, cache, resolver, or CLI changes.

### Slice C — provenance and resolver

Implement resolved-input/provenance models, the minimal cache seam, field-level resolution order, `as_of` rules, and focused tests using fakes. No live adapter or CLI changes.

### Slice D — deterministic valuation fixtures

Add fixture facts and an adapter that prove both methods, temporal rejection, and resolver branches. No network fallback.

### Slice E — provider feasibility, then adapter

First report documented field/series evidence for section 9. Implement only verified capabilities. Mark unsupported historical behavior unavailable. Do not guess an AAA ticker or silently use current snapshots.

### Slice F — unified CLI

Implement the target `graham` command, method-specific options, override semantics, clear output, and CLI tests. Search for and update affected call sites before removing old flags.

### Slice G — documentation and full gate

Synchronize README/current-state notes and any remaining code-facing documentation. Run the complete milestone quality gate. Report failures and the final diff, then stop for human review without committing.

---

## 12. Out of scope

- Golden Suite/evaluator/reporting work owned by Step 2.4;
- durable SQLite cache and migrations owned by Step 3.1;
- LLM-generated growth estimates;
- analyst-consensus or provider growth estimates without a separately approved policy;
- a speculative general strategy registry/plugin framework;
- assuming one provider supplies prices, fundamentals, and macro series;
- complete Graham defensive-investor qualification; and
- investment recommendations.

---

## 13. Completion and review checklist

Step 2.3 is ready for review only when:

- [ ] both methods are explicitly named and mathematically tested;
- [ ] the Graham Number is the CLI default and labeled as a screening ceiling;
- [ ] three-year-average EPS is the default and TTM is explicit;
- [ ] growth requires an explicit user override;
- [ ] `BaseDataClient` remains historical-price focused;
- [ ] valuation provider, cache, resolver, and provenance seams are present;
- [ ] all required inputs follow override → cache → provider → unavailable;
- [ ] historical `as_of` behavior cannot look ahead silently;
- [ ] exact live field mappings are evidenced or declared unsupported;
- [ ] fixtures and tests are deterministic and offline;
- [ ] current-vs-target documentation is truthful and synchronized;
- [ ] the complete quality gate passes; and
- [ ] the uncommitted diff is presented for human review.

After this checklist, stop. Do not begin Step 2.4 and do not commit until approval is given.
