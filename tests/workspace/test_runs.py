"""Focused tests for the run envelope and watchlist models."""

from datetime import UTC, datetime
from uuid import UUID

import pytest
from pydantic import ValidationError

from src.workspace.models import RunOutcome
from src.workspace.requests import GrahamGrowthSelection, GrahamNumberSelection
from src.workspace.runs import (
    AnalysisRun,
    AnalysisRunSummary,
    RunQuery,
    Watchlist,
    WatchlistSummary,
)

RUN_ID = UUID("11111111-1111-4111-8111-111111111111")
REFRESH_ID = UUID("22222222-2222-4222-8222-222222222222")
WATCHLIST_ID = UUID("33333333-3333-4333-8333-333333333333")
STARTED_AT = datetime(2026, 1, 5, 9, 0, tzinfo=UTC)
COMPLETED_AT = datetime(2026, 1, 5, 9, 0, 30, tzinfo=UTC)


def _base_run(**overrides: object) -> dict[str, object]:
    data: dict[str, object] = {
        "analysis_run_id": RUN_ID,
        "ticker": "  ko ",
        "analysis_id": "graham",
        "method_id": "graham_number",
        "config_schema_version": 1,
        "method_version": 1,
        "result_schema_version": 1,
        "evidence_codec_version": 1,
        "requested_config": GrahamNumberSelection(),
        "started_at": STARTED_AT,
        "completed_at": COMPLETED_AT,
        "status": RunOutcome.COMPLETED,
        "result_evidence": {"maximum_indicated_price": 33.8},
    }
    data.update(overrides)
    return data


def test_valid_completed_run_constructs_and_normalizes_ticker() -> None:
    run = AnalysisRun.model_validate(_base_run())
    assert run.ticker == "KO"
    assert run.status is RunOutcome.COMPLETED
    assert run.run_schema_version == 1
    assert run.projection_version == 1


@pytest.mark.parametrize("outcome", list(RunOutcome))
def test_one_valid_construction_per_outcome(outcome: RunOutcome) -> None:
    overrides = {"failure_reason_code": "data_unavailable"} if outcome is RunOutcome.FAILED else {}
    run = AnalysisRun.model_validate(_base_run(status=outcome, **overrides))
    assert run.status is outcome


def test_completed_requires_result_evidence() -> None:
    with pytest.raises(ValidationError, match="result_evidence"):
        AnalysisRun.model_validate(_base_run(result_evidence=None))


def test_failed_without_evidence_or_effective_config_constructs() -> None:
    data = _base_run(status=RunOutcome.FAILED, failure_reason_code="data_unavailable", result_evidence=None)
    run = AnalysisRun.model_validate(data)
    assert run.result_evidence is None
    assert run.effective_config is None


@pytest.mark.parametrize("reason", [None, ""])
def test_failed_requires_failure_reason_code(reason: str | None) -> None:
    with pytest.raises(ValidationError, match="failure_reason_code"):
        AnalysisRun.model_validate(_base_run(status=RunOutcome.FAILED, failure_reason_code=reason))


def test_completed_at_before_started_rejected() -> None:
    with pytest.raises(ValidationError, match="on or after started_at"):
        AnalysisRun.model_validate(_base_run(started_at=COMPLETED_AT, completed_at=STARTED_AT))


@pytest.mark.parametrize("status", ["running", "bogus"])
def test_invalid_status_rejected(status: str) -> None:
    with pytest.raises(ValidationError):
        AnalysisRun.model_validate(_base_run(status=status))


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("config_schema_version", 1.0),
        ("method_version", True),
        ("result_schema_version", "1"),
        ("evidence_codec_version", -3),
        ("method_version", 0),
    ],
)
def test_version_fields_reject_invalid_values(field: str, value: object) -> None:
    with pytest.raises(ValidationError):
        AnalysisRun.model_validate(_base_run(**{field: value}))


@pytest.mark.parametrize(
    "field",
    [
        pytest.param("method_version", id="method-version"),
        pytest.param("result_schema_version", id="result-schema-version"),
        pytest.param("evidence_codec_version", id="evidence-codec-version"),
    ],
)
def test_required_version_fields_reject_omission(field: str) -> None:
    run = _base_run()
    del run[field]
    with pytest.raises(ValidationError, match=field):
        AnalysisRun.model_validate(run)


@pytest.mark.parametrize("ticker", ["   ", ""])
def test_empty_ticker_rejected(ticker: str) -> None:
    with pytest.raises(ValidationError, match="ticker must not be empty"):
        AnalysisRun.model_validate(_base_run(ticker=ticker))


