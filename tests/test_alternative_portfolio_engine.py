"""Tests for alternative_portfolio_engine.py"""

import sys
import json
import tempfile
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from alternative_portfolio_engine import (
    PortfolioProposal,
    PortfolioCategory,
    ProposalStatus,
    ApprovalVote,
    calculate_weight_overlap,
    validate_proposal,
    propose_portfolio,
    record_approval_vote,
    retire_portfolio,
    governance_summary,
    seed_registry_from_legacy,
    load_registry,
    save_registry,
    REQUIRED_APPROVERS,
    MAX_ACTIVE_PORTFOLIOS,
    MAX_WEIGHT_OVERLAP_VS_CIO,
    MAX_WEIGHT_OVERLAP_VS_EXISTING,
)


MAIN_CIO_WEIGHTS = {
    "SPY": 0.20, "QQQ": 0.15, "MSTR": 0.10,
    "GLD": 0.10, "URNM": 0.05, "STRC_PROXY": 0.40,
}

VALID_WEIGHTS = {"MSTR": 0.30, "GLD": 0.25, "URNM": 0.20, "IBIT": 0.15, "XLE": 0.10}
VALID_THESIS = "Concentrated bet that monetary debasement accelerates and scarce hard assets dramatically outperform over a 3–5 year horizon."


def _make_valid_proposal(**overrides) -> PortfolioProposal:
    defaults = dict(
        id="ALT-TEST0001",
        name="Test Scarcity Portfolio",
        thesis=VALID_THESIS,
        differentiation="Eliminates all broad equity. Concentrates in scarcity only. Main CIO holds 35% equity; this holds 0%.",
        intended_regime="reflation",
        expected_failure_mode="Deflationary bust or BTC regulatory shock.",
        benchmark_relevance="Tests whether pure scarcity concentration beats diversified scarcity + equity.",
        why_deserves_tracking="Represents maximum-conviction scarcity worldview.",
        review_cadence="monthly",
        category=PortfolioCategory.CONCENTRATED_THESIS.value,
        weights=VALID_WEIGHTS.copy(),
        proposed_by="test_agent",
        proposed_date="2026-05-13",
        retirement_criteria="If BTC scarcity thesis invalidated or trails CIO by >20% over 12 months.",
    )
    defaults.update(overrides)
    return PortfolioProposal(**defaults)


# ── Weight overlap tests ────────────────────────────────────────────────────

def test_weight_overlap_identical():
    w = {"SPY": 0.5, "GLD": 0.5}
    assert calculate_weight_overlap(w, w) == 1.0


def test_weight_overlap_disjoint():
    a = {"SPY": 0.5, "GLD": 0.5}
    b = {"MSTR": 0.6, "URNM": 0.4}
    assert calculate_weight_overlap(a, b) == 0.0


def test_weight_overlap_partial():
    a = {"SPY": 0.5, "GLD": 0.5}
    b = {"SPY": 0.3, "MSTR": 0.7}
    overlap = calculate_weight_overlap(a, b)
    assert abs(overlap - 0.3) < 1e-9


def test_weight_overlap_symmetric():
    a = {"SPY": 0.6, "GLD": 0.4}
    b = {"SPY": 0.4, "GLD": 0.2, "MSTR": 0.4}
    assert abs(calculate_weight_overlap(a, b) - calculate_weight_overlap(b, a)) < 1e-9


# ── Validation tests ────────────────────────────────────────────────────────

def test_validate_proposal_valid():
    proposal = _make_valid_proposal()
    issues = validate_proposal(proposal, [], MAIN_CIO_WEIGHTS)
    assert issues == [], f"Expected no issues, got: {issues}"


def test_validate_weights_must_sum_to_one():
    proposal = _make_valid_proposal(weights={"SPY": 0.6, "GLD": 0.6})
    issues = validate_proposal(proposal, [], MAIN_CIO_WEIGHTS)
    assert any("sum" in i.lower() or "1.0" in i for i in issues)


def test_validate_empty_weights():
    proposal = _make_valid_proposal(weights={})
    issues = validate_proposal(proposal, [], MAIN_CIO_WEIGHTS)
    assert any("no weights" in i.lower() or "sum" in i.lower() for i in issues)


