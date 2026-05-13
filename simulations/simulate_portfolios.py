"""
Portfolio Simulation Engine — Phase 2.
Simulates all 10 portfolio strategies using real yfinance price data.
Weights from alternative_portfolios/*.yaml applied to actual price returns.
Advisory only — no live trading. Simulated performance ≠ future results.
"""

from __future__ import annotations
import sys
from pathlib import Path
from datetime import date, timedelta

import pandas as pd
import numpy as np
import yaml

ROOT_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT_DIR / "src"))

from data_loader import get_price_history_multi, prices_to_cumulative_returns, get_risk_free_rate

DISCLAIMER = (
    "ADVISORY ONLY. All performance is SIMULATED using model allocations × historical prices. "
    "Not financial advice. Simulated performance does not predict future results."
)

INCEPTION_DATE = date(2026, 5, 13)
STARTING_CAPITAL = 100_000.0

# ─── Alternative portfolio weight maps ───────────────────────────────────────

PORTFOLIO_WEIGHTS: dict[str, dict[str, float]] = {
    "main_cio": {
        "SPY": 0.20, "QQQ": 0.15, "MSTR": 0.10,
        "GLD": 0.10, "URNM": 0.05, "STRC_PROXY": 0.40,
    },
    "aggressive_scarcity": {
        "MSTR": 0.30, "GLD": 0.25, "URNM": 0.20, "IBIT": 0.15, "XLE": 0.10,
    },
    "defensive_macro": {
        "STRC_PROXY": 0.40, "GLD": 0.30, "SLV": 0.10, "TLT": 0.10, "SPY": 0.10,
    },
    "momentum_heavy": {
        "QQQ": 0.35, "MSTR": 0.20, "GLD": 0.20, "SPY": 0.15, "STRC_PROXY": 0.10,
    },
    "technical_confirmation_only": {
        "SPY": 0.30, "QQQ": 0.25, "GLD": 0.20, "MSTR": 0.15, "STRC_PROXY": 0.10,
    },
    "contrarian_sentiment": {
        "STRC_PROXY": 0.60, "GLD": 0.20, "URNM": 0.20,
    },
    "crypto_heavy": {
        "MSTR": 0.40, "IBIT": 0.25, "COIN": 0.15, "CLSK": 0.10, "STRC_PROXY": 0.10,
    },
    "commodities_scarcity": {
        "GLD": 0.35, "URNM": 0.25, "SLV": 0.15, "XLE": 0.15, "COPX": 0.10,
    },
    "ai_structural_change": {
        "QQQ": 0.30, "NVDA": 0.20, "SMH": 0.20, "NEE": 0.10, "MSFT": 0.10, "STRC_PROXY": 0.10,
    },
    "strc_defensive": {
        "STRC_PROXY": 0.80, "GLD": 0.20,
    },
}

BENCHMARK_WEIGHTS: dict[str, dict[str, float]] = {
    "SPY": {"SPY": 1.0},
    "QQQ": {"QQQ": 1.0},
    "BTC": {"BTC": 1.0},
    "60_40": {"SPY": 0.60, "AGG": 0.40},
    "GLD": {"GLD": 1.0},
    "STRC": {"STRC_PROXY": 1.0},
}


def _all_tickers() -> list[str]:
    all_t: set[str] = set()
    for weights in {**PORTFOLIO_WEIGHTS, **BENCHMARK_WEIGHTS}.values():
        all_t.update(weights.keys())
    return list(all_t)


def _weighted_portfolio_returns(
    prices: pd.DataFrame,
    weights: dict[str, float],
    rebalance: str = "none",
) -> pd.Series:
    """
    Compute daily portfolio returns from price DataFrame and weight map.
    `rebalance` options: "none" (buy-and-hold), "monthly", "quarterly".
    """
    available = {t: w for t, w in weights.items() if t in prices.columns}
    if not available:
        return pd.Series(dtype=float)

    total_w = sum(available.values())
    norm_weights = {t: w / total_w for t, w in available.items()}

    price_df = prices[list(norm_weights.keys())].dropna(how="all").ffill()
    if price_df.empty:
        return pd.Series(dtype=float)

    # Buy-and-hold: initial weights drift with price
    if rebalance == "none":
        w_vec = pd.Series(norm_weights)
        initial_shares = w_vec / price_df.iloc[0]
        portfolio_value = (price_df * initial_shares).sum(axis=1)
        portfolio_value = portfolio_value / portfolio_value.iloc[0]
        return portfolio_value.pct_change().dropna()

    # Monthly rebalance
    returns = price_df.pct_change().dropna()
    w_vec = np.array([norm_weights[t] for t in price_df.columns])
    if rebalance == "monthly":
        freq = "ME"
    else:
        freq = "QE"

    port_returns = []
    periods = returns.resample(freq)
    for _, chunk in periods:
        if chunk.empty:
            continue
        r = chunk.values.dot(w_vec)
        port_returns.extend(r.tolist())

    idx = returns.index[: len(port_returns)]
    return pd.Series(port_returns, index=idx)


