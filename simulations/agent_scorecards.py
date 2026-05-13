"""
Agent Scorecards — tracks and scores each agent's recommendation performance.
Phase 2: full tracking from trade log and price history.
Phase 1: schema and stub only.
Advisory only — no live trading.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional

PHASE = 1
DISCLAIMER = "ADVISORY ONLY. All figures are SIMULATED. Not financial advice."

AGENTS = [
    "cio",
    "macro_strategist",
    "scarcity_strategist",
    "technology_structural_change",
    "technical_chart_expert",
    "options_specialist",
    "momentum_trader",
    "crypto_strategist",
    "commodity_specialist",
    "valuation_analyst",
    "sentiment_analyst",
    "bear_case_analyst",
    "risk_officer",
    "portfolio_historian",
    "benchmark_analyst",
    "psychological_agent",
    "meta_philosophy_auditor",
]


@dataclass
class AgentScore:
    agent: str
    total_recommendations: int = 0
    correct: int = 0
    incorrect: int = 0
    abstained: int = 0
    hit_rate_pct: float = 0.0
    avg_return_when_correct: float = 0.0
    avg_loss_when_incorrect: float = 0.0
    best_regime: str = ""  # Regime where agent performed best
    worst_regime: str = ""  # Regime where agent performed worst
    systematic_bias: str = ""  # Any detected bias (too early, too late, etc.)
    note: str = "[SIMULATED - Phase 2+]"


@dataclass
class AgentVote:
    agent: str
    recommendation_id: str
    vote: str  # Agree | Disagree | Neutral | Abstain
    confidence: int  # 1–100
    rationale: str
    outcome: str = ""  # Correct | Incorrect | Pending (filled in post-outcome)


def calculate_agent_scorecard(
    agent: str,
    vote_history: list[AgentVote],
    outcomes: dict[str, str],  # recommendation_id -> Correct | Incorrect
) -> AgentScore:
    """
    Calculate agent scorecard from historical votes and outcomes.
    Phase 1: placeholder. Phase 2: full implementation.
    """
    if PHASE < 2:
        return AgentScore(
            agent=agent,
            note="Phase 2 — scorecard tracking requires trade log history. [SIMULATED]",
        )
    raise NotImplementedError("Phase 2 not yet implemented.")


def get_regime_performance(
    agent: str,
    votes: list[AgentVote],
    regime_map: dict[str, str],  # date -> regime label
) -> dict[str, float]:
    """
    Calculate agent hit rate by macro regime.
    Identifies which agents are best in which market environments.
    Phase 2 implementation.
    """
    if PHASE < 2:
        return {
            "note": "Phase 2 — regime performance tracking not yet implemented.",
        }
    raise NotImplementedError("Phase 2 not yet implemented.")


def generate_all_scorecards(
    vote_histories: dict[str, list[AgentVote]],
    outcomes: dict[str, str],
) -> dict[str, AgentScore]:
    """Generate scorecards for all 17 agents."""
    return {agent: calculate_agent_scorecard(agent, vote_histories.get(agent, []), outcomes) for agent in AGENTS}


def find_most_valuable_agent(scorecards: dict[str, AgentScore]) -> str:
    """Identify the agent with highest hit rate + alpha. Phase 2."""
    if PHASE < 2:
        return "[SIMULATED - Phase 2+]"
    best = max(scorecards, key=lambda a: scorecards[a].hit_rate_pct)
    return best


def detect_agent_bias(scorecard: AgentScore) -> list[str]:
    """
    Detect systematic bias in an agent's recommendations.
    Phase 2: analyzes patterns like "always too early" or "always bullish on X".
    """
    if PHASE < 2:
        return ["[SIMULATED - Phase 2+]"]
    biases = []
    # Phase 2: analyze patterns in vote history
    # Example: if agent recommends Buy within 10 days of every breakout (early entry bias)
    return biases