def test_validate_too_similar_to_cio():
    # Nearly identical to CIO
    cio_clone = {k: v for k, v in MAIN_CIO_WEIGHTS.items()}
    proposal = _make_valid_proposal(weights=cio_clone)
    issues = validate_proposal(proposal, [], MAIN_CIO_WEIGHTS)
    assert any("similar to main cio" in i.lower() or "cio" in i.lower() for i in issues)


def test_validate_too_similar_to_existing():
    existing = _make_valid_proposal(
        id="ALT-EXISTING",
        name="Existing Portfolio",
        weights=VALID_WEIGHTS.copy(),
        status=ProposalStatus.ACTIVE.value,
    )
    new_proposal = _make_valid_proposal(
        id="ALT-NEWONE01",
        name="Nearly Identical Portfolio",
        weights=VALID_WEIGHTS.copy(),
    )
    issues = validate_proposal(new_proposal, [existing], MAIN_CIO_WEIGHTS)
    assert any("similar to existing" in i.lower() or "100%" in i for i in issues)


def test_validate_thesis_too_short():
    proposal = _make_valid_proposal(thesis="Too short.")
    issues = validate_proposal(proposal, [], MAIN_CIO_WEIGHTS)
    assert any("thesis" in i.lower() and "brief" in i.lower() for i in issues)


def test_validate_missing_differentiation():
    proposal = _make_valid_proposal(differentiation="")
    issues = validate_proposal(proposal, [], MAIN_CIO_WEIGHTS)
    assert any("differentiation" in i.lower() for i in issues)


def test_validate_missing_failure_mode():
    proposal = _make_valid_proposal(expected_failure_mode="")
    issues = validate_proposal(proposal, [], MAIN_CIO_WEIGHTS)
    assert any("failure mode" in i.lower() for i in issues)


def test_validate_missing_retirement_criteria():
    proposal = _make_valid_proposal(retirement_criteria="")
    issues = validate_proposal(proposal, [], MAIN_CIO_WEIGHTS)
    assert any("retirement" in i.lower() for i in issues)


def test_validate_invalid_category():
    proposal = _make_valid_proposal(category="made_up_category")
    issues = validate_proposal(proposal, [], MAIN_CIO_WEIGHTS)
    assert any("category" in i.lower() for i in issues)


def test_validate_invalid_cadence():
    proposal = _make_valid_proposal(review_cadence="daily")
    issues = validate_proposal(proposal, [], MAIN_CIO_WEIGHTS)
    assert any("cadence" in i.lower() for i in issues)


def test_validate_all_valid_categories():
    for cat in PortfolioCategory:
        proposal = _make_valid_proposal(category=cat.value)
        issues = validate_proposal(proposal, [], MAIN_CIO_WEIGHTS)
        category_issues = [i for i in issues if "category" in i.lower()]
        assert category_issues == [], f"Category '{cat.value}' should be valid but got: {category_issues}"


# ── Proposal lifecycle tests ───────────────────────────────────────────────

def test_propose_and_store(tmp_path):
    registry_path = tmp_path / "registry.json"
    with patch("alternative_portfolio_engine.REGISTRY_PATH", registry_path):
        proposal, issues = propose_portfolio(
            name="Test Portfolio",
            thesis=VALID_THESIS,
            differentiation="No equity. 100% scarcity assets. Opposite of CIO's 35% equity allocation.",
            intended_regime="reflation",
            expected_failure_mode="Deflationary bust wipes out all risk assets simultaneously.",
            benchmark_relevance="Tests pure scarcity vs diversified portfolio.",
            why_deserves_tracking="Maximum differentiation from main CIO worldview.",
            review_cadence="monthly",
            category=PortfolioCategory.CONCENTRATED_THESIS.value,
            weights=VALID_WEIGHTS,
            proposed_by="test",
            retirement_criteria="If scarcity thesis invalidated or 20% trailing after 12 months.",
            main_cio_weights=MAIN_CIO_WEIGHTS,
        )
        assert issues == []
        assert proposal.status == ProposalStatus.UNDER_REVIEW.value
        assert registry_path.exists()
        with open(registry_path) as f:
            stored = json.load(f)
        assert len(stored) == 1
        assert stored[0]["name"] == "Test Portfolio"


