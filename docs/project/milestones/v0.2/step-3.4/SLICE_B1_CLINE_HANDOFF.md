# Slice B1 — Typed Workspace Requests

## Authority and entry

Gate A was approved by the project owner on 2026-09-13 (America/Toronto).
The [contract](STEP_3_4_CONTRACT_AND_SLICE_PLAN.md) owns slice status and gates;
its §3 method/config matrix owns the request semantics. This handoff makes B1
concrete without extending its scope. B2 and later slices require further review.

Work on `feat/step-3.4-local-research-workspace`, after the documentation checkpoint
is committed by the project owner. Verify that HEAD contains readiness closeout
`60eb55501f3b19cbbd92444dceb8d97acc7b9bf3` and this approved contract. Record the
actual starting commit in the completion evidence; do not substitute the older
`ae62c98` test baseline for verification of the implementation.

## Allowed files and boundaries

- Add `src/workspace/__init__.py` and `src/workspace/requests.py`.
- Add `tests/workspace/test_requests.py` and a test-package initializer only if
  required by existing test conventions.
- Record B1 completion evidence in a companion document in this directory.

Do not edit existing analyzers, configs, calculators, presenters, CLI commands,
settings, dependencies, migrations or repositories. Do not create B2 models,
result codecs, run storage, execution adapters or refresh infrastructure.
The default builder returns typed selections, not a watchlist aggregate; it must
not depend on the future B2 watchlist model.

## Required interfaces

Use explicit typed variants in `requests.py`, with no generic registry:

1. Four selection variants, discriminated by canonical `method_id`, representing
   method configuration without a ticker. Define their union as `AnalysisSelection`.
   Each carries fixed `config_schema_version=1`; reject an unsupported version.
   Preserve the canonical analysis identifier from the contract matrix as a fixed
   value, not an independently editable field that can disagree with the method.
2. `AnalysisRequest` binds a normalized, nonempty ticker to a selection. Requested
   `as_of` and cache choices belong to the method configuration; do not duplicate
   mutable values at the request root. Momentum accepts no `as_of` option.
3. `parse_selection(alias: str, config_json: str) -> AnalysisSelection` accepts the
   four exact CLI aliases in the contract and the method-specific configuration
   object. It does not read a file; CLI file I/O belongs to F1. Reject unknown
   aliases, extra fields, malformed/non-object JSON, duplicate JSON keys and
   non-finite numeric values. Parse request configuration only, not result evidence.
4. `default_selections() -> tuple[AnalysisSelection, ...]` materializes Momentum,
   Graham Number and FCF Growth in that order, with the existing defaults. Never
   include Graham Growth automatically. Construct fresh independent values per
   call, and preserve earlier snapshots after settings or caller inputs change.

Model class names for the four variants are an implementation choice. Use
strict Pydantic models or equivalently validated typed structures consistent with
the contract. A frozen outer wrapper alone is insufficient if it retains a mutable
caller-owned `MomentumConfig`: copy and protect nested snapshot values. Typed
conversion back to existing analyzer configs must preserve their semantics.

The JSON bodies are `{"config": {...}}` for Momentum and both Graham methods;
FCF uses `{"policy": {...}, "currency": "USD", "provider_id": "sec_edgar",
"as_of": null, "use_cache": true}` with omitted fields taking the existing defaults.
An omitted `config`/`policy` object may use existing defaults for the three default
methods; Growth must still reject omitted required assumptions. Ticker, method,
analysis identifier and version cannot be overridden inside the config-file body.
Versions/discriminators belong to the typed selection, not the user body.

Apply the contract's field allowlists at the workspace boundary. In particular,
the current `MomentumConfig` does not itself forbid extra fields, and the FCF
policy is a dataclass; neither fact permits silently ignored workspace fields.
Validate nested values without changing those public types. Preserve existing
finite financial-value semantics: zero/negative values classified by execution
must not acquire new financial thresholds here. No calculator is invoked to
validate a request. Growth always requires explicit growth and AAA yield values.

Use native enum strings for FCF policy (`longest_available`, `3`, `4`, `5`;
`total_fcf`, `fcf_per_share`; `display_only`, `confirmation`, `hard_gate`). Preserve
Graham's provider-dependent EPS/quote defaults and Massive Number's required
`bvps_override`. Check supported provider choices against current CLI composition;
do not construct providers, fetch metadata or read credentials to validate them.
Effective Growth calculation-policy capture belongs to D3 execution evidence;
B1 does not read `_growth_assumptions()` or freeze a new user-editable policy.

## Verification and stop

Before editing, run the relevant existing config/model tests identified from
source inspection. After implementation, test:

- All four alias-to-canonical-identifier mappings and configuration version 1.
- Exact default selection order, absence of Growth, resolved defaults, and
  independence from later settings/caller mutation.
- Venue-suffixed ticker normalization and empty ticker rejection.
- Explicit Growth assumptions; Number/Growth foreign-field rejection; provider
  and EPS-basis compatibility; no invented forecast or new financial thresholds.
- FCF policy enum/default fidelity, currency normalization, aware optional time,
  and cache choice; Momentum rejects `as_of` and foreign fields.
- Malformed JSON, duplicate keys, unknown/nested extra fields, mismatched typed
  discriminators, unsupported versions and NaN/Inf rejection.
- Deterministic config JSON round trips without settings rereads, credentials,
  provider calls, storage or LLM activity. Result-evidence codecs remain deferred.

Run the complete managed quality wrapper specified in the contract. Report the
starting revision, files, API choices, focused tests, full gate and limitations.
Stop for B1 acceptance; do not start B2, commit, push or open a PR automatically.

## Cline prompt

> Implement Slice B1 only, following this handoff, AGENTS.md and the approved
> Step 3.4 contract. Verify the checkpoint and branch, establish the focused
> baseline, implement the typed requests/default selections with deterministic
> tests, and run the managed quality gate. Keep all edits inside the allowlist.
> Report evidence and stop for B1 review. Do not implement later slices or commit.
