# Step 2.4 Design: Free Cash Flow & Earnings Growth Analysis

**Status:** Revised design draft incorporating prospective Real-User clarification; explicit policy locks remain before implementation beyond reconnaissance<br/>
**Prepared:** 2026-08-25<br/>
**Revised:** 2026-08-25<br/>
**Scope:** Milestone v0.2, Step 2.4 only<br/>
**Entry condition:** Step 2.3 is complete, approved, and merged; Step 2.4 Slice A reconnaissance and design work may proceed, while production implementation remains blocked until the policy locks affecting Slice B are reviewed and approved<br/>
**Next step:** Step 2.5 Golden-Test Suite & Strategy Evaluation

---

## 1. Purpose and authority

Step 2.4 adds a third materially different deterministic investor analysis before the Golden Suite.

The immediate product motivation is concrete: a prospective Real-User has clarified that **“FCF (free cash flow) and earnings growth”** means a fundamental screening strategy that combines:

- multi-year historical diluted-EPS growth;
- 1–2 year forward consensus EPS expectations;
- project-defined free cash flow using `CFO - CapEx`;
- a 3–5 year FCF growth/trend view;
- FCF yield relative to market capitalization; and
- an explicit screen result followed by transparent trend/valuation evidence for qualitative investor judgment.

The architectural motivation remains equally useful: Step 2.3 established provider-neutral financial-fact resolution, provenance, strict point-in-time behavior, deterministic fixtures, strategy-specific investor presentation, and a unified direct-analysis CLI. Step 2.4 should prove that those foundations generalize to cash-flow statements, forecast data, valuation ratios, and screen semantics without creating a parallel architecture.

This design treats the prospective-user remarks as **requirements evidence**, not as authority for broad claims about institutional-investor practice. Step 2.4 must implement the requested analytical behavior without pretending to reproduce a generic hedge-fund, long-only, macro, activist, or private-equity methodology.

Document precedence for Step 2.4 should be:

1. `docs/project/MASTER_PLAN.md` — milestone intent and ordering;
2. `docs/project/milestones/v0.2/IMPLEMENTATION_PLAN.md` — active milestone scope, gates, and sequencing;
3. this document — Step 2.4 financial/data/screen/CLI/presentation contract;
4. `docs/user/FINANCE_MATH.md` — formula and financial semantics;
5. `docs/project/ARCHITECTURE.md` — component boundaries;
6. `docs/project/DISCOVERY_WORKBOOK.md` — rationale.

If implementation evidence conflicts with this design, stop and surface the conflict rather than silently widening scope.

---

## 2. Stakeholder intent now established

The following product intent is sufficiently clear to replace the earlier historical-only fallback assumptions.

### 2.1 Earnings growth

The strategy should balance historical performance and expected future momentum:

- use trailing multi-year **diluted EPS** history;
- prefer a 5-year historical growth horizon;
- permit a 3-year minimum when sufficient 5-year history is unavailable;
- incorporate **1-year and 2-year forward consensus diluted-EPS estimates** when a provider can supply them with explicit semantics and provenance;
- show historical and forward evidence separately rather than collapsing them into one opaque growth score.

### 2.2 Free cash flow

The canonical initial definition remains deliberately simple and disclosure-consistent:

```text
free_cash_flow = operating_cash_flow - capital_expenditures
```

The strategy should:

- focus on the 3–5 year FCF history and trajectory rather than one isolated year;
- prefer a 5-year historical view;
- use a 3-year minimum when 5-year history is unavailable;
- expose annual CFO, normalized CapEx, and derived FCF so a CapEx-heavy year is visible rather than hidden;
- calculate **FCF yield = FCF / market capitalization** using an explicitly documented numerator period and denominator valuation date.

### 2.3 Screening behavior

The strategy is intended to be a **screen**, not merely a metrics report.

For each analyzed security it should produce:

1. an explicit screen outcome;
2. per-criterion pass/fail/indeterminate evidence;
3. the actual historical series and valuation ratios used; and
4. enough context for a knowledgeable investor to make a qualitative judgment after the initial screen.

The screen outcome must remain separate from software/calculation status. A valid analysis may legitimately return `fail`. Missing evidence may make the screen `indeterminate` without implying a provider or software error.

### 2.4 Important interpretation boundary

The prospective-user remarks also discuss FCF-to-net-income, FCF margin, FCFF, FCFE, owner-earnings adjustments, stock-based compensation, maintenance-versus-growth CapEx, enterprise-value denominators, and working-capital normalization.

Those ideas are useful context, but they are **not automatically approved Step 2.4 requirements**. They remain possible later refinements unless explicitly promoted into the initial screen at the policy checkpoint below.

---

## 3. Remaining product-policy locks before Slice B

Repository/provider reconnaissance may begin before these are resolved, but production behavior must not silently choose answers to them.

### 3.1 Exact hard-screen thresholds

The stakeholder intent clearly calls for pass/fail screening, but the exact thresholds are not yet unambiguous.

The design therefore requires an explicit human decision on the initial default criteria. Candidate criteria suggested by the remarks include:

