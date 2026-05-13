"""Tests for portfolio_ledger.py — durable portfolio state persistence."""

from __future__ import annotations

import json
import pytest
from pathlib import Path
from unittest.mock import patch

from src.portfolio_ledger import (
    # Config / constants
    EventType,
    DISCLAIMER,
    # Record types
    LedgerEvent,
    PositionRecord,
    ThesisRecord,
    ConfidenceSnapshot,
    WatchEvent,
    DecisionRecord,
    # Narrative types
    PositionNarrative,
    ThesisEvolutionAssessment,
    # Write functions
    open_position,
    record_allocation_change,
    update_confidence,
    record_thesis_evolution,
    record_dissent,
    resolve_dissent,
    record_invalidation,
    update_lifecycle_state,
    add_to_watchlist,
    resolve_watchlist,
    record_decision,
    # Query functions (the 7 canonical questions)
    why_do_we_own,
    what_changed,
    what_were_concerns,
    what_invalidated,
    what_improved,
    original_thesis,
    did_thesis_evolve_correctly,
    # Read helpers
    get_position,
    get_all_positions,
    get_thesis_record,
    get_confidence_timeline,
    get_watchlist_history,
    get_active_watchlist,
    get_decision_audit,
    get_all_events,
    portfolio_summary,
    import_from_yaml,
    # Internal
    LEDGER_PATH,
)

TEST_DATE = "2026-05-13"
TICKER = "BTC"
THESIS_ID = "THESIS-BTC-001"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def clean_ledger(tmp_path, monkeypatch):
    """Each test gets a fresh empty ledger in a temp directory."""
    ledger = tmp_path / "portfolio_ledger.json"
    ledger.write_text(json.dumps({
        "events": [],
        "positions": {},
        "thesis_registry": {},
        "confidence_timeline": {},
        "watchlist_history": {},
        "decision_audit": [],
    }))
    monkeypatch.setattr("src.portfolio_ledger.LEDGER_PATH", ledger)
    yield ledger


def _open_btc(date_str=TEST_DATE, confidence=65, exposure=15.0):
    return open_position(
        ticker=TICKER,
        name="Bitcoin ETF",
        bucket="core_structural",
        thesis_id=THESIS_ID,
        original_thesis=(
            "Fixed 21M supply creates structural scarcity premium "
            "as institutional adoption accelerates via spot ETFs."
        ),
        macro_context="Fed cutting, M2 growing, risk-on regime",
        technical_context="Above 200d MA, BTC dominance rising",
        sentiment_context="Healthy skepticism — not yet euphoric",
        expected_regime="Risk-On Expansion",
        invalidation_conditions=[
            "BTC breaks 200d MA on volume",
            "ETF outflows sustained > 2 weeks",
        ],
        initial_exposure_pct=exposure,
        initial_confidence=confidence,
        date_str=date_str,
    )


# ===========================================================================
# EventType enum
# ===========================================================================

class TestEventTypeEnum:
    def test_all_position_types_present(self):
        values = {e.value for e in EventType}
        assert "position_opened" in values
        assert "position_trimmed" in values
        assert "position_added" in values
        assert "position_exited" in values

    def test_all_thesis_types_present(self):
        values = {e.value for e in EventType}
        assert "thesis_created" in values
        assert "thesis_evolved" in values
        assert "thesis_invalidated" in values
        assert "invalidation_updated" in values

    def test_all_ancillary_types_present(self):
        values = {e.value for e in EventType}
        assert "confidence_updated" in values
        assert "dissent_recorded" in values
        assert "dissent_resolved" in values
        assert "watchlist_added" in values
        assert "decision_recorded" in values


# ===========================================================================
# open_position
# ===========================================================================

