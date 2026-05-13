"""Tests for agent_weight_governor.py"""

import sys
import json
import uuid
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from agent_weight_governor import (
    PreDownweightChecklist,
    WeightChangeProposal,
    WeightChangeDirection,
    WeightChangeStatus,
    propose_weight_change,
    record_weight_approval,
    load_weights,
    save_weights,
    get_agent_weight,
    weight_governance_summary,
    load_proposal_log,
    save_proposal_log,
    WEIGHT_MIN,
    WEIGHT_MAX,
    WEIGHT_DEFAULT,
    MIN_VOTES_FOR_DOWNWEIGHT,
    MIN_VOTES_FOR_UPWEIGHT,
    MIN_DAYS_TRACKING_FOR_DOWNWEIGHT,
    MIN_DAYS_TRACKING_FOR_UPWEIGHT,
    MAX_SINGLE_ADJUSTMENT,
    MIN_CONSECUTIVE_FAILURES_BEFORE_REVIEW,
    REQUIRED_APPROVERS_DOWNWEIGHT,
)


# ── Helpers ─────────────────────────────────────────────────────────────────

def _passing_checklist(**overrides) -> PreDownweightChecklist:
    defaults = dict(
        was_agent_wrong_not_early=True,
        was_regime_neutral_or_favorable=True,
        was_sizing_adequate_not_primary_issue=True,
        agent_did_not_identify_overlooked_risks=True,
        agent_showed_no_improvement_after_feedback=True,
        is_pattern_not_noise=True,
        n_failures_cited=6,
        n_total_votes=25,
    )
    defaults.update(overrides)
    return PreDownweightChecklist(**defaults)


def _propose_downweight(tmp_path, agent="macro_strategist", weight=0.90, checklist=None):
    weights_path = tmp_path / "agent_weights.json"
    log_path = tmp_path / "agent_weight_log.json"
    with (
        patch("agent_weight_governor.WEIGHTS_PATH", weights_path),
        patch("agent_weight_governor.WEIGHT_LOG_PATH", log_path),
    ):
        return propose_weight_change(
            agent=agent,
            proposed_weight=weight,
            proposed_by="learning_coordinator",
            rationale="Systematic underperformance documented.",
            evidence_summary="25 votes, 35% hit rate across neutral regimes.",
            n_resolved_votes=MIN_VOTES_FOR_DOWNWEIGHT,
            days_tracked=MIN_DAYS_TRACKING_FOR_DOWNWEIGHT,
            checklist=checklist or _passing_checklist(),
        )


# ── PreDownweightChecklist ───────────────────────────────────────────────────

def test_all_gates_pass_when_all_true():
    cl = _passing_checklist()
    assert cl.all_gates_pass is True
    assert cl.blocking_reasons == []


def test_gate_1_blocks_when_early():
    cl = _passing_checklist(was_agent_wrong_not_early=False)
    assert cl.all_gates_pass is False
    assert any("EARLY" in r for r in cl.blocking_reasons)


def test_gate_2_blocks_on_hostile_regime():
    cl = _passing_checklist(was_regime_neutral_or_favorable=False)
    assert cl.all_gates_pass is False
    assert any("hostile" in r.lower() for r in cl.blocking_reasons)


def test_gate_3_blocks_on_sizing_error():
    cl = _passing_checklist(was_sizing_adequate_not_primary_issue=False)
    assert cl.all_gates_pass is False
    assert any("sizing" in r.lower() for r in cl.blocking_reasons)


def test_gate_4_blocks_when_found_risks():
    cl = _passing_checklist(agent_did_not_identify_overlooked_risks=False)
    assert cl.all_gates_pass is False
    assert any("risk" in r.lower() for r in cl.blocking_reasons)


def test_gate_5_blocks_when_improving():
    cl = _passing_checklist(agent_showed_no_improvement_after_feedback=False)
    assert cl.all_gates_pass is False
    assert any("improvement" in r.lower() for r in cl.blocking_reasons)


def test_gate_6_blocks_when_noise():
    cl = _passing_checklist(is_pattern_not_noise=False, n_failures_cited=3)
    assert cl.all_gates_pass is False
    assert any("noise" in r.lower() or "pattern" in r.lower() for r in cl.blocking_reasons)


