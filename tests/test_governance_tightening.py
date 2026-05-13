"""Tests for governance_tightening.py."""

import pytest
from src.governance_tightening import (
    # Sentiment
    SentimentState,
    CONTRARIAN_SIGNAL,
    classify_sentiment_state,
    # Regime persistence
    REGIME_PERSISTENCE_MINIMUMS,
    RegimePersistenceCheck,
    check_regime_persistence,
    # Deallocation
    MAX_TRIM_PER_STEP_PCT,
    MIN_REMAINING_EXPOSURE_PCT,
    GradualDeallocationPolicy,
    DeallocationStep,
    build_gradual_deallocation,
    # Dissent
    GROUPTHINK_CONSENSUS_THRESHOLD,
    MINIMUM_DISSENT_VOICES,
    DissentHealthReport,
    evaluate_dissent_health,
    # Human challenge
    BiasFlag,
    InvestorChallenge,
    HumanChallengeReport,
    generate_human_challenge_report,
    # Meta-agent
    PhilosophyChallenge,
    MetaAgentAudit,
    FINAL_GOVERNING_PRINCIPLE,
    SCARCITY_CHALLENGE_INTERVAL_DAYS,
    AI_NARRATIVE_CHALLENGE_INTERVAL_DAYS,
    CORE_WORLDVIEW_CHALLENGE_INTERVAL_DAYS,
    run_meta_agent_audit,
)


# ===========================================================================
# Enums
# ===========================================================================

class TestEnumCompleteness:
    def test_sentiment_state_count(self):
        assert len(SentimentState) == 6

    def test_sentiment_state_values(self):
        values = {s.value for s in SentimentState}
        assert "panic" in values
        assert "exhaustion" in values
        assert "healthy_skepticism" in values
        assert "disbelief_rally" in values
        assert "euphoric_melt_up" in values
        assert "narrative_saturation" in values

    def test_bias_flag_count(self):
        assert len(BiasFlag) >= 5

    def test_contrarian_signal_panic_is_bullish(self):
        assert CONTRARIAN_SIGNAL[SentimentState.PANIC] > 0

    def test_contrarian_signal_euphoria_is_bearish(self):
        assert CONTRARIAN_SIGNAL[SentimentState.EUPHORIC_MELT_UP] < 0

    def test_contrarian_signal_healthy_skepticism_is_neutral(self):
        assert CONTRARIAN_SIGNAL[SentimentState.HEALTHY_SKEPTICISM] == 0

    def test_all_states_have_contrarian_signal(self):
        for state in SentimentState:
            assert state in CONTRARIAN_SIGNAL

    def test_final_governing_principle_non_empty(self):
        assert len(FINAL_GOVERNING_PRINCIPLE) > 50
        assert "adaptive long-term compounding" in FINAL_GOVERNING_PRINCIPLE
        assert "disciplined evolutionary decision-making" in FINAL_GOVERNING_PRINCIPLE


# ===========================================================================
# Sentiment classifier
# ===========================================================================

