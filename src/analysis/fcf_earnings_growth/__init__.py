"""Analysis modules for the free-cash-flow & earnings-growth strategy (Slice B).

Public exports for the pure calculation layer:

- ``HistoricalHorizon`` — historical horizon discriminator.
- ``ForwardPolicy`` — forward consensus policy discriminator.
- ``Classification`` — headline PASS/FAIL/INDETERMINATE conclusion.
- ``TrendClassification`` — historical relationship description.
- ``MetricStatus`` / ``ForwardEvidenceStatus`` — metric outcome discriminators.
- ``ReasonCode`` — machine-readable reason codes.
- ``FCFEarningsGrowthPolicy`` — investor-selectable policy.
- ``MetricResult`` — invariant-checked typed metric result.
- ``ForwardEvidence`` — forward consensus evidence block.
- ``AnnualGrowthObservation`` — one completed-fiscal-year observation.
- ``ClassificationDecision`` — outcome of the classification function.
- ``FCFEarningsGrowthResult`` — complete typed result.
- ``compute_free_cash_flow`` — pure FCF calculator.
- ``compute_growth_percent`` — pure one-period growth calculator.
- ``compute_cagr`` — pure compound annual growth calculator.
- ``compute_fcf_yield`` — pure informational FCF yield calculator.
- ``classify_fcf_earnings_growth`` — pure classification function.
"""

from src.analysis.fcf_earnings_growth.calculators import (
    classify_fcf_earnings_growth,
    compute_cagr,
    compute_fcf_yield,
    compute_free_cash_flow,
    compute_growth_percent,
)
from src.analysis.fcf_earnings_growth.models import (
    AnnualGrowthObservation,
    Classification,
    ClassificationDecision,
    FCFEarningsGrowthPolicy,
    FCFEarningsGrowthResult,
    ForwardEvidence,
    ForwardEvidenceStatus,
    ForwardPolicy,
    HistoricalHorizon,
    MetricResult,
    MetricStatus,
    ReasonCode,
    TrendClassification,
)
from src.core.analysis_status import CalculationStatus

__all__ = [
    "AnnualGrowthObservation",
    "CalculationStatus",
    "Classification",
    "ClassificationDecision",
    "FCFEarningsGrowthPolicy",
    "FCFEarningsGrowthResult",
    "ForwardEvidence",
    "ForwardEvidenceStatus",
    "ForwardPolicy",
    "HistoricalHorizon",
    "MetricResult",
    "MetricStatus",
    "ReasonCode",
    "TrendClassification",
    "classify_fcf_earnings_growth",
    "compute_cagr",
    "compute_fcf_yield",
    "compute_free_cash_flow",
    "compute_growth_percent",
]
