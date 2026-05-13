"""Tests for thesis_memory.py"""

import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from thesis_memory import (
    LifecycleState,
    ThesisEvolutionType,
    ReviewTriggerType,
    DissentType,
    WatchStatus,
    ThesisMemory,
    WatchSetup,
    SignalActionRecord,
    ReviewAlert,
    create_thesis,
    update_lifecycle_state,
    add_thesis_evolution,
    record_confidence_snapshot,
    record_dissent,
    resolve_dissent,
    record_position_adjustment,
    record_signal_action,
    create_watch_setup,
    trigger_watch_setup,
    expire_watch_setup,
    invalidate_watch_setup,
    check_review_triggers,
    generate_thesis_daily_report,
    load_all_theses,
    load_thesis,
    load_watch_setups,
    load_signal_records,
    TERMINAL_STATES,
    WARNING_STATES,
    ACTIVE_STATES,
    LIFECYCLE_SIZING_GUIDANCE,
)


# ── Fixtures ──────────────────────────────────────────────────────────────────

VALID_THESIS_TEXT = (
    "Bitcoin is undergoing a structural re-rating as institutional capital flows accelerate "
    "via spot ETFs. The fixed supply combined with programmatic halving creates a demand shock "
    "in an environment of deteriorating fiat purchasing power."
)
VALID_INVALIDATION = ["BTC ETF inflows reverse for 60+ consecutive days", "Fed pivots to aggressive QT above 6%"]


def _create(tmp_path, ticker="MSTR", **overrides):
    db_path = tmp_path / "thesis_memory.json"
    with patch("thesis_memory.THESIS_MEMORY_PATH", db_path):
        defaults = dict(
            ticker=ticker,
            name="MicroStrategy BTC Proxy",
            original_thesis=VALID_THESIS_TEXT,
            macro_context="Fed on hold; dollar weakening; ETF inflows accelerating.",
            technical_context="MSTR above 200-day MA; RSI 58; no divergence.",
            sentiment_context="Crypto Fear & Greed at 62 (Greed). Not euphoric.",
            expected_regime="liquidity_expansion",
            invalidation_conditions=VALID_INVALIDATION,
            initial_confidence=65,
        )
        defaults.update(overrides)
        return create_thesis(**defaults)


# ── Enum completeness ─────────────────────────────────────────────────────────

def test_lifecycle_states_are_seven():
    values = {s.value for s in LifecycleState}
    assert "Emerging" in values
    assert "Confirming" in values
    assert "High Conviction" in values
    assert "Crowded" in values
    assert "Distribution Risk" in values
    assert "Breakdown Risk" in values
    assert "Invalidated" in values
    assert len(values) == 7


def test_review_trigger_types_are_six():
    values = {t.value for t in ReviewTriggerType}
    assert "macro_regime_change" in values
    assert "technical_breakdown" in values
    assert "liquidity_contraction" in values
    assert "sentiment_euphoria" in values
    assert "valuation_compression" in values
    assert "invalidation_of_assumptions" in values
    assert len(values) == 6


def test_thesis_evolution_types_are_six():
    values = {e.value for e in ThesisEvolutionType}
    assert "refinement" in values
    assert "strengthening" in values
    assert "weakening" in values
    assert "context_change" in values
    assert "regime_update" in values
    assert "invalidation_updated" in values


def test_dissent_types():
    values = {d.value for d in DissentType}
    assert "directional" in values
    assert "timing" in values
    assert "sizing" in values
    assert "risk" in values
    assert "regime" in values


def test_terminal_states_contains_invalidated():
    assert LifecycleState.INVALIDATED.value in TERMINAL_STATES


def test_warning_states_contain_three():
    assert len(WARNING_STATES) == 3
    assert LifecycleState.CROWDED.value in WARNING_STATES
    assert LifecycleState.DISTRIBUTION_RISK.value in WARNING_STATES
    assert LifecycleState.BREAKDOWN_RISK.value in WARNING_STATES


def test_active_states_contain_three():
    assert len(ACTIVE_STATES) == 3
    assert LifecycleState.EMERGING.value in ACTIVE_STATES
    assert LifecycleState.CONFIRMING.value in ACTIVE_STATES
    assert LifecycleState.HIGH_CONVICTION.value in ACTIVE_STATES


