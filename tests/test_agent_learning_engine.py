"""Tests for agent_learning_engine.py"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from agent_learning_engine import (
    MarketRegime,
    FailureMode,
    AdaptationType,
    RegimeVoteRecord,
    AgentRegimeProfile,
    AgentAdaptationRecord,
    AgentLearningProfile,
    classify_regime_from_context,
    compute_regime_profile,
    compute_adaptation_trajectory,
    build_agent_learning_profile,
    generate_regime_attribution_report,
    MIN_REGIME_OBSERVATIONS,
    TENTATIVE_REGIME_OBSERVATIONS,
)


# ── Helpers ─────────────────────────────────────────────────────────────────

def _vote(
    outcome: str = "Correct",
    regime: str = MarketRegime.LIQUIDITY_EXPANSION.value,
    alpha: float = 0.02,
    confidence: int = 70,
    was_early: bool = False,
    regime_hostile: bool = False,
    found_risks: bool = False,
) -> RegimeVoteRecord:
    return RegimeVoteRecord(
        rec_id="REC-001",
        agent="macro_strategist",
        asset="GLD",
        date="2026-01-01",
        regime=regime,
        vote="Agree",
        confidence=confidence,
        outcome=outcome,
        return_pct=alpha + 0.05,
        benchmark_return_pct=0.05,
        alpha_pct=alpha,
        failure_mode=FailureMode.UNCLEAR.value if outcome == "Correct" else FailureMode.WRONG_THESIS.value,
        was_early=was_early,
        regime_was_hostile=regime_hostile,
        identified_key_risks=found_risks,
    )


def _make_votes(n: int, outcome: str = "Correct", **kwargs) -> list[RegimeVoteRecord]:
    return [_vote(outcome=outcome, **kwargs) for _ in range(n)]


def _adaptation(
    agent: str = "macro_strategist",
    adaptation_type: str = AdaptationType.REGIME_AWARENESS.value,
    outcome_tracked: bool = False,
    outcome_notes: str = "",
) -> AgentAdaptationRecord:
    return AgentAdaptationRecord(
        id="ADAPT-001",
        agent=agent,
        date="2026-01-01",
        adaptation_type=adaptation_type,
        description="Added regime-conditional caveats to signals.",
        triggered_by="Underperformance during liquidity tightening.",
        prior_failure_mode=FailureMode.REGIME_MISMATCH.value,
        outcome_tracked=outcome_tracked,
        outcome_notes=outcome_notes,
    )


# ── Enum completeness ─────────────────────────────────────────────────────────

def test_market_regime_values():
    values = {r.value for r in MarketRegime}
    assert "liquidity_expansion" in values
    assert "panic" in values
    assert "stagflation" in values
    assert "unknown" in values
    assert len(values) == 8


def test_failure_mode_values():
    values = {f.value for f in FailureMode}
    assert "wrong_thesis" in values
    assert "early" in values
    assert "regime_mismatch" in values
    assert len(values) == 7


def test_adaptation_type_values():
    values = {a.value for a in AdaptationType}
    assert "methodology_evolution" in values
    assert "regime_awareness" in values
    assert "confidence_calibration" in values
    assert len(values) == 7


# ── Regime classification ────────────────────────────────────────────────────

def test_classify_panic_vix_selloff():
    result = classify_regime_from_context(spy_return_20d=-0.12, vix_level=40)
    assert result == MarketRegime.PANIC


def test_classify_panic_credit_stress_selloff():
    result = classify_regime_from_context(spy_return_20d=-0.10, credit_spread_bps=700)
    assert result == MarketRegime.PANIC


def test_classify_liquidity_tightening_hiking():
    result = classify_regime_from_context(fed_rate_direction="hiking")
    assert result == MarketRegime.LIQUIDITY_TIGHTENING


def test_classify_liquidity_expansion_cutting():
    result = classify_regime_from_context(fed_rate_direction="cutting")
    assert result == MarketRegime.LIQUIDITY_EXPANSION


def test_classify_bubble_rally_complacency():
    result = classify_regime_from_context(spy_return_20d=0.12, vix_level=12)
    assert result == MarketRegime.BUBBLE


def test_classify_stagflation():
    result = classify_regime_from_context(
        inflation_regime="high", growth_regime="contracting"
    )
    assert result == MarketRegime.STAGFLATION


def test_classify_reflation():
    result = classify_regime_from_context(
        inflation_regime="moderate", growth_regime="expanding"
    )
    assert result == MarketRegime.REFLATION


def test_classify_trendless_no_signals():
    result = classify_regime_from_context()
    assert result == MarketRegime.TRENDLESS


def test_classify_unknown_ambiguous_signals():
    # strong rally + strong selloff simultaneously is impossible; use contradictory fed signals
    # spy up strongly but easing signals absent, hiking absent → should resolve to BUBBLE or UNKNOWN
    result = classify_regime_from_context(spy_return_20d=0.10, vix_level=20, fed_rate_direction=None)
    # No complacency (vix=20 ≥ 15), strong rally present, no easing/hiking → UNKNOWN
    assert result == MarketRegime.UNKNOWN


# ── Regime profile computation ────────────────────────────────────────────────

def test_empty_votes_returns_insufficient():
    profile = compute_regime_profile("macro_strategist", "liquidity_expansion", [])
    assert profile.data_quality == "insufficient"
    assert profile.n_votes == 0


def test_insufficient_data_below_min():
    votes = _make_votes(MIN_REGIME_OBSERVATIONS - 1)
    profile = compute_regime_profile("macro_strategist", "liquidity_expansion", votes)
    assert profile.data_quality == "insufficient"
    assert len(profile.note) > 0


def test_tentative_data_between_thresholds():
    votes = _make_votes(TENTATIVE_REGIME_OBSERVATIONS - 1)
    profile = compute_regime_profile("macro_strategist", "liquidity_expansion", votes)
    assert profile.data_quality == "tentative"
    assert len(profile.note) > 0


def test_conclusive_data_above_threshold():
    votes = _make_votes(TENTATIVE_REGIME_OBSERVATIONS + 1)
    profile = compute_regime_profile("macro_strategist", "liquidity_expansion", votes)
    assert profile.data_quality == "conclusive"
    assert profile.note == ""


def test_hit_rate_all_correct():
    votes = _make_votes(10, outcome="Correct")
    profile = compute_regime_profile("macro_strategist", "liquidity_expansion", votes)
    assert profile.n_correct == 10
    assert profile.hit_rate_pct == 100.0


def test_hit_rate_mixed():
    votes = _make_votes(6, "Correct") + _make_votes(4, "Incorrect")
    profile = compute_regime_profile("macro_strategist", "liquidity_expansion", votes)
    assert profile.n_votes == 10
    assert abs(profile.hit_rate_pct - 60.0) < 0.01


def test_alpha_averaged():
    votes = [_vote(alpha=0.02)] * 5 + [_vote(alpha=-0.01)] * 5
    profile = compute_regime_profile("macro_strategist", "liquidity_expansion", votes)
    assert abs(profile.avg_alpha_pct - 0.005) < 1e-6


def test_early_votes_counted():
    votes = _make_votes(5, was_early=True) + _make_votes(5)
    profile = compute_regime_profile("macro_strategist", "liquidity_expansion", votes)
    assert profile.n_early == 5


def test_risk_discovery_counted():
    votes = _make_votes(5, found_risks=True) + _make_votes(5)
    profile = compute_regime_profile("macro_strategist", "liquidity_expansion", votes)
    assert profile.n_risk_discoveries == 5


def test_confidence_calibration_error():
    # 60% confidence, 100% hit rate → error = 40
    votes = _make_votes(10, outcome="Correct", confidence=60)
    profile = compute_regime_profile("macro_strategist", "liquidity_expansion", votes)
    assert abs(profile.confidence_calibration_error - 40.0) < 0.5


def test_profile_to_dict_has_required_fields():
    votes = _make_votes(5)
    profile = compute_regime_profile("macro_strategist", "liquidity_expansion", votes)
    d = profile.to_dict()
    for field in ("agent", "regime", "n_votes", "hit_rate_pct", "data_quality",
                  "characteristic_strength", "characteristic_weakness"):
        assert field in d


def test_empty_profile_factory():
    p = AgentRegimeProfile.empty("cio", "panic")
    assert p.agent == "cio"
    assert p.regime == "panic"
    assert p.data_quality == "insufficient"
    assert p.n_votes == 0


# ── Adaptation trajectory ─────────────────────────────────────────────────────

def test_trajectory_unknown_with_few_adaptations():
    adaptations = [_adaptation() for _ in range(2)]
    assert compute_adaptation_trajectory(adaptations) == "unknown"


def test_trajectory_unknown_with_no_outcome_tracked():
    adaptations = [_adaptation(outcome_tracked=False) for _ in range(3)]
    assert compute_adaptation_trajectory(adaptations) == "unknown"


def test_trajectory_improving_with_positive_outcome():
    adaptations = [
        _adaptation(),
        _adaptation(),
        _adaptation(outcome_tracked=True, outcome_notes="Showed clear improvement in signals."),
    ]
    assert compute_adaptation_trajectory(adaptations) == "improving"


def test_trajectory_stable_tracked_but_no_improve_note():
    adaptations = [
        _adaptation(),
        _adaptation(),
        _adaptation(outcome_tracked=True, outcome_notes="No significant change."),
    ]
    assert compute_adaptation_trajectory(adaptations) == "stable"


# ── Full learning profile ─────────────────────────────────────────────────────

def test_build_profile_empty_votes():
    profile = build_agent_learning_profile("macro_strategist", [], [])
    assert profile.total_resolved_votes == 0
    assert profile.overall_hit_rate_pct == 0.0
    assert profile.regime_best_fit == "insufficient_data"
    assert profile.regime_worst_fit == "insufficient_data"
    assert profile.adaptation_trajectory == "unknown"


def test_build_profile_calculates_overall_hit_rate():
    votes = (
        _make_votes(6, "Correct", regime=MarketRegime.LIQUIDITY_EXPANSION.value) +
        _make_votes(4, "Incorrect", regime=MarketRegime.LIQUIDITY_EXPANSION.value)
    )
    profile = build_agent_learning_profile("macro_strategist", votes, [])
    assert abs(profile.overall_hit_rate_pct - 60.0) < 0.01


def test_build_profile_groups_by_regime():
    votes = (
        _make_votes(5, regime=MarketRegime.LIQUIDITY_EXPANSION.value) +
        _make_votes(5, regime=MarketRegime.PANIC.value)
    )
    profile = build_agent_learning_profile("macro_strategist", votes, [])
    assert MarketRegime.LIQUIDITY_EXPANSION.value in profile.regime_profiles
    assert MarketRegime.PANIC.value in profile.regime_profiles


def test_build_profile_best_worst_regime_from_conclusive_only():
    good_votes = _make_votes(TENTATIVE_REGIME_OBSERVATIONS + 1, "Correct",
                              regime=MarketRegime.REFLATION.value)
    bad_votes = _make_votes(TENTATIVE_REGIME_OBSERVATIONS + 1, "Incorrect",
                             regime=MarketRegime.PANIC.value)
    profile = build_agent_learning_profile("macro_strategist", good_votes + bad_votes, [])
    assert profile.regime_best_fit == MarketRegime.REFLATION.value
    assert profile.regime_worst_fit == MarketRegime.PANIC.value


def test_build_profile_early_tendency_detected():
    votes = _make_votes(10, outcome="Incorrect", was_early=True)
    profile = build_agent_learning_profile("macro_strategist", votes, [])
    assert profile.is_early_not_wrong_tendency is True


def test_build_profile_no_early_tendency_when_genuinely_wrong():
    votes = _make_votes(10, outcome="Incorrect", was_early=False)
    profile = build_agent_learning_profile("macro_strategist", votes, [])
    assert profile.is_early_not_wrong_tendency is False


def test_build_profile_risk_discovery_detected():
    votes = _make_votes(8, found_risks=True) + _make_votes(2, found_risks=False)
    profile = build_agent_learning_profile("macro_strategist", votes, [])
    assert profile.consistent_risk_discovery is True


def test_build_profile_includes_adaptation_records():
    adaptations = [_adaptation() for _ in range(3)]
    profile = build_agent_learning_profile("macro_strategist", [], adaptations)
    assert len(profile.adaptation_records) == 3


def test_build_profile_to_dict_has_required_keys():
    profile = build_agent_learning_profile("macro_strategist", [], [])
    d = profile.to_dict()
    for key in ("agent", "total_resolved_votes", "regime_profiles",
                "adaptation_records", "overall_hit_rate_pct",
                "regime_best_fit", "regime_worst_fit",
                "is_early_not_wrong_tendency", "consistent_risk_discovery",
                "adaptation_trajectory", "last_updated"):
        assert key in d


# ── Regime attribution report ─────────────────────────────────────────────────

def test_generate_report_empty():
    report = generate_regime_attribution_report({}, {})
    assert report.agents_analyzed == 0
    assert report.regime_leaders == {}


def test_generate_report_with_data():
    votes = _make_votes(TENTATIVE_REGIME_OBSERVATIONS + 2, "Correct",
                         regime=MarketRegime.LIQUIDITY_EXPANSION.value)
    report = generate_regime_attribution_report(
        {"macro_strategist": votes},
        {},
        current_regime=MarketRegime.LIQUIDITY_EXPANSION.value,
    )
    assert report.agents_analyzed == 1
    assert report.current_regime == MarketRegime.LIQUIDITY_EXPANSION.value
    assert MarketRegime.LIQUIDITY_EXPANSION.value in report.regime_leaders


def test_generate_report_data_quality_warning_for_low_n():
    votes = _make_votes(3)
    report = generate_regime_attribution_report({"macro_strategist": votes}, {})
    assert any("macro_strategist" in w for w in report.data_quality_warnings)


def test_generate_report_early_agents_tracked():
    votes = _make_votes(10, outcome="Incorrect", was_early=True)
    report = generate_regime_attribution_report({"macro_strategist": votes}, {})
    assert "macro_strategist" in report.early_not_wrong_agents


def test_generate_report_risk_discoverers_tracked():
    votes = _make_votes(10, found_risks=True)
    report = generate_regime_attribution_report({"macro_strategist": votes}, {})
    assert "macro_strategist" in report.consistent_risk_discoverers


def test_generate_report_conservative_note_present():
    report = generate_regime_attribution_report({}, {})
    assert len(report.conservative_learning_note) > 0
    assert str(TENTATIVE_REGIME_OBSERVATIONS) in report.conservative_learning_note


def test_regime_vote_record_to_dict():
    v = _vote()
    d = v.to_dict()
    assert "rec_id" in d
    assert "regime" in d
    assert "was_early" in d
    assert "identified_key_risks" in d
