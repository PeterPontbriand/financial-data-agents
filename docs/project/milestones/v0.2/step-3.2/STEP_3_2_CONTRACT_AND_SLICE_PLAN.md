# Step 3.2 Contract and Slice Plan — DAO & Repository Layer

**Status:** Gate 3.2-A approved and Slice 3.2-B explicitly authorized on 2026-09-07. Production implementation remains unstarted pending the documents-only checkpoint.

**Authority:** [Implementation Plan, Step 3.2](../IMPLEMENTATION_PLAN.md#48-step-32--dao--repository-layer) owns scope, sequencing, and acceptance criteria. This companion supplies the concrete handoff. If they conflict, amend this handoff to match the Implementation Plan before execution.

**Predecessors:** Step 3.1, R1, and R2 are complete and approved. [PR #29](https://github.com/PeterPontbriand/financial-data-agents/pull/29) merged R1/R2 into `main` on 2026-09-07 at 17:55:41 UTC, merge commit `ca914b73281aaf5e618684098bb4f115c90972c5`. Its tree is identical to reviewed R2 tip `c4316425c52488c6574c93027235b9ac980e0803`.

**Authorization:** On 2026-09-07 the project owner confirmed that the documents were reviewed and approved and explicitly authorized Slice 3.2-B. This closes Gate 3.2-A and accepts the inventory, gap dispositions, implementation contract, file scope, and verification requirements below. Create the requested documents-only checkpoint before production edits. No additional planning approval is required for B within this contract; C and D retain their separate review and authorization gates.

## 1. Scope and preservation

Complete only demonstrated gaps in typed access for cache inspection, audit logging, and later analytics. The existing storage and public financial representations remain authoritative. Step 3.2 precedes Step 3.3, P2-Profiles, Step 3.4, and Step 3.5 in the selected sequence.

- Preserve dataclasses, Pydantic models, DataFrames, all cache identities, timestamps, provenance, temporal eligibility, TTL behavior, and existing public methods/imports.
- Keep application persistence SQL in `src/data/repositories/`; the existing telemetry adapter's SQL is a demonstrated gap to move behind that boundary. Migration DDL and test setup/assertion SQL retain their existing owners. No raw SQL belongs in orchestrators, tools, or CLI code.
- Reuse `SQLiteDatabase`, approved tables, and migration-owned encoding metadata. No schema, migration, dependency, connection-policy, or data-format change is proposed.
- Repository errors remain explicit. The telemetry recorder retains sanitization and fail-open behavior; the sink retains its lifecycle and ownership semantics. Storage does not become business control flow.
- No generic DAO base class, registry, ORM rewrite, duplicate cache protocol, provider/model calls, financial recalculation, or user-data migration.
- Step 3.3 owns new data-quality/refresh/invalidation policy. P2-Profiles owns durable instrument profiles. Step 3.4 owns watchlists, Analysis Runs, run browsing, and report projection. No new CLI commands, investor records, aggregate analytics, or telemetry retention/deletion policy are implied here.

## 2. Slice 3.2-A — Source reconciliation and contract review

The inventory below was prepared from current source and tests, not inferred solely from Step 3.1 completion. Paths are repository-relative. The [Step 3.1 contract](../step-3.1/STEP_3_1_SQLITE_SLICE_PLAN.md) and [approved persistence mapping](../step-3.1/STEP_3_1_D0_PERSISTENCE_MAPPING.md) remain the storage authority.

### Existing public surface

| Module | Existing typed boundary | Preservation / limitation |
| :--- | :--- | :--- |
| `src/data/repositories/sqlite.py` | `SQLiteDatabase.transaction()`, `read()`, `close()` | Borrowed scopes; commit/rollback; query-only snapshots; lazy construction; no implicit migration. |
| `src/data/repositories/market_data.py` | `MarketDataCacheKey`, `MarketDataCacheEntry`, `SQLiteMarketDataRepository.put()`, `get()` | Exact historical request snapshots with complete frame/context reconstruction; no enumeration API. |
| `src/data/repositories/resolved_input_cache.py` | `SQLiteResolvedInputCache.put()`, `get()`, `get_series()`, `ttl` | Complete scalar/series provenance; reads apply eligibility and configured TTL, so absent and ineligible entries both appear unavailable. |
| `src/data/financial/cache.py` | `ResolvedInputCacheProtocol`, `ResolvedInputSeriesCacheProtocol`, keys, entries, series query, in-memory implementation | Approved provider-resolution seams; do not expand these protocols for administrative SQLite inspection. |
| `src/core/telemetry/sinks/sqlite.py` | `SQLiteTrajectorySink.record()`, `flush()`, `close()`; `read_trajectory(database, run_id)` | Typed immutable event storage/readback exists, but SQL and row encoding reside outside the repository package. |
| `src/core/telemetry/sinks/__init__.py` | Re-exports `SQLiteTrajectorySink` and `read_trajectory` | Preserve public import paths and call signatures when delegating to a repository. |
| `src/data/repositories/schema.py`, `migrations.py`, `alembic/` | Core table metadata and migration lifecycle | Existing tables/encoding suffice; no replacement infrastructure. |
| `src/data/cached_client.py`, `src/cli_support.py` | Historical cache/provider composition and shared resource scopes | Fetch, fallback, TTL selection, and resource ownership stay with existing callers. |

### Requirement and gap matrix

| ID | Requirement | Finding and evidence | Smallest disposition |
| :--- | :--- | :--- | :--- |
| G1 | Fully typed access for core cached entities | **Satisfied.** Historical `put/get`, scalar `put/get`, and period `get_series` already exist. `tests/data/repositories/test_market_data.py`, `test_resolved_input_cache.py`, and `test_series_cache.py` cover identities, replacement, reopen, precision, lineage, ordering, eligibility, and corrupt storage. | Retain these interfaces and tests; no universal Pydantic conversion or additional cache abstraction. |
| G2 | Cache inspection | **Partially satisfied.** Exact historical lookup is available; financial `get/get_series` expose only eligible entries. Neither concrete repository enumerates stored keys. Storage can contain stale entries that cannot be distinguished from misses through the normal cache interface. | Add approved bounded key enumeration and explicit stored-entry inspection on the concrete SQLite classes, as specified in section 3. No freshness-policy change or CLI. |
| G3 | Audit logging and typed readback | **Satisfied behavior; partial architectural placement.** `SQLiteTrajectorySink` commits immutable events; `read_trajectory` reconstructs ordered typed events. `tests/core/telemetry/test_sqlite_sink.py` covers duplicates/conflicts, concurrency, sanitization, missing/corrupt data, encoding, ownership, and fail-open composition. | Extract existing SQL/serialization into a narrow trajectory repository; retain sink/readback entry points as delegates. No second audit log or new run model. |
| G4 | SQL confined to the repository layer | **Partially satisfied.** Market/fact SQL is in repositories. Telemetry sink/readback directly execute SQLAlchemy statements. | Move only that trajectory persistence responsibility under `src/data/repositories/`; keep schema management and test SQL in their established locations. |
| G5 | Consistent WAL / single-writer connection management | **Satisfied.** `SQLiteDatabase` verifies WAL, foreign keys, busy timeout, query-only reads, and scoped disposal; SQLite serializes competing writers. `tests/data/repositories/test_sqlite.py` exercises reader snapshots, writer timeout, rollback, close guards, and sequential memory scopes. | Reuse unchanged. Do not invent a writer queue or claim the Python lock globally serializes all file writes. Use file-backed tests for WAL/concurrency. |
| G6 | Round trips for core entities | **Satisfied baseline; extend with changes.** Above suites plus `test_persistence_smoke.py`, `test_schema.py`, and `test_migrations.py` verify the persisted lifecycle. | Add focused tests alongside implementation; retain the existing suite and full managed gate. |
| G7 | Support later analytics | **Satisfied foundation, later product work deferred.** Historical frames/context, financial facts/lineage, and ordered trajectory events are reconstructable through typed access. | No speculative analytics query language, joins, watchlists, or Analysis Run repository. Later requirements belong to their owning steps. |

Gate 3.2-A approval on 2026-09-07 accepts G2 as the bounded cache-inspection scope specified in section 3. G3/G4 describe one extraction, not two implementations. No completely missing storage subsystem was found.

### Fresh baseline evidence

On 2026-09-07 the managed wrapper passed Ruff, formatting (283 files), strict mypy (222 source files), and **1,811 tests in 26.87 seconds**. Coverage: **89% reported combined coverage**, 9,376 statements, 776 missing, 2,964 branches, 497 partial branches; statement coverage is approximately 91.7%.

Command: `& (Join-Path (git rev-parse --show-toplevel) 'scripts/run-quality-gates.ps1')`.

Artifacts: `.tmp/quality-runs/20260907143230324-6084-fb6f134eada84485bb6fbef5972eafe2/` (ignored; do not commit).

The run started on `c4316425c52488c6574c93027235b9ac980e0803` with documentation-only changes. The fetched PR merge has the identical tracked tree; the handoff now resides on `docs/step-3.2-repositories` based on that merge. No source or test edits were made. The initial sandboxed attempt could not query the existing Python interpreter; the approved retry used the same non-mutating wrapper and existing environment without dependency synchronization.

### Gate 3.2-A

Approved by the project owner on 2026-09-07 following document review. Approval covers the inventory, G2 inspection interpretation, G3/G4 extraction, section 3's interface/behavior contract, file scope, and recorded green baseline. Slice 3.2-B was explicitly authorized in the same instruction. The documents-only checkpoint is the remaining preparation before coding; no second planning-only slice is needed.

## 3. Slice 3.2-B — Demonstrated gaps with focused tests

**Status:** Explicitly authorized on 2026-09-07 following Gate 3.2-A approval; unstarted pending the documents-only checkpoint.

### Bounded implementation contract

1. Add `src/data/repositories/trajectory.py` with `SQLiteTrajectoryRepository(database)`, `record(event: TrajectoryEvent) -> None`, and `read_trajectory(run_id: UUID) -> list[TrajectoryEvent]`. It borrows an already-migrated database and neither closes nor migrates it. Move the existing row encoding, JSON/finite-value validation, insert/conflict comparison, and ordered readback without altering semantics. Preserve identical-event idempotency, event/run-sequence conflicts, atomic rollback, missing-run empty lists, sequence gaps, nullable fields, and explicit corrupt/unsupported-encoding errors. Preserve current encoding-check behavior rather than introducing new validation policy during extraction.
2. Keep the existing `SQLiteTrajectorySink(database, *, close_database=False)` and module/package `read_trajectory(database, run_id)` signatures. Delegate persistence to the repository; retain sink locking, flush/close behavior, and database ownership in the adapter. The recorder continues to sanitize and handle sink failures. Repository imports may use `TrajectoryEvent` from its model module, but must not import the sink or recorder and create a dependency cycle.
3. Add `list_keys(*, limit: int, offset: int = 0) -> tuple[MarketDataCacheKey, ...]` to `SQLiteMarketDataRepository`, and the equivalent returning `tuple[ResolvedInputCacheKey, ...]` to `SQLiteResolvedInputCache`. Require positive integer `limit` and nonnegative integer `offset`, rejecting booleans; no unbounded/default-limit path. Order by the existing canonical `entry_key` / `cache_key` text in ascending order. Each call is one read snapshot; pagination across concurrent writes is not a frozen database snapshot. Return an empty tuple for an empty page. Validate key representations and encoding versions; malformed selected keys raise explicitly. No dynamic SQL, arbitrary filters, or payload loading merely to enumerate keys.
4. Add `SQLiteResolvedInputCache.inspect(key: ResolvedInputCacheKey) -> ResolvedInputCacheEntry | None`: return the complete validated stored entry irrespective of TTL or analysis eligibility, or `None` only when the exact key is absent. Preserve stored provenance and timestamps; do not relabel it as a current cache hit. Invalid input/storage/version raises as in existing retrieval. The existing historical `get` already provides stored-entry inspection and needs no duplicate method. Share decoding where useful without changing `get/get_series` eligibility semantics. Inspection must never refresh, delete, call providers, or supply facts to normal resolver paths.
5. Keep `ResolvedInputCacheProtocol` and `ResolvedInputSeriesCacheProtocol` unchanged. These concrete administrative methods do not need in-memory-provider equivalents. Expose only the new trajectory repository through the repository package where appropriate; preserve every existing export.

**File scope:** `src/data/repositories/trajectory.py` (new), `__init__.py`, `market_data.py`, `resolved_input_cache.py`; `src/core/telemetry/sinks/sqlite.py`; focused tests under `tests/data/repositories/` and `tests/core/telemetry/test_sqlite_sink.py`; this planning record. Schema, migrations, dependencies, analyzers, provider clients, CLI behavior, and telemetry recorder policy are outside the implementation scope. A demonstrated need beyond this scope requires a contract amendment and review, not an opportunistic rewrite.

**Tests belong in this slice:** Establish/confirm the baseline before refactoring. Add focused failing tests for new inspection behavior and direct repository access, then implement. Cover stable key ordering/pagination, empty pages, invalid bounds, stale/historically ineligible entries visible only to inspection, unchanged normal reads, corruption, unsupported encoding, and no write/provider side effects. Preserve full trajectory equivalence, conflict/rollback, lock/ownership, and recorder fail-open coverage. Use migrated temporary-file databases for durability and concurrency; memory databases only for sequential cases.

**Gate 3.2-B:** Review the bounded diff, full typed API, focused regression evidence, preserved public behavior, and complete managed gate. No known failing or untested implementation is handed to 3.2-C. Record explicit authorization before C begins.

## 4. Slice 3.2-C — Integration and acceptance verification

**Status:** Unstarted; requires Gate 3.2-B approval and explicit authorization.

Verify the combined repository/sink/cache lifecycle against a fresh migrated temporary database and a reopened database. Extend integration tests only for demonstrated coverage gaps; do not duplicate B's tests. Demonstrate exact typed round trips, original provenance/timestamps, unchanged cache eligibility, and preserved telemetry failure handling. Audit production SQL placement, public imports, connection ownership, and the three Step 3.2 acceptance criteria. A defect receives a bounded fix and regression test within the approved contract; wider changes return to review.

Run the complete managed gate and record count/coverage changes relative to A/B, explaining any removed test or changed denominator. Deterministic tests must not call real providers or LLMs. Real user databases and live-model smoke tests are not required.

**Gate 3.2-C:** Review acceptance evidence and authorize D explicitly. Verification success does not mark Step 3.2 complete.

## 5. Slice 3.2-D — Documentation and closeout

**Status:** Unstarted; requires Gate 3.2-C approval and explicit authorization.

Synchronize this record, the Implementation Plan, Master Plan, and affected durable architecture guidance with actual implemented contracts. Reconcile Discovery Workbook references only where affected; preserve historical design and approval snapshots. Record the final full managed gate, whitespace/link checks, and documents/source scope review. Mark Step 3.2 complete only after explicit Gate 3.2-D approval. Step 3.3 and later work retain their own authorization and planning gates.

## 6. Checkpoint and decision record

| Item | Current state |
| :--- | :--- |
| R1/R2 approvals and merge | Complete; PR #29 merged on 2026-09-07. Historical pending entries in predecessor records are superseded by their final approvals and merge closeout. |
| 3.2-A inventory, gap matrix, approved contract, baseline | Reviewed and approved on 2026-09-07. |
| Gate 3.2-A / authorization for B | Explicitly approved / authorized by the project owner on 2026-09-07. |
| Documents-only checkpoint | Pending; no commit or push performed by this task. Include only the five changed planning documents, including this new file. |
| B / C / D | B authorized, awaiting documentation checkpoint; C and D unstarted and not yet authorized. |

Gate 3.2-A approval and B authorization are recorded. Once the documentation checkpoint is committed, begin B directly from this handoff. Preserve a clean source/test baseline, add focused tests with each implementation change, and stop at Gate 3.2-B.