def test_all_states_have_sizing_guidance():
    for state in LifecycleState:
        assert state.value in LIFECYCLE_SIZING_GUIDANCE


# ── Thesis creation ───────────────────────────────────────────────────────────

def test_create_thesis_sets_initial_state(tmp_path):
    thesis = _create(tmp_path)
    assert thesis.lifecycle_state == LifecycleState.EMERGING.value
    assert thesis.ticker == "MSTR"
    assert thesis.is_active is True


def test_create_thesis_stores_all_eleven_fields(tmp_path):
    thesis = _create(tmp_path)
    assert thesis.original_thesis == VALID_THESIS_TEXT
    assert thesis.macro_context != ""
    assert thesis.technical_context != ""
    assert thesis.sentiment_context != ""
    assert thesis.expected_regime != ""
    assert len(thesis.invalidation_conditions) >= 1
    assert isinstance(thesis.thesis_evolution, list)
    assert isinstance(thesis.lifecycle_history, list)
    assert isinstance(thesis.historical_adjustments, list)
    assert isinstance(thesis.associated_dissent, list)
    assert isinstance(thesis.confidence_history, list)


def test_create_thesis_records_initial_confidence(tmp_path):
    thesis = _create(tmp_path, initial_confidence=70)
    assert len(thesis.confidence_history) == 1
    assert thesis.confidence_history[0]["confidence_score"] == 70
    assert thesis.current_confidence == 70


def test_create_thesis_records_initial_lifecycle_event(tmp_path):
    thesis = _create(tmp_path)
    assert len(thesis.lifecycle_history) == 1
    assert thesis.lifecycle_history[0]["to_state"] == LifecycleState.EMERGING.value


def test_create_thesis_short_text_raises(tmp_path):
    db_path = tmp_path / "thesis_memory.json"
    import pytest
    with patch("thesis_memory.THESIS_MEMORY_PATH", db_path):
        with pytest.raises(AssertionError):
            create_thesis(
                ticker="MSTR",
                name="Test",
                original_thesis="Too short.",
                macro_context="ok",
                technical_context="ok",
                sentiment_context="ok",
                expected_regime="bull",
                invalidation_conditions=["something"],
            )


def test_create_thesis_no_invalidation_raises(tmp_path):
    db_path = tmp_path / "thesis_memory.json"
    import pytest
    with patch("thesis_memory.THESIS_MEMORY_PATH", db_path):
        with pytest.raises(AssertionError):
            create_thesis(
                ticker="MSTR",
                name="Test",
                original_thesis=VALID_THESIS_TEXT,
                macro_context="ok",
                technical_context="ok",
                sentiment_context="ok",
                expected_regime="bull",
                invalidation_conditions=[],
            )


def test_create_thesis_persisted_and_loadable(tmp_path):
    db_path = tmp_path / "thesis_memory.json"
    with patch("thesis_memory.THESIS_MEMORY_PATH", db_path):
        original = _create(tmp_path, ticker="IBIT")
        loaded = load_thesis(original.position_id)
    assert loaded is not None
    assert loaded.ticker == "IBIT"
    assert loaded.original_thesis == original.original_thesis


def test_load_thesis_returns_none_for_unknown(tmp_path):
    db_path = tmp_path / "thesis_memory.json"
    with patch("thesis_memory.THESIS_MEMORY_PATH", db_path):
        result = load_thesis("POS-NONEXISTENT")
    assert result is None


# ── Lifecycle transitions ─────────────────────────────────────────────────────

def test_lifecycle_transition_emerging_to_confirming(tmp_path):
    db_path = tmp_path / "thesis_memory.json"
    with patch("thesis_memory.THESIS_MEMORY_PATH", db_path):
        thesis = _create(tmp_path)
        updated = update_lifecycle_state(
            thesis.position_id,
            LifecycleState.CONFIRMING.value,
            "Multiple technical confirmations received.",
            "technical_chart_expert",
        )
    assert updated.lifecycle_state == LifecycleState.CONFIRMING.value
    assert len(updated.lifecycle_history) == 2
    assert updated.lifecycle_history[-1]["from_state"] == LifecycleState.EMERGING.value
    assert updated.lifecycle_history[-1]["to_state"] == LifecycleState.CONFIRMING.value


