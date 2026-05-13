"""
Thesis Engine — manages thesis lifecycle states and transitions.
Implements schemas/thesis_lifecycle_schema.yaml.
Advisory only — no live trading.
"""

from __future__ import annotations
from enum import Enum
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Optional

import yaml

from config import load_thesis_log, PORTFOLIO_DIR


class ThesisState(str, Enum):
    EMERGING = "Emerging"
    CONFIRMING = "Confirming"
    HIGH_CONVICTION = "High Conviction"
    CROWDED = "Crowded"
    DISTRIBUTION_RISK = "Distribution Risk"
    BREAKDOWN_RISK = "Breakdown Risk"
    INVALIDATED = "Invalidated"


STATE_SIZING_GUIDANCE = {
    ThesisState.EMERGING: "1/3 to 1/2 of target — thesis forming, not confirmed",
    ThesisState.CONFIRMING: "1/2 to 3/4 of target — evidence building",
    ThesisState.HIGH_CONVICTION: "Full target or above if asymmetry exceptional",
    ThesisState.CROWDED: "50–75% of peak — begin gradual trimming",
    ThesisState.DISTRIBUTION_RISK: "25–50% of peak — trim on bounces",
    ThesisState.BREAKDOWN_RISK: "10–20% max — consider puts; active exit plan",
    ThesisState.INVALIDATED: "Zero — exit fully; document in Portfolio Historian",
}


@dataclass
class Thesis:
    id: str
    name: str
    related_positions: list[str]
    lifecycle_state: ThesisState
    time_horizon: str  # Tactical | Strategic | Structural
    opened_date: str
    thesis: str
    bull_case: str
    bear_case: str
    confidence_score: int
    key_drivers: list[str]
    invalidation: str
    review_trigger: str
    crowding_check: str
    next_review_date: str
    historical_lessons: str = ""
    state_history: list[dict] = field(default_factory=list)

    def sizing_guidance(self) -> str:
        return STATE_SIZING_GUIDANCE.get(self.lifecycle_state, "Unknown")

    def is_action_required(self) -> bool:
        return self.lifecycle_state in {
            ThesisState.CROWDED,
            ThesisState.DISTRIBUTION_RISK,
            ThesisState.BREAKDOWN_RISK,
            ThesisState.INVALIDATED,
        }

    def days_since_open(self) -> int:
        opened = datetime.strptime(self.opened_date, "%Y-%m-%d").date()
        return (date.today() - opened).days


def load_all_theses() -> list[Thesis]:
    """Load all active theses from thesis_log.yaml."""
    raw = load_thesis_log()
    theses = []
    for item in raw.get("active_theses", []):
        theses.append(Thesis(
            id=item.get("id", ""),
            name=item.get("name", ""),
            related_positions=item.get("related_positions", []),
            lifecycle_state=ThesisState(item.get("lifecycle_state", "Emerging")),
            time_horizon=item.get("time_horizon", "Strategic"),
            opened_date=item.get("opened_date", ""),
            thesis=item.get("thesis", ""),
            bull_case=item.get("bull_case", ""),
            bear_case=item.get("bear_case", ""),
            confidence_score=item.get("confidence_score", 50),
            key_drivers=item.get("key_drivers", []),
            invalidation=item.get("invalidation", ""),
            review_trigger=item.get("review_trigger", ""),
            crowding_check=item.get("crowding_check", ""),
            next_review_date=item.get("next_review_date", ""),
        ))
    return theses


def transition_thesis(thesis: Thesis, new_state: ThesisState, reason: str) -> Thesis:
    """
    Transition a thesis to a new lifecycle state.
    Records the state change in history.
    """
    old_state = thesis.lifecycle_state
    thesis.state_history.append({
        "from": old_state.value,
        "to": new_state.value,
        "date": str(date.today()),
        "reason": reason,
    })
    thesis.lifecycle_state = new_state
    return thesis


def get_theses_requiring_action(theses: list[Thesis]) -> list[Thesis]:
    """Return theses in states that require immediate action."""
    return [t for t in theses if t.is_action_required()]


def get_thesis_lifecycle_health_score(theses: list[Thesis]) -> int:
    """
    Calculate a thesis lifecycle health score (1–100) for the confidence engine.
    High Conviction theses are ideal. Invalidated-but-held is catastrophic.
    """
    if not theses:
        return 50

    state_scores = {
        ThesisState.EMERGING: 40,
        ThesisState.CONFIRMING: 60,
        ThesisState.HIGH_CONVICTION: 90,
        ThesisState.CROWDED: 55,
        ThesisState.DISTRIBUTION_RISK: 30,
        ThesisState.BREAKDOWN_RISK: 15,
        ThesisState.INVALIDATED: 0,
    }

    total = sum(state_scores.get(t.lifecycle_state, 50) for t in theses)
    base_score = total // len(theses)

    if any(t.lifecycle_state == ThesisState.INVALIDATED for t in theses):
        base_score = max(0, base_score - 20)

    return min(100, max(1, base_score))
