"""Typed Graham analyzers borrowing caller-owned execution dependencies."""

from src.analysis.base_analyzer import BaseAnalyzer
from src.analysis.graham_value.analyzer_config import GrahamGrowthConfig, GrahamNumberConfig
from src.analysis.graham_value.input_resolver import GrahamInputResolver
from src.analysis.graham_value.service import (
    GrahamGrowthAnalysis,
    GrahamGrowthCalculationPolicy,
    GrahamNumberAnalysis,
    run_graham_growth_analysis,
    run_graham_number_analysis,
)
from src.data.instrument_profile import InstrumentProfile


def _resolve_ticker(ticker: str | None, default_ticker: str | None) -> str:
    selected = ticker if ticker is not None else default_ticker
    if selected is None or not selected.strip():
        raise ValueError("A nonblank ticker is required.")
    return selected.strip().upper()


class GrahamNumberAnalyzer(BaseAnalyzer[GrahamNumberConfig]):
    """Run the Number service with a borrowed resolver and optional fixed profile."""

    config_schema = GrahamNumberConfig

    def __init__(
        self,
        resolver: GrahamInputResolver,
        *,
        default_ticker: str | None = None,
        instrument_profile: InstrumentProfile | None = None,
    ) -> None:
        """Borrow dependencies; composition owns their construction and closure."""
        super().__init__(default_ticker)
        self._resolver = resolver
        self._instrument_profile = instrument_profile

    def run_analysis(self, config: GrahamNumberConfig, ticker: str | None = None) -> GrahamNumberAnalysis:
        """Return complete service evidence for the explicit or default ticker."""
        selected = _resolve_ticker(ticker, self.default_ticker)
        assert config.eps_basis is not None
        assert config.quote_provider_id is not None
        return run_graham_number_analysis(
            resolver=self._resolver,
            ticker=selected,
            security_provider_id=config.security_provider_id,
            quote_provider_id=config.quote_provider_id,
            eps_basis=config.eps_basis,
            eps_override=config.eps_override,
            bvps_override=config.bvps_override,
            quote_override=config.quote_override,
            as_of=config.as_of,
            use_cache=config.use_cache,
            instrument_profile=self._instrument_profile,
        )


class GrahamGrowthAnalyzer(BaseAnalyzer[GrahamGrowthConfig]):
    """Run the growth service with an explicitly injected calculation policy."""

    config_schema = GrahamGrowthConfig

    def __init__(
        self,
        resolver: GrahamInputResolver,
        *,
        policy: GrahamGrowthCalculationPolicy,
        default_ticker: str | None = None,
        instrument_profile: InstrumentProfile | None = None,
    ) -> None:
        """Borrow policy and execution dependencies without production setup."""
        super().__init__(default_ticker)
        self._resolver = resolver
        self._policy = policy
        self._instrument_profile = instrument_profile

    def run_analysis(self, config: GrahamGrowthConfig, ticker: str | None = None) -> GrahamGrowthAnalysis:
        """Return complete service evidence, retaining the supplied policy/profile."""
        selected = _resolve_ticker(ticker, self.default_ticker)
        assert config.eps_basis is not None
        assert config.quote_provider_id is not None
        return run_graham_growth_analysis(
            resolver=self._resolver,
            ticker=selected,
            security_provider_id=config.security_provider_id,
            quote_provider_id=config.quote_provider_id,
            eps_basis=config.eps_basis,
            eps_override=config.eps_override,
            expected_growth=config.expected_growth,
            aaa_yield_override=config.aaa_yield_override,
            quote_override=config.quote_override,
            as_of=config.as_of,
            use_cache=config.use_cache,
            policy=self._policy,
            instrument_profile=self._instrument_profile,
        )