def test_multiple_gates_fail_shows_multiple_reasons():
    cl = _passing_checklist(
        was_agent_wrong_not_early=False,
        was_regime_neutral_or_favorable=False,
    )
    assert len(cl.blocking_reasons) == 2


def test_checklist_to_dict_has_all_fields():
    cl = _passing_checklist()
    d = cl.to_dict()
    assert "all_gates_pass" in d
    assert "blocking_reasons" in d
    assert "was_agent_wrong_not_early" in d
    assert d["all_gates_pass"] is True


# ── Weight bounds ────────────────────────────────────────────────────────────

def test_weight_min_is_half():
    assert WEIGHT_MIN == 0.5


def test_weight_max_is_one_and_half():
    assert WEIGHT_MAX == 1.5


def test_weight_default_is_one():
    assert WEIGHT_DEFAULT == 1.0


def test_max_single_adjustment():
    assert MAX_SINGLE_ADJUSTMENT == 0.10


def test_required_approvers():
    assert "cio" in REQUIRED_APPROVERS_DOWNWEIGHT
    assert "learning_coordinator" in REQUIRED_APPROVERS_DOWNWEIGHT
    assert len(REQUIRED_APPROVERS_DOWNWEIGHT) == 2


# ── Structural gate validation ───────────────────────────────────────────────

def test_downweight_below_min_blocked(tmp_path):
    weights_path = tmp_path / "agent_weights.json"
    log_path = tmp_path / "agent_weight_log.json"
    with (
        patch("agent_weight_governor.WEIGHTS_PATH", weights_path),
        patch("agent_weight_governor.WEIGHT_LOG_PATH", log_path),
    ):
        proposal, issues = propose_weight_change(
            agent="macro_strategist",
            proposed_weight=0.4,  # below WEIGHT_MIN
            proposed_by="test",
            rationale="test",
            evidence_summary="test",
            n_resolved_votes=MIN_VOTES_FOR_DOWNWEIGHT,
            days_tracked=MIN_DAYS_TRACKING_FOR_DOWNWEIGHT,
            checklist=_passing_checklist(),
        )
    assert any("minimum" in i.lower() or "floor" in i.lower() or "0.5" in i for i in issues)


def test_upweight_above_max_blocked(tmp_path):
    weights_path = tmp_path / "agent_weights.json"
    log_path = tmp_path / "agent_weight_log.json"
    with (
        patch("agent_weight_governor.WEIGHTS_PATH", weights_path),
        patch("agent_weight_governor.WEIGHT_LOG_PATH", log_path),
    ):
        proposal, issues = propose_weight_change(
            agent="macro_strategist",
            proposed_weight=1.6,  # above WEIGHT_MAX
            proposed_by="test",
            rationale="test",
            evidence_summary="test",
            n_resolved_votes=MIN_VOTES_FOR_UPWEIGHT,
            days_tracked=MIN_DAYS_TRACKING_FOR_UPWEIGHT,
        )
    assert any("maximum" in i.lower() or "1.5" in i for i in issues)


def test_adjustment_too_large_blocked(tmp_path):
    weights_path = tmp_path / "agent_weights.json"
    log_path = tmp_path / "agent_weight_log.json"
    with (
        patch("agent_weight_governor.WEIGHTS_PATH", weights_path),
        patch("agent_weight_governor.WEIGHT_LOG_PATH", log_path),
    ):
        proposal, issues = propose_weight_change(
            agent="macro_strategist",
            proposed_weight=0.75,  # 0.25 delta — too large
            proposed_by="test",
            rationale="test",
            evidence_summary="test",
            n_resolved_votes=MIN_VOTES_FOR_DOWNWEIGHT,
            days_tracked=MIN_DAYS_TRACKING_FOR_DOWNWEIGHT,
            checklist=_passing_checklist(),
        )
    assert any("adjustment" in i.lower() or "0.10" in i for i in issues)


def test_insufficient_votes_for_downweight_blocked(tmp_path):
    weights_path = tmp_path / "agent_weights.json"
    log_path = tmp_path / "agent_weight_log.json"
    with (
        patch("agent_weight_governor.WEIGHTS_PATH", weights_path),
        patch("agent_weight_governor.WEIGHT_LOG_PATH", log_path),
    ):
        _, issues = propose_weight_change(
            agent="macro_strategist",
            proposed_weight=0.95,
            proposed_by="test",
            rationale="test",
            evidence_summary="test",
            n_resolved_votes=MIN_VOTES_FOR_DOWNWEIGHT - 1,
            days_tracked=MIN_DAYS_TRACKING_FOR_DOWNWEIGHT,
            checklist=_passing_checklist(),
        )
    assert any("resolved votes" in i.lower() for i in issues)


