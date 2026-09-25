"""Structural conformance tests for the shared analyzer invocation envelope.

Every strategy subclasses ``BaseAnalyzer[ConfigT, ResultT]`` and is invoked identically as
``run_analysis(ticker, config, context)`` (see ``AGENTS.md`` §9). These tests hold that shape
in place across all four analyzers, using only fixture-backed test doubles — no network access.
"""

from __future__ import annotations

import ast
import importlib
import inspect
from collections.abc import Callable, Iterator
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, get_args, get_origin
from unittest.mock import patch

import pytest

from src.analysis.base_analyzer import AnalysisContext, BaseAnalyzer
from src.analysis.strategy.fcf_earnings_growth.analyzer import FCFEarningsGrowthAnalyzer
from src.analysis.strategy.fcf_earnings_growth.input_resolver import ProductionAnnualGrowthSeriesResolver
from src.analysis.strategy.fcf_earnings_growth.models import FCFEarningsGrowthConfig, FCFEarningsGrowthPolicy
from src.analysis.strategy.graham_growth.analyzer import GrahamGrowthAnalyzer
from src.analysis.strategy.graham_growth.calculation import GrahamGrowthCalculationPolicy, GrahamGrowthInputResolver
from src.analysis.strategy.graham_growth.config import GrahamGrowthConfig
from src.analysis.strategy.graham_number.analyzer import GrahamNumberAnalyzer
from src.analysis.strategy.graham_number.calculation import GrahamNumberInputResolver
from src.analysis.strategy.graham_number.config import GrahamNumberConfig
from src.analysis.strategy.momentum.momentum_analyzer import MomentumAnalyzer, MomentumConfig
from src.data.financial.production import ProductionFinancialFactsProvider
from src.data.sec_edgar import SEC_PROVIDER_ID
from src.evaluation.fixtures.fcf_earnings_growth import FixtureAnnualFinancialFactsProvider, annual_series
from src.evaluation.fixtures.graham import NOW, PROVIDER_ID, SECURITY_ID, FixtureFinancialFactsProvider
from src.evaluation.fixtures.market_data import FixtureDataClient

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SRC_ROOT = _REPO_ROOT / "src"
_STRATEGY_PACKAGE = _SRC_ROOT / "analysis" / "strategy"

_GROWTH_POLICY = GrahamGrowthCalculationPolicy(base_pe=8.5, growth_multiplier=2.0, baseline_aaa_yield=4.4)
_MOMENTUM_SETTINGS = {"default": {"default_ticker": "AAPL", "data_start_date": "2026-01-01"}}


class _FixtureDataClientWithIdentity(FixtureDataClient):
    """``FixtureDataClient`` with a stable provider identity for the full resolver path."""

    @property
    def provider_id(self) -> str:
        return "fixture"


def _context() -> AnalysisContext:
    return AnalysisContext(as_of=NOW, executed_at=NOW, use_cache=True)


def _momentum_analyzer() -> MomentumAnalyzer:
    with patch("src.config.ProjectSettings.get_analysis_settings", return_value=_MOMENTUM_SETTINGS):
        return MomentumAnalyzer(default_ticker="AAPL", data_client=_FixtureDataClientWithIdentity())


def _momentum_config() -> MomentumConfig:
    return MomentumConfig(short_window=2, long_window=3, rsi_period=3)


def _graham_number_analyzer() -> GrahamNumberAnalyzer:
    resolver = GrahamNumberInputResolver(FixtureFinancialFactsProvider(), clock=lambda: NOW)
    return GrahamNumberAnalyzer(resolver)


def _graham_number_config() -> GrahamNumberConfig:
    return GrahamNumberConfig.model_validate({"security_provider_id": PROVIDER_ID})


def _graham_growth_analyzer() -> GrahamGrowthAnalyzer:
    resolver = GrahamGrowthInputResolver(FixtureFinancialFactsProvider(), clock=lambda: NOW)
    return GrahamGrowthAnalyzer(resolver, policy=_GROWTH_POLICY)


def _graham_growth_config() -> GrahamGrowthConfig:
    return GrahamGrowthConfig.model_validate(
        {"security_provider_id": PROVIDER_ID, "expected_growth": 5.0, "aaa_yield_override": 4.5}
    )


def _fcf_analyzer() -> FCFEarningsGrowthAnalyzer:
    facts = tuple(
        replace(
            fact,
            provider_id=SEC_PROVIDER_ID,
            provider_fact_id=f"fy-{fact.fiscal_year}:{fact.field_name.value}",
        )
        for fact in annual_series(range(2020, 2026))
    )
    provider = ProductionFinancialFactsProvider(sec_edgar=FixtureAnnualFinancialFactsProvider(facts))
    resolver = ProductionAnnualGrowthSeriesResolver(provider, clock=lambda: NOW)
    return FCFEarningsGrowthAnalyzer(resolver)


