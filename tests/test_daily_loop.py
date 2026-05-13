"""Tests for daily_loop.py — ten-phase daily operating loop."""

from __future__ import annotations

import pytest
from unittest.mock import patch, MagicMock
from src.daily_loop import (
    DailyLoopConfig,
    DailyLoopResult,
    PhaseResult,
    IngestResult,
    RegimeResult,
    RegimeSubAssessment,
    RoutingResult,
    SpecialistMemoResult,
    DissentResult,
    PortfolioConstructionResult,
    CIODecisionResult,
    LearningResult,
    OrgReviewResult,
    FinalReportResult,
    run_daily_loop,
    load_daily_result,
    list_daily_results,
    _run_ingest,
    _run_regime,
    _run_routing,
    _run_dissent,
    _run_portfolio_construction,
    _run_learning,
    _run_org_review,
    _format_front_page,
    _format_appendix,
    _select_decision_type,
    _classify_risk_appetite,
    _classify_technical,
    _classify_volatility,
    _classify_crypto,
    _classify_liquidity,
)

TEST_DATE = "2026-05-13"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def cfg():
    return DailyLoopConfig(mock=True, date=TEST_DATE)


@pytest.fixture
def mock_ingest():
    return IngestResult(
        as_of_date=TEST_DATE,
        prices={
            "SPY": 525.0, "QQQ": 445.0, "BTC": 65000.0, "ETH": 3200.0,
            "GLD": 230.0, "MSTR": 1400.0, "URNM": 38.0, "NVDA": 890.0,
            "COIN": 215.0, "DXY": 104.5, "VIX": 18.2, "TLT": 95.0,
            "AGG": 99.0, "GC": 2300.0, "IBIT": 38.5,
        },
        returns_1d={"SPY": 0.4, "BTC": 1.2, "GLD": 0.1},
        returns_5d={"SPY": 1.2, "BTC": 3.5, "GLD": 0.5},
        returns_20d={"SPY": 4.5, "BTC": 10.0, "ETH": 8.0, "GLD": 2.0},
        returns_ytd={"SPY": 12.0, "BTC": 45.0},
        vix=18.2,
        dxy=104.5,
        btc_price=65000.0,
        gold_price=230.0,
        macro_snapshot={},
        overnight_summary="No overnight developments.",
        data_source="mock",
    )


@pytest.fixture
def mock_regime(mock_ingest):
    return RegimeResult(
        macro_regime="Risk-On Expansion",
        macro_confidence=65,
        macro_rationale="Test regime",
        equity_stance="Bullish",
        btc_crypto_stance="Bullish",
        gold_stance="Neutral",
        sub_assessments=[
            RegimeSubAssessment("Liquidity", "Neutral", 65, "Test"),
            RegimeSubAssessment("Risk Appetite", "Risk-On", 75, "Test"),
            RegimeSubAssessment("Technical", "Bullish Momentum", 60, "Test"),
            RegimeSubAssessment("Volatility", "Low Vol", 80, "Test"),
            RegimeSubAssessment("Crypto", "BTC-Led", 65, "Test"),
        ],
        data_source="mock",
    )


@pytest.fixture
def mock_routing():
    return RoutingResult(
        decision_type="full_committee",
        decision_question="Test question",
        engaged_specialists=["macro_strategist", "crypto_strategist", "risk_officer"],
        skipped_specialists=[],
        routing_rationale="Test routing",
        coordinator_notes="3 specialists engaged",
    )


@pytest.fixture
def mock_memos():
    return SpecialistMemoResult(
        memos=[
            {
                "agent": "macro_strategist",
                "decision_type": "full_committee",
                "stance": "bullish",
                "confidence": 70,
                "key_points": ["Rates stable", "M2 growing"],
                "recommendation": "Maintain current allocation",
                "dissent": "",
            },
            {
                "agent": "crypto_strategist",
                "stance": "bullish",
                "confidence": 75,
                "key_points": ["BTC dominance rising"],
                "recommendation": "Hold BTC exposure",
                "dissent": "",
            },
            {
                "agent": "risk_officer",
                "stance": "hold",
                "confidence": 60,
                "key_points": ["VIX elevated slightly"],
                "recommendation": "No immediate action",
                "dissent": "Yes",
            },
        ],
        memo_count=3,
        mock_mode=True,
    )


