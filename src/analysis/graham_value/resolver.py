"""Deterministic single-fact and method-level input assembly for Graham analysis.

C2 (base): resolves one semantic field value through explicit override, cache
lookup, or provider fallback, producing an ``InputResolutionResult`` with full
provenance metadata and explicit status.

C2D: adds a thin method-level assembly layer on top of the existing
``InputResolver`` for the two Graham methods (Graham Number and Growth
Value).  The assembly layer does **not** perform either calculation — it only
selects, resolves, and packages the required and optional inputs using small
frozen, method-specific typed results.
"""

from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime

from src.analysis.graham_value.cache import ValuationCacheKey, ValuationCacheProtocol
from src.analysis.graham_value.facts import (
    ProviderFact,
    ValuationFactRequest,
    ValuationFactsProvider,
    ValuationField,
    ValuationProviderError,
    ValuationUnit,
)
from src.analysis.graham_value.models import CalculationStatus, GrahamMethod
from src.analysis.graham_value.provenance import (
    ComponentLineage,
    ResolvedInput,
    SourceKind,
    ValuationSubjectKind,
)

# ---------------------------------------------------------------------------
# InputResolutionResult
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class InputResolutionResult:
    """Outcome of a single-fact input resolution.

    Invariants:
        - ``OK`` requires ``resolved_input`` present and ``reason`` is ``None``.
        - ``INVALID_INPUT``, ``INPUT_UNAVAILABLE``, ``PROVIDER_ERROR`` require
          ``resolved_input`` is ``None`` and a non-empty ``reason``.
        - ``NOT_APPLICABLE`` is calculator-level semantics and is rejected here.

    Attributes:
        status: The resolution outcome.
        resolved_input: Present only when status is ``OK``.
        reason: Non-empty explanation when status is not ``OK``.
    """

    status: CalculationStatus
    resolved_input: ResolvedInput | None = None
    reason: str | None = None

    def __post_init__(self) -> None:
        """Enforce status/value invariants."""
        if self.status is CalculationStatus.NOT_APPLICABLE:
            msg = "InputResolutionResult does not permit CalculationStatus.NOT_APPLICABLE."
            raise ValueError(msg)
        if self.status is CalculationStatus.OK:
            if self.resolved_input is None:
                msg = "InputResolutionResult: status OK requires resolved_input to be present."
                raise ValueError(msg)
            if self.reason is not None:
                msg = "InputResolutionResult: status OK requires reason to be None."
                raise ValueError(msg)
        else:
            if self.resolved_input is not None:
                msg = f"InputResolutionResult: status {self.status} requires resolved_input to be None."
                raise ValueError(msg)
            if not self.reason:
                msg = f"InputResolutionResult: status {self.status} requires a non-empty reason."
                raise ValueError(msg)


# ---------------------------------------------------------------------------
# C2D method-level assembly results
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class GrahamNumberInputAssembly:
    """Assembled method inputs for the Graham Number calculation.

    The assembly layer does **not** perform the calculation.  It only
    resolves and packages the required and optional inputs with full
    provenance.

    Invariants:
        - ``OK``: ``eps``, ``bvps`` present; ``reason`` is ``None``.
        - Non-OK: ``reason`` non-empty; field slots that were not resolved
          are ``None``.
        - ``current_price`` is ``None`` when the quote was unavailable or
          the assembly failed before reaching quote resolution.
        - ``quote_status`` / ``quote_reason`` carry the diagnostic when the
          quote was attempted and degraded non-fatally.

    Attributes:
        status: Assembly outcome.
        eps: Resolved EPS input (present when OK).
        bvps: Resolved BVPS input (present when OK).
        current_price: Resolved current price (optional; ``None`` when
            absent or unavailable).
        quote_status: Status of the quote resolution attempt (set when a
            quote was requested and did not return OK).
        quote_reason: Human-readable reason for a non-OK quote.
        reason: Explanation when assembly ``status`` is not OK.
        method: Always ``GrahamMethod.NUMBER``.
    """

    status: CalculationStatus
    eps: ResolvedInput | None = None
    bvps: ResolvedInput | None = None
    current_price: ResolvedInput | None = None
    quote_status: CalculationStatus | None = None
    quote_reason: str | None = None
    reason: str | None = None
    method: GrahamMethod = field(init=False, default=GrahamMethod.NUMBER)


