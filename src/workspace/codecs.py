"""Explicit version dispatch and safe errors for stored workspace evidence."""

from src.analysis.strategy.momentum.momentum_analyzer import MomentumRun
from src.workspace.models import StrictJsonMapping
from src.workspace.momentum import decode_momentum, encode_momentum
from src.workspace.runs import AnalysisRun


class UnsupportedRunVersionError(ValueError):
    """The stored method or version has no supported evidence decoder."""

    reason_code = "unsupported_run_version"


class InvalidStoredRunError(ValueError):
    """Stored evidence violates its declared schema or envelope identity."""

    reason_code = "invalid_stored_run"


def encode_evidence(evidence: MomentumRun) -> StrictJsonMapping:
    """Encode the supported native evidence into an envelope-ready mapping."""
    try:
        return encode_momentum(evidence)
    except (ValueError, TypeError) as exc:
        raise InvalidStoredRunError("Invalid Momentum evidence.") from exc


def decode_evidence(run: AnalysisRun) -> MomentumRun | None:
    """Decode supported evidence using the envelope's explicit version tuple.

    Attempts that ended before resolution may have no result. Version checks
    still apply; unsupported records must never trigger recomputation.
    """
    if (
        run.analysis_id != "momentum"
        or run.method_id != "sma_crossover"
        or any(
            type(version) is not int or version != 1
            for version in (
                run.run_schema_version,
                run.config_schema_version,
                run.method_version,
                run.result_schema_version,
                run.evidence_codec_version,
                run.projection_version,
            )
        )
    ):
        raise UnsupportedRunVersionError("Unsupported Analysis Run method or version.")
    if run.result_evidence is None:
        return None
    try:
        evidence = decode_momentum(run.result_evidence)
        if evidence.metrics.ticker != run.ticker:
            raise ValueError("Ticker mismatch.")
        return evidence
    except (ValueError, TypeError) as exc:
        raise InvalidStoredRunError("Invalid stored Momentum evidence.") from exc