class TestClassifySentimentState:
    def test_panic_extreme_fear_fgi(self):
        state, rationale = classify_sentiment_state(fear_greed_index=15)
        assert state == SentimentState.PANIC
        assert "fear" in rationale.lower() or "panic" in rationale.lower() or "contrarian" in rationale.lower()

    def test_panic_high_put_call(self):
        state, _ = classify_sentiment_state(put_call_ratio=1.35)
        assert state == SentimentState.PANIC

    def test_panic_heavy_capitulation(self):
        state, _ = classify_sentiment_state(
            fear_greed_index=18, put_call_ratio=1.0, price_momentum_20d=-0.15, survey_bull_pct=15
        )
        assert state == SentimentState.PANIC

    def test_euphoric_melt_up(self):
        state, rationale = classify_sentiment_state(
            fear_greed_index=90,
            price_momentum_20d=0.20,
            retail_inflow_spike=True,
            media_coverage_intensity="extreme",
        )
        assert state == SentimentState.EUPHORIC_MELT_UP
        assert "trim" in rationale.lower() or "greed" in rationale.lower()

    def test_narrative_saturation(self):
        state, rationale = classify_sentiment_state(
            fear_greed_index=80,
            media_coverage_intensity="extreme",
            analyst_upgrade_wave=True,
            short_interest_decline=True,
        )
        assert state == SentimentState.NARRATIVE_SATURATION
        assert "crowded" in rationale.lower() or "priced in" in rationale.lower()

    def test_exhaustion(self):
        state, rationale = classify_sentiment_state(
            fear_greed_index=30,
            survey_bull_pct=28,
            price_momentum_20d=-0.08,
            put_call_ratio=1.05,
        )
        assert state == SentimentState.EXHAUSTION
        assert "pessimism" in rationale.lower() or "accumulation" in rationale.lower()

    def test_disbelief_rally(self):
        state, rationale = classify_sentiment_state(
            fear_greed_index=45,
            price_momentum_20d=0.12,
            survey_bull_pct=38,
        )
        assert state == SentimentState.DISBELIEF_RALLY
        assert "wall of worry" in rationale.lower() or "skeptical" in rationale.lower()

    def test_healthy_skepticism_default(self):
        state, rationale = classify_sentiment_state()
        assert state == SentimentState.HEALTHY_SKEPTICISM
        assert "balanced" in rationale.lower() or "no contrarian" in rationale.lower()

    def test_healthy_skepticism_moderate_conditions(self):
        state, _ = classify_sentiment_state(
            fear_greed_index=50,
            price_momentum_20d=0.03,
            survey_bull_pct=50,
        )
        assert state == SentimentState.HEALTHY_SKEPTICISM

    def test_returns_tuple_of_state_and_string(self):
        result = classify_sentiment_state()
        assert isinstance(result, tuple)
        assert len(result) == 2
        assert isinstance(result[0], SentimentState)
        assert isinstance(result[1], str)


# ===========================================================================
# Regime persistence
# ===========================================================================

class TestRegimePersistenceMinimums:
    def test_bubble_minimum(self):
        assert REGIME_PERSISTENCE_MINIMUMS["bubble"] >= 365

    def test_ai_narrative_minimum(self):
        assert REGIME_PERSISTENCE_MINIMUMS["ai_narrative"] >= 365

    def test_scarcity_minimum(self):
        assert REGIME_PERSISTENCE_MINIMUMS["scarcity_thesis"] >= 365

    def test_momentum_minimum(self):
        assert REGIME_PERSISTENCE_MINIMUMS["momentum"] >= 60

    def test_general_default_exists(self):
        assert "general" in REGIME_PERSISTENCE_MINIMUMS