@dataclass(frozen=True)
class GrowthValueInputAssembly:
    """Assembled method inputs for the Graham Growth Value calculation.

    Invariants:
        - ``OK``: ``eps``, ``expected_growth``, ``current_aaa_yield``
          present; ``reason`` is ``None``.
        - Non-OK: ``reason`` non-empty.
        - ``current_price`` is ``None`` when the quote was unavailable or
          the assembly failed before reaching quote resolution.
        - ``quote_status`` / ``quote_reason`` carry the diagnostic when the
          quote was attempted and degraded non-fatally.

    Attributes:
        status: Assembly outcome.
        eps: Resolved EPS input with an explicit basis (present when OK).
        expected_growth: Resolved expected growth rate in percentage points
            (present when OK).
        current_aaa_yield: Resolved current AAA yield in percentage points
            (present when OK).
        current_price: Resolved current price (optional; ``None`` when
            absent or unavailable).
        quote_status: Status of the quote resolution attempt (set when a
            quote was requested and did not return OK).
        quote_reason: Human-readable reason for a non-OK quote.
        reason: Explanation when assembly ``status`` is not OK.
        method: Always ``GrahamMethod.GROWTH_VALUE``.
    """

    status: CalculationStatus
    eps: ResolvedInput | None = None
    expected_growth: ResolvedInput | None = None
    current_aaa_yield: ResolvedInput | None = None
    current_price: ResolvedInput | None = None
    quote_status: CalculationStatus | None = None
    quote_reason: str | None = None
    reason: str | None = None
    method: GrahamMethod = field(init=False, default=GrahamMethod.GROWTH_VALUE)


# ---------------------------------------------------------------------------
# InputResolver
# ---------------------------------------------------------------------------