def test_lifecycle_transition_to_warning_state(tmp_path):
    db_path = tmp_path / "thesis_memory.json"
    with patch("thesis_memory.THESIS_MEMORY_PATH", db_path):
        thesis = _create(tmp_path)
        updated = update_lifecycle_state(
            thesis.position_id,
            LifecycleState.DISTRIBUTION_RISK.value,
            "Smart money flows reversing.",
            "sentiment_analyst",
        )
    assert updated.is_warning is True


def test_lifecycle_transition_to_invalidated(tmp_path):
    db_path = tmp_path / "thesis_memory.json"
    with patch("thesis_memory.THESIS_MEMORY_PATH", db_path):
        thesis = _create(tmp_path)
        updated = update_lifecycle_state(
            thesis.position_id,
            LifecycleState.INVALIDATED.value,
            "BTC ETF inflows reversed for 65 consecutive days.",
            "human",
        )
    assert updated.lifecycle_state == LifecycleState.INVALIDATED.value
    assert updated.is_terminal is True


def test_terminal_state_blocks_further_transitions(tmp_path):
    db_path = tmp_path / "thesis_memory.json"
    import pytest
    with patch("thesis_memory.THESIS_MEMORY_PATH", db_path):
        thesis = _create(tmp_path)
        update_lifecycle_state(thesis.position_id, LifecycleState.INVALIDATED.value, "Invalidated.", "human")
        with pytest.raises(ValueError, match="terminal"):
            update_lifecycle_state(thesis.position_id, LifecycleState.EMERGING.value, "Reset.", "human")


def test_lifecycle_transition_unknown_id_raises(tmp_path):
    db_path = tmp_path / "thesis_memory.json"
    import pytest
    with patch("thesis_memory.THESIS_MEMORY_PATH", db_path):
        with pytest.raises(KeyError):
            update_lifecycle_state("POS-UNKNOWN", LifecycleState.CONFIRMING.value, "test", "test")


# ── Thesis evolution ──────────────────────────────────────────────────────────

def test_add_evolution_entry(tmp_path):
    db_path = tmp_path / "thesis_memory.json"
    with patch("thesis_memory.THESIS_MEMORY_PATH", db_path):
        thesis = _create(tmp_path)
        updated = add_thesis_evolution(
            thesis.position_id,
            ThesisEvolutionType.STRENGTHENING.value,
            "BlackRock ETF crossed $50B AUM — institutional adoption accelerating beyond initial model.",
            "macro_strategist",
        )
    assert len(updated.thesis_evolution) == 1
    assert updated.thesis_evolution[0]["evolution_type"] == ThesisEvolutionType.STRENGTHENING.value


def test_multiple_evolution_entries_accumulate(tmp_path):
    db_path = tmp_path / "thesis_memory.json"
    with patch("thesis_memory.THESIS_MEMORY_PATH", db_path):
        thesis = _create(tmp_path)
        add_thesis_evolution(thesis.position_id, ThesisEvolutionType.STRENGTHENING.value, "Bullish update.", "agent_a")
        updated = add_thesis_evolution(thesis.position_id, ThesisEvolutionType.WEAKENING.value, "Bearish update.", "agent_b")
    assert len(updated.thesis_evolution) == 2


def test_evolution_invalid_type_raises(tmp_path):
    db_path = tmp_path / "thesis_memory.json"
    import pytest
    with patch("thesis_memory.THESIS_MEMORY_PATH", db_path):
        thesis = _create(tmp_path)
        with pytest.raises(AssertionError):
            add_thesis_evolution(thesis.position_id, "invalid_type", "test", "agent")


# ── Confidence tracking ───────────────────────────────────────────────────────

def test_record_confidence_snapshot(tmp_path):
    db_path = tmp_path / "thesis_memory.json"
    with patch("thesis_memory.THESIS_MEMORY_PATH", db_path):
        thesis = _create(tmp_path, initial_confidence=60)
        updated = record_confidence_snapshot(
            thesis.position_id,
            confidence_score=75,
            regime="liquidity_expansion",
            key_factors=["ETF inflows strong", "Technical breakout confirmed"],
        )
    assert len(updated.confidence_history) == 2
    assert updated.current_confidence == 75