@pytest.mark.parametrize(
    ("field", "payload"),
    [
        ("result_evidence", {"series": [1.0, float("nan")]}),
        ("presentation_inputs", {"deep": {"value": float("inf")}}),
    ],
)
def test_non_finite_float_in_json_fields_rejected(field: str, payload: dict[str, object]) -> None:
    with pytest.raises(ValidationError, match="finite"):
        AnalysisRun.model_validate(_base_run(**{field: payload}))


@pytest.mark.parametrize("overrides", [{"refresh_id": REFRESH_ID}, {"batch_position": 2}])
def test_refresh_id_and_batch_position_must_pair(overrides: dict[str, object]) -> None:
    with pytest.raises(ValidationError, match="both be set or both null"):
        AnalysisRun.model_validate(_base_run(**overrides))


@pytest.mark.parametrize("overrides", [{"watchlist_id": WATCHLIST_ID}, {"watchlist_name": "My Watch"}])
def test_watchlist_id_and_name_must_pair(overrides: dict[str, object]) -> None:
    with pytest.raises(ValidationError, match="both be set or both null"):
        AnalysisRun.model_validate(_base_run(**overrides))


def test_identifiers_must_match_requested_config() -> None:
    with pytest.raises(ValidationError, match="match requested_config"):
        AnalysisRun.model_validate(_base_run(analysis_id="momentum"))


def test_identifiers_must_match_effective_config_when_present() -> None:
    growth = GrahamGrowthSelection(expected_growth=5.0, aaa_yield_override=4.0)
    with pytest.raises(ValidationError, match="match effective_config"):
        AnalysisRun.model_validate(_base_run(effective_config=growth))


def _base_watchlist(**overrides: object) -> dict[str, object]:
    data: dict[str, object] = {
        "watchlist_id": WATCHLIST_ID,
        "display_name": "My Watch",
        "normalized_name": "my watch",
        "created_at": STARTED_AT,
        "members": ("KO", "PFE"),
        "selections": [
            GrahamNumberSelection(),
            GrahamGrowthSelection(expected_growth=5.0, aaa_yield_override=4.0),
        ],
    }
    data.update(overrides)
    return data


def test_valid_watchlist_preserves_member_order() -> None:
    watchlist = Watchlist.model_validate(_base_watchlist())
    assert watchlist.members == ("KO", "PFE")
    assert [selection.method_id for selection in watchlist.selections] == ["graham_number", "graham_growth_value"]


def test_duplicate_method_id_across_selections_rejected() -> None:
    with pytest.raises(ValidationError, match="distinct method_id"):
        Watchlist.model_validate(_base_watchlist(selections=[GrahamNumberSelection(), GrahamNumberSelection()]))


def test_duplicate_member_ticker_rejected() -> None:
    with pytest.raises(ValidationError, match="members must be unique"):
        Watchlist.model_validate(_base_watchlist(members=("KO", "PFE", "KO")))


@pytest.mark.parametrize("normalized", ["MY WATCH", "mywatch", " my watch ", ""])
def test_normalized_name_must_match_display_name(normalized: str) -> None:
    with pytest.raises(ValidationError, match="casefold"):
        Watchlist.model_validate(_base_watchlist(normalized_name=normalized))


def test_blank_display_name_rejected() -> None:
    with pytest.raises(ValidationError, match="display_name must not be blank"):
        Watchlist.model_validate(_base_watchlist(display_name="   ", normalized_name=""))


def test_run_query_defaults_and_bounds() -> None:
    query = RunQuery()
    assert query.limit == 20
    assert query.offset == 0
    with pytest.raises(ValidationError):
        RunQuery(limit=0)
    with pytest.raises(ValidationError):
        RunQuery(limit=101)


def test_summaries_construct() -> None:
    summary = AnalysisRunSummary(
        analysis_run_id=RUN_ID,
        ticker="KO",
        method_id="graham_number",
        status=RunOutcome.COMPLETED,
        completed_at=COMPLETED_AT,
        refresh_id=REFRESH_ID,
    )
    assert summary.refresh_id == REFRESH_ID

    watchlist_summary = WatchlistSummary(
        watchlist_id=WATCHLIST_ID,
        display_name="My Watch",
        member_count=2,
        selection_count=2,
        created_at=STARTED_AT,
    )
    assert watchlist_summary.member_count == 2
