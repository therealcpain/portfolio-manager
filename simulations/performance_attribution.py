"""
Performance Attribution — Phase 2.
Decomposes portfolio returns into selection, timing, sizing, and options impact.
Advisory only — no live trading.
"""

from __future__ import annotations
import sys
from pathlib import Path
from datetime import date
from typing import Optional

import pandas as pd
import numpy as np

ROOT_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT_DIR / "src"))

DISCLAIMER = "ADVISORY ONLY. Attribution is SIMULATED. Not financial advice."


def position_contribution(
    ticker: str,
    weight: float,
    price_series: pd.Series,
    start: Optional[date] = None,
    end: Optional[date] = None,
) -> dict:
    """
    Calculate a single position's contribution to portfolio return.
    Contribution = weight × position_return.
    """
    if price_series.empty or len(price_series) < 2:
        return {"ticker": ticker, "weight": weight, "return_pct": 0.0, "contribution_pct": 0.0}

    s = price_series.copy()
    if start:
        s = s[s.index >= pd.Timestamp(start)]
    if end:
        s = s[s.index <= pd.Timestamp(end)]
    if s.empty or len(s) < 2:
        return {"ticker": ticker, "weight": weight, "return_pct": 0.0, "contribution_pct": 0.0}

    position_return = (s.iloc[-1] / s.iloc[0] - 1) * 100
    contribution = weight * position_return

    return {
        "ticker": ticker,
        "weight": round(weight, 4),
        "return_pct": round(position_return, 2),
        "contribution_pct": round(contribution, 2),
    }


def attribution_from_weights(
    weights: dict[str, float],
    price_df: pd.DataFrame,
    start: Optional[date] = None,
    end: Optional[date] = None,
) -> dict:
    """
    Full attribution breakdown for a weighted portfolio.
    Returns per-position contributions sorted by impact.
    """
    total_w = sum(weights.values())
    norm = {t: w / total_w for t, w in weights.items() if t in price_df.columns}

    contributions = []
    for ticker, weight in norm.items():
        s = price_df[ticker].dropna()
        contrib = position_contribution(ticker, weight, s, start, end)
        contributions.append(contrib)

    contributions.sort(key=lambda x: x["contribution_pct"], reverse=True)
    total_contribution = sum(c["contribution_pct"] for c in contributions)

    top_contributors = [c for c in contributions if c["contribution_pct"] > 0]
    top_detractors = [c for c in contributions if c["contribution_pct"] < 0]

    return {
        "total_portfolio_return_pct": round(total_contribution, 2),
        "contributions": contributions,
        "top_contributors": top_contributors[:3],
        "top_detractors": top_detractors[-3:] if top_detractors else [],
        "disclaimer": DISCLAIMER,
    }


def options_pnl_summary(options_log: list[dict]) -> dict:
    """
    Summarize options P&L from the options position log.
    Calculates net premium paid, realized P&L, and theta drag estimate.
    """
    if not options_log:
        return {
            "total_premium_paid": 0.0,
            "realized_pnl": 0.0,
            "unrealized_pnl": 0.0,
            "net_pnl": 0.0,
            "win_rate_pct": 0.0,
            "avg_hold_days": 0.0,
            "note": "No options positions recorded.",
        }

    total_premium = sum(p.get("total_premium_paid", 0) for p in options_log)
    realized = sum(p.get("realized_pnl", 0) for p in options_log if p.get("status") in ("Closed", "Expired"))
    unrealized = sum(p.get("unrealized_pnl", 0) for p in options_log if p.get("status") == "Active")
    wins = [p for p in options_log if p.get("realized_pnl", 0) > 0]

    return {
        "total_premium_paid": round(total_premium, 2),
        "realized_pnl": round(realized, 2),
        "unrealized_pnl": round(unrealized, 2),
        "net_pnl": round(realized + unrealized, 2),
        "win_rate_pct": round(len(wins) / len(options_log) * 100, 1) if options_log else 0.0,
        "positions_analyzed": len(options_log),
    }


def vs_simple_spy(
    portfolio_total_return_pct: float,
    spy_total_return_pct: float,
) -> dict:
    """The simplest attribution question: did we beat just owning SPY?"""
    alpha = portfolio_total_return_pct - spy_total_return_pct
    verdict = "Outperformed" if alpha > 0 else "Underperformed" if alpha < 0 else "Matched"
    return {
        "portfolio_return_pct": round(portfolio_total_return_pct, 2),
        "spy_return_pct": round(spy_total_return_pct, 2),
        "alpha_pct": round(alpha, 2),
        "verdict": verdict,
        "note": (
            f"{'Added' if alpha > 0 else 'Destroyed'} {abs(alpha):.2f}% vs simply owning SPY. "
            "Every active position must justify itself against this baseline."
        ),
    }
