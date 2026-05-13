"""Tests for org_evolution_engine.py"""

import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from org_evolution_engine import (
    AgentProposalType,
    OrgProposalStatus,
    ObservationCategory,
    ObservationSeverity,
    ComplexityImpact,
    ComplexityMetrics,
    OrgObservation,
    AgentProposalChecklist,
    AgentProposal,
    WorkflowChange,
    OrgImprovementReport,
    propose_agent_change,
    propose_workflow_change,
    record_org_vote,
    record_org_observation,
    generate_org_improvement_report,
    org_governance_summary,
    load_org_proposals,
    save_org_proposals,
    load_org_observations,
    save_org_observations,
    MAX_ACTIVE_AGENTS,
    MAX_DEBATE_SIZE,
    REDUNDANCY_ALERT_THRESHOLD,
    UNNECESSARY_ANALYSIS_THRESHOLD,
    REPORT_BLOAT_THRESHOLD,
    MIN_GAP_OBSERVATIONS,
    MAX_NEW_AGENT_OVERLAP,
    TRIAL_PERIOD_MIN_DAYS,
    TRIAL_PERIOD_MAX_DAYS,
    MIN_SUCCESS_CRITERIA,
    REQUIRED_APPROVERS_ORG,
    _compute_session_redundancy,
    _compute_unnecessary_rate,
    _compute_complexity_score,
    _compute_alerts,
)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _passing_checklist(**overrides) -> AgentProposalChecklist:
    defaults = dict(
        expertise_gap_documented=True,
        overlap_below_threshold=True,
        complexity_cost_bounded=True,
        trial_period_defined=True,
        success_criteria_measurable=True,
        routing_change_insufficient=True,
        specialization_is_narrow=True,
        gap_observation_count=MIN_GAP_OBSERVATIONS,
        estimated_overlap_pct=0.2,
    )
    defaults.update(overrides)
    return AgentProposalChecklist(**defaults)


VALID_PURPOSE = "Provide dedicated geopolitical risk analysis for energy and commodity theses. Identifies country-specific supply disruption risks that macro_strategist treats only at a high level."
VALID_VALUE = "Improves commodity and energy thesis accuracy by surfacing geopolitical tail risks before they materialize. Expected to increase hit rate in commodity regime by 10–15 percentage points."
VALID_OVERLAP = "macro_strategist covers geopolitical risk at ~30% overlap. No other agent explicitly analyzes country-specific supply chain disruption. Overlap below 50% threshold."
VALID_COST = "Adds 1 specialist output per commodity/energy decision session. Increases avg debate size by ~0.3. No additional coordinator layer needed."
VALID_CRITERIA = ["Hit rate ≥ 60% on commodity positions within trial period", "At least 3 unique geopolitical risks surfaced that were not identified by macro_strategist"]


def _propose_new_agent(tmp_path, **overrides):
    proposals_path = tmp_path / "org_proposals.json"
    obs_path = tmp_path / "org_obs.json"
    complexity_path = tmp_path / "complexity.json"
    with (
        patch("org_evolution_engine.ORG_PROPOSALS_PATH", proposals_path),
        patch("org_evolution_engine.ORG_OBSERVATIONS_PATH", obs_path),
        patch("org_evolution_engine.COMPLEXITY_LOG_PATH", complexity_path),
    ):
        defaults = dict(
            proposal_type=AgentProposalType.NEW_AGENT.value,
            agent_name="geopolitical_risk_analyst",
            clear_purpose=VALID_PURPOSE,
            expected_value=VALID_VALUE,
            overlap_analysis=VALID_OVERLAP,
            complexity_cost=VALID_COST,
            success_criteria=VALID_CRITERIA,
            proposed_by="learning_coordinator",
            trial_period_days=90,
            checklist=_passing_checklist(),
        )
        defaults.update(overrides)
        return propose_agent_change(**defaults)


# ── Enum completeness ─────────────────────────────────────────────────────────