def test_confidence_out_of_range_raises(tmp_path):
    db_path = tmp_path / "thesis_memory.json"
    import pytest
    with patch("thesis_memory.THESIS_MEMORY_PATH", db_path):
        thesis = _create(tmp_path)
        with pytest.raises(AssertionError):
            record_confidence_snapshot(thesis.position_id, 105, "bull", ["test"])


def test_confidence_history_accumulates(tmp_path):
    db_path = tmp_path / "thesis_memory.json"
    with patch("thesis_memory.THESIS_MEMORY_PATH", db_path):
        thesis = _create(tmp_path, initial_confidence=50)
        record_confidence_snapshot(thesis.position_id, 60, "bull", ["improving"])
        updated = record_confidence_snapshot(thesis.position_id, 70, "bull", ["confirmed"])
    assert len(updated.confidence_history) == 3
    assert updated.current_confidence == 70


# ── Dissent recording ─────────────────────────────────────────────────────────

def test_record_dissent(tmp_path):
    db_path = tmp_path / "thesis_memory.json"
    with patch("thesis_memory.THESIS_MEMORY_PATH", db_path):
        thesis = _create(tmp_path)
        updated = record_dissent(
            thesis.position_id,
            agent="bear_case_analyst",
            dissent_type=DissentType.TIMING.value,
            description="Thesis is correct but timing is early — ETF inflows not yet self-sustaining.",
        )
    assert len(updated.associated_dissent) == 1
    assert updated.associated_dissent[0]["agent"] == "bear_case_analyst"
    assert len(updated.unresolved_dissent) == 1


def test_resolve_dissent(tmp_path):
    db_path = tmp_path / "thesis_memory.json"
    with patch("thesis_memory.THESIS_MEMORY_PATH", db_path):
        thesis = _create(tmp_path)
        record_dissent(thesis.position_id, "bear_case_analyst", DissentType.TIMING.value, "Too early.")
        loaded = load_thesis(thesis.position_id)
        dissent_id = loaded.associated_dissent[0]["id"]
        updated = resolve_dissent(thesis.position_id, dissent_id, "Timing confirmed — ETF flows now self-sustaining.")
    assert updated.associated_dissent[0]["resolved"] is True
    assert len(updated.unresolved_dissent) == 0


def test_resolve_unknown_dissent_raises(tmp_path):
    db_path = tmp_path / "thesis_memory.json"
    import pytest
    with patch("thesis_memory.THESIS_MEMORY_PATH", db_path):
        thesis = _create(tmp_path)
        with pytest.raises(KeyError):
            resolve_dissent(thesis.position_id, "DIS-NONEXISTENT", "notes")


# ── Position adjustments ──────────────────────────────────────────────────────

def test_record_adjustment(tmp_path):
    db_path = tmp_path / "thesis_memory.json"
    with patch("thesis_memory.THESIS_MEMORY_PATH", db_path):
        thesis = _create(tmp_path)
        updated = record_position_adjustment(
            thesis.position_id,
            action="add",
            size_pct=2.5,
            reason="Technical breakout confirmed with volume. Adding to position.",
            confidence_at_time=72,
        )
    assert len(updated.historical_adjustments) == 1
    assert updated.historical_adjustments[0]["action"] == "add"
    assert updated.historical_adjustments[0]["size_pct"] == 2.5


def test_exit_marks_thesis_inactive(tmp_path):
    db_path = tmp_path / "thesis_memory.json"
    with patch("thesis_memory.THESIS_MEMORY_PATH", db_path):
        thesis = _create(tmp_path)
        updated = record_position_adjustment(
            thesis.position_id,
            action="exit",
            size_pct=100.0,
            reason="Invalidation condition met.",
            confidence_at_time=10,
        )
    assert updated.is_active is False


def test_invalid_action_raises(tmp_path):
    db_path = tmp_path / "thesis_memory.json"
    import pytest
    with patch("thesis_memory.THESIS_MEMORY_PATH", db_path):
        thesis = _create(tmp_path)
        with pytest.raises(AssertionError):
            record_position_adjustment(thesis.position_id, "yolo", 5.0, "test", 50)


# ── Signal/Action separation ──────────────────────────────────────────────────

