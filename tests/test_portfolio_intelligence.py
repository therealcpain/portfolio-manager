"""Tests for portfolio_intelligence.py"""

import sys
from pathlib import Path
from datetime import date, timedelta
import pandas as pd
import numpy as np

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from portfolio_intelligence import (
    classify_regime,
    analyze_regime_performance,
    analyze_why_outperformed,
    check_outperformance_trigger,
    check_underperformance_alert,
    WhyAnalysis,
    RegimePerformance,
    MIN_OBSERVATIONS_FOR_CONCLUSION,
    OUTPERFORMANCE_REVIEW_DAYS,
)


# ── Helpers ─────────────────────────────────────────────────────────────────

def _make_nav_series(n_days: int, daily_return: float, start: str = "2025-01-01") -> pd.Series:
    """Create a NAV series with a constant daily return."""
    dates = pd.date_range(start=start, periods=n_days, freq="B")
    values = [(1 + daily_return) ** i for i in range(n_days)]
    return pd.Series(values, index=dates)


def _make_mixed_nav(n_days: int, bull_return: float = 0.002, bear_return: float = -0.002) -> pd.Series:
    """Alternates between bull and bear returns every 30 days."""
    dates = pd.date_range(start="2025-01-01", periods=n_days, freq="B")
    values = [1.0]
    for i in range(1, n_days):
        ret = bull_return if (i // 30) % 2 == 0 else bear_return
        values.append(values[-1] * (1 + ret))
    return pd.Series(values, index=dates)


# ── Regime classification tests ──────────────────────────────────────────────

def test_classify_regime_bull():
    assert classify_regime(spy_return_20d=0.08) == "bull"


def test_classify_regime_bear():
    assert classify_regime(spy_return_20d=-0.08, vix_level=25) == "bear"


def test_classify_regime_risk_off():
    assert classify_regime(spy_return_20d=-0.08, vix_level=45) == "risk_off"


def test_classify_regime_sideways():
    assert classify_regime(spy_return_20d=0.01) == "sideways"


def test_classify_regime_sideways_negative_small():
    assert classify_regime(spy_return_20d=-0.03) == "sideways"


# ── Regime performance analysis tests ────────────────────────────────────────

def test_analyze_regime_performance_returns_list():
    portfolio_nav = _make_nav_series(100, 0.001)
    cio_nav = _make_nav_series(100, 0.0008)
    spy_nav = _make_mixed_nav(100)
    results = analyze_regime_performance(portfolio_nav, cio_nav, spy_nav)
    assert isinstance(results, list)


def test_analyze_regime_performance_empty_input():
    results = analyze_regime_performance(pd.Series(dtype=float), pd.Series(dtype=float), pd.Series(dtype=float))
    assert results == []


def test_analyze_regime_performance_has_required_fields():
    portfolio_nav = _make_nav_series(120, 0.001)
    cio_nav = _make_nav_series(120, 0.0008)
    spy_nav = _make_nav_series(120, 0.0006)
    results = analyze_regime_performance(portfolio_nav, cio_nav, spy_nav)
    if results:
        r = results[0]
        assert hasattr(r, "regime")
        assert hasattr(r, "observations")
        assert hasattr(r, "portfolio_return_pct")
        assert hasattr(r, "alpha_pct")
        assert hasattr(r, "max_drawdown_pct")
        assert hasattr(r, "win_rate_pct")


def test_regime_performance_note_for_small_n():
    portfolio_nav = _make_nav_series(5, 0.001)
    cio_nav = _make_nav_series(5, 0.0008)
    spy_nav = _make_nav_series(5, 0.0006)
    results = analyze_regime_performance(portfolio_nav, cio_nav, spy_nav)
    if results:
        r = results[0]
        if r.observations < MIN_OBSERVATIONS_FOR_CONCLUSION:
            assert len(r.note) > 0


def test_regime_performance_alpha_calculation():
    portfolio_nav = _make_nav_series(100, 0.002)   # outperforms
    cio_nav = _make_nav_series(100, 0.001)
    spy_nav = _make_nav_series(100, 0.001)
    results = analyze_regime_performance(portfolio_nav, cio_nav, spy_nav)
    if results:
        r = results[0]
        assert r.alpha_pct > 0  # portfolio outperforms CIO


# ── Why analysis tests ────────────────────────────────────────────────────────

def test_analyze_why_outperformed_returns_analysis():
    port_nav = _make_nav_series(60, 0.002)
    cio_nav = _make_nav_series(60, 0.001)
    weights_port = {"MSTR": 0.50, "GLD": 0.50}
    weights_cio = {"SPY": 0.60, "GLD": 0.40}
    result = analyze_why_outperformed(
        portfolio_id="ALT-TEST",
        portfolio_nav=port_nav,
        cio_nav=cio_nav,
        portfolio_weights=weights_port,
        cio_weights=weights_cio,
        price_data=pd.DataFrame(),
        intended_regime="bull",
        actual_regime="bull",
    )
    assert isinstance(result, WhyAnalysis)
    assert result.portfolio_id == "ALT-TEST"
    assert result.primary_driver in ("asset_selection", "regime_fit", "concentration", "cash_drag", "unclear")


def test_analyze_why_insufficient_data_not_conclusive():
    port_nav = _make_nav_series(5, 0.002)
    cio_nav = _make_nav_series(5, 0.001)
    result = analyze_why_outperformed(
        portfolio_id="ALT-TEST",
        portfolio_nav=port_nav,
        cio_nav=cio_nav,
        portfolio_weights={"MSTR": 1.0},
        cio_weights={"SPY": 1.0},
        price_data=pd.DataFrame(),
        intended_regime="bull",
        actual_regime="bull",
    )
    assert result.is_conclusive is False
    assert len(result.caveats) > 0


def test_analyze_why_sufficient_data_can_be_conclusive():
    port_nav = _make_nav_series(MIN_OBSERVATIONS_FOR_CONCLUSION + 5, 0.002)
    cio_nav = _make_nav_series(MIN_OBSERVATIONS_FOR_CONCLUSION + 5, 0.001)
    result = analyze_why_outperformed(
        portfolio_id="ALT-TEST",
        portfolio_nav=port_nav,
        cio_nav=cio_nav,
        portfolio_weights={"MSTR": 1.0},
        cio_weights={"SPY": 1.0},
        price_data=pd.DataFrame(),
        intended_regime="bull",
        actual_regime="bull",
    )
    assert result.is_conclusive is True


def test_analyze_why_regime_mismatch_flagged():
    port_nav = _make_nav_series(60, 0.002)
    cio_nav = _make_nav_series(60, 0.001)
    result = analyze_why_outperformed(
        portfolio_id="ALT-TEST",
        portfolio_nav=port_nav,
        cio_nav=cio_nav,
        portfolio_weights={"MSTR": 1.0},
        cio_weights={"SPY": 1.0},
        price_data=pd.DataFrame(),
        intended_regime="bear",
        actual_regime="bull",
    )
    assert any("mismatch" in c.lower() or "intended" in c.lower() for c in result.caveats)


def test_analyze_why_empty_nav():
    result = analyze_why_outperformed(
        portfolio_id="ALT-EMPTY",
        portfolio_nav=pd.Series(dtype=float),
        cio_nav=pd.Series(dtype=float),
        portfolio_weights={"SPY": 1.0},
        cio_weights={"SPY": 1.0},
        price_data=pd.DataFrame(),
        intended_regime="bull",
        actual_regime="bull",
    )
    assert result.is_conclusive is False
    assert result.primary_driver == "unclear"


def test_analyze_why_to_dict():
    port_nav = _make_nav_series(20, 0.001)
    cio_nav = _make_nav_series(20, 0.001)
    result = analyze_why_outperformed(
        portfolio_id="ALT-DICT",
        portfolio_nav=port_nav,
        cio_nav=cio_nav,
        portfolio_weights={"SPY": 1.0},
        cio_weights={"SPY": 1.0},
        price_data=pd.DataFrame(),
        intended_regime="bull",
        actual_regime="bull",
    )
    d = result.to_dict()
    assert "portfolio_id" in d
    assert "is_conclusive" in d
    assert "key_finding" in d
    assert "primary_driver" in d


# ── Constitutional trigger tests ─────────────────────────────────────────────

def test_outperformance_trigger_fires_after_90_days():
    port_nav = _make_nav_series(OUTPERFORMANCE_REVIEW_DAYS + 10, 0.002)
    cio_nav = _make_nav_series(OUTPERFORMANCE_REVIEW_DAYS + 10, 0.001)
    alert = check_outperformance_trigger("ALT-001", "Test Portfolio", port_nav, cio_nav, "bull")
    assert alert is not None
    assert alert.alert_type == "outperformance_review"
    assert alert.severity == "action_required"


def test_outperformance_trigger_does_not_fire_before_90_days():
    port_nav = _make_nav_series(OUTPERFORMANCE_REVIEW_DAYS - 5, 0.002)
    cio_nav = _make_nav_series(OUTPERFORMANCE_REVIEW_DAYS - 5, 0.001)
    alert = check_outperformance_trigger("ALT-001", "Test Portfolio", port_nav, cio_nav, "bull")
    assert alert is None


def test_outperformance_trigger_does_not_fire_when_trailing():
    port_nav = _make_nav_series(OUTPERFORMANCE_REVIEW_DAYS + 10, 0.001)
    cio_nav = _make_nav_series(OUTPERFORMANCE_REVIEW_DAYS + 10, 0.002)
    alert = check_outperformance_trigger("ALT-001", "Test Portfolio", port_nav, cio_nav, "bull")
    assert alert is None


def test_outperformance_trigger_to_dict():
    port_nav = _make_nav_series(OUTPERFORMANCE_REVIEW_DAYS + 10, 0.003)
    cio_nav = _make_nav_series(OUTPERFORMANCE_REVIEW_DAYS + 10, 0.001)
    alert = check_outperformance_trigger("ALT-001", "Test Portfolio", port_nav, cio_nav, "reflation")
    assert alert is not None
    d = alert.to_dict()
    assert "warning" in d.get("evidence", {})
    assert "Do not rebalance" in d["evidence"]["warning"]


def test_underperformance_alert_fires_when_lagging():
    port_nav = _make_nav_series(100, 0.0005)    # small gain
    cio_nav = _make_nav_series(100, 0.003)      # much larger gain
    alert = check_underperformance_alert("ALT-001", "Lagging Portfolio", port_nav, cio_nav, "bull")
    assert alert is not None
    assert alert.alert_type == "underperformance_alert"
    assert alert.severity == "warning"


def test_underperformance_alert_does_not_fire_when_competitive():
    port_nav = _make_nav_series(100, 0.002)
    cio_nav = _make_nav_series(100, 0.002)
    alert = check_underperformance_alert("ALT-001", "Competitive Portfolio", port_nav, cio_nav, "bull")
    assert alert is None


def test_underperformance_alert_empty():
    alert = check_underperformance_alert("ALT-001", "Test", pd.Series(dtype=float), pd.Series(dtype=float), "bull")
    assert alert is None