- positive multi-year historical diluted-EPS growth;
- positive multi-year historical FCF growth;
- positive 1–2 year forward consensus EPS momentum;
- positive FCF yield;
- a minimum FCF-yield threshold, with **6%–8% mentioned as an example rather than an approved default**.

Do not encode `6%`, `8%`, or any other numerical cutoff merely because it appeared in explanatory prose.

The implementation should support typed criterion results so a future threshold change does not require redesigning the result model.

### 3.2 What exactly “5-year” means

Two common interpretations exist and should not be conflated:

- **5 elapsed years of compound growth**: requires six annual endpoint observations (`t-5` through `t`);
- **a 5-observation annual history window**: contains four elapsed year intervals.

Proposed project convention: `growth_years` means **elapsed years**, so a 5-year CAGR requires six compatible annual observations and a 3-year CAGR requires four. This convention must be explicitly approved before Slice B because it affects fixtures, fallback behavior, CLI language, and stakeholder expectations.

### 3.3 FCF CapEx-distortion treatment

The prospective Real-User specifically warns that a single CapEx-heavy year may depress simple FCF even when the business remains fundamentally strong.

The initial design locks two principles but not yet one exact smoothing formula:

- never alter the canonical annual `FCF = CFO - CapEx` facts to make them look smoother;
- do not make the hard screen depend only on the latest single-year FCF value.

Before Slice B, choose whether the multi-year FCF screen uses only endpoint CAGR or also a deterministic smoothing/trend statistic such as a rolling-average comparison. Any smoothing metric must be shown separately from raw annual FCF and must not rewrite the underlying FCF series.

### 3.4 4-year intermediate fallback

Section 6.1 must follow whichever fallback policy is approved here rather than silently choosing an intermediate horizon.

Before Slice B, the stakeholder must explicitly approve whether the resolver prefers the longest available compatible horizon (5 → 4 → 3) or drops directly from an unusable 5-year horizon to the 3-year minimum. The 4-year intermediate fallback is a proposal, not an approved default. The chosen behavior affects fixtures, CLI language, and stakeholder expectations.

### 3.5 FCF-yield numerator basis

The remarks specify `FCF / Market Cap` but do not fully specify whether the numerator should be:

- latest completed fiscal-year FCF;
- trailing-twelve-month FCF; or
- a normalized/smoothed multi-year FCF amount.

Proposed v0.2 default: **latest completed fiscal-year FCF divided by market capitalization at the analysis `as_of`**, with both dates made explicit. This minimizes new interim-cash-flow complexity while preserving a useful current valuation ratio. This must be resolved before Slice B, not deferred to Slice D.

### 3.6 Forward-consensus screen semantics

The strategy should show 1-year and 2-year consensus EPS estimates, but “forward growth” still needs an exact deterministic definition.

Proposed initial derivations:

```text
forward_year_1_growth_percent = (consensus_eps_fy1 - latest_actual_eps) / latest_actual_eps * 100
forward_year_2_growth_percent = (consensus_eps_fy2 - consensus_eps_fy1) / consensus_eps_fy1 * 100
```

These percentages are available only when the relevant denominator is strictly positive under the same sign/zero rules used for historical growth. Raw estimate values remain reportable when a percentage is mathematically nonmeaningful.

The stakeholder should confirm whether the hard screen requires both forward years to be positive, either year to be positive, or merely requires the estimates to be displayed as qualitative evidence.

### 3.7 “Trendlines” in a terminal product

The requirement to show “actual trendlines” can mean either:

- the actual annual time series and a deterministic trend classification; or
- a literal visual sparkline/ASCII chart.

Proposed Step 2.4 interpretation: the concise/details presentation must expose the annual series and trend direction; a literal chart is optional unless the stakeholder specifically requests one.

### 3.8 Universe screening versus per-security screen result

Step 2.4 can define a hard pass/fail/indeterminate result for each analyzed security without introducing watchlist/universe infrastructure.

Unless separately approved, Step 2.4 does **not** add a new universe loader, market-wide batch scanner, portfolio/watchlist persistence layer, or ranking engine. Those systems may later consume the per-security screen result.

---

## 4. Strategy identity and meaning

Stable strategy identifier:

```text
fcf_earnings_growth
```

Proposed direct CLI command:

```text
financial-agents fcf-growth TICKER [options]
```

Investor-facing name:

```text
Free Cash Flow & Earnings Growth
```

This strategy is a **fundamental quality/growth/valuation screen with transparent historical and consensus evidence**. It is not:

- an intrinsic-value model;
- a discounted-cash-flow model;
- a P/E- or book-value-based valuation model;
- a complete quality-of-business assessment;
- a complete “Druckenmiller” or other named-investor methodology;
- a claim that accounting manipulation has been proven or disproven;
- an investment recommendation.

The strategy may identify divergence between reported earnings and cash generation as a warning signal, but it must use neutral wording such as `earnings_cash_flow_divergence` rather than claiming fraud or manipulation from the screen alone.

---

## 5. Canonical financial semantics

