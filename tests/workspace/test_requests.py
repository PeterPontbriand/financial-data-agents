"""Focused tests for typed, immutable workspace analysis selections."""

from collections.abc import Generator
from datetime import UTC, datetime
from typing import Any

import pytest
from pydantic import ValidationError

from src.analysis.strategy.graham_number.config import GrahamNumberConfig
from src.analysis.strategy.momentum.momentum_analyzer import MomentumConfig
from src.workspace.requests import GrahamNumberSelection, MomentumSelection


@pytest.fixture(autouse=True)
def mock_settings_config(monkeypatch: pytest.MonkeyPatch) -> Generator[None, None, None]:
    """Materialize deterministic configured-policy defaults for selection snapshots."""
    with monkeypatch.context() as ctx:
        ctx.setattr(
            "src.config.ProjectSettings.get_momentum_analysis",
            lambda self: {"window_sizes": {"short_window": 2, "long_window": 5}},  # noqa: ARG005
        )
        yield


def test_fixed_identifiers_and_schema_version() -> None:
    momentum = MomentumSelection.from_settings()
    assert momentum.analysis_id == "momentum"
    assert (momentum.method_id, momentum.config_schema_version) == ("sma_crossover", 1)

    graham = GrahamNumberSelection()
    assert graham.analysis_id == "graham"
    assert (graham.method_id, graham.config_schema_version) == ("graham_number", 1)


def test_momentum_defaults_materialized_from_configured_policy() -> None:
    selection = MomentumSelection.from_settings()
    assert (selection.short_window, selection.long_window, selection.rsi_period) == (2, 5, 14)

    config = selection.to_momentum_config()
    assert isinstance(config, MomentumConfig)
    assert (config.short_window, config.long_window, config.rsi_period) == (2, 5, 14)


def test_momentum_explicit_inputs_win_over_settings() -> None:
    selection = MomentumSelection.from_settings(short_window=3, rsi_period=9)
    assert (selection.short_window, selection.long_window, selection.rsi_period) == (3, 5, 9)


def test_momentum_snapshot_is_independent_of_caller_inputs() -> None:
    caller_values = {"short_window": 20, "long_window": 60}
    selection = MomentumSelection.model_validate(caller_values)
    caller_values.update(short_window=1, long_window=2)

    assert (selection.short_window, selection.long_window, selection.rsi_period) == (20, 60, 14)
    assert (selection.to_momentum_config().short_window, selection.to_momentum_config().long_window) == (20, 60)


def test_momentum_rejects_foreign_fields() -> None:
    with pytest.raises(ValidationError, match="extra_forbidden"):
        MomentumSelection.from_settings(as_of=None)
    with pytest.raises(ValidationError, match="extra_forbidden"):
        MomentumSelection(expected_growth=5.0)  # type: ignore[call-arg]


def test_momentum_rejects_invalid_windows() -> None:
    for value in (0, -1):
        with pytest.raises(ValidationError):
            MomentumSelection(short_window=value, long_window=5)
        with pytest.raises(ValidationError):
            MomentumSelection(short_window=2, long_window=5, rsi_period=value)

    with pytest.raises(ValidationError, match="smaller than long_window"):
        MomentumSelection(short_window=5, long_window=5)
    with pytest.raises(ValidationError, match="smaller than long_window"):
        MomentumSelection.from_settings(short_window=10, long_window=2)


@pytest.mark.parametrize("field", ["short_window", "long_window", "rsi_period"])
def test_momentum_selection_is_frozen(field: str) -> None:
    selection = MomentumSelection.from_settings()
    with pytest.raises(ValidationError):
        setattr(selection, field, 1)


@pytest.mark.parametrize("provider", ["sec_edgar", "massive"])
def test_graham_defaults_resolve_like_analyzer_config(provider: str) -> None:
    selection = GrahamNumberSelection(security_provider_id=provider, bvps_override=20.0)
    config = selection.to_graham_number_config()

    assert isinstance(config, GrahamNumberConfig)
    expected_basis = "three_year_average" if provider == "sec_edgar" else "ttm"
    expected_quote = "yfinance" if provider == "sec_edgar" else provider
    assert (selection.eps_basis, selection.quote_provider_id) == (expected_basis, expected_quote)
    assert config.use_cache is True


def test_graham_number_defaults() -> None:
    selection = GrahamNumberSelection()
    assert (selection.security_provider_id, selection.quote_provider_id, selection.eps_basis) == (
        "sec_edgar",
        "yfinance",
        "three_year_average",
    )
    assert selection.use_cache is True


def test_graham_normalization_and_explicit_values() -> None:
    as_of = datetime(2025, 1, 1, tzinfo=UTC)
    selection = GrahamNumberSelection.model_validate(
        {
            "security_provider_id": " MASSIVE ",
            "quote_provider_id": " YFINANCE ",
            "eps_basis": " TTM ",
            "eps_override": 4.5,
            "bvps_override": 20.0,
            "quote_override": 100.0,
            "as_of": as_of,
            "use_cache": False,
        }
    )
    assert (selection.security_provider_id, selection.quote_provider_id) == ("massive", "yfinance")
    config = selection.to_graham_number_config()
    assert (config.eps_override, config.bvps_override, config.quote_override) == (4.5, 20.0, 100.0)
    assert config.as_of == as_of
    assert config.use_cache is False