def test_agent_proposal_type_values():
    values = {t.value for t in AgentProposalType}
    assert "new_agent" in values
    assert "merge_agents" in values
    assert "retire_agent" in values
    assert "temporary_agent" in values
    assert "workflow_redesign" in values
    assert "reporting_redesign" in values
    assert len(values) == 6


def test_observation_category_values():
    values = {c.value for c in ObservationCategory}
    assert "missing_expertise" in values
    assert "duplicated_expertise" in values
    assert "coordination_failure" in values
    assert "process_weakness" in values
    assert len(values) == 4


def test_org_proposal_status_values():
    values = {s.value for s in OrgProposalStatus}
    assert "proposed" in values
    assert "approved" in values
    assert "active" in values
    assert "completed" in values
    assert "rejected" in values
    assert "withdrawn" in values


# ── Complexity metrics ────────────────────────────────────────────────────────

def test_complexity_metrics_empty_sessions():
    metrics = ComplexityMetrics.from_sessions(n_active_agents=17, sessions=[])
    assert metrics.n_active_agents == 17
    assert metrics.avg_debate_size == 0.0
    assert metrics.redundant_output_rate == 0.0
    assert metrics.complexity_score >= 0.0


def test_complexity_metrics_agent_count_component():
    low = ComplexityMetrics.from_sessions(5, [])
    high = ComplexityMetrics.from_sessions(20, [])
    assert high.complexity_score > low.complexity_score


def test_complexity_metrics_debate_size():
    sessions = [{"specialists_engaged": ["a", "b", "c", "d", "e", "f", "g", "h", "i"]}]
    metrics = ComplexityMetrics.from_sessions(17, sessions)
    assert metrics.avg_debate_size == 9.0
    assert any("debate" in a.lower() for a in metrics.alerts)


def test_complexity_metrics_redundancy_alert():
    # All memos have same stance → redundancy = 100%
    sessions = [{"memos": [{"stance": "bullish"}, {"stance": "bullish"}, {"stance": "bullish"}]}]
    metrics = ComplexityMetrics.from_sessions(17, sessions)
    assert metrics.redundant_output_rate > REDUNDANCY_ALERT_THRESHOLD
    assert any("redundant" in a.lower() for a in metrics.alerts)


def test_complexity_metrics_unnecessary_analysis():
    sessions = [{
        "specialists_engaged": ["a", "b", "c", "d"],
        "cio_cited_agents": ["a"],
    }]
    metrics = ComplexityMetrics.from_sessions(17, sessions)
    assert metrics.unnecessary_analysis_rate == 0.75
    assert any("unnecessary" in a.lower() for a in metrics.alerts)


def test_complexity_metrics_report_bloat_alert():
    sessions = [{"report_sections": REPORT_BLOAT_THRESHOLD + 10}]
    metrics = ComplexityMetrics.from_sessions(17, sessions)
    assert any("bloat" in a.lower() or "report" in a.lower() for a in metrics.alerts)


def test_complexity_metrics_no_alerts_clean_sessions():
    sessions = [{
        "specialists_engaged": ["a", "b", "c"],
        "cio_cited_agents": ["a", "b", "c"],
        "memos": [{"stance": "bullish"}, {"stance": "bearish"}, {"stance": "neutral"}],
        "report_sections": 10,
    }]
    metrics = ComplexityMetrics.from_sessions(10, sessions)
    assert metrics.alerts == []
    assert not metrics.is_alerting


def test_complexity_metrics_to_dict():
    metrics = ComplexityMetrics.from_sessions(17, [])
    d = metrics.to_dict()
    for key in ("n_active_agents", "avg_debate_size", "redundant_output_rate",
                "unnecessary_analysis_rate", "complexity_score", "alerts"):
        assert key in d


def test_agent_count_alert_at_ceiling():
    alerts = _compute_alerts(MAX_ACTIVE_AGENTS, 0, 0, 0, 0)
    assert any("ceiling" in a.lower() or "count" in a.lower() for a in alerts)