class TestCheckRegimePersistence:
    def test_too_early_to_fade_bubble(self):
        check = check_regime_persistence(
            regime_label="bubble",
            regime_start_date="2024-01-01",
            current_date="2024-06-01",
            days_elapsed=150,
            fade_signal_present=True,
            confirmation_signals=["signal_a", "signal_b"],
        )
        assert check.verdict == "too_early_to_fade"

    def test_confirmed_end_with_sufficient_evidence(self):
        check = check_regime_persistence(
            regime_label="momentum",
            regime_start_date="2023-01-01",
            current_date="2024-01-01",
            days_elapsed=365,
            fade_signal_present=True,
            confirmation_signals=["break_below_200dma", "volume_confirmation"],
        )
        assert check.verdict == "confirmed_end"

    def test_monitor_insufficient_confirmation_signals(self):
        check = check_regime_persistence(
            regime_label="momentum",
            regime_start_date="2023-01-01",
            current_date="2024-01-01",
            days_elapsed=365,
            fade_signal_present=True,
            confirmation_signals=["only_one_signal"],
        )
        assert check.verdict == "monitor"

    def test_monitor_no_fade_signal(self):
        check = check_regime_persistence(
            regime_label="general",
            regime_start_date="2023-01-01",
            current_date="2024-01-01",
            days_elapsed=120,
            fade_signal_present=False,
        )
        assert check.verdict == "monitor"

    def test_rationale_is_populated(self):
        check = check_regime_persistence(
            regime_label="bubble",
            regime_start_date="2024-01-01",
            current_date="2024-06-01",
            days_elapsed=100,
            fade_signal_present=True,
        )
        assert len(check.rationale) > 10

    def test_minimum_persistence_days_populated(self):
        check = check_regime_persistence(
            regime_label="bubble",
            regime_start_date="2024-01-01",
            current_date="2024-06-01",
            days_elapsed=100,
            fade_signal_present=False,
        )
        assert check.minimum_persistence_days == REGIME_PERSISTENCE_MINIMUMS["bubble"]

    def test_unknown_regime_uses_general_minimum(self):
        check = check_regime_persistence(
            regime_label="unknown_custom_regime",
            regime_start_date="2024-01-01",
            current_date="2024-06-01",
            days_elapsed=100,
            fade_signal_present=False,
        )
        assert check.minimum_persistence_days == REGIME_PERSISTENCE_MINIMUMS["general"]

    def test_all_gates_pass_only_when_confirmed_end(self):
        check_end = check_regime_persistence(
            regime_label="momentum",
            regime_start_date="2023-01-01",
            current_date="2024-01-01",
            days_elapsed=365,
            fade_signal_present=True,
            confirmation_signals=["a", "b"],
        )
        check_early = check_regime_persistence(
            regime_label="bubble",
            regime_start_date="2024-01-01",
            current_date="2024-06-01",
            days_elapsed=100,
            fade_signal_present=True,
            confirmation_signals=["a", "b"],
        )
        assert check_end.all_gates_pass is True
        assert check_early.all_gates_pass is False


# ===========================================================================
# Gradual deallocation
# ===========================================================================

class TestGradualDeallocation:
    def test_blocked_when_regime_too_early(self):
        check = check_regime_persistence(
            regime_label="bubble",
            regime_start_date="2024-01-01",
            current_date="2024-06-01",
            days_elapsed=100,
            fade_signal_present=True,
            confirmation_signals=["a", "b"],
        )
        policy = build_gradual_deallocation(
            position_id="p1",
            ticker="BTC",
            current_exposure_pct=60.0,
            desired_reduction_pct=40.0,
            sentiment_state=SentimentState.EUPHORIC_MELT_UP,
            regime_persistence_check=check,
        )
        assert policy.blocked is True
        assert "regime persistence" in policy.blocked_reason.lower()
        assert policy.steps == []
        assert policy.final_exposure_pct == 60.0

    def test_generates_steps_when_not_blocked(self):
        policy = build_gradual_deallocation(
            position_id="p1",
            ticker="BTC",
            current_exposure_pct=60.0,
            desired_reduction_pct=30.0,
            sentiment_state=SentimentState.EUPHORIC_MELT_UP,
            n_steps=3,
        )
        assert not policy.blocked
        assert len(policy.steps) > 0

    def test_never_exceeds_max_trim_per_step(self):
        policy = build_gradual_deallocation(
            position_id="p1",
            ticker="BTC",
            current_exposure_pct=80.0,
            desired_reduction_pct=60.0,
            sentiment_state=SentimentState.EUPHORIC_MELT_UP,
            n_steps=3,
        )
        for step in policy.steps:
            max_allowed = step.current_exposure_pct * (MAX_TRIM_PER_STEP_PCT / 100)
            assert step.trim_amount_pct <= max_allowed + 0.001  # float tolerance

    def test_never_goes_below_minimum_exposure(self):
        policy = build_gradual_deallocation(
            position_id="p1",
            ticker="BTC",
            current_exposure_pct=50.0,
            desired_reduction_pct=45.0,   # wants 5% remaining — but floor is MIN_REMAINING_EXPOSURE_PCT
            sentiment_state=SentimentState.EUPHORIC_MELT_UP,
            n_steps=5,
        )
        assert policy.final_exposure_pct >= MIN_REMAINING_EXPOSURE_PCT

    def test_steps_are_sequential(self):
        policy = build_gradual_deallocation(
            position_id="p2",
            ticker="ETH",
            current_exposure_pct=60.0,
            desired_reduction_pct=25.0,
            sentiment_state=SentimentState.NARRATIVE_SATURATION,
            n_steps=3,
        )
        for i, step in enumerate(policy.steps):
            assert step.step_number == i + 1

    def test_initial_and_final_exposure_populated(self):
        policy = build_gradual_deallocation(
            position_id="p3",
            ticker="NVDA",
            current_exposure_pct=70.0,
            desired_reduction_pct=20.0,
            sentiment_state=SentimentState.EUPHORIC_MELT_UP,
        )
        assert policy.initial_exposure_pct == 70.0
        assert policy.final_exposure_pct < 70.0

    def test_target_exposure_respects_floor(self):
        policy = build_gradual_deallocation(
            position_id="p4",
            ticker="SOL",
            current_exposure_pct=30.0,
            desired_reduction_pct=25.0,  # wants 5% — floor should kick in
            sentiment_state=SentimentState.EUPHORIC_MELT_UP,
        )
        assert policy.target_exposure_pct >= MIN_REMAINING_EXPOSURE_PCT

    def test_no_regime_check_allowed(self):
        policy = build_gradual_deallocation(
            position_id="p5",
            ticker="BNB",
            current_exposure_pct=40.0,
            desired_reduction_pct=15.0,
            sentiment_state=SentimentState.NARRATIVE_SATURATION,
            regime_persistence_check=None,
        )
        assert not policy.blocked