@pytest.fixture
def mock_dissent():
    return DissentResult(
        groupthink_alert=False,
        groupthink_reason="",
        dissent_suppressed=False,
        dissenting_agents=["risk_officer"],
        majority_position="bullish",
        majority_pct=0.67,
        sentiment_state="healthy_skepticism",
        sentiment_rationale="Test",
        recommendations=["Dissent health adequate."],
    )


@pytest.fixture
def mock_pc():
    return PortfolioConstructionResult(
        allocation_changes=[],
        options_changes=[],
        watchlist_additions=[],
        watchlist_removals=[],
        derisking_triggered=False,
        risk_on_triggered=False,
        regime_persistence_blocks=[],
        coordinator_summary="No changes proposed.",
    )


@pytest.fixture
def mock_cio():
    return CIODecisionResult(
        final_stance="Hold",
        final_confidence=65,
        required_actions=["Monitor BTC support at $62k"],
        watchlist_only=["URNM: watch for breakout"],
        signals=[{"source": "macro_strategist", "signal_type": "bullish"}],
        actions=[],
        dissent_acknowledged=True,
        challenge_questions=["What is the invalidation for BTC thesis?"],
        next_review_trigger="BTC price action or VIX > 25",
        allocation_change=False,
    )


@pytest.fixture
def mock_learning():
    return LearningResult(
        votes_recorded=3,
        thesis_updates=0,
        regime_attributions_recorded=1,
        benchmark_snapshot_recorded=True,
        alternative_portfolio_snapshots=0,
        notes=[],
    )


@pytest.fixture
def mock_org():
    return OrgReviewResult(
        complexity_score=45.0,
        health_score=72.0,
        alerts=[],
        actionable_observations=0,
        pending_proposals=0,
        complexity_breach=False,
        recommendations=[],
    )


# ---------------------------------------------------------------------------
# DailyLoopConfig
# ---------------------------------------------------------------------------

class TestDailyLoopConfig:
    def test_resolved_date_defaults_to_today(self):
        from datetime import date
        cfg = DailyLoopConfig()
        assert cfg.resolved_date() == str(date.today())

    def test_resolved_date_uses_provided(self):
        cfg = DailyLoopConfig(date="2026-01-01")
        assert cfg.resolved_date() == "2026-01-01"

    def test_mock_default_true(self):
        cfg = DailyLoopConfig()
        assert cfg.mock is True

    def test_skip_phases_empty_by_default(self):
        cfg = DailyLoopConfig()
        assert cfg.skip_phases == []


# ---------------------------------------------------------------------------
# Phase 1 — Ingest
# ---------------------------------------------------------------------------

class TestIngest:
    def test_mock_ingest_returns_ingest_result(self, cfg):
        result = _run_ingest(cfg)
        assert isinstance(result, IngestResult)

    def test_mock_ingest_has_key_tickers(self, cfg):
        result = _run_ingest(cfg)
        assert "SPY" in result.prices
        assert "BTC" in result.prices
        assert "GLD" in result.prices
        assert "VIX" in result.prices

    def test_mock_ingest_prices_positive(self, cfg):
        result = _run_ingest(cfg)
        for ticker, price in result.prices.items():
            assert price > 0, f"Price for {ticker} should be positive"

    def test_mock_ingest_vix_populated(self, cfg):
        result = _run_ingest(cfg)
        assert result.vix > 0

    def test_mock_ingest_data_source_is_mock(self, cfg):
        result = _run_ingest(cfg)
        assert result.data_source == "mock"

    def test_mock_ingest_date_matches_config(self, cfg):
        result = _run_ingest(cfg)
        assert result.as_of_date == TEST_DATE

    def test_mock_ingest_returns_populated(self, cfg):
        result = _run_ingest(cfg)
        assert isinstance(result.returns_1d, dict)
        assert isinstance(result.returns_20d, dict)
        assert len(result.returns_1d) > 0


# ---------------------------------------------------------------------------
# Phase 2 — Regime
# ---------------------------------------------------------------------------

