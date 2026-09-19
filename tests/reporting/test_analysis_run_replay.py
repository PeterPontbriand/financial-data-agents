"""Deterministic replay tests for projection v1 (Momentum): no recalculation, no live calls."""

import json
from collections.abc import Iterator
from datetime import UTC, datetime
from unittest.mock import patch
from uuid import UUID

import pytest

from src.analysis.strategy.graham_number.calculation import GrahamNumberInputAssembly, GrahamNumberResult
from src.analysis.strategy.graham_number.service import GrahamNumberAnalysis
from src.analysis.strategy.momentum.momentum_analyzer import MomentumAnalyzer, MomentumRun
from src.core.analysis_status import CalculationStatus
from src.data.financial.provenance import ResolvedInput, SourceKind
from src.data.instrument_profile import InstrumentKind, InstrumentProfile
from src.evaluation.fixtures.instrument_profiles import fixture_instrument_profile, fixture_known_etf_profile
from src.evaluation.fixtures.market_data import FixtureDataClient
from src.reporting.analysis_runs import ReplayOptions, UnsupportedProjectionError, project_run
from src.reporting.presentation import PresentationMode
from src.workspace.codecs import decode_evidence, encode_evidence
from src.workspace.execution import ExecutionCapture, execute
from src.workspace.models import RunOutcome
from src.workspace.momentum_execution import run_momentum
from src.workspace.requests import AnalysisRequest, GrahamNumberSelection, MomentumSelection
from src.workspace.runs import AnalysisRun

NOW = datetime(2026, 9, 19, 12, 0, 0, tzinfo=UTC)
RUN_ID = UUID("22222222-2222-4222-8222-222222222222")


class _FixtureClient(FixtureDataClient):
    """FixtureDataClient with a stable provider identity for the full resolver path."""

    @property
    def provider_id(self) -> str:
        return "fixture"


@pytest.fixture(autouse=True)
def mock_momentum_settings() -> Iterator[None]:
    """Materialize deterministic Momentum defaults for the analyzer's fallback ticker."""
    mock_analysis = {"default": {"default_ticker": "BTC-USD", "data_start_date": "2026-01-01"}}
    with patch("src.config.ProjectSettings.get_analysis_settings", return_value=mock_analysis):
        yield


class _FakeSink:
    """Minimal AnalysisRunSink that just records; not exercised by replay tests directly."""

    def insert(self, run: AnalysisRun) -> None:
        del run


def _build_run(profile: InstrumentProfile | None = None) -> AnalysisRun:
    """A real, deterministic, persisted-shape Momentum run: the checked-in replay fixture.

    ``presentation_inputs`` is deliberately set to a value that does NOT match
    what the real fixture SMAs would produce if recomputed, so tests can prove
    replay consumes the stored value rather than recalculating it.
    """
    selection = MomentumSelection(short_window=2, long_window=3)
    request = AnalysisRequest(ticker="AAPL", selection=selection)

    def capture() -> ExecutionCapture:
        client = _FixtureClient()
        native = run_momentum(selection, "AAPL", client)
        return ExecutionCapture(
            native_evidence=native,
            profile=profile,
            outcome=RunOutcome.COMPLETED,
            presentation_inputs={"sma_spread": 999.0, "sma_spread_percent": 111.0},
        )

    return execute(request, capture=capture, repository=_FakeSink(), id_factory=lambda: RUN_ID, clock=lambda: NOW)


def _graham_analysis() -> GrahamNumberAnalysis:
    """A deterministic Graham Number analysis whose stored result cannot be recomputed from its inputs.

    The assembly inputs (EPS 4.0, BVPS 10.0) would recompute to a Graham Number of 30.0, but the
    stored ``result`` is 42.0 — so a passing render proves replay consumed the stored evidence
    rather than recalculating it. The native profile copy is deliberately absent.
    """
    eps = ResolvedInput("eps", 4.0, SourceKind.PROVIDER, NOW, provider_id="sec_edgar", as_of=NOW)
    bvps = ResolvedInput("book_value_per_share", 10.0, SourceKind.OVERRIDE, NOW, as_of=NOW)
    assembly = GrahamNumberInputAssembly(CalculationStatus.OK, eps, bvps, None)
    return GrahamNumberAnalysis(
        ticker="KO",
        as_of=NOW,
        assembly=assembly,
        result=GrahamNumberResult(status=CalculationStatus.OK, maximum_indicated_price=42.0),
        margin_of_safety_percent=None,
    )


