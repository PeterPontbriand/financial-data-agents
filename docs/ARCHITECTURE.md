# Financial Data Agents Architecture

**Related roadmap:** `MASTER_PLAN.md`  
**Active implementation detail:** `milestones/v0.2/IMPLEMENTATION_PLAN.md`  
**Step 2.3 implementation specification:** `milestones/v0.2/STEP_2_3_GRAHAM_DESIGN.md`  
**Rationale:** `DISCOVERY_WORKBOOK.md`  
**Last updated:** 2026-08-20  
**Current status:** Step 2.2 implementation complete; Step 2.3 target design approved and implementation uncommitted. Work proceeds in reviewable slices, with production provider mappings held behind the evidence gate.

This document describes current boundaries and approved near-term target seams. It does not claim that Step 2.3 target components already exist, and it does not override the active milestone plan's sequencing or review gates.

---

## 1. Architectural invariants

1. **LLM orchestration, deterministic execution:** The LLM plans/selects tools and synthesizes results; Python performs calculations, validation, data processing, and persistence.
2. **Typed boundaries:** Tool/analyzer/data inputs and outputs are explicitly typed at application boundaries.
3. **Heterogeneous strategies:** Different financial strategies may have different config/data/result shapes. The architecture must not make every analysis Momentum-shaped.
4. **No speculative strategy framework:** Reuse the existing `BaseAnalyzer` and current tool dispatch path unless implementation proves a new abstraction is necessary.
5. **Provider isolation:** Historical-price access remains behind `BaseDataClient`; Step 2.3 valuation facts use a dedicated provider/resolution boundary rather than enlarging a price-history-shaped interface.
6. **Historical prices, quotes, fundamentals, and macro series are distinct capabilities:** A composed valuation façade may coordinate narrow providers, but no upstream service is assumed to supply every capability.
7. **Evaluation is not persistence:** Golden fixtures, evaluation results, trajectory telemetry, and production market-data storage are separate concerns.
8. **Local-LLM boundary:** The LLM cannot directly execute shell/code or access the external network. Registered data tools may perform controlled provider access.
9. **Telemetry is observational:** Telemetry failures must not change business execution semantics.
10. **Light Mode first:** Core useful analysis must remain viable under the documented Light Mode path.
11. **Method-explicit financial semantics:** Graham Number and Graham growth value retain distinct names, inputs, typed results, and limitations.
12. **Time-bounded provenance:** Resolved inputs preserve source, reporting/observation and availability dates, transformations, cache/override state, and requested analysis `as_of`.

---

## 2. Current and near-term architecture

```text
                               CLI / caller
                                   │
                                   ▼
                         Agent Orchestrator
                   context + structured-output policy
                                   │
                                   ▼
                         Tool / analysis dispatch
                                   │
                   ┌───────────────┴───────────────┐
                   ▼                               ▼
          MomentumAnalyzer                    Graham analysis
          (implemented)                    (Step 2.3 target)
          SMA/crossover                 ┌─────────┴─────────┐
                   │                    ▼                   ▼
                   │              Graham Number       Growth value
                   │                    │                   │
                   │                    └─────────┬─────────┘
                   │                              ▼
                   │                    typed method result
                   │                              ▲
                   │                              │
                   │                       InputResolver
                   │              override → cache → provider
                   │                              │
                   │                    resolved inputs +
                   │                       provenance
                   │                              ▲
                   │                              │
                   │              ValuationFactsProvider boundary
                   │               quote / fundamentals / macro
                   │                              │
                   ▼                              ▼
            BaseDataClient                  live + fixture
          historical prices                  capabilities
                   │                              │
                   └──────────────┬───────────────┘
                                  ▼
                       Step 3.1 durable cache /
                         production persistence
```

`BaseAnalyzer` is the existing common analyzer abstraction. The diagram does **not** imply a new strategy registry, plugin system, factory hierarchy, or unified strategy-result model.

---

## 3. Core entities and boundaries

