"""Tests for memo_builder.py"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from memo_builder import (
    AgentMemo,
    PortfolioSnapshot,
    build_context_packet,
    build_cio_brief,
    parse_memo_from_response,
    summarize_memos_for_coordinator,
)


def _make_portfolio() -> PortfolioSnapshot:
    return PortfolioSnapshot(
        total_value=100_000.0,
        cash_pct=30.0,
        positions=[
            {"ticker": "SPY", "pct": 20.0, "bucket": "core_structural", "thesis_state": "Confirming"},
            {"ticker": "GLD", "pct": 10.0, "bucket": "core_structural", "thesis_state": "High Conviction"},
            {"ticker": "MSTR", "pct": 10.0, "bucket": "core_structural", "thesis_state": "Confirming"},
        ],
        active_theses=[
            {"id": "THESIS-001", "asset": "SPY", "state": "Confirming", "confidence": 60},
            {"id": "THESIS-002", "asset": "BTC", "state": "High Conviction", "confidence": 72},
        ],
        latest_nav_return_pct=5.2,
        options_premium_at_risk_pct=3.5,
    )


def _make_valid_response(
    stance="Bullish",
    confidence=70,
    dissent="No",
    risk_flags="none",
) -> str:
    return f"""STANCE: {stance}
CONFIDENCE: {confidence}
KEY POINTS:
- Macro regime supports risk-on positioning
- Scarcity thesis intact with strong on-chain metrics
- Momentum confirming with volume
RECOMMENDATION: Maintain current allocation. Consider adding on dips.
DISSENT: {dissent}
DISSENT REASON: {"Crowding risk in crypto underappreciated." if dissent == "Yes" else ""}
RISK FLAGS: {risk_flags}
INVALIDATION SIGNALS: RSI breaks below 50 on weekly | ETF outflows sustained 3 weeks
"""


# ── Context packet tests ────────────────────────────────────────────────────

def test_context_packet_contains_decision_question():
    portfolio = _make_portfolio()
    packet = build_context_packet(
        agent="macro_strategist",
        decision_type="macro_update",
        decision_question="Is the macro regime supportive of risk-on positioning?",
        portfolio=portfolio,
    )
    assert "Is the macro regime supportive of risk-on positioning?" in packet


def test_context_packet_contains_isolation_notice():
    portfolio = _make_portfolio()
    packet = build_context_packet(
        agent="technical_chart_expert",
        decision_type="technical_signal",
        decision_question="Is the technical structure constructive?",
        portfolio=portfolio,
    )
    assert "ISOLATION NOTICE" in packet


def test_context_packet_contains_portfolio_data():
    portfolio = _make_portfolio()
    packet = build_context_packet(
        agent="valuation_analyst",
        decision_type="full_committee",
        decision_question="Evaluate portfolio positioning.",
        portfolio=portfolio,
    )
    assert "SPY" in packet
    assert "GLD" in packet
    assert "$100,000" in packet


def test_context_packet_includes_coordinator_summary():
    portfolio = _make_portfolio()
    packet = build_context_packet(
        agent="risk_officer",
        decision_type="risk_alert",
        decision_question="Assess tail risk.",
        portfolio=portfolio,
        prior_coordinator_summary="Research coordinator summary: macro regime is cautious.",
    )
    assert "Research coordinator summary" in packet


def test_context_packet_excludes_other_specialists():
    portfolio = _make_portfolio()
    packet = build_context_packet(
        agent="momentum_trader",
        decision_type="technical_signal",
        decision_question="Confirm momentum direction.",
        portfolio=portfolio,
    )
    # The isolation notice tells agents NOT to infer consensus
    assert "Do not attempt to infer consensus" in packet


def test_context_packet_includes_asset_context():
    portfolio = _make_portfolio()
    packet = build_context_packet(
        agent="crypto_strategist",
        decision_type="crypto_change",
        decision_question="Evaluate BTC exposure.",
        portfolio=portfolio,
        asset_context={"BTC Price": "$95,000", "ETF Flows": "+$500M weekly"},
    )
    assert "BTC Price" in packet
    assert "$95,000" in packet


# ── Memo parsing tests ──────────────────────────────────────────────────────

def test_parse_memo_stance():
    memo = parse_memo_from_response("macro_strategist", "macro_update", _make_valid_response())
    assert memo.stance == "Bullish"


def test_parse_memo_confidence_bounded():
    memo = parse_memo_from_response("macro_strategist", "macro_update", _make_valid_response(confidence=70))
    assert 1 <= memo.confidence <= 100
    assert memo.confidence == 70


def test_parse_memo_key_points():
    memo = parse_memo_from_response("scarcity_strategist", "full_committee", _make_valid_response())
    assert len(memo.key_points) >= 1
    assert all(isinstance(p, str) and len(p) > 0 for p in memo.key_points)


def test_parse_memo_recommendation():
    memo = parse_memo_from_response("sentiment_analyst", "macro_update", _make_valid_response())
    assert len(memo.recommendation) > 10


def test_parse_memo_dissent_flag_no():
    memo = parse_memo_from_response("valuation_analyst", "full_committee", _make_valid_response(dissent="No"))
    assert memo.dissent_flag is False


def test_parse_memo_dissent_flag_yes():
    memo = parse_memo_from_response("bear_case_analyst", "full_committee", _make_valid_response(dissent="Yes"))
    assert memo.dissent_flag is True
    assert len(memo.dissent_reason) > 0


def test_parse_memo_risk_flags_none():
    memo = parse_memo_from_response("momentum_trader", "technical_signal", _make_valid_response(risk_flags="none"))
    assert memo.risk_flags == []


def test_parse_memo_risk_flags_present():
    memo = parse_memo_from_response(
        "risk_officer", "risk_alert",
        _make_valid_response(risk_flags="tail risk unpriced | liquidity thin")
    )
    assert len(memo.risk_flags) == 2


def test_parse_memo_invalidation_signals():
    memo = parse_memo_from_response("macro_strategist", "macro_update", _make_valid_response())
    assert len(memo.invalidation_signals) >= 1


def test_parse_memo_malformed_gracefully():
    bad_response = "This is not a structured response at all."
    memo = parse_memo_from_response("test_agent", "full_committee", bad_response)
    assert memo.agent == "test_agent"
    assert 1 <= memo.confidence <= 100  # fallback to 50
    assert isinstance(memo.stance, str)


def test_parse_memo_to_dict():
    memo = parse_memo_from_response("technical_chart_expert", "technical_signal", _make_valid_response())
    d = memo.to_dict()
    assert "agent" in d
    assert "stance" in d
    assert "confidence" in d
    assert "key_points" in d
    assert "recommendation" in d


# ── Coordinator synthesis tests ──────────────────────────────────────────────

def test_summarize_memos_returns_string():
    memos = [
        parse_memo_from_response("macro_strategist", "macro_update", _make_valid_response("Bullish", 70)),
        parse_memo_from_response("scarcity_strategist", "macro_update", _make_valid_response("Bullish", 65)),
        parse_memo_from_response("bear_case_analyst", "macro_update", _make_valid_response("Bearish", 40, dissent="Yes")),
    ]
    summary = summarize_memos_for_coordinator(memos)
    assert isinstance(summary, str)
    assert "macro_strategist" in summary.lower() or "MACRO_STRATEGIST" in summary


def test_summarize_memos_shows_dissenter():
    memos = [
        parse_memo_from_response("macro_strategist", "full_committee", _make_valid_response("Bullish", 70)),
        parse_memo_from_response("bear_case_analyst", "full_committee", _make_valid_response("Bearish", 35, dissent="Yes")),
    ]
    summary = summarize_memos_for_coordinator(memos)
    assert "bear_case_analyst" in summary


def test_summarize_memos_empty():
    summary = summarize_memos_for_coordinator([])
    assert "No specialist memos" in summary


def test_summarize_memos_average_confidence():
    memos = [
        parse_memo_from_response("a", "full_committee", _make_valid_response("Bullish", 60)),
        parse_memo_from_response("b", "full_committee", _make_valid_response("Bullish", 80)),
    ]
    summary = summarize_memos_for_coordinator(memos)
    assert "70" in summary  # average of 60 and 80


# ── CIO brief tests ──────────────────────────────────────────────────────────

def test_build_cio_brief_contains_all_sections():
    brief = build_cio_brief(
        research_summary="Research summary here.",
        bear_case_summary="Bear case summary here.",
        portfolio_construction_notes="No changes required.",
        decision_question="Should we increase BTC exposure?",
        routing_rationale="Crypto change decision type.",
    )
    assert "Research Coordinator Summary" in brief
    assert "Risk & Dissent Coordinator Summary" in brief
    assert "Portfolio Construction Notes" in brief
    assert "CIO Required Output" in brief
    assert "Should we increase BTC exposure?" in brief


def test_memo_to_summary_bounded():
    memo = parse_memo_from_response(
        "technical_chart_expert", "technical_signal",
        _make_valid_response("Wait", 55)
    )
    summary = memo.to_summary(max_points=2)
    assert "technical_chart_expert" in summary.lower()
    assert "Wait" in summary