def _graham_run(
    profile: InstrumentProfile | None = None,
    *,
    analysis: GrahamNumberAnalysis | None = None,
) -> AnalysisRun:
    """A persisted-shape Graham Number run built directly from stored evidence."""
    if analysis is None:
        analysis = _graham_analysis()
    return AnalysisRun(
        analysis_run_id=RUN_ID,
        ticker=analysis.ticker,
        analysis_id="graham",
        method_id="graham_number",
        config_schema_version=1,
        requested_config=GrahamNumberSelection(),
        started_at=NOW,
        completed_at=NOW,
        method_version=1,
        result_schema_version=1,
        evidence_codec_version=1,
        status=RunOutcome.COMPLETED,
        result_evidence=encode_evidence(analysis),
        instrument_profile=profile,
    )


def test_project_run_concise_uses_the_stored_spread_not_a_recomputed_one() -> None:
    """The strongest proof of 'no recalculation'.

    The fixture's real SMAs imply a different spread than the deliberately
    mismatched value stored in presentation_inputs. If replay recomputed
    instead of consuming the stored value, this assertion would fail.
    """
    run = _build_run()
    evidence = decode_evidence(run)
    assert isinstance(evidence, MomentumRun)
    assert evidence.metrics.short_sma_val is not None
    assert evidence.metrics.long_sma_val is not None
    real_spread = evidence.metrics.short_sma_val - evidence.metrics.long_sma_val
    assert real_spread != 999.0  # sanity: the stored/real mismatch is genuine, not coincidental

    rendered = project_run(run, ReplayOptions(mode=PresentationMode.CONCISE))
    assert "SMA spread: 999.00 (currency unspecified) (111.00%)" in rendered


def test_project_run_renders_the_captured_profile_not_the_native_evidence_copy() -> None:
    """Prove replay reads the envelope's own captured profile, not the native copy.

    Momentum's analyzer never sets MomentumRun.instrument_profile; the envelope's
    own top-level field is what replay must use, or a captured profile would
    always render as unavailable even though it was genuinely captured.
    """
    profile = fixture_instrument_profile("AAPL", kind=InstrumentKind.EQUITY, provider_value="EQUITY")
    run = _build_run(profile=profile)
    evidence = decode_evidence(run)
    assert isinstance(evidence, MomentumRun)
    assert evidence.instrument_profile is None  # confirms the native copy is genuinely absent
    assert run.instrument_profile == profile

    rendered = project_run(run, ReplayOptions(mode=PresentationMode.DETAILS))
    assert "Instrument kind: equity" in rendered
    assert "Instrument kind: unavailable" not in rendered


def test_project_run_all_modes_render_from_the_reopened_run() -> None:
    run = _build_run()
    for mode in PresentationMode:
        rendered = project_run(run, ReplayOptions(mode=mode))
        assert rendered
        assert "AAPL" in rendered


def test_project_run_json_matches_the_run_owns_captured_values() -> None:
    run = _build_run()
    payload = json.loads(project_run(run, ReplayOptions(mode=PresentationMode.JSON)))
    assert payload["result"]["sma_spread"] == 999.0
    assert payload["result"]["sma_spread_percent"] == 111.0
    assert payload["ticker"] == "AAPL"


def test_project_run_defaults_to_concise() -> None:
    run = _build_run()
    assert project_run(run) == project_run(run, ReplayOptions(mode=PresentationMode.CONCISE))


def test_project_run_rejects_an_unsupported_projection_version() -> None:
    run = _build_run().model_copy(update={"projection_version": 2})
    with pytest.raises(UnsupportedProjectionError, match="projection version"):
        project_run(run)


def test_project_run_rejects_an_unimplemented_method() -> None:
    run = _build_run().model_copy(update={"analysis_id": "graham", "method_id": "graham_growth_value"})
    with pytest.raises(UnsupportedProjectionError, match="No v1 replay"):
        project_run(run)


def test_project_run_rejects_a_malformed_stored_presentation_input() -> None:
    """presentation_inputs has no per-key schema; a reopened row is a real boundary."""
    run = _build_run().model_copy(update={"presentation_inputs": {"sma_spread": "not-a-number"}})
    with pytest.raises(UnsupportedProjectionError, match="sma_spread"):
        project_run(run)


def test_project_run_rejects_a_malformed_stored_spread_percent() -> None:
    run = _build_run().model_copy(
        update={"presentation_inputs": {"sma_spread": 1.0, "sma_spread_percent": "not-a-number"}}
    )
    with pytest.raises(UnsupportedProjectionError, match="sma_spread_percent"):
        project_run(run)