def test_propose_invalid_not_stored(tmp_path):
    registry_path = tmp_path / "registry.json"
    with patch("alternative_portfolio_engine.REGISTRY_PATH", registry_path):
        _, issues = propose_portfolio(
            name="Bad Portfolio",
            thesis="Too short.",
            differentiation="",
            intended_regime="bull",
            expected_failure_mode="",
            benchmark_relevance="test",
            why_deserves_tracking="test",
            review_cadence="monthly",
            category=PortfolioCategory.REGIME.value,
            weights={"SPY": 0.5, "GLD": 0.8},  # invalid sum
            proposed_by="test",
            retirement_criteria="",
            main_cio_weights=MAIN_CIO_WEIGHTS,
        )
        assert len(issues) > 0
        assert not registry_path.exists()


# ── Approval workflow tests ────────────────────────────────────────────────

def test_requires_all_three_approvers(tmp_path):
    registry_path = tmp_path / "registry.json"
    with patch("alternative_portfolio_engine.REGISTRY_PATH", registry_path):
        proposal, _ = propose_portfolio(
            name="Approval Test Portfolio",
            thesis=VALID_THESIS,
            differentiation="No equity exposure. Pure scarcity assets only. Fundamentally different from CIO.",
            intended_regime="reflation",
            expected_failure_mode="Deflationary bust.",
            benchmark_relevance="Scarcity concentration test.",
            why_deserves_tracking="Learning value.",
            review_cadence="monthly",
            category=PortfolioCategory.CONCENTRATED_THESIS.value,
            weights=VALID_WEIGHTS,
            proposed_by="test",
            retirement_criteria="Thesis invalidated.",
            main_cio_weights=MAIN_CIO_WEIGHTS,
        )
        pid = proposal.id

        # Two approvals — not enough
        record_approval_vote(pid, "cio", "approve", "Looks good.")
        record_approval_vote(pid, "learning_coordinator", "approve", "Learning value confirmed.")

        registry = load_registry()
        p = next(x for x in registry if x.id == pid)
        assert p.status == ProposalStatus.UNDER_REVIEW.value
        assert not p.is_fully_approved

        # Third approval — activates
        record_approval_vote(pid, "risk_dissent_coordinator", "approve", "Risk acceptable.")
        registry = load_registry()
        p = next(x for x in registry if x.id == pid)
        assert p.status == ProposalStatus.ACTIVE.value
        assert p.is_fully_approved


def test_single_rejection_blocks_approval(tmp_path):
    registry_path = tmp_path / "registry.json"
    with patch("alternative_portfolio_engine.REGISTRY_PATH", registry_path):
        proposal, _ = propose_portfolio(
            name="Rejection Test Portfolio",
            thesis=VALID_THESIS,
            differentiation="Pure scarcity play. No equity whatsoever. Opposite of broad market exposure.",
            intended_regime="reflation",
            expected_failure_mode="Deflationary environment.",
            benchmark_relevance="Pure scarcity benchmark.",
            why_deserves_tracking="Testing scarcity concentration thesis.",
            review_cadence="monthly",
            category=PortfolioCategory.CONCENTRATED_THESIS.value,
            weights=VALID_WEIGHTS,
            proposed_by="test",
            retirement_criteria="Thesis invalidated.",
            main_cio_weights=MAIN_CIO_WEIGHTS,
        )
        pid = proposal.id

        record_approval_vote(pid, "cio", "approve", "OK.")
        record_approval_vote(pid, "learning_coordinator", "reject", "Selection bias concern.")

        registry = load_registry()
        p = next(x for x in registry if x.id == pid)
        assert p.status == ProposalStatus.REJECTED.value
        assert p.is_rejected


def test_invalid_approver_rejected(tmp_path):
    registry_path = tmp_path / "registry.json"
    with patch("alternative_portfolio_engine.REGISTRY_PATH", registry_path):
        save_registry([_make_valid_proposal(status=ProposalStatus.UNDER_REVIEW.value)])
        p, msg = record_approval_vote("ALT-TEST0001", "macro_strategist", "approve")
        assert p is None
        assert "not a required approver" in msg.lower()