# ===========================================================================
# Dissent health
# ===========================================================================

class TestDissentHealth:
    def _make_votes(self, n_bull: int, n_bear: int, n_neutral: int = 0) -> list[dict]:
        votes = []
        for i in range(n_bull):
            votes.append({"agent": f"bull_{i}", "vote": "buy", "confidence": 70})
        for i in range(n_bear):
            votes.append({"agent": f"bear_{i}", "vote": "sell", "confidence": 70})
        for i in range(n_neutral):
            votes.append({"agent": f"neutral_{i}", "vote": "hold", "confidence": 50})
        return votes

    def test_empty_votes_no_alert(self):
        report = evaluate_dissent_health("s1", [])
        assert report.total_votes == 0
        assert not report.groupthink_alert

    def test_groupthink_alert_when_consensus_too_high(self):
        votes = self._make_votes(n_bull=9, n_bear=0, n_neutral=1)
        report = evaluate_dissent_health("s2", votes)
        assert report.groupthink_alert is True
        assert len(report.groupthink_reason) > 10

    def test_no_groupthink_with_sufficient_dissent(self):
        votes = self._make_votes(n_bull=6, n_bear=2, n_neutral=2)
        report = evaluate_dissent_health("s3", votes)
        assert not report.groupthink_alert

    def test_dissent_suppressed_when_too_few_dissenters(self):
        votes = self._make_votes(n_bull=8, n_bear=1, n_neutral=0)
        report = evaluate_dissent_health("s4", votes)
        assert report.dissent_suppressed is True

    def test_dissent_not_suppressed_with_enough_dissenters(self):
        votes = self._make_votes(n_bull=6, n_bear=2, n_neutral=2)
        report = evaluate_dissent_health("s5", votes)
        assert not report.dissent_suppressed

    def test_dissenting_agents_listed(self):
        votes = self._make_votes(n_bull=7, n_bear=3)
        report = evaluate_dissent_health("s6", votes)
        assert len(report.dissenting_agents) == 3

    def test_majority_position_identified(self):
        votes = self._make_votes(n_bull=8, n_bear=2)
        report = evaluate_dissent_health("s7", votes)
        assert report.majority_position == "buy"
        assert report.majority_pct == pytest.approx(0.8)

    def test_recommendations_populated(self):
        votes = self._make_votes(n_bull=9, n_bear=1)
        report = evaluate_dissent_health("s8", votes)
        assert len(report.recommendations) > 0

    def test_healthy_dissent_produces_adequate_message(self):
        votes = self._make_votes(n_bull=5, n_bear=3, n_neutral=2)
        report = evaluate_dissent_health("s9", votes)
        assert any("adequate" in r.lower() for r in report.recommendations)

    def test_groupthink_threshold_boundary(self):
        # exactly at threshold — 85% of 20 = 17 bull, 3 bear
        votes = self._make_votes(n_bull=17, n_bear=3)
        report = evaluate_dissent_health("s10", votes)
        # 17/20 = 0.85, which is NOT > 0.85 (strictly greater than)
        assert not report.groupthink_alert

        # 18/20 = 0.90, which IS > 0.85
        votes2 = self._make_votes(n_bull=18, n_bear=2)
        report2 = evaluate_dissent_health("s11", votes2)
        assert report2.groupthink_alert