### 5.1 Free cash flow

For the initial project implementation:

```text
free_cash_flow = operating_cash_flow - capital_expenditures
```

Where:

- `operating_cash_flow` means net cash provided by operating activities for the selected reporting period;
- `capital_expenditures` is normalized by the provider/resolution layer to a **positive expenditure amount** before subtraction;
- the derived FCF retains complete component lineage.

Example:

```text
Operating cash flow:       1,000
Reported CapEx cash flow:   -250
Normalized expenditure:      250
Free cash flow:              750
```

FCF is a project-defined non-GAAP analytical measure. Provider/company presentations may define similarly named measures differently. Output must therefore show the project's definition in details/JSON and must not silently consume a provider's precomputed “free cash flow” field unless its definition is proven compatible.

Do not adjust this canonical FCF for stock-based compensation, working-capital normalization, maintenance-versus-growth CapEx, financing cash flows, or other owner-earnings/FCFF/FCFE concepts in Step 2.4 unless explicitly approved as a named secondary metric.

### 5.2 Earnings basis — historical actuals

The historical earnings measure is **completed fiscal-year diluted EPS**.

Rules:

- preserve basic/diluted basis explicitly;
- do not mix annual EPS observations with TTM observations in one historical growth series;
- do not mix incompatible share classes;
- preserve split/restatement evidence where available;
- use only observations knowable by the requested `as_of`.

A later explicit variation may support another earnings basis, but it must be named and cannot silently replace diluted annual EPS.

### 5.3 Earnings basis — forward consensus

Forward earnings evidence consists of provider-supplied **consensus diluted-EPS point estimates** for the next one and two comparable fiscal periods.

Every estimate must preserve at least:

- forecast fiscal period/end;
- estimate value;
- diluted/basic basis if supplied;
- currency/units where applicable;
- provider/source;
- provider field/concept;
- estimate snapshot/observation timestamp;
- retrieved timestamp;
- analyst-count or dispersion metadata when available, but neither is required for v0.2.

Do not silently use an opaque provider “growth estimate” field when the underlying period, basis, and update semantics cannot be verified. Prefer deriving forward growth from explicit consensus EPS point estimates.

### 5.4 Market capitalization

For the initial FCF-yield denominator, `market_capitalization` means the provider-resolved equity market capitalization for the analyzed security at the applicable valuation timestamp.

Requirements:

- preserve currency;
- preserve provider and observation timestamp;
- do not synthesize historical market capitalization from current price unless explicitly approved;
- do not substitute enterprise value for market capitalization;
- the output must display the numerator period and denominator date because they are not necessarily the same date.

### 5.5 Period alignment

An annual FCF observation is valid only when operating cash flow and capital expenditures refer to the same compatible fiscal period and currency.

Do not combine:

- year-to-date CFO with full-year CapEx;
- different fiscal-year ends;
- different currencies without an approved conversion policy;
- values from incompatible consolidated scopes;
- facts not yet published/available by the requested `as_of`.

If compatible component facts cannot be established, that FCF period is unavailable.

Historical EPS and FCF series should align by comparable fiscal-year ordering, but EPS and FCF do not need identical filing timestamps. Provenance must preserve each fact's actual availability.

---

## 6. Historical-window and growth semantics

### 6.1 Preferred horizon and fallback

The investor intent is **5-year baseline, 3-year minimum**.

Subject to the policy locks in Sections 3.2 and 3.4, the resolver should:

1. attempt the preferred 5-year historical growth horizon;
2. if insufficient compatible history exists, apply the fallback policy explicitly approved under Section 3.4;
3. expose the actual horizon used;
4. never silently label a shorter-horizon result as 5-year growth.

A shorter-than-3-year history is insufficient for the core historical growth screen unless a future policy explicitly allows it.

### 6.2 Year-over-year change

For a metric `x`:

```text
yoy_growth_percent = (current - prior) / prior * 100
```

Baseline rule:

- if `prior > 0`, percentage growth may be calculated;
- if `prior <= 0`, percentage growth is `None` with a structured reason;
- retain the raw current/prior values so the investor can still see the economic change.

Do not emit infinity, an enormous pseudo-growth percentage from a zero denominator, or silently reinterpret a loss-to-profit / negative-to-positive transition as ordinary percentage growth.

### 6.3 CAGR

For a positive metric observed `N` elapsed years apart:

```text
cagr_percent = ((ending / beginning) ** (1 / N) - 1) * 100
```

CAGR rules:

- beginning and ending values must both be strictly positive;
- periods must represent the requested elapsed-year span without silent gaps;
- negative/zero endpoints, sign changes, or incompatible periods make CAGR unavailable with a structured reason;
- raw history remains visible;
- no clipping, flooring, absolute-value transformation, or sign erasure.

The same mathematical policy applies independently to FCF CAGR and diluted-EPS CAGR.

### 6.4 FCF trajectory and CapEx-heavy years

The strategy must preserve the raw annual series:

```text
fiscal_year
operating_cash_flow
capital_expenditures
free_cash_flow
```