def _fcf_config() -> FCFEarningsGrowthConfig:
    return FCFEarningsGrowthConfig(policy=FCFEarningsGrowthPolicy(), currency="USD", provider_id=SEC_PROVIDER_ID)


@dataclass(frozen=True)
class _Case:
    """One strategy's analyzer class plus fixture-backed factories to exercise it live."""

    name: str
    analyzer_class: type[BaseAnalyzer[Any, Any]]
    build_analyzer: Callable[[], BaseAnalyzer[Any, Any]]
    build_config: Callable[[], object]
    ticker: str


_CASES: tuple[_Case, ...] = (
    _Case("momentum", MomentumAnalyzer, _momentum_analyzer, _momentum_config, "AAPL"),
    _Case("graham_number", GrahamNumberAnalyzer, _graham_number_analyzer, _graham_number_config, SECURITY_ID),
    _Case("graham_growth", GrahamGrowthAnalyzer, _graham_growth_analyzer, _graham_growth_config, SECURITY_ID),
    _Case("fcf_earnings_growth", FCFEarningsGrowthAnalyzer, _fcf_analyzer, _fcf_config, "ACME"),
)


def _generic_args(analyzer_class: type[BaseAnalyzer[Any, Any]]) -> tuple[type, type]:
    """Return ``(ConfigT, ResultT)`` as declared directly on ``BaseAnalyzer[ConfigT, ResultT]``."""
    for base in getattr(analyzer_class, "__orig_bases__", ()):
        if get_origin(base) is BaseAnalyzer:
            config_type, result_type = get_args(base)
            return config_type, result_type
    raise AssertionError(f"{analyzer_class!r} does not directly subclass BaseAnalyzer[ConfigT, ResultT].")


@pytest.mark.parametrize("case", _CASES, ids=lambda case: case.name)
def test_analyzer_subclasses_base_analyzer(case: _Case) -> None:
    """Item 1: every strategy's analyzer is a genuine ``BaseAnalyzer`` subclass."""
    assert issubclass(case.analyzer_class, BaseAnalyzer)


@pytest.mark.parametrize("case", _CASES, ids=lambda case: case.name)
def test_run_analysis_signature_matches_the_shared_envelope(case: _Case) -> None:
    """Item 2: every ``run_analysis`` matches ``(self, ticker, config, context) -> ResultT`` exactly."""
    config_type, result_type = _generic_args(case.analyzer_class)
    signature = inspect.signature(case.analyzer_class.run_analysis, eval_str=True)
    parameters = list(signature.parameters.values())

    assert [parameter.name for parameter in parameters] == ["self", "ticker", "config", "context"]
    assert all(parameter.kind is inspect.Parameter.POSITIONAL_OR_KEYWORD for parameter in parameters)

    annotations = {parameter.name: parameter.annotation for parameter in parameters}
    assert annotations["ticker"] is str
    assert annotations["config"] is config_type
    assert annotations["context"] is AnalysisContext
    assert signature.return_annotation is result_type


@pytest.mark.parametrize("case", _CASES, ids=lambda case: case.name)
def test_run_analysis_returns_its_declared_result_type(case: _Case) -> None:
    """Item 3: calling ``run_analysis`` with fakes returns an instance of the declared ``ResultT``."""
    _, result_type = _generic_args(case.analyzer_class)
    result = case.build_analyzer().run_analysis(case.ticker, case.build_config(), _context())
    assert isinstance(result, result_type)


def _python_files_outside_strategy_package() -> Iterator[Path]:
    for path in sorted(_SRC_ROOT.rglob("*.py")):
        try:
            path.relative_to(_STRATEGY_PACKAGE)
        except ValueError:
            yield path


def _strategy_boundary_function_imports() -> list[str]:
    """Return one ``module:qualified_name`` entry per plain-function import crossing the boundary."""
    violations: list[str] = []
    for path in _python_files_outside_strategy_package():
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.ImportFrom) or node.module is None:
                continue
            if node.module != "src.analysis.strategy" and not node.module.startswith("src.analysis.strategy."):
                continue
            module = importlib.import_module(node.module)
            for alias in node.names:
                imported = getattr(module, alias.name, None)
                if inspect.isfunction(imported):
                    relative_path = path.relative_to(_REPO_ROOT)
                    violations.append(f"{relative_path}: from {node.module} import {alias.name}")
    return violations


def test_no_plain_function_imports_cross_the_strategy_boundary() -> None:
    """Item 4: only classes may be imported from ``src.analysis.strategy.**`` outside that package."""
    violations = _strategy_boundary_function_imports()
    assert not violations, "Plain-function imports crossing the strategy boundary:\n" + "\n".join(violations)