def test_no_agent_count_alert_below_ceiling():
    alerts = _compute_alerts(MAX_ACTIVE_AGENTS - 1, 0, 0, 0, 0)
    assert not any("ceiling" in a.lower() for a in alerts)


def test_session_redundancy_all_same():
    session = {"memos": [{"stance": "bullish"}, {"stance": "bullish"}, {"stance": "bullish"}]}
    rate = _compute_session_redundancy(session)
    assert rate > 0.5


def test_session_redundancy_all_different():
    session = {"memos": [{"stance": "bullish"}, {"stance": "bearish"}, {"stance": "neutral"}]}
    rate = _compute_session_redundancy(session)
    assert rate == 0.0


def test_session_redundancy_empty():
    assert _compute_session_redundancy({}) == 0.0
    assert _compute_session_redundancy({"memos": []}) == 0.0


def test_unnecessary_rate_all_cited():
    session = {"specialists_engaged": ["a", "b"], "cio_cited_agents": ["a", "b"]}
    assert _compute_unnecessary_rate(session) == 0.0


def test_unnecessary_rate_none_cited():
    session = {"specialists_engaged": ["a", "b", "c"], "cio_cited_agents": []}
    assert _compute_unnecessary_rate(session) == 1.0


def test_unnecessary_rate_empty_engaged():
    assert _compute_unnecessary_rate({"specialists_engaged": []}) == 0.0


# ── AgentProposalChecklist ────────────────────────────────────────────────────

def test_checklist_all_gates_pass():
    cl = _passing_checklist()
    assert cl.all_gates_pass is True
    assert cl.blocking_reasons == []


def test_gate_1_blocks_undocumented_gap():
    cl = _passing_checklist(expertise_gap_documented=False, gap_observation_count=1)
    assert cl.all_gates_pass is False
    assert any("gap" in r.lower() for r in cl.blocking_reasons)


def test_gate_2_blocks_high_overlap():
    cl = _passing_checklist(overlap_below_threshold=False, estimated_overlap_pct=0.7)
    assert cl.all_gates_pass is False
    assert any("overlap" in r.lower() for r in cl.blocking_reasons)


def test_gate_3_blocks_unbounded_cost():
    cl = _passing_checklist(complexity_cost_bounded=False)
    assert cl.all_gates_pass is False
    assert any("complexity" in r.lower() for r in cl.blocking_reasons)


def test_gate_4_blocks_no_trial():
    cl = _passing_checklist(trial_period_defined=False)
    assert cl.all_gates_pass is False
    assert any("trial" in r.lower() for r in cl.blocking_reasons)


def test_gate_5_blocks_vague_criteria():
    cl = _passing_checklist(success_criteria_measurable=False)
    assert cl.all_gates_pass is False
    assert any("criteria" in r.lower() or "success" in r.lower() for r in cl.blocking_reasons)


def test_gate_6_blocks_when_routing_sufficient():
    cl = _passing_checklist(routing_change_insufficient=False)
    assert cl.all_gates_pass is False
    assert any("routing" in r.lower() for r in cl.blocking_reasons)


def test_gate_7_blocks_broad_scope():
    cl = _passing_checklist(specialization_is_narrow=False)
    assert cl.all_gates_pass is False
    assert any("broad" in r.lower() or "specializ" in r.lower() for r in cl.blocking_reasons)


def test_multiple_gate_failures_all_listed():
    cl = _passing_checklist(
        expertise_gap_documented=False,
        overlap_below_threshold=False,
        trial_period_defined=False,
    )
    assert len(cl.blocking_reasons) == 3


def test_checklist_to_dict_has_required_fields():
    cl = _passing_checklist()
    d = cl.to_dict()
    assert "all_gates_pass" in d
    assert "blocking_reasons" in d
    assert d["all_gates_pass"] is True


# ── Valid proposal creation ───────────────────────────────────────────────────

