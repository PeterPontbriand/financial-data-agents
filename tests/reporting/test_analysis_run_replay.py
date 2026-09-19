"""Deterministic replay tests for projection v1 (Momentum): no recalculation, no live calls."""

import json
from collections.abc import Iterator
from datetime import UTC, datetime
from unittest.mock import patch
from uuid import UUID

import pytest

from src.analysis.strategy.momentum.momentum_analyzer import MomentumAnalyzer, MomentumRun
from src.data.instrument_profile import InstrumentKind, InstrumentProfile
from src.evaluation.fixtures.instrument_profiles import fixture_instrument_profile
from src.evaluation.fixtures.market_data import FixtureDataClient
from src.reporting.analysis_runs import ReplayOptions, UnsupportedProjectionError, project_run
from src.reporting.presentation import PresentationMode
from src.workspace.codecs import decode_evidence
from src.workspace.execution import ExecutionCapture, execute
from src.workspace.models import RunOutcome
from src.workspace.momentum_execution import run_momentum
from src.workspace.requests import AnalysisRequest, MomentumSelection
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
    run = _build_run().model_copy(update={"analysis_id": "graham", "method_id": "graham_number"})
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