def test_record_signal_action_creates_paired_record(tmp_path):
    db_path = tmp_path / "thesis_memory.json"
    with patch("thesis_memory.THESIS_MEMORY_PATH", db_path):
        record = record_signal_action(
            ticker="MSTR",
            signal_type="Momentum_Breakout_Early",
            signal_description="MSTR 4-hour RSI divergence confirmed. Momentum improving across last 3 sessions.",
            action_taken="No portfolio change.",
            action_rationale="Weekly resistance at $600 unconfirmed. Waiting for weekly close above $600 with volume confirmation before adding to position.",
            watch_triggers=["Weekly close above $600 with volume >150% of 20-day avg"],
            regime_at_signal="liquidity_expansion",
            requires_immediate_action=False,
        )
    assert record.signal.ticker == "MSTR"
    assert record.action.action_taken == "No portfolio change."
    assert not record.action.requires_immediate_action
    assert len(record.action.watch_triggers) == 1


def test_signal_action_summary_has_required_fields(tmp_path):
    db_path = tmp_path / "thesis_memory.json"
    with patch("thesis_memory.THESIS_MEMORY_PATH", db_path):
        record = record_signal_action(
            ticker="IBIT",
            signal_type="Breakout_Above_Resistance",
            signal_description="IBIT broke above $45 resistance with strong volume.",
            action_taken="Added 1.5% to position.",
            action_rationale="Breakout confirmed on weekly close with volume 2x the 20-day average. Thesis at Confirming state.",
            watch_triggers=["IBIT holds above $45 for 2 weeks"],
            requires_immediate_action=True,
            sizing_implication="Bring position to 8% of portfolio.",
        )
    summary = record.summary()
    assert "signal" in summary
    assert "action" in summary
    assert "rationale" in summary
    assert "watch_triggers" in summary
    assert summary["requires_immediate_action"] is True


def test_signal_action_persisted(tmp_path):
    db_path = tmp_path / "thesis_memory.json"
    with patch("thesis_memory.THESIS_MEMORY_PATH", db_path):
        record_signal_action(
            ticker="GLD",
            signal_type="Momentum_Fading",
            signal_description="GLD momentum fading on 4h chart.",
            action_taken="No portfolio change.",
            action_rationale="Fading momentum in isolation not sufficient — waiting for RSI divergence confirmation.",
            watch_triggers=["Daily RSI divergence on GLD"],
        )
        signals = load_signal_records()
    assert len(signals) == 1


def test_explicit_no_action_is_valid_decision(tmp_path):
    """The 'no action' decision is as valid and important as an action decision."""
    db_path = tmp_path / "thesis_memory.json"
    with patch("thesis_memory.THESIS_MEMORY_PATH", db_path):
        record = record_signal_action(
            ticker="MSTR",
            signal_type="Momentum_Breakout_Early",
            signal_description="Momentum improving.",
            action_taken="No portfolio change yet because resistance remains unconfirmed.",
            action_rationale="Resistance at $480 unconfirmed. Intraday spikes are not confirmation.",
            watch_triggers=["Weekly close above $480"],
        )
    assert "No portfolio change" in record.action.action_taken
    assert not record.action.requires_immediate_action


# ── Watch setups ──────────────────────────────────────────────────────────────

def test_create_watch_setup(tmp_path):
    db_path = tmp_path / "thesis_memory.json"
    with patch("thesis_memory.THESIS_MEMORY_PATH", db_path):
        setup = create_watch_setup(
            ticker="MSTR",
            name="MSTR breakout above $600",
            setup_description="MSTR consolidating above $450 support. Watching for breakout above $600.",
            entry_triggers=["Weekly close above $600", "MSTR/BTC ratio improving"],
            exit_triggers=["Weekly close below $420", "BTC dominance falls below 55%"],
            patience_note="Do not enter on intraday spikes — wait for weekly confirmation only.",
            expiry_days=60,
        )
    assert setup.status == WatchStatus.WATCHING.value
    assert setup.is_active
    assert len(setup.entry_triggers) == 2
    assert len(setup.exit_triggers) == 2
    assert setup.expiry_date is not None


