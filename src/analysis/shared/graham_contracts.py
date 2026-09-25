"""Shared Graham configuration and method contracts."""

from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, StrictFloat, field_validator

from src.data.financial.resolution_trace import ResolutionEvent, ResolutionOutcome, ResolutionStage, ResolutionTrace


class GrahamMethod(StrEnum):
    """Explicit method discriminator for Graham valuation calculations."""

    NUMBER = "graham_number"
    GROWTH_VALUE = "graham_growth_value"


# One canonical definition per method, per `docs/user/FINANCE_MATH.md` §"EPS basis": Graham
# Number's SEC EDGAR calculation never accepts a single-fiscal-year basis; Graham Growth's SEC
# EDGAR calculation explicitly supports an additional single completed fiscal-year basis "for
# reviewed workflows" alongside its three-year-average default. Both configs, and both
# orchestrator tool-argument models, import these — never a locally duplicated Literal — so the
# two surfaces cannot drift apart again.
GrahamNumberEPSBasis = Literal["three_year_average", "ttm"]
GrahamGrowthEPSBasis = Literal["three_year_average", "ttm", "fiscal_year"]

# Graham Growth alone widens SEC EDGAR's accepted bases beyond the shared three-year-average
# default (`fiscal_year`, for reviewed workflows). Defined once so the analyzer-facing Config and
# the workspace-facing Selection cannot each state a different extra-accepted set.
GRAHAM_GROWTH_EXTRA_SEC_EDGAR_BASES: frozenset[str] = frozenset({"fiscal_year"})


def resolve_graham_eps_basis(
    eps_basis: str | None,
    security_provider_id: str,
    quote_provider_id: str | None,
    default_basis: str,
    *,
    extra_allowed_sec_edgar_bases: frozenset[str] = frozenset(),
) -> tuple[str, str]:
    """Resolve one method's effective EPS basis and quote provider.

    Shared by ``_GrahamConfig`` (analyzer-facing) and ``_GrahamSelection`` (workspace-facing)
    so the accept/reject rule and its default are defined exactly once and cannot silently
    diverge between the two production entry points for the same method. ``default_basis`` and
    ``extra_allowed_sec_edgar_bases`` are each method's own choice, supplied by the caller — see
    `docs/user/FINANCE_MATH.md` §"EPS basis" and `docs/user/GRAHAM.md`'s per-method table. Values
    outside a method's own allowed set are rejected, never silently transformed into a different
    basis.
    """
    basis = eps_basis or default_basis
    sec_edgar_allowed = {"three_year_average", *extra_allowed_sec_edgar_bases}
    if security_provider_id == "sec_edgar" and basis not in sec_edgar_allowed:
        allowed = ", ".join(sorted(sec_edgar_allowed))
        raise ValueError(f"SEC EDGAR requires eps_basis to be one of ({allowed}) (received {basis!r}).")
    if security_provider_id == "massive" and basis != "ttm":
        raise ValueError(f"Massive requires eps_basis='ttm' (received {basis!r}).")
    resolved_quote = quote_provider_id
    if resolved_quote is None:
        resolved_quote = "yfinance" if security_provider_id == "sec_edgar" else security_provider_id
    return basis, resolved_quote


class _GrahamConfig(BaseModel):
    """Common request fields; financial validity remains with execution services."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    security_provider_id: str = "sec_edgar"
    quote_provider_id: str | None = None
    eps_basis: str | None = None
    eps_override: StrictFloat | None = None
    quote_override: StrictFloat | None = None

    @field_validator("security_provider_id", "quote_provider_id")
    @classmethod
    def normalize_provider(cls, value: str | None) -> str | None:
        """Normalize supplied provider identifiers without restricting injection."""
        if value is None:
            return None
        normalized = value.strip().lower()
        if not normalized:
            raise ValueError("Provider identifier must not be blank.")
        return normalized

    @field_validator("eps_basis", mode="before")
    @classmethod
    def normalize_basis(cls, value: object) -> object:
        """Normalize text before validating the supported EPS basis literals."""
        return value.strip().lower() if isinstance(value, str) else value

    def _resolve_defaults(
        self,
        default_basis: Literal["three_year_average", "ttm"],
        *,
        extra_allowed_sec_edgar_bases: frozenset[str] = frozenset(),
    ) -> None:
        """Resolve the effective EPS basis/quote provider for one method's own accepted bases.

        Delegates to :func:`resolve_graham_eps_basis`, the single definition shared with
        ``_GrahamSelection`` at the workspace boundary, so the two production entry points
        cannot silently diverge.
        """
        basis, quote_provider = resolve_graham_eps_basis(
            self.eps_basis,
            self.security_provider_id,
            self.quote_provider_id,
            default_basis,
            extra_allowed_sec_edgar_bases=extra_allowed_sec_edgar_bases,
        )
        object.__setattr__(self, "eps_basis", basis)
        object.__setattr__(self, "quote_provider_id", quote_provider)


def _require_ticker(ticker: str) -> str:
    """Normalize and require a nonblank ticker.

    Every production caller already normalizes its ticker before this point (the CLI's own
    ``_resolve_ticker``, the orchestrator's ``_AnalysisToolArguments.normalize_ticker``); this
    is the analyzer's own independent check, not delegation to an upstream one — the same
    trust-but-verify posture every analyzer in this project takes toward its own inputs.
    """
    normalized = ticker.strip().upper()
    if not normalized:
        raise ValueError("A nonblank ticker is required.")
    return normalized


def _event(
    field_name: str,
    stage: ResolutionStage,
    outcome: ResolutionOutcome,
    message: str,
) -> ResolutionEvent:
    """Construct an assembly trace event from caller-supplied text."""
    return ResolutionEvent(field_name=field_name, stage=stage, outcome=outcome, message=message)


def _trace_event(
    field_name: str,
    stage: ResolutionStage,
    outcome: ResolutionOutcome,
    message: str,
) -> ResolutionTrace:
    """Construct a one-event assembly trace from caller-supplied text."""
    return ResolutionTrace(events=(_event(field_name, stage, outcome, message),))
