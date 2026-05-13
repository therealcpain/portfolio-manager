"""
Regime Engine — classifies the current macro regime.
Phase 1: manual input. Phase 3: driven by live macro data.
Advisory only — no live trading.
"""

from __future__ import annotations
from enum import Enum
from dataclasses import dataclass
from typing import Optional


class MacroRegime(str, Enum):
    RISK_ON_EXPANSION = "Risk-On Expansion"
    LATE_CYCLE_CAUTION = "Late Cycle Caution"
    STAGFLATION_RISK = "Stagflation Risk"
    RECESSION_RISK = "Recession Risk"
    LIQUIDITY_CONTRACTION = "Liquidity Contraction"
    LIQUIDITY_EXPANSION = "Liquidity Expansion"
    REFLATION = "Reflation"
    DISINFLATION = "Disinflation"
    DEFLATIONARY_SHOCK = "Deflationary Shock"
    UNKNOWN = "Unknown — Live Data Required"


@dataclass
class RegimeSignals:
    """Input signals used to determine regime. Phase 1: all manual/placeholder."""
    m2_yoy_pct: Optional[float] = None           # M2 money supply YoY change %
    fed_stance: Optional[str] = None             # Hiking | Pausing | Cutting
    real_rates: Optional[float] = None           # TIPS-implied real rate %
    yield_curve_2_10: Optional[float] = None     # 2yr - 10yr spread (bps)
    ism_manufacturing: Optional[float] = None    # ISM Manufacturing PMI
    credit_spread_hy: Optional[float] = None     # HY credit spread (bps)
    vix: Optional[float] = None                  # VIX level
    cpi_yoy: Optional[float] = None              # CPI YoY %
    gdp_growth: Optional[float] = None           # Real GDP growth YoY %
    data_source: str = "[LIVE DATA REQUIRED — Phase 3]"


@dataclass
class RegimeAssessment:
    regime: MacroRegime
    confidence: int  # 1–100
    rationale: str
    equity_stance: str  # Bullish | Neutral | Bearish
    btc_crypto_stance: str
    gold_stance: str
    commodity_stance: str
    dollar_stance: str
    bond_stance: str
    key_risks: list[str]
    data_source: str = "[LIVE DATA REQUIRED — Phase 3]"


def classify_regime(signals: RegimeSignals) -> RegimeAssessment:
    """
    Classify macro regime from input signals.
    Phase 1: returns UNKNOWN with placeholder confidence.
    Phase 3: implement full classification logic.
    """
    if signals.data_source == "[LIVE DATA REQUIRED — Phase 3]":
        return RegimeAssessment(
            regime=MacroRegime.UNKNOWN,
            confidence=0,
            rationale=(
                "Phase 1 — no live macro data available. "
                "Regime classification requires Phase 3 data integration. "
                "Manually set regime in config.yaml for now."
            ),
            equity_stance="Unknown",
            btc_crypto_stance="Unknown",
            gold_stance="Unknown",
            commodity_stance="Unknown",
            dollar_stance="Unknown",
            bond_stance="Unknown",
            key_risks=["[LIVE DATA REQUIRED]"],
            data_source=signals.data_source,
        )

    # Phase 3 implementation: rule-based regime classification
    # Example logic (to be expanded):
    # if signals.m2_yoy_pct > 5 and signals.fed_stance == "Cutting":
    #     regime = MacroRegime.LIQUIDITY_EXPANSION
    # elif signals.cpi_yoy > 4 and signals.gdp_growth < 1:
    #     regime = MacroRegime.STAGFLATION_RISK
    raise NotImplementedError("Phase 3 regime classification not yet implemented.")


REGIME_PORTFOLIO_IMPLICATIONS = {
    MacroRegime.RISK_ON_EXPANSION: {
        "core_target": 70,
        "defensive_target": 5,
        "options_bias": "calls",
        "note": "Full risk-on. Max core allocation. Favor growth, crypto, commodities.",
    },
    MacroRegime.LATE_CYCLE_CAUTION: {
        "core_target": 60,
        "defensive_target": 15,
        "options_bias": "mixed",
        "note": "Reduce tail risk. Add downside hedges. Trim most extended positions.",
    },
    MacroRegime.LIQUIDITY_CONTRACTION: {
        "core_target": 50,
        "defensive_target": 25,
        "options_bias": "puts",
        "note": "Defensive posture. Increase STRC. Reduce BTC-adjacent if BTC technical breaks.",
    },
    MacroRegime.RECESSION_RISK: {
        "core_target": 40,
        "defensive_target": 35,
        "options_bias": "puts",
        "note": "Significantly defensive. Gold outperforms. Reduce equities. Full de-risk if confirmed.",
    },
    MacroRegime.STAGFLATION_RISK: {
        "core_target": 55,
        "defensive_target": 20,
        "options_bias": "puts_on_growth",
        "note": "Commodities and gold outperform. Reduce growth equities. Uranium strong.",
    },
    MacroRegime.UNKNOWN: {
        "core_target": 60,
        "defensive_target": 15,
        "options_bias": "none",
        "note": "Regime unclear. Hold existing allocations. Await data.",
    },
}