A large CapEx year is not an error and must not be normalized away merely to improve the screen result.

The presenter should call attention to material year-to-year FCF volatility when it may make an endpoint CAGR misleading. If a smoothing/trend statistic is approved at the Section 3.3 policy lock, it must be:

- deterministic;
- separately named;
- calculated from the same raw annual FCF history;
- fully testable;
- never substituted for raw FCF without disclosure.

### 6.5 Forward consensus growth

When valid FY1/FY2 consensus EPS point estimates are available, derive the approved forward metrics from the explicit estimate values.

Forward estimates are **expectations, not actuals**. Presentation and JSON must label them as consensus estimates and must never place them in the historical actual series.

### 6.6 FCF yield

Initial formula:

```text
fcf_yield_percent = free_cash_flow / market_capitalization * 100
```

Rules:

- market capitalization must be strictly positive;
- FCF may be positive, zero, or negative;
- negative FCF produces a negative yield rather than a software error;
- numerator period and market-cap date must be explicit;
- no enterprise-value substitution;
- no reciprocal P/FCF metric is required unless separately approved.

---

## 7. Screen semantics

### 7.1 Screen outcome is not calculation status

Define a strategy-level screen decision independently from the project's operational/calculation status vocabulary.

Screen decision vocabulary:

```text
pass
fail
indeterminate
```

Meaning:

- `pass` — all required hard criteria have valid evidence and pass;
- `fail` — at least one hard criterion has valid evidence and fails. A known hard failure remains FAIL even when another required criterion lacks evidence;
- `indeterminate` — no hard criterion has valid failing evidence, but one or more required criteria cannot be evaluated because evidence is missing/unavailable or mathematically nonmeaningful.

A known hard failure is never rescued into INDETERMINATE by the absence of evidence for a different criterion. Software/calculation status remains separate from the investment-screen outcome.

A provider failure remains a provider/software status and should not be disguised as an investment-screen `fail`.

### 7.2 Per-criterion evidence

Each hard criterion should produce a typed result containing at least:

```text
criterion_id
status = pass | fail | indeterminate
observed_value(s)
threshold / rule
horizon / period
reason
```

This keeps the final screen auditable and allows thresholds to change without turning the overall strategy into a hidden composite score.

### 7.3 No arbitrary weighted score

Step 2.4 should not produce a weighted 0–100 quality score or optimize weights. The requested product is a **hard gate followed by evidence**, not an opaque ranking model.

### 7.4 Earnings-versus-FCF divergence

The strategy may produce a deterministic warning/classification when reported earnings expansion and cash-flow expansion materially disagree.

Possible neutral classifications include:

- `both_expanding`;
- `earnings_expanding_fcf_not`;
- `fcf_expanding_earnings_not`;
- `neither_expanding`;
- `insufficient_or_nonmeaningful_growth`.

This is descriptive evidence. Do not label a company a “fraudster,” “manipulator,” or “earnings trap” solely from these metrics.

---

## 8. Typed result contract

Prefer a strategy-specific typed result rather than adding fields to Graham or Momentum result models.

Illustrative result shape:

```text
FCFEarningsGrowthResult
    strategy = fcf_earnings_growth
    status                         # software/analysis status
    ticker / subject
    requested_as_of

    preferred_growth_years
    actual_growth_years_used
    minimum_growth_years
    latest_completed_fiscal_period

    annual_history[]
        fiscal_period
        operating_cash_flow
        capital_expenditures
        free_cash_flow
        diluted_eps

    historical_fcf_cagr_percent | None
    historical_eps_cagr_percent | None
    fcf_yoy_growth_percent | None
    eps_yoy_growth_percent | None

    consensus_eps_fy1 | None
    consensus_eps_fy2 | None
    forward_fy1_eps_growth_percent | None
    forward_fy2_eps_growth_percent | None

    market_capitalization | None
    market_cap_as_of | None
    fcf_yield_percent | None

    trend_classification

    screen_decision = pass | fail | indeterminate
    screen_criteria[]

    resolved_inputs / derived lineage
    warnings
```

Exact Python names should follow repository conventions after reconnaissance.

### 8.1 Analysis status behavior

Use existing project status vocabulary where it fits. Do not invent a new broad error hierarchy without need.

At minimum distinguish:

- `ok` — the analysis produced the required core evidence; one or more optional/submetrics may still be unavailable with explicit reasons;
- `input_unavailable` — required financial facts/history could not be resolved;
- `invalid_input` — invalid requested horizon/configuration or incompatible explicit input;
- `provider_error` — provider failure distinct from absent evidence.

Negative FCF or negative EPS is not automatically a software error. It is economically meaningful data. Percentage-growth/CAGR submetrics may become unavailable under the rules above while the raw series remains reportable.

For screen purposes, mathematically unavailable or missing required evidence yields `screen_decision = indeterminate` only when no other hard criterion has valid failing evidence. A valid hard failure remains `fail` even when another required criterion is unavailable.

---

## 9. Data and resolution boundary

### 9.1 Reuse Step 2.3 foundations

