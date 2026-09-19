"""Pure report replay for stored Analysis Runs (projection v1).

``project_run(run, options)`` renders an already-persisted ``AnalysisRun``
using only evidence captured when the run executed. It must never call
analyzers, financial calculators, providers, profile resolvers, mutable
caches, settings defaults, LLMs, or the current time: every value it shows
was decided at execution time, not at replay time.

Financial derivations that the live presenter computes at render time (for
Momentum, the SMA spread and its percentage) are read from the run's own
``presentation_inputs`` instead of being recomputed from raw metrics, so a
future change to that formula can never silently alter a historical
replay. Pure formatting/label helpers already used by the live direct
commands are reused as-is; only the financial-derivation substitution point
is new. This module owns exactly one supported projection version (v1);
an unsupported version or an unimplemented method/analysis pair raises
rather than guessing or upgrading silently.
"""

from dataclasses import dataclass

from src.analysis.strategy.momentum.momentum_analyzer import MomentumRun
from src.reporting.momentum import MomentumPresentation, render_momentum
from src.reporting.presentation import PresentationMode
from src.workspace.codecs import decode_evidence
from src.workspace.requests import MomentumSelection
from src.workspace.runs import AnalysisRun

_SUPPORTED_PROJECTION_VERSION = 1


class UnsupportedProjectionError(ValueError):
    """The run's projection version, or its (analysis_id, method_id), has no v1 replay."""


@dataclass(frozen=True)
class ReplayOptions:
    """Explicit view selection for one replay.

    Locale and time formatting are not configurable: projection v1 reuses
    the existing formatting helpers, which are already fixed to the
    en-CA-style number/currency conventions and ISO-8601 UTC timestamps
    the direct commands already show.
    """

    mode: PresentationMode = PresentationMode.CONCISE


def project_run(run: AnalysisRun, options: ReplayOptions | None = None) -> str:
    """Render one stored run using only its own captured evidence.

    Uses the run's own stored ``projection_version``; there is no automatic
    upgrade to a later version.

    Args:
        run: An already-persisted, reopened `AnalysisRun`.
        options: The requested view; defaults to the concise mode.

    Returns:
        The rendered text (or JSON document, when `options.mode` is JSON).

    Raises:
        UnsupportedProjectionError: If `run.projection_version` is not the
            one this module implements, or if no v1 replay exists yet for
            `run`'s `(analysis_id, method_id)` pair.
    """
    resolved_options = options if options is not None else ReplayOptions()
    if run.projection_version != _SUPPORTED_PROJECTION_VERSION:
        raise UnsupportedProjectionError(f"Unsupported projection version: {run.projection_version}.")
    if (run.analysis_id, run.method_id) == ("momentum", "sma_crossover"):
        return _project_momentum_v1(run, resolved_options)
    raise UnsupportedProjectionError(
        f"No v1 replay is implemented for analysis={run.analysis_id!r}, method={run.method_id!r}."
    )


def _project_momentum_v1(run: AnalysisRun, options: ReplayOptions) -> str:
    """Reconstruct a Momentum presentation from stored evidence only.

    Identity/kind evidence comes from the envelope's own ``instrument_profile``
    field rather than the native evidence's copy: Momentum's analyzer never
    sets `MomentumRun.instrument_profile` (the profile is composed outside the
    calculator), so that field is always null for this method and would
    otherwise render as "unavailable" even when a profile was captured.
    """
    # decode_evidence dispatches on (run.analysis_id, run.method_id), which project_run
    # already confirmed is momentum's pair; AnalysisRun's own validator likewise
    # guarantees requested_config/effective_config match that same pair. Neither
    # assertion below is user-facing validation — both are internal invariants
    # already enforced elsewhere, asserted here only so mypy can narrow the type.
    evidence = decode_evidence(run)
    assert isinstance(evidence, MomentumRun)
    selection = run.effective_config if run.effective_config is not None else run.requested_config
    assert isinstance(selection, MomentumSelection)

    # Unlike the envelope's typed fields, presentation_inputs is a generic JSON
    # mapping with no schema tying its keys to specific types; a reopened row is
    # a real system boundary, so this is genuine validation, not paranoia.
    presentation_inputs = run.presentation_inputs or {}
    captured_spread = presentation_inputs.get("sma_spread")
    captured_spread_percent = presentation_inputs.get("sma_spread_percent")
    if not isinstance(captured_spread, (float, int)) and captured_spread is not None:
        raise UnsupportedProjectionError("Stored sma_spread is not a finite number or null.")
    if not isinstance(captured_spread_percent, (float, int)) and captured_spread_percent is not None:
        raise UnsupportedProjectionError("Stored sma_spread_percent is not a finite number or null.")

    presentation = MomentumPresentation(
        metrics=evidence.metrics,
        config=selection.to_momentum_config(),
        market_data=evidence.market_data,
        resolution_trace=evidence.resolution_trace,
        data_resolution=evidence.data_resolution,
        instrument_profile=run.instrument_profile,
        use_captured_spread=True,
        captured_sma_spread=captured_spread,
        captured_sma_spread_percent=captured_spread_percent,
    )
    return render_momentum(presentation, options.mode)


__all__ = [
    "ReplayOptions",
    "UnsupportedProjectionError",
    "project_run",
]