# ===========================================================================
# Human challenge report
# ===========================================================================

class TestHumanChallengeReport:
    def _base_history(self):
        return [
            {
                "ticker": "BTC",
                "held_days": 90,
                "return_pct": -0.15,
                "thesis_state": "Breakdown Risk",
                "notes": "Held through support break",
            }
        ]

    def _base_votes(self):
        return [
            {"ticker": "ETH", "agent": f"agent_{i}", "vote": "buy", "confidence": 75}
            for i in range(5)
        ]

    def _base_theses(self):
        return [
            {
                "ticker": "BTC",
                "lifecycle_state": "High Conviction",
                "confidence": 80,
                "invalidation_conditions": ["below 30k"],
            }
        ]

    def test_emotional_attachment_detected(self):
        report = generate_human_challenge_report(
            date="2024-06-01",
            position_history=self._base_history(),
            recent_votes=[],
            current_theses=[],
        )
        assert len(report.emotional_attachment_warnings) > 0
        assert any(c.bias_flag == BiasFlag.EMOTIONAL_ATTACHMENT for c in report.challenges)

    def test_emotional_attachment_high_severity_when_held_very_long(self):
        history = [{"ticker": "BTC", "held_days": 90, "return_pct": -0.2, "thesis_state": "Breakdown Risk"}]
        report = generate_human_challenge_report("2024-06-01", history, [], [])
        high = [c for c in report.challenges if c.severity == "high"]
        assert len(high) > 0

    def test_emotional_attachment_medium_severity_when_held_less(self):
        history = [{"ticker": "ETH", "held_days": 35, "return_pct": -0.1, "thesis_state": "Breakdown Risk"}]
        report = generate_human_challenge_report("2024-06-01", history, [], [])
        medium = [c for c in report.challenges if c.severity == "medium"]
        assert len(medium) > 0

    def test_no_emotional_attachment_for_active_thesis(self):
        history = [{"ticker": "SOL", "held_days": 10, "return_pct": 0.05, "thesis_state": "Confirming"}]
        report = generate_human_challenge_report("2024-06-01", history, [], [])
        assert len(report.emotional_attachment_warnings) == 0

    def test_confirmation_bias_detected(self):
        votes = [
            {"ticker": "NVDA", "agent": f"a{i}", "vote": "buy", "confidence": 80}
            for i in range(5)
        ]
        report = generate_human_challenge_report("2024-06-01", [], votes, [])
        assert len(report.confirmation_bias_alerts) > 0
        assert any(c.bias_flag == BiasFlag.CONFIRMATION_BIAS for c in report.challenges)

    def test_no_confirmation_bias_when_mixed_votes(self):
        votes = [
            {"ticker": "NVDA", "agent": "bull", "vote": "buy", "confidence": 80},
            {"ticker": "NVDA", "agent": "bear", "vote": "sell", "confidence": 70},
            {"ticker": "NVDA", "agent": "neutral", "vote": "hold", "confidence": 50},
        ]
        report = generate_human_challenge_report("2024-06-01", [], votes, [])
        assert len(report.confirmation_bias_alerts) == 0

    def test_worldview_divergence_detected(self):
        votes = [
            {"ticker": "BTC", "agent": f"a{i}", "vote": "sell", "confidence": 30}
            for i in range(4)
        ]
        theses = [{"ticker": "BTC", "lifecycle_state": "High Conviction", "confidence": 85, "invalidation_conditions": []}]
        report = generate_human_challenge_report("2024-06-01", [], votes, theses)
        assert len(report.worldview_divergences) > 0
        assert any(c.bias_flag == BiasFlag.WORLDVIEW_DIVERGENCE for c in report.challenges)

    def test_no_worldview_divergence_when_aligned(self):
        votes = [
            {"ticker": "BTC", "agent": f"a{i}", "vote": "buy", "confidence": 80}
            for i in range(4)
        ]
        theses = [{"ticker": "BTC", "lifecycle_state": "High Conviction", "confidence": 78, "invalidation_conditions": []}]
        report = generate_human_challenge_report("2024-06-01", [], votes, theses)
        assert len(report.worldview_divergences) == 0

    def test_no_challenges_produces_clean_summary(self):
        report = generate_human_challenge_report("2024-06-01", [], [], [])
        assert "no significant" in report.summary.lower()

    def test_challenges_produce_meaningful_summary(self):
        report = generate_human_challenge_report(
            "2024-06-01",
            self._base_history(),
            self._base_votes() * 2,  # enough for bias detection
            self._base_theses(),
        )
        assert len(report.summary) > 20

    def test_high_severity_count_tracked(self):
        history = [{"ticker": "BTC", "held_days": 90, "return_pct": -0.2, "thesis_state": "Breakdown Risk"}]
        report = generate_human_challenge_report("2024-06-01", history, [], [])
        assert report.high_severity_count >= 1

    def test_challenge_has_question(self):
        history = [{"ticker": "BTC", "held_days": 90, "return_pct": -0.2, "thesis_state": "Breakdown Risk"}]
        report = generate_human_challenge_report("2024-06-01", history, [], [])
        for c in report.challenges:
            assert "?" in c.challenge_question