Step 2.4 should reuse the existing provider-neutral financial-fact, cache, resolver, provenance, fixture, and presentation patterns established in Step 2.3.

Do **not** create:

- a parallel FCF-only provider framework;
- a separate consensus-estimate architecture unless the existing fact contract proves concretely incapable of representing forecasts;
- a new strategy registry/plugin system;
- a second provenance model;
- a second cache hierarchy;
- a second CLI presentation framework.

The new strategy is allowed to prove that a current Step 2.3 name is too narrow, but a rename/generalization must be justified by concrete incompatibility rather than aesthetics.

### 9.2 Minimum new financial facts

The revised Step 2.4 core requires provider-neutral support for:

- operating cash flow / net cash provided by operating activities;
- capital expenditures;
- completed annual diluted EPS history;
- market capitalization;
- forward consensus diluted-EPS estimate for the next comparable fiscal period;
- forward consensus diluted-EPS estimate for the following comparable fiscal period.

EPS should reuse the existing annual EPS capability where semantically compatible.

Likely new semantic fields include:

```text
OPERATING_CASH_FLOW
CAPITAL_EXPENDITURES
MARKET_CAPITALIZATION
CONSENSUS_EPS
```

Do not add revenue, net income, debt, enterprise value, stock-based compensation, maintenance CapEx, or other fields unless the product-policy checkpoint explicitly promotes a secondary metric that requires them.

### 9.3 Forecast fact semantics

Consensus estimates are materially different from historical reported facts and must not be squeezed into the existing model if doing so destroys meaning.

A provider-neutral forecast fact/request must be able to represent:

- subject/security;
- metric and basis;
- forecast fiscal period;
- value/units/currency;
- consensus/provider identity;
- snapshot/observation timestamp;
- availability/retrieval timestamp;
- requested `as_of` behavior.

Historical `as_of` support for consensus estimates is allowed only if the provider supplies point-in-time estimate history or another evidence-approved mechanism. If only current consensus is available, a historical analysis request must not silently pair today's consensus with historical actuals as though it were historically knowable.

### 9.4 Derived FCF lineage

FCF is derived per fiscal period.

Each derived FCF observation must retain lineage sufficient to reconstruct:

```text
FCF
├── operating cash flow
└── normalized capital expenditures
```

Lineage must preserve:

- source/provider;
- exact provider concepts/fields;
- fiscal period start/end;
- filing/publication/availability timestamp;
- units/currency;
- retrieved/resolved timestamps;
- CapEx sign normalization;
- any duplicate/restatement selection rule.

### 9.5 `as_of` policy

Step 2.3's no-look-ahead rule remains authoritative.

For every historical fact used:

- fiscal period end alone is insufficient;
- the fact must be published/filed/available on or before requested `as_of`;
- later restatements are not eligible for an earlier historical analysis unless already available by that boundary;
- current snapshots may not masquerade as historical evidence.

For market capitalization and consensus estimates, provenance must separately establish what observation/snapshot was available at the requested boundary.

The resolver captures the analysis boundary once per deterministic assembly operation where the existing clock contract requires a single coherent execution time.

---

## 10. Provider evidence gate

Begin production integration with evidence, not field-name guessing.

SEC EDGAR remains the natural first candidate for historical financial-statement actuals because Step 2.3 already established SEC infrastructure. Analyst consensus will probably require a different provider. No production mapping is approved merely by this document.

Before accepting a production mapping, record evidence for:

| Capability | Evidence required |
| :--- | :--- |
| Operating cash flow | Exact SEC/provider concept(s), cash-flow-statement semantics, units, annual-period behavior, amended/restated filing behavior, availability timestamp |
| Capital expenditures | Exact concept(s), what expenditures are included/excluded, reported sign convention, units, period behavior, availability timestamp |
| Annual diluted EPS | Confirm reuse of the Step 2.3 evidence-approved annual diluted-EPS path or document any necessary difference |
| Period alignment | Proof that CFO and CapEx can be paired for the same completed fiscal period without mixing cumulative/interim/full-year values |
| Market capitalization | Exact provider field/derivation, security scope, currency, observation timestamp, historical/current availability |
| Consensus EPS FY1/FY2 | Exact meaning of “consensus,” fiscal-period mapping, diluted/basic basis, provider field(s), update cadence, snapshot timestamp, analyst-count/dispersion availability if any |
| Historical consensus `as_of` | Whether prior consensus snapshots are available; if not, document the limitation and reject unsupported historical-forward combinations |
| Historical `as_of` actuals | Proof that filing/availability time prevents look-ahead |
| Ticker/security identity | Preserve the Step 2.3 provider-backed subject-validation principle |
| Licensing/usage | Confirm that the selected consensus-estimate source may be used in the project's intended mode and outputs |

If SEC filings expose multiple plausible CapEx concepts, do not guess. Define and test a conservative selection rule only after evidence review.

If no acceptable consensus provider is available, do not fabricate forward estimates with an LLM. Surface the limitation and keep the screen indeterminate where forward consensus is an approved hard requirement, provided no other hard criterion already has valid failing evidence.