def test_create_watch_setup_no_entry_triggers_raises(tmp_path):
    db_path = tmp_path / "thesis_memory.json"
    import pytest
    with patch("thesis_memory.THESIS_MEMORY_PATH", db_path):
        with pytest.raises(AssertionError):
            create_watch_setup(
                ticker="MSTR",
                name="test",
                setup_description="test",
                entry_triggers=[],
                exit_triggers=["some exit"],
                patience_note="Wait for it.",
            )


def test_create_watch_setup_no_exit_triggers_raises(tmp_path):
    db_path = tmp_path / "thesis_memory.json"
    import pytest
    with patch("thesis_memory.THESIS_MEMORY_PATH", db_path):
        with pytest.raises(AssertionError):
            create_watch_setup(
                ticker="MSTR",
                name="test",
                setup_description="test",
                entry_triggers=["some trigger"],
                exit_triggers=[],
                patience_note="Wait for it.",
            )


def test_trigger_watch_setup_changes_status(tmp_path):
    db_path = tmp_path / "thesis_memory.json"
    with patch("thesis_memory.THESIS_MEMORY_PATH", db_path):
        setup = create_watch_setup(
            ticker="MSTR",
            name="test",
            setup_description="test",
            entry_triggers=["weekly close above $600"],
            exit_triggers=["close below $420"],
            patience_note="Wait for weekly confirmation.",
        )
        triggered = trigger_watch_setup(setup.id)
    assert triggered.status == WatchStatus.TRIGGERED.value
    assert triggered.triggered_date is not None
    assert not triggered.is_active


def test_expire_watch_setup(tmp_path):
    db_path = tmp_path / "thesis_memory.json"
    with patch("thesis_memory.THESIS_MEMORY_PATH", db_path):
        setup = create_watch_setup(
            ticker="MSTR",
            name="test",
            setup_description="test",
            entry_triggers=["trigger"],
            exit_triggers=["exit"],
            patience_note="Wait patiently.",
        )
        expired = expire_watch_setup(setup.id, "60-day window closed without trigger.")
    assert expired.status == WatchStatus.EXPIRED.value
    assert not expired.is_active


def test_invalidate_watch_setup(tmp_path):
    db_path = tmp_path / "thesis_memory.json"
    with patch("thesis_memory.THESIS_MEMORY_PATH", db_path):
        setup = create_watch_setup(
            ticker="MSTR",
            name="test",
            setup_description="test",
            entry_triggers=["trigger"],
            exit_triggers=["BTC below $75k"],
            patience_note="Wait for weekly close confirmation before acting.",
        )
        inv = invalidate_watch_setup(setup.id, "BTC fell below $75k — setup premise invalid.")
    assert inv.status == WatchStatus.INVALIDATED.value
    assert "below $75k" in inv.invalidation_reason


def test_trigger_unknown_setup_raises(tmp_path):
    db_path = tmp_path / "thesis_memory.json"
    import pytest
    with patch("thesis_memory.THESIS_MEMORY_PATH", db_path):
        with pytest.raises(KeyError):
            trigger_watch_setup("WATCH-NONEXISTENT")


# ── Review triggers ───────────────────────────────────────────────────────────

def _base_thesis(tmp_path):
    db_path = tmp_path / "thesis_memory.json"
    with patch("thesis_memory.THESIS_MEMORY_PATH", db_path):
        return _create(tmp_path)


def test_macro_regime_change_triggers_alert(tmp_path):
    db_path = tmp_path / "thesis_memory.json"
    with patch("thesis_memory.THESIS_MEMORY_PATH", db_path):
        thesis = _create(tmp_path)  # expected_regime = "liquidity_expansion"
    alerts = check_review_triggers(thesis, current_regime="liquidity_tightening")
    types = [a.trigger_type for a in alerts]
    assert ReviewTriggerType.MACRO_REGIME_CHANGE.value in types


def test_no_regime_alert_when_matching(tmp_path):
    db_path = tmp_path / "thesis_memory.json"
    with patch("thesis_memory.THESIS_MEMORY_PATH", db_path):
        thesis = _create(tmp_path)  # expected_regime = "liquidity_expansion"
    alerts = check_review_triggers(thesis, current_regime="liquidity_expansion")
    types = [a.trigger_type for a in alerts]
    assert ReviewTriggerType.MACRO_REGIME_CHANGE.value not in types


