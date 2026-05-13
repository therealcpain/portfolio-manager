"""
Agent Learning Engine — Phase 3 Governance Redesign.

Regime-aware performance attribution for all 17 agents.
Conservative by design: understand HOW agents fail before drawing conclusions.

Core principles:
- "Wrong" and "Early" are different failure modes with different remedies
- Regime fit is required context for any performance evaluation
- Risk discovery has value independent of directional accuracy
- Adaptation trajectory matters as much as current hit rate
- N<15 per regime = tentative; N<5 = insufficient (do not conclude)
Advisory only — no live trading.
"""

from __future__ import annotations
import json
from dataclasses import asdict, dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Optional

ROOT_DIR = Path(__file__).parent.parent
LEARNING_DB_PATH = ROOT_DIR / "data" / "processed" / "agent_learning.json"
ADAPTATION_LOG_PATH = ROOT_DIR / "data" / "processed" / "agent_adaptations.json"

MIN_REGIME_OBSERVATIONS = 5    # fewer = "insufficient"
TENTATIVE_REGIME_OBSERVATIONS = 15  # fewer than this = "tentative"
DISCLAIMER = "ADVISORY ONLY. All outputs are simulated. Not financial advice."


# ── Market regimes ──────────────────────────────────────────────────────────

class MarketRegime(str, Enum):
    LIQUIDITY_EXPANSION = "liquidity_expansion"   # QE, rate cuts, risk-on credit
    LIQUIDITY_TIGHTENING = "liquidity_tightening" # QT, rate hikes, credit stress
    BUBBLE = "bubble"                              # Euphoria, extended valuations
    PANIC = "panic"                                # Fear extreme, VIX spike, liquidity pull
    TRENDLESS = "trendless"                        # Sideways, range-bound, no trend
    REFLATION = "reflation"                        # Growth + moderate inflation
    STAGFLATION = "stagflation"                    # High inflation + weak growth
    UNKNOWN = "unknown"                            # Regime not yet classified


# ── Failure mode taxonomy ───────────────────────────────────────────────────

class FailureMode(str, Enum):
    WRONG_THESIS = "wrong_thesis"               # Core thesis premise was incorrect
    EARLY = "early"                              # Correct thesis, wrong timing
    REGIME_MISMATCH = "regime_mismatch"         # Agent style not suited to this regime
    SIZING_ERROR = "sizing_error"               # Direction correct, position too large/small
    THESIS_DRIFT = "thesis_drift"               # Held thesis past its invalidation
    INSUFFICIENT_DATA = "insufficient_data"     # Not enough data to evaluate
    UNCLEAR = "unclear"                          # Cannot determine from available evidence


# ── Adaptation types ────────────────────────────────────────────────────────

class AdaptationType(str, Enum):
    METHODOLOGY_EVOLUTION = "methodology_evolution"     # Agent's analytical framework improved
    THESIS_REFINEMENT = "thesis_refinement"             # More precise thesis construction
    TIMING_IMPROVEMENT = "timing_improvement"           # Better entry/exit identification
    RISK_FRAMING = "risk_framing"                       # Improved downside case articulation
    INVALIDATION_LOGIC = "invalidation_logic"           # Sharper invalidation conditions
    REGIME_AWARENESS = "regime_awareness"               # Better regime-conditional positioning
    CONFIDENCE_CALIBRATION = "confidence_calibration"  # Stated confidence matches actual accuracy


# ── Agent learning data structures ─────────────────────────────────────────

@dataclass
class RegimeVoteRecord:
    """A single resolved vote annotated with its regime context."""
    rec_id: str
    agent: str
    asset: str
    date: str
    regime: str                  # MarketRegime value
    vote: str                    # Agree / Disagree / Abstain
    confidence: int
    outcome: str                 # Correct / Incorrect / Partial
    return_pct: float
    benchmark_return_pct: float
    alpha_pct: float
    failure_mode: str            # FailureMode value (if incorrect)
    was_early: bool              # Correct thesis but wrong timing
    regime_was_hostile: bool     # Regime structurally opposed to agent's style
    identified_key_risks: bool   # Agent surfaced risks others missed (value independent of outcome)
    notes: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class AgentRegimeProfile:
    """Performance profile for one agent in one regime."""
    agent: str
    regime: str
    n_votes: int
    n_correct: int
    n_incorrect: int
    n_early: int                          # correct direction, wrong timing
    n_regime_hostile: int                 # regime worked against agent's style
    n_risk_discoveries: int               # times agent identified overlooked risks
    hit_rate_pct: float
    avg_alpha_pct: float
    avg_confidence: float
    confidence_calibration_error: float   # abs(stated confidence - actual hit rate)
    characteristic_strength: str          # qualitative: what this agent does well here
    characteristic_weakness: str          # qualitative: what this agent struggles with here
    data_quality: str                     # "conclusive" / "tentative" / "insufficient"
    note: str = ""

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def empty(cls, agent: str, regime: str) -> "AgentRegimeProfile":
        return cls(
            agent=agent, regime=regime,
            n_votes=0, n_correct=0, n_incorrect=0,
            n_early=0, n_regime_hostile=0, n_risk_discoveries=0,
            hit_rate_pct=0.0, avg_alpha_pct=0.0, avg_confidence=0.0,
            confidence_calibration_error=0.0,
            characteristic_strength="Insufficient data",
            characteristic_weakness="Insufficient data",
            data_quality="insufficient",
        )