---

## 11. Deterministic fixtures

Add deterministic fixture evidence sufficient to test the preferred horizon plus fallback behavior.

Subject to the Section 3.2 horizon convention, fixtures should include enough annual observations to test a full 5-year compound-growth calculation and a 3-year fallback.

Fixture coverage should include:

- multi-year annual operating-cash-flow facts;
- matching annual CapEx facts;
- matching annual diluted-EPS facts;
- market capitalization with observation timestamp;
- FY1 consensus diluted-EPS estimate;
- FY2 consensus diluted-EPS estimate;
- consensus snapshot timestamps;
- compatible currencies/units;
- filing/availability timestamps;
- CapEx reported with provider-native sign and normalized expenditure lineage;
- one duplicate/restatement scenario;
- one future-published fact excluded by `as_of`;
- one missing CapEx period;
- one mismatched-period case;
- one 5-year-insufficient / 3-year-valid fallback case;
- one shorter-than-3-year insufficient-history case;
- one zero/negative prior value causing percentage growth to be unavailable;
- one negative FCF or EPS case;
- one missing FY1/FY2 consensus case;
- one historical `as_of` request where current-only consensus cannot be used;
- one negative/zero market-cap validation case;
- explicit screen pass, fail, and indeterminate cases;
- one provider-error path.

No fixture execution may silently fall back to live network data.

---

## 12. Pure calculation responsibilities

Keep deterministic arithmetic independent from data access.

Candidate pure functions:

```text
compute_free_cash_flow(operating_cash_flow, capital_expenditures)
compute_growth_percent(current, prior)
compute_cagr(beginning, ending, years)
compute_fcf_yield(free_cash_flow, market_capitalization)
classify_fcf_earnings_growth(...)
evaluate_screen_criterion(...)
evaluate_fcf_earnings_screen(...)
```

If a smoothing/trend statistic is approved, it must also be a pure deterministic function.

Pure functions must:

- reject non-finite numeric inputs;
- never perform provider/cache/filesystem/clock I/O;
- never infer periods;
- never invent missing values;
- return explicit unavailable/invalid semantics rather than NaN or infinity.

CapEx sign normalization belongs at the provider/resolution boundary, not hidden inside a generic subtraction formula, so the pure FCF calculator receives a positive expenditure amount.

Screen evaluation must consume already-resolved metric results plus an explicit typed screen policy. It must not reach into provider data or hide thresholds in presentation code.

---

## 13. Direct CLI contract

Proposed command:

```text
financial-agents fcf-growth TICKER [options]
```

Initial options should remain minimal until the screen policy is locked. Likely options:

```text
--growth-years INTEGER          # proposed preferred default 5
--minimum-growth-years INTEGER  # proposed default 3
--as-of DATE_OR_TIMESTAMP
--data-provider PROVIDER_ID
--consensus-provider PROVIDER_ID
--no-cache
--details
--diagnostics
--json
```

Rules:

- positional ticker remains the preferred identity style established in Step 2.3;
- default analysis prefers the approved 5-year horizon and truthfully falls back to the longest approved valid horizon down to 3 years;
- the actual horizon used is always exposed;
- unsupported requested horizons and insufficient history are reported through the appropriate software/analysis status (`invalid_input` or `input_unavailable`) and do not automatically imply screen `FAIL`;
- do not add threshold flags until there is a real user need for per-run threshold customization; first lock a named default screen policy in configuration/code;
- do not add awkward unperiodized repeated numeric override flags merely to mimic Graham;
- if series/forecast overrides are later needed, design an explicit period-tagged representation rather than accepting ambiguous ordered floats;
- normal failure output must not expose provider-library implementation details or framework tracebacks.

A future batch/universe command may consume this per-security screen, but is not required for Step 2.4.

---

## 14. Investor-facing presentation

Reuse the Step 2.3 progressive-disclosure grammar with a strategy-specific presenter.

### 14.1 Default concise view

Recommended information order:

1. ticker + `Free Cash Flow & Earnings Growth`;
2. **screen result: PASS / FAIL / INDETERMINATE**;
3. historical horizon actually used;
4. historical diluted-EPS growth;
5. FY1/FY2 consensus EPS estimates and forward growth where meaningful;
6. historical FCF growth/trajectory;
7. current FCF yield;
8. short earnings-versus-FCF comparison;
9. high-level source/freshness line;
10. material warnings / unavailable criterion reasons;
11. short limitation.

Example shape only:

```text
KO — Free Cash Flow & Earnings Growth
Screen: PASS
Historical window: 5-year growth horizon

Diluted EPS growth:              +X.X% CAGR
Consensus EPS FY1:               $Y.YY  (+A.A% vs latest actual)
Consensus EPS FY2:               $Z.ZZ  (+B.B% vs FY1 consensus)
Free cash flow growth:           +C.C% CAGR
FCF yield:                        D.D%

Trend: Historical earnings and free cash flow are both expanding.
Source: SEC EDGAR actuals; <consensus provider> estimates; <market-data provider> market cap
Note: FCF = operating cash flow - capital expenditures.
```

