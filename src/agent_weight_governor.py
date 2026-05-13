"""
Agent Weight Governor — Phase 3 Governance Redesign.

Conservative governance layer for agent influence weights.
Enforces the pre-downweight checklist before any weight reduction.
Weights affect CIO synthesis — they never silence an agent.

Core rules:
- Minimum weight 0.5 (agents are never silenced)
- Maximum weight 1.5
- Downweight is HARD to do; upweight is EASIER
- 6 pre-downweight questions must be answered before ANY reduction
- Cannot downweight on regime mismatch, being early, or single failed thesis
- Dual approval required (Learning Coordinator + CIO) for all downweights
Advisory only — no live trading.
"""

from __future__ import annotations
import json
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from pathlib import Path
from typing import Optional

ROOT_DIR = Path(__file__).parent.parent
WEIGHTS_PATH = ROOT_DIR / "data" / "processed" / "agent_weights.json"
WEIGHT_LOG_PATH = ROOT_DIR / "data" / "processed" / "agent_weight_log.json"

# Weight bounds
WEIGHT_MIN = 0.5       # Agents are never silenced — minimum floor
WEIGHT_MAX = 1.5       # Maximum influence amplifier
WEIGHT_DEFAULT = 1.0   # All agents start equal

# Governance thresholds
MIN_VOTES_FOR_DOWNWEIGHT = 20        # Must have at least 20 resolved votes
MIN_VOTES_FOR_UPWEIGHT = 15          # Easier to reward than punish
MIN_DAYS_TRACKING_FOR_DOWNWEIGHT = 90   # Must track for 90+ days before downweight
MIN_DAYS_TRACKING_FOR_UPWEIGHT = 60     # 60 days for upweight
MAX_SINGLE_ADJUSTMENT = 0.10        # Cannot move weight by more than 10% in one step
MIN_CONSECUTIVE_FAILURES_BEFORE_REVIEW = 5   # Fewer than 5 failures = not yet a pattern
REQUIRED_APPROVERS_DOWNWEIGHT = frozenset(["cio", "learning_coordinator"])
DISCLAIMER = "ADVISORY ONLY. All outputs are simulated. Not financial advice."


class WeightChangeDirection(str, Enum):
    INCREASE = "increase"
    DECREASE = "decrease"


class WeightChangeStatus(str, Enum):
    PROPOSED = "proposed"
    APPROVED = "approved"
    REJECTED = "rejected"
    WITHDRAWN = "withdrawn"


# ── Pre-downweight checklist ─────────────────────────────────────────────────

@dataclass
class PreDownweightChecklist:
    """
    Six mandatory questions that must be answered before any weight reduction.
    If the answers suggest the agent was early, regime-mismatched, or improving,
    downweight should be deferred.

    Returns a recommendation — the governor enforces the decision gate.
    """
    was_agent_wrong_not_early: bool
    # True = agent's thesis was fundamentally incorrect (not just poorly timed)
    # False = agent was directionally correct but early → BLOCK downweight

    was_regime_neutral_or_favorable: bool
    # True = the regime was not structurally hostile to this agent's style
    # False = regime was hostile → downweight based on this period is unfair → BLOCK

    was_sizing_adequate_not_primary_issue: bool
    # True = the problem was thesis quality, not position sizing
    # False = sizing was the primary error (addressable without downweight) → defer

    agent_did_not_identify_overlooked_risks: bool
    # True = agent provided no additional risk insight beyond other agents
    # False = agent identified risks others missed (value even when wrong) → BLOCK

    agent_showed_no_improvement_after_feedback: bool
    # True = agent has not adapted after feedback was given
    # False = agent has shown improvement trajectory → BLOCK downweight, track instead

    is_pattern_not_noise: bool
    # True = failure is systematic (N≥5 failures, multiple regimes, no improvement)
    # False = could be noise, single regime, or short run → BLOCK

    # Context fields (informational — not gates but required for transparency)
    n_failures_cited: int = 0
    n_total_votes: int = 0
    regime_context: str = ""
    evidence_notes: str = ""

    @property
    def all_gates_pass(self) -> bool:
        """Returns True only if ALL six questions justify a downweight."""
        return (
            self.was_agent_wrong_not_early
            and self.was_regime_neutral_or_favorable
            and self.was_sizing_adequate_not_primary_issue
            and self.agent_did_not_identify_overlooked_risks
            and self.agent_showed_no_improvement_after_feedback
            and self.is_pattern_not_noise
        )

    @property
    def blocking_reasons(self) -> list[str]:
        """List of specific reasons blocking the downweight."""
        reasons = []
        if not self.was_agent_wrong_not_early:
            reasons.append("Agent appears to have been EARLY rather than WRONG. Downweight is inappropriate — early calls have thesis value.")
        if not self.was_regime_neutral_or_favorable:
            reasons.append(f"Regime was hostile to this agent's style ({self.regime_context}). Underperformance may be structural, not a skill deficit.")
        if not self.was_sizing_adequate_not_primary_issue:
            reasons.append("Sizing appears to be the primary issue, not thesis quality. Address sizing discipline without reducing agent weight.")
        if not self.agent_did_not_identify_overlooked_risks:
            reasons.append("Agent identified risks others missed. This contribution has value independent of directional accuracy.")
        if not self.agent_showed_no_improvement_after_feedback:
            reasons.append("Agent has shown improvement after feedback. Downweight now would penalize learning — track adaptation instead.")
        if not self.is_pattern_not_noise:
            reasons.append(f"Pattern may be noise (N={self.n_failures_cited} failures cited). Require N≥{MIN_CONSECUTIVE_FAILURES_BEFORE_REVIEW} systematic failures across multiple regimes.")
        return reasons

    def to_dict(self) -> dict:
        return {
            "was_agent_wrong_not_early": self.was_agent_wrong_not_early,
            "was_regime_neutral_or_favorable": self.was_regime_neutral_or_favorable,
            "was_sizing_adequate_not_primary_issue": self.was_sizing_adequate_not_primary_issue,
            "agent_did_not_identify_overlooked_risks": self.agent_did_not_identify_overlooked_risks,
            "agent_showed_no_improvement_after_feedback": self.agent_showed_no_improvement_after_feedback,
            "is_pattern_not_noise": self.is_pattern_not_noise,
            "all_gates_pass": self.all_gates_pass,
            "blocking_reasons": self.blocking_reasons,
            "n_failures_cited": self.n_failures_cited,
            "n_total_votes": self.n_total_votes,
            "regime_context": self.regime_context,
            "evidence_notes": self.evidence_notes,
        }


