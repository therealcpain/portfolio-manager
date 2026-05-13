"""Tests for benchmark_comparison.py"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / "simulations"))

from benchmark_comparison import (
    calculate_sharpe,
    calculate_max_drawdown,
    opportunity_cost_alert,
)


def test_sharpe_positive_returns():
    daily_returns = [0.001] * 252  # 0.1% per day
    sharpe = calculate_sharpe(daily_returns, risk_free_rate=0.045)
    assert sharpe > 0


def test_sharpe_zero_returns():
    daily_returns = [0.0] * 252
    sharpe = calculate_sharpe(daily_returns, risk_free_rate=0.045)
    assert sharpe <= 0  # returns below risk-free rate


def test_sharpe_empty():
    assert calculate_sharpe([]) == 0.0


def test_max_drawdown_no_drawdown():
    prices = [100, 105, 110, 115, 120]
    dd = calculate_max_drawdown(prices)
    assert dd == 0.0


def test_max_drawdown_simple():
    prices = [100, 120, 80, 90]  # 80 is peak-to-trough of 120 to 80
    dd = calculate_max_drawdown(prices)
    assert abs(dd - 33.33) < 0.1


def test_max_drawdown_empty():
    assert calculate_max_drawdown([]) == 0.0


def test_opportunity_cost_alert_triggered():
    alert = opportunity_cost_alert(portfolio_return=3.0, strc_return=4.5, period_months=6)
    assert alert is not None
    assert "OPPORTUNITY COST" in alert


def test_opportunity_cost_alert_not_triggered():
    alert = opportunity_cost_alert(portfolio_return=12.0, strc_return=4.5, period_months=6)
    assert alert is None