class TestOpenPosition:
    def test_returns_position_record(self):
        pos = _open_btc()
        assert isinstance(pos, PositionRecord)

    def test_position_stored_in_ledger(self):
        _open_btc()
        pos = get_position(TICKER)
        assert pos is not None
        assert pos.ticker == TICKER

    def test_thesis_registry_created(self):
        _open_btc()
        tr = get_thesis_record(THESIS_ID)
        assert tr is not None
        assert tr.thesis_id == THESIS_ID

    def test_original_thesis_immutable(self):
        _open_btc()
        tr = get_thesis_record(THESIS_ID)
        assert "scarcity premium" in tr.original_thesis

    def test_genesis_event_appended(self):
        _open_btc()
        events = get_all_events(ticker=TICKER)
        assert any(e.event_type == EventType.POSITION_OPENED for e in events)

    def test_initial_confidence_stored(self):
        _open_btc(confidence=70)
        pos = get_position(TICKER)
        assert pos.current_confidence == 70

    def test_confidence_timeline_initialized(self):
        _open_btc()
        timeline = get_confidence_timeline(TICKER)
        assert len(timeline) == 1
        assert timeline[0].confidence == 65

    def test_thesis_lifecycle_starts_emerging(self):
        _open_btc()
        pos = get_position(TICKER)
        assert pos.current_lifecycle_state == "Emerging"

    def test_invalidation_conditions_stored(self):
        _open_btc()
        pos = get_position(TICKER)
        assert len(pos.invalidation_conditions) == 2
        assert "200d MA" in pos.invalidation_conditions[0]

    def test_position_is_active_on_open(self):
        _open_btc()
        pos = get_position(TICKER)
        assert pos.is_active is True

    def test_original_thesis_matches_current_at_open(self):
        _open_btc()
        pos = get_position(TICKER)
        assert pos.original_thesis == pos.current_thesis

    def test_peak_exposure_set_on_open(self):
        _open_btc(exposure=18.0)
        pos = get_position(TICKER)
        assert pos.peak_exposure_pct == 18.0

    def test_lifecycle_history_has_opening_entry(self):
        _open_btc()
        tr = get_thesis_record(THESIS_ID)
        assert len(tr.lifecycle_history) == 1
        assert tr.lifecycle_history[0]["to_state"] == "Emerging"

    def test_multiple_positions(self):
        _open_btc()
        open_position(
            ticker="GLD",
            name="Gold ETF",
            bucket="core_structural",
            thesis_id="THESIS-GLD-001",
            original_thesis="Monetary hedge against debasement with 5000 year track record.",
            macro_context="Inflationary environment",
            technical_context="Above 200d MA",
            sentiment_context="Under-owned",
            expected_regime="Stagflation Risk",
            invalidation_conditions=["Real rates rise above 3%"],
            initial_exposure_pct=10.0,
            initial_confidence=60,
        )
        active = get_all_positions(active_only=True)
        assert len(active) == 2


# ===========================================================================
# record_allocation_change
# ===========================================================================

class TestAllocationChange:
    def setup_method(self):
        _open_btc(exposure=15.0)

    def test_trim_reduces_exposure(self):
        record_allocation_change(TICKER, "trim", 15.0, 10.0, "Euphoria detected — trimming.")
        pos = get_position(TICKER)
        assert pos.current_exposure_pct == 10.0

    def test_add_increases_exposure(self):
        record_allocation_change(TICKER, "add", 15.0, 20.0, "Pullback to support — adding.")
        pos = get_position(TICKER)
        assert pos.current_exposure_pct == 20.0

    def test_add_updates_peak_exposure(self):
        record_allocation_change(TICKER, "add", 15.0, 22.0, "Strong confirmation — adding to target.")
        pos = get_position(TICKER)
        assert pos.peak_exposure_pct == 22.0

    def test_exit_marks_position_inactive(self):
        record_allocation_change(TICKER, "exit", 15.0, 0.0, "Thesis invalidated — full exit.")
        pos = get_position(TICKER)
        assert not pos.is_active
        assert pos.current_exposure_pct == 0.0

    def test_exit_records_exit_date(self):
        record_allocation_change(TICKER, "exit", 15.0, 0.0, "Full exit.", date_str="2026-06-01")
        pos = get_position(TICKER)
        assert pos.exited_date == "2026-06-01"

    def test_trim_count_increments(self):
        record_allocation_change(TICKER, "trim", 15.0, 12.0, "Trim 1.")
        record_allocation_change(TICKER, "trim", 12.0, 9.0, "Trim 2.")
        pos = get_position(TICKER)
        assert pos.trim_count == 2

    def test_add_count_increments(self):
        record_allocation_change(TICKER, "add", 15.0, 18.0, "Add on confirmation.")
        pos = get_position(TICKER)
        assert pos.add_count == 1

    def test_dissent_on_change_stored(self):
        record_allocation_change(
            TICKER, "trim", 15.0, 10.0, "Trimming on sentiment.",
            dissent_on_change="Bear case analyst: trimming here is premature — trend intact."
        )
        concerns = what_were_concerns(TICKER)
        assert len(concerns) == 0  # dissent_on_change writes to payload, not dissent_log
        events = what_changed(TICKER)
        trim_events = [e for e in events if e.event_type == EventType.POSITION_TRIMMED]
        assert len(trim_events) == 1
        assert "dissent_argument" in trim_events[0].payload

    def test_event_appended_for_trim(self):
        record_allocation_change(TICKER, "trim", 15.0, 10.0, "Trim.")
        events = get_all_events(ticker=TICKER, event_type=EventType.POSITION_TRIMMED)
        assert len(events) == 1

    def test_event_appended_for_add(self):
        record_allocation_change(TICKER, "add", 15.0, 18.0, "Add.")
        events = get_all_events(ticker=TICKER, event_type=EventType.POSITION_ADDED)
        assert len(events) == 1

    def test_unknown_ticker_raises(self):
        with pytest.raises(KeyError):
            record_allocation_change("XYZ", "trim", 10.0, 8.0, "Trim unknown.")

    def test_invalid_action_raises(self):
        with pytest.raises(AssertionError):
            record_allocation_change(TICKER, "short", 15.0, 10.0, "Invalid.")


# ===========================================================================
# update_confidence
# ===========================================================================