A failing or indeterminate screen should identify the decisive criterion in concise form without dumping all diagnostics.

Do not hard-code this exact formatting before presenter tests; preserve the common visual grammar rather than exact whitespace.

### 14.2 `--details`

Show:

- per-criterion screen results, observed values, rules, and reasons;
- annual CFO, normalized CapEx, derived FCF, and diluted-EPS series;
- fiscal periods;
- FCF growth endpoints and actual horizon used;
- any approved smoothing/trend statistic alongside raw FCF;
- FY1/FY2 consensus EPS values, forecast periods, snapshot timestamp, and derived forward growth;
- market capitalization, valuation date, and FCF-yield numerator period;
- provider concepts/fields;
- availability dates;
- CapEx normalization;
- derived lineage;
- fallback-horizon warnings;
- other material limitations.

### 14.3 `--diagnostics`

Show software resolution behavior only:

- cache behavior;
- provider attempts;
- selection/rejection reasons;
- derivation steps;
- forecast-period matching;
- horizon fallback decisions;
- unavailable/error classification.

Do not confuse cache state with financial source provenance or screen failure with software failure.

### 14.4 `--json`

Use the existing machine-readable presentation conventions and explicit schema versioning policy.

Requirements:

- unavailable growth metrics are JSON `null` with a structured reason, never `NaN`;
- screen decision and criterion results are explicit;
- historical actuals and forward consensus estimates are separate arrays/objects;
- numerator/denominator dates for FCF yield are explicit;
- actual growth horizon used is explicit.

---

## 15. Testing requirements

At minimum test:

1. exact FCF arithmetic;
2. CapEx sign normalization outside the pure calculator;
3. exact YoY growth;
4. exact 5-year preferred CAGR behavior under the approved horizon convention;
5. exact 3-year fallback behavior;
6. shorter-than-3-year history → insufficient;
7. zero/negative prior denominator → percentage growth unavailable;
8. zero/negative CAGR endpoint → CAGR unavailable;
9. negative latest FCF remains reportable;
10. exact FCF-yield arithmetic;
11. nonpositive/invalid market-cap denominator is rejected explicitly;
12. incompatible periods are rejected;
13. incompatible units/currencies are rejected;
14. missing CapEx makes the affected FCF period unavailable;
15. strict `as_of` excludes later filings/restatements;
16. eligible duplicate/restatement selection is deterministic;
17. annual diluted-EPS reuse preserves basis/provenance;
18. FY1/FY2 consensus periods are mapped deterministically;
19. exact forward-growth derivation under the approved rule;
20. current-only consensus cannot masquerade as historical consensus evidence;
21. missing required consensus evidence with no other valid hard failure → screen indeterminate, not fabricated fail;
22. screen pass with all hard criteria satisfied;
23. screen fail with valid evidence and at least one hard criterion missed;
24. screen indeterminate with required evidence unavailable/nonmeaningful and no valid hard failure;
25. valid hard failure plus another required criterion unavailable → screen fail;
26. earnings-versus-FCF divergence classification uses neutral deterministic semantics;
27. cache/provider/derived lineage remains truthful;
28. concise/details/diagnostics/JSON presentation semantics;
29. invalid/missing ticker and provider errors produce one clean user-facing failure surface;
30. no live provider or LLM calls in automated tests.

If a CapEx-smoothing/trend statistic is approved, add exact tests for its calculation, missing-history behavior, and presentation.

After implementation, run the complete repository quality gate required by the milestone plan.

---

## 16. Proposed implementation slices

### Slice A — reconnaissance and policy lock

Inspect the current post-Step-2.3 repository and answer:

- which Step 2.3 fact/resolver/provenance types can be reused unchanged;
- which enums/requests need minimal extension;
- whether `ValuationFactsProvider` naming is tolerable for the new strategy or a concrete incompatibility exists;
- which SEC/provider concepts plausibly represent CFO and CapEx;
- how annual period pairing/restatement selection currently works;
- which provider can supply market capitalization with adequate timestamp semantics;
- which provider(s) can supply FY1/FY2 consensus diluted-EPS estimates with adequate period, snapshot, and licensing semantics;
- whether historical consensus snapshots are supported;
- what presenter/CLI patterns are reusable;
- the exact files likely to change.

Make no production changes.

**Stop for human review and resolve all Section 3 policy locks that affect Slice B before implementation begins.**

### Slice B — pure FCF/growth/yield math and screen semantics

Implement:

- pure FCF calculation;
- percentage-growth helper;
- CAGR helper;
- FCF-yield helper;
- approved FCF trajectory/smoothing helper, if any;
- typed strategy result and submetric-status semantics;
- typed screen policy / criterion result / screen decision;
- deterministic unit tests.

No provider or CLI work.

### Slice C — historical financial-fact extension, resolution, and fixtures

Minimally extend the existing provider-neutral fact/resolution system for CFO and CapEx, add period-aligned FCF derivation with lineage, annual EPS/FCF history assembly, preferred-horizon/fallback resolution, market-cap fact semantics, and deterministic multi-year fixtures.