def test_valid_new_agent_proposal_created(tmp_path):
    proposal, issues = _propose_new_agent(tmp_path)
    assert issues == []
    assert proposal.status == OrgProposalStatus.PROPOSED.value
    assert proposal.proposal_type == AgentProposalType.NEW_AGENT.value


def test_blocked_proposal_not_saved(tmp_path):
    proposals_path = tmp_path / "org_proposals.json"
    with patch("org_evolution_engine.ORG_PROPOSALS_PATH", proposals_path):
        _, issues = propose_agent_change(
            proposal_type=AgentProposalType.NEW_AGENT.value,
            agent_name="test",
            clear_purpose="Too short",
            expected_value="Too short",
            overlap_analysis="Too short",
            complexity_cost="Too short",
            success_criteria=["only one"],
            proposed_by="test",
            trial_period_days=90,
            checklist=_passing_checklist(),
        )
        assert len(issues) > 0
        assert not proposals_path.exists()


def test_trial_period_too_short_blocked(tmp_path):
    _, issues = _propose_new_agent(tmp_path, trial_period_days=TRIAL_PERIOD_MIN_DAYS - 1)
    assert any("trial" in i.lower() for i in issues)


def test_trial_period_too_long_blocked(tmp_path):
    _, issues = _propose_new_agent(tmp_path, trial_period_days=TRIAL_PERIOD_MAX_DAYS + 1)
    assert any("trial" in i.lower() for i in issues)


def test_agent_ceiling_blocks_new_agent(tmp_path):
    _, issues = _propose_new_agent(tmp_path, n_active_agents=MAX_ACTIVE_AGENTS)
    assert any("ceiling" in i.lower() or "count" in i.lower() for i in issues)


def test_missing_checklist_blocks_new_agent(tmp_path):
    proposals_path = tmp_path / "org_proposals.json"
    with patch("org_evolution_engine.ORG_PROPOSALS_PATH", proposals_path):
        _, issues = propose_agent_change(
            proposal_type=AgentProposalType.NEW_AGENT.value,
            agent_name="test_agent",
            clear_purpose=VALID_PURPOSE,
            expected_value=VALID_VALUE,
            overlap_analysis=VALID_OVERLAP,
            complexity_cost=VALID_COST,
            success_criteria=VALID_CRITERIA,
            proposed_by="test",
            trial_period_days=90,
            checklist=None,
        )
    assert any("checklist" in i.lower() for i in issues)


def test_failing_checklist_blocks_proposal(tmp_path):
    bad_cl = _passing_checklist(expertise_gap_documented=False, gap_observation_count=1)
    _, issues = _propose_new_agent(tmp_path, checklist=bad_cl)
    assert len(issues) > 0
    assert any("gap" in i.lower() for i in issues)


def test_retire_agent_no_checklist_required(tmp_path):
    proposals_path = tmp_path / "org_proposals.json"
    with patch("org_evolution_engine.ORG_PROPOSALS_PATH", proposals_path):
        proposal, issues = propose_agent_change(
            proposal_type=AgentProposalType.RETIRE_AGENT.value,
            agent_name="benchmark_analyst",
            clear_purpose="The benchmark_analyst's function is fully covered by the portfolio_historian and the CIO's own benchmark comparison logic. No unique value is being added.",
            expected_value="Reduces debate size by 1 specialist. Eliminates one source of redundant benchmark commentary per session.",
            overlap_analysis="portfolio_historian covers 80% of benchmark_analyst outputs. CIO directly compares to benchmarks without prompting.",
            complexity_cost="Reduces complexity — one fewer specialist in routing.",
            success_criteria=["Benchmark coverage maintained without dedicated agent", "Debate size reduced by 1 per session"],
            proposed_by="learning_coordinator",
            trial_period_days=0,
        )
    assert issues == []
    assert proposal.status == OrgProposalStatus.PROPOSED.value