class TestUpdateConfidence:
    def setup_method(self):
        _open_btc(confidence=65)

    def test_confidence_updated_in_position(self):
        update_confidence(TICKER, 75, "ETF inflows accelerating.", regime="Risk-On Expansion")
        pos = get_position(TICKER)
        assert pos.current_confidence == 75

    def test_confidence_snapshot_appended(self):
        update_confidence(TICKER, 75, "ETF inflows accelerating.")
        timeline = get_confidence_timeline(TICKER)
        assert len(timeline) == 2
        assert timeline[-1].confidence == 75

    def test_delta_computed(self):
        update_confidence(TICKER, 75, "Rationale.")
        timeline = get_confidence_timeline(TICKER)
        assert timeline[-1].delta == 10

    def test_negative_delta(self):
        update_confidence(TICKER, 55, "Weakening thesis.")
        timeline = get_confidence_timeline(TICKER)
        assert timeline[-1].delta == -10

    def test_thesis_confidence_history_updated(self):
        update_confidence(TICKER, 75, "ETF inflows.")
        tr = get_thesis_record(THESIS_ID)
        assert len(tr.confidence_history) == 2
        assert tr.confidence_history[-1]["confidence"] == 75

    def test_confidence_event_appended(self):
        update_confidence(TICKER, 75, "Rationale.")
        events = get_all_events(ticker=TICKER, event_type=EventType.CONFIDENCE_UPDATED)
        assert len(events) == 1

    def test_unknown_ticker_raises(self):
        with pytest.raises(KeyError):
            update_confidence("UNKNOWN", 70, "Test.")


# ===========================================================================
# record_thesis_evolution
# ===========================================================================

class TestThesisEvolution:
    def setup_method(self):
        _open_btc()

    def test_strengthening_stored(self):
        record_thesis_evolution(
            TICKER, "strengthening",
            "ETF inflows exceeded projections significantly.",
            "IBIT: $500M single-day inflow"
        )
        improved = what_improved(TICKER)
        assert len(improved) == 1

    def test_weakening_stored(self):
        record_thesis_evolution(
            TICKER, "weakening",
            "Regulatory headwinds increased — SEC opened probe into spot ETFs.",
            "SEC enforcement action filed"
        )
        tr = get_thesis_record(THESIS_ID)
        assert any(e["evolution_type"] == "weakening" for e in tr.evolution_log)

    def test_evolution_count_increments(self):
        record_thesis_evolution(TICKER, "strengthening", "Strong ETF inflows observed.", "IBIT flow data")
        record_thesis_evolution(TICKER, "refinement", "Thesis refined to focus on sovereign demand.", "UAE BTC announcement")
        pos = get_position(TICKER)
        assert pos.evolution_count == 2

    def test_thesis_text_updated_on_refinement(self):
        new_thesis = (
            "Fixed 21M supply + sovereign treasury demand creates "
            "multi-decade scarcity premium, now expanded to nation-state adoption."
        )
        record_thesis_evolution(
            TICKER, "refinement",
            "Thesis refined to include sovereign adoption as primary driver.",
            "El Salvador + UAE sovereign BTC reserves confirmed",
            updated_thesis=new_thesis,
        )
        pos = get_position(TICKER)
        assert pos.current_thesis == new_thesis

    def test_original_thesis_unchanged_after_refinement(self):
        original = get_position(TICKER).original_thesis
        record_thesis_evolution(
            TICKER, "refinement",
            "Thesis refined significantly after sovereign adoption evidence.",
            "Nation-state adoption confirmed",
            updated_thesis="Completely new thesis statement for testing purposes here.",
        )
        tr = get_thesis_record(THESIS_ID)
        assert tr.original_thesis == original

    def test_invalidation_conditions_updated(self):
        new_conditions = [
            "BTC breaks 200d MA on volume > 3x average",
            "ETF outflows sustained > 4 weeks",
            "G7 regulatory ban introduced",
        ]
        record_thesis_evolution(
            TICKER, "invalidation_updated",
            "Invalidation conditions tightened after increased liquidity.",
            "Improved market depth; tightened conditions accordingly",
            updated_invalidation_conditions=new_conditions,
        )
        pos = get_position(TICKER)
        assert len(pos.invalidation_conditions) == 3

    def test_short_description_raises(self):
        with pytest.raises(AssertionError):
            record_thesis_evolution(TICKER, "strengthening", "Too short", "Evidence here")

    def test_short_evidence_raises(self):
        with pytest.raises(AssertionError):
            record_thesis_evolution(TICKER, "strengthening", "Long enough description here.", "short")

    def test_invalid_evolution_type_raises(self):
        with pytest.raises(ValueError):
            record_thesis_evolution(
                TICKER, "wrong_type",
                "This evolution type does not exist in the taxonomy.",
                "Some evidence for testing purposes"
            )

    def test_strengthening_event_type(self):
        record_thesis_evolution(TICKER, "strengthening", "Strong evidence observed in data.", "Data source confirmed")
        events = get_all_events(ticker=TICKER, event_type=EventType.THESIS_STRENGTHENED)
        assert len(events) == 1

    def test_weakening_event_type(self):
        record_thesis_evolution(TICKER, "weakening", "Counter-evidence emerged from data.", "Conflicting data source")
        events = get_all_events(ticker=TICKER, event_type=EventType.THESIS_WEAKENED)
        assert len(events) == 1


