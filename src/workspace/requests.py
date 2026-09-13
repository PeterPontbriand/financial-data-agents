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
from typing import Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, StrictFloat, field_validator, model_validator

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


class GrahamNumberSelection(_FrozenSelection):
    """Immutable snapshot of an effective Graham Number configuration.

    The canonical analysis/method identifiers are fixed (``graham`` /
    ``graham_number``). The security-fact provider is restricted to the CLI-supported
    SEC EDGAR or Massive choices; the EPS basis and quote provider resolve from it
    using the same rules as :class:`GrahamNumberConfig`. Non-finite financial
    overrides are rejected here rather than deferred to execution.
    """

    analysis_id: Literal["graham"] = "graham"
    method_id: Literal["graham_number"] = "graham_number"
    config_schema_version: Literal[1] = 1
    security_provider_id: str = "sec_edgar"
    quote_provider_id: str | None = None
    eps_basis: Literal["three_year_average", "ttm"] | None = None
    eps_override: StrictFloat | None = None
    bvps_override: StrictFloat | None = None
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

    @field_validator("eps_override", "bvps_override", "quote_override")
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
    def _resolve_effective_configuration(self) -> "GrahamNumberSelection":
        """Resolve the effective EPS basis/quote provider and enforce compatibility."""
        security_provider_id = self.security_provider_id
        if self.quote_provider_id is None:
            resolved_quote = "yfinance" if security_provider_id == "sec_edgar" else security_provider_id
        else:
            resolved_quote = self.quote_provider_id

        eps_basis = self.eps_basis or ("three_year_average" if security_provider_id == "sec_edgar" else "ttm")

        if security_provider_id == "sec_edgar" and eps_basis != "three_year_average":
            raise ValueError("SEC EDGAR financial data requires the three-year average EPS basis.")
        if security_provider_id == "massive":
            if eps_basis != "ttm":
                raise ValueError("Massive financial data requires the TTM EPS basis.")
            if self.bvps_override is None:
                raise ValueError("Massive provider requires an explicit book value per share override.")

        object.__setattr__(self, "quote_provider_id", resolved_quote)
        object.__setattr__(self, "eps_basis", eps_basis)
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
