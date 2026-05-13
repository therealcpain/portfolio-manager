"""
Alternative Portfolio Engine — Phase 3 Governance Redesign.

Dynamic registry replacing hardcoded theme portfolios.
Proposal → Committee Review → Approval → Active Tracking → Retirement.

Key design principles:
- Portfolios emerge from differentiated worldviews, not preset themes
- Committee approval required (CIO + Learning + Risk — all three)
- Anti-bias validation prevents selection drift and tiny variations
- Conservative: understand WHY, not just THAT, portfolios outperform
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
REGISTRY_PATH = ROOT_DIR / "data" / "processed" / "alternative_portfolios" / "registry.json"
PROPOSALS_PATH = ROOT_DIR / "data" / "processed" / "alternative_portfolios" / "proposals.json"

# Governance constants
MAX_ACTIVE_PORTFOLIOS = 15
MAX_WEIGHT_OVERLAP_VS_CIO = 0.85        # reject if >85% overlap with main CIO
MAX_WEIGHT_OVERLAP_VS_EXISTING = 0.90   # reject if >90% overlap with any active alternative
MIN_THESIS_LENGTH = 50                  # characters
REQUIRED_APPROVERS = frozenset(["cio", "learning_coordinator", "risk_dissent_coordinator"])
OUTPERFORMANCE_REVIEW_DAYS = 90         # constitutional mandate: 90-day trigger
MIN_OBSERVATIONS_FOR_CONCLUSION = 10    # conservative learning: N<10 = tentative only

DISCLAIMER = "ADVISORY ONLY. All outputs are simulated. Not financial advice."


# ── Enums ──────────────────────────────────────────────────────────────────

class PortfolioCategory(str, Enum):
    REGIME = "regime"
    TACTICAL = "tactical"
    STRUCTURAL = "structural"
    CONCENTRATED_THESIS = "concentrated_thesis"
    CONTRARIAN = "contrarian"
    MACRO_DEFENSIVE = "macro_defensive"
    EXPERIMENTAL = "experimental"
    HYBRID = "hybrid"


class ProposalStatus(str, Enum):
    PROPOSED = "proposed"
    UNDER_REVIEW = "under_review"
    APPROVED = "approved"
    ACTIVE = "active"
    REJECTED = "rejected"
    RETIRED = "retired"


class ApprovalVote(str, Enum):
    APPROVE = "approve"
    REJECT = "reject"
    ABSTAIN = "abstain"


class Regime(str, Enum):
    BULL = "bull"
    BEAR = "bear"
    SIDEWAYS = "sideways"
    STAGFLATION = "stagflation"
    LIQUIDITY_CRISIS = "liquidity_crisis"
    RISK_OFF = "risk_off"
    REFLATION = "reflation"
    ANY = "any"


# ── Data structures ────────────────────────────────────────────────────────

@dataclass
class ApprovalRecord:
    reviewer: str
    vote: str          # ApprovalVote value
    notes: str
    date: str


@dataclass
class PortfolioProposal:
    """A proposed alternative portfolio undergoing committee review."""
    id: str
    name: str
    thesis: str
    differentiation: str        # How it differs from main CIO portfolio
    intended_regime: str        # Regime where this should outperform
    expected_failure_mode: str  # When/why it would underperform
    benchmark_relevance: str    # What benchmark question it answers
    why_deserves_tracking: str  # Justification for inclusion
    review_cadence: str         # "weekly" / "monthly" / "quarterly"
    category: str               # PortfolioCategory value
    weights: dict[str, float]   # ticker -> weight (must sum to 1.0 ± 0.01)
    proposed_by: str
    proposed_date: str
    retirement_criteria: str    # When to stop tracking
    status: str = ProposalStatus.PROPOSED.value
    approval_records: list[dict] = field(default_factory=list)
    approved_date: Optional[str] = None
    retired_date: Optional[str] = None
    retirement_reason: Optional[str] = None
    rejection_reason: Optional[str] = None
    performance_notes: str = ""

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "PortfolioProposal":
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})

    @property
    def approval_votes(self) -> dict[str, str]:
        return {r["reviewer"]: r["vote"] for r in self.approval_records}

    @property
    def is_fully_approved(self) -> bool:
        votes = self.approval_votes
        return all(
            votes.get(r) == ApprovalVote.APPROVE.value
            for r in REQUIRED_APPROVERS
        )

    @property
    def is_rejected(self) -> bool:
        votes = self.approval_votes
        return any(
            votes.get(r) == ApprovalVote.REJECT.value
            for r in REQUIRED_APPROVERS
        )

    def pending_approvers(self) -> list[str]:
        votes = self.approval_votes
        return [r for r in REQUIRED_APPROVERS if r not in votes]


# ── Anti-bias validation ───────────────────────────────────────────────────

def calculate_weight_overlap(weights_a: dict[str, float], weights_b: dict[str, float]) -> float:
    """
    Compute portfolio overlap as minimum weight sum across shared tickers.
    Returns 0.0 (no overlap) to 1.0 (identical).
    """
    shared = set(weights_a) & set(weights_b)
    return sum(min(weights_a[t], weights_b[t]) for t in shared)


def validate_proposal(
    proposal: PortfolioProposal,
    active_proposals: list[PortfolioProposal],
    main_cio_weights: Optional[dict[str, float]] = None,
) -> list[str]:
    """
    Validate a new proposal against anti-bias rules.
    Returns a list of issues (empty = valid).
    """
    issues: list[str] = []

    # 1. Weight integrity
    total_weight = sum(proposal.weights.values())
    if abs(total_weight - 1.0) > 0.01:
        issues.append(
            f"Weights sum to {total_weight:.4f} — must sum to 1.0 (±0.01)."
        )

    if not proposal.weights:
        issues.append("Portfolio has no weights defined.")

    # 2. Active portfolio cap
    active_count = sum(1 for p in active_proposals if p.status == ProposalStatus.ACTIVE.value)
    if active_count >= MAX_ACTIVE_PORTFOLIOS:
        issues.append(
            f"Maximum active portfolios ({MAX_ACTIVE_PORTFOLIOS}) reached. "
            "Retire an existing portfolio before adding a new one."
        )

    # 3. Similarity to main CIO portfolio
    if main_cio_weights and proposal.weights:
        cio_overlap = calculate_weight_overlap(proposal.weights, main_cio_weights)
        if cio_overlap > MAX_WEIGHT_OVERLAP_VS_CIO:
            issues.append(
                f"Portfolio is {cio_overlap:.0%} similar to main CIO — "
                f"must be below {MAX_WEIGHT_OVERLAP_VS_CIO:.0%} to represent a differentiated worldview."
            )

    # 4. Similarity to existing active alternatives
    for existing in active_proposals:
        if existing.status not in (ProposalStatus.ACTIVE.value, ProposalStatus.APPROVED.value):
            continue
        if existing.id == proposal.id:
            continue
        overlap = calculate_weight_overlap(proposal.weights, existing.weights)
        if overlap > MAX_WEIGHT_OVERLAP_VS_EXISTING:
            issues.append(
                f"Portfolio is {overlap:.0%} similar to existing '{existing.name}' "
                f"— must differ by more than {1 - MAX_WEIGHT_OVERLAP_VS_EXISTING:.0%}."
            )

    # 5. Required narrative fields
    if len(proposal.thesis) < MIN_THESIS_LENGTH:
        issues.append(
            f"Thesis too brief ({len(proposal.thesis)} chars). "
            f"Must be at least {MIN_THESIS_LENGTH} characters — explain the worldview."
        )

    if not proposal.differentiation.strip():
        issues.append("Differentiation field is required — explain how this differs from the main CIO portfolio.")

    if not proposal.expected_failure_mode.strip():
        issues.append("Expected failure mode is required — when would this portfolio underperform?")

    if not proposal.retirement_criteria.strip():
        issues.append("Retirement criteria is required — when should tracking stop?")

    # 6. Category must be valid
    valid_categories = {c.value for c in PortfolioCategory}
    if proposal.category not in valid_categories:
        issues.append(f"Category '{proposal.category}' is not valid. Must be one of: {sorted(valid_categories)}")

    # 7. Review cadence
    valid_cadences = {"weekly", "monthly", "quarterly"}
    if proposal.review_cadence not in valid_cadences:
        issues.append(f"Review cadence '{proposal.review_cadence}' invalid. Must be: {valid_cadences}")

    # 8. Liquidity check — warn on very illiquid assets (no hard block)
    illiquid_keywords = ["OTC", "illiquid", "private"]
    for ticker in proposal.weights:
        if any(kw.lower() in ticker.lower() for kw in illiquid_keywords):
            issues.append(f"Ticker '{ticker}' may be illiquid — verify it can be simulated with public price data.")

    return issues


# ── Registry I/O ───────────────────────────────────────────────────────────

def _ensure_dirs() -> None:
    REGISTRY_PATH.parent.mkdir(parents=True, exist_ok=True)


def load_registry() -> list[PortfolioProposal]:
    _ensure_dirs()
    if not REGISTRY_PATH.exists():
        return []
    with open(REGISTRY_PATH) as f:
        raw = json.load(f)
    return [PortfolioProposal.from_dict(d) for d in raw]


def save_registry(proposals: list[PortfolioProposal]) -> None:
    _ensure_dirs()
    with open(REGISTRY_PATH, "w") as f:
        json.dump([p.to_dict() for p in proposals], f, indent=2, default=str)


def get_active_portfolios() -> list[PortfolioProposal]:
    return [p for p in load_registry() if p.status == ProposalStatus.ACTIVE.value]


def get_portfolio_weights_map() -> dict[str, dict[str, float]]:
    """Return {name: weights} for all active alternative portfolios. Used by simulate_portfolios.py."""
    active = get_active_portfolios()
    return {p.name: p.weights for p in active}


# ── Proposal lifecycle ─────────────────────────────────────────────────────

def propose_portfolio(
    name: str,
    thesis: str,
    differentiation: str,
    intended_regime: str,
    expected_failure_mode: str,
    benchmark_relevance: str,
    why_deserves_tracking: str,
    review_cadence: str,
    category: str,
    weights: dict[str, float],
    proposed_by: str,
    retirement_criteria: str,
    main_cio_weights: Optional[dict[str, float]] = None,
) -> tuple[PortfolioProposal, list[str]]:
    """
    Submit a new portfolio proposal.
    Returns (proposal, validation_issues).
    If validation_issues is non-empty, the proposal is NOT saved — caller decides whether to force-save.
    """
    registry = load_registry()
    proposal = PortfolioProposal(
        id=f"ALT-{uuid.uuid4().hex[:8].upper()}",
        name=name,
        thesis=thesis,
        differentiation=differentiation,
        intended_regime=intended_regime,
        expected_failure_mode=expected_failure_mode,
        benchmark_relevance=benchmark_relevance,
        why_deserves_tracking=why_deserves_tracking,
        review_cadence=review_cadence,
        category=category,
        weights=weights,
        proposed_by=proposed_by,
        proposed_date=datetime.now().strftime("%Y-%m-%d"),
        retirement_criteria=retirement_criteria,
        status=ProposalStatus.PROPOSED.value,
    )

    issues = validate_proposal(proposal, registry, main_cio_weights)
    if not issues:
        proposal.status = ProposalStatus.UNDER_REVIEW.value
        registry.append(proposal)
        save_registry(registry)

    return proposal, issues


def record_approval_vote(
    proposal_id: str,
    reviewer: str,
    vote: str,
    notes: str = "",
) -> tuple[Optional[PortfolioProposal], str]:
    """
    Record a vote from one of the required approvers.
    Returns (updated_proposal, status_message).
    """
    if reviewer not in REQUIRED_APPROVERS:
        return None, f"'{reviewer}' is not a required approver. Must be one of: {sorted(REQUIRED_APPROVERS)}"

    vote_value = vote.lower()
    if vote_value not in {v.value for v in ApprovalVote}:
        return None, f"Invalid vote '{vote}'. Must be: approve / reject / abstain"

    registry = load_registry()
    proposal = next((p for p in registry if p.id == proposal_id), None)
    if proposal is None:
        return None, f"Proposal '{proposal_id}' not found."

    if proposal.status not in (ProposalStatus.PROPOSED.value, ProposalStatus.UNDER_REVIEW.value):
        return proposal, f"Proposal is already in status '{proposal.status}' — cannot vote."

    # Overwrite if reviewer already voted (allows changing vote before finalization)
    proposal.approval_records = [
        r for r in proposal.approval_records if r["reviewer"] != reviewer
    ]
    proposal.approval_records.append({
        "reviewer": reviewer,
        "vote": vote_value,
        "notes": notes,
        "date": datetime.now().strftime("%Y-%m-%d"),
    })
    proposal.status = ProposalStatus.UNDER_REVIEW.value

    # Check for final decision
    if proposal.is_fully_approved:
        proposal.status = ProposalStatus.ACTIVE.value
        proposal.approved_date = datetime.now().strftime("%Y-%m-%d")
        msg = f"✓ Portfolio '{proposal.name}' APPROVED and now ACTIVE."
    elif proposal.is_rejected:
        rejectors = [r["reviewer"] for r in proposal.approval_records if r["vote"] == ApprovalVote.REJECT.value]
        proposal.status = ProposalStatus.REJECTED.value
        proposal.rejection_reason = f"Rejected by: {', '.join(rejectors)}. Notes: {notes}"
        msg = f"✗ Portfolio '{proposal.name}' REJECTED by {', '.join(rejectors)}."
    else:
        pending = proposal.pending_approvers()
        msg = f"Vote recorded. Pending: {', '.join(pending)}"

    save_registry([p if p.id != proposal_id else proposal for p in registry])
    return proposal, msg


def retire_portfolio(
    proposal_id: str,
    retirement_reason: str,
) -> tuple[Optional[PortfolioProposal], str]:
    """Mark an active portfolio as retired."""
    registry = load_registry()
    proposal = next((p for p in registry if p.id == proposal_id), None)
    if proposal is None:
        return None, f"Portfolio '{proposal_id}' not found."

    if proposal.status != ProposalStatus.ACTIVE.value:
        return proposal, f"Portfolio status is '{proposal.status}' — only active portfolios can be retired."

    proposal.status = ProposalStatus.RETIRED.value
    proposal.retired_date = datetime.now().strftime("%Y-%m-%d")
    proposal.retirement_reason = retirement_reason

    save_registry([p if p.id != proposal_id else proposal for p in registry])
    return proposal, f"Portfolio '{proposal.name}' retired: {retirement_reason}"


# ── Governance summary ─────────────────────────────────────────────────────

def governance_summary() -> dict:
    """Return a summary of the current portfolio governance state."""
    registry = load_registry()

    by_status: dict[str, list[str]] = {}
    for p in registry:
        by_status.setdefault(p.status, []).append(p.name)

    active = [p for p in registry if p.status == ProposalStatus.ACTIVE.value]
    under_review = [p for p in registry if p.status == ProposalStatus.UNDER_REVIEW.value]

    category_breakdown: dict[str, int] = {}
    for p in active:
        category_breakdown[p.category] = category_breakdown.get(p.category, 0) + 1

    return {
        "total_in_registry": len(registry),
        "active": len(active),
        "under_review": len(under_review),
        "capacity_remaining": MAX_ACTIVE_PORTFOLIOS - len(active),
        "by_status": by_status,
        "active_by_category": category_breakdown,
        "active_portfolios": [
            {
                "id": p.id,
                "name": p.name,
                "category": p.category,
                "intended_regime": p.intended_regime,
                "review_cadence": p.review_cadence,
                "approved_date": p.approved_date,
                "tickers": list(p.weights.keys()),
            }
            for p in active
        ],
        "pending_votes": [
            {
                "id": p.id,
                "name": p.name,
                "pending_approvers": p.pending_approvers(),
            }
            for p in under_review
        ],
        "disclaimer": DISCLAIMER,
    }


# ── Seed loader (one-time migration from legacy YAML files) ──────────────

LEGACY_SEED_PORTFOLIOS: list[dict] = [
    {
        "name": "Aggressive Scarcity",
        "thesis": (
            "Concentrated bet that monetary debasement accelerates and scarce hard assets "
            "dramatically outperform financial assets over a 3–5 year horizon. BTC proxy via MSTR "
            "dominates; gold and uranium provide diversification within the scarcity theme."
        ),
        "differentiation": (
            "Eliminates all broad equity exposure. Concentrates exclusively in scarcity assets. "
            "Main CIO holds 35% broad equity (SPY+QQQ); this holds 0%."
        ),
        "intended_regime": Regime.REFLATION.value,
        "expected_failure_mode": "Underperforms severely in deflationary bust, liquidity crisis, or BTC regulatory shock.",
        "benchmark_relevance": "Tests whether pure scarcity concentration beats diversified scarcity + equity.",
        "why_deserves_tracking": "Represents the maximum-conviction scarcity worldview. Important to know if diversification into equity is additive or dilutive.",
        "review_cadence": "monthly",
        "category": PortfolioCategory.CONCENTRATED_THESIS.value,
        "weights": {"MSTR": 0.30, "GLD": 0.25, "URNM": 0.20, "IBIT": 0.15, "XLE": 0.10},
        "proposed_by": "system_seed",
        "retirement_criteria": "If BTC scarcity thesis is invalidated OR if 3-year returns trail main CIO by >20%.",
    },
    {
        "name": "Macro Defensive",
        "thesis": (
            "Risk-off positioning anticipating macro deterioration: credit tightening, recession, "
            "or stagflation. Maximizes defensive reserve (STRC proxy), gold monetary hedge, and "
            "silver. Minimal equity. Tests the cost of being early/wrong on defense."
        ),
        "differentiation": (
            "Inverts the CIO equity allocation. Main CIO is 35% equity; this is 10% equity with "
            "40% STRC cash proxy and 40% precious metals."
        ),
        "intended_regime": Regime.BEAR.value,
        "expected_failure_mode": "Badly underperforms in sustained bull market. Significant opportunity cost vs STRC in sideways markets.",
        "benchmark_relevance": "Answers: what is the cost of full defensiveness vs staying invested?",
        "why_deserves_tracking": "Quantifies the true cost of being defensively positioned. Essential for risk-adjusted decision-making during macro deterioration signals.",
        "review_cadence": "monthly",
        "category": PortfolioCategory.MACRO_DEFENSIVE.value,
        "weights": {"STRC_PROXY": 0.40, "GLD": 0.30, "SLV": 0.10, "TLT": 0.10, "SPY": 0.10},
        "proposed_by": "system_seed",
        "retirement_criteria": "If macro regime is firmly bull for 12+ months with no recession signal.",
    },
    {
        "name": "Momentum Heavy",
        "thesis": (
            "Trend-following with momentum bias. Overweights recent relative strength leaders "
            "and underweights laggards. Assumes momentum persists. Tests whether a momentum tilt "
            "beats the CIO's thesis-based approach."
        ),
        "differentiation": "Weight assignment driven by trailing performance, not thesis conviction.",
        "intended_regime": Regime.BULL.value,
        "expected_failure_mode": "Momentum reversal (mean reversion after extended trend). Typically suffers most at trend inflection points.",
        "benchmark_relevance": "Tests whether momentum factor beats conviction-based allocation.",
        "why_deserves_tracking": "Provides the purest test of momentum factor vs thesis-driven investing. If momentum consistently wins, it challenges the conviction-based CIO model.",
        "review_cadence": "monthly",
        "category": PortfolioCategory.TACTICAL.value,
        "weights": {"QQQ": 0.35, "MSTR": 0.20, "GLD": 0.20, "SPY": 0.15, "STRC_PROXY": 0.10},
        "proposed_by": "system_seed",
        "retirement_criteria": "If momentum factor consistently underperforms CIO over 18+ months.",
    },
    {
        "name": "Contrarian Sentiment",
        "thesis": (
            "Buys assets at maximum fear with thesis still intact. Overweights STRC as dry powder "
            "to deploy at sentiment extremes. Contrarian to crowd positioning — enters when others exit. "
            "Tests patience and conviction during drawdowns."
        ),
        "differentiation": "Holds 60% STRC (vs CIO 30%) waiting for fear-driven entry points. Very low equity until sentiment reaches extreme fear.",
        "intended_regime": Regime.RISK_OFF.value,
        "expected_failure_mode": "Market never reaches extreme fear; STRC drag grows unbearable. Or fear signals trigger but thesis is actually invalidating.",
        "benchmark_relevance": "Tests value of waiting vs staying invested. Contrarian timing vs conviction holding.",
        "why_deserves_tracking": "Explores the behavioral edge of patience — does waiting for fear extremes generate durable alpha? Directly challenges the always-invested CIO approach.",
        "review_cadence": "quarterly",
        "category": PortfolioCategory.CONTRARIAN.value,
        "weights": {"STRC_PROXY": 0.60, "GLD": 0.20, "URNM": 0.20},
        "proposed_by": "system_seed",
        "retirement_criteria": "If fear-driven entries fail to generate alpha over 24 months.",
    },
    {
        "name": "AI Structural Change",
        "thesis": (
            "Concentrated bet on AI infrastructure as the picks-and-shovels trade of the decade. "
            "Thesis: compute, power, and semiconductor scarcity are the binding constraints on AI "
            "growth. Overweights semiconductor ETF, datacenter power, and AI hardware. "
            "Avoids pure software AI (abundance risk)."
        ),
        "differentiation": "No gold, no BTC proxy, no uranium. Pure technology structural change play. Opposite of scarcity thesis.",
        "intended_regime": Regime.BULL.value,
        "expected_failure_mode": "AI hype cycle bust, compute commoditization, regulatory intervention in large tech.",
        "benchmark_relevance": "Tests technology structural change vs scarcity thesis as primary driver.",
        "why_deserves_tracking": "The CIO thesis is scarcity-first. This challenges it directly with a technology-abundance worldview. If AI structural change outperforms scarcity, the CIO framework needs revision.",
        "review_cadence": "monthly",
        "category": PortfolioCategory.STRUCTURAL.value,
        "weights": {"QQQ": 0.30, "NVDA": 0.20, "SMH": 0.20, "NEE": 0.10, "MSFT": 0.10, "STRC_PROXY": 0.10},
        "proposed_by": "system_seed",
        "retirement_criteria": "If AI infrastructure thesis invalidated or if QQQ consistently substitutes for it.",
    },
]


def seed_registry_from_legacy(main_cio_weights: Optional[dict[str, float]] = None) -> list[str]:
    """
    One-time migration of legacy hardcoded portfolios into the registry.
    Auto-approves all seed portfolios (bypasses committee — legacy only).
    Returns list of names added.
    """
    existing = load_registry()
    existing_names = {p.name for p in existing}
    added = []

    for seed in LEGACY_SEED_PORTFOLIOS:
        if seed["name"] in existing_names:
            continue

        proposal = PortfolioProposal(
            id=f"ALT-SEED-{seed['name'].upper().replace(' ', '-')[:12]}",
            name=seed["name"],
            thesis=seed["thesis"],
            differentiation=seed["differentiation"],
            intended_regime=seed["intended_regime"],
            expected_failure_mode=seed["expected_failure_mode"],
            benchmark_relevance=seed["benchmark_relevance"],
            why_deserves_tracking=seed["why_deserves_tracking"],
            review_cadence=seed["review_cadence"],
            category=seed["category"],
            weights=seed["weights"],
            proposed_by=seed["proposed_by"],
            proposed_date="2026-05-13",
            retirement_criteria=seed["retirement_criteria"],
            status=ProposalStatus.ACTIVE.value,
            approval_records=[
                {"reviewer": r, "vote": ApprovalVote.APPROVE.value, "notes": "Seed portfolio — auto-approved at system initialization.", "date": "2026-05-13"}
                for r in REQUIRED_APPROVERS
            ],
            approved_date="2026-05-13",
        )
        existing.append(proposal)
        added.append(seed["name"])

    if added:
        save_registry(existing)

    return added