# ===========================================================================
# record_dissent / resolve_dissent
# ===========================================================================

class TestDissent:
    def setup_method(self):
        _open_btc()

    def test_dissent_stored_in_thesis(self):
        record_dissent(
            TICKER, "bear_case_analyst",
            "BTC thesis is crowding — hedge funds uniformly long. Reversal risk is asymmetric.",
            "analytical", "high"
        )
        tr = get_thesis_record(THESIS_ID)
        assert len(tr.dissent_log) == 1

    def test_dissent_count_increments(self):
        record_dissent(TICKER, "risk_officer", "Volatility risk remains elevated above historical norms.", severity="medium")
        record_dissent(TICKER, "bear_case_analyst", "Valuation compression risk at current consensus positioning levels.", severity="high")
        pos = get_position(TICKER)
        assert pos.dissent_count == 2

    def test_dissent_appears_in_concerns(self):
        record_dissent(TICKER, "risk_officer", "Tail risk scenario not adequately priced into current sizing.", severity="high")
        concerns = what_were_concerns(TICKER)
        assert len(concerns) == 1
        assert concerns[0]["resolved"] is False

    def test_resolved_dissent_excluded_by_default(self):
        record_dissent(TICKER, "risk_officer", "Short-term technical overextension observed on daily chart.", severity="low")
        concerns = what_were_concerns(TICKER)
        diss_id = concerns[0]["dissent_id"]
        resolve_dissent(TICKER, diss_id, "Risk officer's concern addressed — we trimmed 5%.")
        concerns_after = what_were_concerns(TICKER)
        assert len(concerns_after) == 0

    def test_resolved_dissent_visible_with_flag(self):
        record_dissent(TICKER, "risk_officer", "Short-term technical overextension observed on daily chart.", severity="low")
        diss_id = what_were_concerns(TICKER)[0]["dissent_id"]
        resolve_dissent(TICKER, diss_id, "Concern addressed — position trimmed accordingly.")
        all_concerns = what_were_concerns(TICKER, include_resolved=True)
        assert len(all_concerns) == 1
        assert all_concerns[0]["resolved"] is True

    def test_resolution_note_stored(self):
        record_dissent(TICKER, "risk_officer", "Sizing risk appears elevated relative to thesis confidence level.", severity="medium")
        diss_id = what_were_concerns(TICKER)[0]["dissent_id"]
        resolve_dissent(TICKER, diss_id, "Position trimmed 5% — risk officer's concern acknowledged.")
        all_concerns = what_were_concerns(TICKER, include_resolved=True)
        assert "trimmed" in all_concerns[0]["resolution_note"]

    def test_short_argument_raises(self):
        with pytest.raises(AssertionError):
            record_dissent(TICKER, "risk_officer", "Too short")

    def test_short_resolution_raises(self):
        record_dissent(TICKER, "risk_officer", "Technical overextension risk observed at current price level.", severity="low")
        diss_id = what_were_concerns(TICKER)[0]["dissent_id"]
        with pytest.raises(AssertionError):
            resolve_dissent(TICKER, diss_id, "short")

    def test_invalid_dissent_id_raises(self):
        with pytest.raises(KeyError):
            resolve_dissent(TICKER, "DISS-BOGUS", "Resolution note of adequate length here.")

    def test_dissent_event_appended(self):
        record_dissent(TICKER, "bear_case_analyst", "Crowding risk is elevated at current institutional positioning levels.", severity="high")
        events = get_all_events(ticker=TICKER, event_type=EventType.DISSENT_RECORDED)
        assert len(events) == 1

    def test_resolve_event_appended(self):
        record_dissent(TICKER, "risk_officer", "Tail risk not adequately hedged at current exposure level.", severity="medium")
        diss_id = what_were_concerns(TICKER)[0]["dissent_id"]
        resolve_dissent(TICKER, diss_id, "Added protective puts — tail risk addressed adequately.")
        events = get_all_events(ticker=TICKER, event_type=EventType.DISSENT_RESOLVED)
        assert len(events) == 1


# ===========================================================================
# record_invalidation
# ===========================================================================

class TestInvalidation:
    def setup_method(self):
        _open_btc()

    def test_invalidation_marks_thesis_closed(self):
        record_invalidation(
            TICKER,
            reason="BTC broke 200d MA on 3x average volume for 3 consecutive days.",
            triggered_by="BTC breaks 200d MA on volume",
        )
        tr = get_thesis_record(THESIS_ID)
        assert tr.current_lifecycle_state == "Invalidated"
        assert not tr.is_active

    def test_what_invalidated_returns_event(self):
        record_invalidation(
            TICKER,
            reason="BTC broke 200d MA on 3x average volume for 3 consecutive days.",
            triggered_by="BTC breaks 200d MA on volume",
        )
        inv = what_invalidated(TICKER)
        assert inv is not None
        assert "200d MA" in inv["reason"]

    def test_what_invalidated_returns_none_if_active(self):
        inv = what_invalidated(TICKER)
        assert inv is None

    def test_original_conditions_in_invalidation_response(self):
        record_invalidation(TICKER, "Broke key support on volume.", "200d MA break")
        inv = what_invalidated(TICKER)
        assert "original_invalidation_conditions" in inv
        assert len(inv["original_invalidation_conditions"]) == 2

    def test_invalidation_event_stored(self):
        record_invalidation(TICKER, "Broke key support.", "200d MA break")
        events = get_all_events(ticker=TICKER, event_type=EventType.THESIS_INVALIDATED)
        assert len(events) == 1