def test_merge_agents_no_trial_required(tmp_path):
    proposals_path = tmp_path / "org_proposals.json"
    with patch("org_evolution_engine.ORG_PROPOSALS_PATH", proposals_path):
        proposal, issues = propose_agent_change(
            proposal_type=AgentProposalType.MERGE_AGENTS.value,
            agent_name="merged_commodity_specialist",
            agents_affected=["commodity_specialist", "scarcity_strategist"],
            clear_purpose="Merges commodity and scarcity coverage into one agent with explicit overlap. Analysis showed 72% stance overlap across 40 sessions.",
            expected_value="Reduces specialist count by 1. Eliminates redundant commodity/scarcity analysis. Expected to reduce debate size without information loss.",
            overlap_analysis="commodity_specialist and scarcity_strategist produced identical stances in 72% of sessions over 6 months.",
            complexity_cost="Reduces complexity by eliminating one specialist slot and 1 routing path.",
            success_criteria=["No information loss in commodity/scarcity coverage", "Debate size reduced by 1 per relevant session"],
            proposed_by="learning_coordinator",
            trial_period_days=0,
        )
    assert issues == []


# ── Workflow change proposal ──────────────────────────────────────────────────

def test_valid_workflow_change_created(tmp_path):
    change, issues = propose_workflow_change(
        description="Tighten CRYPTO_CHANGE routing to exclude sentiment_analyst when BTC dominance is above 60%.",
        rationale="Sentiment_analyst adds minimal value on BTC-dominant cycles — analysis shows 0% unique contribution in those sessions.",
        expected_improvement="Reduces avg debate size by 0.5 specialists per crypto session. Faster CIO decision.",
        complexity_impact=ComplexityImpact.REDUCES.value,
        proposed_by="learning_coordinator",
    )
    assert issues == []
    assert change.status == OrgProposalStatus.PROPOSED.value
    assert change.complexity_impact == ComplexityImpact.REDUCES.value


def test_workflow_change_too_brief_blocked(tmp_path):
    _, issues = propose_workflow_change(
        description="Change routing.",
        rationale="Just do it.",
        expected_improvement="Better.",
        complexity_impact=ComplexityImpact.NEUTRAL.value,
        proposed_by="test",
    )
    assert len(issues) > 0


# ── Org observation recording ─────────────────────────────────────────────────

def test_record_observation_creates_new(tmp_path):
    obs_path = tmp_path / "obs.json"
    with patch("org_evolution_engine.ORG_OBSERVATIONS_PATH", obs_path):
        obs = record_org_observation(
            category=ObservationCategory.MISSING_EXPERTISE.value,
            description="No agent covers geopolitical supply chain risk for energy positions.",
            evidence="Three commodity sessions missed geopolitical tail risk (2026-04-10, 2026-04-22, 2026-05-01).",
            severity=ObservationSeverity.MEDIUM.value,
            suggested_remedy="Propose geopolitical_risk_analyst or expand commodity_specialist scope.",
        )
    assert obs.observation_count == 1
    assert obs.category == ObservationCategory.MISSING_EXPERTISE.value
    assert not obs.is_actionable  # count < MIN_GAP_OBSERVATIONS


def test_record_observation_increments_on_repeat(tmp_path):
    obs_path = tmp_path / "obs.json"
    with patch("org_evolution_engine.ORG_OBSERVATIONS_PATH", obs_path):
        for _ in range(MIN_GAP_OBSERVATIONS):
            obs = record_org_observation(
                category=ObservationCategory.MISSING_EXPERTISE.value,
                description="No agent covers geopolitical supply chain risk for energy positions.",
                evidence="Evidence.",
                severity=ObservationSeverity.MEDIUM.value,
                suggested_remedy="Remedy.",
            )
    assert obs.observation_count == MIN_GAP_OBSERVATIONS
    assert obs.is_actionable


def test_observation_is_actionable_at_threshold(tmp_path):
    obs_path = tmp_path / "obs.json"
    with patch("org_evolution_engine.ORG_OBSERVATIONS_PATH", obs_path):
        obs = None
        for _ in range(MIN_GAP_OBSERVATIONS):
            obs = record_org_observation(
                category=ObservationCategory.COORDINATION_FAILURE.value,
                description="TECHNICAL_SIGNAL routing includes macro_strategist unnecessarily.",
                evidence="5 sessions.",
                severity=ObservationSeverity.LOW.value,
                suggested_remedy="Remove macro_strategist from TECHNICAL_SIGNAL base set.",
            )
        assert obs.is_actionable