class InputResolver:
    """Resolves a single valuation fact through override, cache, or provider.

    Precedence for one field:
        1. Explicit override (short-circuits cache and provider).
        2. Valid cache entry (relabelled as CACHE source).
        3. Configured provider (validated, then optionally cached).
        4. Explicit unavailable / provider-error outcome.

    Args:
        provider: The configured ``ValuationFactsProvider``.
        cache: Optional valuation cache implementation.
        clock: Zero-argument callable returning a timezone-aware datetime.
            Defaults to ``datetime.now(UTC)``.
        cache_schema_version: Positive integer schema version for cache keys.
    """

    _DEFAULT_CLOCK: Callable[[], datetime] = staticmethod(lambda: datetime.now(UTC))

    def __init__(
        self,
        provider: ValuationFactsProvider,
        cache: ValuationCacheProtocol | None = None,
        clock: Callable[[], datetime] | None = None,
        cache_schema_version: int = 1,
    ) -> None:
        """Create an ``InputResolver``.

        Args:
            provider: The configured ``ValuationFactsProvider``.
            cache: Optional valuation cache.
            clock: Clock callable returning a timezone-aware datetime.
            cache_schema_version: Positive integer schema version for cache keys.

        Raises:
            ValueError: If ``cache_schema_version`` is less than 1.
        """
        if cache_schema_version < 1:
            msg = f"cache_schema_version must be >= 1 (received {cache_schema_version})."
            raise ValueError(msg)
        self._provider = provider
        self._cache = cache
        self._clock: Callable[[], datetime] = clock if clock is not None else self._DEFAULT_CLOCK
        self._schema_version = cache_schema_version

    def resolve(
        self,
        request: ValuationFactRequest,
        *,
        override: float | None = None,
        use_cache: bool = True,
    ) -> InputResolutionResult:
        """Resolve a single valuation fact for *request*.

        Precedence: explicit override, then cache, then provider.

        Args:
            request: The valuation fact request (single observation).
            override: Caller-supplied numeric value; short-circuits cache and provider.
            use_cache: When False, skip both cache read and cache write.

        Returns:
            An ``InputResolutionResult`` describing the outcome.
        """
        # 0. Single-observation contract: this resolver handles exactly one
        #    observation.  A multi-observation request must be rejected before
        #    any override, cache, or provider work.
        if request.observation_count != 1:
            return InputResolutionResult(
                status=CalculationStatus.INVALID_INPUT,
                reason=(
                    f"This single-fact resolver requires observation_count=1 (received {request.observation_count})."
                ),
            )

        # 1. Explicit override — no cache, no provider.
        if override is not None:
            return self._resolve_override(request, override)

        # 2. Cache lookup.
        if use_cache and self._cache is not None:
            key = self._build_cache_key(request)
            entry = self._cache.get(key)
            if entry is not None:
                ri = self._try_cache_hit(request, entry.resolved_input, key)
                if ri is not None:
                    return InputResolutionResult(status=CalculationStatus.OK, resolved_input=ri)
                # Temporal rejection: fall through to provider.

        # 3. Provider fallback.
        return self._resolve_provider(request, use_cache)

    def resolve_three_year_average_eps(  # noqa: PLR0911, PLR0912, PLR0915
        self,
        request: ValuationFactRequest,
        *,
        use_cache: bool = True,
    ) -> InputResolutionResult:
        """Resolve the three-year average EPS.

        Validates the request, checks the derived cache, calls the provider once,
        selects the three most recent distinct eligible completed fiscal-year EPS
        observations, composes their arithmetic mean, and optionally caches the
        derived result.

        Args:
            request: The valuation fact request (EPS, observation_count=3,
                basis="fiscal_year").
            use_cache: When False, skip both cache read and cache write.

        Returns:
            An ``InputResolutionResult`` describing the outcome.
        """
        # --- 1. Request validation (before any cache/provider work) ---
        if request.field_name is not ValuationField.EPS:
            return InputResolutionResult(
                status=CalculationStatus.INVALID_INPUT,
                reason=f"resolve_three_year_average_eps requires field_name=EPS (received {request.field_name.name}).",
            )
        if request.observation_count != 3:
            return InputResolutionResult(
                status=CalculationStatus.INVALID_INPUT,
                reason=(
                    f"resolve_three_year_average_eps requires observation_count=3 "
                    f"(received {request.observation_count})."
                ),
            )
        if request.basis != "fiscal_year":
            return InputResolutionResult(
                status=CalculationStatus.INVALID_INPUT,
                reason=f'resolve_three_year_average_eps requires basis="fiscal_year" (received {request.basis!r}).',
            )

        # --- 2. Derived cache lookup ---
        if use_cache and self._cache is not None:
            key = self._build_derived_cache_key(request)
            entry = self._cache.get(key)
            if entry is not None:
                ri = self._try_derived_cache_hit(entry.resolved_input, key)
                if ri is not None:
                    return InputResolutionResult(status=CalculationStatus.OK, resolved_input=ri)

        # --- 3. Provider call (exactly once) ---
        try:
            facts = self._provider.fetch_facts(request)
        except ValuationProviderError as exc:
            return InputResolutionResult(
                status=CalculationStatus.PROVIDER_ERROR,
                reason=f"Provider error: {exc}",
            )

        # --- 4. Validate every candidate ---
        for fact in facts:
            err = self._validate_candidate(fact, request)
            if err is not None:
                return InputResolutionResult(status=CalculationStatus.PROVIDER_ERROR, reason=err)

        # --- 5. Temporal eligibility (capture one clock value) ---
        resolver_now = self._clock()
        eligible: list[ProviderFact] = []
        for fact in facts:
            if self._is_temporally_eligible(fact, request, resolver_now):
                eligible.append(fact)

        # --- 6. Selection ---
        # Group by observation_period_end
        by_period_end: dict[datetime, list[ProviderFact]] = {}
        for fact in eligible:
            assert fact.observation_period_end is not None
            by_period_end.setdefault(fact.observation_period_end, []).append(fact)

        # Sort distinct period ends newest to oldest
        sorted_ends = sorted(by_period_end.keys(), reverse=True)

        # Fewer than three distinct eligible periods
        if len(sorted_ends) < 3:
            return InputResolutionResult(
                status=CalculationStatus.INPUT_UNAVAILABLE,
                reason=(
                    f"Insufficient eligible fiscal-year EPS observations: "
                    f"found {len(sorted_ends)} distinct period(s), need 3."
                ),
            )

        # Select newest three
        selected_ends = sorted_ends[:3]

        # Duplicate/ambiguous in any selected period => PROVIDER_ERROR
        for end in selected_ends:
            if len(by_period_end[end]) > 1:
                return InputResolutionResult(
                    status=CalculationStatus.PROVIDER_ERROR,
                    reason=(
                        f"Ambiguous: {len(by_period_end[end])} candidates share "
                        f"observation_period_end={end.isoformat()} in a selected period."
                    ),
                )

        selected_facts = [by_period_end[end][0] for end in selected_ends]

        # --- 7. Selected-series compatibility ---
        common_provider_field = selected_facts[0].provider_field
        common_units = selected_facts[0].units
        common_currency = selected_facts[0].currency
        common_basis = selected_facts[0].basis
        for fact in selected_facts[1:]:
            if fact.provider_field != common_provider_field:
                return InputResolutionResult(
                    status=CalculationStatus.PROVIDER_ERROR,
                    reason=f"Incompatible provider_field: {fact.provider_field!r} != {common_provider_field!r}.",
                )
            if fact.units is not common_units:
                return InputResolutionResult(
                    status=CalculationStatus.PROVIDER_ERROR,
                    reason=f"Incompatible units: {fact.units.name} != {common_units.name}.",
                )
            if fact.currency != common_currency:
                return InputResolutionResult(
                    status=CalculationStatus.PROVIDER_ERROR,
                    reason=f"Incompatible currency: {fact.currency!r} != {common_currency!r}.",
                )
            if fact.basis != common_basis:
                return InputResolutionResult(
                    status=CalculationStatus.PROVIDER_ERROR,
                    reason=f"Incompatible basis: {fact.basis!r} != {common_basis!r}.",
                )

        # --- 8. Composition ---
        # Order oldest -> newest by observation_period_end
        def _end_key(f: ProviderFact) -> datetime:
            assert f.observation_period_end is not None  # guaranteed by prior validation
            return f.observation_period_end

        selected_facts_sorted = sorted(selected_facts, key=_end_key)

        resolved_at = resolver_now
        components: list[ResolvedInput] = []
        for fact in selected_facts_sorted:
            comp = ResolvedInput(
                field_name="eps",
                value=fact.value,
                source_kind=SourceKind.PROVIDER,
                resolved_at=resolved_at,
                basis=fact.basis,
                units=fact.units.value,
                currency=fact.currency,
                provider_id=fact.provider_id,
                provider_field=fact.provider_field,
                observation_period_start=fact.observation_period_start,
                observation_period_end=fact.observation_period_end,
                observed_at=fact.observed_at,
                available_at=fact.available_at,
                as_of=request.as_of,
                retrieved_at=fact.retrieved_at,
                notes=fact.notes,
            )
            components.append(comp)

        values = [f.value for f in selected_facts_sorted]
        mean_value = sum(values) / 3.0

        # Derive temporal metadata
        oldest = components[0]
        newest = components[-1]
        available_ats = [c.available_at for c in components if c.available_at is not None]
        derived_available_at = max(available_ats) if len(available_ats) == len(components) else None
        retrieved_ats = [c.retrieved_at for c in components if c.retrieved_at is not None]
        derived_retrieved_at = max(retrieved_ats) if retrieved_ats else resolver_now

        lineage = ComponentLineage(
            transformation="arithmetic_mean",
            components=tuple(components),
        )

        derived_ri = ResolvedInput(
            field_name="eps",
            value=mean_value,
            source_kind=SourceKind.DERIVED,
            resolved_at=resolved_at,
            basis="three_year_average",
            units=common_units.value,
            currency=common_currency,
            provider_id=request.provider_id,
            observation_period_start=oldest.observation_period_start,
            observation_period_end=newest.observation_period_end,
            observed_at=None,
            available_at=derived_available_at,
            as_of=request.as_of,
            retrieved_at=derived_retrieved_at,
            lineage=lineage,
        )

        # --- 9. Cache the DERIVED result ---
        if use_cache and self._cache is not None:
            key = self._build_derived_cache_key(request)
            self._cache.put(key, derived_ri)

        return InputResolutionResult(status=CalculationStatus.OK, resolved_input=derived_ri)

    # ------------------------------------------------------------------
    # C2D method-level assembly
    # ------------------------------------------------------------------

    def assemble_graham_number(  # noqa: PLR0913
        self,
        *,
        security_subject_id: str,
        security_provider_id: str,
        eps_basis: str = "three_year_average",
        eps_override: float | None = None,
        bvps_override: float | None = None,
        quote_override: float | None = None,
        quote_provider_id: str | None = None,
        as_of: datetime | None = None,
        use_cache: bool = True,
    ) -> GrahamNumberInputAssembly:
        """Assemble the inputs required by the Graham Number method.

        Resolves required EPS and BVPS, then optionally resolves the current
        price.  Does **not** perform the Graham Number calculation.

        Args:
            security_subject_id: Security symbol for EPS/BVPS/quote.
            security_provider_id: Provider identifier for security fields.
            eps_basis: ``"three_year_average"`` (default) or ``"ttm"``.
            eps_override: Explicit EPS value; bypasses cache/provider.
            bvps_override: Explicit BVPS value; bypasses cache/provider.
            quote_override: Explicit current price; bypasses cache/provider.
            quote_provider_id: Optional provider identifier for the quote.
                Defaults to ``security_provider_id`` for backward compatibility.
            as_of: Optional historical boundary (timezone-aware).
            use_cache: When False, skip cache read and write for all fields.

        Returns:
            A ``GrahamNumberInputAssembly`` with resolved inputs or a failure
            status with a field-specific reason.
        """
        # --- 1. Validate EPS basis ---
        if eps_basis not in ("three_year_average", "ttm"):
            return GrahamNumberInputAssembly(
                status=CalculationStatus.INVALID_INPUT,
                reason=f"eps_basis must be 'three_year_average' or 'ttm' (received {eps_basis!r}).",
            )

        # --- 2. Resolve EPS (required) ---
        eps_result = self._resolve_eps(
            security_subject_id=security_subject_id,
            security_provider_id=security_provider_id,
            eps_basis=eps_basis,
            eps_override=eps_override,
            as_of=as_of,
            use_cache=use_cache,
        )
        if eps_result.status is not CalculationStatus.OK:
            return GrahamNumberInputAssembly(
                status=eps_result.status,
                reason=f"eps: {eps_result.reason}",
            )
        eps_input = eps_result.resolved_input

        # --- 3. Resolve BVPS (required) ---
        bvps_request = ValuationFactRequest(
            subject_kind=ValuationSubjectKind.SECURITY,
            subject_id=security_subject_id,
            field_name=ValuationField.BVPS,
            provider_id=security_provider_id,
            as_of=as_of,
        )
        bvps_result = self.resolve(bvps_request, override=bvps_override, use_cache=use_cache)
        if bvps_result.status is not CalculationStatus.OK:
            return GrahamNumberInputAssembly(
                status=bvps_result.status,
                eps=eps_input,
                reason=f"bvps: {bvps_result.reason}",
            )
        bvps_input = bvps_result.resolved_input

        # --- 4. Resolve optional quote ---
        quote_result = self._resolve_optional_quote(
            security_subject_id=security_subject_id,
            security_provider_id=quote_provider_id or security_provider_id,
            quote_override=quote_override,
            as_of=as_of,
            use_cache=use_cache,
        )
        if quote_result.status is CalculationStatus.INVALID_INPUT:
            # Invalid explicit quote override: fail assembly.
            return GrahamNumberInputAssembly(
                status=CalculationStatus.INVALID_INPUT,
                eps=eps_input,
                bvps=bvps_input,
                reason=f"current_price: {quote_result.reason}",
            )
        if quote_result.status is not CalculationStatus.OK:
            # INPUT_UNAVAILABLE / PROVIDER_ERROR: non-fatal degradation.
            return GrahamNumberInputAssembly(
                status=CalculationStatus.OK,
                eps=eps_input,
                bvps=bvps_input,
                current_price=None,
                quote_status=quote_result.status,
                quote_reason=quote_result.reason,
            )
        # Quote resolved OK.
        return GrahamNumberInputAssembly(
            status=CalculationStatus.OK,
            eps=eps_input,
            bvps=bvps_input,
            current_price=quote_result.resolved_input,
        )

    def assemble_growth_value(  # noqa: PLR0911, PLR0913
        self,
        *,
        security_subject_id: str,
        security_provider_id: str,
        eps_basis: str,
        eps_override: float | None = None,
        expected_growth: float | None = None,
        aaa_subject_id: str,
        aaa_provider_id: str,
        aaa_yield_override: float | None = None,
        quote_override: float | None = None,
        quote_provider_id: str | None = None,
        as_of: datetime | None = None,
        use_cache: bool = True,
    ) -> GrowthValueInputAssembly:
        """Assemble the inputs required by the Graham Growth Value method.

        Resolves required EPS (explicit basis), expected growth rate
        (override only), current AAA yield, then optionally resolves the
        current price.  Does **not** perform the growth-value calculation.

        Args:
            security_subject_id: Security symbol for EPS/quote.
            security_provider_id: Provider identifier for security fields.
            eps_basis: Explicit EPS basis (e.g. ``"ttm"``,
                ``"three_year_average"``).  Required; no default.
            eps_override: Explicit EPS value; bypasses cache/provider.
            expected_growth: Expected growth rate in percentage points
                (required; override-only policy).
            aaa_subject_id: MACRO subject identifier for the AAA yield.
            aaa_provider_id: Provider identifier for the AAA yield.
            aaa_yield_override: Explicit AAA yield value in percentage points;
                bypasses cache/provider for that field.
            quote_override: Explicit current price; bypasses cache/provider.
            quote_provider_id: Optional provider identifier for the quote.
                Defaults to ``security_provider_id`` for backward compatibility.
            as_of: Optional historical boundary (timezone-aware).
            use_cache: When False, skip cache read and write for all fields.

        Returns:
            A ``GrowthValueInputAssembly`` with resolved inputs or a failure
            status with a field-specific reason.
        """
        # --- 1. Resolve EPS (required, explicit basis) ---
        if not eps_basis.strip():
            return GrowthValueInputAssembly(
                status=CalculationStatus.INVALID_INPUT,
                reason="eps_basis must be a non-empty string.",
            )

        eps_result = self._resolve_eps(
            security_subject_id=security_subject_id,
            security_provider_id=security_provider_id,
            eps_basis=eps_basis,
            eps_override=eps_override,
            as_of=as_of,
            use_cache=use_cache,
        )
        if eps_result.status is not CalculationStatus.OK:
            return GrowthValueInputAssembly(
                status=eps_result.status,
                reason=f"eps: {eps_result.reason}",
            )
        eps_input = eps_result.resolved_input

        # --- 2. Resolve expected growth (required, override-only) ---
        growth_result = self._resolve_expected_growth(expected_growth, as_of=as_of)
        if growth_result.status is not CalculationStatus.OK:
            return GrowthValueInputAssembly(
                status=growth_result.status,
                eps=eps_input,
                reason=f"expected_growth: {growth_result.reason}",
            )
        growth_input = growth_result.resolved_input

        # --- 3. Resolve current AAA yield (required) ---
        aaa_request = ValuationFactRequest(
            subject_kind=ValuationSubjectKind.MACRO,
            subject_id=aaa_subject_id,
            field_name=ValuationField.CURRENT_AAA_YIELD,
            provider_id=aaa_provider_id,
            as_of=as_of,
        )
        aaa_result = self.resolve(aaa_request, override=aaa_yield_override, use_cache=use_cache)
        if aaa_result.status is not CalculationStatus.OK:
            return GrowthValueInputAssembly(
                status=aaa_result.status,
                eps=eps_input,
                expected_growth=growth_input,
                reason=f"current_aaa_yield: {aaa_result.reason}",
            )
        aaa_input = aaa_result.resolved_input

        # --- 4. Resolve optional quote ---
        quote_result = self._resolve_optional_quote(
            security_subject_id=security_subject_id,
            security_provider_id=quote_provider_id or security_provider_id,
            quote_override=quote_override,
            as_of=as_of,
            use_cache=use_cache,
        )
        if quote_result.status is CalculationStatus.INVALID_INPUT:
            # Invalid explicit quote override: fail assembly.
            return GrowthValueInputAssembly(
                status=CalculationStatus.INVALID_INPUT,
                eps=eps_input,
                expected_growth=growth_input,
                current_aaa_yield=aaa_input,
                reason=f"current_price: {quote_result.reason}",
            )
        if quote_result.status is not CalculationStatus.OK:
            # INPUT_UNAVAILABLE / PROVIDER_ERROR: non-fatal degradation.
            return GrowthValueInputAssembly(
                status=CalculationStatus.OK,
                eps=eps_input,
                expected_growth=growth_input,
                current_aaa_yield=aaa_input,
                current_price=None,
                quote_status=quote_result.status,
                quote_reason=quote_result.reason,
            )
        # Quote resolved OK.
        return GrowthValueInputAssembly(
            status=CalculationStatus.OK,
            eps=eps_input,
            expected_growth=growth_input,
            current_aaa_yield=aaa_input,
            current_price=quote_result.resolved_input,
        )

    # ------------------------------------------------------------------
    # C2D private helpers
    # ------------------------------------------------------------------

    def _resolve_eps(  # noqa: PLR0913
        self,
        *,
        security_subject_id: str,
        security_provider_id: str,
        eps_basis: str,
        eps_override: float | None,
        as_of: datetime | None,
        use_cache: bool,
    ) -> InputResolutionResult:
        """Resolve EPS using the appropriate C2C entry point.

        Delegates to ``resolve_three_year_average_eps`` for the
        ``three_year_average`` basis, or the single-fact ``resolve`` for
        ``ttm`` and any other single-observation basis.  An explicit
        override always bypasses cache/provider.
        """
        if eps_override is not None:
            # Override bypasses cache/provider; retain the selected basis.
            request = ValuationFactRequest(
                subject_kind=ValuationSubjectKind.SECURITY,
                subject_id=security_subject_id,
                field_name=ValuationField.EPS,
                provider_id=security_provider_id,
                basis=eps_basis,
                as_of=as_of,
            )
            return self.resolve(request, override=eps_override, use_cache=use_cache)

        if eps_basis == "three_year_average":
            request = ValuationFactRequest(
                subject_kind=ValuationSubjectKind.SECURITY,
                subject_id=security_subject_id,
                field_name=ValuationField.EPS,
                provider_id=security_provider_id,
                basis="fiscal_year",
                as_of=as_of,
                observation_count=3,
            )
            return self.resolve_three_year_average_eps(request, use_cache=use_cache)

        # Single-observation basis (ttm, etc.)
        request = ValuationFactRequest(
            subject_kind=ValuationSubjectKind.SECURITY,
            subject_id=security_subject_id,
            field_name=ValuationField.EPS,
            provider_id=security_provider_id,
            basis=eps_basis,
            as_of=as_of,
        )
        return self.resolve(request, use_cache=use_cache)

    def _resolve_expected_growth(self, value: float | None, *, as_of: datetime | None = None) -> InputResolutionResult:
        """Validate and construct an OVERRIDE ResolvedInput for expected growth.

        Growth is override-only: there is no cache or provider path.
        ``None`` (missing) yields ``INPUT_UNAVAILABLE``; a non-finite value
        yields ``INVALID_INPUT``; a finite value becomes an OVERRIDE
        ``ResolvedInput`` with ``percentage_points`` units.

        Args:
            value: The expected growth rate in percentage points, or ``None``.
            as_of: Optional historical boundary preserved in provenance.
        """
        if value is None:
            return InputResolutionResult(
                status=CalculationStatus.INPUT_UNAVAILABLE,
                reason="expected_growth is required but was not provided.",
            )
        if not math.isfinite(value):
            return InputResolutionResult(
                status=CalculationStatus.INVALID_INPUT,
                reason=f"expected_growth must be finite (received {value!r}).",
            )
        ri = ResolvedInput(
            field_name="expected_growth",
            value=value,
            source_kind=SourceKind.OVERRIDE,
            resolved_at=self._clock(),
            units="percentage_points",
            as_of=as_of,
        )
        return InputResolutionResult(status=CalculationStatus.OK, resolved_input=ri)

    def _resolve_optional_quote(
        self,
        *,
        security_subject_id: str,
        security_provider_id: str,
        quote_override: float | None,
        as_of: datetime | None,
        use_cache: bool,
    ) -> InputResolutionResult:
        """Resolve the optional current price.

        This method is only called after all required inputs succeed.
        Returns an ``InputResolutionResult`` whose status determines the
        caller's behavior:
            - OK: include the resolved input.
            - INPUT_UNAVAILABLE / PROVIDER_ERROR: non-fatal degradation.
            - INVALID_INPUT: fatal — fail the assembly.

        Note: this method is only called after all required inputs succeed.
        """
        request = ValuationFactRequest(
            subject_kind=ValuationSubjectKind.SECURITY,
            subject_id=security_subject_id,
            field_name=ValuationField.CURRENT_PRICE,
            provider_id=security_provider_id,
            as_of=as_of,
        )
        return self.resolve(request, override=quote_override, use_cache=use_cache)

    def _build_derived_cache_key(self, request: ValuationFactRequest) -> ValuationCacheKey:
        """Build the cache key for a derived three-year-average EPS result."""
        return ValuationCacheKey(
            subject_kind=request.subject_kind,
            subject_id=request.subject_id,
            field_name="eps",
            basis="three_year_average",
            provider_id=request.provider_id,
            analysis_as_of=request.as_of,
            schema_version=self._schema_version,
        )

    def _try_derived_cache_hit(
        self,
        stored: ResolvedInput,
        key: ValuationCacheKey,
    ) -> ResolvedInput | None:
        """Relabel a cached DERIVED entry as a CACHE-sourced ResolvedInput.

        Returns None if the entry is not a valid DERIVED source or is temporally unusable.
        """
        if stored.source_kind is not SourceKind.DERIVED:
            return None
        if stored.available_at is not None and stored.available_at > self._clock():
            return None

        return ResolvedInput(
            field_name=stored.field_name,
            value=stored.value,
            source_kind=SourceKind.CACHE,
            resolved_at=self._clock(),
            origin_source_kind=SourceKind.DERIVED,
            basis=stored.basis,
            units=stored.units,
            currency=stored.currency,
            provider_id=stored.provider_id,
            provider_field=stored.provider_field,
            observation_period_start=stored.observation_period_start,
            observation_period_end=stored.observation_period_end,
            observed_at=stored.observed_at,
            available_at=stored.available_at,
            as_of=key.analysis_as_of,
            retrieved_at=stored.retrieved_at,
            cache_schema_version=key.schema_version,
            lineage=stored.lineage,
            notes=stored.notes,
        )

    @staticmethod
    def _validate_candidate(  # noqa: PLR0911
        fact: ProviderFact, request: ValuationFactRequest
    ) -> str | None:
        """Validate a single provider fact candidate. Returns error string or None."""
        if fact.subject_kind is not request.subject_kind:
            return f"Provider fact subject_kind ({fact.subject_kind}) does not match request ({request.subject_kind})."
        if fact.subject_id != request.subject_id:
            return f"Provider fact subject_id ({fact.subject_id!r}) does not match request ({request.subject_id!r})."
        if fact.field_name is not ValuationField.EPS:
            return f"Provider fact field_name ({fact.field_name.name}) is not EPS."
        if fact.provider_id != request.provider_id:
            return f"Provider fact provider_id ({fact.provider_id!r}) does not match request ({request.provider_id!r})."
        if fact.basis != "fiscal_year":
            return f"Provider fact basis ({fact.basis!r}) is not 'fiscal_year'."
        if fact.observation_period_start is None:
            return "Provider fact is missing observation_period_start."
        if fact.observation_period_end is None:
            return "Provider fact is missing observation_period_end."
        return None

    @staticmethod
    def _is_temporally_eligible(  # noqa: PLR0911
        fact: ProviderFact,
        request: ValuationFactRequest,
        resolver_now: datetime,
    ) -> bool:
        """Check temporal eligibility of a single candidate."""
        period_end = fact.observation_period_end
        assert period_end is not None  # guaranteed by prior validation

        if request.as_of is not None:
            # Historical: period_end <= as_of, available_at present and <= as_of
            if period_end > request.as_of:
                return False
            if fact.available_at is None:
                return False
            return not fact.available_at > request.as_of
        else:
            # Current: period_end <= resolver_now, available_at is None or <= resolver_now
            if period_end > resolver_now:
                return False
            return fact.available_at is None or fact.available_at <= resolver_now

    def _resolve_override(
        self,
        request: ValuationFactRequest,
        override: float,
    ) -> InputResolutionResult:
        """Validate and construct an OVERRIDE resolution."""
        if not math.isfinite(override):
            return InputResolutionResult(
                status=CalculationStatus.INVALID_INPUT,
                reason=f"Override value must be finite (received {override!r}).",
            )

        if request.field_name is ValuationField.CURRENT_PRICE and override <= 0:
            return InputResolutionResult(
                status=CalculationStatus.INVALID_INPUT,
                reason=f"current_price override must be strictly positive (received {override}).",
            )
        if request.field_name is ValuationField.CURRENT_AAA_YIELD and override <= 0:
            return InputResolutionResult(
                status=CalculationStatus.INVALID_INPUT,
                reason=f"current_aaa_yield override must be strictly positive (received {override}).",
            )

        resolved_at = self._clock()
        ri = ResolvedInput(
            field_name=request.field_name.value,
            value=override,
            source_kind=SourceKind.OVERRIDE,
            resolved_at=resolved_at,
            basis=request.basis,
            units=_field_unit(request.field_name).value,
            as_of=request.as_of,
        )
        return InputResolutionResult(status=CalculationStatus.OK, resolved_input=ri)

    def _build_cache_key(self, request: ValuationFactRequest) -> ValuationCacheKey:
        """Construct the cache key from the request and configured schema version."""
        return ValuationCacheKey(
            subject_kind=request.subject_kind,
            subject_id=request.subject_id,
            field_name=request.field_name.value,
            basis=request.basis,
            provider_id=request.provider_id,
            analysis_as_of=request.as_of,
            schema_version=self._schema_version,
        )

    def _try_cache_hit(
        self,
        request: ValuationFactRequest,
        stored: ResolvedInput,
        key: ValuationCacheKey,
    ) -> ResolvedInput | None:
        """Relabel a valid cached entry as a new CACHE-sourced ``ResolvedInput``.

        Returns ``None`` if the entry is temporally unusable for the request.
        """
        # Current-request temporal check: available_at must not be in the future.
        if request.as_of is None and stored.available_at is not None and stored.available_at > self._clock():
            return None

        return ResolvedInput(
            field_name=stored.field_name,
            value=stored.value,
            source_kind=SourceKind.CACHE,
            resolved_at=self._clock(),
            origin_source_kind=stored.source_kind,
            basis=stored.basis,
            units=stored.units,
            currency=stored.currency,
            provider_id=stored.provider_id,
            provider_field=stored.provider_field,
            observation_period_start=stored.observation_period_start,
            observation_period_end=stored.observation_period_end,
            observed_at=stored.observed_at,
            available_at=stored.available_at,
            as_of=request.as_of,
            retrieved_at=stored.retrieved_at,
            cache_schema_version=key.schema_version,
            lineage=stored.lineage,
            notes=stored.notes,
        )

    def _resolve_provider(
        self,
        request: ValuationFactRequest,
        use_cache: bool,
    ) -> InputResolutionResult:
        """Call the provider, validate the response, and optionally cache it."""
        try:
            facts = self._provider.fetch_facts(request)
        except ValuationProviderError as exc:
            return InputResolutionResult(
                status=CalculationStatus.PROVIDER_ERROR,
                reason=f"Provider error: {exc}",
            )

        if len(facts) == 0:
            return InputResolutionResult(
                status=CalculationStatus.INPUT_UNAVAILABLE,
                reason="Provider returned no data for the requested field.",
            )

        if len(facts) > 1:
            return InputResolutionResult(
                status=CalculationStatus.PROVIDER_ERROR,
                reason=(f"Provider returned {len(facts)} facts for a single-observation request; expected exactly 1."),
            )

        fact = facts[0]

        # Validate coherence and temporal eligibility before accepting or caching.
        validation = _validate_provider_response(request, fact, self._clock())
        if validation is not None:
            return InputResolutionResult(status=validation[0], reason=validation[1])

        # Convert to a PROVIDER-sourced ResolvedInput.
        ri = ResolvedInput(
            field_name=request.field_name.value,
            value=fact.value,
            source_kind=SourceKind.PROVIDER,
            resolved_at=self._clock(),
            basis=fact.basis,
            units=fact.units.value,
            currency=fact.currency,
            provider_id=fact.provider_id,
            provider_field=fact.provider_field,
            observation_period_start=fact.observation_period_start,
            observation_period_end=fact.observation_period_end,
            observed_at=fact.observed_at,
            available_at=fact.available_at,
            as_of=request.as_of,
            retrieved_at=fact.retrieved_at,
            notes=fact.notes,
        )

        # Cache after full validation passes.
        if use_cache and self._cache is not None:
            key = self._build_cache_key(request)
            self._cache.put(key, ri)

        return InputResolutionResult(status=CalculationStatus.OK, resolved_input=ri)