# ── Weight change proposal ───────────────────────────────────────────────────

@dataclass
class WeightChangeProposal:
    id: str
    agent: str
    current_weight: float
    proposed_weight: float
    direction: str                          # WeightChangeDirection value
    proposed_by: str
    proposed_date: str
    rationale: str
    evidence_summary: str
    n_resolved_votes: int
    days_tracked: int

    # Gate checks (populated during validation)
    structural_gates_pass: bool = False     # Volume, time, and adjustment-size gates
    structural_gate_failures: list[str] = field(default_factory=list)

    # Pre-downweight checklist (only required for decreases)
    checklist: Optional[dict] = None

    # Approval tracking
    status: str = WeightChangeStatus.PROPOSED.value
    approval_records: list[dict] = field(default_factory=list)
    approved_date: Optional[str] = None
    rejection_reason: str = ""

    def to_dict(self) -> dict:
        return asdict(self)

    @property
    def approval_votes(self) -> dict[str, str]:
        return {r["reviewer"]: r["vote"] for r in self.approval_records}

    @property
    def is_fully_approved(self) -> bool:
        votes = self.approval_votes
        return all(votes.get(r) == "approve" for r in REQUIRED_APPROVERS_DOWNWEIGHT)

    @property
    def delta(self) -> float:
        return round(self.proposed_weight - self.current_weight, 4)


# ── Weight store ─────────────────────────────────────────────────────────────

def load_weights() -> dict[str, float]:
    """Load current agent weights. Returns default 1.0 for any missing agent."""
    if not WEIGHTS_PATH.exists():
        return {}
    with open(WEIGHTS_PATH) as f:
        return json.load(f)


def get_agent_weight(agent: str) -> float:
    weights = load_weights()
    return weights.get(agent, WEIGHT_DEFAULT)


def save_weights(weights: dict[str, float]) -> None:
    WEIGHTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(WEIGHTS_PATH, "w") as f:
        json.dump(weights, f, indent=2, default=str)


def get_all_weights() -> dict[str, float]:
    """Return weights for all 17 agents, defaulting to 1.0."""
    from vote_db import AGENTS
    stored = load_weights()
    return {agent: stored.get(agent, WEIGHT_DEFAULT) for agent in AGENTS}


# ── Proposal log ─────────────────────────────────────────────────────────────

def load_proposal_log() -> list[WeightChangeProposal]:
    if not WEIGHT_LOG_PATH.exists():
        return []
    with open(WEIGHT_LOG_PATH) as f:
        raw = json.load(f)
    proposals = []
    for d in raw:
        d.setdefault("structural_gates_pass", False)
        d.setdefault("structural_gate_failures", [])
        d.setdefault("checklist", None)
        d.setdefault("approval_records", [])
        d.setdefault("approved_date", None)
        d.setdefault("rejection_reason", "")
        proposals.append(WeightChangeProposal(**d))
    return proposals


