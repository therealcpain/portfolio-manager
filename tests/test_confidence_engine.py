"""Tests for confidence_engine.py"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from confidence_engine import ConfidenceFactors, calculate_portfolio_confidence


def test_phase1_caps_at_65():
    factors = ConfidenceFactors(
        macro_alignment=100,
        technical_confirmation=100,
        thesis_lifecycle_health=100,
        agent_consensus=100,
        risk_profile=100,
        sentiment_alignment=100,
        phase_1_penalty=True,
    )
    result = calculate_portfolio_confidence(factors)
    assert result["score"] <= 65, "Phase 1 cap should not exceed 65"


def test_strong_dissent_penalty():
    factors = ConfidenceFactors(
        macro_alignment=80,
        technical_confirmation=80,
        thesis_lifecycle_health=80,
        agent_consensus=80,
        risk_profile=80,
        sentiment_alignment=80,
        strong_dissent_count=3,
        phase_1_penalty=False,
    )
    result_without_dissent = calculate_portfolio_confidence(
        ConfidenceFactors(macro_alignment=80, technical_confirmation=80, thesis_lifecycle_health=80,
                          agent_consensus=80, risk_profile=80, sentiment_alignment=80, phase_1_penalty=False)
    )
    result_with_dissent = calculate_portfolio_confidence(factors)
    assert result_with_dissent["score"] < result_without_dissent["score"]
    assert any("dissent" in p.lower() for p in result_with_dissent["penalties_applied"])


def test_invalidation_held_penalty():
    factors = ConfidenceFactors(
        macro_alignment=70, technical_confirmation=70, thesis_lifecycle_health=70,
        agent_consensus=70, risk_profile=70, sentiment_alignment=70,
        invalidation_held=True, phase_1_penalty=False,
    )
    result = calculate_portfolio_confidence(factors)
    assert any("invalidation" in p.lower() for p in result["penalties_applied"])


def test_score_is_bounded():
    # Minimum
    factors_low = ConfidenceFactors(
        macro_alignment=1, technical_confirmation=1, thesis_lifecycle_health=1,
        agent_consensus=1, risk_profile=1, sentiment_alignment=1,
        strong_dissent_count=5, invalidation_held=True, rsi_divergence_count=3,
        phase_1_penalty=False,
    )
    result_low = calculate_portfolio_confidence(factors_low)
    assert result_low["score"] >= 1

    # Maximum (no penalties, no phase cap)
    factors_high = ConfidenceFactors(
        macro_alignment=100, technical_confirmation=100, thesis_lifecycle_health=100,
        agent_consensus=100, risk_profile=100, sentiment_alignment=100,
        phase_1_penalty=False,
    )
    result_high = calculate_portfolio_confidence(factors_high)
    assert result_high["score"] <= 100


def test_low_confidence_protocol_triggered():
    factors = ConfidenceFactors(
        macro_alignment=20, technical_confirmation=20, thesis_lifecycle_health=20,
        agent_consensus=20, risk_profile=20, sentiment_alignment=20,
        phase_1_penalty=False,
    )
    result = calculate_portfolio_confidence(factors)
    assert result["score"] <= 40
    assert "LOW CONFIDENCE" in result["protocol"]
