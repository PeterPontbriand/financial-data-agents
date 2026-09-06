# R1 Contract and Implementation Handoff

**Status:** Gate R1-A approved on 2026-09-06; R1-B authorized, implementation unstarted pending the requested documentation checkpoint commit.
**Authority:** [Implementation Plan, R1](../IMPLEMENTATION_PLAN.md).
**Approval effect:** Approval of this record and the amended implementation plan
closes Gate R1-A and authorizes R1-B immediately. It does not authorize R1-C or
any later work. Stop for review after R1-B's complete quality gate.

## 1. Scope and ordering

R1-B adds method-specific configuration/analyzer wrappers over existing Graham
execution services. R1-C replaces the combined command and extracts applicable
CLI support. Preserve legacy public analyzer/config interfaces, orchestration
handlers/tool identities, service functions, resolver rules, numerical behavior,
provenance, applicability, and result schemas. R1 precedes Step 3.4 by scheduling
choice, not a technical prerequisite. No other strategy must adopt BaseAnalyzer.

## 2. Configuration contract

Add `GrahamNumberConfig` and `GrahamGrowthConfig` in
`src/analysis/graham_value/analyzer_config.py`, both with `extra="forbid"` and
`frozen=True`. No discriminator or presentation-mode field is needed: the model
type identifies the method; rendering is a caller responsibility.

| Field | Type/default | Applicability |
| :--- | :--- | :--- |
| `security_provider_id` | `str`, default `sec_edgar` | Both; trim/lowercase, reject blank |
| `quote_provider_id` | `str \| None`, default None | Both; derive from effective security provider if omitted; normalize explicit nonblank value |
| `eps_basis` | `Literal["three_year_average", "ttm"] \| None`, default None | Both; normalize text and resolve using the matrix below |
| `eps_override` | `float \| None`, default None | Both |
| `quote_override` | `float \| None`, default None | Both |
| `as_of` | `datetime \| None`, default None | Both; require timezone awareness when present |
| `use_cache` | `bool`, default True | Both |
| `bvps_override` | `float \| None`, default None | Number only |
| `expected_growth` | required `float` | Growth only |
| `aaa_yield_override` | required `float` | Growth only |

Normalized configs contain a resolved EPS basis and quote provider. Derive quote
provider as `yfinance` for `sec_edgar`, `massive` for `massive`, and the supplied
security provider for another injected provider. Other nonblank provider IDs
remain usable with explicit injected resolvers; production CLI composition still
rejects unsupported providers before fetching, using its existing failure path.

| Method/provider | Omitted EPS basis | Accepted explicit basis | Additional condition |
| :--- | :--- | :--- | :--- |
| Number / SEC | three_year_average | three_year_average | None |
| Number / Massive | three_year_average, then reject | ttm | Explicit BVPS override required; do not silently change the old default |
| Number / injected other | three_year_average | either supported basis | None |
| Growth / SEC | three_year_average | three_year_average | Growth and AAA yield required |
| Growth / Massive | ttm | ttm | Growth and AAA yield required |
| Growth / injected other | ttm | either supported basis | Growth and AAA yield required |

Reject blank/unknown EPS bases and cross-method fields, even when an extra
field is supplied as None. Trim/lowercase supported basis strings. Keep numeric
financial-validity decisions at existing service/resolver/calculator boundaries:
wrong types or missing required fields are config errors; numeric values that
previously produced typed invalid/unavailable results must not become new CLI
usage errors. Explicitly regression-test zero, negative, and non-finite inputs
against current service behavior; no invalid value may become a successful result.

## 3. Analyzer and resource contracts

Add `GrahamNumberAnalyzer` and `GrahamGrowthAnalyzer` in
`src/analysis/graham_value/analyzers.py`; expose them and their configs through
the package's existing `__init__.py` without removing existing exports.

- Each subclasses `BaseAnalyzer` with its concrete config and sets
  `config_schema` to that config class.
- Number constructor: injected `GrahamInputResolver`, keyword-only
  `default_ticker: str | None = None`, `instrument_profile: InstrumentProfile | None = None`.
- Growth constructor: the same dependencies plus required keyword-only
  `policy: GrahamGrowthCalculationPolicy`.
- `run_analysis(config, ticker=None)` returns `GrahamNumberAnalysis` or
  `GrahamGrowthAnalysis`, respectively, by delegating to the matching service.
- Use the explicit ticker when it is not None, otherwise the constructor default;
  trim/uppercase and reject missing/blank input. Do not invent a fallback symbol.
- The supplied profile is execution context, not part of the config. Service
  validation enforces its ticker match. The CLI builds one analyzer for the
  selected ticker/profile per invocation. An analyzer with a fixed profile is
  not a reusable cross-ticker profile lookup service.
- Pass normalized config fields, profile, and injected policy directly to the
  existing services. Return complete evidence including assembly, result, margin,
  requested boundary, and retained profile without reconstruction or relabeling.
- Composition owns provider/cache construction, closure, profile resolution, and
  reading configured growth constants. Analyzers borrow these objects, perform
  no implicit production setup, and do not close resources or create clocks.
  Existing resolver clocks and service temporal checks remain authoritative.