def test_project_run_never_calls_the_live_analyzer_or_settings() -> None:
    def forbidden(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("Replay must not call the live analyzer or read settings.")

    run = _build_run()
    with (
        patch.object(MomentumAnalyzer, "run_with_context", forbidden),
        patch.object(MomentumAnalyzer, "run_analysis", forbidden),
        patch("src.config.ProjectSettings.get_momentum_analysis", forbidden),
    ):
        assert project_run(run, ReplayOptions(mode=PresentationMode.DETAILS))


# --- Graham Number (graham / graham_number) v1 replay -----------------------


def test_graham_project_run_renders_the_stored_result_not_a_recomputed_one() -> None:
    """Replay must render the stored result; recomputing from inputs would give a different value."""
    run = _graham_run()
    evidence = decode_evidence(run)
    assert isinstance(evidence, GrahamNumberAnalysis)
    # The assembly inputs (EPS 4.0, BVPS 10.0) recompute to sqrt(22.5 * 4 * 10) == 30.0, not the stored 42.0.
    assert evidence.result.maximum_indicated_price == 42.0

    rendered = project_run(run, ReplayOptions(mode=PresentationMode.CONCISE))
    assert "KO" in rendered
    # The stored value renders; a recompute would render 30.00 instead.
    assert "42.00" in rendered
    assert "30.00" not in rendered


def test_graham_project_run_renders_the_captured_profile_not_the_native_evidence_copy() -> None:
    """Prove replay reads the envelope's own captured profile, not the native copy."""
    profile = fixture_instrument_profile("KO", kind=InstrumentKind.EQUITY, provider_value="EQUITY")
    run = _graham_run(profile=profile)
    evidence = decode_evidence(run)
    assert isinstance(evidence, GrahamNumberAnalysis)
    assert evidence.instrument_profile is None  # confirms the native copy is genuinely absent
    assert run.instrument_profile == profile

    rendered = project_run(run, ReplayOptions(mode=PresentationMode.DETAILS))
    assert "Instrument kind: equity" in rendered
    assert "Instrument kind: unavailable" not in rendered


def test_graham_project_run_all_modes_render_from_the_reopened_run() -> None:
    run = _graham_run()
    for mode in PresentationMode:
        rendered = project_run(run, ReplayOptions(mode=mode))
        assert rendered
        assert "KO" in rendered


def test_graham_project_run_json_matches_the_stored_result() -> None:
    run = _graham_run()
    payload = json.loads(project_run(run, ReplayOptions(mode=PresentationMode.JSON)))
    assert payload["result"]["maximum_indicated_price"] == 42.0
    assert payload["ticker"] == "KO"
    assert payload["analysis"] == "graham"
    assert payload["method"] == "graham_number"


def test_graham_project_run_defaults_to_concise() -> None:
    run = _graham_run()
    assert project_run(run) == project_run(run, ReplayOptions(mode=PresentationMode.CONCISE))


# --- Graham Number (graham / graham_number) v1 replay edge cases --------------


def _graham_invalid_input_analysis() -> GrahamNumberAnalysis:
    """A deterministic Graham Number run whose stored evidence is an invalid-input failure."""
    reason = "current_price: The configured quote provider could not complete the request."
    assembly = GrahamNumberInputAssembly(
        status=CalculationStatus.INVALID_INPUT,
        eps=ResolvedInput("eps", 4.0, SourceKind.PROVIDER, NOW, provider_id="sec_edgar", as_of=NOW),
        bvps=ResolvedInput("book_value_per_share", 10.0, SourceKind.OVERRIDE, NOW, as_of=NOW),
        reason=reason,
    )
    return GrahamNumberAnalysis(
        ticker="KO",
        as_of=NOW,
        assembly=assembly,
        result=GrahamNumberResult(status=CalculationStatus.INVALID_INPUT, reason=reason),
        margin_of_safety_percent=None,
    )


def test_graham_project_run_invalid_input_renders_stored_failure_without_recalculation() -> None:
    """Replay renders the stored invalid-input status and reason verbatim; it does not recompute a Graham Number."""
    run = _graham_run(analysis=_graham_invalid_input_analysis())
    evidence = decode_evidence(run)
    assert isinstance(evidence, GrahamNumberAnalysis)
    assert evidence.assembly.status is CalculationStatus.INVALID_INPUT
    assert evidence.result.status is CalculationStatus.INVALID_INPUT
    assert evidence.margin_of_safety_percent is None

    rendered = project_run(run, ReplayOptions(mode=PresentationMode.CONCISE))
    assert "KO" in rendered
    assert "Status: invalid input" in rendered
    # The stored reason renders verbatim; no Graham Number value is fabricated.
    assert "current_price: The configured quote provider could not complete the request." in rendered
    assert "Graham Number (maximum indicated price)" not in rendered


def _graham_quote_failure_analysis() -> GrahamNumberAnalysis:
    """A successful Number analysis whose optional quote lookup failed with a raw technical reason.

    ``quote_status`` is a genuine failure status and ``quote_reason`` is deliberately NOT
    investor-facing; replay must render the normalized public sentence, not this text.
    """
    eps = ResolvedInput("eps", 4.0, SourceKind.PROVIDER, NOW, provider_id="sec_edgar", as_of=NOW)
    bvps = ResolvedInput("book_value_per_share", 10.0, SourceKind.OVERRIDE, NOW, as_of=NOW)
    assembly = GrahamNumberInputAssembly(
        status=CalculationStatus.OK,
        eps=eps,
        bvps=bvps,
        current_price=None,
        quote_status=CalculationStatus.PROVIDER_ERROR,
        quote_reason="Provider error: connection reset",
    )
    return GrahamNumberAnalysis(
        ticker="KO",
        as_of=NOW,
        assembly=assembly,
        result=GrahamNumberResult(status=CalculationStatus.OK, maximum_indicated_price=42.0),
        margin_of_safety_percent=None,
    )


def test_graham_project_run_normalizes_raw_quote_reason_to_public_sentence() -> None:
    """Replay renders the investor-facing quote sentence and never leaks the raw technical reason."""
    run = _graham_run(analysis=_graham_quote_failure_analysis())
    evidence = decode_evidence(run)
    assert isinstance(evidence, GrahamNumberAnalysis)
    # The stored evidence carries a genuine quote failure with a deliberately raw/technical reason.
    assert evidence.assembly.quote_status is CalculationStatus.PROVIDER_ERROR
    assert evidence.assembly.quote_reason == "Provider error: connection reset"

    rendered = project_run(run, ReplayOptions(mode=PresentationMode.DIAGNOSTICS))
    # The stored technical reason must be replaced by the investor-facing sentence...
    assert "The configured quote provider could not complete the request." in rendered
    # ...and the raw technical string must never appear anywhere in the replay output.
    assert "Provider error: connection reset" not in rendered


def _graham_etf_not_applicable_analysis() -> GrahamNumberAnalysis:
    """A deterministic Graham Number run whose stored evidence is the ETF not-applicable failure."""
    reason = (
        "Graham Number is a company-level valuation method and does not apply directly to an ETF. "
        "No constituent-level or aggregate ETF valuation was performed."
    )
    assembly = GrahamNumberInputAssembly(status=CalculationStatus.NOT_APPLICABLE, reason=reason)
    return GrahamNumberAnalysis(
        ticker="FLSW",
        as_of=NOW,
        assembly=assembly,
        result=GrahamNumberResult(status=CalculationStatus.NOT_APPLICABLE, reason=reason),
        margin_of_safety_percent=None,
    )


def test_graham_project_run_etf_not_applicable_renders_stored_failure() -> None:
    """Replay renders the stored ETF not-applicable status and reason; it does not fabricate a Graham Number."""
    profile = fixture_known_etf_profile()
    run = _graham_run(profile=profile, analysis=_graham_etf_not_applicable_analysis())
    evidence = decode_evidence(run)
    assert isinstance(evidence, GrahamNumberAnalysis)
    assert evidence.assembly.status is CalculationStatus.NOT_APPLICABLE
    assert evidence.result.status is CalculationStatus.NOT_APPLICABLE
    assert evidence.margin_of_safety_percent is None

    rendered = project_run(run, ReplayOptions(mode=PresentationMode.CONCISE))
    assert "FLSW" in rendered
    assert "Status: not applicable" in rendered
    # The stored ETF reason renders verbatim; no Graham Number value is fabricated.
    assert "Graham Number is a company-level valuation method and does not apply directly to an ETF." in rendered
    assert "Graham Number (maximum indicated price)" not in rendered


def test_graham_project_run_comparison_unavailable_renders_stored_result_without_price() -> None:
    """Replay renders the stored Graham Number and marks the price comparison explicitly unavailable."""
    run = _graham_run()
    evidence = decode_evidence(run)
    assert isinstance(evidence, GrahamNumberAnalysis)
    assert evidence.result.status is CalculationStatus.OK
    assert evidence.assembly.current_price is None
    assert evidence.margin_of_safety_percent is None

    rendered = project_run(run, ReplayOptions(mode=PresentationMode.CONCISE))
    # The stored Graham Number renders...
    assert "42.00" in rendered
    # ...but the price comparison is explicitly unavailable (no quote was fabricated).
    assert "Current price: unavailable" in rendered
    assert "Price comparison: unavailable (no current quote)" in rendered


def test_graham_project_run_failure_fixtures_render_in_all_modes() -> None:
    """The invalid-input and ETF not-applicable runs render in every mode without fabricating a Graham Number."""
    failure_runs = (
        _graham_run(analysis=_graham_invalid_input_analysis()),
        _graham_run(profile=fixture_known_etf_profile(), analysis=_graham_etf_not_applicable_analysis()),
    )
    for run in failure_runs:
        for mode in PresentationMode:
            rendered = project_run(run, ReplayOptions(mode=mode))
            assert rendered
            assert "Graham Number (maximum indicated price)" not in rendered
