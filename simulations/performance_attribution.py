"""
Performance Attribution — decomposes portfolio returns into components.
Phase 2: asset selection, timing, sizing, options impact.
Phase 1: stub only.
Advisory only — no live trading.
"""

from __future__ import annotations
from dataclasses import dataclass
from typing import Optional

PHASE = 1
DISCLAIMER = "ADVISORY ONLY. All figures are SIMULATED. Not financial advice."


@dataclass
class AttributionResult:
    total_return_pct: float
    asset_selection_contribution: float
    timing_contribution: float
    sizing_contribution: float
    options_contribution: float  # net of theta decay
    cash_drag: float
    benchmark_comparison: dict[str, float]
    note: str = "[SIMULATED - Phase 2+]"


def calculate_attribution(
    portfolio_positions: list[dict],
    trade_log: list[dict],
    price_data: dict[str, list[float]],
    start_date: str,
    end_date: str,
) -> AttributionResult:
    """
    Calculate performance attribution.
    Phase 1: returns placeholder.
    Phase 2: implements Brinson-Hood-Beebower attribution model.
    """
    if PHASE < 2:
        return AttributionResult(
            total_return_pct=0,
            asset_selection_contribution=0,
            timing_contribution=0,
            sizing_contribution=0,
            options_contribution=0,
            cash_drag=0,
            benchmark_comparison={},
            note="Phase 2 — attribution requires price history and trade log. [SIMULATED]",
        )
    raise NotImplementedError("Phase 2 attribution not yet implemented.")


def get_options_pnl_summary(options_trade_log: list[dict]) -> dict:
    """
    Summarize options P&L: wins, losses, theta drag, net contribution.
    Phase 2 implementation.
    """
    if PHASE < 2:
        return {"note": "Phase 2 — options P&L tracking not yet implemented. [SIMULATED]"}
    raise NotImplementedError("Phase 2 not yet implemented.")