@dataclass
class AgentAdaptationRecord:
    """Evidence of an agent improving its reasoning or approach."""
    id: str
    agent: str
    date: str
    adaptation_type: str          # AdaptationType value
    description: str              # What specifically changed
    triggered_by: str             # What prompted this adaptation
    prior_failure_mode: str       # What failure mode this addresses
    outcome_tracked: bool         # Are we measuring if this worked?
    outcome_notes: str = ""       # Follow-up notes after observing impact

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class AgentLearningProfile:
    """Full learning profile for a single agent across all regimes."""
    agent: str
    total_resolved_votes: int
    regime_profiles: dict[str, dict]        # regime -> AgentRegimeProfile.to_dict()
    adaptation_records: list[dict]          # list of AdaptationRecord.to_dict()
    overall_hit_rate_pct: float
    regime_best_fit: str                    # which regime this agent excels in
    regime_worst_fit: str                   # which regime this agent struggles in
    is_early_not_wrong_tendency: bool       # agent tends to be early, not wrong
    consistent_risk_discovery: bool         # agent reliably surfaces overlooked risks
    adaptation_trajectory: str             # "improving" / "stable" / "declining" / "unknown"
    last_updated: str

    def to_dict(self) -> dict:
        return {
            "agent": self.agent,
            "total_resolved_votes": self.total_resolved_votes,
            "regime_profiles": self.regime_profiles,
            "adaptation_records": self.adaptation_records,
            "overall_hit_rate_pct": self.overall_hit_rate_pct,
            "regime_best_fit": self.regime_best_fit,
            "regime_worst_fit": self.regime_worst_fit,
            "is_early_not_wrong_tendency": self.is_early_not_wrong_tendency,
            "consistent_risk_discovery": self.consistent_risk_discovery,
            "adaptation_trajectory": self.adaptation_trajectory,
            "last_updated": self.last_updated,
        }


# ── Regime classification ────────────────────────────────────────────────────

def classify_regime_from_context(
    spy_return_20d: Optional[float] = None,
    vix_level: Optional[float] = None,
    fed_rate_direction: Optional[str] = None,   # "hiking" / "cutting" / "hold"
    credit_spread_bps: Optional[float] = None,
    inflation_regime: Optional[str] = None,      # "high" / "moderate" / "low"
    growth_regime: Optional[str] = None,         # "expanding" / "contracting" / "stagnant"
) -> MarketRegime:
    """
    Classify the current market regime from available context signals.
    Designed to be called with whatever data is available — all args optional.
    Returns UNKNOWN if insufficient context.
    """
    signals: list[str] = []

    if spy_return_20d is not None:
        if spy_return_20d > 0.08:
            signals.append("strong_rally")
        elif spy_return_20d < -0.08:
            signals.append("strong_selloff")

    if vix_level is not None:
        if vix_level > 35:
            signals.append("panic_vix")
        elif vix_level < 15:
            signals.append("complacency")

    if fed_rate_direction is not None:
        if fed_rate_direction == "hiking":
            signals.append("tightening")
        elif fed_rate_direction == "cutting":
            signals.append("easing")

    if credit_spread_bps is not None:
        if credit_spread_bps > 600:
            signals.append("credit_stress")
        elif credit_spread_bps < 200:
            signals.append("credit_calm")

    if inflation_regime is not None and growth_regime is not None:
        if inflation_regime == "high" and growth_regime == "contracting":
            return MarketRegime.STAGFLATION
        if inflation_regime in ("moderate", "high") and growth_regime == "expanding":
            return MarketRegime.REFLATION

    # Panic: VIX spike + selloff (or credit stress + selloff)
    if "panic_vix" in signals and "strong_selloff" in signals:
        return MarketRegime.PANIC
    if "credit_stress" in signals and "strong_selloff" in signals:
        return MarketRegime.PANIC

    # Liquidity tightening: Fed hiking + credit stress or selloff
    if "tightening" in signals:
        return MarketRegime.LIQUIDITY_TIGHTENING

    # Liquidity expansion: Fed cutting + rally
    if "easing" in signals:
        return MarketRegime.LIQUIDITY_EXPANSION

    # Bubble: strong rally + complacency
    if "strong_rally" in signals and "complacency" in signals:
        return MarketRegime.BUBBLE

    # Trendless: no strong directional signals
    if not signals or all(s in ("complacency", "credit_calm") for s in signals):
        return MarketRegime.TRENDLESS

    return MarketRegime.UNKNOWN


