"""
Thesis Engine — Phase 2.
Manages thesis lifecycle states, transitions, and automated monitoring alerts.
Implements schemas/thesis_lifecycle_schema.yaml.
Advisory only — no live trading.
"""

from __future__ import annotations
import json
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Optional

import yaml

ROOT_DIR = Path(__file__).parent.parent
PORTFOLIO_DIR = ROOT_DIR / "portfolio"
THESIS_LOG_FILE = PORTFOLIO_DIR / "thesis_log.yaml"
THESIS_HISTORY_FILE = ROOT_DIR / "data" / "processed" / "thesis_history.json"


class ThesisState:
    EMERGING = "Emerging"
    CONFIRMING = "Confirming"
    HIGH_CONVICTION = "High Conviction"
    CROWDED = "Crowded"
    DISTRIBUTION_RISK = "Distribution Risk"
    BREAKDOWN_RISK = "Breakdown Risk"
    INVALIDATED = "Invalidated"

    ALL = [EMERGING, CONFIRMING, HIGH_CONVICTION, CROWDED, DISTRIBUTION_RISK, BREAKDOWN_RISK, INVALIDATED]


STATE_SIZING_GUIDANCE = {
    ThesisState.EMERGING: "1/3 to 1/2 of target — thesis forming, not confirmed",
    ThesisState.CONFIRMING: "1/2 to 3/4 of target — evidence building",
    ThesisState.HIGH_CONVICTION: "Full target or above if asymmetry exceptional",
    ThesisState.CROWDED: "50–75% of peak — begin gradual trimming",
    ThesisState.DISTRIBUTION_RISK: "25–50% of peak — trim on bounces, prepare exit",
    ThesisState.BREAKDOWN_RISK: "10–20% max — consider puts; active exit plan",
    ThesisState.INVALIDATED: "Zero — exit fully; document in Portfolio Historian",
}

STATE_URGENCY = {
    ThesisState.EMERGING: "Low",
    ThesisState.CONFIRMING: "Low",
    ThesisState.HIGH_CONVICTION: "Low",
    ThesisState.CROWDED: "Medium",
    ThesisState.DISTRIBUTION_RISK: "High",
    ThesisState.BREAKDOWN_RISK: "Critical",
    ThesisState.INVALIDATED: "Critical",
}

ACTION_REQUIRED_STATES = {ThesisState.CROWDED, ThesisState.DISTRIBUTION_RISK, ThesisState.BREAKDOWN_RISK, ThesisState.INVALIDATED}


@dataclass
class Thesis:
    id: str
    name: str
    related_positions: list[str]
    lifecycle_state: str
    time_horizon: str
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

    def urgency(self) -> str:
        return STATE_URGENCY.get(self.lifecycle_state, "Low")

    def is_action_required(self) -> bool:
        return self.lifecycle_state in ACTION_REQUIRED_STATES

    def days_since_open(self) -> int:
        try:
            opened = datetime.strptime(self.opened_date, "%Y-%m-%d").date()
            return (date.today() - opened).days
        except Exception:
            return 0

    def days_until_review(self) -> int:
        try:
            review = datetime.strptime(self.next_review_date, "%Y-%m-%d").date()
            return (review - date.today()).days
        except Exception:
            return 999

    def is_overdue_for_review(self) -> bool:
        return self.days_until_review() < 0


def load_all_theses() -> list[Thesis]:
    """Load all active theses from thesis_log.yaml."""
    with open(THESIS_LOG_FILE) as f:
        raw = yaml.safe_load(f)

    theses = []
    for item in raw.get("active_theses", []):
        theses.append(Thesis(
            id=item.get("id", ""),
            name=item.get("name", ""),
            related_positions=item.get("related_positions", []),
            lifecycle_state=item.get("lifecycle_state", ThesisState.EMERGING),
            time_horizon=item.get("time_horizon", "Strategic"),
            opened_date=item.get("opened_date", ""),
            thesis=str(item.get("thesis", "")),
            bull_case=item.get("bull_case", ""),
            bear_case=item.get("bear_case", ""),
            confidence_score=int(item.get("confidence_score", 50)),
            key_drivers=item.get("key_drivers", []),
            invalidation=item.get("invalidation", ""),
            review_trigger=item.get("review_trigger", ""),
            crowding_check=item.get("crowding_check", ""),
            next_review_date=item.get("next_review_date", ""),
        ))
    return theses