def test_technical_breakdown_triggers_alert(tmp_path):
    db_path = tmp_path / "thesis_memory.json"
    with patch("thesis_memory.THESIS_MEMORY_PATH", db_path):
        thesis = _create(tmp_path)
    alerts = check_review_triggers(thesis, is_below_support=True)
    types = [a.trigger_type for a in alerts]
    assert ReviewTriggerType.TECHNICAL_BREAKDOWN.value in types


def test_liquidity_contraction_triggers_alert(tmp_path):
    db_path = tmp_path / "thesis_memory.json"
    with patch("thesis_memory.THESIS_MEMORY_PATH", db_path):
        thesis = _create(tmp_path)
    alerts = check_review_triggers(thesis, liquidity_contracting=True)
    types = [a.trigger_type for a in alerts]
    assert ReviewTriggerType.LIQUIDITY_CONTRACTION.value in types


def test_sentiment_euphoria_triggers_alert(tmp_path):
    db_path = tmp_path / "thesis_memory.json"
    with patch("thesis_memory.THESIS_MEMORY_PATH", db_path):
        thesis = _create(tmp_path)
    alerts = check_review_triggers(thesis, sentiment_score=85.0)
    types = [a.trigger_type for a in alerts]
    assert ReviewTriggerType.SENTIMENT_EUPHORIA.value in types


def test_sentiment_below_threshold_no_alert(tmp_path):
    db_path = tmp_path / "thesis_memory.json"
    with patch("thesis_memory.THESIS_MEMORY_PATH", db_path):
        thesis = _create(tmp_path)
    alerts = check_review_triggers(thesis, sentiment_score=65.0)
    types = [a.trigger_type for a in alerts]
    assert ReviewTriggerType.SENTIMENT_EUPHORIA.value not in types


def test_valuation_compression_triggers_alert(tmp_path):
    db_path = tmp_path / "thesis_memory.json"
    with patch("thesis_memory.THESIS_MEMORY_PATH", db_path):
        thesis = _create(tmp_path)
    alerts = check_review_triggers(thesis, valuation_compressed=True)
    types = [a.trigger_type for a in alerts]
    assert ReviewTriggerType.VALUATION_COMPRESSION.value in types


def test_assumption_violation_triggers_alert(tmp_path):
    db_path = tmp_path / "thesis_memory.json"
    with patch("thesis_memory.THESIS_MEMORY_PATH", db_path):
        thesis = _create(tmp_path)
    alerts = check_review_triggers(thesis, assumptions_violated=["ETF inflows reversed"])
    types = [a.trigger_type for a in alerts]
    assert ReviewTriggerType.INVALIDATION_OF_ASSUMPTIONS.value in types


def test_known_invalidation_condition_flagged_in_alert(tmp_path):
    db_path = tmp_path / "thesis_memory.json"
    with patch("thesis_memory.THESIS_MEMORY_PATH", db_path):
        thesis = _create(tmp_path)
    # VALID_INVALIDATION[0] = "BTC ETF inflows reverse for 60+ consecutive days"
    alerts = check_review_triggers(thesis, assumptions_violated=["BTC ETF inflows reverse for 60+ consecutive days"])
    assert any("matches thesis invalidation condition" in a.description for a in alerts)


def test_no_alerts_when_clean(tmp_path):
    db_path = tmp_path / "thesis_memory.json"
    with patch("thesis_memory.THESIS_MEMORY_PATH", db_path):
        thesis = _create(tmp_path)
    alerts = check_review_triggers(
        thesis,
        current_regime="liquidity_expansion",
        is_below_support=False,
        sentiment_score=60.0,
        liquidity_contracting=False,
        valuation_compressed=False,
    )
    assert alerts == []


def test_alert_has_severity(tmp_path):
    db_path = tmp_path / "thesis_memory.json"
    with patch("thesis_memory.THESIS_MEMORY_PATH", db_path):
        thesis = _create(tmp_path)
    alerts = check_review_triggers(thesis, is_below_support=True)
    for alert in alerts:
        assert alert.severity in ("critical", "high", "medium", "low")


def test_review_alert_to_dict(tmp_path):
    db_path = tmp_path / "thesis_memory.json"
    with patch("thesis_memory.THESIS_MEMORY_PATH", db_path):
        thesis = _create(tmp_path)
    alerts = check_review_triggers(thesis, is_below_support=True)
    assert len(alerts) > 0
    d = alerts[0].to_dict()
    for key in ("position_id", "ticker", "trigger_type", "severity", "recommended_action"):
        assert key in d