# ===========================================================================
# update_lifecycle_state
# ===========================================================================

class TestLifecycleState:
    def setup_method(self):
        _open_btc()

    def test_state_updated(self):
        update_lifecycle_state(TICKER, "Confirming", "Multiple on-chain metrics confirming.")
        pos = get_position(TICKER)
        assert pos.current_lifecycle_state == "Confirming"

    def test_lifecycle_history_recorded(self):
        update_lifecycle_state(TICKER, "Confirming", "Confirmed.")
        update_lifecycle_state(TICKER, "High Conviction", "All metrics aligned.")
        tr = get_thesis_record(THESIS_ID)
        # genesis + 2 transitions
        assert len(tr.lifecycle_history) == 3

    def test_invalid_state_raises(self):
        with pytest.raises(ValueError):
            update_lifecycle_state(TICKER, "Moonshot", "Invalid state.")

    def test_crowded_state(self):
        update_lifecycle_state(TICKER, "Crowded", "Fund manager survey shows 80% long BTC.")
        pos = get_position(TICKER)
        assert pos.current_lifecycle_state == "Crowded"


# ===========================================================================
# Watchlist
# ===========================================================================

class TestWatchlist:
    def test_add_to_watchlist(self):
        add_to_watchlist(
            ticker="NVDA",
            thesis_summary="AI compute scarcity; dominant GPU architecture; H100 backlog persists.",
            entry_triggers=["Pullback to 50d MA with RSI reset to 50"],
            exit_triggers=["AI capex cycle reversal confirmed", "China export ban expanded"],
            patience_note="Wait for the technical reset — do not chase after recent breakout.",
        )
        history = get_watchlist_history("NVDA")
        assert len(history) == 1
        assert history[0].ticker == "NVDA"

    def test_watchlist_event_appended(self):
        add_to_watchlist(
            ticker="NVDA",
            thesis_summary="AI compute scarcity; dominant GPU architecture; H100 backlog persists.",
            entry_triggers=["RSI reset to 50"],
            exit_triggers=["AI capex cycle confirmed reversal"],
            patience_note="Wait for technical setup before acting on this idea.",
        )
        events = get_all_events(ticker="NVDA", event_type=EventType.WATCHLIST_ADDED)
        assert len(events) == 1

    def test_active_watchlist_query(self):
        add_to_watchlist(
            ticker="NVDA",
            thesis_summary="AI compute scarcity; dominant GPU architecture; H100 backlog persists.",
            entry_triggers=["Pullback to 50d MA"],
            exit_triggers=["AI thesis breaks"],
            patience_note="Wait for the technical reset before entering this position.",
        )
        active = get_active_watchlist()
        tickers = [w.ticker for w in active]
        assert "NVDA" in tickers

    def test_resolve_watchlist_triggered(self):
        add_to_watchlist(
            ticker="NVDA",
            thesis_summary="AI compute scarcity; dominant GPU architecture with persistent backlog.",
            entry_triggers=["Pullback to 50d MA"],
            exit_triggers=["AI thesis breaks"],
            patience_note="Wait for technical reset before entering.",
        )
        resolve_watchlist("NVDA", "triggered", "Pulled back to 50d MA — entering position now.")
        history = get_watchlist_history("NVDA")
        assert history[-1].outcome == "triggered"

    def test_resolve_watchlist_expired(self):
        add_to_watchlist(
            ticker="NVDA",
            thesis_summary="AI compute scarcity; dominant GPU architecture with persistent backlog.",
            entry_triggers=["Pullback to 50d MA"],
            exit_triggers=["AI thesis breaks"],
            patience_note="90-day window to enter — then reassess the opportunity.",
        )
        resolve_watchlist("NVDA", "expired", "90 days elapsed without technical setup.")
        active = get_active_watchlist()
        assert all(w.ticker != "NVDA" for w in active)

    def test_missing_entry_triggers_raises(self):
        with pytest.raises(AssertionError):
            add_to_watchlist(
                ticker="NVDA",
                thesis_summary="AI compute scarcity thesis well documented.",
                entry_triggers=[],  # must have at least one
                exit_triggers=["AI thesis breaks"],
                patience_note="Wait for technical setup before entering.",
            )

    def test_short_thesis_summary_raises(self):
        with pytest.raises(AssertionError):
            add_to_watchlist(
                ticker="NVDA",
                thesis_summary="Too short",
                entry_triggers=["50d MA pullback"],
                exit_triggers=["AI thesis breaks"],
                patience_note="Wait for setup.",
            )

    def test_no_unresolved_entry_raises_on_resolve(self):
        with pytest.raises(KeyError):
            resolve_watchlist("NVDA", "triggered", "No watchlist entry was ever created.")