def transition_thesis(thesis: Thesis, new_state: str, reason: str) -> Thesis:
    """Transition thesis to new state, recording history."""
    assert new_state in ThesisState.ALL, f"Invalid state: {new_state}"
    entry = {
        "from": thesis.lifecycle_state,
        "to": new_state,
        "date": str(date.today()),
        "reason": reason,
    }
    thesis.state_history.append(entry)
    thesis.lifecycle_state = new_state
    _append_history(thesis.id, entry)
    return thesis


def _append_history(thesis_id: str, entry: dict) -> None:
    THESIS_HISTORY_FILE.parent.mkdir(parents=True, exist_ok=True)
    history: dict = {}
    if THESIS_HISTORY_FILE.exists():
        with open(THESIS_HISTORY_FILE) as f:
            history = json.load(f)
    history.setdefault(thesis_id, []).append(entry)
    with open(THESIS_HISTORY_FILE, "w") as f:
        json.dump(history, f, indent=2)


def get_thesis_history(thesis_id: str) -> list[dict]:
    """Retrieve full state transition history for a thesis."""
    if not THESIS_HISTORY_FILE.exists():
        return []
    with open(THESIS_HISTORY_FILE) as f:
        return json.load(f).get(thesis_id, [])


def get_theses_requiring_action(theses: list[Thesis]) -> list[Thesis]:
    return [t for t in theses if t.is_action_required()]


def get_overdue_reviews(theses: list[Thesis]) -> list[Thesis]:
    return [t for t in theses if t.is_overdue_for_review()]


def get_thesis_lifecycle_health_score(theses: list[Thesis]) -> int:
    """
    Portfolio-level lifecycle health score (1–100).
    High Conviction is ideal. Invalidated-and-held is catastrophic.
    """
    if not theses:
        return 50

    STATE_SCORES = {
        ThesisState.EMERGING: 40,
        ThesisState.CONFIRMING: 60,
        ThesisState.HIGH_CONVICTION: 90,
        ThesisState.CROWDED: 55,
        ThesisState.DISTRIBUTION_RISK: 30,
        ThesisState.BREAKDOWN_RISK: 15,
        ThesisState.INVALIDATED: 0,
    }
    scores = [STATE_SCORES.get(t.lifecycle_state, 50) for t in theses]
    base = int(sum(scores) / len(scores))
    if any(t.lifecycle_state == ThesisState.INVALIDATED for t in theses):
        base = max(0, base - 20)
    return min(100, max(1, base))


def lifecycle_monitor_report(theses: list[Thesis]) -> dict:
    """
    Generate a full lifecycle monitoring report.
    Flags overdue reviews, action-required theses, and lifecycle drift.
    """
    action_required = get_theses_requiring_action(theses)
    overdue = get_overdue_reviews(theses)
    health_score = get_thesis_lifecycle_health_score(theses)

    state_distribution = {}
    for t in theses:
        state_distribution[t.lifecycle_state] = state_distribution.get(t.lifecycle_state, 0) + 1

    alerts = []
    for t in action_required:
        alerts.append({
            "type": "ACTION_REQUIRED",
            "thesis_id": t.id,
            "thesis_name": t.name,
            "state": t.lifecycle_state,
            "urgency": t.urgency(),
            "sizing_guidance": t.sizing_guidance(),
            "positions": t.related_positions,
        })
    for t in overdue:
        if not t.is_action_required():  # avoid duplication
            alerts.append({
                "type": "REVIEW_OVERDUE",
                "thesis_id": t.id,
                "thesis_name": t.name,
                "days_overdue": abs(t.days_until_review()),
                "urgency": "Medium",
            })

    thesis_table = [
        {
            "id": t.id,
            "name": t.name,
            "state": t.lifecycle_state,
            "confidence": t.confidence_score,
            "horizon": t.time_horizon,
            "days_open": t.days_since_open(),
            "days_to_review": t.days_until_review(),
            "positions": t.related_positions,
            "action_required": t.is_action_required(),
            "sizing": t.sizing_guidance(),
        }
        for t in theses
    ]

    return {
        "health_score": health_score,
        "total_theses": len(theses),
        "action_required_count": len(action_required),
        "overdue_review_count": len(overdue),
        "state_distribution": state_distribution,
        "alerts": alerts,
        "thesis_table": thesis_table,
        "generated_at": datetime.now().isoformat(),
    }