def save_proposal_log(proposals: list[WeightChangeProposal]) -> None:
    WEIGHT_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(WEIGHT_LOG_PATH, "w") as f:
        json.dump([p.to_dict() for p in proposals], f, indent=2, default=str)


# ── Governance validation ────────────────────────────────────────────────────

def _validate_structural_gates(
    agent: str,
    current_weight: float,
    proposed_weight: float,
    direction: str,
    n_resolved_votes: int,
    days_tracked: int,
) -> tuple[bool, list[str]]:
    """
    Check the hard structural gates before any weight change.
    Returns (all_pass, list_of_failures).
    """
    failures = []

    # Weight bounds
    if proposed_weight < WEIGHT_MIN:
        failures.append(f"Proposed weight {proposed_weight} is below minimum {WEIGHT_MIN}. Agents cannot be silenced.")
    if proposed_weight > WEIGHT_MAX:
        failures.append(f"Proposed weight {proposed_weight} exceeds maximum {WEIGHT_MAX}.")

    # Maximum single adjustment
    delta = abs(proposed_weight - current_weight)
    if delta > MAX_SINGLE_ADJUSTMENT:
        failures.append(
            f"Single adjustment of {delta:.2f} exceeds maximum {MAX_SINGLE_ADJUSTMENT}. "
            "Reduce the adjustment size or stage it over multiple reviews."
        )

    # Volume and time gates (stricter for downweight)
    if direction == WeightChangeDirection.DECREASE.value:
        if n_resolved_votes < MIN_VOTES_FOR_DOWNWEIGHT:
            failures.append(
                f"Only {n_resolved_votes} resolved votes — require {MIN_VOTES_FOR_DOWNWEIGHT} before downweight. "
                "Insufficient track record for a negative assessment."
            )
        if days_tracked < MIN_DAYS_TRACKING_FOR_DOWNWEIGHT:
            failures.append(
                f"Only {days_tracked} days of tracking — require {MIN_DAYS_TRACKING_FOR_DOWNWEIGHT} before downweight. "
                "Short-term underperformance is not a pattern."
            )
    else:  # increase
        if n_resolved_votes < MIN_VOTES_FOR_UPWEIGHT:
            failures.append(
                f"Only {n_resolved_votes} resolved votes — require {MIN_VOTES_FOR_UPWEIGHT} before upweight."
            )
        if days_tracked < MIN_DAYS_TRACKING_FOR_UPWEIGHT:
            failures.append(
                f"Only {days_tracked} days of tracking — require {MIN_DAYS_TRACKING_FOR_UPWEIGHT} before upweight."
            )

    return len(failures) == 0, failures


def propose_weight_change(
    agent: str,
    proposed_weight: float,
    proposed_by: str,
    rationale: str,
    evidence_summary: str,
    n_resolved_votes: int,
    days_tracked: int,
    checklist: Optional[PreDownweightChecklist] = None,
) -> tuple[WeightChangeProposal, list[str]]:
    """
    Submit a weight change proposal.
    Returns (proposal, blocking_issues).
    blocking_issues is non-empty if the proposal cannot proceed.
    """
    current_weight = get_agent_weight(agent)
    direction = (
        WeightChangeDirection.DECREASE.value
        if proposed_weight < current_weight
        else WeightChangeDirection.INCREASE.value
    )

    # Structural gates
    struct_pass, struct_failures = _validate_structural_gates(
        agent, current_weight, proposed_weight, direction,
        n_resolved_votes, days_tracked,
    )

    blocking_issues = list(struct_failures)

    # For downweights: checklist is mandatory
    checklist_dict = None
    if direction == WeightChangeDirection.DECREASE.value:
        if checklist is None:
            blocking_issues.append(
                "Pre-downweight checklist is mandatory for all weight reductions. "
                "Submit a completed PreDownweightChecklist with this proposal."
            )
        else:
            checklist_dict = checklist.to_dict()
            if not checklist.all_gates_pass:
                blocking_issues.extend(checklist.blocking_reasons)

    proposal = WeightChangeProposal(
        id=f"WC-{agent.upper()[:6]}-{uuid.uuid4().hex[:6].upper()}",
        agent=agent,
        current_weight=current_weight,
        proposed_weight=proposed_weight,
        direction=direction,
        proposed_by=proposed_by,
        proposed_date=datetime.now().strftime("%Y-%m-%d"),
        rationale=rationale,
        evidence_summary=evidence_summary,
        n_resolved_votes=n_resolved_votes,
        days_tracked=days_tracked,
        structural_gates_pass=struct_pass,
        structural_gate_failures=struct_failures,
        checklist=checklist_dict,
        status=WeightChangeStatus.PROPOSED.value if not blocking_issues else WeightChangeStatus.REJECTED.value,
        rejection_reason="; ".join(blocking_issues) if blocking_issues else "",
    )

    if not blocking_issues:
        # Save to log for approval
        log = load_proposal_log()
        log.append(proposal)
        save_proposal_log(log)

    return proposal, blocking_issues


