"""Typed, immutable per-method analysis selections for the local research workspace.

Selection variants freeze one method's effective configuration at creation time:
defaults are materialized from the current configured policy or explicit caller
inputs, unknown fields are rejected, non-finite financial values are rejected, and
later changes to settings or caller-owned containers cannot alter an existing
snapshot. Conversions return the existing analyzer config types with their original
semantics; they never construct data providers, fetch metadata, or perform analysis
work.

Provider choices are restricted at this boundary to those supported by the current
CLI composition (see ``src/cli.py`` provider resolution): the security-fact provider
must be SEC EDGAR (``sec_edgar``) or Massive (``massive``), even though the base
analyzer configs permit arbitrary identifiers for dependency injection. The quote
provider resolves from the security provider using the existing Graham semantics.

The canonical analysis/method identifiers and ``config_schema_version`` are fixed to
the contract matrix values and cannot be overridden or made to disagree with one
another; an unsupported version is rejected at validation time.
"""

import math
from typing import Annotated, Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, StrictFloat, field_validator, model_validator

from src.analysis.strategy.fcf_earnings_growth.models import (
    FCFClassificationBasis,
    FCFEarningsGrowthPolicy,
    ForwardPolicy,
    HistoricalHorizon,
)
from src.analysis.strategy.graham_growth.config import GrahamGrowthConfig
from src.analysis.strategy.graham_number.config import GrahamNumberConfig
from src.analysis.strategy.momentum.momentum_analyzer import MomentumConfig
from src.config import settings
from src.core.constants import ConfigKeys

# Provider identifiers supported by the current CLI composition. These mirror the
# stable IDs declared in ``src.data.massive.constants``,
# ``src.data.sec_edgar.financial_facts`` and ``src.data.yfinance.client``; they are
# used as literals here (as the base Graham configs do) to keep this request model
# free of the production provider stack.
_CLI_SECURITY_PROVIDERS = ("sec_edgar", "massive")
_CLI_QUOTE_PROVIDERS = ("yfinance", "massive")


class _FrozenSelection(BaseModel):
    """Shared strictness for workspace selection snapshots."""

    model_config = ConfigDict(frozen=True, extra="forbid")


class MomentumSelection(_FrozenSelection):
    """Immutable snapshot of the effective Momentum configuration.

    The canonical analysis/method identifiers are fixed to the contract matrix values
    (``momentum`` / ``sma_crossover``) and cannot be overridden or made to disagree
    with one another. Window and RSI values are materialized from explicit inputs or
    the current configured policy at creation time; later settings changes do not
    affect an existing selection. Momentum accepts no ``as_of`` option.
    """

    analysis_id: Literal["momentum"] = "momentum"
    method_id: Literal["sma_crossover"] = "sma_crossover"
    config_schema_version: Literal[1] = 1
    short_window: int = Field(gt=0, strict=True)
    long_window: int = Field(gt=0, strict=True)
    rsi_period: int = Field(default=14, gt=0, strict=True)

    @model_validator(mode="after")
    def _validate_windows(self) -> "MomentumSelection":
        """Require a short window smaller than the long window, as the analyzer does."""
        if self.short_window >= self.long_window:
            raise ValueError("short_window must be smaller than long_window.")
        return self

    @classmethod
    def from_settings(
        cls,
        *,
        short_window: int | None = None,
        long_window: int | None = None,
        rsi_period: int | None = None,
        **overrides: object,
    ) -> "MomentumSelection":
        """Create a selection, materializing omitted values from configured policy.

        Window defaults follow the same ``window_sizes`` configuration table used by
        :class:`MomentumConfig`; the RSI period keeps that config's fixed 14 default
        because it is not part of the momentum settings file. Unknown keyword arguments
        are forwarded to validation so they are rejected with a standard extra-field
        error rather than a constructor TypeError.
        """
        values: dict[str, object] = {**overrides}
        window_sizes = (
            settings.get_momentum_analysis()[ConfigKeys.WINDOW_SIZES]
            if short_window is None or long_window is None
            else {}
        )
        if short_window is not None:
            values["short_window"] = short_window
        else:
            values["short_window"] = int(window_sizes[ConfigKeys.SHORT_WINDOW])
        if long_window is not None:
            values["long_window"] = long_window
        else:
            values["long_window"] = int(window_sizes[ConfigKeys.LONG_WINDOW])
        if rsi_period is not None:
            values["rsi_period"] = rsi_period
        return cls.model_validate(values)

    def to_momentum_config(self) -> MomentumConfig:
        """Return the existing analyzer config carrying this snapshot's values."""
        return MomentumConfig(
            short_window=self.short_window,
            long_window=self.long_window,
            rsi_period=self.rsi_period,
        )