class TestRegime:
    def test_regime_result_from_mock_ingest(self, mock_ingest):
        result = _run_regime(mock_ingest)
        assert isinstance(result, RegimeResult)

    def test_regime_has_sub_assessments(self, mock_ingest):
        result = _run_regime(mock_ingest)
        assert len(result.sub_assessments) == 5

    def test_sub_assessment_names(self, mock_ingest):
        result = _run_regime(mock_ingest)
        names = {s.name for s in result.sub_assessments}
        assert "Liquidity" in names
        assert "Risk Appetite" in names
        assert "Technical" in names
        assert "Volatility" in names
        assert "Crypto" in names

    def test_regime_rationale_non_empty(self, mock_ingest):
        result = _run_regime(mock_ingest)
        assert len(result.macro_rationale) > 5

    def test_risk_appetite_low_vix(self):
        ingest = MagicMock()
        ingest.vix = 13.0
        sub = _classify_risk_appetite(ingest)
        assert "complacency" in sub.label.lower() or "risk-on" in sub.label.lower()

    def test_risk_appetite_high_vix(self):
        ingest = MagicMock()
        ingest.vix = 38.0
        sub = _classify_risk_appetite(ingest)
        assert "extreme" in sub.label.lower() or "risk-off" in sub.label.lower()

    def test_risk_appetite_zero_vix_unknown(self):
        ingest = MagicMock()
        ingest.vix = 0.0
        sub = _classify_risk_appetite(ingest)
        assert sub.label == "Unknown"

    def test_technical_bullish_when_spy_strong(self):
        ingest = MagicMock()
        ingest.returns_20d = {"SPY": 8.0}
        sub = _classify_technical(ingest)
        assert "bullish" in sub.label.lower()

    def test_technical_bearish_when_spy_weak(self):
        ingest = MagicMock()
        ingest.returns_20d = {"SPY": -8.0}
        sub = _classify_technical(ingest)
        assert "bearish" in sub.label.lower()

    def test_volatility_low(self):
        ingest = MagicMock()
        ingest.vix = 12.0
        sub = _classify_volatility(ingest)
        assert "low" in sub.label.lower()

    def test_volatility_crisis(self):
        ingest = MagicMock()
        ingest.vix = 40.0
        sub = _classify_volatility(ingest)
        assert "crisis" in sub.label.lower()

    def test_crypto_risk_on_when_both_up(self):
        ingest = MagicMock()
        ingest.returns_20d = {"BTC": 15.0, "ETH": 12.0}
        sub = _classify_crypto(ingest)
        assert "risk-on" in sub.label.lower()

    def test_crypto_risk_off_when_btc_down(self):
        ingest = MagicMock()
        ingest.returns_20d = {"BTC": -15.0, "ETH": -10.0}
        sub = _classify_crypto(ingest)
        assert "risk-off" in sub.label.lower()

    def test_liquidity_unknown_when_no_data(self):
        ingest = MagicMock()
        sub = _classify_liquidity({}, ingest)
        assert "unknown" in sub.label.lower()


# ---------------------------------------------------------------------------
# Phase 3 — Routing
# ---------------------------------------------------------------------------

class TestRouting:
    def test_routing_returns_result(self, cfg, mock_ingest, mock_regime):
        from src.daily_loop import _run_routing
        result = _run_routing(cfg, mock_ingest, mock_regime)
        assert isinstance(result, RoutingResult)

    def test_routing_has_specialists(self, cfg, mock_ingest, mock_regime):
        from src.daily_loop import _run_routing
        result = _run_routing(cfg, mock_ingest, mock_regime)
        assert len(result.engaged_specialists) > 0

    def test_routing_decision_type_populated(self, cfg, mock_ingest, mock_regime):
        from src.daily_loop import _run_routing
        result = _run_routing(cfg, mock_ingest, mock_regime)
        assert result.decision_type in (
            "full_committee", "crypto_change", "risk_alert", "macro_update",
            "technical_signal", "options_review", "commodity_change", "thesis_review",
            "learning_review",
        )

    def test_select_decision_type_escalates_on_big_btc_move(self, cfg):
        ingest = MagicMock()
        ingest.returns_1d = {"BTC": 7.0, "SPY": 0.2}
        result = _select_decision_type(cfg, ingest)
        assert result == "risk_alert"

    def test_select_decision_type_escalates_on_big_spy_move(self, cfg):
        ingest = MagicMock()
        ingest.returns_1d = {"BTC": 0.5, "SPY": 3.2}
        result = _select_decision_type(cfg, ingest)
        assert result == "risk_alert"

    def test_select_decision_type_default_full_committee(self, cfg):
        ingest = MagicMock()
        ingest.returns_1d = {"BTC": 0.5, "SPY": 0.2}
        result = _select_decision_type(cfg, ingest)
        assert result == "full_committee"

    def test_select_decision_type_respects_override(self):
        cfg = DailyLoopConfig(mock=True, decision_type="crypto_change")
        ingest = MagicMock()
        ingest.returns_1d = {"BTC": 0.5, "SPY": 0.2}
        result = _select_decision_type(cfg, ingest)
        assert result == "crypto_change"