No production provider guessing.

### Slice D — provider evidence and forward-consensus integration

Evidence and implement the minimum safe production path:

- preferably reuse SEC EDGAR infrastructure for historical CFO/CapEx/annual EPS if proven compatible;
- integrate an evidence-approved market-cap source;
- integrate evidence-approved FY1/FY2 consensus EPS data;
- enforce forecast-period and `as_of` semantics;
- preserve provider/source boundaries explicitly.

Unsupported filings, securities, forecast histories, or provider semantics remain unavailable rather than guessed.

### Slice E — strategy assembly and hard-screen evaluation

Assemble the historical, valuation, and forward-consensus evidence into the strategy result and evaluate the approved hard-screen criteria.

Confirm explicit pass/fail/indeterminate behavior across deterministic fixtures before investor presentation work.

### Slice F — investor CLI and presentation

Add `fcf-growth` direct execution plus concise/details/diagnostics/JSON output using the approved shared grammar.

Perform representative live validation only after deterministic tests are green.

### Slice G — documentation and full gate

Synchronize documentation, run full Ruff/format/strict-mypy/pytest/diff gates, review the complete Step 2.4 diff, and stop for explicit human completion approval before Step 2.5 Golden work begins.

---

## 17. Acceptance criteria

Step 2.4 is complete only when:

- [ ] the Section 3 policy locks are explicitly resolved;
- [ ] the strategy is named and typed independently from Momentum and Graham;
- [ ] screen decision is represented separately from software/calculation status;
- [ ] explicit pass/fail/indeterminate criterion semantics are tested;
- [ ] the canonical initial `FCF = CFO - CapEx` definition is explicit and tested;
- [ ] CapEx provider sign conventions are normalized transparently;
- [ ] annual CFO and CapEx are paired only across compatible fiscal periods;
- [ ] the preferred 5-year historical horizon and 3-year minimum/fallback are implemented under an explicitly approved year-count convention;
- [ ] annual diluted-EPS growth uses an explicit documented basis;
- [ ] FY1/FY2 consensus diluted-EPS estimates use explicit provider, forecast-period, and snapshot semantics;
- [ ] forward growth derivation is explicit and tested;
- [ ] historical `as_of` does not silently use current-only consensus estimates;
- [ ] FCF yield uses an explicit numerator basis, market-cap denominator, currency, and valuation timestamp;
- [ ] negative/zero values are represented truthfully without NaN/infinity or fabricated fallbacks;
- [ ] the screen does not rely solely on a single latest FCF year;
- [ ] any approved smoothing/trend metric is separately named and does not rewrite raw annual FCF;
- [ ] strict `as_of` prevents look-ahead for historical facts and for any provider capability claiming point-in-time consensus support;
- [ ] derived FCF retains full component lineage;
- [ ] the Step 2.3 provider/cache/resolver/provenance architecture is reused or minimally extended rather than duplicated;
- [ ] deterministic fixtures cover pass, fail, indeterminate, preferred horizon, fallback horizon, missing data, period mismatch, negative/zero growth, restatement, consensus, market-cap, and historical-boundary cases;
- [ ] a representative supported production ticker can run the analysis without manual financial-statement arithmetic;
- [ ] concise/details/diagnostics/JSON output follows the established investor-facing grammar;
- [ ] actual annual history and forward consensus evidence are visible enough for qualitative investor judgment after the screen;
- [ ] automated tests make no live network or LLM calls;
- [ ] full repository quality gates pass;
- [ ] documentation matches implemented semantics;
- [ ] the final Step 2.4 diff receives explicit human approval.

After approval, stop. Step 2.5 Golden-Suite implementation begins only as a separately reviewed step.

---

## 18. Explicit non-goals

Step 2.4 does not include unless separately approved during the policy checkpoint:

- discounted cash-flow valuation;
- terminal-value modeling;
- cost-of-capital estimation;
- LLM-generated growth forecasts;
- enterprise-value-based FCF yield / FCFF valuation;
- FCFE modeling;
- owner-earnings normalization;
- maintenance-versus-growth CapEx estimation;
- stock-based-compensation adjustment;
- working-capital normalization beyond the CFO reported in the canonical FCF formula;
- FCF-to-net-income as a required core ratio;
- FCF margin as a required core ratio;
- P/FCF as a required core metric;
- a broad named-investor methodology;
- arbitrary composite scoring/ranking;
- claims that the screen proves accounting fraud or manipulation;
- investment recommendations;
- market-wide universe ingestion/batch scanning unless separately approved;
- Golden Suite/evaluator implementation;
- durable SQLite persistence/migrations;
- watchlists or Analysis Run persistence;
- a generic strategy/plugin registry;
- unrelated refactoring.

The purpose is to add one useful, auditable screening strategy that combines cash-flow reality, earnings growth, forward expectations, and a simple FCF valuation ratio while proving the existing architecture can accommodate the necessary historical and forecast data cleanly.
