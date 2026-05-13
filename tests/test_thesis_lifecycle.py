"""Tests for thesis_engine.py"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from thesis_engine import (
    Thesis,
    ThesisState,
    transition_thesis,
    get_theses_requiring_action,
    get_thesis_lifecycle_health_score,
    STATE_SIZING_GUIDANCE,
)


def _make_thesis(state: ThesisState) -> Thesis:
    return Thesis(
        id="TEST-001",
        name="Test Thesis",
        related_positions=["SPY"],
        lifecycle_state=state,
        time_horizon="Strategic",
        opened_date="2026-05-13",
        thesis="Test thesis description.",
        bull_case="Bull case.",
        bear_case="Bear case.",
        confidence_score=60,
        key_drivers=["Factor 1"],
        invalidation="Test invalidation condition.",
        review_trigger="Test trigger.",
        crowding_check="Not crowded.",
        next_review_date="2026-05-20",
    )


def test_all_states_have_sizing_guidance():
    for state in ThesisState:
        assert state in STATE_SIZING_GUIDANCE, f"Missing sizing guidance for {state}"


def test_transition_records_history():
    thesis = _make_thesis(ThesisState.EMERGING)
    thesis = transition_thesis(thesis, ThesisState.CONFIRMING, "Technical confirmation received.")
    assert thesis.lifecycle_state == ThesisState.CONFIRMING
    assert len(thesis.state_history) == 1
    assert thesis.state_history[0]["from"] == "Emerging"
    assert thesis.state_history[0]["to"] == "Confirming"


def test_action_required_states():
    action_states = [
        ThesisState.CROWDED,
        ThesisState.DISTRIBUTION_RISK,
        ThesisState.BREAKDOWN_RISK,
        ThesisState.INVALIDATED,
    ]
    for state in action_states:
        thesis = _make_thesis(state)
        assert thesis.is_action_required(), f"{state} should require action"


def test_no_action_for_healthy_states():
    safe_states = [ThesisState.EMERGING, ThesisState.CONFIRMING, ThesisState.HIGH_CONVICTION]
    for state in safe_states:
        thesis = _make_thesis(state)
        assert not thesis.is_action_required(), f"{state} should not require action"


def test_lifecycle_health_score_high_conviction():
    theses = [_make_thesis(ThesisState.HIGH_CONVICTION) for _ in range(3)]
    score = get_thesis_lifecycle_health_score(theses)
    assert score >= 80


def test_lifecycle_health_score_invalidated():
    theses = [_make_thesis(ThesisState.INVALIDATED)]
    score = get_thesis_lifecycle_health_score(theses)
    assert score <= 20


def test_get_theses_requiring_action():
    theses = [
        _make_thesis(ThesisState.HIGH_CONVICTION),
        _make_thesis(ThesisState.INVALIDATED),
        _make_thesis(ThesisState.CONFIRMING),
        _make_thesis(ThesisState.CROWDED),
    ]
    requiring_action = get_theses_requiring_action(theses)
    assert len(requiring_action) == 2
    states = {t.lifecycle_state for t in requiring_action}
    assert ThesisState.INVALIDATED in states
    assert ThesisState.CROWDED in states
