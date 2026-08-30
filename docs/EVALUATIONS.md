# Evaluations & Golden Suite

**Status:** Milestone v0.2 Step 2.5 scaffold; benchmark implementation has not yet begun<br/>
**Governing sequence and acceptance criteria:** [Milestone v0.2 Implementation Plan](project/milestones/v0.2/IMPLEMENTATION_PLAN.md#4518-implementation-sequence)<br/>
**Formal implementation slices:** [Step 2.5 Golden Suite Slice Plan](project/milestones/v0.2/STEP_2_5_GOLDEN_SUITE_SLICE_PLAN.md)<br/>
**Architecture:** [Financial Data Agents Architecture](project/ARCHITECTURE.md#7-golden-suite-architecture-step-25)

## 1. Purpose

The Golden Suite is the project's reproducible benchmark for the approved v0.2 analytical strategies:

- Momentum;
- the Graham Number;
- the Graham growth-value method; and
- Free Cash Flow & Earnings Growth.

It evaluates deterministic financial behavior separately from local-model strategy and tool selection. It is an evaluation system, not a production data store, production cache, trajectory-log archive, or investor-facing Analysis Run library.

Step 2.5 implementation lives under `src/evaluation/`. The package consumes the existing strategy, market-data, financial-fact, provenance, resolution, tool-dispatch, and telemetry boundaries. It must not create a parallel strategy framework or force heterogeneous strategy results into one production result model.

## 2. Current implementation status

The tracked `src/evaluation/` package boundary and this guide exist so later implementation tasks can be limited to explicit artifacts. Existing deterministic market-data, Graham financial-fact, and annual FCF financial-fact providers have been extracted into `src/evaluation/fixtures/` without changing their values or behavior. They are reusable fixture foundations, not yet the typed Golden Case catalog.

Production strategy handlers are registered outside the evaluation and test packages through `src/orchestrator/analysis_tools.py`. The explicit tool names are `analyze_momentum`, `analyze_graham_number`, `analyze_graham_growth_value`, and `analyze_fcf_earnings_growth`. Their Pydantic argument models are available through the read-only `ANALYSIS_TOOL_ARGUMENT_MODELS` mapping. `register_analysis_tools(...)` attaches dependency-injected handlers to the existing `AsyncToolDispatcher`; the same seam accepts production adapters or deterministic fixture-backed analyzers and resolvers. Each handler preserves its strategy's native typed result rather than introducing a generic strategy-result model.

Typed Golden Case models, evaluators, reports, execution harnesses, CLI commands, and empirical local-model evaluation have not yet been implemented.

The implementation proceeds in bounded reviewed slices. The minimum heterogeneous deterministic suite must work and stop for human review before case expansion or optional local-model evaluation continues.

## 3. Execution modes

The suite has two explicitly separate modes.

### Deterministic/no-LLM mode

This mode validates fixture loading, shared data contracts, strategy calculations, expected numerical values, evaluator behavior, aggregation, and report serialization without calling an LLM or a live market-data provider.

Deterministic/no-LLM execution cannot measure LLM strategy or tool selection. Its strategy-selection component must be reported as `not_measured`; scripted execution or direct invocation must never be presented as a passing LLM-selection result.

### Real-local-Ollama mode

This optional empirical mode measures observable strategy, method, tool, and argument selection through the production orchestration and tool-dispatch boundaries as far as practical. It records the model identifier, Ollama configuration, relevant sampling settings, repetition policy, and nondeterministic outcomes.

Real-local-Ollama execution remains separate from deterministic regression tests and is not mandatory CI unless explicitly configured. Deterministic tests mock all local-model endpoints.

## 4. Evaluation components

Reports distinguish at least:

- strategy/tool-selection correctness;
- Graham method-selection correctness where applicable;
- deterministic numerical correctness;
- fixture/data failures;
- other execution failures; and
- overall case pass/fail.

Component denominators include only cases for which the component is actually measurable and applicable. In particular, `not_measured` strategy selection in deterministic/no-LLM mode is not silently converted to pass or fail and is not counted as an observed selection attempt.

The aggregate pass rate remains the number of executed cases satisfying all required case-level criteria divided by the total number of executed benchmark cases. Mode-specific required criteria and component metrics must remain explicit in the report. The milestone's ≥90% target is a measurement target and must not be used to weaken expectations, remove useful failing cases, or tune the benchmark instrument until a model passes.

## 5. Golden cases and fixtures

Every Golden Case is typed and identifies its case ID, description, task or prompt, fixture IDs, expected strategy/tool behavior, expected deterministic outputs, tolerances, required/permitted/forbidden behavior, pass rules, and optional tags.

Golden fixtures are tracked, deterministic, reviewable benchmark evidence. They must:

- use the shared market-data and financial-fact contracts;
- include only evidence required by their cases;
- retain relevant provider, source, retrieval, period, currency, timezone/date, transformation, schema-version, and reference metadata;
- fail explicitly when requested evidence is absent;
- never fall back to a live provider or mutable production cache;
- remain independent of SQLite and later production persistence; and
- preserve explicit `as_of` boundaries wherever dates affect eligibility.

Benchmark fixture implementations belong to the importable `src/evaluation/fixtures/` boundary rather than under `tests/`. Test modules may construct additional small fakes, but the runtime evaluation package must not import test code. The extracted deterministic providers preserve the approved provider-neutral contracts and remain separate from production cache data.

Expected numerical values are benchmark contract data. They must be verified using transparent reference calculations, a separate reference implementation, or sufficiently simple manual calculations. Production functions under test must never generate their own expected values. Tolerances are case-appropriate absolute and/or relative tolerances rather than one universal constant.

## 6. Initial benchmark composition

The minimum heterogeneous set defined by the milestone plan includes Momentum success and boundary behavior; the default and TTM Graham Number variants; Graham `not_applicable`, growth-value, missing-price, method-selection, and input-resolution behavior; and FCF/Earnings Growth success, nonmeaningful or insufficient growth, period alignment, and historical `as_of` behavior.

At least one case must materially discriminate the requested strategy from a plausible wrong strategy. A discriminating case may also satisfy another required minimum category when that overlap is explicit and useful.

This minimum produces approximately 11–12 cases depending on deliberate overlap and therefore already falls within the approved initial target of 10–18 high-signal cases. Expansion beyond the reviewed minimum is review-driven, not automatic. Each added case must document the failure mode or signal it contributes.

## 7. Telemetry and reporting

End-to-end evaluation uses Step 2.1 trajectory telemetry as observable execution evidence where available. Telemetry may provide selected tool names, validated arguments, structured results, errors, recovery events, step boundaries, and run identity. It is observational evidence and must never control financial execution or substitute for benchmark expectations. Private reasoning and model-specific `<think>` content are not evaluation inputs.

The machine-readable report contains the suite and fixture-set versions, execution timestamp, execution mode, applicable model/provider configuration, case totals, component metrics, end-to-end case score, per-case results, classified failure reasons, and run or trajectory identity where available.

Generated reports and raw trajectories are local execution artifacts unless a separately reviewed sanitized result record is intentionally added. Secrets, API keys, raw operational logs, and raw trajectory logs must never be committed.

## 8. Evaluator self-test

The evaluator includes a regression test proving that an intentionally incorrect observed result is detected. The synthetic incorrect result is test input, not a normal benchmark case, and remains outside the benchmark denominator so a correctly detected failure does not make CI fail.

## 9. CLI and CI contract

The Step 2.5 CLI is not implemented yet. When its reviewed slice lands, the normal `uv run` workflow will support the full suite, one named case, deterministic/no-LLM mode, optional real-local-Ollama mode, and an explicit report location. Required benchmark failures return a non-zero process status.

Deterministic/no-LLM execution is the headless CI boundary. Real-model and network-dependent evaluation is recorded separately and is not a mandatory CI dependency unless explicitly configured.

## 10. Maintenance rules

- Add or change a case only with a documented reason and independently verified expectations.
- Preserve stable case IDs once results have been recorded.
- Version material case-schema, fixture-set, evaluator, and report-contract changes deliberately.
- Do not silently refresh fixture evidence or replace historical values with current provider data.
- Do not remove a useful failing case merely to improve a reported score.
- Keep deterministic and empirical local-model results clearly separated.
- Run the complete repository quality gate before Step 2.5 completion review.