def record_weight_approval(
    proposal_id: str,
    reviewer: str,
    vote: str,
    notes: str = "",
) -> tuple[Optional[WeightChangeProposal], str]:
    """Record a vote on a weight change proposal."""
    if reviewer not in REQUIRED_APPROVERS_DOWNWEIGHT:
        return None, f"'{reviewer}' is not a required approver. Must be: {sorted(REQUIRED_APPROVERS_DOWNWEIGHT)}"

    log = load_proposal_log()
    proposal = next((p for p in log if p.id == proposal_id), None)
    if proposal is None:
        return None, f"Proposal '{proposal_id}' not found."

    if proposal.status != WeightChangeStatus.PROPOSED.value:
        return proposal, f"Proposal already in status '{proposal.status}'."

    vote_value = vote.lower()
    if vote_value not in ("approve", "reject", "abstain"):
        return None, f"Invalid vote '{vote}'. Must be: approve / reject / abstain"

    proposal.approval_records = [r for r in proposal.approval_records if r["reviewer"] != reviewer]
    proposal.approval_records.append({
        "reviewer": reviewer, "vote": vote_value,
        "notes": notes, "date": datetime.now().strftime("%Y-%m-%d"),
    })

    if proposal.is_fully_approved:
        proposal.status = WeightChangeStatus.APPROVED.value
        proposal.approved_date = datetime.now().strftime("%Y-%m-%d")
        # Apply weight change
        weights = load_weights()
        weights[proposal.agent] = round(proposal.proposed_weight, 4)
        save_weights(weights)
        msg = (
            f"✓ Weight change APPROVED: {proposal.agent} "
            f"{proposal.current_weight:.2f} → {proposal.proposed_weight:.2f}"
        )
    elif any(r["vote"] == "reject" for r in proposal.approval_records):
        rejector = next(r["reviewer"] for r in proposal.approval_records if r["vote"] == "reject")
        proposal.status = WeightChangeStatus.REJECTED.value
        proposal.rejection_reason = f"Rejected by {rejector}: {notes}"
        msg = f"✗ Weight change REJECTED by {rejector}."
    else:
        pending = [r for r in REQUIRED_APPROVERS_DOWNWEIGHT if r not in proposal.approval_votes]
        msg = f"Vote recorded. Pending: {', '.join(pending)}"

    save_proposal_log([p if p.id != proposal_id else proposal for p in log])
    return proposal, msg


# ── Weight summary ────────────────────────────────────────────────────────────

def weight_governance_summary() -> dict:
    """Return full summary of current agent weights and recent proposals."""
    weights = get_all_weights()
    log = load_proposal_log()

    non_default = {a: w for a, w in weights.items() if abs(w - WEIGHT_DEFAULT) > 0.001}
    elevated = {a: w for a, w in non_default.items() if w > WEIGHT_DEFAULT}
    reduced = {a: w for a, w in non_default.items() if w < WEIGHT_DEFAULT}

    pending = [p.to_dict() for p in log if p.status == WeightChangeStatus.PROPOSED.value]
    recent_approved = [
        p.to_dict() for p in sorted(log, key=lambda x: x.approved_date or "", reverse=True)
        if p.status == WeightChangeStatus.APPROVED.value
    ][:5]

    return {
        "all_weights": weights,
        "agents_at_default": len(weights) - len(non_default),
        "agents_elevated": elevated,
        "agents_reduced": reduced,
        "weight_range": {"min": WEIGHT_MIN, "max": WEIGHT_MAX, "default": WEIGHT_DEFAULT},
        "governance_thresholds": {
            "min_votes_downweight": MIN_VOTES_FOR_DOWNWEIGHT,
            "min_votes_upweight": MIN_VOTES_FOR_UPWEIGHT,
            "min_days_downweight": MIN_DAYS_TRACKING_FOR_DOWNWEIGHT,
            "min_days_upweight": MIN_DAYS_TRACKING_FOR_UPWEIGHT,
            "max_single_adjustment": MAX_SINGLE_ADJUSTMENT,
        },
        "pending_proposals": pending,
        "recent_approved_changes": recent_approved,
        "disclaimer": DISCLAIMER,
    }
