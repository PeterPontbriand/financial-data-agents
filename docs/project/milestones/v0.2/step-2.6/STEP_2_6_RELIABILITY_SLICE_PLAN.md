# Step 2.6 Reliability Limits Slice Plan

**Status:** approved on 2026-09-02; implementation not started; Slice A awaits the documentation-only checkpoint<br/>
**Milestone owner:** [v0.2 Implementation Plan](../IMPLEMENTATION_PLAN.md)<br/>
**Architecture:** [Financial Data Agents Architecture](../../../ARCHITECTURE.md#9-failure-and-reliability-boundary)<br/>
**Master Plan:** [Financial Data Agents Master Plan](../../../MASTER_PLAN.md#6-failure-taxonomy--handling-strategy)

## 1. Purpose and authority

This document turns Step 2.6 into bounded implementation handoffs. It is
subordinate to the milestone implementation plan and owns the detailed
reliability contract where that plan is intentionally brief. It does not
authorize Step 3 persistence work, change financial calculations, or make
telemetry a business-control dependency.

Step 2.6 prevents orchestration from consuming unbounded time, planning steps,
or retry attempts. A limit breach is an expected terminal runtime outcome: it
must be observable, diagnosable, and returned without an unhandled exception.

## 2. Current-state findings

- `OrchestratorConfig.max_steps` already defaults to 10, but exhaustion returns
  only a terminal text message.
- `SchemaConfig.max_validation_retries` already defaults to 3 and bounds schema
  repair within one planning step.
- `LLMClient.generate()` currently passes `timeout=None`.
- `AsyncToolDispatcher` has no timeout boundary, and synchronous handlers run on
  the event-loop thread.
- unexpected orchestration exceptions are recorded at lower boundaries where
  applicable but are re-raised from the run.
- `RECOVERY_ATTEMPTED` exists in the telemetry vocabulary but is not emitted by
  the schema-repair loop.
- `TrajectoryRecorder` writes events but does not expose a bounded recent-event
  view for terminal diagnostics.

These are starting conditions, not permission for unrelated refactoring.

## 3. Fixed reliability contract

### 3.1 Configuration and defaults

Introduce one immutable typed `ReliabilityLimits` model, owned by the
orchestrator reliability boundary and loaded through `ProjectSettings`. An
`OrchestratorConfig` may receive an explicit instance for deterministic tests or
per-run overrides; otherwise it uses the settings-derived value. There must be
one effective value for each limit in a run.

| Limit | Default | Meaning |
| :--- | ---: | :--- |
| Maximum planning steps | 10 | Existing inclusive loop bound |
| Maximum transient retries | 3 | Total corrective retries for one operation |
| Maximum consecutive schema violations | 4 | Initial invalid response plus three corrective retries |
| Overall run timeout | 300 s | Monotonic deadline from run start through terminal result |
| Planning-step timeout | 180 s | LLM/schema repair plus all tools in one step |
| LLM-call timeout | 120 s | One provider request, including response-body receipt |
| Tool-call timeout | 60 s | One registered tool invocation |
| Recent diagnostic events | 5 | Sanitized in-memory trajectory summaries included on breach |

All numeric limits are strictly positive except retry counts, which may be zero.
Environment overrides use the existing nested-settings convention under
`reliability_limits`, rather than ad hoc environment reads in runtime modules.

The existing `max_steps` and schema retry inputs must be migrated without
silently changing their defaults or breaking supported construction paths. The
implementation must not leave two independently authoritative values. Any
compatibility adapter is bounded to input normalization and must reject
conflicting explicit values.

### 3.2 Deadline semantics and precedence

- All elapsed-time decisions use `time.monotonic()` or the event loop's
  monotonic clock. Wall-clock timestamps remain telemetry only.
- The overall deadline starts immediately before `RUN_START` is recorded.
- A step deadline starts immediately before `STEP_START` is recorded.
- Each LLM or tool operation receives the earliest of its own deadline, its
  step deadline, and the overall run deadline.
- The terminal reason identifies the deadline that actually expired:
  `overall_timeout`, `step_timeout`, `llm_timeout`, or `tool_timeout`.
- A deadline is checked before each planning step and before and after each
  LLM/tool boundary. Starting new work after its effective deadline is
  forbidden.
- Timeout handling must use bounded async primitives and must preserve
  `finally` cleanup, span closure, `RUN_END`, telemetry flush, and client-owned
  cleanup responsibilities.

An asynchronous operation is cancelled on timeout. A synchronous tool handler
must be moved off the event-loop thread before a timeout can be enforced, but
Python cannot safely kill arbitrary running thread work. Therefore:

- the caller stops awaiting a timed-out synchronous handler and returns a
  terminal timeout outcome;
- the diagnostic states that cancellation was not confirmed;
- tool handlers remain responsible for their own lower-level I/O timeouts and
  idempotency; and
- Step 2.6 does not add processes, forceful thread termination, or speculative
  rollback machinery.

### 3.3 Retry and error-threshold semantics

A retry is a repeated attempt at the same logical operation. The original
attempt is not a retry. Every retry emits `RECOVERY_ATTEMPTED` before the
repeated call with the sanitized failure category, retry number, configured
maximum, step index, and causal span linkage.

For Step 2.6:

- schema validation failures retain their existing corrective-prompt flow;
- the fourth consecutive invalid response trips
  `schema_violation_limit` under the defaults above;
- a valid schema response resets the consecutive-schema counter;
- the counter does not reset merely because parsing fallback produced a tool
  request;
- timeout breaches are terminal and are never themselves retried by the
  orchestrator;
- LLM transport failures may be retried only when explicitly classified as
  transient (connection interruption, HTTP 429, or HTTP 5xx);
- malformed/provider-invalid requests, authentication/authorization failures,
  and other HTTP 4xx failures are non-recoverable;
- tool failures are not automatically retried in Step 2.6 because the current
  dispatcher has no reviewed retry-safety/idempotency contract; and
- telemetry failures remain fail-open and neither consume retry budget nor trip
  the circuit.

Transient retry numbering and schema-violation counting are separate evidence,
but no operation may exceed the configured transient-retry maximum. Backoff may
be added only as a bounded, deterministic configuration with injectable waiting
for tests; it is not required for the initial step.

### 3.4 Circuit state and trip reasons

Use a small request-scoped `CircuitBreaker` or equivalently named reliability
controller. It owns monotonic deadlines and counters only. It must not select
strategies, interpret financial results, query persistence, or depend on a
working telemetry sink.

The closed trip-reason vocabulary is:

- `max_steps_exceeded`;
- `overall_timeout`;
- `step_timeout`;
- `llm_timeout`;
- `tool_timeout`;
- `transient_retry_limit`;
- `schema_violation_limit`.

The controller is created once per orchestration run. A trip is idempotent: the
first reason is authoritative, no new work begins afterward, and cleanup may not
replace it with a secondary failure.

### 3.5 Structured terminal outcome

Extend the existing terminal step/run contract minimally rather than creating a
parallel orchestration result hierarchy. A reliability failure contains:

- stable trip reason;
- safe human-readable message;
- `run_id`;
- final step number, when one started;
- configured threshold and observed value or elapsed duration;
- up to the configured number of recent sanitized trajectory-event summaries;
- whether cancellation was confirmed, when relevant; and
- no raw prompts, tool arguments/results, secrets, tracebacks, or private model
  reasoning.

The CLI renders this failure and exits nonzero. Library consumers receive the
typed terminal result. A reliability trip is not raised as an unhandled
exception. External cancellation (`CancelledError`), interpreter shutdown, and
programmer defects remain distinct from a circuit trip and must not be falsely
reported as one.

The human diagnostic begins with the trip reason and `run_id`, then reports the
limit and recent sanitized events. If telemetry is disabled or unavailable, an
empty recent-event collection is valid and the reliability outcome still works.

### 3.6 Telemetry contract

- Emit `RECOVERY_ATTEMPTED` for every actual retry, including schema repair.
- Record a classified `ERROR` when a limit trips.
- End the active operation and step spans exactly once where they were started.
- Emit one `RUN_END` whose payload carries the same terminal reason as the typed
  result.
- Retain only a bounded in-memory deque of already-sanitized event summaries for
  diagnostics; persistent sink readback is not required.
- Sink failure must not affect deadlines, counters, terminal reason, or cleanup.

No new telemetry event type is required unless implementation proves that the
existing `ERROR` plus `RUN_END` representation cannot express a trip without
ambiguity. Such a vocabulary change requires review before adoption.

## 4. Scope boundaries

### In scope

- the main `AgentOrchestrator` execution path;
- LLM calls made by that path, including schema repair calls;
- tools dispatched by that path;
- the CLI boundary that consumes orchestration terminal results;
- deterministic reliability unit/integration tests; and
- directly affected configuration, architecture, user, and milestone docs.

### Out of scope

- financial formula, strategy, provider-mapping, or applicability changes;
- SQLite or other Step 3 persistence;
- automatic retries for tools without a retry-safety contract;
- token-budget enforcement when providers omit token counts;
- process isolation or forceful termination of synchronous work;
- unattended scheduling, monitoring, or notifications;
- real provider calls or real local-model calls in automated tests; and
- broad redesign of `LLMClient`, the dispatcher, telemetry, or CLI.

The empirical Golden runner may continue to pass `max_steps`, but Step 2.6 does
not expand into a second reliability implementation inside evaluation code. It
must use the shared orchestrator boundary where applicable. Any evaluator-only
batch timeout is a separate evaluation concern and requires explicit scope.

## 5. Slice sequence and review gates

### Slice A — contracts and configuration

**Objective:** establish the typed policy and failure vocabulary without
changing runtime behavior.

**Owned work**

1. Add `ReliabilityLimits`, trip-reason, circuit-state, and typed failure models
   at the narrow orchestrator boundary.
2. Integrate settings and explicit per-run overrides with conflict validation.
3. Add a clock/deadline seam suitable for deterministic tests.
4. Add focused model/configuration tests for defaults, validation,
   serialization, override precedence, and conflicting legacy inputs.

**Gate A:** focused Ruff, formatting, strict mypy, and tests. Stop for human
review of public contracts and defaults before enforcement work.

### Slice B — enforcement and telemetry

**Objective:** enforce the approved policy throughout one orchestration run.

**Owned work**

1. Consult the circuit before each step and around each LLM/tool operation.
2. Enforce effective overall, step, LLM, and tool deadlines with cleanup-safe
   cancellation.
3. Apply schema and transient-failure counters and emit
   `RECOVERY_ATTEMPTED` before every retry.
4. Provide bounded sanitized recent-event summaries independently of sink
   success.
5. Add deterministic tests using fake clients/tools and controlled clocks for
   normal completion, every trip reason, deadline precedence, counter reset,
   retry exhaustion, telemetry failure, and cancellation cleanup.

If Slice B proves too large for coherent review, split it without changing
contracts:

- **B1:** deadlines, timeout enforcement, and cancellation cleanup;
- **B2:** retries, schema threshold, recent-event diagnostics, and telemetry.

**Gate B:** focused gates plus the complete repository quality wrapper. Stop for
human review of enforcement and failure evidence before CLI closeout.

### Slice C — terminal presentation and closeout

**Objective:** expose reliability outcomes coherently and synchronize the
documentation.

**Owned work**

1. Return the typed reliability failure through the existing terminal result
   path and render its concise CLI diagnostic with nonzero exit status.
2. Add integration tests proving no reliability breach escapes as an unhandled
   exception and each diagnostic contains the correct `run_id` and reason.
3. Document supported settings/defaults and the synchronous-handler cancellation
   limitation.
4. Run the complete quality wrapper and reconcile every Step 2.6 acceptance
   criterion.

**Gate C:** stop for final human review. Do not mark Step 2.6 complete, commit,
push, open/merge a PR, or begin Step 3.1 without the corresponding explicit
human authorization.

## 6. Verification matrix

Automated verification is deterministic and uses no real network, provider, or
LLM endpoint.

| Scenario | Required evidence |
| :--- | :--- |
| Normal completion | No trip; existing result and ordered telemetry preserved |
| Maximum steps | Typed `max_steps_exceeded`; no step 11 under defaults |
| Overall timeout | Overall reason wins and no later work begins |
| Step timeout | Active step ends cleanly; run ends with matching reason |
| LLM timeout | Request cancellation attempted; typed diagnostic returned |
| Async tool timeout | Tool cancellation attempted; no subsequent tool starts |
| Sync tool timeout | Event loop remains responsive; cancellation-not-confirmed is explicit |
| Transient LLM recovery | At most three retries; one recovery event per retry |
| Non-recoverable LLM error | No retry; existing error boundary remains intact |
| Schema recovery | Valid response resets consecutive counter |
| Schema exhaustion | Fourth consecutive violation trips under defaults |
| Telemetry sink failure | Same result/reason as with a healthy sink |
| Cleanup | Spans, `RUN_END`, flush, and close each occur as specified |
| Configuration | Defaults and environment/per-run overrides need no code edits |

Tests should inject clocks/events rather than sleep against real time. Tiny
event-loop yields may coordinate cancellation tests, but pass/fail behavior must
not depend on machine speed.

## 7. Local-model decision

Real local-model execution is not required for Step 2.6 implementation or
acceptance. Reliability logic is better proven with deterministic delayed,
failing, malformed, and cancellation-aware fakes. Model speed varies with
hardware and load and cannot establish correct deadline or retry semantics.

An optional manual smoke run may be recorded after Slice C, but it cannot replace
the deterministic tests or block Step 2.6 closeout. Empirical native-schema
compatibility for the supported Light Mode model remains owned by the existing
Step 2.2 follow-up and Step 3.5 exit criterion.

## 8. Step acceptance criteria

- [ ] The fixed defaults are implemented and documented through one effective
  typed configuration path.
- [ ] Maximum steps, all four timeout scopes, transient retries, and consecutive
  schema violations are bounded as specified.
- [ ] Every breach returns a typed terminal failure with a clear `run_id`-linked
  diagnostic and never escapes as an unhandled reliability exception.
- [ ] Every actual retry emits sanitized `RECOVERY_ATTEMPTED` telemetry.
- [ ] Recent-event diagnostics remain bounded and telemetry failures remain
  fail-open.
- [ ] Deterministic tests cover the full verification matrix without live API or
  LLM calls.
- [ ] Focused checks and the complete repository quality gate pass.
- [ ] Architecture, milestone, configuration, and user-facing documentation are
  synchronized to implemented behavior.
- [ ] The final diff receives explicit human approval before Step 3.1 begins.

## 9. Immediate next action

The human approved this plan, including its timeout defaults, retry semantics,
slice boundaries, and synchronous-tool limitation, on 2026-09-02. Create and
push the documentation-only checkpoint, then establish the focused baseline and
begin Slice A only. This approval does not authorize Slice B, a completion
claim, or Step 3.1 work.