def test_observation_not_actionable_when_resolved(tmp_path):
    obs_path = tmp_path / "obs.json"
    with patch("org_evolution_engine.ORG_OBSERVATIONS_PATH", obs_path):
        for _ in range(MIN_GAP_OBSERVATIONS):
            obs = record_org_observation(
                category=ObservationCategory.PROCESS_WEAKNESS.value,
                description="Reports are too long.",
                evidence="Evidence.",
                severity=ObservationSeverity.HIGH.value,
                suggested_remedy="Reduce sections.",
            )
        obs.resolved = True
        assert not obs.is_actionable


def test_observation_to_dict_has_fields(tmp_path):
    obs_path = tmp_path / "obs.json"
    with patch("org_evolution_engine.ORG_OBSERVATIONS_PATH", obs_path):
        obs = record_org_observation(
            category=ObservationCategory.DUPLICATED_EXPERTISE.value,
            description="commodity_specialist and scarcity_strategist overlap.",
            evidence="40 sessions, 72% identical stances.",
            severity=ObservationSeverity.HIGH.value,
            suggested_remedy="Merge agents.",
        )
    d = obs.to_dict()
    for key in ("id", "category", "description", "evidence", "observation_count",
                "severity", "suggested_remedy", "first_seen", "last_seen"):
        assert key in d


# ── Approval workflow ─────────────────────────────────────────────────────────

def test_dual_approval_activates_proposal(tmp_path):
    proposals_path = tmp_path / "org_proposals.json"
    with patch("org_evolution_engine.ORG_PROPOSALS_PATH", proposals_path):
        proposal, _ = _propose_new_agent(tmp_path)
        pid = proposal.id

        record_org_vote(pid, "cio", "approve", "Value is clear.")
        p, _ = record_org_vote(pid, "learning_coordinator", "approve", "Gates all pass.")

        assert p.status in (OrgProposalStatus.ACTIVE.value, OrgProposalStatus.APPROVED.value)
        assert p.approved_date is not None


def test_trial_period_moves_to_active_on_approval(tmp_path):
    proposals_path = tmp_path / "org_proposals.json"
    with patch("org_evolution_engine.ORG_PROPOSALS_PATH", proposals_path):
        proposal, _ = _propose_new_agent(tmp_path, trial_period_days=90)
        pid = proposal.id

        record_org_vote(pid, "cio", "approve", "OK.")
        p, _ = record_org_vote(pid, "learning_coordinator", "approve", "OK.")

        assert p.status == OrgProposalStatus.ACTIVE.value
        assert p.trial_start_date is not None


def test_single_approval_not_enough(tmp_path):
    proposals_path = tmp_path / "org_proposals.json"
    with patch("org_evolution_engine.ORG_PROPOSALS_PATH", proposals_path):
        proposal, _ = _propose_new_agent(tmp_path)
        pid = proposal.id

        record_org_vote(pid, "cio", "approve", "OK.")
        proposals = load_org_proposals()
        p = next(x for x in proposals if x.id == pid)
        assert p.status == OrgProposalStatus.PROPOSED.value


def test_single_rejection_blocks(tmp_path):
    proposals_path = tmp_path / "org_proposals.json"
    with patch("org_evolution_engine.ORG_PROPOSALS_PATH", proposals_path):
        proposal, _ = _propose_new_agent(tmp_path)
        pid = proposal.id

        record_org_vote(pid, "cio", "approve", "OK.")
        p, _ = record_org_vote(pid, "learning_coordinator", "reject", "Routing change is sufficient.")
        assert p.status == OrgProposalStatus.REJECTED.value