def test_insufficient_days_for_downweight_blocked(tmp_path):
    weights_path = tmp_path / "agent_weights.json"
    log_path = tmp_path / "agent_weight_log.json"
    with (
        patch("agent_weight_governor.WEIGHTS_PATH", weights_path),
        patch("agent_weight_governor.WEIGHT_LOG_PATH", log_path),
    ):
        _, issues = propose_weight_change(
            agent="macro_strategist",
            proposed_weight=0.95,
            proposed_by="test",
            rationale="test",
            evidence_summary="test",
            n_resolved_votes=MIN_VOTES_FOR_DOWNWEIGHT,
            days_tracked=MIN_DAYS_TRACKING_FOR_DOWNWEIGHT - 1,
            checklist=_passing_checklist(),
        )
    assert any("days" in i.lower() for i in issues)


def test_insufficient_votes_for_upweight_blocked(tmp_path):
    weights_path = tmp_path / "agent_weights.json"
    log_path = tmp_path / "agent_weight_log.json"
    with (
        patch("agent_weight_governor.WEIGHTS_PATH", weights_path),
        patch("agent_weight_governor.WEIGHT_LOG_PATH", log_path),
    ):
        _, issues = propose_weight_change(
            agent="macro_strategist",
            proposed_weight=1.05,
            proposed_by="test",
            rationale="test",
            evidence_summary="test",
            n_resolved_votes=MIN_VOTES_FOR_UPWEIGHT - 1,
            days_tracked=MIN_DAYS_TRACKING_FOR_UPWEIGHT,
        )
    assert any("resolved votes" in i.lower() for i in issues)


def test_missing_checklist_blocks_downweight(tmp_path):
    weights_path = tmp_path / "agent_weights.json"
    log_path = tmp_path / "agent_weight_log.json"
    with (
        patch("agent_weight_governor.WEIGHTS_PATH", weights_path),
        patch("agent_weight_governor.WEIGHT_LOG_PATH", log_path),
    ):
        _, issues = propose_weight_change(
            agent="macro_strategist",
            proposed_weight=0.95,
            proposed_by="test",
            rationale="test",
            evidence_summary="test",
            n_resolved_votes=MIN_VOTES_FOR_DOWNWEIGHT,
            days_tracked=MIN_DAYS_TRACKING_FOR_DOWNWEIGHT,
            checklist=None,  # missing!
        )
    assert any("checklist" in i.lower() for i in issues)


def test_failing_checklist_blocks_downweight(tmp_path):
    weights_path = tmp_path / "agent_weights.json"
    log_path = tmp_path / "agent_weight_log.json"
    bad_checklist = _passing_checklist(was_agent_wrong_not_early=False)
    with (
        patch("agent_weight_governor.WEIGHTS_PATH", weights_path),
        patch("agent_weight_governor.WEIGHT_LOG_PATH", log_path),
    ):
        _, issues = propose_weight_change(
            agent="macro_strategist",
            proposed_weight=0.95,
            proposed_by="test",
            rationale="test",
            evidence_summary="test",
            n_resolved_votes=MIN_VOTES_FOR_DOWNWEIGHT,
            days_tracked=MIN_DAYS_TRACKING_FOR_DOWNWEIGHT,
            checklist=bad_checklist,
        )
    assert any("EARLY" in i for i in issues)


# ── Valid proposal creation ───────────────────────────────────────────────────

def test_valid_downweight_creates_proposal(tmp_path):
    proposal, issues = _propose_downweight(tmp_path)
    assert issues == []
    assert proposal.status == WeightChangeStatus.PROPOSED.value
    assert proposal.direction == WeightChangeDirection.DECREASE.value
    assert proposal.delta < 0