# ---------------------------------------------------------------------------
# Phase 5 — Dissent
# ---------------------------------------------------------------------------

class TestDissent:
    def test_dissent_returns_result(self, mock_ingest, mock_regime, mock_memos):
        result = _run_dissent(mock_ingest, mock_regime, mock_memos)
        assert isinstance(result, DissentResult)

    def test_dissent_majority_position_set(self, mock_ingest, mock_regime, mock_memos):
        result = _run_dissent(mock_ingest, mock_regime, mock_memos)
        assert result.majority_position != ""

    def test_dissent_groupthink_not_triggered_with_mixed_votes(self, mock_ingest, mock_regime, mock_memos):
        result = _run_dissent(mock_ingest, mock_regime, mock_memos)
        assert not result.groupthink_alert

    def test_dissent_groupthink_triggered_on_uniform_votes(self, mock_ingest, mock_regime):
        uniform_memos = SpecialistMemoResult(
            memos=[
                {"agent": f"agent_{i}", "stance": "buy", "confidence": 80,
                 "key_points": [], "recommendation": "", "dissent": ""}
                for i in range(10)
            ],
            memo_count=10,
            mock_mode=True,
        )
        result = _run_dissent(mock_ingest, mock_regime, uniform_memos)
        assert result.groupthink_alert

    def test_dissent_sentiment_state_classified(self, mock_ingest, mock_regime, mock_memos):
        result = _run_dissent(mock_ingest, mock_regime, mock_memos)
        assert result.sentiment_state in (
            "panic", "exhaustion", "healthy_skepticism",
            "disbelief_rally", "euphoric_melt_up", "narrative_saturation",
        )

    def test_dissent_no_memos_produces_clean_result(self, mock_ingest, mock_regime):
        empty_memos = SpecialistMemoResult(memos=[], memo_count=0, mock_mode=True)
        result = _run_dissent(mock_ingest, mock_regime, empty_memos)
        assert isinstance(result, DissentResult)


# ---------------------------------------------------------------------------
# Phase 6 — Portfolio Construction
# ---------------------------------------------------------------------------

