"""
Confidence Engine — calculates portfolio and position confidence scores.
Implements the scoring logic from schemas/confidence_schema.yaml.
Advisory only — no live trading.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class ConfidenceFactors:
    macro_alignment: int = 50       # 1–100
    technical_confirmation: int = 50
    thesis_lifecycle_health: int = 50
    agent_consensus: int = 50
    risk_profile: int = 50
    sentiment_alignment: int = 50

    # Penalties applied automatically
    strong_dissent_count: int = 0       # agents strongly opposing
    invalidation_held: bool = False     # held past invalidation condition
    rsi_divergence_count: int = 0       # active RSI divergences at resistance
    phase_1_penalty: bool = True        # cap at 65 in Phase 1


def calculate_portfolio_confidence(factors: ConfidenceFactors) -> dict:
    """
    Calculate overall portfolio confidence score (1–100).
    Based on schemas/confidence_schema.yaml.
    """
    WEIGHTS = {
        "macro_alignment": 0.25,
        "technical_confirmation": 0.20,
        "thesis_lifecycle_health": 0.25,
        "agent_consensus": 0.15,
        "risk_profile": 0.10,
        "sentiment_alignment": 0.05,
    }

    weighted_score = (
        factors.macro_alignment * WEIGHTS["macro_alignment"]
        + factors.technical_confirmation * WEIGHTS["technical_confirmation"]
        + factors.thesis_lifecycle_health * WEIGHTS["thesis_lifecycle_health"]
        + factors.agent_consensus * WEIGHTS["agent_consensus"]
        + factors.risk_profile * WEIGHTS["risk_profile"]
        + factors.sentiment_alignment * WEIGHTS["sentiment_alignment"]
    )

    penalties = []

    if factors.strong_dissent_count >= 3:
        penalty = 15
        weighted_score -= penalty
        penalties.append(f"Strong dissent penalty: -{penalty} ({factors.strong_dissent_count} agents opposing)")

    if factors.invalidation_held:
        penalty = 20
        weighted_score -= penalty
        penalties.append(f"Invalidation held penalty: -{penalty} (position held past invalidation condition)")

    if factors.rsi_divergence_count > 0:
        penalty = factors.rsi_divergence_count * 5
        weighted_score -= penalty
        penalties.append(f"RSI divergence penalty: -{penalty} ({factors.rsi_divergence_count} active divergences)")

    if factors.phase_1_penalty:
        cap = 65
        if weighted_score > cap:
            penalties.append(f"Phase 1 cap: score capped at {cap} (no live data)")
            weighted_score = cap

    final_score = max(1, min(100, round(weighted_score)))

    level = _score_to_level(final_score)
    protocol = _get_protocol(final_score, factors)

    return {
        "score": final_score,
        "level": level,
        "factor_scores": {
            "macro_alignment": factors.macro_alignment,
            "technical_confirmation": factors.technical_confirmation,
            "thesis_lifecycle_health": factors.thesis_lifecycle_health,
            "agent_consensus": factors.agent_consensus,
            "risk_profile": factors.risk_profile,
            "sentiment_alignment": factors.sentiment_alignment,
        },
        "penalties_applied": penalties,
        "protocol": protocol,
    }


def _score_to_level(score: int) -> str:
    if score <= 20:
        return "Very Low"
    elif score <= 40:
        return "Low"
    elif score <= 60:
        return "Moderate"
    elif score <= 75:
        return "Moderately High"
    elif score <= 90:
        return "High"
    else:
        return "Very High"


def _get_protocol(score: int, factors: ConfidenceFactors) -> str:
    if score <= 40:
        return (
            "LOW CONFIDENCE PROTOCOL: Diagnose cause first. "
            "If uncertainty is unresolved, move incremental capital to STRC/money market/core only. "
            "Do NOT interpret low confidence as automatically defensive — diagnose first."
        )
    elif score <= 60:
        return "MODERATE CONFIDENCE: Standard sizing. Monitor closely. Require technical confirmation before adds."
    elif score <= 75:
        return "MODERATELY HIGH CONFIDENCE: Above-average sizing appropriate. Options convexity may be warranted."
    elif score <= 90:
        return "HIGH CONFIDENCE: Full target sizing. Consider options if asymmetry is clear."
    else:
        return "VERY HIGH CONFIDENCE: Can exceed standard bucket targets. Exceptional asymmetry case."


@dataclass
class PositionConfidence:
    ticker: str
    score: int
    level: str
    key_drivers: list[str] = field(default_factory=list)
    key_concerns: list[str] = field(default_factory=list)
    contrarian_view: str = ""
    what_would_raise: list[str] = field(default_factory=list)
    what_would_lower: list[str] = field(default_factory=list)
    invalidation_condition: str = ""


def build_position_confidence(
    ticker: str,
    score: int,
    drivers: list[str],
    concerns: list[str],
    contrarian_view: str,
    raise_conditions: list[str],
    lower_conditions: list[str],
    invalidation: str,
) -> PositionConfidence:
    """Build a PositionConfidence object for a given position."""
    return PositionConfidence(
        ticker=ticker,
        score=max(1, min(100, score)),
        level=_score_to_level(score),
        key_drivers=drivers,
        key_concerns=concerns,
        contrarian_view=contrarian_view,
        what_would_raise=raise_conditions,
        what_would_lower=lower_conditions,
        invalidation_condition=invalidation,
    )
