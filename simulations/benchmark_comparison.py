"""
Benchmark Comparison — full implementation with real metrics.
Sharpe, Sortino, alpha, beta, max drawdown vs all benchmarks.
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

DISCLAIMER = "ADVISORY ONLY. All figures are SIMULATED. Not financial advice."


def calculate_sharpe(returns, risk_free_rate: float = 0.045) -> float:
    """Annualized Sharpe ratio from daily return series."""
    returns = pd.Series(returns)
    if returns.empty or len(returns) < 2:
        return 0.0
    daily_rf = risk_free_rate / 252
    excess = returns - daily_rf
    std = excess.std()
    if std == 0:
        return 0.0
    return float((excess.mean() / std) * np.sqrt(252))


def calculate_sortino(returns, risk_free_rate: float = 0.045) -> float:
    """Annualized Sortino ratio (penalizes only downside volatility)."""
    returns = pd.Series(returns)
    if returns.empty or len(returns) < 2:
        return 0.0
    daily_rf = risk_free_rate / 252
    excess = returns - daily_rf
    downside = excess[excess < 0]
    if downside.empty or downside.std() == 0:
        return 0.0
    return float((excess.mean() / downside.std()) * np.sqrt(252))


def calculate_max_drawdown(prices) -> float:
    """Maximum peak-to-trough drawdown as a positive percentage."""
    prices = pd.Series(prices)
    if prices.empty:
        return 0.0
    peak = prices.cummax()
    drawdown = (prices - peak) / peak
    return float(abs(drawdown.min()) * 100)


def calculate_beta(portfolio_returns: pd.Series, market_returns: pd.Series) -> float:
    """OLS beta of portfolio vs market."""
    aligned = pd.concat([portfolio_returns, market_returns], axis=1).dropna()
    if aligned.empty or len(aligned) < 2:
        return 1.0
    cov = aligned.cov().iloc[0, 1]
    var = aligned.iloc[:, 1].var()
    return float(cov / var) if var > 0 else 1.0


def calculate_alpha(
    portfolio_returns: pd.Series,
    market_returns: pd.Series,
    risk_free_rate: float = 0.045,
) -> float:
    """Jensen's alpha (annualized)."""
    beta = calculate_beta(portfolio_returns, market_returns)
    daily_rf = risk_free_rate / 252
    port_excess = portfolio_returns.mean() - daily_rf
    mkt_excess = market_returns.mean() - daily_rf
    alpha_daily = port_excess - beta * mkt_excess
    return float(alpha_daily * 252 * 100)  # annualized %


def calculate_calmar(annualized_return_pct: float, max_drawdown_pct: float) -> float:
    """Calmar ratio: annualized return / max drawdown."""
    if max_drawdown_pct == 0:
        return 0.0
    return round(annualized_return_pct / max_drawdown_pct, 3)


def calculate_win_rate(returns: pd.Series) -> float:
    """Percentage of days with positive return."""
    if returns.empty:
        return 0.0
    return float((returns > 0).sum() / len(returns) * 100)


def full_metrics(
    portfolio_nav: pd.Series,
    spy_nav: Optional[pd.Series] = None,
    risk_free_rate: float = 0.045,
) -> dict:
    """Compute the full metrics suite for a portfolio NAV series."""
    if portfolio_nav.empty or len(portfolio_nav) < 2:
        return {"note": "Insufficient data — started today or no price history yet."}

    returns = portfolio_nav.pct_change().dropna()
    total_ret = (portfolio_nav.iloc[-1] / portfolio_nav.iloc[0] - 1) * 100
    days = (portfolio_nav.index[-1] - portfolio_nav.index[0]).days
    years = max(days / 365, 1 / 365)
    ann_ret = ((portfolio_nav.iloc[-1] / portfolio_nav.iloc[0]) ** (1 / years) - 1) * 100

    metrics = {
        "total_return_pct": round(total_ret, 2),
        "annualized_return_pct": round(ann_ret, 2),
        "max_drawdown_pct": round(calculate_max_drawdown(portfolio_nav), 2),
        "sharpe_ratio": round(calculate_sharpe(returns, risk_free_rate), 3),
        "sortino_ratio": round(calculate_sortino(returns, risk_free_rate), 3),
        "win_rate_pct": round(calculate_win_rate(returns), 1),
        "trading_days": len(returns),
        "volatility_ann_pct": round(returns.std() * np.sqrt(252) * 100, 2),
    }

    if spy_nav is not None and not spy_nav.empty:
        spy_returns = spy_nav.pct_change().dropna()
        aligned = pd.concat([returns, spy_returns], axis=1).dropna()
        if len(aligned) >= 2:
            port_r, spy_r = aligned.iloc[:, 0], aligned.iloc[:, 1]
            metrics["beta_vs_spy"] = round(calculate_beta(port_r, spy_r), 3)
            metrics["alpha_vs_spy_ann_pct"] = round(calculate_alpha(port_r, spy_r, risk_free_rate), 2)
            spy_total = (spy_nav.iloc[-1] / spy_nav.iloc[0] - 1) * 100
            metrics["vs_spy_pct"] = round(total_ret - spy_total, 2)
            metrics["calmar_ratio"] = calculate_calmar(ann_ret, metrics["max_drawdown_pct"])

    return metrics


def compare_all(simulation_results: dict[str, dict], risk_free_rate: float = 0.045) -> dict:
    """
    Given simulation results dict, compute full comparative metrics.
    Returns summary table suitable for reporting.
    """
    # Reconstruct NAV series from simulation results
    def to_nav(result: dict) -> pd.Series:
        nav_dict = result.get("nav_series", {})
        if not nav_dict:
            return pd.Series(dtype=float)
        s = pd.Series({pd.Timestamp(k): v for k, v in nav_dict.items()})
        return s.sort_index()

    spy_nav = to_nav(simulation_results.get("benchmark_SPY", {}))
    comparison = {}
    for name, result in simulation_results.items():
        nav = to_nav(result)
        if nav.empty:
            comparison[name] = {"note": result.get("note", "No data")}
        else:
            comparison[name] = full_metrics(nav, spy_nav, risk_free_rate)
            comparison[name]["name"] = result.get("name", name)

    return comparison


def opportunity_cost_alert(
    portfolio_return: float,
    strc_return: float,
    period_months: int,
) -> Optional[str]:
    """Alert if STRC / money market beats the portfolio."""
    if portfolio_return < strc_return:
        return (
            f"⚠️  OPPORTUNITY COST ALERT: Portfolio +{portfolio_return:.1f}% vs "
            f"STRC +{strc_return:.1f}% over {period_months} months. "
            "Active management is not adding value vs risk-free rate. "
            "Review allocation and agent performance."
        )
    return None