def test_invalid_vote_value_rejected(tmp_path):
    registry_path = tmp_path / "registry.json"
    with patch("alternative_portfolio_engine.REGISTRY_PATH", registry_path):
        save_registry([_make_valid_proposal(status=ProposalStatus.UNDER_REVIEW.value)])
        p, msg = record_approval_vote("ALT-TEST0001", "cio", "maybe")
        assert p is None
        assert "invalid vote" in msg.lower()


# ── Retirement tests ───────────────────────────────────────────────────────

def test_retire_active_portfolio(tmp_path):
    registry_path = tmp_path / "registry.json"
    with patch("alternative_portfolio_engine.REGISTRY_PATH", registry_path):
        active = _make_valid_proposal(status=ProposalStatus.ACTIVE.value)
        save_registry([active])
        p, msg = retire_portfolio("ALT-TEST0001", "Thesis invalidated by BTC regulatory shock.")
        assert p.status == ProposalStatus.RETIRED.value
        assert p.retired_date is not None
        assert "invalidated" in p.retirement_reason.lower()


def test_retire_non_active_fails(tmp_path):
    registry_path = tmp_path / "registry.json"
    with patch("alternative_portfolio_engine.REGISTRY_PATH", registry_path):
        proposed = _make_valid_proposal(status=ProposalStatus.PROPOSED.value)
        save_registry([proposed])
        p, msg = retire_portfolio("ALT-TEST0001", "Testing.")
        assert p.status == ProposalStatus.PROPOSED.value
        assert "only active" in msg.lower()


# ── Governance summary tests ────────────────────────────────────────────────

def test_governance_summary_structure(tmp_path):
    registry_path = tmp_path / "registry.json"
    with patch("alternative_portfolio_engine.REGISTRY_PATH", registry_path):
        active = _make_valid_proposal(status=ProposalStatus.ACTIVE.value)
        save_registry([active])
        summary = governance_summary()
        assert "total_in_registry" in summary
        assert "active" in summary
        assert "capacity_remaining" in summary
        assert summary["active"] == 1
        assert summary["capacity_remaining"] == MAX_ACTIVE_PORTFOLIOS - 1


# ── Proposal data integrity ────────────────────────────────────────────────

def test_proposal_serialization_roundtrip():
    p = _make_valid_proposal()
    d = p.to_dict()
    p2 = PortfolioProposal.from_dict(d)
    assert p2.name == p.name
    assert p2.weights == p.weights
    assert p2.category == p.category


def test_proposal_pending_approvers():
    p = _make_valid_proposal(status=ProposalStatus.UNDER_REVIEW.value)
    p.approval_records = [{"reviewer": "cio", "vote": "approve", "notes": "", "date": "2026-05-13"}]
    pending = p.pending_approvers()
    assert "cio" not in pending
    assert "learning_coordinator" in pending
    assert "risk_dissent_coordinator" in pending


# ── Seed tests ─────────────────────────────────────────────────────────────

def test_seed_registry_creates_active_portfolios(tmp_path):
    registry_path = tmp_path / "registry.json"
    with patch("alternative_portfolio_engine.REGISTRY_PATH", registry_path):
        added = seed_registry_from_legacy(MAIN_CIO_WEIGHTS)
        assert len(added) > 0
        registry = load_registry()
        for p in registry:
            assert p.status == ProposalStatus.ACTIVE.value
            assert p.is_fully_approved


def test_seed_idempotent(tmp_path):
    registry_path = tmp_path / "registry.json"
    with patch("alternative_portfolio_engine.REGISTRY_PATH", registry_path):
        added_first = seed_registry_from_legacy(MAIN_CIO_WEIGHTS)
        added_second = seed_registry_from_legacy(MAIN_CIO_WEIGHTS)
        assert added_second == []  # no duplicates added
        registry = load_registry()
        assert len(registry) == len(added_first)


# ── Category enum completeness ─────────────────────────────────────────────

def test_all_eight_categories_exist():
    categories = {c.value for c in PortfolioCategory}
    required = {"regime", "tactical", "structural", "concentrated_thesis",
                "contrarian", "macro_defensive", "experimental", "hybrid"}
    assert categories == required
