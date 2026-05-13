"""
Agent Vote Database — persistent JSON store for all agent votes and outcomes.
Backs the agent scorecard system.
Advisory only — no live trading.
"""

from __future__ import annotations
import json
from datetime import date, datetime
from pathlib import Path
from typing import Optional

ROOT_DIR = Path(__file__).parent.parent
VOTES_FILE = ROOT_DIR / "data" / "processed" / "agent_votes.json"

AGENTS = [
    "cio", "macro_strategist", "scarcity_strategist", "technology_structural_change",
    "technical_chart_expert", "options_specialist", "momentum_trader", "crypto_strategist",
    "commodity_specialist", "valuation_analyst", "sentiment_analyst", "bear_case_analyst",
    "risk_officer", "portfolio_historian", "benchmark_analyst", "psychological_agent",
    "meta_philosophy_auditor",
]

VOTE_OPTIONS = ("Agree", "Disagree", "Neutral", "Abstain")
OUTCOME_OPTIONS = ("Correct", "Incorrect", "Partial", "Pending", "Invalidated")


def _load() -> dict:
    if VOTES_FILE.exists():
        with open(VOTES_FILE) as f:
            return json.load(f)
    return {"recommendations": {}, "votes": []}


def _save(data: dict) -> None:
    VOTES_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(VOTES_FILE, "w") as f:
        json.dump(data, f, indent=2)


def record_recommendation(
    rec_id: str,
    date_str: str,
    asset: str,
    action: str,
    thesis_summary: str,
    confidence: int,
    time_horizon: str,
    invalidation: str,
    target_zone: str = "",
    lead_agent: str = "cio",
    regime: str = "unknown",
) -> None:
    """Record a new investment recommendation."""
    data = _load()
    data["recommendations"][rec_id] = {
        "date": date_str,
        "asset": asset,
        "action": action,
        "thesis_summary": thesis_summary,
        "confidence": confidence,
        "time_horizon": time_horizon,
        "invalidation": invalidation,
        "target_zone": target_zone,
        "lead_agent": lead_agent,
        "regime": regime,
        "outcome": "Pending",
        "outcome_date": None,
        "outcome_return_pct": None,
        "outcome_notes": "",
        "benchmark_return_pct": None,
        "beat_benchmark": None,
        "outcome_regime": None,
    }
    _save(data)


def record_vote(
    rec_id: str,
    agent: str,
    vote: str,
    confidence: int,
    rationale: str,
    regime: str = "",
) -> None:
    """Record an agent's vote on a recommendation."""
    assert vote in VOTE_OPTIONS, f"Invalid vote: {vote}"
    assert agent in AGENTS, f"Unknown agent: {agent}"
    data = _load()
    data["votes"].append({
        "rec_id": rec_id,
        "agent": agent,
        "vote": vote,
        "confidence": confidence,
        "rationale": rationale,
        "regime": regime,
        "timestamp": datetime.now().isoformat(),
    })
    _save(data)


def resolve_outcome(
    rec_id: str,
    outcome: str,
    return_pct: float,
    benchmark_return_pct: float,
    notes: str = "",
    outcome_regime: str = "",
) -> None:
    """Resolve the outcome of a recommendation once enough time has passed."""
    assert outcome in OUTCOME_OPTIONS
    data = _load()
    if rec_id not in data["recommendations"]:
        raise KeyError(f"Recommendation {rec_id} not found.")
    rec = data["recommendations"][rec_id]
    rec["outcome"] = outcome
    rec["outcome_date"] = str(date.today())
    rec["outcome_return_pct"] = round(return_pct, 2)
    rec["benchmark_return_pct"] = round(benchmark_return_pct, 2)
    rec["beat_benchmark"] = return_pct > benchmark_return_pct
    rec["outcome_notes"] = notes
    rec["outcome_regime"] = outcome_regime or rec.get("regime", "")
    _save(data)


def get_agent_scorecard(agent: str, regime_filter: str = "") -> dict:
    """Compute scorecard metrics for one agent from resolved votes.

    Pass regime_filter to restrict scoring to votes made during a specific market regime.
    """
    data = _load()
    agent_votes = [v for v in data["votes"] if v["agent"] == agent]
    resolved = {
        rec_id: rec
        for rec_id, rec in data["recommendations"].items()
        if rec["outcome"] not in ("Pending",)
    }

    total, correct, incorrect, beat_bmk = 0, 0, 0, 0
    returns_when_correct, returns_when_incorrect = [], []

    for v in agent_votes:
        rec = resolved.get(v["rec_id"])
        if rec is None:
            continue
        vote_regime = v.get("regime") or rec.get("regime", "")
        if regime_filter and vote_regime != regime_filter:
            continue
        total += 1
        outcome = rec["outcome"]
        ret = rec.get("outcome_return_pct") or 0.0
        is_agree = v["vote"] == "Agree"
        is_correct = (is_agree and outcome == "Correct") or (not is_agree and outcome == "Incorrect")

        if is_correct:
            correct += 1
            returns_when_correct.append(ret)
        else:
            incorrect += 1
            returns_when_incorrect.append(ret)
        if rec.get("beat_benchmark"):
            beat_bmk += 1

    hit_rate = (correct / total * 100) if total else 0.0
    avg_win = sum(returns_when_correct) / len(returns_when_correct) if returns_when_correct else 0.0
    avg_loss = sum(returns_when_incorrect) / len(returns_when_incorrect) if returns_when_incorrect else 0.0

    result = {
        "agent": agent,
        "total_votes": total,
        "correct": correct,
        "incorrect": incorrect,
        "hit_rate_pct": round(hit_rate, 1),
        "avg_return_when_correct": round(avg_win, 2),
        "avg_return_when_incorrect": round(avg_loss, 2),
        "beat_benchmark_count": beat_bmk,
        "pending_votes": len([v for v in agent_votes
                               if resolved.get(v["rec_id"]) is None]),
    }
    if regime_filter:
        result["regime_filter"] = regime_filter
    return result


def get_all_scorecards() -> list[dict]:
    """Get scorecards for all 17 agents, sorted by hit rate."""
    cards = [get_agent_scorecard(a) for a in AGENTS]
    return sorted(cards, key=lambda x: x["hit_rate_pct"], reverse=True)


def get_recommendation_summary(rec_id: str) -> Optional[dict]:
    data = _load()
    rec = data["recommendations"].get(rec_id)
    if not rec:
        return None
    votes = [v for v in data["votes"] if v["rec_id"] == rec_id]
    agrees = sum(1 for v in votes if v["vote"] == "Agree")
    disagrees = sum(1 for v in votes if v["vote"] == "Disagree")
    return {**rec, "vote_agrees": agrees, "vote_disagrees": disagrees, "vote_total": len(votes)}


def list_pending_recommendations() -> list[dict]:
    data = _load()
    return [
        {"rec_id": k, **v}
        for k, v in data["recommendations"].items()
        if v["outcome"] == "Pending"
    ]


from typing import Optional