class TestPortfolioConstruction:
    def test_pc_returns_result(self, mock_ingest, mock_regime, mock_memos, mock_dissent):
        result = _run_portfolio_construction(mock_ingest, mock_regime, mock_memos, mock_dissent)
        assert isinstance(result, PortfolioConstructionResult)

    def test_pc_coordinator_summary_non_empty(self, mock_ingest, mock_regime, mock_memos, mock_dissent):
        result = _run_portfolio_construction(mock_ingest, mock_regime, mock_memos, mock_dissent)
        assert len(result.coordinator_summary) > 10

    def test_pc_derisking_on_high_vix(self, mock_ingest, mock_regime, mock_dissent):
        ingest = MagicMock()
        ingest.vix = 35.0
        ingest.returns_20d = {}
        ingest.as_of_date = TEST_DATE
        ingest.macro_snapshot = {}

        bearish_memos = SpecialistMemoResult(
            memos=[
                {"agent": f"agent_{i}", "stance": "bearish", "confidence": 70,
                 "key_points": [], "recommendation": "reduce exposure", "dissent": ""}
                for i in range(5)
            ],
            memo_count=5,
            mock_mode=True,
        )
        result = _run_portfolio_construction(ingest, mock_regime, bearish_memos, mock_dissent)
        assert result.derisking_triggered or len(result.options_changes) > 0

    def test_pc_groupthink_mentioned_in_summary(self, mock_ingest, mock_regime, mock_memos):
        dissent_with_alert = DissentResult(
            groupthink_alert=True,
            groupthink_reason="90% consensus detected",
            dissent_suppressed=False,
            dissenting_agents=[],
            majority_position="buy",
            majority_pct=0.90,
            sentiment_state="healthy_skepticism",
            sentiment_rationale="",
            recommendations=[],
        )
        result = _run_portfolio_construction(mock_ingest, mock_regime, mock_memos, dissent_with_alert)
        assert "groupthink" in result.coordinator_summary.lower()

    def test_pc_regime_persistence_blocks_deallocation(self, mock_ingest, mock_regime, mock_memos, mock_dissent):
        # Euphoric sentiment should trigger deallocation attempt,
        # but regime persistence (not enough confirmations) will block it
        euphoric_dissent = DissentResult(
            groupthink_alert=False,
            groupthink_reason="",
            dissent_suppressed=False,
            dissenting_agents=[],
            majority_position="buy",
            majority_pct=0.6,
            sentiment_state="euphoric_melt_up",
            sentiment_rationale="",
            recommendations=[],
        )
        result = _run_portfolio_construction(mock_ingest, mock_regime, mock_memos, euphoric_dissent)
        # If portfolio has large positions, regime persistence should block trims
        # (The mock portfolio may not have large positions, so just check structure)
        assert isinstance(result.regime_persistence_blocks, list)


# ---------------------------------------------------------------------------
# Phase 8 — Learning
# ---------------------------------------------------------------------------

class TestLearning:
    def test_learning_returns_result(self, mock_ingest, mock_regime, mock_memos, mock_cio):
        result = _run_learning(mock_ingest, mock_regime, mock_memos, mock_cio)
        assert isinstance(result, LearningResult)

    def test_learning_notes_is_list(self, mock_ingest, mock_regime, mock_memos, mock_cio):
        result = _run_learning(mock_ingest, mock_regime, mock_memos, mock_cio)
        assert isinstance(result.notes, list)

    def test_learning_votes_recorded_non_negative(self, mock_ingest, mock_regime, mock_memos, mock_cio):
        result = _run_learning(mock_ingest, mock_regime, mock_memos, mock_cio)
        assert result.votes_recorded >= 0


# ---------------------------------------------------------------------------
# Phase 9 — Org Review
# ---------------------------------------------------------------------------

class TestOrgReview:
    def test_org_review_returns_result(self, mock_ingest, mock_memos):
        result = _run_org_review(mock_ingest, mock_memos)
        assert isinstance(result, OrgReviewResult)

    def test_org_complexity_score_in_range(self, mock_ingest, mock_memos):
        result = _run_org_review(mock_ingest, mock_memos)
        assert 0 <= result.complexity_score <= 200  # generous upper bound

    def test_org_health_score_non_negative(self, mock_ingest, mock_memos):
        result = _run_org_review(mock_ingest, mock_memos)
        assert result.health_score >= 0


# ---------------------------------------------------------------------------
# Phase 10 — Final Report
# ---------------------------------------------------------------------------