class _GrahamSelection(_FrozenSelection):
    """Shared provider choices and immutable scalar configuration for Graham methods."""

    analysis_id: Literal["graham"] = "graham"
    config_schema_version: Literal[1] = 1
    security_provider_id: str = "sec_edgar"
    quote_provider_id: str | None = None
    eps_basis: Literal["three_year_average", "ttm"] | None = None
    eps_override: StrictFloat | None = None
    quote_override: StrictFloat | None = None
    as_of: AwareDatetime | None = None
    use_cache: bool = Field(default=True, strict=True)

    @field_validator("security_provider_id")
    @classmethod
    def _restrict_security_provider(cls, value: str) -> str:
        """Normalize and restrict the security-fact provider to CLI-supported choices."""
        normalized = value.strip().lower()
        if not normalized:
            raise ValueError("Provider identifier must not be blank.")
        if normalized not in _CLI_SECURITY_PROVIDERS:
            raise ValueError(
                f"Unsupported security provider {normalized!r}; supported providers are 'sec_edgar' and 'massive'."
            )
        return normalized

    @field_validator("quote_provider_id")
    @classmethod
    def _restrict_quote_provider(cls, value: str | None) -> str | None:
        """Normalize and restrict an explicit quote provider to CLI-supported choices."""
        if value is None:
            return None
        normalized = value.strip().lower()
        if not normalized:
            raise ValueError("Provider identifier must not be blank.")
        if normalized not in _CLI_QUOTE_PROVIDERS:
            raise ValueError(
                f"Unsupported quote provider {normalized!r}; supported providers are 'yfinance' and 'massive'."
            )
        return normalized

    @field_validator("eps_override", "quote_override")
    @classmethod
    def _require_finite_overrides(cls, value: float | None) -> float | None:
        """Reject NaN/Inf financial overrides at the workspace boundary."""
        if value is not None and not math.isfinite(value):
            raise ValueError("Financial override must be a finite number.")
        return value

    @field_validator("eps_basis", mode="before")
    @classmethod
    def _normalize_basis(cls, value: object) -> object:
        """Normalize explicit basis strings before validating supported literals."""
        return value.strip().lower() if isinstance(value, str) else value

    @model_validator(mode="after")
    def _resolve_effective_configuration(self) -> "_GrahamSelection":
        """Resolve the effective EPS basis/quote provider and enforce compatibility."""
        security_provider_id = self.security_provider_id
        if self.quote_provider_id is None:
            resolved_quote = "yfinance" if security_provider_id == "sec_edgar" else security_provider_id
        else:
            resolved_quote = self.quote_provider_id

        eps_basis = self.eps_basis or ("three_year_average" if security_provider_id == "sec_edgar" else "ttm")

        if security_provider_id == "sec_edgar" and eps_basis != "three_year_average":
            raise ValueError("SEC EDGAR financial data requires the three-year average EPS basis.")
        if security_provider_id == "massive" and eps_basis != "ttm":
            raise ValueError("Massive financial data requires the TTM EPS basis.")

        object.__setattr__(self, "quote_provider_id", resolved_quote)
        object.__setattr__(self, "eps_basis", eps_basis)
        return self


class GrahamNumberSelection(_GrahamSelection):
    """Immutable Graham Number selection with an optional book-value override."""

    method_id: Literal["graham_number"] = "graham_number"
    bvps_override: StrictFloat | None = None

    @field_validator("bvps_override")
    @classmethod
    def _finite_book_value(cls, value: float | None) -> float | None:
        return cls._require_finite_overrides(value)

    @model_validator(mode="after")
    def _require_massive_book_value(self) -> "GrahamNumberSelection":
        if self.security_provider_id == "massive" and self.bvps_override is None:
            raise ValueError("Massive provider requires an explicit book value per share override.")
        return self

    def to_graham_number_config(self) -> GrahamNumberConfig:
        """Return the existing analyzer config carrying this snapshot's values."""
        return GrahamNumberConfig(
            security_provider_id=self.security_provider_id,
            quote_provider_id=self.quote_provider_id,
            eps_basis=self.eps_basis,
            eps_override=self.eps_override,
            bvps_override=self.bvps_override,
            quote_override=self.quote_override,
            as_of=self.as_of,
            use_cache=self.use_cache,
        )