# ===========================================================================
# record_decision
# ===========================================================================

class TestDecisionAudit:
    def test_decision_stored(self):
        record_decision(
            decision_type="full_committee",
            question="Should we increase BTC exposure?",
            regime="Risk-On Expansion",
            final_stance="Hold",
            final_confidence=65,
            allocation_change=False,
            required_actions=["Monitor BTC support at $62k"],
            watchlist_only=["URNM: watch for breakout"],
            rationale="Regime supportive but sentiment not yet euphoric — hold current allocation.",
        )
        audit = get_decision_audit()
        assert len(audit) == 1

    def test_decision_fields_stored(self):
        record_decision(
            decision_type="crypto_change",
            question="Should we add to MSTR position?",
            regime="Risk-On Expansion",
            final_stance="Trim",
            final_confidence=70,
            allocation_change=True,
            required_actions=["Trim MSTR 5% on next open"],
            watchlist_only=[],
            rationale="MSTR premium to NAV has expanded — gradual trim warranted.",
            dissent_present=True,
            groupthink_alert=False,
            challenge_questions=["What is the MSTR premium threshold for full exit?"],
            next_review_trigger="MSTR premium to NAV > 3x or BTC < $50k",
        )
        audit = get_decision_audit()
        dec = audit[0]
        assert dec.final_stance == "Trim"
        assert dec.dissent_present is True
        assert len(dec.challenge_questions) == 1

    def test_decision_event_appended(self):
        record_decision(
            decision_type="full_committee",
            question="Review portfolio positioning",
            regime="Unknown",
            final_stance="Hold",
            final_confidence=50,
            allocation_change=False,
            required_actions=[],
            watchlist_only=[],
            rationale="No significant changes required at this time.",
        )
        events = get_all_events(event_type=EventType.DECISION_RECORDED)
        assert len(events) == 1

    def test_decision_id_unique(self):
        for i in range(3):
            record_decision(
                decision_type="full_committee",
                question=f"Question {i}",
                regime="Risk-On",
                final_stance="Hold",
                final_confidence=60,
                allocation_change=False,
                required_actions=[],
                watchlist_only=[],
                rationale="No action required at this time.",
            )
        audit = get_decision_audit()
        ids = [d.decision_id for d in audit]
        assert len(set(ids)) == 3


# ===========================================================================
# The 7 canonical query functions
# ===========================================================================

class TestWhyDoWeOwn:
    def setup_method(self):
        _open_btc()

    def test_returns_narrative(self):
        narr = why_do_we_own(TICKER)
        assert isinstance(narr, PositionNarrative)

    def test_original_thesis_in_narrative(self):
        narr = why_do_we_own(TICKER)
        assert "scarcity premium" in narr.original_thesis

    def test_is_active_true_for_open_position(self):
        narr = why_do_we_own(TICKER)
        assert narr.is_active is True

    def test_is_active_false_after_exit(self):
        record_allocation_change(TICKER, "exit", 15.0, 0.0, "Full exit.")
        narr = why_do_we_own(TICKER)
        assert narr.is_active is False

    def test_open_dissents_in_narrative(self):
        record_dissent(TICKER, "bear_case_analyst", "Crowding risk is elevated — hedge funds uniformly positioned.", severity="high")
        narr = why_do_we_own(TICKER)
        assert len(narr.open_dissents) == 1

    def test_sizing_guidance_present(self):
        narr = why_do_we_own(TICKER)
        assert len(narr.sizing_guidance) > 10

    def test_unknown_ticker_raises(self):
        with pytest.raises(KeyError):
            why_do_we_own("UNKNOWN")


class TestWhatChanged:
    def setup_method(self):
        _open_btc()

    def test_returns_all_events(self):
        record_thesis_evolution(TICKER, "strengthening", "ETF inflows exceeded initial projections.", "IBIT data source")
        update_confidence(TICKER, 72, "Higher conviction after ETF data.")
        events = what_changed(TICKER)
        assert len(events) >= 3  # open + evolution + confidence

    def test_since_date_filter(self):
        events = what_changed(TICKER, since_date="2030-01-01")
        assert len(events) == 0

    def test_event_type_filter(self):
        update_confidence(TICKER, 72, "Higher conviction.")
        events = what_changed(TICKER, event_types=["confidence_updated"])
        assert all(e.event_type == EventType.CONFIDENCE_UPDATED for e in events)

    def test_sorted_chronologically(self):
        record_thesis_evolution(TICKER, "strengthening", "Strong ETF inflow evidence observed.", "Bloomberg data")
        events = what_changed(TICKER)
        timestamps = [e.timestamp for e in events]
        assert timestamps == sorted(timestamps)


