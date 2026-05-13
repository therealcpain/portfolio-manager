"""
Portfolio Simulation Engine — Phase 2 implementation.
Simulates performance of main portfolio and all 10 alternatives from inception.
Phase 1: stub with placeholder returns.
Advisory only — no live trading. Past simulated performance ≠ future results.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path
from typing import Optional
import yaml

ROOT_DIR = Path(__file__).parent.parent
ALT_DIR = ROOT_DIR / "alternative_portfolios"
BENCHMARKS_DIR = ROOT_DIR / "benchmarks"

DISCLAIMER = "ADVISORY ONLY. All performance figures are SIMULATED model outputs. Not financial advice. Past simulated performance does not predict future results."
PHASE = 1


@dataclass
class PortfolioReturn:
    name: str
    start_date: str
    end_date: str
    starting_value: float
    ending_value: float
    total_return_pct: float
    max_drawdown_pct: float
    daily_returns: list[float] = field(default_factory=list)
    note: str = "[SIMULATED - Phase 2+]"


def simulate_all_portfolios(
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
) -> dict[str, PortfolioReturn]:
    """
    Simulate all portfolio strategies from start to end date.
    Phase 1: returns placeholder objects.
    Phase 2: implements actual price-weighted simulation from yfinance data.
    """
    start = start_date or date(2026, 5, 13)  # inception
    end = end_date or date.today()

    if PHASE < 2:
        placeholder = PortfolioReturn(
            name="[PLACEHOLDER]",
            start_date=str(start),
            end_date=str(end),
            starting_value=100000,
            ending_value=0,
            total_return_pct=0,
            max_drawdown_pct=0,
            note="Phase 2 — simulation engine not yet implemented. Requires live price data from Phase 3.",
        )
        portfolios = [
            "main_cio", "aggressive_scarcity", "defensive_macro", "momentum_heavy",
            "technical_confirmation_only", "contrarian_sentiment", "crypto_heavy",
            "commodities_scarcity", "ai_structural_change", "strc_defensive",
        ]
        return {name: PortfolioReturn(name=name, **{k: v for k, v in vars(placeholder).items() if k != "name"}) for name in portfolios}

    raise NotImplementedError("Phase 2 simulation engine not yet implemented.")


def compare_to_benchmarks(
    portfolio_return: PortfolioReturn,
    benchmark_returns: dict[str, float],
) -> dict:
    """Compare a portfolio's return to benchmarks. Phase 2 implementation."""
    if PHASE < 2:
        return {
            "portfolio": portfolio_return.name,
            "total_return": "[SIMULATED - Phase 2+]",
            "vs_spy": "[SIMULATED - Phase 2+]",
            "vs_btc": "[SIMULATED - Phase 2+]",
            "vs_strc": "[SIMULATED - Phase 2+]",
        }
    raise NotImplementedError("Phase 2 not yet implemented.")


def find_best_alternative(
    results: dict[str, PortfolioReturn],
) -> tuple[str, PortfolioReturn]:
    """Identify the best-performing alternative portfolio. Phase 2."""
    if PHASE < 2:
        return ("[SIMULATED - Phase 2+]", list(results.values())[0])
    best_name = max(results, key=lambda k: results[k].total_return_pct)
    return best_name, results[best_name]


if __name__ == "__main__":
    print(f"\n{DISCLAIMER}\n")
    results = simulate_all_portfolios()
    for name, result in results.items():
        print(f"  {name:<35} {result.note}")
    print(f"\nPhase 2 will implement full simulation from inception date.")