# ── Profile computation ──────────────────────────────────────────────────────

def compute_regime_profile(
    agent: str,
    regime: str,
    votes: list[RegimeVoteRecord],
) -> AgentRegimeProfile:
    """Compute regime performance profile for one agent in one regime."""
    if not votes:
        return AgentRegimeProfile.empty(agent, regime)

    n = len(votes)
    n_correct = sum(1 for v in votes if v.outcome == "Correct")
    n_incorrect = sum(1 for v in votes if v.outcome == "Incorrect")
    n_early = sum(1 for v in votes if v.was_early)
    n_hostile = sum(1 for v in votes if v.regime_was_hostile)
    n_risk_disc = sum(1 for v in votes if v.identified_key_risks)

    hit_rate = (n_correct / n * 100) if n > 0 else 0.0
    avg_alpha = sum(v.alpha_pct for v in votes) / n if n > 0 else 0.0
    avg_conf = sum(v.confidence for v in votes) / n if n > 0 else 0.0
    conf_error = abs(avg_conf - hit_rate)

    if n < MIN_REGIME_OBSERVATIONS:
        data_quality = "insufficient"
        note = f"Only {n} observations in this regime — do not draw conclusions."
    elif n < TENTATIVE_REGIME_OBSERVATIONS:
        data_quality = "tentative"
        note = f"{n} observations — signals are tentative. Require {TENTATIVE_REGIME_OBSERVATIONS} for conclusions."
    else:
        data_quality = "conclusive"
        note = ""

    # Characteristic strengths/weaknesses
    strength = _infer_strength(agent, regime, hit_rate, n_early, n_risk_disc, n)
    weakness = _infer_weakness(agent, regime, hit_rate, n_early, n_hostile, n_incorrect, n)

    return AgentRegimeProfile(
        agent=agent,
        regime=regime,
        n_votes=n,
        n_correct=n_correct,
        n_incorrect=n_incorrect,
        n_early=n_early,
        n_regime_hostile=n_hostile,
        n_risk_discoveries=n_risk_disc,
        hit_rate_pct=round(hit_rate, 2),
        avg_alpha_pct=round(avg_alpha, 4),
        avg_confidence=round(avg_conf, 1),
        confidence_calibration_error=round(conf_error, 2),
        characteristic_strength=strength,
        characteristic_weakness=weakness,
        data_quality=data_quality,
        note=note,
    )


def _infer_strength(agent: str, regime: str, hit_rate: float, n_early: int, n_risk_disc: int, n: int) -> str:
    if n < MIN_REGIME_OBSERVATIONS:
        return "Insufficient data"
    parts = []
    if hit_rate >= 70:
        parts.append(f"High directional accuracy ({hit_rate:.0f}%)")
    if n_risk_disc >= max(1, n * 0.4):
        parts.append("Reliable risk discovery")
    if n_early >= max(1, n * 0.3) and hit_rate >= 55:
        parts.append("Often early — thesis quality high despite timing")
    return "; ".join(parts) if parts else "No distinctive strength identified yet"


def _infer_weakness(agent: str, regime: str, hit_rate: float, n_early: int, n_hostile: int, n_incorrect: int, n: int) -> str:
    if n < MIN_REGIME_OBSERVATIONS:
        return "Insufficient data"
    parts = []
    if hit_rate < 40 and n_hostile < n * 0.3:
        parts.append(f"Low accuracy ({hit_rate:.0f}%) not explained by regime hostility")
    if n_hostile >= n * 0.4:
        parts.append(f"Regime structurally hostile ({n_hostile}/{n} votes) — poor environment for this style")
    if n_incorrect > 0 and n_early < n_incorrect * 0.5:
        parts.append("Incorrect calls not attributable to timing — thesis quality concern")
    return "; ".join(parts) if parts else "No distinctive weakness identified yet"


