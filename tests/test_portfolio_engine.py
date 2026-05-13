"""Tests for portfolio_engine.py"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from portfolio_engine import (
    Position,
    PortfolioState,
    calculate_total_return,
)


def test_calculate_total_return_positive():
    result = calculate_total_return(current_value=110000, starting_capital=100000)
    assert result["dollar_return"] == 10000
    assert result["pct_return"] == 10.0


def test_calculate_total_return_negative():
    result = calculate_total_return(current_value=85000, starting_capital=100000)
    assert result["dollar_return"] == -15000
    assert result["pct_return"] == -15.0


def test_calculate_total_return_flat():
    result = calculate_total_return(current_value=100000, starting_capital=100000)
    assert result["dollar_return"] == 0
    assert result["pct_return"] == 0.0


def test_portfolio_state_bucket_allocations():
    positions = [
        Position("SPY", "SPY ETF", "core_structural", 20000, 20.0, "Confirming", "Strategic", "", ""),
        Position("GLD", "Gold ETF", "core_structural", 10000, 10.0, "Confirming", "Structural", "", ""),
        Position("STRC", "STRC", "tactical_strategic", 10000, 10.0, "N/A", "Tactical", "", ""),
    ]
    state = PortfolioState(total_value=100000, cash_and_strc=60000, options_premium_at_risk=0, positions=positions)
    buckets = state.bucket_allocations
    assert abs(buckets.get("core_structural", 0) - 30.0) < 0.01
    assert abs(buckets.get("tactical_strategic", 0) - 10.0) < 0.01


def test_concentration_flag_triggered():
    positions = [
        Position("MSTR", "MicroStrategy", "core_structural", 20000, 20.0, "Confirming", "Strategic", "", ""),
    ]
    state = PortfolioState(total_value=100000, cash_and_strc=80000, options_premium_at_risk=0, positions=positions)
    flags = state.get_concentration_flags(single_name_threshold=15.0)
    assert len(flags) == 1
    assert "MSTR" in flags[0]


def test_concentration_flag_not_triggered():
    positions = [
        Position("SPY", "SPY", "core_structural", 10000, 10.0, "Confirming", "Strategic", "", ""),
    ]
    state = PortfolioState(total_value=100000, cash_and_strc=90000, options_premium_at_risk=0, positions=positions)
    flags = state.get_concentration_flags(single_name_threshold=15.0)
    assert len(flags) == 0