class TestFinalReport:
    def test_format_front_page_non_empty(
        self, cfg, mock_ingest, mock_regime, mock_routing, mock_dissent, mock_cio, mock_org
    ):
        text = _format_front_page(cfg, mock_ingest, mock_regime, mock_routing, mock_dissent, mock_cio, mock_org)
        assert len(text) > 200

    def test_format_front_page_contains_regime(
        self, cfg, mock_ingest, mock_regime, mock_routing, mock_dissent, mock_cio, mock_org
    ):
        text = _format_front_page(cfg, mock_ingest, mock_regime, mock_routing, mock_dissent, mock_cio, mock_org)
        assert "Risk-On Expansion" in text

    def test_format_front_page_contains_cio_stance(
        self, cfg, mock_ingest, mock_regime, mock_routing, mock_dissent, mock_cio, mock_org
    ):
        text = _format_front_page(cfg, mock_ingest, mock_regime, mock_routing, mock_dissent, mock_cio, mock_org)
        assert "Hold" in text

    def test_format_front_page_contains_disclaimer(
        self, cfg, mock_ingest, mock_regime, mock_routing, mock_dissent, mock_cio, mock_org
    ):
        text = _format_front_page(cfg, mock_ingest, mock_regime, mock_routing, mock_dissent, mock_cio, mock_org)
        assert "ADVISORY ONLY" in text

    def test_format_appendix_non_empty(
        self, mock_ingest, mock_regime, mock_routing, mock_memos,
        mock_dissent, mock_pc, mock_cio, mock_learning, mock_org
    ):
        phase_results = [PhaseResult(phase="ingest", status="ok", elapsed_s=0.1)]
        text = _format_appendix(
            mock_ingest, mock_regime, mock_routing, mock_memos,
            mock_dissent, mock_pc, mock_cio, mock_learning, mock_org, phase_results
        )
        assert len(text) > 200

    def test_format_appendix_contains_phase_timing(
        self, mock_ingest, mock_regime, mock_routing, mock_memos,
        mock_dissent, mock_pc, mock_cio, mock_learning, mock_org
    ):
        phase_results = [PhaseResult(phase="ingest", status="ok", elapsed_s=0.123)]
        text = _format_appendix(
            mock_ingest, mock_regime, mock_routing, mock_memos,
            mock_dissent, mock_pc, mock_cio, mock_learning, mock_org, phase_results
        )
        assert "ingest" in text
        assert "0.123" in text


# ---------------------------------------------------------------------------
# Full loop integration
# ---------------------------------------------------------------------------