def compute_adaptation_trajectory(adaptation_records: list[AgentAdaptationRecord]) -> str:
    """
    Assess whether an agent's adaptation record shows improving, stable, or declining trajectory.
    Very conservative: returns "unknown" for N<3 adaptations.
    """
    if len(adaptation_records) < 3:
        return "unknown"

    # Recent adaptations (last 3) vs older ones
    recent = adaptation_records[-3:]
    has_outcome_tracked = any(r.outcome_tracked for r in recent)
    has_positive_outcomes = any(
        r.outcome_tracked and "improve" in r.outcome_notes.lower()
        for r in recent
        if r.outcome_notes
    )

    if not has_outcome_tracked:
        return "unknown"
    if has_positive_outcomes:
        return "improving"
    return "stable"


# ── Full learning profile builder ────────────────────────────────────────────

def build_agent_learning_profile(
    agent: str,
    all_votes: list[RegimeVoteRecord],
    adaptation_records: list[AgentAdaptationRecord],
) -> AgentLearningProfile:
    """Build a complete learning profile for one agent from all vote history."""
    n_total = len(all_votes)
    n_correct = sum(1 for v in all_votes if v.outcome == "Correct")
    overall_hit_rate = (n_correct / n_total * 100) if n_total > 0 else 0.0

    # Group votes by regime
    by_regime: dict[str, list[RegimeVoteRecord]] = {}
    for v in all_votes:
        by_regime.setdefault(v.regime, []).append(v)

    # Compute per-regime profiles
    regime_profiles: dict[str, dict] = {}
    for regime, votes in by_regime.items():
        profile = compute_regime_profile(agent, regime, votes)
        regime_profiles[regime] = profile.to_dict()

    # Best/worst regime fit (only from regimes with conclusive data)
    conclusive = {
        r: p for r, p in regime_profiles.items()
        if p["data_quality"] == "conclusive"
    }
    if conclusive:
        best_regime = max(conclusive, key=lambda r: conclusive[r]["hit_rate_pct"])
        worst_regime = min(conclusive, key=lambda r: conclusive[r]["hit_rate_pct"])
    else:
        best_regime = "insufficient_data"
        worst_regime = "insufficient_data"

    # Early-not-wrong tendency: >30% of incorrect calls were actually early
    total_incorrect = sum(1 for v in all_votes if v.outcome == "Incorrect")
    n_early = sum(1 for v in all_votes if v.was_early)
    is_early_tendency = (n_early / total_incorrect > 0.3) if total_incorrect > 0 else False

    # Consistent risk discovery: >25% of all votes surfaced overlooked risks
    n_risk_disc = sum(1 for v in all_votes if v.identified_key_risks)
    consistent_risk_disc = (n_risk_disc / n_total > 0.25) if n_total > 0 else False

    trajectory = compute_adaptation_trajectory(adaptation_records)

    return AgentLearningProfile(
        agent=agent,
        total_resolved_votes=n_total,
        regime_profiles=regime_profiles,
        adaptation_records=[r.to_dict() for r in adaptation_records],
        overall_hit_rate_pct=round(overall_hit_rate, 2),
        regime_best_fit=best_regime,
        regime_worst_fit=worst_regime,
        is_early_not_wrong_tendency=is_early_tendency,
        consistent_risk_discovery=consistent_risk_disc,
        adaptation_trajectory=trajectory,
        last_updated=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    )


# ── Persistence ──────────────────────────────────────────────────────────────

def load_learning_db() -> dict[str, dict]:
    """Load full agent learning database. Returns {agent: profile_dict}."""
    if not LEARNING_DB_PATH.exists():
        return {}
    with open(LEARNING_DB_PATH) as f:
        return json.load(f)


def save_learning_db(profiles: dict[str, AgentLearningProfile]) -> None:
    LEARNING_DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(LEARNING_DB_PATH, "w") as f:
        json.dump({a: p.to_dict() for a, p in profiles.items()}, f, indent=2, default=str)


def load_adaptation_log() -> dict[str, list[dict]]:
    """Load adaptation records. Returns {agent: [record_dict]}."""
    if not ADAPTATION_LOG_PATH.exists():
        return {}
    with open(ADAPTATION_LOG_PATH) as f:
        return json.load(f)


