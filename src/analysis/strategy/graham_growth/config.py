"""Configuration for the graham_growth strategy."""

from __future__ import annotations

from typing import Self

from pydantic import StrictFloat, model_validator

from src.analysis.shared.graham_contracts import (
    GRAHAM_GROWTH_EXTRA_SEC_EDGAR_BASES,
    GrahamGrowthEPSBasis,
    _GrahamConfig,
)


class GrahamGrowthConfig(_GrahamConfig):
    """Growth-value request with explicit growth and AAA yield in percent units."""

    eps_basis: GrahamGrowthEPSBasis | None = None
    expected_growth: StrictFloat
    aaa_yield_override: StrictFloat

    @model_validator(mode="after")
    def validate_method(self) -> Self:
        """Resolve the provider-dependent EPS basis and quote provider.

        SEC EDGAR also accepts an explicit single completed fiscal-year basis alongside its
        three-year-average default, per `docs/user/FINANCE_MATH.md` §"EPS basis" — a documented,
        deliberately narrower capability than Graham Number's, not an oversight.
        """
        self._resolve_defaults(
            "three_year_average" if self.security_provider_id == "sec_edgar" else "ttm",
            extra_allowed_sec_edgar_bases=GRAHAM_GROWTH_EXTRA_SEC_EDGAR_BASES,
        )
        return self
