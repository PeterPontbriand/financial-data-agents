# Evaluations & Golden Suite

**Status:** Milestone v0.2 Step 2.5 is paused at Gate M for human re-review; the approved Slice H correction is implemented and verified in the working tree<br/>
**Governing sequence and acceptance criteria:** [Milestone v0.2 Implementation Plan](project/milestones/v0.2/IMPLEMENTATION_PLAN.md#4518-implementation-sequence)<br/>
**Formal implementation slices:** [Step 2.5 Golden Suite Slice Plan](project/milestones/v0.2/STEP_2_5_GOLDEN_SUITE_SLICE_PLAN.md)<br/>
**Current gate decision:** [Step 2.5 Gate M Review](project/milestones/v0.2/STEP_2_5_GATE_M_REVIEW.md)<br/>
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

The tracked `src/evaluation/` package now contains typed Golden cases and expectation models, independently reviewed expected-value evidence, numerical and method/tool evaluators, aggregate result/report models, deterministic fixture composition, an evaluator self-test, and a deterministic runner. Existing deterministic market-data, Graham financial-fact, and annual FCF financial-fact providers live in `src/evaluation/fixtures/` without becoming production cache data.

Production strategy handlers are registered outside the evaluation and test packages through `src/orchestrator/analysis_tools.py`. The explicit tool names are `analyze_momentum`, `analyze_graham_number`, `analyze_graham_growth_value`, and `analyze_fcf_earnings_growth`. Their Pydantic argument models are available through the read-only `ANALYSIS_TOOL_ARGUMENT_MODELS` mapping. `register_analysis_tools(...)` attaches dependency-injected handlers to the existing `AsyncToolDispatcher`; the same seam accepts production adapters or deterministic fixture-backed analyzers and resolvers. Each handler preserves its strategy's native typed result rather than introducing a generic strategy-result model.

The corrected minimum contains fifteen stable case IDs across Momentum, both Graham methods, Graham resolution, and FCF/Earnings Growth. Slice H adds a narrowly typed expected-domain-outcome contract, integrates it with deterministic execution/reporting, corrects the five reviewed boundary cases, completes the four-route ETF scenario, and provides one internal canonical catalog/request builder and report entry point. The canonical deterministic report passes all 15 cases; the complete repository gate passes. Gate M remains human-owned and is not yet approved.

P1 hardening is complete and approved. Its evidence, mappings, implementation decisions, and review record are in the [P1 Instrument Applicability Mapping Record](project/milestones/v0.2/STEP_2_5_P1_INSTRUMENT_APPLICABILITY_MAPPING_RECORD.md). A known ETF remains applicable to Momentum but is `not_applicable` to both Graham methods and the existing company-level FCF Growth strategy. Unknown kind remains fail-open; it is never guessed from missing facts, a ticker, or a name.

P1 does not add persistence or another strategy. P2 — durable instrument profiles and a distinct ETF aggregate FCF-growth strategy — is planned only after Step 3.1. P2 may later extend the reviewed suite through the normal human-directed case-expansion process; it must not change existing case definitions, silently substitute for company-level FCF Growth, or turn production cache data into Golden fixtures.

Slice H has corrected the Gate M defects, added the three missing ETF routes, produced one canonical fifteen-case deterministic report, passed the complete repository gate, and stopped again for human Gate M review. Optional local-model evaluation, CLI work, and completion remain blocked.

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

Expected native domain outcomes are benchmark results, not exceptions to the
benchmark. A case designed to prove `input_unavailable` or `not_applicable`
passes only when the exact expected status and material reason/availability
contract is observed. The same observed status is a classified failure when the
case expected success. Correct non-success domain outcomes must not be converted
automatically into fixture or execution failures.

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

Instrument-profile fixtures retain the normalized kind, raw provider classification, provider identity, and resolution timestamp required to audit applicability. A deterministic known-ETF case must obtain ETF status from that fixture evidence; absence of company facts alone is not ETF evidence.

Benchmark fixture implementations belong to the importable `src/evaluation/fixtures/` boundary rather than under `tests/`. Test modules may construct additional small fakes, but the runtime evaluation package must not import test code. The extracted deterministic providers preserve the approved provider-neutral contracts and remain separate from production cache data.

Expected numerical values are benchmark contract data. They must be verified using transparent reference calculations, a separate reference implementation, or sufficiently simple manual calculations. Production functions under test must never generate their own expected values. Tolerances are case-appropriate absolute and/or relative tolerances rather than one universal constant.

## 6. Initial benchmark composition

The corrected fifteen-case set includes Momentum success and boundary behavior; the default and TTM Graham Number variants; Graham Number `not_applicable`, growth-value, missing-price, and input-resolution behavior; FCF/Earnings Growth success, nonmeaningful growth, period alignment, and historical `as_of` behavior; and the three additional ETF routes below.

The Gate M review established that one Graham-only ETF case did not prove the
cross-strategy applicability contract. Slice H added three cases against the same
reviewed ETF profile boundary: Momentum remains applicable, while Graham growth
value and company-level FCF Growth return their native `not_applicable` outcomes.
Together with the existing Graham Number case, the scenario covers all four
routes without treating the ticker as invalid or substituting an aggregate ETF
strategy.

At least one case must materially discriminate the requested strategy from a plausible wrong strategy. A discriminating case may also satisfy another required minimum category when that overlap is explicit and useful.

The corrected minimum contains fifteen cases, within the approved initial target of 10–18 high-signal cases. Further expansion remains review-driven, not automatic. Each added case must document the failure mode or signal it contributes.

## 7. Telemetry and reporting

End-to-end evaluation uses Step 2.1 trajectory telemetry as observable execution evidence where available. Telemetry may provide selected tool names, validated arguments, structured results, errors, recovery events, step boundaries, and run identity. It is observational evidence and must never control financial execution or substitute for benchmark expectations. Private reasoning and model-specific `<think>` content are not evaluation inputs.

The machine-readable report contains the suite and fixture-set versions, execution timestamp, execution mode, applicable model/provider configuration, case totals, component metrics, end-to-end case score, per-case results, classified failure reasons, and run or trajectory identity where available.

Generated reports and raw trajectories are local execution artifacts unless a separately reviewed sanitized result record is intentionally added. Secrets, API keys, raw operational logs, and raw trajectory logs must never be committed.

## 8. Evaluator self-test

The evaluator includes a regression test proving that an intentionally incorrect observed result is detected. The synthetic incorrect result is test input, not a normal benchmark case, and remains outside the benchmark denominator so a correctly detected failure does not make CI fail.

## 9. CLI and CI contract

The Step 2.5 public CLI is not implemented yet. Slice H added only an internal canonical deterministic catalog/request-builder entry point so Gate M can execute the complete suite. When the later reviewed CLI slice lands, the normal `uv run` workflow will support the full suite, one named case, deterministic/no-LLM mode, an explicit report location, and optional real-local-Ollama mode only if the empirical runner has separately been implemented. Required benchmark failures return a non-zero process status.

Deterministic/no-LLM execution is the headless CI boundary. Real-model and network-dependent evaluation is recorded separately and is not a mandatory CI dependency unless explicitly configured.

## 10. Maintenance rules

- Add or change a case only with a documented reason and independently verified expectations.
- Preserve stable case IDs once results have been recorded.
- Version material case-schema, fixture-set, evaluator, and report-contract changes deliberately.
- Do not silently refresh fixture evidence or replace historical values with current provider data.
- Do not remove a useful failing case merely to improve a reported score.
- Keep deterministic and empirical local-model results clearly separated.
- Run the complete repository quality gate before Step 2.5 completion review.