def record_adaptation(
    agent: str,
    adaptation_type: str,
    description: str,
    triggered_by: str,
    prior_failure_mode: str,
) -> AgentAdaptationRecord:
    """Record an observed agent adaptation."""
    record = AgentAdaptationRecord(
        id=f"ADAPT-{agent.upper()[:6]}-{datetime.now().strftime('%Y%m%d%H%M%S')}",
        agent=agent,
        date=datetime.now().strftime("%Y-%m-%d"),
        adaptation_type=adaptation_type,
        description=description,
        triggered_by=triggered_by,
        prior_failure_mode=prior_failure_mode,
        outcome_tracked=False,
    )
    log = load_adaptation_log()
    log.setdefault(agent, []).append(record.to_dict())
    ADAPTATION_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(ADAPTATION_LOG_PATH, "w") as f:
        json.dump(log, f, indent=2, default=str)
    return record


def record_regime_vote(vote: RegimeVoteRecord) -> None:
    """Append a resolved regime-annotated vote to the learning database."""
    db = load_learning_db()
    agent_data = db.get(vote.agent, {"votes": []})
    agent_data.setdefault("votes", []).append(vote.to_dict())
    db[vote.agent] = agent_data
    LEARNING_DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(LEARNING_DB_PATH, "w") as f:
        json.dump(db, f, indent=2, default=str)


# ── Regime performance report ────────────────────────────────────────────────

@dataclass
class RegimeAttributionReport:
    generated_at: str
    current_regime: str
    agents_analyzed: int
    regime_leaders: dict[str, list[str]]   # regime -> [top 3 agents]
    regime_laggards: dict[str, list[str]]  # regime -> [bottom 3 agents]
    agent_profiles: dict[str, dict]        # agent -> profile summary
    early_not_wrong_agents: list[str]
    consistent_risk_discoverers: list[str]
    improving_agents: list[str]
    data_quality_warnings: list[str]       # agents with insufficient data
    conservative_learning_note: str


def generate_regime_attribution_report(
    votes_by_agent: dict[str, list[RegimeVoteRecord]],
    adaptations_by_agent: dict[str, list[AgentAdaptationRecord]],
    current_regime: str = MarketRegime.UNKNOWN.value,
) -> RegimeAttributionReport:
    """Generate a full regime-aware attribution report across all agents."""
    profiles: dict[str, AgentLearningProfile] = {}

    for agent, votes in votes_by_agent.items():
        adaptations = adaptations_by_agent.get(agent, [])
        profiles[agent] = build_agent_learning_profile(agent, votes, adaptations)

    # Regime leaders: best hit rate per regime (conclusive data only)
    all_regimes = {v.regime for vlist in votes_by_agent.values() for v in vlist}
    regime_leaders: dict[str, list[str]] = {}
    regime_laggards: dict[str, list[str]] = {}

    for regime in all_regimes:
        regime_data = []
        for agent, profile in profiles.items():
            rp = profile.regime_profiles.get(regime, {})
            if rp.get("data_quality") == "conclusive":
                regime_data.append((agent, rp["hit_rate_pct"]))

        if regime_data:
            sorted_agents = sorted(regime_data, key=lambda x: x[1], reverse=True)
            regime_leaders[regime] = [a for a, _ in sorted_agents[:3]]
            regime_laggards[regime] = [a for a, _ in sorted_agents[-3:]]

    early_agents = [a for a, p in profiles.items() if p.is_early_not_wrong_tendency]
    risk_discoverers = [a for a, p in profiles.items() if p.consistent_risk_discovery]
    improving = [a for a, p in profiles.items() if p.adaptation_trajectory == "improving"]

    data_warnings = [
        f"{a}: insufficient regime data (total votes: {p.total_resolved_votes})"
        for a, p in profiles.items()
        if p.total_resolved_votes < MIN_REGIME_OBSERVATIONS
    ]

    return RegimeAttributionReport(
        generated_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        current_regime=current_regime,
        agents_analyzed=len(profiles),
        regime_leaders=regime_leaders,
        regime_laggards=regime_laggards,
        agent_profiles={a: p.to_dict() for a, p in profiles.items()},
        early_not_wrong_agents=early_agents,
        consistent_risk_discoverers=risk_discoverers,
        improving_agents=improving,
        data_quality_warnings=data_warnings,
        conservative_learning_note=(
            f"Regime profiles require N≥{TENTATIVE_REGIME_OBSERVATIONS} for conclusions. "
            f"N<{TENTATIVE_REGIME_OBSERVATIONS} = tentative. "
            f"N<{MIN_REGIME_OBSERVATIONS} = insufficient — do not use for decisions. "
            "Early calls and risk discoveries are tracked independently of hit rate."
        ),
    )
