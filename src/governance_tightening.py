"""
governance_tightening.py — Final governance layer.

Implements:
  - 6-state sentiment taxonomy (not binary contrarian)
  - Regime persistence awareness (don't fade trends prematurely)
  - Gradual deallocation policy during euphoria
  - Dissent health monitoring (groupthink detection)
  - Human investor challenge framework
  - Meta-Agent periodic self-audit authority
  - Final governing principle: adaptive long-term compounding through
    disciplined evolutionary decision-making
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


# ---------------------------------------------------------------------------
# 1. Sentiment taxonomy
# ---------------------------------------------------------------------------

class SentimentState(str, Enum):
    PANIC = "panic"
    EXHAUSTION = "exhaustion"
    HEALTHY_SKEPTICISM = "healthy_skepticism"
    DISBELIEF_RALLY = "disbelief_rally"
    EUPHORIC_MELT_UP = "euphoric_melt_up"
    NARRATIVE_SATURATION = "narrative_saturation"


# Contrarian signal strength by state: positive = bullish lean, negative = bearish lean
# "healthy_skepticism" is NEUTRAL — no contrarian trade warranted
CONTRARIAN_SIGNAL = {
    SentimentState.PANIC: +1,                # strong buy signal
    SentimentState.EXHAUSTION: +0.5,         # mild accumulate
    SentimentState.HEALTHY_SKEPTICISM: 0,    # no signal — wall of worry
    SentimentState.DISBELIEF_RALLY: +0.3,    # stay long, don't fade
    SentimentState.EUPHORIC_MELT_UP: -0.5,   # trim gradually
    SentimentState.NARRATIVE_SATURATION: -1, # reduce exposure
}


def classify_sentiment_state(
    *,
    fear_greed_index: Optional[float] = None,   # 0–100 (0=extreme fear, 100=extreme greed)
    put_call_ratio: Optional[float] = None,      # >1.2 = panic, <0.7 = greed
    price_momentum_20d: Optional[float] = None, # % return over 20 trading days
    survey_bull_pct: Optional[float] = None,    # 0–100 AAII or similar bull %
    media_coverage_intensity: Optional[str] = None,  # "low"/"moderate"/"high"/"extreme"
    retail_inflow_spike: bool = False,
    short_interest_decline: bool = False,
    analyst_upgrade_wave: bool = False,
) -> tuple[SentimentState, str]:
    """
    Return (SentimentState, rationale).

    Distinguishes six states to prevent blind contrarian mistakes.
    """
    greed = fear_greed_index or 50.0
    pc = put_call_ratio or 1.0
    mom = price_momentum_20d or 0.0
    bull = survey_bull_pct or 50.0
    coverage = media_coverage_intensity or "moderate"

    # --- PANIC ---
    if (
        greed <= 20
        or pc >= 1.3
        or (bull <= 20 and mom <= -0.10)
    ):
        return (
            SentimentState.PANIC,
            "Extreme fear signals (FGI≤20 or P/C≥1.3 or heavy capitulation). "
            "Contrarian lean: cautious accumulation.",
        )

    # --- EUPHORIC MELT-UP ---
    if (
        greed >= 85
        and mom >= 0.15
        and (retail_inflow_spike or analyst_upgrade_wave or coverage == "extreme")
    ):
        return (
            SentimentState.EUPHORIC_MELT_UP,
            "Extreme greed + strong momentum + mass participation. "
            "Policy: trim gradually, do not exit all at once.",
        )

    # --- NARRATIVE SATURATION ---
    if (
        greed >= 75
        and coverage in ("high", "extreme")
        and analyst_upgrade_wave
        and short_interest_decline
    ):
        return (
            SentimentState.NARRATIVE_SATURATION,
            "Crowded consensus: upgrades + low shorts + heavy coverage. "
            "Narrative is fully priced in. Reduce exposure.",
        )

    # --- EXHAUSTION ---
    if (
        greed <= 35
        and bull <= 35
        and mom <= -0.05
        and pc >= 1.0
    ):
        return (
            SentimentState.EXHAUSTION,
            "Widespread pessimism but not panic-level. "
            "Mild accumulation bias — sellers losing conviction.",
        )

    # --- DISBELIEF RALLY ---
    if mom >= 0.08 and greed <= 55 and bull <= 45:
        return (
            SentimentState.DISBELIEF_RALLY,
            "Price rising while sentiment remains skeptical. "
            "Classic 'wall of worry' rally — do not fade the trend.",
        )

    # --- HEALTHY SKEPTICISM (default) ---
    return (
        SentimentState.HEALTHY_SKEPTICISM,
        "Balanced sentiment — neither extreme fear nor greed. "
        "No contrarian signal; follow thesis and regime.",
    )


# ---------------------------------------------------------------------------
# 2. Regime persistence awareness
# ---------------------------------------------------------------------------

# Minimum days before a trend is considered "confirmed ended" by default.
# These are constitutional guardrails — not absolute overrides.
REGIME_PERSISTENCE_MINIMUMS: dict[str, int] = {
    "bubble": 365,            # bubbles persist far longer than expected
    "ai_narrative": 730,      # AI adoption cycles span years
    "scarcity_thesis": 730,   # scarcity overshoots are multi-year
    "momentum": 90,           # trend continuation bias minimum
    "credit_cycle": 180,      # credit regimes are sticky
    "rate_cycle": 270,        # central bank regimes persist
    "general": 60,            # default for any unclassified regime
}


@dataclass
class RegimePersistenceCheck:
    regime_label: str
    regime_start_date: str          # ISO date string
    current_date: str               # ISO date string
    days_elapsed: int
    minimum_persistence_days: int
    fade_signal_present: bool
    confirmation_signals: list[str]
    verdict: str                    # "too_early_to_fade" | "confirmed_end" | "monitor"
    rationale: str

    @property
    def all_gates_pass(self) -> bool:
        return self.verdict == "confirmed_end"


def check_regime_persistence(
    regime_label: str,
    regime_start_date: str,
    current_date: str,
    days_elapsed: int,
    fade_signal_present: bool,
    confirmation_signals: Optional[list[str]] = None,
) -> RegimePersistenceCheck:
    """
    Gate: is it too early to fade this regime?

    Returns a RegimePersistenceCheck. If verdict == "too_early_to_fade",
    any deallocation proposal should be blocked or heavily trimmed.
    """
    confirmation_signals = confirmation_signals or []

    key = regime_label.lower().replace(" ", "_")
    minimum = REGIME_PERSISTENCE_MINIMUMS.get(key, REGIME_PERSISTENCE_MINIMUMS["general"])

    too_early = days_elapsed < minimum
    confirmed_end = (
        not too_early
        and fade_signal_present
        and len(confirmation_signals) >= 2
    )

    if confirmed_end:
        verdict = "confirmed_end"
        rationale = (
            f"Regime has persisted {days_elapsed}d (minimum {minimum}d), "
            f"fade signal present, and {len(confirmation_signals)} confirmation(s) received."
        )
    elif fade_signal_present and not too_early and len(confirmation_signals) < 2:
        verdict = "monitor"
        rationale = (
            f"Regime has persisted {days_elapsed}d. Fade signal present but only "
            f"{len(confirmation_signals)} confirmation signal(s) — need ≥2 before acting."
        )
    elif too_early:
        verdict = "too_early_to_fade"
        rationale = (
            f"Only {days_elapsed}d elapsed; minimum for '{regime_label}' is {minimum}d. "
            "Do not fade prematurely. Regime persistence bias applies."
        )
    else:
        verdict = "monitor"
        rationale = f"No fade signal detected. Continue monitoring regime '{regime_label}'."

    return RegimePersistenceCheck(
        regime_label=regime_label,
        regime_start_date=regime_start_date,
        current_date=current_date,
        days_elapsed=days_elapsed,
        minimum_persistence_days=minimum,
        fade_signal_present=fade_signal_present,
        confirmation_signals=confirmation_signals,
        verdict=verdict,
        rationale=rationale,
    )


# ---------------------------------------------------------------------------
# 3. Gradual deallocation policy
# ---------------------------------------------------------------------------

MAX_TRIM_PER_STEP_PCT = 20        # never reduce by more than 20% of current exposure in one step
MIN_REMAINING_EXPOSURE_PCT = 10   # always preserve some upside; never exit all
EUPHORIC_TRIM_TRIGGER_FGI = 80    # FGI threshold that activates gradual trim policy


@dataclass
class DeallocationStep:
    step_number: int
    current_exposure_pct: float
    trim_amount_pct: float
    remaining_exposure_pct: float
    trigger: str
    sentiment_state: str
    rationale: str


@dataclass
class GradualDeallocationPolicy:
    position_id: str
    ticker: str
    initial_exposure_pct: float
    target_exposure_pct: float        # the floor — not zero
    sentiment_state: SentimentState
    regime_persistence_check: Optional[RegimePersistenceCheck]
    steps: list[DeallocationStep]
    blocked: bool
    blocked_reason: str
    final_exposure_pct: float


def build_gradual_deallocation(
    position_id: str,
    ticker: str,
    current_exposure_pct: float,
    desired_reduction_pct: float,     # how much to reduce total (e.g., 40 means go from 60% → 20%)
    sentiment_state: SentimentState,
    regime_persistence_check: Optional[RegimePersistenceCheck] = None,
    n_steps: int = 3,
) -> GradualDeallocationPolicy:
    """
    Build a multi-step gradual deallocation plan.

    Rules:
    - Never trim more than MAX_TRIM_PER_STEP_PCT of current exposure in one step
    - Always preserve at least MIN_REMAINING_EXPOSURE_PCT
    - If regime persistence check says too_early_to_fade, block the deallocation
    - If sentiment is not euphoric/saturated, allow but add caution note
    """
    # Block if regime says too early
    if regime_persistence_check and regime_persistence_check.verdict == "too_early_to_fade":
        return GradualDeallocationPolicy(
            position_id=position_id,
            ticker=ticker,
            initial_exposure_pct=current_exposure_pct,
            target_exposure_pct=current_exposure_pct,
            sentiment_state=sentiment_state,
            regime_persistence_check=regime_persistence_check,
            steps=[],
            blocked=True,
            blocked_reason=(
                f"Regime persistence check: {regime_persistence_check.rationale}"
            ),
            final_exposure_pct=current_exposure_pct,
        )

    # Hard floor: can never go below MIN_REMAINING_EXPOSURE_PCT
    target = max(
        MIN_REMAINING_EXPOSURE_PCT,
        current_exposure_pct - desired_reduction_pct,
    )

    steps: list[DeallocationStep] = []
    exposure = current_exposure_pct
    total_to_trim = exposure - target
    per_step = total_to_trim / max(n_steps, 1)

    for i in range(1, n_steps + 1):
        max_trim = exposure * (MAX_TRIM_PER_STEP_PCT / 100)
        trim = min(per_step, max_trim)
        trim = max(trim, 0.0)
        new_exposure = max(exposure - trim, target)
        actual_trim = exposure - new_exposure

        if actual_trim <= 0:
            break

        rationale = (
            f"Step {i}/{n_steps}: trim {actual_trim:.1f}% of exposure. "
            f"Sentiment: {sentiment_state.value}. "
            "Preserving upside participation — no full exit."
        )

        steps.append(DeallocationStep(
            step_number=i,
            current_exposure_pct=round(exposure, 2),
            trim_amount_pct=round(actual_trim, 2),
            remaining_exposure_pct=round(new_exposure, 2),
            trigger=f"euphoria_trim_step_{i}",
            sentiment_state=sentiment_state.value,
            rationale=rationale,
        ))
        exposure = new_exposure

    return GradualDeallocationPolicy(
        position_id=position_id,
        ticker=ticker,
        initial_exposure_pct=current_exposure_pct,
        target_exposure_pct=target,
        sentiment_state=sentiment_state,
        regime_persistence_check=regime_persistence_check,
        steps=steps,
        blocked=False,
        blocked_reason="",
        final_exposure_pct=round(exposure, 2),
    )


# ---------------------------------------------------------------------------
# 4. Dissent health monitoring
# ---------------------------------------------------------------------------

GROUPTHINK_CONSENSUS_THRESHOLD = 0.85   # >85% agreement = groupthink alert
MINIMUM_DISSENT_VOICES = 2              # healthy debate needs ≥2 dissenting views


@dataclass
class DissentHealthReport:
    session_id: str
    total_votes: int
    majority_position: str
    majority_pct: float
    dissent_count: int
    dissenting_agents: list[str]
    groupthink_alert: bool
    groupthink_reason: str
    dissent_suppressed: bool     # True if dissent count < MINIMUM_DISSENT_VOICES
    recommendations: list[str]


def evaluate_dissent_health(
    session_id: str,
    votes: list[dict],           # [{"agent": str, "vote": str, "confidence": int}]
    topic: str = "",
) -> DissentHealthReport:
    """
    Evaluate whether a session shows unhealthy consensus.

    votes: list of {"agent": str, "vote": str}
    """
    if not votes:
        return DissentHealthReport(
            session_id=session_id,
            total_votes=0,
            majority_position="",
            majority_pct=0.0,
            dissent_count=0,
            dissenting_agents=[],
            groupthink_alert=False,
            groupthink_reason="No votes recorded.",
            dissent_suppressed=False,
            recommendations=["Ensure agents are voting before evaluating dissent health."],
        )

    from collections import Counter
    vote_counts: Counter = Counter(v["vote"] for v in votes)
    total = len(votes)
    majority_pos, majority_n = vote_counts.most_common(1)[0]
    majority_pct = majority_n / total

    dissenting = [v["agent"] for v in votes if v["vote"] != majority_pos]
    dissent_count = len(dissenting)

    groupthink_alert = majority_pct > GROUPTHINK_CONSENSUS_THRESHOLD
    groupthink_reason = ""
    if groupthink_alert:
        groupthink_reason = (
            f"{majority_pct:.0%} of agents voted '{majority_pos}'. "
            f"Threshold is {GROUPTHINK_CONSENSUS_THRESHOLD:.0%}. "
            "Premature consensus detected — dissenting voices should be solicited."
        )

    dissent_suppressed = dissent_count < MINIMUM_DISSENT_VOICES

    recommendations: list[str] = []
    if groupthink_alert:
        recommendations.append(
            "Explicitly solicit dissenting analysis before finalizing position."
        )
    if dissent_suppressed:
        recommendations.append(
            f"Only {dissent_count} dissenting voice(s). "
            f"Minimum is {MINIMUM_DISSENT_VOICES}. "
            "Consider routing to Devil's Advocate or Risk & Dissent Coordinator."
        )
    if not groupthink_alert and not dissent_suppressed:
        recommendations.append("Dissent health is adequate for this session.")

    return DissentHealthReport(
        session_id=session_id,
        total_votes=total,
        majority_position=majority_pos,
        majority_pct=majority_pct,
        dissent_count=dissent_count,
        dissenting_agents=dissenting,
        groupthink_alert=groupthink_alert,
        groupthink_reason=groupthink_reason,
        dissent_suppressed=dissent_suppressed,
        recommendations=recommendations,
    )


# ---------------------------------------------------------------------------
# 5. Human investor challenge framework
# ---------------------------------------------------------------------------

class BiasFlag(str, Enum):
    EMOTIONAL_ATTACHMENT = "emotional_attachment"
    CONFIRMATION_BIAS = "confirmation_bias"
    INCONSISTENCY = "inconsistency"
    WORLDVIEW_DIVERGENCE = "worldview_divergence"
    OVERCONFIDENCE = "overconfidence"
    RECENCY_BIAS = "recency_bias"


@dataclass
class InvestorChallenge:
    id: str
    date: str
    bias_flag: BiasFlag
    ticker: Optional[str]
    observation: str          # specific fact-based observation
    challenge_question: str   # respectful question to the investor
    severity: str             # "low" | "medium" | "high"
    evidence: list[str]


@dataclass
class HumanChallengeReport:
    date: str
    challenges: list[InvestorChallenge]
    worldview_divergences: list[str]
    emotional_attachment_warnings: list[str]
    confirmation_bias_alerts: list[str]
    inconsistency_flags: list[str]
    high_severity_count: int
    summary: str


def generate_human_challenge_report(
    date: str,
    position_history: list[dict],     # [{"ticker", "held_days", "return_pct", "thesis_state", "notes"}]
    recent_votes: list[dict],          # [{"ticker", "agent", "vote", "confidence", "rationale"}]
    current_theses: list[dict],        # [{"ticker", "lifecycle_state", "confidence", "invalidation_conditions"}]
) -> HumanChallengeReport:
    """
    Generate daily investor challenge report.

    Scans for:
    - Emotional attachment: held too long despite weakness
    - Confirmation bias: only bullish votes being accepted
    - Inconsistency: position size doesn't match stated conviction
    - Worldview divergence: committee disagrees with investor's view
    """
    challenges: list[InvestorChallenge] = []
    worldview_divergences: list[str] = []
    emotional_attachment_warnings: list[str] = []
    confirmation_bias_alerts: list[str] = []
    inconsistency_flags: list[str] = []

    # Check for emotional attachment (held through invalidation signals)
    for pos in position_history:
        if pos.get("thesis_state") in ("Breakdown Risk", "Invalidated") and pos.get("held_days", 0) > 30:
            c = InvestorChallenge(
                id=f"CHG-{uuid.uuid4().hex[:6].upper()}",
                date=date,
                bias_flag=BiasFlag.EMOTIONAL_ATTACHMENT,
                ticker=pos.get("ticker"),
                observation=(
                    f"{pos['ticker']} has been in '{pos['thesis_state']}' state "
                    f"for {pos['held_days']} days."
                ),
                challenge_question=(
                    f"What specific new evidence has emerged that justifies holding "
                    f"{pos['ticker']} beyond the original invalidation conditions?"
                ),
                severity="high" if pos["held_days"] > 60 else "medium",
                evidence=[
                    f"Thesis state: {pos['thesis_state']}",
                    f"Days held past warning state: {pos['held_days']}",
                ],
            )
            challenges.append(c)
            emotional_attachment_warnings.append(
                f"{pos['ticker']}: held {pos['held_days']}d in {pos['thesis_state']} state"
            )

    # Check for confirmation bias in recent votes
    from collections import defaultdict
    ticker_votes: dict[str, list[str]] = defaultdict(list)
    for v in recent_votes:
        ticker_votes[v["ticker"]].append(v["vote"])

    for ticker, vote_list in ticker_votes.items():
        bullish = sum(1 for v in vote_list if v in ("buy", "strong_buy", "accumulate", "bullish"))
        total = len(vote_list)
        if total >= 3 and bullish / total >= 0.90:
            c = InvestorChallenge(
                id=f"CHG-{uuid.uuid4().hex[:6].upper()}",
                date=date,
                bias_flag=BiasFlag.CONFIRMATION_BIAS,
                ticker=ticker,
                observation=(
                    f"{bullish}/{total} recent votes on {ticker} are bullish "
                    f"({bullish/total:.0%})."
                ),
                challenge_question=(
                    f"Have we adequately stress-tested the bearish case for {ticker}? "
                    "What would cause us to be wrong?"
                ),
                severity="medium",
                evidence=[f"Vote distribution: {bullish} bullish / {total - bullish} other"],
            )
            challenges.append(c)
            confirmation_bias_alerts.append(
                f"{ticker}: {bullish/total:.0%} bullish vote rate"
            )

    # Check for worldview divergence (thesis at High Conviction but committee neutral/bearish)
    for thesis in current_theses:
        ticker = thesis["ticker"]
        thesis_confidence = thesis.get("confidence", 50)
        ticker_recent = [v for v in recent_votes if v["ticker"] == ticker]
        if not ticker_recent:
            continue
        avg_confidence = sum(v.get("confidence", 50) for v in ticker_recent) / len(ticker_recent)
        if thesis_confidence >= 75 and avg_confidence <= 50:
            divergence = (
                f"{ticker}: investor confidence {thesis_confidence}% vs "
                f"committee avg {avg_confidence:.0f}%"
            )
            worldview_divergences.append(divergence)
            c = InvestorChallenge(
                id=f"CHG-{uuid.uuid4().hex[:6].upper()}",
                date=date,
                bias_flag=BiasFlag.WORLDVIEW_DIVERGENCE,
                ticker=ticker,
                observation=divergence,
                challenge_question=(
                    f"The committee's average confidence on {ticker} is {avg_confidence:.0f}% "
                    f"vs your {thesis_confidence}% conviction. "
                    "What do you know that the committee is missing?"
                ),
                severity="medium",
                evidence=[
                    f"Investor confidence: {thesis_confidence}%",
                    f"Committee avg: {avg_confidence:.0f}%",
                ],
            )
            challenges.append(c)

    high_count = sum(1 for c in challenges if c.severity == "high")

    if not challenges:
        summary = "No significant behavioral biases detected today. Decision-making appears disciplined."
    else:
        parts = []
        if emotional_attachment_warnings:
            parts.append(f"{len(emotional_attachment_warnings)} emotional attachment warning(s)")
        if confirmation_bias_alerts:
            parts.append(f"{len(confirmation_bias_alerts)} confirmation bias alert(s)")
        if worldview_divergences:
            parts.append(f"{len(worldview_divergences)} worldview divergence(s)")
        summary = "Investor challenge report: " + "; ".join(parts) + "."

    return HumanChallengeReport(
        date=date,
        challenges=challenges,
        worldview_divergences=worldview_divergences,
        emotional_attachment_warnings=emotional_attachment_warnings,
        confirmation_bias_alerts=confirmation_bias_alerts,
        inconsistency_flags=inconsistency_flags,
        high_severity_count=high_count,
        summary=summary,
    )


# ---------------------------------------------------------------------------
# 6. Meta-Agent audit (periodic organizational self-challenge)
# ---------------------------------------------------------------------------

@dataclass
class PhilosophyChallenge:
    id: str
    category: str            # "org_structure" | "core_worldview" | "recurring_assumption" | "rigidity"
    challenge: str           # the uncomfortable question
    evidence: list[str]      # supporting observations
    severity: str            # "low" | "medium" | "high" | "critical"
    recommended_action: str


@dataclass
class MetaAgentAudit:
    audit_id: str
    date: str
    trigger: str                       # "scheduled_monthly" | "manual" | "performance_threshold"
    org_challenges: list[PhilosophyChallenge]
    worldview_challenges: list[PhilosophyChallenge]
    assumption_challenges: list[PhilosophyChallenge]
    rigidity_flags: list[PhilosophyChallenge]
    ideology_lock_detected: bool
    ideology_lock_evidence: list[str]
    final_governing_principle: str
    meta_confidence_score: int         # 0–100: how confident the org is in its own philosophy
    summary: str

    @property
    def total_challenges(self) -> int:
        return (
            len(self.org_challenges)
            + len(self.worldview_challenges)
            + len(self.assumption_challenges)
            + len(self.rigidity_flags)
        )

    @property
    def critical_count(self) -> int:
        all_ch = (
            self.org_challenges
            + self.worldview_challenges
            + self.assumption_challenges
            + self.rigidity_flags
        )
        return sum(1 for c in all_ch if c.severity == "critical")


FINAL_GOVERNING_PRINCIPLE = (
    "The goal is not maximum activity, perfect prediction, or intellectual sophistication. "
    "The goal is: adaptive long-term compounding through disciplined evolutionary "
    "decision-making."
)

# Ideology lock detection: if scarcity thesis goes unchallenged too long
SCARCITY_CHALLENGE_INTERVAL_DAYS = 30
AI_NARRATIVE_CHALLENGE_INTERVAL_DAYS = 45
CORE_WORLDVIEW_CHALLENGE_INTERVAL_DAYS = 60


def run_meta_agent_audit(
    date: str,
    trigger: str,
    days_since_scarcity_challenged: int,
    days_since_worldview_challenged: int,
    days_since_ai_narrative_challenged: int,
    scarcity_thesis_unchanged_pct: float,   # % of sessions where scarcity not questioned
    agent_count: int,
    active_alternative_portfolios: int,
    recent_pip_count: int,                  # process improvement proposals in last 90 days
    org_hit_rate: float,                    # overall directional accuracy 0–1
    dissent_health_scores: list[float],     # recent dissent health (0–1)
    meta_confidence_override: Optional[int] = None,
) -> MetaAgentAudit:
    """
    Periodic Meta-Agent self-audit.

    The Meta-Agent has authority to challenge the organization itself.
    It does NOT have authority to change allocations — only to force discussion.
    """
    audit_id = f"META-{uuid.uuid4().hex[:8].upper()}"
    org_challenges: list[PhilosophyChallenge] = []
    worldview_challenges: list[PhilosophyChallenge] = []
    assumption_challenges: list[PhilosophyChallenge] = []
    rigidity_flags: list[PhilosophyChallenge] = []
    ideology_lock_evidence: list[str] = []

    # Org structure challenges
    if agent_count > 18:
        org_challenges.append(PhilosophyChallenge(
            id=f"ORG-{uuid.uuid4().hex[:6].upper()}",
            category="org_structure",
            challenge=(
                f"We now have {agent_count} active agents. "
                "Does each agent add non-redundant value, or are we building complexity for its own sake?"
            ),
            evidence=[f"Agent count: {agent_count} (ceiling: 20)"],
            severity="medium" if agent_count <= 20 else "high",
            recommended_action="Run full redundancy audit. Merge or retire agents that overlap >50%.",
        ))

    if active_alternative_portfolios > 5:
        org_challenges.append(PhilosophyChallenge(
            id=f"ORG-{uuid.uuid4().hex[:6].upper()}",
            category="org_structure",
            challenge=(
                f"We are tracking {active_alternative_portfolios} alternative portfolios simultaneously. "
                "Is this genuine intellectual exploration, or selection bias accumulation?"
            ),
            evidence=[f"Active alternatives: {active_alternative_portfolios}"],
            severity="medium",
            recommended_action="Review each alternative for selection bias. Retire any without clear regime rationale.",
        ))

    # Worldview challenges — scarcity thesis
    if days_since_scarcity_challenged > SCARCITY_CHALLENGE_INTERVAL_DAYS:
        worldview_challenges.append(PhilosophyChallenge(
            id=f"WV-{uuid.uuid4().hex[:6].upper()}",
            category="core_worldview",
            challenge=(
                f"The scarcity thesis has not been formally challenged in "
                f"{days_since_scarcity_challenged} days. "
                "What specific market development would prove scarcity to be wrong?"
            ),
            evidence=[
                f"Days since scarcity challenged: {days_since_scarcity_challenged}",
                f"Challenge interval: {SCARCITY_CHALLENGE_INTERVAL_DAYS} days",
            ],
            severity="high" if days_since_scarcity_challenged > 60 else "medium",
            recommended_action="Schedule formal scarcity thesis review. Require the Macro Strategist to argue the abundance case.",
        ))
        ideology_lock_evidence.append(
            f"Scarcity thesis unchallenged for {days_since_scarcity_challenged}d"
        )

    if scarcity_thesis_unchanged_pct > 0.80:
        worldview_challenges.append(PhilosophyChallenge(
            id=f"WV-{uuid.uuid4().hex[:6].upper()}",
            category="core_worldview",
            challenge=(
                f"In {scarcity_thesis_unchanged_pct:.0%} of recent sessions, "
                "the scarcity thesis was accepted without question. "
                "Are we testing it or just confirming it?"
            ),
            evidence=[f"Sessions without scarcity challenge: {scarcity_thesis_unchanged_pct:.0%}"],
            severity="high",
            recommended_action="Mandate minimum one scarcity challenge per week. Track challenge-to-acceptance ratio.",
        ))
        ideology_lock_evidence.append(
            f"Scarcity accepted without challenge in {scarcity_thesis_unchanged_pct:.0%} of sessions"
        )

    # AI narrative staleness
    if days_since_ai_narrative_challenged > AI_NARRATIVE_CHALLENGE_INTERVAL_DAYS:
        worldview_challenges.append(PhilosophyChallenge(
            id=f"WV-{uuid.uuid4().hex[:6].upper()}",
            category="core_worldview",
            challenge=(
                f"AI narrative thesis last challenged {days_since_ai_narrative_challenged} days ago. "
                "Has the investment case evolved, or are we anchored to the original framing?"
            ),
            evidence=[f"Days since AI narrative challenged: {days_since_ai_narrative_challenged}"],
            severity="medium",
            recommended_action="Require Tech & AI Specialist to formally update the AI thesis with current evidence.",
        ))

    # Core worldview staleness
    if days_since_worldview_challenged > CORE_WORLDVIEW_CHALLENGE_INTERVAL_DAYS:
        worldview_challenges.append(PhilosophyChallenge(
            id=f"WV-{uuid.uuid4().hex[:6].upper()}",
            category="core_worldview",
            challenge=(
                f"Core investment worldview has not been formally reviewed in "
                f"{days_since_worldview_challenged} days. "
                "Are our foundational beliefs still supported by evidence?"
            ),
            evidence=[f"Days since worldview reviewed: {days_since_worldview_challenged}"],
            severity="high" if days_since_worldview_challenged > 90 else "medium",
            recommended_action="Convene full committee worldview review. CIO must defend core positions.",
        ))

    # Assumption challenges — low hit rate
    if org_hit_rate < 0.50 and org_hit_rate > 0:
        assumption_challenges.append(PhilosophyChallenge(
            id=f"ASS-{uuid.uuid4().hex[:6].upper()}",
            category="recurring_assumption",
            challenge=(
                f"Organizational directional accuracy is {org_hit_rate:.0%}. "
                "Which specific assumptions are driving repeated errors?"
            ),
            evidence=[f"Hit rate: {org_hit_rate:.0%} (below 50% threshold)"],
            severity="critical" if org_hit_rate < 0.40 else "high",
            recommended_action=(
                "Run failure mode analysis. Identify top 3 recurring wrong assumptions "
                "and propose specific changes."
            ),
        ))

    # Rigidity flags — low process improvement activity
    if recent_pip_count == 0:
        rigidity_flags.append(PhilosophyChallenge(
            id=f"RIG-{uuid.uuid4().hex[:6].upper()}",
            category="rigidity",
            challenge=(
                "No process improvement proposals have been submitted in the last 90 days. "
                "Is the organization learning, or is it calcifying?"
            ),
            evidence=["PIP count (90 days): 0"],
            severity="medium",
            recommended_action="Require Learning Coordinator to produce minimum 1 PIP per quarter.",
        ))

    # Rigidity flag — poor dissent health trend
    if dissent_health_scores:
        avg_dissent = sum(dissent_health_scores) / len(dissent_health_scores)
        if avg_dissent < 0.40:
            rigidity_flags.append(PhilosophyChallenge(
                id=f"RIG-{uuid.uuid4().hex[:6].upper()}",
                category="rigidity",
                challenge=(
                    f"Average dissent health score is {avg_dissent:.0%} over recent sessions. "
                    "The organization is not generating adequate competing worldviews."
                ),
                evidence=[
                    f"Avg dissent health: {avg_dissent:.0%}",
                    f"Sessions analyzed: {len(dissent_health_scores)}",
                ],
                severity="high",
                recommended_action=(
                    "Mandate Devil's Advocate participation in all High Conviction decisions. "
                    "Track and publish dissent rate in monthly learning report."
                ),
            ))

    ideology_lock_detected = len(ideology_lock_evidence) >= 2

    # Meta-confidence score: starts at 70, adjusts based on findings
    if meta_confidence_override is not None:
        meta_confidence = meta_confidence_override
    else:
        meta_confidence = 70
        meta_confidence -= len(worldview_challenges) * 5
        meta_confidence -= len(rigidity_flags) * 8
        meta_confidence += min(recent_pip_count * 3, 15)
        meta_confidence = max(10, min(95, meta_confidence))

    all_ch = org_challenges + worldview_challenges + assumption_challenges + rigidity_flags
    critical = sum(1 for c in all_ch if c.severity == "critical")
    high = sum(1 for c in all_ch if c.severity == "high")

    if not all_ch:
        summary = (
            "No philosophical rigidity detected. Organization appears to be evolving adaptively."
        )
    else:
        summary = (
            f"Meta-Agent audit: {len(all_ch)} challenge(s) identified "
            f"({critical} critical, {high} high). "
            + ("Ideology lock detected. " if ideology_lock_detected else "")
            + FINAL_GOVERNING_PRINCIPLE
        )

    return MetaAgentAudit(
        audit_id=audit_id,
        date=date,
        trigger=trigger,
        org_challenges=org_challenges,
        worldview_challenges=worldview_challenges,
        assumption_challenges=assumption_challenges,
        rigidity_flags=rigidity_flags,
        ideology_lock_detected=ideology_lock_detected,
        ideology_lock_evidence=ideology_lock_evidence,
        final_governing_principle=FINAL_GOVERNING_PRINCIPLE,
        meta_confidence_score=meta_confidence,
        summary=summary,
    )