# ---------------------------------------------------------------------------
# Module-level helpers
# ---------------------------------------------------------------------------


def _field_unit(field_name: ValuationField) -> ValuationUnit:
    """Map a semantic field to its required unit."""
    if field_name is ValuationField.CURRENT_AAA_YIELD:
        return ValuationUnit.PERCENTAGE_POINTS
    return ValuationUnit.CURRENCY_PER_SHARE


def _validate_provider_response(
    request: ValuationFactRequest,
    fact: ProviderFact,
    now: datetime,
) -> tuple[CalculationStatus, str] | None:
    """Validate that the fact coherently answers the request and is temporally eligible.

    Returns a ``(status, reason)`` tuple when validation fails, or ``None`` on success.
    """
    # Coherence: the fact must answer the request.
    coherence_checks: tuple[tuple[bool, str], ...] = (
        (
            fact.subject_kind is request.subject_kind,
            f"Provider fact subject_kind ({fact.subject_kind}) does not match request ({request.subject_kind}).",
        ),
        (
            fact.subject_id == request.subject_id,
            f"Provider fact subject_id ({fact.subject_id!r}) does not match request ({request.subject_id!r}).",
        ),
        (
            fact.field_name is request.field_name,
            f"Provider fact field_name ({fact.field_name.name}) does not match request ({request.field_name.name}).",
        ),
        (
            fact.provider_id == request.provider_id,
            f"Provider fact provider_id ({fact.provider_id!r}) does not match request ({request.provider_id!r}).",
        ),
        (
            fact.basis == request.basis,
            f"Provider fact basis ({fact.basis!r}) does not match request ({request.basis!r}).",
        ),
    )
    for passed, message in coherence_checks:
        if not passed:
            return (CalculationStatus.PROVIDER_ERROR, message)

    # Temporal eligibility.
    if request.as_of is not None:
        # Historical: available_at is required and must be <= as_of.
        if fact.available_at is None:
            return (
                CalculationStatus.INPUT_UNAVAILABLE,
                "Historical request requires available_at; fact has no available_at.",
            )
        if fact.available_at > request.as_of:
            return (
                CalculationStatus.INPUT_UNAVAILABLE,
                f"Fact available_at ({fact.available_at.isoformat()}) is later than "
                f"request as_of ({request.as_of.isoformat()}).",
            )
    elif fact.available_at is not None and fact.available_at > now:
        return (
            CalculationStatus.INPUT_UNAVAILABLE,
            f"Fact available_at ({fact.available_at.isoformat()}) is later than current time ({now.isoformat()}).",
        )
    return None