# ===========================================================================
# Meta-Agent audit
# ===========================================================================

class TestMetaAgentAudit:
    def _run_clean_audit(self, **overrides):
        defaults = dict(
            date="2024-06-01",
            trigger="scheduled_monthly",
            days_since_scarcity_challenged=20,
            days_since_worldview_challenged=30,
            days_since_ai_narrative_challenged=30,
            scarcity_thesis_unchanged_pct=0.50,
            agent_count=15,
            active_alternative_portfolios=3,
            recent_pip_count=2,
            org_hit_rate=0.60,
            dissent_health_scores=[0.70, 0.65, 0.80],
        )
        defaults.update(overrides)
        return run_meta_agent_audit(**defaults)

    def test_audit_id_is_set(self):
        audit = self._run_clean_audit()
        assert audit.audit_id.startswith("META-")

    def test_final_governing_principle_present(self):
        audit = self._run_clean_audit()
        assert "adaptive long-term compounding" in audit.final_governing_principle

    def test_no_challenges_when_all_healthy(self):
        audit = self._run_clean_audit()
        assert audit.total_challenges == 0
        assert not audit.ideology_lock_detected

    def test_scarcity_unchallenged_too_long_triggers_challenge(self):
        audit = self._run_clean_audit(
            days_since_scarcity_challenged=SCARCITY_CHALLENGE_INTERVAL_DAYS + 5
        )
        assert len(audit.worldview_challenges) >= 1
        assert any("scarcity" in c.challenge.lower() for c in audit.worldview_challenges)

    def test_scarcity_high_acceptance_rate_triggers_challenge(self):
        audit = self._run_clean_audit(scarcity_thesis_unchanged_pct=0.90)
        wv = [c for c in audit.worldview_challenges if "80%" in c.challenge or "90%" in c.challenge or "acceptance" in c.challenge.lower() or "without question" in c.challenge.lower()]
        assert len(wv) >= 1 or len(audit.worldview_challenges) >= 1

    def test_ideology_lock_detected_when_two_signals(self):
        audit = self._run_clean_audit(
            days_since_scarcity_challenged=SCARCITY_CHALLENGE_INTERVAL_DAYS + 10,
            scarcity_thesis_unchanged_pct=0.85,
        )
        assert audit.ideology_lock_detected is True
        assert len(audit.ideology_lock_evidence) >= 2

    def test_ai_narrative_stale_triggers_challenge(self):
        audit = self._run_clean_audit(
            days_since_ai_narrative_challenged=AI_NARRATIVE_CHALLENGE_INTERVAL_DAYS + 5
        )
        assert any("ai" in c.challenge.lower() or "narrative" in c.challenge.lower()
                   for c in audit.worldview_challenges)

    def test_worldview_stale_triggers_challenge(self):
        audit = self._run_clean_audit(
            days_since_worldview_challenged=CORE_WORLDVIEW_CHALLENGE_INTERVAL_DAYS + 5
        )
        assert len(audit.worldview_challenges) >= 1

    def test_high_agent_count_triggers_org_challenge(self):
        audit = self._run_clean_audit(agent_count=19)
        assert len(audit.org_challenges) >= 1
        assert any(str(19) in c.challenge for c in audit.org_challenges)

    def test_too_many_alternatives_triggers_org_challenge(self):
        audit = self._run_clean_audit(active_alternative_portfolios=6)
        assert any("alternative" in c.challenge.lower() for c in audit.org_challenges)

    def test_low_hit_rate_triggers_assumption_challenge(self):
        audit = self._run_clean_audit(org_hit_rate=0.42)
        assert len(audit.assumption_challenges) >= 1

    def test_critical_severity_at_very_low_hit_rate(self):
        audit = self._run_clean_audit(org_hit_rate=0.35)
        assert any(c.severity == "critical" for c in audit.assumption_challenges)

    def test_zero_pips_triggers_rigidity_flag(self):
        audit = self._run_clean_audit(recent_pip_count=0)
        assert len(audit.rigidity_flags) >= 1
        assert any("no process improvement" in c.challenge.lower() or "calcifying" in c.challenge.lower()
                   for c in audit.rigidity_flags)

    def test_poor_dissent_health_triggers_rigidity_flag(self):
        audit = self._run_clean_audit(dissent_health_scores=[0.30, 0.25, 0.35])
        assert any("dissent" in c.challenge.lower() for c in audit.rigidity_flags)

    def test_meta_confidence_score_is_reasonable(self):
        audit = self._run_clean_audit()
        assert 0 <= audit.meta_confidence_score <= 100

    def test_meta_confidence_decreases_with_problems(self):
        clean = self._run_clean_audit()
        troubled = self._run_clean_audit(
            days_since_scarcity_challenged=SCARCITY_CHALLENGE_INTERVAL_DAYS + 30,
            days_since_worldview_challenged=CORE_WORLDVIEW_CHALLENGE_INTERVAL_DAYS + 30,
            recent_pip_count=0,
        )
        assert troubled.meta_confidence_score < clean.meta_confidence_score

    def test_meta_confidence_override(self):
        audit = self._run_clean_audit(meta_confidence_override=42)
        assert audit.meta_confidence_score == 42

    def test_total_challenges_property(self):
        audit = self._run_clean_audit(
            days_since_scarcity_challenged=SCARCITY_CHALLENGE_INTERVAL_DAYS + 10,
            recent_pip_count=0,
        )
        total = (
            len(audit.org_challenges)
            + len(audit.worldview_challenges)
            + len(audit.assumption_challenges)
            + len(audit.rigidity_flags)
        )
        assert audit.total_challenges == total

    def test_critical_count_property(self):
        audit = self._run_clean_audit(org_hit_rate=0.35)
        assert audit.critical_count >= 1

    def test_summary_non_empty(self):
        audit = self._run_clean_audit()
        assert len(audit.summary) > 10

    def test_summary_mentions_ideology_lock_when_present(self):
        audit = self._run_clean_audit(
            days_since_scarcity_challenged=SCARCITY_CHALLENGE_INTERVAL_DAYS + 10,
            scarcity_thesis_unchanged_pct=0.85,
        )
        if audit.ideology_lock_detected:
            assert "ideology lock" in audit.summary.lower()

    def test_trigger_stored(self):
        audit = self._run_clean_audit(trigger="manual")
        assert audit.trigger == "manual"