class TestWhatWereConcerns:
    def setup_method(self):
        _open_btc()

    def test_empty_when_no_dissent(self):
        concerns = what_were_concerns(TICKER)
        assert concerns == []

    def test_returns_unresolved_only(self):
        record_dissent(TICKER, "risk_officer", "Tail risk scenario is not adequately hedged currently.", severity="medium")
        record_dissent(TICKER, "bear_case_analyst", "Crowding risk is elevated — fund positioning survey confirms.", severity="high")
        diss_id = what_were_concerns(TICKER)[0]["dissent_id"]
        resolve_dissent(TICKER, diss_id, "Protective puts added — tail risk addressed.")
        concerns = what_were_concerns(TICKER)
        assert len(concerns) == 1

    def test_severity_in_response(self):
        record_dissent(TICKER, "risk_officer", "Tail risk exceeds acceptable threshold at current sizing.", severity="high")
        concerns = what_were_concerns(TICKER)
        assert concerns[0]["severity"] == "high"


class TestWhatInvalidated:
    def setup_method(self):
        _open_btc()

    def test_none_when_active(self):
        assert what_invalidated(TICKER) is None

    def test_invalidation_reason_returned(self):
        record_invalidation(TICKER, "BTC broke 200d MA on 3x average volume.", "200d MA break")
        inv = what_invalidated(TICKER)
        assert "200d MA" in inv["reason"]

    def test_original_conditions_attached(self):
        record_invalidation(TICKER, "BTC broke 200d MA.", "Technical breach")
        inv = what_invalidated(TICKER)
        assert len(inv["original_invalidation_conditions"]) > 0


class TestWhatImproved:
    def setup_method(self):
        _open_btc()

    def test_empty_when_no_evolution(self):
        assert what_improved(TICKER) == []

    def test_returns_only_strengthening(self):
        record_thesis_evolution(TICKER, "strengthening", "ETF inflows exceed initial projections.", "IBIT flow data")
        record_thesis_evolution(TICKER, "weakening", "Regulatory headwind increased significantly.", "SEC probe news")
        improved = what_improved(TICKER)
        assert len(improved) == 1
        assert improved[0]["evolution_type"] == "strengthening"

    def test_evidence_in_response(self):
        record_thesis_evolution(TICKER, "strengthening", "Sovereign adoption accelerated beyond expectations.", "UAE announcement")
        improved = what_improved(TICKER)
        assert "UAE announcement" in improved[0]["evidence"]


class TestOriginalThesis:
    def setup_method(self):
        _open_btc()

    def test_returns_original_thesis(self):
        orig = original_thesis(TICKER)
        assert orig is not None
        assert "scarcity premium" in orig["original_thesis"]

    def test_original_thesis_unchanged_after_evolution(self):
        text_before = original_thesis(TICKER)["original_thesis"]
        record_thesis_evolution(
            TICKER, "refinement",
            "Thesis refined to incorporate sovereign adoption thesis.",
            "UAE sovereign BTC reserve confirmed",
            updated_thesis="Completely revised thesis statement that is much longer.",
        )
        text_after = original_thesis(TICKER)["original_thesis"]
        assert text_before == text_after

    def test_all_inception_fields_present(self):
        orig = original_thesis(TICKER)
        required_fields = [
            "original_thesis",
            "original_macro_context",
            "original_technical_context",
            "original_sentiment_context",
            "original_expected_regime",
            "original_invalidation_conditions",
            "original_confidence",
        ]
        for field in required_fields:
            assert field in orig, f"Missing field: {field}"

    def test_returns_none_for_unknown_ticker(self):
        assert original_thesis("UNKNOWN") is None