### `BaseAnalyzer`
Existing abstract analysis boundary. A strategy owns:
- its configuration model;
- deterministic calculation;
- typed result/metrics;
- only the data capabilities it actually requires.

### `MomentumAnalyzer`
Existing deterministic SMA/crossover analyzer. It consumes historical market data and returns Momentum-specific metrics.

### Graham analysis (Step 2.3 target)
The approved Graham family has two method identifiers:

- `graham_number` — default screening-ceiling method using three-year-average EPS by default plus BVPS;
- `graham_growth_value` — explicit secondary method using normalized EPS, user-supplied growth under the initial policy, and a documented current AAA-yield observation.

The implementation may use separate analyzer/config/result models or a typed discriminated union, but invalid cross-method combinations must not be representable. The uncommitted `GrahamValueAnalyzer` interface is not a compatibility constraint and must not remain misleading merely because it already exists locally.

Graham is intentionally not required to return `TrendStatus` or consume a historical DataFrame merely to look like Momentum.

### `BaseDataClient`
Existing provider boundary for historical market prices. Under the selected Step 2.3 Option A direction, it remains price-history focused rather than becoming the owner of fundamentals, valuation quotes, macro series, and cache policy.

Do not implement current quote retrieval by invoking a one-day historical request merely to avoid defining the correct valuation-input capability.

### `ValuationFactsProvider` boundary (Step 2.3 target)
A dedicated provider-neutral valuation-input boundary supplies or composes the minimum quote, company-fundamental, and macro-series capabilities required by the two Graham methods.

The exact interfaces and production field mappings remain subject to the evidence-gathering planning phase. A concrete adapter must not pretend that one upstream provider supplies a capability it cannot document.

### `InputResolver` (Step 2.3 target)
Resolves each required field independently using:

```text
explicit override → valid cache → configured provider → unavailable
```

Calculators receive resolved values and do not perform I/O. The resolver enforces requested `as_of` boundaries and preserves typed provenance.

### Valuation cache seam (Step 2.3 target)
A narrow in-memory/fixture-backed `get`/`put` seam proves precedence, temporal eligibility, and provenance. The resolver—not the cache—owns provider fallback. Durable SQLite-backed caching remains Step 3.1.

### Resolved input and provenance models (Step 2.3 target)
Typed records preserve value, units/currency, source kind, provider field/series, reporting/observation period, availability/filing date where supplied, analysis `as_of`, retrieval time, transformations/derived lineage, and override/cache state.

### Fixture-backed data capabilities
Introduced minimally in Step 2.3 to prove the historical-price and valuation-input contracts:
- deterministic;
- historical data for Momentum;
- quote, EPS history/TTM EPS, BVPS facts/components, and AAA-yield observations for Graham;
- override/cache/provider/unavailable resolution paths;
- realistic reporting, availability, `as_of`, and retrieval metadata;
- explicit failure when data is absent;
- no live network fallback.

Step 2.4 reuses this foundation for Golden cases.

### `TrajectoryEvent` / `TrajectoryRecorder` / `TrajectorySink`
Step 2.1 structured telemetry components. JSONL is the initial sink; SQLite is added in Step 3.1.

Telemetry records observable execution evidence and does not provide benchmark ground truth.

---

## 4. Structured-output boundary

Step 2.2 establishes structured-output enforcement with layered defenses:

1. use native Ollama/provider schema constraints when capability is confirmed;
2. retain Pydantic validation at the application boundary;
3. use the configured prompt-based schema fallback when native capability is unavailable or unknown;
4. retain legacy compatibility parsing only as the final fallback where required.

Empirical model-by-model validation of native-schema behavior for the supported Light Mode configuration remains a non-blocking validation item before Step 3.5 completion.

Do not rewrite the runtime around a model-specific assumption merely to make one model pass.

---

## 5. Module layout