def simulate_portfolio(
    name: str,
    weights: dict[str, float],
    prices: pd.DataFrame,
    start: date,
) -> dict:
    """Simulate one portfolio from start date using buy-and-hold."""
    # Align to start date
    start_ts = pd.Timestamp(start)
    prices_from = prices[prices.index >= start_ts]

    if prices_from.empty or prices_from.shape[0] < 2:
        return {
            "name": name,
            "start_date": str(start),
            "end_date": str(date.today()),
            "total_return_pct": 0.0,
            "max_drawdown_pct": 0.0,
            "sharpe_ratio": 0.0,
            "annualized_return_pct": 0.0,
            "note": "Insufficient price data (inception date may be today)",
        }

    daily_ret = _weighted_portfolio_returns(prices_from, weights)
    if daily_ret.empty:
        return {"name": name, "note": "No price data for portfolio tickers."}

    cum_ret = (1 + daily_ret).cumprod()
    total_return = (cum_ret.iloc[-1] - 1) * 100
    days = (cum_ret.index[-1] - cum_ret.index[0]).days
    years = max(days / 365, 1 / 365)
    annualized = ((cum_ret.iloc[-1]) ** (1 / years) - 1) * 100

    # Max drawdown
    rolling_max = cum_ret.cummax()
    drawdown = (cum_ret - rolling_max) / rolling_max
    max_dd = abs(drawdown.min()) * 100

    # Sharpe
    rf = get_risk_free_rate()
    daily_rf = rf / 252
    excess = daily_ret - daily_rf
    sharpe = (excess.mean() / excess.std() * np.sqrt(252)) if excess.std() > 0 else 0.0

    return {
        "name": name,
        "start_date": str(prices_from.index[0].date()),
        "end_date": str(prices_from.index[-1].date()),
        "total_return_pct": round(total_return, 2),
        "annualized_return_pct": round(annualized, 2),
        "max_drawdown_pct": round(max_dd, 2),
        "sharpe_ratio": round(sharpe, 3),
        "trading_days": len(daily_ret),
        "nav_series": (cum_ret * STARTING_CAPITAL).to_dict(),
        "daily_returns": daily_ret.to_dict(),
        "note": DISCLAIMER,
    }


def simulate_all(
    start: date = INCEPTION_DATE,
    end: Optional[date] = None,
) -> dict[str, dict]:
    """
    Simulate all 10 alternative portfolios + 6 benchmarks.
    Returns dict keyed by portfolio name.
    """
    end = end or date.today()

    # Use 2-year lookback so charts have context even before inception
    lookback_start = start - timedelta(days=730)
    all_tickers = _all_tickers()

    print(f"  Fetching price data for {len(all_tickers)} tickers...")
    prices = get_price_history_multi(all_tickers, start=lookback_start, end=end)

    results = {}
    all_portfolios = {**PORTFOLIO_WEIGHTS, **{f"benchmark_{k}": v for k, v in BENCHMARK_WEIGHTS.items()}}
    for name, weights in all_portfolios.items():
        results[name] = simulate_portfolio(name, weights, prices, start)

    return results


def print_summary_table(results: dict[str, dict]) -> None:
    """Print a rich summary table of all portfolio results."""
    from rich.table import Table
    from rich.console import Console

    console = Console()
    table = Table(title=f"Portfolio Simulation — Inception: {INCEPTION_DATE}", show_lines=True)
    table.add_column("Portfolio", style="cyan", min_width=28)
    table.add_column("Total Return", justify="right")
    table.add_column("Ann. Return", justify="right")
    table.add_column("Max DD", justify="right")
    table.add_column("Sharpe", justify="right")

    order = list(PORTFOLIO_WEIGHTS.keys()) + [f"benchmark_{k}" for k in BENCHMARK_WEIGHTS]
    for name in order:
        r = results.get(name, {})
        tr = r.get("total_return_pct", 0)
        ann = r.get("annualized_return_pct", 0)
        dd = r.get("max_drawdown_pct", 0)
        sh = r.get("sharpe_ratio", 0)
        color = "green" if tr >= 0 else "red"
        table.add_row(
            name,
            f"[{color}]{tr:+.2f}%[/{color}]",
            f"[{color}]{ann:+.2f}%[/{color}]",
            f"[red]{dd:.2f}%[/red]",
            f"{sh:.3f}",
        )

    console.print(table)
    console.print(f"\n[dim]{DISCLAIMER}[/dim]")


from typing import Optional

if __name__ == "__main__":
    print(f"\n{DISCLAIMER}\n")
    print("Running simulation...")
    results = simulate_all()
    print_summary_table(results)
