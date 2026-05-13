"""Tests for routing_engine.py"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from routing_engine import (
    DecisionType,
    RoutingContext,
    route_decision,
    describe_routing_plan,
    ALL_SPECIALISTS,
    COORDINATORS,
)


def test_full_committee_engages_all_specialists():
    plan = route_decision(DecisionType.FULL_COMMITTEE)
    for specialist in ALL_SPECIALISTS:
        assert specialist in plan.specialists, f"{specialist} missing from FULL_COMMITTEE"


def test_technical_signal_only_technical_agents():
    plan = route_decision(DecisionType.TECHNICAL_SIGNAL)
    assert "technical_chart_expert" in plan.specialists
    assert "momentum_trader" in plan.specialists
    assert "risk_officer" in plan.specialists
    # Commodity and options specialists should NOT be engaged
    assert "commodity_specialist" not in plan.specialists
    assert "options_specialist" not in plan.specialists
    assert "crypto_strategist" not in plan.specialists


def test_crypto_change_engages_crypto_specialists():
    plan = route_decision(DecisionType.CRYPTO_CHANGE)
    assert "macro_strategist" in plan.specialists
    assert "crypto_strategist" in plan.specialists
    assert "scarcity_strategist" in plan.specialists
    assert "sentiment_analyst" in plan.specialists
    assert "risk_officer" in plan.specialists
    # Commodity specialist should NOT engage for pure crypto decision
    assert "commodity_specialist" not in plan.specialists


def test_options_review_excludes_commodity():
    plan = route_decision(DecisionType.OPTIONS_REVIEW)
    assert "options_specialist" in plan.specialists
    assert "technical_chart_expert" in plan.specialists
    assert "commodity_specialist" not in plan.specialists
    assert "crypto_strategist" not in plan.specialists


def test_high_confidence_triggers_meta_auditor():
    ctx = RoutingContext(aggregate_confidence=80)
    plan = route_decision(DecisionType.MACRO_UPDATE, ctx)
    assert "meta_philosophy_auditor" in plan.specialists
    assert "meta_philosophy_auditor" in plan.conditional_additions


def test_low_confidence_does_not_trigger_meta_auditor():
    ctx = RoutingContext(aggregate_confidence=60)
    plan = route_decision(DecisionType.MACRO_UPDATE, ctx)
    assert "meta_philosophy_auditor" not in plan.specialists


def test_repeat_sessions_trigger_psychological_agent():
    ctx = RoutingContext(sessions_same_asset=3)
    plan = route_decision(DecisionType.THESIS_REVIEW, ctx)
    assert "psychological_agent" in plan.specialists
    assert "psychological_agent" in plan.conditional_additions


def test_fewer_sessions_no_psychological_agent():
    ctx = RoutingContext(sessions_same_asset=2)
    plan = route_decision(DecisionType.THESIS_REVIEW, ctx)
    assert "psychological_agent" not in plan.specialists


def test_thesis_review_adds_domain_specialist():
    ctx = RoutingContext(thesis_domain_specialists=["commodity_specialist"])
    plan = route_decision(DecisionType.THESIS_REVIEW, ctx)
    assert "commodity_specialist" in plan.specialists
    assert "commodity_specialist" in plan.conditional_additions


def test_wave_sequence_has_three_waves():
    plan = route_decision(DecisionType.CRYPTO_CHANGE)
    assert len(plan.wave_sequence) == 3
    # Wave 3 is always CIO
    assert plan.wave_sequence[2] == ["cio"]


def test_wave1_is_specialists_only():
    plan = route_decision(DecisionType.OPTIONS_REVIEW)
    wave1 = plan.wave_sequence[0]
    for agent in wave1:
        assert agent in plan.specialists
        assert agent not in COORDINATORS


def test_skipped_agents_have_reasons():
    plan = route_decision(DecisionType.TECHNICAL_SIGNAL)
    # Some specialists must be skipped for TECHNICAL_SIGNAL
    assert len(plan.skipped) > 0
    for agent, reason in plan.skipped.items():
        assert len(reason) > 5, f"Skip reason too short for {agent}: '{reason}'"


def test_risk_alert_has_risk_dissent_coordinator():
    plan = route_decision(DecisionType.RISK_ALERT)
    assert "risk_dissent_coordinator" in plan.coordinators


def test_learning_review_has_learning_coordinator():
    plan = route_decision(DecisionType.LEARNING_REVIEW)
    assert "learning_coordinator" in plan.coordinators


def test_describe_routing_plan_returns_string():
    plan = route_decision(DecisionType.MACRO_UPDATE)
    description = describe_routing_plan(plan)
    assert isinstance(description, str)
    assert "Wave 1" in description
    assert "Wave 2" in description
    assert "Wave 3" in description
    assert "cio" in description


def test_all_decision_types_have_routing():
    for dt in DecisionType:
        plan = route_decision(dt)
        assert plan.decision_type == dt
        assert len(plan.wave_sequence) == 3