```text
src/
├── config.py
├── core/
│   ├── constants.py
│   └── telemetry/
│       ├── models.py
│       ├── recorder.py
│       ├── run_context.py
│       ├── redaction.py
│       └── sinks/
├── llm/
├── tools/
├── orchestrator/
├── data/
│   ├── base_client.py
│   ├── yfinance_client.py
│   ├── massive_client.py
│   └── repositories/
├── analysis/
│   ├── base.py
│   ├── momentum/
│   └── graham_value/          # Step 2.3 target; exact files follow approved plan
├── reporting/
└── utils/
```

Step 2.3 adds/refines Graham under `src/analysis/` according to current package conventions. The selected Option A valuation-provider/resolver/cache seams should live with the narrowest responsible package after the worktree and provider feasibility are inspected; this diagram does not pre-authorize speculative files. Step 3 persistence/repositories remain under `src/data/repositories/`.

---

## 6. Data flow and persistence boundaries

The project distinguishes:

```text
External Provider
      │
      ▼
Provider Adapter Boundary
      │
      ├── BaseDataClient ───────────────► historical series ─► Momentum
      │
      └── ValuationFactsProvider
              │
              ├── quote
              ├── company fundamentals
              └── macro observation
                      │
                      ▼
              InputResolver ◄── override / cache
                      │
                      ▼
               resolved inputs
                      │
                      ▼
             deterministic Graham method
                      │
                      ▼
                typed method result
```

Separately:

```text
Golden fixture data ──► fixture adapter ──► analyzer/tool execution
trajectory events   ──► telemetry sink
production data     ──► SQLite/cache repositories
evaluation result   ──► Golden report/artifact
```

These stores/artifacts must not be collapsed merely because they can all be serialized.

---

## 7. Golden-Suite architecture (Step 2.4)

Step 2.4 consumes the stable Step 2.3 contracts.

```text
Golden Case
   │
   ├── prompt/task
   ├── fixture IDs
   ├── expected strategy/tool behavior
   └── independently verified numeric expectations
   │
   ▼
real orchestration path
   │
   ├── structured strategy/tool evidence
   └── deterministic result
   │
   ▼
Evaluator
   ├── strategy/tool-selection score
   ├── Graham method-selection score
   ├── numerical-correctness score
   └── overall case pass/fail
```

Deterministic/no-LLM tests validate fixtures, contracts, analytics, evaluator behavior, and report serialization. They cannot measure actual model strategy selection.

Real-local-Ollama evaluation is an empirical mode and remains separate from deterministic regression/CI tests unless explicitly configured.

The ≥90% target is a measurement target, not permission to weaken cases until a model passes.

---

## 8. Logging and telemetry boundary

Operational logging and trajectory telemetry remain separate:

```text
Agent Runtime
   │
   ├── operational logging ──► human-readable diagnostics
   │
   └── trajectory telemetry ─► machine-readable execution evidence
                                ├── JSONL (Step 2.1)
                                └── SQLite (Step 3.1)
```

Telemetry may capture observable provider/model metadata, prompts/completions, tool arguments/results, latency, and exposed token metrics subject to retention/redaction policy.

Private model reasoning is never reconstructed.

---

## 9. Failure and reliability boundary

- Recoverable failures may enter a bounded retry/repair path.
- Non-recoverable failures halt with structured diagnostics.
- Step 2.5 owns hard execution/time/error caps.
- The configured limits are authoritative; runtime documents must not invent a separate fixed turn limit.
- Telemetry sink failures fail open.

---

## 10. Development guardrails

- Preserve existing behavior outside the active step.
- Use the smallest change that satisfies the current milestone plan.
- Do not create a generic strategy registry merely to support Momentum + Graham.
- Do not collapse the two Graham methods behind ambiguous names or optional-field bags.
- Keep calculators free of provider/cache/CLI I/O.
- Enforce requested `as_of` as an information boundary; do not substitute later current facts.
- Do not assume yfinance or any one adapter supplies a documented AAA macro series.
- Do not build Step 2.4 evaluator/reporting work during Step 2.3.
- Do not build Step 3.1 production persistence/cache during Step 2.3/2.4.
- Use `src/data/repositories/` for the planned repository layer.
- Run Ruff, `mypy --strict`, and pytest according to the active milestone plan.
