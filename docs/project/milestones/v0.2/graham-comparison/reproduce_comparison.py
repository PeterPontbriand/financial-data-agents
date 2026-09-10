"""Deterministically reproduce lost Graham comparisons through CLI composition.

Run explicitly with pytest; this is review evidence, not a permanent assertion
that unavailable comparisons are correct. Replace with success regressions in R2.
"""

import json
from unittest.mock import patch

import pytest
from typer.testing import CliRunner

from src.analysis.strategy.graham_growth.calculation import GrahamGrowthInputResolver
from src.analysis.strategy.graham_number.calculation import GrahamNumberInputResolver
from src.cli import app
from src.evaluation.fixtures.graham import NOW, PROVIDER_ID, SECURITY_ID, FixtureFinancialFactsProvider


@pytest.mark.parametrize("command", ["graham-number", "graham-growth"])
def test_current_composition_loses_comparison(command: str) -> None:
    """Show valid inputs but no comparison through real CLI/profile/services."""
    resolver_type = GrahamGrowthInputResolver if command == "graham-growth" else GrahamNumberInputResolver
    resolver = resolver_type(FixtureFinancialFactsProvider(), clock=lambda: NOW)
    arguments = [command, SECURITY_ID, "--data-provider", PROVIDER_ID, "--no-cache"]
    if command == "graham-growth":
        arguments.extend(["--expected-growth", "5", "--aaa-yield", "4.5"])
    with (
        patch("src.cli._build_graham_resolver", return_value=resolver),
        patch("src.cli.YFinanceClient.resolve_security_identity", return_value=None),
        patch("src.cli.YFinanceClient.resolve_instrument_kind", return_value=None),
        patch("socket.socket.connect", side_effect=AssertionError("Network forbidden")),
        patch("src.cli_support.SQLiteDatabase", side_effect=AssertionError("Operational database forbidden")),
    ):
        result = CliRunner().invoke(app, [*arguments, "--json"])
        details = CliRunner().invoke(app, [*arguments, "--details"])
    assert result.exit_code == 0, result.output
    assert details.exit_code == 0, details.output
    payload = json.loads(result.stdout)
    reference_key = "maximum_indicated_price" if command == "graham-number" else "growth_value"
    reference = payload["result"][reference_key]
    quote = payload["inputs"]["current_price"]
    assert payload["status"] == "ok"
    assert reference > 0
    assert quote["value"] > 0
    assert payload["inputs"]["eps"]["currency"] == quote["currency"] == "USD"
    expected = (reference - quote["value"]) / reference * 100
    assert isinstance(expected, float)
    assert payload["result"]["margin_of_safety_percent"] is None
    assert "Price comparison: unavailable\n" in details.stdout
    assert "Price relationship:" not in details.stdout
