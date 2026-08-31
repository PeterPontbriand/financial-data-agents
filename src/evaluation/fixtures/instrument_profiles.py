"""Deterministic instrument-profile evidence for evaluation and tests."""

from __future__ import annotations

from datetime import UTC, datetime

from src.data.instrument_profile import InstrumentKind, InstrumentKindEvidence, InstrumentProfile
from src.data.security_identity import SecurityIdentity

FIXTURE_PROFILE_RESOLVED_AT = datetime(2026, 8, 30, 18, 0, tzinfo=UTC)


def fixture_instrument_profile(
    ticker: str,
    *,
    kind: InstrumentKind | None,
    provider_value: str,
    instrument_name: str | None = None,
    resolved_at: datetime = FIXTURE_PROFILE_RESOLVED_AT,
) -> InstrumentProfile:
    """Return independently sourced fixture identity and Yahoo kind evidence."""
    identity = SecurityIdentity(
        ticker=ticker,
        provider_id="fixture_identity",
        resolved_at=resolved_at,
        instrument_name=instrument_name,
    )
    evidence = InstrumentKindEvidence(
        ticker=ticker,
        kind=kind,
        provider_value=provider_value,
        provider_id="yfinance",
        resolved_at=resolved_at,
    )
    return InstrumentProfile(
        ticker=ticker,
        identity=identity,
        kind_evidence=evidence,
        diagnostics=(),
    )