def test_graham_snapshot_is_independent_of_caller_inputs() -> None:
    caller_values = {"security_provider_id": "massive", "bvps_override": 25.0}
    selection = GrahamNumberSelection.model_validate(caller_values)
    caller_values.update(security_provider_id="sec_edgar")

    assert selection.security_provider_id == "massive"
    assert selection.to_graham_number_config().security_provider_id == "massive"


@pytest.mark.parametrize(
    ("values", "message"),
    [
        ({"security_provider_id": "sec_edgar", "eps_basis": "ttm"}, "three-year average"),
        ({"security_provider_id": "massive", "eps_basis": "three_year_average"}, "TTM"),
        ({"security_provider_id": "massive"}, "book value per share"),
        ({"eps_basis": "annual"}, "literal_error"),
    ],
)
def test_graham_rejects_incompatible_provider_combinations(values: dict[str, Any], message: str) -> None:
    with pytest.raises(ValidationError, match=message):
        GrahamNumberSelection(**values)


@pytest.mark.parametrize("field", ["expected_growth", "aaa_yield_override"])
def test_graham_rejects_foreign_fields(field: str) -> None:
    with pytest.raises(ValidationError, match="extra_forbidden"):
        GrahamNumberSelection(**{field: None})  # type: ignore[arg-type]


def test_graham_rejects_naive_as_of() -> None:
    with pytest.raises(ValidationError, match="timezone_aware"):
        GrahamNumberSelection(as_of=datetime(2025, 1, 1))


@pytest.mark.parametrize("value", [0.0, -1.0])
def test_graham_numeric_financial_validity_is_deferred(value: float) -> None:
    selection = GrahamNumberSelection(eps_override=value, bvps_override=value, quote_override=value)
    assert (selection.eps_override, selection.bvps_override, selection.quote_override) == (value, value, value)


def test_graham_selection_is_frozen() -> None:
    selection = GrahamNumberSelection()
    with pytest.raises(ValidationError):
        selection.use_cache = False


@pytest.mark.parametrize("model", [MomentumSelection, GrahamNumberSelection])
@pytest.mark.parametrize(
    ("field", "value"),
    [("analysis_id", "wrong"), ("method_id", "wrong"), ("config_schema_version", 2)],
)
def test_identity_overrides_rejected(
    model: type[MomentumSelection] | type[GrahamNumberSelection], field: str, value: object
) -> None:
    values: dict[str, object] = {"short_window": 2, "long_window": 5} if model is MomentumSelection else {}
    values[field] = value
    with pytest.raises(ValidationError) as error:
        model.model_validate(values)
    assert [item["loc"] for item in error.value.errors()] == [(field,)]


@pytest.mark.parametrize("field", ["eps_override", "bvps_override", "quote_override"])
@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf")])
def test_nonfinite_override_rejected(field: str, value: float) -> None:
    with pytest.raises(ValidationError, match="finite number"):
        GrahamNumberSelection.model_validate({field: value})


@pytest.mark.parametrize("field", ["security_provider_id", "quote_provider_id"])
@pytest.mark.parametrize("value", ["injected", "quotes", "", "   "])
def test_unsupported_providers_rejected(field: str, value: str) -> None:
    with pytest.raises(ValidationError) as error:
        GrahamNumberSelection.model_validate({field: value})
    assert [item["loc"] for item in error.value.errors()] == [(field,)]


@pytest.mark.parametrize("field", ["short_window", "long_window", "rsi_period"])
@pytest.mark.parametrize("value", [0, -1, True, 1.5])
def test_invalid_window_reports_target_field(field: str, value: object) -> None:
    values: dict[str, object] = {"short_window": 2, "long_window": 5, "rsi_period": 14}
    values[field] = value
    with pytest.raises(ValidationError) as error:
        MomentumSelection.model_validate(values)
    assert [item["loc"] for item in error.value.errors()] == [(field,)]


def test_rsi_period_one_preserves_existing_config_semantics() -> None:
    selection = MomentumSelection(short_window=2, long_window=5, rsi_period=1)
    assert selection.to_momentum_config().rsi_period == 1


def test_settings_mutation_and_converted_config_cannot_change_snapshot(monkeypatch: pytest.MonkeyPatch) -> None:
    selection = MomentumSelection.from_settings()
    monkeypatch.setattr(
        "src.config.ProjectSettings.get_momentum_analysis",
        lambda self: {"window_sizes": {"short_window": 10, "long_window": 30}},  # noqa: ARG005
    )
    assert MomentumSelection.from_settings().short_window == 10
    converted = selection.to_momentum_config()
    converted.short_window = 1
    assert selection.short_window == 2
    assert selection.to_momentum_config().short_window == 2


def test_round_trip_and_conversion_do_not_read_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    momentum = MomentumSelection.from_settings()
    graham = GrahamNumberSelection(as_of=datetime(2025, 1, 1, tzinfo=UTC))

    def forbidden_settings(_self: object) -> None:
        pytest.fail("Snapshot reconstruction must not read settings")

    monkeypatch.setattr("src.config.ProjectSettings.get_momentum_analysis", forbidden_settings)
    assert MomentumSelection.model_validate_json(momentum.model_dump_json()) == momentum
    assert GrahamNumberSelection.model_validate_json(graham.model_dump_json()) == graham
    assert momentum.to_momentum_config().short_window == 2
    assert graham.to_graham_number_config().as_of == graham.as_of
    assert MomentumSelection.from_settings(short_window=2, long_window=5) == momentum
