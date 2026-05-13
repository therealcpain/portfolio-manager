"""
Benchmark Comparison — compares portfolio to all benchmarks and alternatives.
Phase 2: full comparison with Sharpe, drawdown, alpha.
Phase 1: stub only.
Advisory only — no live trading.
"""

from __future__ import annotations
from dataclasses import dataclass
from typing import Optional
import math

PHASE = 1
DISCLAIMER = "ADVISORY ONLY. All figures are SIMULATED. Not financial advice."

BENCHMARK_TICKERS = {
    "SPY": "S&P 500",
    "QQQ": "Nasdaq-100",
    "BTC-USD": "Bitcoin",
    "60_40": "60/40 Portfolio",
    "STRC": "STRC / Money Market",
}


@dataclass
class BenchmarkMetrics:
    name: str
    total_return_pct: float
    annualized_return_pct: float
    max_drawdown_pct: float
    sharpe_ratio: float
    sortino_ratio: float
    beta_vs_spy: float
    alpha_vs_spy: float
    note: str = "[SIMULATED - Phase 2+]"


def calculate_sharpe(returns: list[float], risk_free_rate: float = 0.045) -> float:
    """Calculate annualized Sharpe ratio from daily returns. Phase 2."""
    if not returns or len(returns) < 2:
        return 0.0
    daily_rf = risk_free_rate / 252
    excess = [r - daily_rf for r in returns]
    mean = sum(excess) / len(excess)
    variance = sum((r - mean) ** 2 for r in excess) / (len(excess) - 1)
    std = math.sqrt(variance)
    if std == 0:
        return 0.0
    return (mean / std) * math.sqrt(252)


def calculate_max_drawdown(prices: list[float]) -> float:
    """Calculate maximum drawdown from a price series. Phase 2."""
    if not prices:
        return 0.0
    peak = prices[0]
    max_dd = 0.0
    for price in prices:
        if price > peak:
            peak = price
        dd = (peak - price) / peak
        if dd > max_dd:
            max_dd = dd
    return max_dd * 100  # as percentage


def compare_all_benchmarks(
    portfolio_prices: list[float],
    benchmark_price_data: dict[str, list[float]],
    dates: list[str],
    risk_free_rate: float = 0.045,
) -> dict[str, BenchmarkMetrics]:
    """
    Compare portfolio against all benchmarks.
    Phase 1: placeholder. Phase 2: full implementation.
    """
    if PHASE < 2:
        return {
            name: BenchmarkMetrics(
                name=name,
                total_return_pct=0,
                annualized_return_pct=0,
                max_drawdown_pct=0,
                sharpe_ratio=0,
                sortino_ratio=0,
                beta_vs_spy=0,
                alpha_vs_spy=0,
                note="[SIMULATED - Phase 2+] Requires price history from Phase 3 data integration.",
            )
            for name in benchmark_price_data
        }
    raise NotImplementedError("Phase 2 not yet implemented.")


def opportunity_cost_alert(
    portfolio_return: float,
    strc_return: float,
    period_months: int,
) -> Optional[str]:
    """
    Alert if STRC / money market is outperforming the portfolio.
    This is the key opportunity cost check.
    """
    if portfolio_return < strc_return:
        return (
            f"⚠️  OPPORTUNITY COST ALERT: Portfolio returned {portfolio_return:.1f}% "
            f"vs STRC {strc_return:.1f}% over {period_months} months. "
            f"Active management is not adding value vs risk-free rate. "
            f"Review allocation and agent performance immediately."
        )
    return None


from typing import Optional
