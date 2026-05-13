"""
Organizational Evolution Engine — Phase 3 Governance.

Tracks organizational health, proposes structural improvements, and governs
agent lifecycle changes (new / merge / retire / temporary).

Conservative by design:
- Organizational changes are harder to make than portfolio changes
- Complexity is a liability — the system monitors and resists it
- Every new agent must justify its existence with measurable criteria
- Experimentation is permitted but bounded by trial periods and gates

Advisory only — no live trading.
"""

from __future__ import annotations
import json
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Optional

ROOT_DIR = Path(__file__).parent.parent
ORG_PROPOSALS_PATH = ROOT_DIR / "data" / "processed" / "org_proposals.json"
ORG_OBSERVATIONS_PATH = ROOT_DIR / "data" / "processed" / "org_observations.json"
COMPLEXITY_LOG_PATH = ROOT_DIR / "data" / "processed" / "complexity_log.json"

DISCLAIMER = "ADVISORY ONLY. All outputs are simulated. Not financial advice."

# ── Complexity thresholds ────────────────────────────────────────────────────

MAX_ACTIVE_AGENTS = 20              # Hard ceiling on committee size
MAX_DEBATE_SIZE = 8                 # Max specialists per decision
REDUNDANCY_ALERT_THRESHOLD = 0.30   # >30% identical stances = redundancy problem
UNNECESSARY_ANALYSIS_THRESHOLD = 0.25  # >25% specialist outputs uncited by CIO
REPORT_BLOAT_THRESHOLD = 25         # >25 sections per report = bloat
COMPLEXITY_SCORE_ALERT = 70.0       # 0–100 scale; above this = intervention needed

# ── New-agent conservative gates ─────────────────────────────────────────────

MIN_GAP_OBSERVATIONS = 3            # Must observe expertise gap 3× before proposing
MAX_NEW_AGENT_OVERLAP = 0.50        # New agent must be <50% overlapping with any existing
TRIAL_PERIOD_MIN_DAYS = 30
TRIAL_PERIOD_MAX_DAYS = 180
MIN_SUCCESS_CRITERIA = 2            # At least 2 measurable success criteria required

REQUIRED_APPROVERS_ORG = frozenset(["cio", "learning_coordinator"])


# ── Proposal types ───────────────────────────────────────────────────────────

class AgentProposalType(str, Enum):
    NEW_AGENT = "new_agent"
    MERGE_AGENTS = "merge_agents"
    RETIRE_AGENT = "retire_agent"
    TEMPORARY_AGENT = "temporary_agent"
    WORKFLOW_REDESIGN = "workflow_redesign"
    REPORTING_REDESIGN = "reporting_redesign"


class OrgProposalStatus(str, Enum):
    PROPOSED = "proposed"
    APPROVED = "approved"
    REJECTED = "rejected"
    ACTIVE = "active"          # trial running
    COMPLETED = "completed"    # trial ended, permanent decision made
    WITHDRAWN = "withdrawn"


class ObservationCategory(str, Enum):
    MISSING_EXPERTISE = "missing_expertise"
    DUPLICATED_EXPERTISE = "duplicated_expertise"
    COORDINATION_FAILURE = "coordination_failure"
    PROCESS_WEAKNESS = "process_weakness"