def test_valid_upweight_creates_proposal(tmp_path):
    weights_path = tmp_path / "agent_weights.json"
    log_path = tmp_path / "agent_weight_log.json"
    with (
        patch("agent_weight_governor.WEIGHTS_PATH", weights_path),
        patch("agent_weight_governor.WEIGHT_LOG_PATH", log_path),
    ):
        proposal, issues = propose_weight_change(
            agent="macro_strategist",
            proposed_weight=1.05,
            proposed_by="cio",
            rationale="Consistent outperformance.",
            evidence_summary="20 votes, 72% hit rate.",
            n_resolved_votes=MIN_VOTES_FOR_UPWEIGHT,
            days_tracked=MIN_DAYS_TRACKING_FOR_UPWEIGHT,
        )
    assert issues == []
    assert proposal.direction == WeightChangeDirection.INCREASE.value
    assert proposal.delta > 0


def test_blocked_proposal_not_saved(tmp_path):
    weights_path = tmp_path / "agent_weights.json"
    log_path = tmp_path / "agent_weight_log.json"
    with (
        patch("agent_weight_governor.WEIGHTS_PATH", weights_path),
        patch("agent_weight_governor.WEIGHT_LOG_PATH", log_path),
    ):
        _, issues = propose_weight_change(
            agent="macro_strategist",
            proposed_weight=0.95,
            proposed_by="test",
            rationale="test",
            evidence_summary="test",
            n_resolved_votes=5,  # too few
            days_tracked=MIN_DAYS_TRACKING_FOR_DOWNWEIGHT,
            checklist=_passing_checklist(),
        )
        assert len(issues) > 0
        assert not log_path.exists()


# ── Approval workflow ─────────────────────────────────────────────────────────

def test_dual_approval_activates_weight_change(tmp_path):
    weights_path = tmp_path / "agent_weights.json"
    log_path = tmp_path / "agent_weight_log.json"
    with (
        patch("agent_weight_governor.WEIGHTS_PATH", weights_path),
        patch("agent_weight_governor.WEIGHT_LOG_PATH", log_path),
    ):
        proposal, _ = _propose_downweight(tmp_path, weight=0.95)
        pid = proposal.id

        record_weight_approval(pid, "cio", "approve", "Evidence supports downweight.")
        p, _ = record_weight_approval(pid, "learning_coordinator", "approve", "Checklist satisfied.")

        assert p.status == WeightChangeStatus.APPROVED.value
        assert p.approved_date is not None

        weights = load_weights()
        assert weights.get("macro_strategist") == 0.95


def test_single_approval_not_enough(tmp_path):
    weights_path = tmp_path / "agent_weights.json"
    log_path = tmp_path / "agent_weight_log.json"
    with (
        patch("agent_weight_governor.WEIGHTS_PATH", weights_path),
        patch("agent_weight_governor.WEIGHT_LOG_PATH", log_path),
    ):
        proposal, _ = _propose_downweight(tmp_path, weight=0.95)
        pid = proposal.id

        record_weight_approval(pid, "cio", "approve", "Looks good.")
        log = load_proposal_log()
        p = next(x for x in log if x.id == pid)

        assert p.status == WeightChangeStatus.PROPOSED.value
        assert not weights_path.exists() or "macro_strategist" not in load_weights()


def test_single_rejection_blocks(tmp_path):
    weights_path = tmp_path / "agent_weights.json"
    log_path = tmp_path / "agent_weight_log.json"
    with (
        patch("agent_weight_governor.WEIGHTS_PATH", weights_path),
        patch("agent_weight_governor.WEIGHT_LOG_PATH", log_path),
    ):
        proposal, _ = _propose_downweight(tmp_path, weight=0.95)
        pid = proposal.id

        record_weight_approval(pid, "cio", "approve", "OK.")
        p, _ = record_weight_approval(pid, "learning_coordinator", "reject", "Insufficient evidence.")

        assert p.status == WeightChangeStatus.REJECTED.value
        assert not weights_path.exists() or "macro_strategist" not in load_weights()


def test_invalid_reviewer_rejected(tmp_path):
    weights_path = tmp_path / "agent_weights.json"
    log_path = tmp_path / "agent_weight_log.json"
    with (
        patch("agent_weight_governor.WEIGHTS_PATH", weights_path),
        patch("agent_weight_governor.WEIGHT_LOG_PATH", log_path),
    ):
        proposal, _ = _propose_downweight(tmp_path, weight=0.95)
        p, msg = record_weight_approval(proposal.id, "macro_strategist", "approve")

    assert p is None
    assert "not a required approver" in msg.lower()