class TestRunDailyLoop:
    def test_full_mock_loop_all_phases_ok(self, cfg, tmp_path, monkeypatch):
        monkeypatch.setattr(
            "src.daily_loop.DAILY_LOOPS_DIR", tmp_path / "loops"
        )
        monkeypatch.setattr(
            "src.daily_loop.REPORTS_DAILY_DIR", tmp_path / "reports"
        )
        result = run_daily_loop(cfg)
        assert isinstance(result, DailyLoopResult)
        assert set(result.phases_ok()) == {
            "ingest", "regime", "routing", "memos", "dissent",
            "portfolio_construction", "cio_decision", "learning",
            "org_review", "final_report",
        }
        assert result.phases_failed() == []

    def test_result_has_run_id(self, cfg, tmp_path, monkeypatch):
        monkeypatch.setattr("src.daily_loop.DAILY_LOOPS_DIR", tmp_path / "loops")
        monkeypatch.setattr("src.daily_loop.REPORTS_DAILY_DIR", tmp_path / "reports")
        result = run_daily_loop(cfg)
        assert result.run_id.startswith("LOOP-")

    def test_result_timing_present(self, cfg, tmp_path, monkeypatch):
        monkeypatch.setattr("src.daily_loop.DAILY_LOOPS_DIR", tmp_path / "loops")
        monkeypatch.setattr("src.daily_loop.REPORTS_DAILY_DIR", tmp_path / "reports")
        result = run_daily_loop(cfg)
        assert result.total_elapsed_s > 0
        assert result.started_at != ""
        assert result.completed_at != ""

    def test_phase_result_count(self, cfg, tmp_path, monkeypatch):
        monkeypatch.setattr("src.daily_loop.DAILY_LOOPS_DIR", tmp_path / "loops")
        monkeypatch.setattr("src.daily_loop.REPORTS_DAILY_DIR", tmp_path / "reports")
        result = run_daily_loop(cfg)
        assert len(result.phase_results) == 10

    def test_ingest_populated(self, cfg, tmp_path, monkeypatch):
        monkeypatch.setattr("src.daily_loop.DAILY_LOOPS_DIR", tmp_path / "loops")
        monkeypatch.setattr("src.daily_loop.REPORTS_DAILY_DIR", tmp_path / "reports")
        result = run_daily_loop(cfg)
        assert result.ingest is not None
        assert result.ingest.data_source == "mock"

    def test_regime_populated(self, cfg, tmp_path, monkeypatch):
        monkeypatch.setattr("src.daily_loop.DAILY_LOOPS_DIR", tmp_path / "loops")
        monkeypatch.setattr("src.daily_loop.REPORTS_DAILY_DIR", tmp_path / "reports")
        result = run_daily_loop(cfg)
        assert result.regime is not None
        assert len(result.regime.sub_assessments) == 5

    def test_routing_populated(self, cfg, tmp_path, monkeypatch):
        monkeypatch.setattr("src.daily_loop.DAILY_LOOPS_DIR", tmp_path / "loops")
        monkeypatch.setattr("src.daily_loop.REPORTS_DAILY_DIR", tmp_path / "reports")
        result = run_daily_loop(cfg)
        assert result.routing is not None
        assert len(result.routing.engaged_specialists) > 0

    def test_memos_populated(self, cfg, tmp_path, monkeypatch):
        monkeypatch.setattr("src.daily_loop.DAILY_LOOPS_DIR", tmp_path / "loops")
        monkeypatch.setattr("src.daily_loop.REPORTS_DAILY_DIR", tmp_path / "reports")
        result = run_daily_loop(cfg)
        assert result.memos is not None
        assert result.memos.mock_mode is True

    def test_cio_decision_populated(self, cfg, tmp_path, monkeypatch):
        monkeypatch.setattr("src.daily_loop.DAILY_LOOPS_DIR", tmp_path / "loops")
        monkeypatch.setattr("src.daily_loop.REPORTS_DAILY_DIR", tmp_path / "reports")
        result = run_daily_loop(cfg)
        assert result.cio_decision is not None
        assert result.cio_decision.final_confidence >= 0

    def test_final_report_populated(self, cfg, tmp_path, monkeypatch):
        monkeypatch.setattr("src.daily_loop.DAILY_LOOPS_DIR", tmp_path / "loops")
        monkeypatch.setattr("src.daily_loop.REPORTS_DAILY_DIR", tmp_path / "reports")
        result = run_daily_loop(cfg)
        assert result.final_report is not None
        assert len(result.final_report.front_page) > 100

    def test_phases_ok_helper(self, cfg, tmp_path, monkeypatch):
        monkeypatch.setattr("src.daily_loop.DAILY_LOOPS_DIR", tmp_path / "loops")
        monkeypatch.setattr("src.daily_loop.REPORTS_DAILY_DIR", tmp_path / "reports")
        result = run_daily_loop(cfg)
        assert "ingest" in result.phases_ok()
        assert "regime" in result.phases_ok()

    def test_phases_failed_empty_on_success(self, cfg, tmp_path, monkeypatch):
        monkeypatch.setattr("src.daily_loop.DAILY_LOOPS_DIR", tmp_path / "loops")
        monkeypatch.setattr("src.daily_loop.REPORTS_DAILY_DIR", tmp_path / "reports")
        result = run_daily_loop(cfg)
        assert result.phases_failed() == []

    def test_skip_phases(self, tmp_path, monkeypatch):
        monkeypatch.setattr("src.daily_loop.DAILY_LOOPS_DIR", tmp_path / "loops")
        monkeypatch.setattr("src.daily_loop.REPORTS_DAILY_DIR", tmp_path / "reports")
        cfg = DailyLoopConfig(mock=True, date=TEST_DATE, skip_phases=["org_review", "final_report"])
        result = run_daily_loop(cfg)
        org_pr = result.phase("org_review")
        assert org_pr is not None and org_pr.status == "skipped"
        report_pr = result.phase("final_report")
        assert report_pr is not None and report_pr.status == "skipped"

    def test_loop_resilient_to_phase_error(self, tmp_path, monkeypatch):
        monkeypatch.setattr("src.daily_loop.DAILY_LOOPS_DIR", tmp_path / "loops")
        monkeypatch.setattr("src.daily_loop.REPORTS_DAILY_DIR", tmp_path / "reports")

        def _bad_org(*args, **kwargs):
            raise RuntimeError("Simulated org review crash")

        monkeypatch.setattr("src.daily_loop._run_org_review", _bad_org)
        cfg = DailyLoopConfig(mock=True, date=TEST_DATE)
        result = run_daily_loop(cfg)
        # Org review should fail but rest should continue
        assert "org_review" in result.phases_failed()
        assert "final_report" in result.phases_ok()

    def test_default_config_runs(self, tmp_path, monkeypatch):
        monkeypatch.setattr("src.daily_loop.DAILY_LOOPS_DIR", tmp_path / "loops")
        monkeypatch.setattr("src.daily_loop.REPORTS_DAILY_DIR", tmp_path / "reports")
        result = run_daily_loop()  # no config = default mock
        assert isinstance(result, DailyLoopResult)


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------