- Preserve `GrahamValueAnalyzer`/`GrahamValueConfig` and all current callers.
  Orchestration continues using service functions directly; no tool migration.

## 4. CLI contract and migration

The replacement command names are `graham-number` and `graham-growth`.
Remove `graham` and `--method`/`-m`; no compatibility alias or subcommand group.
Keep positional ticker and `--ticker`/`-t` alias with existing conflict behavior.

Both commands retain `--as-of`, `--data-provider`, `--no-cache`, `--eps`/`-e`,
`--eps-basis`, `--current-price`/`-p`, and the mutually exclusive presentation
options `--details`, `--diagnostics`, `--json`. Map these to the corresponding
config fields; `--no-cache` maps to `use_cache=False`. Quote-provider selection
remains internal; do not add a new CLI flag for it.

Number alone exposes `--bvps`. Growth alone requires `--expected-growth` with
aliases `--expected-growth-rate`/`-g`, and `--aaa-yield` with aliases
`--current-aaa-yield`/`-y`. Preserve existing option explanations, replacing
references to the removed `--method` selector with the appropriate command.
Command summaries: "Execute the Graham Number earnings-and-book-value screen."
and "Execute Graham Growth Value with explicit growth and AAA-yield assumptions."

| Old invocation | Replacement |
| :--- | :--- |
| `financial-agents graham KO` | `financial-agents graham-number KO` |
| `financial-agents graham KO --method number --bvps 20` | `financial-agents graham-number KO --bvps 20` |
| `financial-agents graham KO --method growth --expected-growth 5 --aaa-yield 4.5` | `financial-agents graham-growth KO --expected-growth 5 --aaa-yield 4.5` |

Other supported flags carry over unchanged to their applicable command.
Publish this mapping in the active usage guide during R1-C, update current
examples/help together, and preserve historical milestone evidence. Removed
commands/options must fail as usage errors; do not silently route them elsewhere.

## 5. CLI support and error handling

Use `src/cli_support.py`, retaining `src/cli.py:app` and its current entry point.
Move ticker, presentation-mode, as-of, and provider-normalization helpers and
both production resource context managers. Support code must not import cli.py;
move required imports/constants with the helpers to avoid circular imports.
Make ticker-usage diagnostics accept the invoking command name rather than
hard-coding the removed command. CLI parsing performs string/date conversion;
config validators perform method/provider combination checks.

Use a shared context manager for equivalent execution-error mechanics with
explicit command-specific message callbacks. Keep usage validation outside it;
translate Pydantic validation failures into concise option-specific
`typer.BadParameter` errors (exit 2), without raw model dumps. Propagate intentional
`typer.Exit` and usage exceptions before broad exception handling. Preserve
execution-error exit 1, successful/not-applicable statuses, stdout/stderr,
optional-quote handling, and each presentation mode. Do not treat every typed
unavailable result as an exception. Preserve cache closure on all exit paths.
Only applicable commands use each helper; do not add options to other commands
or merge financial and historical cache policy.

## 6. Files and verification

R1-B write allowlist:
- `src/analysis/graham_value/analyzer_config.py` (new)
- `src/analysis/graham_value/analyzers.py` (new)
- `src/analysis/graham_value/__init__.py` (exports only)
- `tests/analysis/graham_value/test_analyzer_config.py` (new)
- `tests/analysis/graham_value/test_method_analyzers.py` (new)
- R1 planning records for evidence/status only.

R1-C write scope: `src/cli.py`, new `src/cli_support.py`, affected CLI/composition
and help/schema tests under `tests/`, active user/command documentation, and R1
planning evidence. Before editing, enumerate the exact affected tests/docs from
imports, patch targets, command invocations, and entry-point references; record
that list in this file. No production changes outside the two CLI modules are
authorized by R1-C; escalate a demonstrated contract conflict for review.

Before each implementation slice, establish the full managed baseline. Test the
complete config matrix, service-equivalent typed results, explicit/default
ticker behavior, profile mismatch, legacy interfaces, and injected cache/provider
ownership. CLI regressions cover both new commands, removed invocations, all
aliases/defaults, usage errors, presentation modes, provider errors, optional
quotes, financial-cache reuse/bypass, historical-cache reuse, and exception
cleanup. Update moved-helper patch targets without weakening assertions. Use
only deterministic fixtures/mocks; do not call live providers or LLM endpoints.

Run the managed full quality gate after each implementation slice (Ruff,
formatting, strict mypy, pytest/coverage). Review the actual diff and evidence at
Gate R1-B before authorizing R1-C, and at Gate R1-C before completing R1. No
subsequent work begins automatically. No dependency change or database migration
is included in this authorization.

## 7. Approval record

On 2026-09-06, the project owner approved this handoff and authorized R1-B.
The subsequent instruction requires a checkpoint commit of all pending planning
documentation changes before any R1-B implementation edits. Gate R1-C remains
unauthorized pending completion and stakeholder approval of Gate R1-B.

Pre-implementation checkpoint verification passed on 2026-09-06: Ruff,
formatting, strict mypy, and the full deterministic pytest/coverage suite.
Artifacts: .tmp/quality-runs/20260906133144108-40088-8eda8918aa094309954f6509d9b88164/.
No production or test files were changed before this checkpoint.