class ObservationSeverity(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class ComplexityImpact(str, Enum):
    REDUCES = "reduces"
    NEUTRAL = "neutral"
    INCREASES = "increases"


# ── Complexity metrics ───────────────────────────────────────────────────────

@dataclass
class ComplexityMetrics:
    """Snapshot of organizational complexity at a point in time."""
    measured_at: str
    n_active_agents: int
    avg_debate_size: float          # avg specialists engaged per decision session
    redundant_output_rate: float    # fraction of memos with same stance as another in same session
    unnecessary_analysis_rate: float  # fraction of specialist memos not referenced in CIO decision
    avg_report_sections: float      # avg sections per generated report
    report_bloat_score: float       # 0–100; derived from section count and actionable density
    complexity_score: float         # composite 0–100; higher = more complex
    alerts: list[str]               # triggered threshold breaches

    def to_dict(self) -> dict:
        return asdict(self)

    @property
    def is_alerting(self) -> bool:
        return len(self.alerts) > 0 or self.complexity_score >= COMPLEXITY_SCORE_ALERT

    @classmethod
    def from_sessions(
        cls,
        n_active_agents: int,
        sessions: list[dict],
    ) -> "ComplexityMetrics":
        """
        Compute metrics from a list of committee session dicts.
        Each session dict should contain: specialists_engaged, memos, cio_cited_agents, report_sections.
        All fields are optional — missing data is treated conservatively.
        """
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        if not sessions:
            return cls(
                measured_at=now,
                n_active_agents=n_active_agents,
                avg_debate_size=0.0,
                redundant_output_rate=0.0,
                unnecessary_analysis_rate=0.0,
                avg_report_sections=0.0,
                report_bloat_score=0.0,
                complexity_score=_compute_complexity_score(n_active_agents, 0, 0, 0, 0),
                alerts=_compute_alerts(n_active_agents, 0, 0, 0, 0),
            )

        debate_sizes = [len(s.get("specialists_engaged", [])) for s in sessions]
        avg_debate = sum(debate_sizes) / len(debate_sizes) if debate_sizes else 0.0

        redundancy_rates = [_compute_session_redundancy(s) for s in sessions]
        avg_redundancy = sum(redundancy_rates) / len(redundancy_rates) if redundancy_rates else 0.0

        unnecessary_rates = [_compute_unnecessary_rate(s) for s in sessions]
        avg_unnecessary = sum(unnecessary_rates) / len(unnecessary_rates) if unnecessary_rates else 0.0

        section_counts = [s.get("report_sections", 0) for s in sessions]
        avg_sections = sum(section_counts) / len(section_counts) if section_counts else 0.0

        bloat = min(100.0, (avg_sections / REPORT_BLOAT_THRESHOLD) * 100) if avg_sections > 0 else 0.0
        complexity = _compute_complexity_score(n_active_agents, avg_debate, avg_redundancy, avg_unnecessary, bloat)
        alerts = _compute_alerts(n_active_agents, avg_debate, avg_redundancy, avg_unnecessary, avg_sections)

        return cls(
            measured_at=now,
            n_active_agents=n_active_agents,
            avg_debate_size=round(avg_debate, 2),
            redundant_output_rate=round(avg_redundancy, 4),
            unnecessary_analysis_rate=round(avg_unnecessary, 4),
            avg_report_sections=round(avg_sections, 1),
            report_bloat_score=round(bloat, 1),
            complexity_score=round(complexity, 1),
            alerts=alerts,
        )


def _compute_session_redundancy(session: dict) -> float:
    """Fraction of memos in a session that share an identical stance with another memo."""
    memos = session.get("memos", [])
    if len(memos) < 2:
        return 0.0
    stances = [m.get("stance", "").lower().strip() for m in memos]
    non_empty = [s for s in stances if s]
    if not non_empty:
        return 0.0
    duplicates = sum(1 for i, s in enumerate(non_empty) if s in non_empty[:i])
    return duplicates / len(non_empty)


def _compute_unnecessary_rate(session: dict) -> float:
    """Fraction of specialist memos whose agent was not cited in the CIO decision."""
    engaged = session.get("specialists_engaged", [])
    cited = session.get("cio_cited_agents", [])
    if not engaged:
        return 0.0
    uncited = sum(1 for a in engaged if a not in cited)
    return uncited / len(engaged)


def _compute_complexity_score(
    n_agents: int,
    avg_debate: float,
    redundancy: float,
    unnecessary: float,
    bloat: float,
) -> float:
    """Composite 0–100 complexity score. Higher = more complex."""
    agent_component = min(40.0, (n_agents / MAX_ACTIVE_AGENTS) * 40)
    debate_component = min(20.0, (avg_debate / MAX_DEBATE_SIZE) * 20)
    redundancy_component = min(20.0, (redundancy / REDUNDANCY_ALERT_THRESHOLD) * 20)
    unnecessary_component = min(10.0, (unnecessary / UNNECESSARY_ANALYSIS_THRESHOLD) * 10)
    bloat_component = min(10.0, (bloat / 100) * 10)
    return round(
        agent_component + debate_component + redundancy_component + unnecessary_component + bloat_component,
        1,
    )


def _compute_alerts(
    n_agents: int,
    avg_debate: float,
    redundancy: float,
    unnecessary: float,
    avg_sections: float,
) -> list[str]:
    alerts = []
    if n_agents >= MAX_ACTIVE_AGENTS:
        alerts.append(
            f"Agent count ({n_agents}) has reached the ceiling ({MAX_ACTIVE_AGENTS}). "
            "No new agents may be added without retiring an existing one."
        )
    if avg_debate > MAX_DEBATE_SIZE:
        alerts.append(
            f"Average debate size ({avg_debate:.1f}) exceeds maximum ({MAX_DEBATE_SIZE}). "
            "Too many specialists are being engaged per decision — review routing."
        )
    if redundancy > REDUNDANCY_ALERT_THRESHOLD:
        alerts.append(
            f"Redundant output rate ({redundancy:.0%}) exceeds threshold ({REDUNDANCY_ALERT_THRESHOLD:.0%}). "
            "Multiple agents are producing identical stances — consider merging or retiring."
        )
    if unnecessary > UNNECESSARY_ANALYSIS_THRESHOLD:
        alerts.append(
            f"Unnecessary analysis rate ({unnecessary:.0%}) exceeds threshold ({UNNECESSARY_ANALYSIS_THRESHOLD:.0%}). "
            "Specialist outputs are not being used in CIO decisions — tighten routing."
        )
    if avg_sections > REPORT_BLOAT_THRESHOLD:
        alerts.append(
            f"Average report length ({avg_sections:.0f} sections) exceeds threshold ({REPORT_BLOAT_THRESHOLD}). "
            "Reports are becoming too long — redesign for conciseness."
        )
    return alerts


# ── Organizational observation ───────────────────────────────────────────────

@dataclass
class OrgObservation:
    """A single observed organizational weakness or opportunity."""
    id: str
    category: str              # ObservationCategory value
    description: str
    evidence: str
    observation_count: int     # times this pattern has been seen
    severity: str              # ObservationSeverity value
    suggested_remedy: str
    first_seen: str
    last_seen: str
    resolved: bool = False
    resolution_notes: str = ""

    def to_dict(self) -> dict:
        return asdict(self)

    @property
    def is_actionable(self) -> bool:
        return self.observation_count >= MIN_GAP_OBSERVATIONS and not self.resolved


# ── Agent proposal checklist (7 gates for new/temporary agents) ───────────────

@dataclass
class AgentProposalChecklist:
    """
    Seven mandatory gates for all new or temporary agent proposals.
    All seven must pass before a proposal can be submitted.
    Merge and retire proposals use a shorter checklist (4 gates).
    """
    expertise_gap_documented: bool
    # True = gap observed ≥ MIN_GAP_OBSERVATIONS times and logged
    # False = BLOCK — anecdotal gaps don't justify new agents

    overlap_below_threshold: bool
    # True = proposed agent overlaps <50% with any single existing agent
    # False = BLOCK — too similar to existing coverage; merge instead

    complexity_cost_bounded: bool
    # True = explicit statement of what complexity this adds to the committee
    # False = BLOCK — must quantify the cost, not just the benefit

    trial_period_defined: bool
    # True = has a trial period within [30, 180] days
    # False = BLOCK — permanent agents require permanent justification; start with trials

    success_criteria_measurable: bool
    # True = at least 2 specific, measurable success criteria provided
    # False = BLOCK — vague criteria cannot be evaluated

    routing_change_insufficient: bool
    # True = a coordinator routing change alone cannot address the identified gap
    # False = BLOCK — routing changes are always cheaper than new agents; try them first

    specialization_is_narrow: bool
    # True = agent addresses a specific niche, not a broad domain covered by existing agents
    # False = BLOCK — broad new agents duplicate existing generalists

    # Context (informational — not gates)
    gap_observation_count: int = 0
    estimated_overlap_pct: float = 0.0
    evidence_notes: str = ""

    @property
    def all_gates_pass(self) -> bool:
        return (
            self.expertise_gap_documented
            and self.overlap_below_threshold
            and self.complexity_cost_bounded
            and self.trial_period_defined
            and self.success_criteria_measurable
            and self.routing_change_insufficient
            and self.specialization_is_narrow
        )

    @property
    def blocking_reasons(self) -> list[str]:
        reasons = []
        if not self.expertise_gap_documented:
            reasons.append(
                f"Expertise gap not sufficiently documented "
                f"(observed {self.gap_observation_count}×, require ≥{MIN_GAP_OBSERVATIONS}×). "
                "Record gap observations before proposing a new agent."
            )
        if not self.overlap_below_threshold:
            reasons.append(
                f"Proposed agent overlaps ~{self.estimated_overlap_pct:.0%} with an existing agent "
                f"(threshold: <{MAX_NEW_AGENT_OVERLAP:.0%}). "
                "Consider merging with or routing through the existing agent instead."
            )
        if not self.complexity_cost_bounded:
            reasons.append(
                "Complexity cost is not explicitly bounded. "
                "State concretely: how many additional outputs per session, what increase in latency, "
                "and which routing paths change."
            )
        if not self.trial_period_defined:
            reasons.append(
                f"No trial period defined. All new agents must run a trial of "
                f"{TRIAL_PERIOD_MIN_DAYS}–{TRIAL_PERIOD_MAX_DAYS} days "
                "before permanent status is granted."
            )
        if not self.success_criteria_measurable:
            reasons.append(
                f"Success criteria are missing or vague. "
                f"Provide at least {MIN_SUCCESS_CRITERIA} specific, measurable criteria "
                "that will be evaluated at the end of the trial period."
            )
        if not self.routing_change_insufficient:
            reasons.append(
                "A coordinator routing change may be sufficient to address this gap. "
                "Document why routing alone cannot solve the problem before proposing a new agent."
            )
        if not self.specialization_is_narrow:
            reasons.append(
                "The proposed agent's scope is too broad and risks duplicating existing generalists. "
                "Narrow the scope to a specific analytical niche."
            )
        return reasons

    def to_dict(self) -> dict:
        return {
            "expertise_gap_documented": self.expertise_gap_documented,
            "overlap_below_threshold": self.overlap_below_threshold,
            "complexity_cost_bounded": self.complexity_cost_bounded,
            "trial_period_defined": self.trial_period_defined,
            "success_criteria_measurable": self.success_criteria_measurable,
            "routing_change_insufficient": self.routing_change_insufficient,
            "specialization_is_narrow": self.specialization_is_narrow,
            "all_gates_pass": self.all_gates_pass,
            "blocking_reasons": self.blocking_reasons,
            "gap_observation_count": self.gap_observation_count,
            "estimated_overlap_pct": self.estimated_overlap_pct,
            "evidence_notes": self.evidence_notes,
        }


# ── Agent lifecycle proposal ──────────────────────────────────────────────────

@dataclass
class AgentProposal:
    """Full proposal for any agent lifecycle change."""
    id: str
    proposal_type: str               # AgentProposalType value
    agent_name: str                  # Name of agent being proposed/affected
    agents_affected: list[str]       # Existing agents affected (merge, retire)
    proposed_by: str
    proposed_date: str

    # Mandatory narrative fields
    clear_purpose: str
    expected_value: str
    overlap_analysis: str
    complexity_cost: str
    success_criteria: list[str]
    trial_period_days: int           # 0 = no trial (retire/merge only)

    # Gate results
    checklist: Optional[dict] = None          # populated for new/temporary proposals
    structural_gates_pass: bool = False
    structural_gate_failures: list[str] = field(default_factory=list)

    # Lifecycle
    status: str = OrgProposalStatus.PROPOSED.value
    approval_records: list[dict] = field(default_factory=list)
    approved_date: Optional[str] = None
    rejection_reason: str = ""
    trial_start_date: Optional[str] = None
    trial_end_date: Optional[str] = None
    outcome_notes: str = ""

    def to_dict(self) -> dict:
        return asdict(self)

    @property
    def approval_votes(self) -> dict[str, str]:
        return {r["reviewer"]: r["vote"] for r in self.approval_records}

    @property
    def is_fully_approved(self) -> bool:
        votes = self.approval_votes
        return all(votes.get(r) == "approve" for r in REQUIRED_APPROVERS_ORG)

    @property
    def is_rejected(self) -> bool:
        return self.status == OrgProposalStatus.REJECTED.value

    def pending_approvers(self) -> list[str]:
        return [r for r in sorted(REQUIRED_APPROVERS_ORG) if self.approval_votes.get(r) != "approve"]


# ── Workflow change proposal ──────────────────────────────────────────────────

@dataclass
class WorkflowChange:
    """Proposal for a routing, coordination, or process change (not an agent change)."""
    id: str
    description: str
    rationale: str
    expected_improvement: str
    complexity_impact: str           # ComplexityImpact value
    proposed_by: str
    proposed_date: str
    status: str = OrgProposalStatus.PROPOSED.value
    approval_records: list[dict] = field(default_factory=list)
    rejection_reason: str = ""
    outcome_notes: str = ""

    def to_dict(self) -> dict:
        return asdict(self)

    @property
    def approval_votes(self) -> dict[str, str]:
        return {r["reviewer"]: r["vote"] for r in self.approval_records}

    @property
    def is_fully_approved(self) -> bool:
        return all(self.approval_votes.get(r) == "approve" for r in REQUIRED_APPROVERS_ORG)


# ── Org improvement report ────────────────────────────────────────────────────

@dataclass
class OrgImprovementReport:
    """Daily organizational health and improvement watch report."""
    generated_at: str
    complexity_metrics: dict
    missing_expertise: list[dict]
    duplicated_expertise: list[dict]
    coordination_failures: list[dict]
    process_weaknesses: list[dict]
    proposed_agent_changes: list[dict]
    proposed_workflow_changes: list[dict]
    proposed_structural_improvements: list[str]
    org_health_score: float          # 0–100; higher = healthier
    is_alerting: bool
    conservative_note: str

    def to_dict(self) -> dict:
        return asdict(self)


def _compute_org_health(metrics: ComplexityMetrics, observations: list[OrgObservation]) -> float:
    """
    Org health score 0–100. Penalizes complexity and open high-severity observations.
    100 = ideal; lower = more problems detected.
    """
    health = 100.0 - metrics.complexity_score
    high_severity = sum(1 for o in observations if o.severity == ObservationSeverity.HIGH.value and not o.resolved)
    medium_severity = sum(1 for o in observations if o.severity == ObservationSeverity.MEDIUM.value and not o.resolved)
    health -= high_severity * 5
    health -= medium_severity * 2
    return max(0.0, min(100.0, round(health, 1)))


# ── Validation ────────────────────────────────────────────────────────────────

def _validate_agent_proposal_structure(
    proposal_type: str,
    clear_purpose: str,
    expected_value: str,
    overlap_analysis: str,
    complexity_cost: str,
    success_criteria: list[str],
    trial_period_days: int,
    checklist: Optional[AgentProposalChecklist],
    n_active_agents: int,
) -> tuple[bool, list[str]]:
    """
    Structural gate validation for agent proposals.
    Returns (all_pass, failures).
    """
    failures = []

    # Narrative completeness
    if len(clear_purpose.strip()) < 50:
        failures.append("Clear purpose is too brief (< 50 characters). State concretely what analytical gap this fills.")
    if len(expected_value.strip()) < 50:
        failures.append("Expected value is too brief (< 50 characters). Quantify or specify the expected improvement.")
    if len(overlap_analysis.strip()) < 30:
        failures.append("Overlap analysis is missing or too brief. Document which existing agents overlap and by how much.")
    if len(complexity_cost.strip()) < 30:
        failures.append("Complexity cost statement is missing. State what additional complexity this agent introduces.")
    if len(success_criteria) < MIN_SUCCESS_CRITERIA:
        failures.append(
            f"Too few success criteria ({len(success_criteria)} provided, {MIN_SUCCESS_CRITERIA} required). "
            "Each criterion must be measurable at the end of the trial period."
        )

    # Trial period (only for new and temporary agents)
    needs_trial = proposal_type in (AgentProposalType.NEW_AGENT.value, AgentProposalType.TEMPORARY_AGENT.value)
    if needs_trial:
        if trial_period_days < TRIAL_PERIOD_MIN_DAYS:
            failures.append(
                f"Trial period ({trial_period_days} days) is below minimum ({TRIAL_PERIOD_MIN_DAYS} days). "
                "All new agents must run a trial before permanent status."
            )
        if trial_period_days > TRIAL_PERIOD_MAX_DAYS:
            failures.append(
                f"Trial period ({trial_period_days} days) exceeds maximum ({TRIAL_PERIOD_MAX_DAYS} days). "
                "Trials must conclude within a reasonable window."
            )

    # Agent count ceiling (for new/temporary agents)
    if proposal_type in (AgentProposalType.NEW_AGENT.value, AgentProposalType.TEMPORARY_AGENT.value):
        if n_active_agents >= MAX_ACTIVE_AGENTS:
            failures.append(
                f"Agent count ({n_active_agents}) has reached the ceiling ({MAX_ACTIVE_AGENTS}). "
                "Retire or merge an existing agent before adding a new one."
            )

    # Checklist gates (required for new/temporary)
    if proposal_type in (AgentProposalType.NEW_AGENT.value, AgentProposalType.TEMPORARY_AGENT.value):
        if checklist is None:
            failures.append(
                "AgentProposalChecklist is mandatory for new and temporary agent proposals. "
                "Complete all 7 gates before submitting."
            )
        elif not checklist.all_gates_pass:
            failures.extend(checklist.blocking_reasons)

    return len(failures) == 0, failures


# ── Persistence ───────────────────────────────────────────────────────────────

def load_org_proposals() -> list[AgentProposal]:
    if not ORG_PROPOSALS_PATH.exists():
        return []
    with open(ORG_PROPOSALS_PATH) as f:
        raw = json.load(f)
    proposals = []
    for d in raw:
        d.setdefault("agents_affected", [])
        d.setdefault("checklist", None)
        d.setdefault("structural_gates_pass", False)
        d.setdefault("structural_gate_failures", [])
        d.setdefault("approval_records", [])
        d.setdefault("approved_date", None)
        d.setdefault("rejection_reason", "")
        d.setdefault("trial_start_date", None)
        d.setdefault("trial_end_date", None)
        d.setdefault("outcome_notes", "")
        proposals.append(AgentProposal(**d))
    return proposals


def save_org_proposals(proposals: list[AgentProposal]) -> None:
    ORG_PROPOSALS_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(ORG_PROPOSALS_PATH, "w") as f:
        json.dump([p.to_dict() for p in proposals], f, indent=2, default=str)


def load_org_observations() -> list[OrgObservation]:
    if not ORG_OBSERVATIONS_PATH.exists():
        return []
    with open(ORG_OBSERVATIONS_PATH) as f:
        raw = json.load(f)
    return [OrgObservation(**d) for d in raw]


def save_org_observations(observations: list[OrgObservation]) -> None:
    ORG_OBSERVATIONS_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(ORG_OBSERVATIONS_PATH, "w") as f:
        json.dump([o.to_dict() for o in observations], f, indent=2, default=str)


def load_complexity_log() -> list[dict]:
    if not COMPLEXITY_LOG_PATH.exists():
        return []
    with open(COMPLEXITY_LOG_PATH) as f:
        return json.load(f)


def append_complexity_snapshot(metrics: ComplexityMetrics) -> None:
    COMPLEXITY_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    log = load_complexity_log()
    log.append(metrics.to_dict())
    with open(COMPLEXITY_LOG_PATH, "w") as f:
        json.dump(log, f, indent=2, default=str)


# ── Public API ────────────────────────────────────────────────────────────────

def record_org_observation(
    category: str,
    description: str,
    evidence: str,
    severity: str,
    suggested_remedy: str,
) -> OrgObservation:
    """
    Record or increment an organizational observation.
    Deduplicates by (category, description) — increments observation_count on repeat.
    """
    assert category in {c.value for c in ObservationCategory}, f"Invalid category: {category}"
    assert severity in {s.value for s in ObservationSeverity}, f"Invalid severity: {severity}"

    observations = load_org_observations()
    now = datetime.now().strftime("%Y-%m-%d")

    # Dedup: match on category + first 80 chars of description
    match_key = (category, description[:80].lower())
    for obs in observations:
        if (obs.category, obs.description[:80].lower()) == match_key:
            obs.observation_count += 1
            obs.last_seen = now
            obs.evidence = evidence  # update with latest evidence
            save_org_observations(observations)
            return obs

    new_obs = OrgObservation(
        id=f"OBS-{uuid.uuid4().hex[:8].upper()}",
        category=category,
        description=description,
        evidence=evidence,
        observation_count=1,
        severity=severity,
        suggested_remedy=suggested_remedy,
        first_seen=now,
        last_seen=now,
    )
    observations.append(new_obs)
    save_org_observations(observations)
    return new_obs


def propose_agent_change(
    proposal_type: str,
    agent_name: str,
    clear_purpose: str,
    expected_value: str,
    overlap_analysis: str,
    complexity_cost: str,
    success_criteria: list[str],
    proposed_by: str,
    trial_period_days: int = 0,
    agents_affected: Optional[list[str]] = None,
    checklist: Optional[AgentProposalChecklist] = None,
    n_active_agents: int = 17,
) -> tuple[AgentProposal, list[str]]:
    """
    Submit an agent lifecycle proposal.
    Returns (proposal, blocking_issues). blocking_issues non-empty means proposal is rejected.
    """
    assert proposal_type in {t.value for t in AgentProposalType}, f"Invalid type: {proposal_type}"

    gates_pass, failures = _validate_agent_proposal_structure(
        proposal_type=proposal_type,
        clear_purpose=clear_purpose,
        expected_value=expected_value,
        overlap_analysis=overlap_analysis,
        complexity_cost=complexity_cost,
        success_criteria=success_criteria,
        trial_period_days=trial_period_days,
        checklist=checklist,
        n_active_agents=n_active_agents,
    )

    proposal = AgentProposal(
        id=f"ORG-{uuid.uuid4().hex[:8].upper()}",
        proposal_type=proposal_type,
        agent_name=agent_name,
        agents_affected=agents_affected or [],
        proposed_by=proposed_by,
        proposed_date=datetime.now().strftime("%Y-%m-%d"),
        clear_purpose=clear_purpose,
        expected_value=expected_value,
        overlap_analysis=overlap_analysis,
        complexity_cost=complexity_cost,
        success_criteria=success_criteria,
        trial_period_days=trial_period_days,
        checklist=checklist.to_dict() if checklist else None,
        structural_gates_pass=gates_pass,
        structural_gate_failures=failures,
        status=OrgProposalStatus.PROPOSED.value if not failures else OrgProposalStatus.REJECTED.value,
        rejection_reason="; ".join(failures) if failures else "",
    )

    if not failures:
        proposals = load_org_proposals()
        proposals.append(proposal)
        save_org_proposals(proposals)

    return proposal, failures


def propose_workflow_change(
    description: str,
    rationale: str,
    expected_improvement: str,
    complexity_impact: str,
    proposed_by: str,
) -> tuple[WorkflowChange, list[str]]:
    """Submit a workflow or process change proposal."""
    assert complexity_impact in {c.value for c in ComplexityImpact}, f"Invalid impact: {complexity_impact}"

    failures = []
    if len(description.strip()) < 30:
        failures.append("Description is too brief (< 30 characters).")
    if len(rationale.strip()) < 30:
        failures.append("Rationale is too brief (< 30 characters).")
    if len(expected_improvement.strip()) < 30:
        failures.append("Expected improvement statement is too brief.")

    change = WorkflowChange(
        id=f"WF-{uuid.uuid4().hex[:8].upper()}",
        description=description,
        rationale=rationale,
        expected_improvement=expected_improvement,
        complexity_impact=complexity_impact,
        proposed_by=proposed_by,
        proposed_date=datetime.now().strftime("%Y-%m-%d"),
        status=OrgProposalStatus.PROPOSED.value if not failures else OrgProposalStatus.REJECTED.value,
        rejection_reason="; ".join(failures) if failures else "",
    )
    return change, failures


def record_org_vote(
    proposal_id: str,
    reviewer: str,
    vote: str,
    notes: str = "",
) -> tuple[Optional[AgentProposal], str]:
    """Record an approval vote on an agent proposal."""
    if reviewer not in REQUIRED_APPROVERS_ORG:
        return None, f"'{reviewer}' is not a required approver. Must be: {sorted(REQUIRED_APPROVERS_ORG)}"

    proposals = load_org_proposals()
    proposal = next((p for p in proposals if p.id == proposal_id), None)
    if proposal is None:
        return None, f"Proposal '{proposal_id}' not found."

    if proposal.status not in (OrgProposalStatus.PROPOSED.value,):
        return proposal, f"Proposal is already in status '{proposal.status}'."

    vote_value = vote.lower()
    if vote_value not in ("approve", "reject", "abstain"):
        return None, f"Invalid vote '{vote}'. Must be: approve / reject / abstain"

    # Replace any prior vote from this reviewer
    proposal.approval_records = [r for r in proposal.approval_records if r["reviewer"] != reviewer]
    proposal.approval_records.append({
        "reviewer": reviewer,
        "vote": vote_value,
        "notes": notes,
        "date": datetime.now().strftime("%Y-%m-%d"),
    })

    if proposal.is_fully_approved:
        proposal.status = OrgProposalStatus.APPROVED.value
        proposal.approved_date = datetime.now().strftime("%Y-%m-%d")
        if proposal.trial_period_days > 0:
            proposal.status = OrgProposalStatus.ACTIVE.value
            proposal.trial_start_date = datetime.now().strftime("%Y-%m-%d")
        msg = f"✓ Proposal APPROVED: {proposal.agent_name} ({proposal.proposal_type})"
    elif any(r["vote"] == "reject" for r in proposal.approval_records):
        rejector = next(r["reviewer"] for r in proposal.approval_records if r["vote"] == "reject")
        proposal.status = OrgProposalStatus.REJECTED.value
        proposal.rejection_reason = f"Rejected by {rejector}: {notes}"
        msg = f"✗ Proposal REJECTED by {rejector}."
    else:
        pending = proposal.pending_approvers()
        msg = f"Vote recorded. Pending: {', '.join(pending)}"

    save_org_proposals([p if p.id != proposal_id else proposal for p in proposals])
    return proposal, msg


def generate_org_improvement_report(
    n_active_agents: int = 17,
    sessions: Optional[list[dict]] = None,
    additional_structural_improvements: Optional[list[str]] = None,
) -> OrgImprovementReport:
    """
    Generate the daily organizational improvement watch report.
    Aggregates observations, pending proposals, and complexity metrics.
    """
    sessions = sessions or []
    metrics = ComplexityMetrics.from_sessions(n_active_agents, sessions)
    append_complexity_snapshot(metrics)

    observations = load_org_observations()
    active_obs = [o for o in observations if not o.resolved]

    missing_exp = [o.to_dict() for o in active_obs if o.category == ObservationCategory.MISSING_EXPERTISE.value]
    dup_exp = [o.to_dict() for o in active_obs if o.category == ObservationCategory.DUPLICATED_EXPERTISE.value]
    coord_fail = [o.to_dict() for o in active_obs if o.category == ObservationCategory.COORDINATION_FAILURE.value]
    proc_weak = [o.to_dict() for o in active_obs if o.category == ObservationCategory.PROCESS_WEAKNESS.value]

    proposals = load_org_proposals()
    pending = [p.to_dict() for p in proposals if p.status in (
        OrgProposalStatus.PROPOSED.value, OrgProposalStatus.ACTIVE.value
    )]
    agent_proposals = [p for p in pending if p.get("proposal_type") not in (
        AgentProposalType.WORKFLOW_REDESIGN.value, AgentProposalType.REPORTING_REDESIGN.value
    )]
    workflow_proposals = [p for p in pending if p.get("proposal_type") in (
        AgentProposalType.WORKFLOW_REDESIGN.value, AgentProposalType.REPORTING_REDESIGN.value
    )]

    health = _compute_org_health(metrics, active_obs)

    structural = additional_structural_improvements or []
    if metrics.alerts:
        structural = [f"[COMPLEXITY ALERT] {a}" for a in metrics.alerts] + structural

    return OrgImprovementReport(
        generated_at=metrics.measured_at,
        complexity_metrics=metrics.to_dict(),
        missing_expertise=missing_exp,
        duplicated_expertise=dup_exp,
        coordination_failures=coord_fail,
        process_weaknesses=proc_weak,
        proposed_agent_changes=agent_proposals,
        proposed_workflow_changes=workflow_proposals,
        proposed_structural_improvements=structural,
        org_health_score=health,
        is_alerting=metrics.is_alerting or health < 60.0,
        conservative_note=(
            "Organizational changes are subject to conservative gates. "
            f"New agents require a {TRIAL_PERIOD_MIN_DAYS}–{TRIAL_PERIOD_MAX_DAYS}-day trial "
            f"and {len(REQUIRED_APPROVERS_ORG)}-person approval (CIO + Learning Coordinator). "
            f"Agent count ceiling: {MAX_ACTIVE_AGENTS}. "
            "Prefer routing improvements over structural changes whenever possible."
        ),
    )


def org_governance_summary() -> dict:
    """Return a concise governance summary for display."""
    proposals = load_org_proposals()
    observations = load_org_observations()

    by_status: dict[str, int] = {}
    for p in proposals:
        by_status[p.status] = by_status.get(p.status, 0) + 1

    actionable_obs = [o for o in observations if o.is_actionable]

    return {
        "total_proposals": len(proposals),
        "proposals_by_status": by_status,
        "actionable_observations": len(actionable_obs),
        "high_severity_observations": sum(
            1 for o in actionable_obs if o.severity == ObservationSeverity.HIGH.value
        ),
        "complexity_thresholds": {
            "max_active_agents": MAX_ACTIVE_AGENTS,
            "max_debate_size": MAX_DEBATE_SIZE,
            "redundancy_alert": REDUNDANCY_ALERT_THRESHOLD,
            "unnecessary_analysis_alert": UNNECESSARY_ANALYSIS_THRESHOLD,
            "report_bloat_threshold": REPORT_BLOAT_THRESHOLD,
        },
        "org_preferences": [
            "Modularity over monoliths",
            "Clarity over comprehensiveness",
            "Narrow specialization over broad coverage",
            "Coordinator routing over committee expansion",
            "Efficient debate over exhaustive debate",
        ],
        "disclaimer": DISCLAIMER,
    }