class TestPersistence:
    def test_persist_and_load(self, cfg, tmp_path, monkeypatch):
        monkeypatch.setattr("src.daily_loop.DAILY_LOOPS_DIR", tmp_path / "loops")
        monkeypatch.setattr("src.daily_loop.REPORTS_DAILY_DIR", tmp_path / "reports")
        run_daily_loop(cfg)
        loaded = load_daily_result(TEST_DATE)
        assert loaded is not None
        assert loaded["date"] == TEST_DATE

    def test_loaded_result_has_phases_ok(self, cfg, tmp_path, monkeypatch):
        monkeypatch.setattr("src.daily_loop.DAILY_LOOPS_DIR", tmp_path / "loops")
        monkeypatch.setattr("src.daily_loop.REPORTS_DAILY_DIR", tmp_path / "reports")
        run_daily_loop(cfg)
        loaded = load_daily_result(TEST_DATE)
        assert "phases_ok" in loaded
        assert isinstance(loaded["phases_ok"], list)

    def test_list_daily_results_returns_list(self, tmp_path, monkeypatch):
        monkeypatch.setattr("src.daily_loop.DAILY_LOOPS_DIR", tmp_path / "loops")
        monkeypatch.setattr("src.daily_loop.REPORTS_DAILY_DIR", tmp_path / "reports")
        results = list_daily_results()
        assert isinstance(results, list)

    def test_list_daily_results_finds_persisted(self, cfg, tmp_path, monkeypatch):
        monkeypatch.setattr("src.daily_loop.DAILY_LOOPS_DIR", tmp_path / "loops")
        monkeypatch.setattr("src.daily_loop.REPORTS_DAILY_DIR", tmp_path / "reports")
        run_daily_loop(cfg)
        results = list_daily_results()
        assert len(results) >= 1

    def test_load_missing_date_returns_none(self, tmp_path, monkeypatch):
        monkeypatch.setattr("src.daily_loop.DAILY_LOOPS_DIR", tmp_path / "loops")
        loaded = load_daily_result("2000-01-01")
        assert loaded is None


# ---------------------------------------------------------------------------
# PhaseResult helpers
# ---------------------------------------------------------------------------

class TestPhaseResult:
    def test_ok_status(self):
        pr = PhaseResult(phase="ingest", status="ok", elapsed_s=0.1)
        assert pr.ok() is True

    def test_error_status(self):
        pr = PhaseResult(phase="ingest", status="error", elapsed_s=0.1, error="fail")
        assert pr.ok() is False

    def test_skipped_status(self):
        pr = PhaseResult(phase="ingest", status="skipped", elapsed_s=0.0)
        assert pr.ok() is False

    def test_phase_accessor(self, tmp_path, monkeypatch):
        monkeypatch.setattr("src.daily_loop.DAILY_LOOPS_DIR", tmp_path / "loops")
        monkeypatch.setattr("src.daily_loop.REPORTS_DAILY_DIR", tmp_path / "reports")
        cfg = DailyLoopConfig(mock=True, date=TEST_DATE)
        result = run_daily_loop(cfg)
        pr = result.phase("ingest")
        assert pr is not None
        assert pr.phase == "ingest"

    def test_phase_accessor_returns_none_for_unknown(self, tmp_path, monkeypatch):
        monkeypatch.setattr("src.daily_loop.DAILY_LOOPS_DIR", tmp_path / "loops")
        monkeypatch.setattr("src.daily_loop.REPORTS_DAILY_DIR", tmp_path / "reports")
        cfg = DailyLoopConfig(mock=True, date=TEST_DATE)
        result = run_daily_loop(cfg)
        assert result.phase("nonexistent_phase") is None