def test_invalid_reviewer_blocked(tmp_path):
    proposals_path = tmp_path / "org_proposals.json"
    with patch("org_evolution_engine.ORG_PROPOSALS_PATH", proposals_path):
        proposal, _ = _propose_new_agent(tmp_path)
        p, msg = record_org_vote(proposal.id, "macro_strategist", "approve")
    assert p is None
    assert "not a required approver" in msg.lower()


def test_invalid_vote_blocked(tmp_path):
    proposals_path = tmp_path / "org_proposals.json"
    with patch("org_evolution_engine.ORG_PROPOSALS_PATH", proposals_path):
        proposal, _ = _propose_new_agent(tmp_path)
        p, msg = record_org_vote(proposal.id, "cio", "maybe")
    assert p is None
    assert "invalid vote" in msg.lower()


def test_vote_on_nonexistent_proposal(tmp_path):
    proposals_path = tmp_path / "org_proposals.json"
    with patch("org_evolution_engine.ORG_PROPOSALS_PATH", proposals_path):
        p, msg = record_org_vote("ORG-DOESNOTEXIST", "cio", "approve")
    assert p is None
    assert "not found" in msg.lower()


def test_pending_approvers_list(tmp_path):
    proposals_path = tmp_path / "org_proposals.json"
    with patch("org_evolution_engine.ORG_PROPOSALS_PATH", proposals_path):
        proposal, _ = _propose_new_agent(tmp_path)
        assert set(proposal.pending_approvers()) == REQUIRED_APPROVERS_ORG

        record_org_vote(proposal.id, "cio", "approve", "OK.")
        proposals = load_org_proposals()
        p = next(x for x in proposals if x.id == proposal.id)
        assert "cio" not in p.pending_approvers()
        assert "learning_coordinator" in p.pending_approvers()


# ── Org improvement report ────────────────────────────────────────────────────

def test_generate_report_structure(tmp_path):
    proposals_path = tmp_path / "org_proposals.json"
    obs_path = tmp_path / "obs.json"
    complexity_path = tmp_path / "complexity.json"
    with (
        patch("org_evolution_engine.ORG_PROPOSALS_PATH", proposals_path),
        patch("org_evolution_engine.ORG_OBSERVATIONS_PATH", obs_path),
        patch("org_evolution_engine.COMPLEXITY_LOG_PATH", complexity_path),
    ):
        report = generate_org_improvement_report(n_active_agents=17)

    assert isinstance(report, OrgImprovementReport)
    assert "n_active_agents" in report.complexity_metrics
    assert isinstance(report.missing_expertise, list)
    assert isinstance(report.duplicated_expertise, list)
    assert isinstance(report.coordination_failures, list)
    assert isinstance(report.process_weaknesses, list)
    assert isinstance(report.proposed_agent_changes, list)
    assert isinstance(report.proposed_workflow_changes, list)
    assert isinstance(report.proposed_structural_improvements, list)
    assert 0 <= report.org_health_score <= 100
    assert len(report.conservative_note) > 0


def test_generate_report_complexity_alerts_in_structural(tmp_path):
    proposals_path = tmp_path / "org_proposals.json"
    obs_path = tmp_path / "obs.json"
    complexity_path = tmp_path / "complexity.json"
    # Agent count at ceiling triggers alert
    sessions = [{"specialists_engaged": list("abcdefghi")}]  # 9 specialists > MAX_DEBATE_SIZE=8
    with (
        patch("org_evolution_engine.ORG_PROPOSALS_PATH", proposals_path),
        patch("org_evolution_engine.ORG_OBSERVATIONS_PATH", obs_path),
        patch("org_evolution_engine.COMPLEXITY_LOG_PATH", complexity_path),
    ):
        report = generate_org_improvement_report(n_active_agents=17, sessions=sessions)

    assert report.is_alerting
    assert any("COMPLEXITY ALERT" in s for s in report.proposed_structural_improvements)