def test_invalid_vote_value_rejected(tmp_path):
    weights_path = tmp_path / "agent_weights.json"
    log_path = tmp_path / "agent_weight_log.json"
    with (
        patch("agent_weight_governor.WEIGHTS_PATH", weights_path),
        patch("agent_weight_governor.WEIGHT_LOG_PATH", log_path),
    ):
        proposal, _ = _propose_downweight(tmp_path, weight=0.95)
        p, msg = record_weight_approval(proposal.id, "cio", "maybe")

    assert p is None
    assert "invalid vote" in msg.lower()


def test_vote_on_nonexistent_proposal(tmp_path):
    log_path = tmp_path / "agent_weight_log.json"
    weights_path = tmp_path / "agent_weights.json"
    with (
        patch("agent_weight_governor.WEIGHTS_PATH", weights_path),
        patch("agent_weight_governor.WEIGHT_LOG_PATH", log_path),
    ):
        p, msg = record_weight_approval("WC-NONEXISTENT", "cio", "approve")

    assert p is None
    assert "not found" in msg.lower()


# ── Weight defaults and persistence ──────────────────────────────────────────

def test_get_agent_weight_defaults_to_one(tmp_path):
    weights_path = tmp_path / "agent_weights.json"
    with patch("agent_weight_governor.WEIGHTS_PATH", weights_path):
        w = get_agent_weight("macro_strategist")
    assert w == WEIGHT_DEFAULT


def test_save_and_load_weights(tmp_path):
    weights_path = tmp_path / "agent_weights.json"
    with patch("agent_weight_governor.WEIGHTS_PATH", weights_path):
        save_weights({"macro_strategist": 0.9, "cio": 1.1})
        loaded = load_weights()
    assert loaded["macro_strategist"] == 0.9
    assert loaded["cio"] == 1.1


# ── Weight governance summary ─────────────────────────────────────────────────

def test_governance_summary_structure(tmp_path):
    weights_path = tmp_path / "agent_weights.json"
    log_path = tmp_path / "agent_weight_log.json"
    with (
        patch("agent_weight_governor.WEIGHTS_PATH", weights_path),
        patch("agent_weight_governor.WEIGHT_LOG_PATH", log_path),
    ):
        summary = weight_governance_summary()

    assert "all_weights" in summary
    assert "weight_range" in summary
    assert "governance_thresholds" in summary
    assert "pending_proposals" in summary
    assert "recent_approved_changes" in summary
    assert summary["weight_range"]["min"] == WEIGHT_MIN
    assert summary["weight_range"]["max"] == WEIGHT_MAX
    assert summary["governance_thresholds"]["min_votes_downweight"] == MIN_VOTES_FOR_DOWNWEIGHT
    assert summary["governance_thresholds"]["min_days_downweight"] == MIN_DAYS_TRACKING_FOR_DOWNWEIGHT


def test_governance_summary_shows_pending(tmp_path):
    weights_path = tmp_path / "agent_weights.json"
    log_path = tmp_path / "agent_weight_log.json"
    with (
        patch("agent_weight_governor.WEIGHTS_PATH", weights_path),
        patch("agent_weight_governor.WEIGHT_LOG_PATH", log_path),
    ):
        _propose_downweight(tmp_path, weight=0.95)
        summary = weight_governance_summary()

    assert len(summary["pending_proposals"]) == 1


# ── Proposal serialization ────────────────────────────────────────────────────

def test_proposal_to_dict_has_required_fields(tmp_path):
    proposal, _ = _propose_downweight(tmp_path, weight=0.95)
    d = proposal.to_dict()
    for key in ("id", "agent", "current_weight", "proposed_weight", "direction",
                "status", "checklist", "structural_gates_pass"):
        assert key in d


def test_proposal_delta_correct(tmp_path):
    proposal, _ = _propose_downweight(tmp_path, weight=0.95)
    assert abs(proposal.delta - (-0.05)) < 0.001


# ── Thresholds: upweight vs downweight asymmetry ──────────────────────────────

def test_upweight_lower_bar_than_downweight():
    assert MIN_VOTES_FOR_UPWEIGHT < MIN_VOTES_FOR_DOWNWEIGHT
    assert MIN_DAYS_TRACKING_FOR_UPWEIGHT < MIN_DAYS_TRACKING_FOR_DOWNWEIGHT