class GrahamGrowthSelection(_GrahamSelection):
    """Graham growth-value selection requiring explicit growth and AAA yield percentages."""

    method_id: Literal["graham_growth_value"] = "graham_growth_value"
    expected_growth: StrictFloat
    aaa_yield_override: StrictFloat

    @field_validator("expected_growth", "aaa_yield_override")
    @classmethod
    def _finite_assumption(cls, value: float) -> float:
        cls._require_finite_overrides(value)
        return value

    def to_graham_growth_config(self) -> GrahamGrowthConfig:
        """Return the existing config without deriving assumptions or calculation policy."""
        return GrahamGrowthConfig(
            security_provider_id=self.security_provider_id,
            quote_provider_id=self.quote_provider_id,
            eps_basis=self.eps_basis,
            eps_override=self.eps_override,
            quote_override=self.quote_override,
            expected_growth=self.expected_growth,
            aaa_yield_override=self.aaa_yield_override,
            as_of=self.as_of,
            use_cache=self.use_cache,
        )


class FCFPolicySnapshot(_FrozenSelection):
    """Validated immutable copy of the existing FCF policy and its native enums."""

    historical_horizon: HistoricalHorizon = HistoricalHorizon.LONGEST_AVAILABLE
    classification_basis: FCFClassificationBasis = FCFClassificationBasis.TOTAL_FCF
    forward_policy: ForwardPolicy = ForwardPolicy.DISPLAY_ONLY
    include_fcf_yield: bool = Field(default=True, strict=True)

    @model_validator(mode="before")
    @classmethod
    def _copy_existing_policy(cls, value: object) -> object:
        if isinstance(value, FCFEarningsGrowthPolicy):
            return {
                "historical_horizon": value.historical_horizon,
                "classification_basis": value.classification_basis,
                "forward_policy": value.forward_policy,
                "include_fcf_yield": value.include_fcf_yield,
            }
        return value

    def to_policy(self) -> FCFEarningsGrowthPolicy:
        """Return a fresh instance of the analyzer's existing policy dataclass."""
        return FCFEarningsGrowthPolicy(
            historical_horizon=self.historical_horizon,
            classification_basis=self.classification_basis,
            forward_policy=self.forward_policy,
            include_fcf_yield=self.include_fcf_yield,
        )


class FCFGrowthSelection(_FrozenSelection):
    """Historical FCF/Earnings Growth request options, independent of Graham configs."""

    analysis_id: Literal["fcf_earnings_growth"] = "fcf_earnings_growth"
    method_id: Literal["reported_fcf_eps_cagr"] = "reported_fcf_eps_cagr"
    config_schema_version: Literal[1] = 1
    policy: FCFPolicySnapshot = Field(default_factory=FCFPolicySnapshot)
    currency: str = "USD"
    provider_id: Literal["sec_edgar"] = "sec_edgar"
    as_of: AwareDatetime | None = None
    use_cache: bool = Field(default=True, strict=True)

    @field_validator("provider_id", mode="before")
    @classmethod
    def _normalize_provider(cls, value: object) -> object:
        return value.strip().lower() if isinstance(value, str) else value

    @field_validator("currency")
    @classmethod
    def _normalize_currency(cls, value: str) -> str:
        normalized = value.strip().upper()
        if len(normalized) != 3 or not normalized.isalpha():
            raise ValueError("currency must be a three-letter ISO 4217 code.")
        return normalized

    def to_fcf_policy(self) -> FCFEarningsGrowthPolicy:
        """Return the existing policy type for explicit analyzer invocation."""
        return self.policy.to_policy()


AnalysisSelection = Annotated[
    MomentumSelection | GrahamNumberSelection | GrahamGrowthSelection | FCFGrowthSelection,
    Field(discriminator="method_id"),
]


class AnalysisRequest(_FrozenSelection):
    """Bind a normalized ticker to one fully specified immutable method selection."""

    ticker: str
    selection: AnalysisSelection

    @field_validator("ticker")
    @classmethod
    def _normalize_ticker(cls, value: str) -> str:
        normalized = value.strip().upper()
        if not normalized:
            raise ValueError("ticker must not be empty.")
        return normalized


def default_selections() -> tuple[AnalysisSelection, ...]:
    """Materialize independent Momentum, Number and historical FCF defaults in order."""
    return (MomentumSelection.from_settings(), GrahamNumberSelection(), FCFGrowthSelection())
