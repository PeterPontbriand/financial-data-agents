"""Method-specific Graham configuration without presentation or resource ownership."""

from typing import Literal, Self

from pydantic import AwareDatetime, BaseModel, ConfigDict, StrictFloat, field_validator, model_validator


class _GrahamConfig(BaseModel):
    """Common request fields; financial validity remains with execution services."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    security_provider_id: str = "sec_edgar"
    quote_provider_id: str | None = None
    eps_basis: Literal["three_year_average", "ttm"] | None = None
    eps_override: StrictFloat | None = None
    quote_override: StrictFloat | None = None
    as_of: AwareDatetime | None = None
    use_cache: bool = True

    @field_validator("security_provider_id", "quote_provider_id")
    @classmethod
    def normalize_provider(cls, value: str | None) -> str | None:
        """Normalize supplied provider identifiers without restricting injection."""
        if value is None:
            return None
        normalized = value.strip().lower()
        if not normalized:
            raise ValueError("Provider identifier must not be blank.")
        return normalized

    @field_validator("eps_basis", mode="before")
    @classmethod
    def normalize_basis(cls, value: object) -> object:
        """Normalize text before validating the supported EPS basis literals."""
        return value.strip().lower() if isinstance(value, str) else value

    def _resolve_defaults(self, default_basis: Literal["three_year_average", "ttm"]) -> None:
        basis = self.eps_basis or default_basis
        if self.security_provider_id == "sec_edgar" and basis != "three_year_average":
            raise ValueError("SEC EDGAR requires eps_basis='three_year_average'.")
        if self.security_provider_id == "massive" and basis != "ttm":
            raise ValueError("Massive requires eps_basis='ttm'.")
        quote_provider = self.quote_provider_id
        if quote_provider is None:
            quote_provider = "yfinance" if self.security_provider_id == "sec_edgar" else self.security_provider_id
        object.__setattr__(self, "eps_basis", basis)
        object.__setattr__(self, "quote_provider_id", quote_provider)


class GrahamNumberConfig(_GrahamConfig):
    """Graham Number request, defaulting to three-year-average fiscal EPS."""

    bvps_override: StrictFloat | None = None

    @model_validator(mode="after")
    def validate_method(self) -> Self:
        """Resolve defaults and enforce the provider-specific book-value contract."""
        self._resolve_defaults("three_year_average")
        if self.security_provider_id == "massive" and self.bvps_override is None:
            raise ValueError("Massive Graham Number requires bvps_override.")
        return self


class GrahamGrowthConfig(_GrahamConfig):
    """Growth-value request with explicit growth and AAA yield in percent units."""

    expected_growth: StrictFloat
    aaa_yield_override: StrictFloat

    @model_validator(mode="after")
    def validate_method(self) -> Self:
        """Resolve the provider-dependent EPS basis and quote provider."""
        self._resolve_defaults("three_year_average" if self.security_provider_id == "sec_edgar" else "ttm")
        return self