# ── Daily report ──────────────────────────────────────────────────────────────

def test_daily_report_structure(tmp_path):
    db_path = tmp_path / "thesis_memory.json"
    with patch("thesis_memory.THESIS_MEMORY_PATH", db_path):
        _create(tmp_path, ticker="MSTR")
        _create(tmp_path, ticker="GLD")
        report = generate_thesis_daily_report(current_regime="liquidity_expansion")

    assert report["active_theses"] == 2
    assert len(report["positions"]) == 2
    assert "critical_alerts" in report
    assert "high_alerts" in report
    assert "active_watch_setups" in report
    assert "disciplined_patience_note" in report
    assert len(report["disciplined_patience_note"]) > 0


def test_daily_report_warnings_first(tmp_path):
    db_path = tmp_path / "thesis_memory.json"
    with patch("thesis_memory.THESIS_MEMORY_PATH", db_path):
        t1 = _create(tmp_path, ticker="MSTR")
        t2 = _create(tmp_path, ticker="GLD")
        update_lifecycle_state(
            t2.position_id,
            LifecycleState.DISTRIBUTION_RISK.value,
            "Distribution signals.",
            "human",
        )
        report = generate_thesis_daily_report()

    # Warning thesis (GLD) should appear first
    assert report["positions"][0]["ticker"] == "GLD"


def test_daily_report_includes_watch_setups(tmp_path):
    db_path = tmp_path / "thesis_memory.json"
    with patch("thesis_memory.THESIS_MEMORY_PATH", db_path):
        create_watch_setup(
            ticker="MSTR",
            name="Breakout watch",
            setup_description="Watching MSTR for breakout.",
            entry_triggers=["Weekly close above $600"],
            exit_triggers=["Close below $420"],
            patience_note="Wait for weekly close.",
        )
        report = generate_thesis_daily_report()

    assert len(report["active_watch_setups"]) == 1


def test_daily_report_counts_signals(tmp_path):
    db_path = tmp_path / "thesis_memory.json"
    with patch("thesis_memory.THESIS_MEMORY_PATH", db_path):
        record_signal_action(
            ticker="MSTR",
            signal_type="Momentum_Breakout_Early",
            signal_description="Momentum improving.",
            action_taken="No portfolio change yet.",
            action_rationale="Waiting for weekly close confirmation above resistance.",
            watch_triggers=["Weekly close above $480"],
        )
        report = generate_thesis_daily_report()

    assert report["signal_records_count"] == 1


# ── ThesisMemory helpers ──────────────────────────────────────────────────────

def test_thesis_daily_status(tmp_path):
    db_path = tmp_path / "thesis_memory.json"
    with patch("thesis_memory.THESIS_MEMORY_PATH", db_path):
        thesis = _create(tmp_path)
    status = thesis.daily_status()
    for key in ("position_id", "ticker", "lifecycle_state", "sizing_guidance",
                "is_warning", "is_terminal", "current_confidence", "expected_regime"):
        assert key in status


def test_thesis_to_dict_and_from_dict_roundtrip(tmp_path):
    db_path = tmp_path / "thesis_memory.json"
    with patch("thesis_memory.THESIS_MEMORY_PATH", db_path):
        thesis = _create(tmp_path)
    d = thesis.to_dict()
    restored = ThesisMemory.from_dict(d)
    assert restored.ticker == thesis.ticker
    assert restored.original_thesis == thesis.original_thesis
    assert restored.expected_regime == thesis.expected_regime
    assert len(restored.invalidation_conditions) == len(thesis.invalidation_conditions)


def test_load_all_theses(tmp_path):
    db_path = tmp_path / "thesis_memory.json"
    with patch("thesis_memory.THESIS_MEMORY_PATH", db_path):
        _create(tmp_path, ticker="MSTR")
        _create(tmp_path, ticker="GLD")
        _create(tmp_path, ticker="URNM")
        theses = load_all_theses()
    assert len(theses) == 3
    tickers = {t.ticker for t in theses}
    assert tickers == {"MSTR", "GLD", "URNM"}