class TestDidThesisEvolveCorrectly:
    def setup_method(self):
        _open_btc(confidence=65)

    def test_returns_assessment(self):
        result = did_thesis_evolve_correctly(TICKER)
        assert isinstance(result, ThesisEvolutionAssessment)

    def test_insufficient_data_with_no_events(self):
        result = did_thesis_evolve_correctly(TICKER)
        assert "Insufficient" in result.overall_verdict

    def test_disciplined_with_consistent_evolution(self):
        record_thesis_evolution(TICKER, "strengthening", "ETF inflows accelerate beyond projections.", "IBIT flow data")
        update_confidence(TICKER, 72, "Higher confidence after inflow data.")
        result = did_thesis_evolve_correctly(TICKER)
        assert result.overall_verdict in ("Disciplined", "Caution", "Insufficient data — no evolution events recorded.")

    def test_confidence_trend_rising_after_increases(self):
        update_confidence(TICKER, 72, "Inflows.")
        update_confidence(TICKER, 78, "Sovereign adoption.")
        update_confidence(TICKER, 82, "Halving confirmed.")
        result = did_thesis_evolve_correctly(TICKER)
        assert result.confidence_trend == "Rising"

    def test_confidence_trend_falling(self):
        update_confidence(TICKER, 58, "Regulatory concern.")
        update_confidence(TICKER, 50, "ETF outflows.")
        update_confidence(TICKER, 42, "Technical breakdown.")
        result = did_thesis_evolve_correctly(TICKER)
        assert result.confidence_trend == "Falling"

    def test_strengthening_events_counted(self):
        record_thesis_evolution(TICKER, "strengthening", "Evidence 1 is strong and supports thesis.", "Data source 1")
        record_thesis_evolution(TICKER, "strengthening", "Evidence 2 is strong and further confirms.", "Data source 2")
        result = did_thesis_evolve_correctly(TICKER)
        assert result.strengthening_events == 2

    def test_weakening_events_counted(self):
        record_thesis_evolution(TICKER, "weakening", "Counter-evidence 1 against the thesis.", "Source data A")
        result = did_thesis_evolve_correctly(TICKER)
        assert result.weakening_events == 1

    def test_invalidation_update_flag(self):
        for i in range(3):
            record_thesis_evolution(
                TICKER, "invalidation_updated",
                f"Invalidation condition update number {i} with good rationale.",
                f"Market evidence for update {i}",
                updated_invalidation_conditions=[f"Condition {i}"],
            )
        result = did_thesis_evolve_correctly(TICKER)
        assert any("goal-post" in flag.lower() for flag in result.discipline_flags)

    def test_assessment_narrative_non_empty(self):
        result = did_thesis_evolve_correctly(TICKER)
        assert len(result.assessment_narrative) > 20

    def test_confidence_mismatch_flag(self):
        # Weakening + confidence rose = flag
        record_thesis_evolution(TICKER, "weakening", "Counter-evidence 1 against main thesis.", "Source data A")
        record_thesis_evolution(TICKER, "weakening", "Counter-evidence 2 also against thesis.", "Source data B")
        update_confidence(TICKER, 82, "Raising anyway.")  # delta = +17
        result = did_thesis_evolve_correctly(TICKER)
        assert any("confirmation bias" in flag.lower() for flag in result.discipline_flags)


# ===========================================================================
# portfolio_summary
# ===========================================================================

class TestPortfolioSummary:
    def test_empty_summary(self):
        summary = portfolio_summary()
        assert summary["active_positions"] == 0
        assert summary["total_events"] == 0

    def test_counts_active_position(self):
        _open_btc()
        summary = portfolio_summary()
        assert summary["active_positions"] == 1

    def test_event_count_grows(self):
        _open_btc()
        record_thesis_evolution(TICKER, "strengthening", "Strong evidence supports this thesis.", "Evidence source A")
        summary = portfolio_summary()
        assert summary["total_events"] >= 2

    def test_open_dissents_counted(self):
        _open_btc()
        record_dissent(TICKER, "risk_officer", "Tail risk is not adequately hedged at current exposure.", severity="high")
        summary = portfolio_summary()
        assert summary["open_dissents"] >= 1

    def test_position_in_summary(self):
        _open_btc()
        summary = portfolio_summary()
        tickers = [p["ticker"] for p in summary["positions"]]
        assert TICKER in tickers


# ===========================================================================
# import_from_yaml
# ===========================================================================

class TestImportFromYaml:
    def _make_yaml(self):
        return {
            "core_structural": {
                "positions": [
                    {
                        "ticker": "SPY",
                        "name": "SPDR S&P 500 ETF",
                        "bucket": "core_structural",
                        "portfolio_pct": 20.0,
                        "thesis": "Broad US equity exposure; macro risk-on regime core holding.",
                        "invalidation": "SPY breaks 200d MA with volume confirmation",
                        "thesis_lifecycle": "Confirming",
                    },
                    {
                        "ticker": "GLD",
                        "name": "SPDR Gold Shares",
                        "bucket": "core_structural",
                        "portfolio_pct": 10.0,
                        "thesis": "Monetary scarcity hedge — gold preserves purchasing power against debasement.",
                        "invalidation": "Real rates rise above 3%",
                        "thesis_lifecycle": "Confirming",
                    },
                ]
            }
        }

    def test_import_creates_positions(self):
        imported = import_from_yaml(self._make_yaml())
        assert "SPY" in imported
        assert "GLD" in imported

    def test_positions_accessible_after_import(self):
        import_from_yaml(self._make_yaml())
        spy = get_position("SPY")
        assert spy is not None
        assert spy.ticker == "SPY"

    def test_import_idempotent(self):
        import_from_yaml(self._make_yaml())
        imported2 = import_from_yaml(self._make_yaml())
        assert imported2 == []  # nothing new added

    def test_all_queries_work_after_import(self):
        import_from_yaml(self._make_yaml())
        narr = why_do_we_own("SPY")
        assert narr.ticker == "SPY"
        orig = original_thesis("SPY")
        assert orig is not None
        changes = what_changed("SPY")
        assert len(changes) > 0

    def test_non_position_keys_skipped(self):
        yaml = {
            "metadata": {"as_of_date": "2026-05-13"},
            "core_structural": {
                "positions": [
                    {
                        "ticker": "MSTR",
                        "name": "MicroStrategy",
                        "bucket": "core_structural",
                        "portfolio_pct": 10.0,
                        "thesis": "Leveraged BTC treasury company with scarcity premium builtin.",
                        "invalidation": "BTC structural breakdown",
                    }
                ]
            },
        }
        imported = import_from_yaml(yaml)
        assert "MSTR" in imported