def test_generate_report_includes_pending_proposals(tmp_path):
    proposals_path = tmp_path / "org_proposals.json"
    obs_path = tmp_path / "obs.json"
    complexity_path = tmp_path / "complexity.json"
    with (
        patch("org_evolution_engine.ORG_PROPOSALS_PATH", proposals_path),
        patch("org_evolution_engine.ORG_OBSERVATIONS_PATH", obs_path),
        patch("org_evolution_engine.COMPLEXITY_LOG_PATH", complexity_path),
    ):
        _propose_new_agent(tmp_path)
        report = generate_org_improvement_report(n_active_agents=17)

    assert len(report.proposed_agent_changes) == 1


def test_generate_report_includes_observations(tmp_path):
    proposals_path = tmp_path / "org_proposals.json"
    obs_path = tmp_path / "obs.json"
    complexity_path = tmp_path / "complexity.json"
    with (
        patch("org_evolution_engine.ORG_PROPOSALS_PATH", proposals_path),
        patch("org_evolution_engine.ORG_OBSERVATIONS_PATH", obs_path),
        patch("org_evolution_engine.COMPLEXITY_LOG_PATH", complexity_path),
    ):
        record_org_observation(
            category=ObservationCategory.MISSING_EXPERTISE.value,
            description="No geopolitical risk coverage.",
            evidence="Three sessions missed it.",
            severity=ObservationSeverity.MEDIUM.value,
            suggested_remedy="Expand commodity_specialist scope.",
        )
        report = generate_org_improvement_report(n_active_agents=17)

    assert len(report.missing_expertise) == 1


def test_report_to_dict(tmp_path):
    proposals_path = tmp_path / "org_proposals.json"
    obs_path = tmp_path / "obs.json"
    complexity_path = tmp_path / "complexity.json"
    with (
        patch("org_evolution_engine.ORG_PROPOSALS_PATH", proposals_path),
        patch("org_evolution_engine.ORG_OBSERVATIONS_PATH", obs_path),
        patch("org_evolution_engine.COMPLEXITY_LOG_PATH", complexity_path),
    ):
        report = generate_org_improvement_report()
    d = report.to_dict()
    for key in ("generated_at", "complexity_metrics", "missing_expertise",
                "org_health_score", "conservative_note"):
        assert key in d


# ── Governance summary ────────────────────────────────────────────────────────

def test_governance_summary_structure(tmp_path):
    proposals_path = tmp_path / "org_proposals.json"
    obs_path = tmp_path / "obs.json"
    with (
        patch("org_evolution_engine.ORG_PROPOSALS_PATH", proposals_path),
        patch("org_evolution_engine.ORG_OBSERVATIONS_PATH", obs_path),
    ):
        summary = org_governance_summary()

    assert "total_proposals" in summary
    assert "complexity_thresholds" in summary
    assert "org_preferences" in summary
    assert summary["complexity_thresholds"]["max_active_agents"] == MAX_ACTIVE_AGENTS
    assert len(summary["org_preferences"]) >= 5


# ── Conservative constants ────────────────────────────────────────────────────

def test_max_active_agents_is_20():
    assert MAX_ACTIVE_AGENTS == 20


def test_trial_bounds():
    assert TRIAL_PERIOD_MIN_DAYS == 30
    assert TRIAL_PERIOD_MAX_DAYS == 180


def test_min_success_criteria():
    assert MIN_SUCCESS_CRITERIA == 2


def test_min_gap_observations():
    assert MIN_GAP_OBSERVATIONS == 3


def test_required_approvers_are_cio_and_learning():
    assert "cio" in REQUIRED_APPROVERS_ORG
    assert "learning_coordinator" in REQUIRED_APPROVERS_ORG
    assert len(REQUIRED_APPROVERS_ORG) == 2


def test_upweight_lower_bar_than_downweight():
    from agent_weight_governor import MIN_VOTES_FOR_UPWEIGHT, MIN_VOTES_FOR_DOWNWEIGHT
    assert MIN_VOTES_FOR_UPWEIGHT < MIN_VOTES_FOR_DOWNWEIGHT
