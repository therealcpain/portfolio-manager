"""
portfolio_ledger.py — Durable, event-sourced portfolio state persistence.

Every position, thesis, allocation change, confidence update, dissent argument,
and CIO decision is written to an append-only event log. Seven query functions
reconstruct narrative answers from that log.

Seven canonical questions this module must answer:
  1. Why do we own this?          → why_do_we_own(ticker)
  2. What changed?                → what_changed(ticker)
  3. What were the concerns?      → what_were_concerns(ticker)
  4. What invalidated?            → what_invalidated(ticker)
  5. What improved?               → what_improved(ticker)
  6. What was the original thesis? → original_thesis(ticker)
  7. Did the thesis evolve correctly? → did_thesis_evolve_correctly(ticker)

Storage layout (single JSON file, multiple top-level sections):
  events[]            — append-only ledger of every mutation
  positions{}         — latest snapshot per ticker
  thesis_registry{}   — full narrative record per thesis_id
  confidence_timeline{} — per-ticker time series of confidence snapshots
  watchlist_history{} — per-ticker list of watch events
  decision_audit[]    — every CIO decision with full context

Advisory only — no live trading.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import asdict, dataclass, field
from datetime import date, datetime
from enum import Enum
from pathlib import Path
from typing import Any, Optional

ROOT_DIR = Path(__file__).parent.parent
LEDGER_PATH = ROOT_DIR / "data" / "processed" / "portfolio_ledger.json"

DISCLAIMER = "ADVISORY ONLY. All outputs are simulated. Not financial advice."


# ---------------------------------------------------------------------------
# Event taxonomy
# ---------------------------------------------------------------------------

class EventType(str, Enum):
    # Position lifecycle
    POSITION_OPENED       = "position_opened"
    POSITION_ADDED        = "position_added"        # incremental buy
    POSITION_TRIMMED      = "position_trimmed"       # partial sell
    POSITION_EXITED       = "position_exited"        # full exit
    # Thesis lifecycle
    THESIS_CREATED        = "thesis_created"
    THESIS_EVOLVED        = "thesis_evolved"         # narrative update
    THESIS_STRENGTHENED   = "thesis_strengthened"    # new supporting evidence
    THESIS_WEAKENED       = "thesis_weakened"        # new counter-evidence
    THESIS_INVALIDATED    = "thesis_invalidated"
    INVALIDATION_UPDATED  = "invalidation_updated"   # conditions revised
    # Confidence
    CONFIDENCE_UPDATED    = "confidence_updated"
    # Dissent
    DISSENT_RECORDED      = "dissent_recorded"
    DISSENT_RESOLVED      = "dissent_resolved"
    # Watchlist
    WATCHLIST_ADDED       = "watchlist_added"
    WATCHLIST_TRIGGERED   = "watchlist_triggered"    # entry conditions met
    WATCHLIST_EXPIRED     = "watchlist_expired"
    WATCHLIST_REMOVED     = "watchlist_removed"
    # Decisions
    DECISION_RECORDED     = "decision_recorded"


# ---------------------------------------------------------------------------
# Core record types
# ---------------------------------------------------------------------------

@dataclass
class LedgerEvent:
    event_id: str
    event_type: EventType
    date: str                     # ISO date
    timestamp: str                # ISO datetime
    ticker: Optional[str]         # None for portfolio-level events
    thesis_id: Optional[str]
    payload: dict                 # event-specific data
    author: str                   # agent name or "human"
    session_id: Optional[str]     # links back to committee session

    def to_dict(self) -> dict:
        d = asdict(self)
        d["event_type"] = self.event_type.value
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "LedgerEvent":
        return cls(
            event_id=d["event_id"],
            event_type=EventType(d["event_type"]),
            date=d["date"],
            timestamp=d["timestamp"],
            ticker=d.get("ticker"),
            thesis_id=d.get("thesis_id"),
            payload=d.get("payload", {}),
            author=d.get("author", "system"),
            session_id=d.get("session_id"),
        )


@dataclass
class PositionRecord:
    """Current snapshot of a position — rebuilt from events."""
    ticker: str
    name: str
    bucket: str
    thesis_id: str
    opened_date: str
    is_active: bool
    exited_date: Optional[str]
    # Current state
    current_exposure_pct: float
    peak_exposure_pct: float
    cost_basis_note: str
    current_lifecycle_state: str
    current_confidence: int
    # Narrative
    original_thesis: str
    current_thesis: str
    invalidation_conditions: list[str]
    # Counts
    trim_count: int
    add_count: int
    dissent_count: int
    evolution_count: int

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "PositionRecord":
        return cls(**d)


@dataclass
class ThesisRecord:
    """Full narrative history of a thesis."""
    thesis_id: str
    ticker: str
    name: str
    opened_date: str
    closed_date: Optional[str]
    is_active: bool
    # Immutable inception fields
    original_thesis: str
    original_macro_context: str
    original_technical_context: str
    original_sentiment_context: str
    original_expected_regime: str
    original_invalidation_conditions: list[str]
    original_confidence: int
    # Current state
    current_thesis: str
    current_lifecycle_state: str
    current_confidence: int
    current_invalidation_conditions: list[str]
    # Evolution log
    evolution_log: list[dict]         # ThesisEvolutionEntry dicts
    lifecycle_history: list[dict]     # {date, from_state, to_state, reason}
    confidence_history: list[dict]    # {date, confidence, rationale, regime}
    dissent_log: list[dict]           # DissentRecord dicts
    invalidation_event: Optional[dict]

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "ThesisRecord":
        return cls(**d)


@dataclass
class ConfidenceSnapshot:
    date: str
    ticker: str
    thesis_id: str
    confidence: int
    prior_confidence: int
    delta: int
    rationale: str
    regime: str
    triggered_by: str       # agent name or "human"

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class WatchEvent:
    event_id: str
    date: str
    ticker: str
    event_type: str         # "added" | "triggered" | "expired" | "removed"
    thesis_summary: str
    entry_triggers: list[str]
    exit_triggers: list[str]
    patience_note: str
    outcome: Optional[str]  # None until resolved
    outcome_note: Optional[str]
    resolved_date: Optional[str]

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "WatchEvent":
        return cls(**d)


@dataclass
class DecisionRecord:
    decision_id: str
    date: str
    session_id: Optional[str]
    decision_type: str
    question: str
    regime: str
    # Inputs
    signals_considered: list[dict]   # {ticker, type, description}
    specialists_consulted: list[str]
    dissent_present: bool
    groupthink_alert: bool
    # Output
    final_stance: str
    final_confidence: int
    allocation_change: bool
    required_actions: list[str]
    watchlist_only: list[str]
    rationale: str
    # Challenge questions raised for investor
    challenge_questions: list[str]
    next_review_trigger: str
    author: str

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "DecisionRecord":
        return cls(**d)


# ---------------------------------------------------------------------------
# Narrative answer types (returned by the 7 query functions)
# ---------------------------------------------------------------------------

@dataclass
class PositionNarrative:
    """Answer to: Why do we own this?"""
    ticker: str
    name: str
    is_active: bool
    opened_date: str
    original_thesis: str
    current_thesis: str
    current_lifecycle_state: str
    current_confidence: int
    invalidation_conditions: list[str]
    sizing_guidance: str
    key_changes_summary: str       # one-paragraph summary of evolution
    open_dissents: list[str]       # unresolved concerns
    exited_date: Optional[str]
    exit_reason: Optional[str]


@dataclass
class ThesisEvolutionAssessment:
    """Answer to: Did the thesis evolve correctly?"""
    ticker: str
    thesis_id: str
    overall_verdict: str           # "Disciplined" | "Drifting" | "Reversed" | "Insufficient data"
    evolution_count: int
    strengthening_events: int
    weakening_events: int
    invalidation_events: int
    confidence_trend: str          # "Rising" | "Falling" | "Stable" | "Volatile"
    original_confidence: int
    current_confidence: int
    regime_accuracy: str           # did we anticipate regime correctly?
    discipline_flags: list[str]    # e.g. "Held through multiple invalidation signals"
    assessment_narrative: str


# ---------------------------------------------------------------------------
# Storage
# ---------------------------------------------------------------------------

def _load_db() -> dict:
    if LEDGER_PATH.exists():
        with open(LEDGER_PATH) as f:
            return json.load(f)
    return {
        "events": [],
        "positions": {},
        "thesis_registry": {},
        "confidence_timeline": {},
        "watchlist_history": {},
        "decision_audit": [],
    }


def _save_db(db: dict) -> None:
    LEDGER_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(LEDGER_PATH, "w") as f:
        json.dump(db, f, indent=2, default=str)


def _new_event_id() -> str:
    return f"EVT-{uuid.uuid4().hex[:8].upper()}"


def _now_str() -> str:
    return datetime.now().isoformat()


def _today_str() -> str:
    return str(date.today())


def _append_event(db: dict, event: LedgerEvent) -> None:
    db["events"].append(event.to_dict())


_LIFECYCLE_SIZING_GUIDANCE = {
    "Emerging":          "1/3 to 1/2 of target — thesis forming, not confirmed",
    "Confirming":        "1/2 to 3/4 of target — evidence accumulating",
    "High Conviction":   "Full target — thesis confirmed across macro/technical/sentiment",
    "Crowded":           "50–75% of peak — begin gradual trimming",
    "Distribution Risk": "25–50% of peak — trim on bounces, prepare exit",
    "Breakdown Risk":    "10–20% max — active exit plan; consider protection",
    "Invalidated":       "Zero — exit fully; document lessons",
}


def _lifecycle_sizing_guidance(state: str) -> str:
    return _LIFECYCLE_SIZING_GUIDANCE.get(state, "Unknown — check lifecycle state")


# ---------------------------------------------------------------------------
# Write operations
# ---------------------------------------------------------------------------

def open_position(
    ticker: str,
    name: str,
    bucket: str,
    thesis_id: str,
    original_thesis: str,
    macro_context: str,
    technical_context: str,
    sentiment_context: str,
    expected_regime: str,
    invalidation_conditions: list[str],
    initial_exposure_pct: float,
    initial_confidence: int,
    author: str = "cio",
    session_id: Optional[str] = None,
    date_str: Optional[str] = None,
    cost_basis_note: str = "",
) -> PositionRecord:
    """
    Record the opening of a new position and create its thesis registry entry.

    This is the genesis event — it establishes the original_thesis,
    all original context fields, and the invalidation conditions.
    These fields are IMMUTABLE after this call.
    """
    d = date_str or _today_str()
    db = _load_db()

    # Create thesis registry entry
    thesis_record = ThesisRecord(
        thesis_id=thesis_id,
        ticker=ticker,
        name=name,
        opened_date=d,
        closed_date=None,
        is_active=True,
        original_thesis=original_thesis,
        original_macro_context=macro_context,
        original_technical_context=technical_context,
        original_sentiment_context=sentiment_context,
        original_expected_regime=expected_regime,
        original_invalidation_conditions=invalidation_conditions[:],
        original_confidence=initial_confidence,
        current_thesis=original_thesis,
        current_lifecycle_state="Emerging",
        current_confidence=initial_confidence,
        current_invalidation_conditions=invalidation_conditions[:],
        evolution_log=[],
        lifecycle_history=[
            {
                "date": d,
                "from_state": None,
                "to_state": "Emerging",
                "reason": "Position opened.",
            }
        ],
        confidence_history=[
            {
                "date": d,
                "confidence": initial_confidence,
                "rationale": "Initial confidence at position opening.",
                "regime": expected_regime,
                "triggered_by": author,
            }
        ],
        dissent_log=[],
        invalidation_event=None,
    )
    db["thesis_registry"][thesis_id] = thesis_record.to_dict()

    # Create position record
    position = PositionRecord(
        ticker=ticker,
        name=name,
        bucket=bucket,
        thesis_id=thesis_id,
        opened_date=d,
        is_active=True,
        exited_date=None,
        current_exposure_pct=initial_exposure_pct,
        peak_exposure_pct=initial_exposure_pct,
        cost_basis_note=cost_basis_note,
        current_lifecycle_state="Emerging",
        current_confidence=initial_confidence,
        original_thesis=original_thesis,
        current_thesis=original_thesis,
        invalidation_conditions=invalidation_conditions[:],
        trim_count=0,
        add_count=0,
        dissent_count=0,
        evolution_count=0,
    )
    db["positions"][ticker] = position.to_dict()

    # Confidence timeline
    db["confidence_timeline"].setdefault(ticker, [])
    db["confidence_timeline"][ticker].append(
        ConfidenceSnapshot(
            date=d,
            ticker=ticker,
            thesis_id=thesis_id,
            confidence=initial_confidence,
            prior_confidence=0,
            delta=initial_confidence,
            rationale="Initial confidence at position opening.",
            regime=expected_regime,
            triggered_by=author,
        ).to_dict()
    )

    # Append event
    event = LedgerEvent(
        event_id=_new_event_id(),
        event_type=EventType.POSITION_OPENED,
        date=d,
        timestamp=_now_str(),
        ticker=ticker,
        thesis_id=thesis_id,
        payload={
            "name": name,
            "bucket": bucket,
            "original_thesis": original_thesis,
            "macro_context": macro_context,
            "technical_context": technical_context,
            "sentiment_context": sentiment_context,
            "expected_regime": expected_regime,
            "invalidation_conditions": invalidation_conditions,
            "initial_exposure_pct": initial_exposure_pct,
            "initial_confidence": initial_confidence,
            "cost_basis_note": cost_basis_note,
        },
        author=author,
        session_id=session_id,
    )
    _append_event(db, event)
    _save_db(db)
    return position


def record_allocation_change(
    ticker: str,
    action: str,                    # "add" | "trim" | "exit"
    from_exposure_pct: float,
    to_exposure_pct: float,
    reason: str,
    regime: str = "",
    author: str = "cio",
    session_id: Optional[str] = None,
    date_str: Optional[str] = None,
    dissent_on_change: Optional[str] = None,
) -> LedgerEvent:
    """
    Log every allocation change — add, trim, or full exit.

    Dissent_on_change: if any agent disagreed with this change, record their argument.
    """
    d = date_str or _today_str()
    db = _load_db()

    if ticker not in db["positions"]:
        raise KeyError(f"Position {ticker} not found in ledger. Call open_position first.")

    pos = PositionRecord.from_dict(db["positions"][ticker])
    action = action.lower()
    assert action in ("add", "trim", "exit"), f"Unknown action: {action}"

    event_type = {
        "add": EventType.POSITION_ADDED,
        "trim": EventType.POSITION_TRIMMED,
        "exit": EventType.POSITION_EXITED,
    }[action]

    # Update position record
    pos.current_exposure_pct = to_exposure_pct
    if action == "add":
        pos.add_count += 1
        pos.peak_exposure_pct = max(pos.peak_exposure_pct, to_exposure_pct)
    elif action == "trim":
        pos.trim_count += 1
    elif action == "exit":
        pos.is_active = False
        pos.exited_date = d
        pos.current_exposure_pct = 0.0
        # Mark thesis closed
        if pos.thesis_id in db["thesis_registry"]:
            db["thesis_registry"][pos.thesis_id]["closed_date"] = d
            db["thesis_registry"][pos.thesis_id]["is_active"] = False

    db["positions"][ticker] = pos.to_dict()

    payload = {
        "action": action,
        "from_exposure_pct": from_exposure_pct,
        "to_exposure_pct": to_exposure_pct,
        "reason": reason,
        "regime": regime,
    }
    if dissent_on_change:
        payload["dissent_argument"] = dissent_on_change
        pos.dissent_count += 1
        db["positions"][ticker] = pos.to_dict()

    event = LedgerEvent(
        event_id=_new_event_id(),
        event_type=event_type,
        date=d,
        timestamp=_now_str(),
        ticker=ticker,
        thesis_id=pos.thesis_id,
        payload=payload,
        author=author,
        session_id=session_id,
    )
    _append_event(db, event)
    _save_db(db)
    return event


def update_confidence(
    ticker: str,
    new_confidence: int,
    rationale: str,
    regime: str = "",
    triggered_by: str = "cio",
    session_id: Optional[str] = None,
    date_str: Optional[str] = None,
) -> ConfidenceSnapshot:
    """Record a confidence score change for a position."""
    d = date_str or _today_str()
    db = _load_db()

    if ticker not in db["positions"]:
        raise KeyError(f"Position {ticker} not found in ledger.")

    pos = PositionRecord.from_dict(db["positions"][ticker])
    thesis_id = pos.thesis_id
    prior = pos.current_confidence
    delta = new_confidence - prior

    # Update position
    pos.current_confidence = new_confidence
    db["positions"][ticker] = pos.to_dict()

    # Update thesis
    if thesis_id in db["thesis_registry"]:
        tr = db["thesis_registry"][thesis_id]
        tr["current_confidence"] = new_confidence
        tr["confidence_history"].append({
            "date": d,
            "confidence": new_confidence,
            "rationale": rationale,
            "regime": regime,
            "triggered_by": triggered_by,
        })

    snap = ConfidenceSnapshot(
        date=d,
        ticker=ticker,
        thesis_id=thesis_id,
        confidence=new_confidence,
        prior_confidence=prior,
        delta=delta,
        rationale=rationale,
        regime=regime,
        triggered_by=triggered_by,
    )
    db["confidence_timeline"].setdefault(ticker, [])
    db["confidence_timeline"][ticker].append(snap.to_dict())

    event = LedgerEvent(
        event_id=_new_event_id(),
        event_type=EventType.CONFIDENCE_UPDATED,
        date=d,
        timestamp=_now_str(),
        ticker=ticker,
        thesis_id=thesis_id,
        payload={
            "prior_confidence": prior,
            "new_confidence": new_confidence,
            "delta": delta,
            "rationale": rationale,
            "regime": regime,
        },
        author=triggered_by,
        session_id=session_id,
    )
    _append_event(db, event)
    _save_db(db)
    return snap


def record_thesis_evolution(
    ticker: str,
    evolution_type: str,              # "strengthening" | "weakening" | "refinement" | "context_change" | "invalidation_updated"
    description: str,
    evidence: str,
    updated_thesis: Optional[str] = None,
    updated_invalidation_conditions: Optional[list[str]] = None,
    author: str = "cio",
    session_id: Optional[str] = None,
    date_str: Optional[str] = None,
) -> LedgerEvent:
    """
    Record how and why the thesis evolved.

    This is the core of "Did the thesis evolve correctly?" tracking.
    Every evolution must include evidence — no evidence-free narrative updates.
    """
    assert len(description) >= 20, "Evolution description must be at least 20 characters."
    assert len(evidence) >= 10, "Evidence must be at least 10 characters."

    d = date_str or _today_str()
    db = _load_db()

    if ticker not in db["positions"]:
        raise KeyError(f"Position {ticker} not found in ledger.")

    pos = PositionRecord.from_dict(db["positions"][ticker])
    thesis_id = pos.thesis_id

    valid_types = {"strengthening", "weakening", "refinement", "context_change",
                   "invalidation_updated", "regime_update"}
    if evolution_type not in valid_types:
        raise ValueError(f"evolution_type must be one of {valid_types}")

    event_type_map = {
        "strengthening": EventType.THESIS_STRENGTHENED,
        "weakening": EventType.THESIS_WEAKENED,
        "refinement": EventType.THESIS_EVOLVED,
        "context_change": EventType.THESIS_EVOLVED,
        "invalidation_updated": EventType.INVALIDATION_UPDATED,
        "regime_update": EventType.THESIS_EVOLVED,
    }

    # Update thesis registry
    if thesis_id in db["thesis_registry"]:
        tr = db["thesis_registry"][thesis_id]
        entry = {
            "date": d,
            "evolution_type": evolution_type,
            "description": description,
            "evidence": evidence,
            "author": author,
        }
        if updated_thesis:
            entry["updated_thesis"] = updated_thesis
            tr["current_thesis"] = updated_thesis
            pos.current_thesis = updated_thesis
        if updated_invalidation_conditions:
            entry["updated_invalidation_conditions"] = updated_invalidation_conditions
            tr["current_invalidation_conditions"] = updated_invalidation_conditions
            pos.invalidation_conditions = updated_invalidation_conditions
        tr["evolution_log"].append(entry)

    pos.evolution_count += 1
    db["positions"][ticker] = pos.to_dict()

    event = LedgerEvent(
        event_id=_new_event_id(),
        event_type=event_type_map[evolution_type],
        date=d,
        timestamp=_now_str(),
        ticker=ticker,
        thesis_id=thesis_id,
        payload={
            "evolution_type": evolution_type,
            "description": description,
            "evidence": evidence,
            "updated_thesis": updated_thesis,
            "updated_invalidation_conditions": updated_invalidation_conditions,
        },
        author=author,
        session_id=session_id,
    )
    _append_event(db, event)
    _save_db(db)
    return event


def record_dissent(
    ticker: str,
    agent: str,
    argument: str,
    bias_type: str = "analytical",        # "analytical" | "emotional_attachment" | "confirmation_bias" | "worldview_divergence"
    severity: str = "medium",
    author: str = "risk_dissent_coordinator",
    session_id: Optional[str] = None,
    date_str: Optional[str] = None,
) -> LedgerEvent:
    """
    Record a dissent argument against a position or thesis.

    Dissent is tracked permanently. Resolution is recorded separately.
    Every unresolved dissent shows up in what_were_concerns().
    """
    assert len(argument) >= 20, "Dissent argument must be at least 20 characters."
    d = date_str or _today_str()
    db = _load_db()

    if ticker not in db["positions"]:
        raise KeyError(f"Position {ticker} not found in ledger.")

    pos = PositionRecord.from_dict(db["positions"][ticker])
    thesis_id = pos.thesis_id
    dissent_id = f"DISS-{uuid.uuid4().hex[:6].upper()}"

    dissent_entry = {
        "dissent_id": dissent_id,
        "date": d,
        "agent": agent,
        "argument": argument,
        "bias_type": bias_type,
        "severity": severity,
        "resolved": False,
        "resolution_date": None,
        "resolution_note": "",
    }

    if thesis_id in db["thesis_registry"]:
        db["thesis_registry"][thesis_id]["dissent_log"].append(dissent_entry)

    pos.dissent_count += 1
    db["positions"][ticker] = pos.to_dict()

    event = LedgerEvent(
        event_id=_new_event_id(),
        event_type=EventType.DISSENT_RECORDED,
        date=d,
        timestamp=_now_str(),
        ticker=ticker,
        thesis_id=thesis_id,
        payload={
            "dissent_id": dissent_id,
            "agent": agent,
            "argument": argument,
            "bias_type": bias_type,
            "severity": severity,
        },
        author=author,
        session_id=session_id,
    )
    _append_event(db, event)
    _save_db(db)
    return event


def resolve_dissent(
    ticker: str,
    dissent_id: str,
    resolution_note: str,
    author: str = "cio",
    session_id: Optional[str] = None,
    date_str: Optional[str] = None,
) -> None:
    """Mark a dissent argument as resolved with an explanation."""
    assert len(resolution_note) >= 10, "Resolution note must be at least 10 characters."
    d = date_str or _today_str()
    db = _load_db()

    if ticker not in db["positions"]:
        raise KeyError(f"Position {ticker} not found.")

    pos = PositionRecord.from_dict(db["positions"][ticker])
    thesis_id = pos.thesis_id

    resolved = False
    if thesis_id in db["thesis_registry"]:
        for entry in db["thesis_registry"][thesis_id]["dissent_log"]:
            if entry["dissent_id"] == dissent_id:
                entry["resolved"] = True
                entry["resolution_date"] = d
                entry["resolution_note"] = resolution_note
                resolved = True
                break

    if not resolved:
        raise KeyError(f"Dissent {dissent_id} not found for {ticker}.")

    event = LedgerEvent(
        event_id=_new_event_id(),
        event_type=EventType.DISSENT_RESOLVED,
        date=d,
        timestamp=_now_str(),
        ticker=ticker,
        thesis_id=thesis_id,
        payload={"dissent_id": dissent_id, "resolution_note": resolution_note},
        author=author,
        session_id=session_id,
    )
    _append_event(db, event)
    _save_db(db)


def record_invalidation(
    ticker: str,
    reason: str,
    triggered_by: str,           # what condition was breached
    author: str = "cio",
    session_id: Optional[str] = None,
    date_str: Optional[str] = None,
) -> LedgerEvent:
    """
    Record that a position's thesis has been invalidated.

    This is separate from exiting the position — a thesis can be invalidated
    while the exit is being executed gradually.
    """
    d = date_str or _today_str()
    db = _load_db()

    if ticker not in db["positions"]:
        raise KeyError(f"Position {ticker} not found in ledger.")

    pos = PositionRecord.from_dict(db["positions"][ticker])
    thesis_id = pos.thesis_id

    invalidation_event = {
        "date": d,
        "reason": reason,
        "triggered_by": triggered_by,
        "author": author,
    }

    pos.current_lifecycle_state = "Invalidated"
    db["positions"][ticker] = pos.to_dict()

    if thesis_id in db["thesis_registry"]:
        db["thesis_registry"][thesis_id]["current_lifecycle_state"] = "Invalidated"
        db["thesis_registry"][thesis_id]["is_active"] = False
        db["thesis_registry"][thesis_id]["invalidation_event"] = invalidation_event
        db["thesis_registry"][thesis_id]["closed_date"] = d
        db["thesis_registry"][thesis_id]["lifecycle_history"].append({
            "date": d,
            "from_state": "Breakdown Risk",
            "to_state": "Invalidated",
            "reason": reason,
        })

    event = LedgerEvent(
        event_id=_new_event_id(),
        event_type=EventType.THESIS_INVALIDATED,
        date=d,
        timestamp=_now_str(),
        ticker=ticker,
        thesis_id=thesis_id,
        payload={
            "reason": reason,
            "triggered_by": triggered_by,
        },
        author=author,
        session_id=session_id,
    )
    _append_event(db, event)
    _save_db(db)
    return event


def update_lifecycle_state(
    ticker: str,
    new_state: str,
    reason: str,
    author: str = "cio",
    session_id: Optional[str] = None,
    date_str: Optional[str] = None,
) -> None:
    """Update thesis lifecycle state and record the transition."""
    valid_states = {
        "Emerging", "Confirming", "High Conviction",
        "Crowded", "Distribution Risk", "Breakdown Risk", "Invalidated",
    }
    if new_state not in valid_states:
        raise ValueError(f"Invalid lifecycle state: {new_state}")

    d = date_str or _today_str()
    db = _load_db()

    if ticker not in db["positions"]:
        raise KeyError(f"Position {ticker} not found in ledger.")

    pos = PositionRecord.from_dict(db["positions"][ticker])
    old_state = pos.current_lifecycle_state
    pos.current_lifecycle_state = new_state
    db["positions"][ticker] = pos.to_dict()

    thesis_id = pos.thesis_id
    if thesis_id in db["thesis_registry"]:
        db["thesis_registry"][thesis_id]["current_lifecycle_state"] = new_state
        db["thesis_registry"][thesis_id]["lifecycle_history"].append({
            "date": d,
            "from_state": old_state,
            "to_state": new_state,
            "reason": reason,
        })

    event_type = (
        EventType.THESIS_INVALIDATED
        if new_state == "Invalidated"
        else EventType.THESIS_EVOLVED
    )
    event = LedgerEvent(
        event_id=_new_event_id(),
        event_type=event_type,
        date=d,
        timestamp=_now_str(),
        ticker=ticker,
        thesis_id=thesis_id,
        payload={"from_state": old_state, "to_state": new_state, "reason": reason},
        author=author,
        session_id=session_id,
    )
    _append_event(db, event)
    _save_db(db)


def add_to_watchlist(
    ticker: str,
    thesis_summary: str,
    entry_triggers: list[str],
    exit_triggers: list[str],
    patience_note: str,
    author: str = "cio",
    session_id: Optional[str] = None,
    date_str: Optional[str] = None,
) -> WatchEvent:
    """Add a ticker to the watchlist with full entry/exit discipline."""
    assert len(thesis_summary) >= 20, "Thesis summary must be at least 20 characters."
    assert len(entry_triggers) >= 1, "Must specify at least one entry trigger."
    assert len(exit_triggers) >= 1, "Must specify at least one exit trigger."

    d = date_str or _today_str()
    db = _load_db()

    watch_event = WatchEvent(
        event_id=_new_event_id(),
        date=d,
        ticker=ticker,
        event_type="added",
        thesis_summary=thesis_summary,
        entry_triggers=entry_triggers,
        exit_triggers=exit_triggers,
        patience_note=patience_note,
        outcome=None,
        outcome_note=None,
        resolved_date=None,
    )

    db["watchlist_history"].setdefault(ticker, [])
    db["watchlist_history"][ticker].append(watch_event.to_dict())

    event = LedgerEvent(
        event_id=watch_event.event_id,
        event_type=EventType.WATCHLIST_ADDED,
        date=d,
        timestamp=_now_str(),
        ticker=ticker,
        thesis_id=None,
        payload={
            "thesis_summary": thesis_summary,
            "entry_triggers": entry_triggers,
            "exit_triggers": exit_triggers,
            "patience_note": patience_note,
        },
        author=author,
        session_id=session_id,
    )
    _append_event(db, event)
    _save_db(db)
    return watch_event


def resolve_watchlist(
    ticker: str,
    outcome: str,              # "triggered" | "expired" | "removed"
    outcome_note: str,
    author: str = "cio",
    session_id: Optional[str] = None,
    date_str: Optional[str] = None,
) -> None:
    """Resolve a watchlist entry — triggered (entered), expired, or manually removed."""
    assert outcome in ("triggered", "expired", "removed")
    d = date_str or _today_str()
    db = _load_db()

    if ticker not in db["watchlist_history"]:
        raise KeyError(f"No watchlist history for {ticker}.")

    # Find the most recent unresolved entry
    resolved = False
    for entry in reversed(db["watchlist_history"][ticker]):
        if entry.get("outcome") is None:
            entry["outcome"] = outcome
            entry["resolved_date"] = d
            entry["outcome_note"] = outcome_note
            resolved = True
            break

    if not resolved:
        raise KeyError(f"No unresolved watchlist entry found for {ticker}.")

    event_type_map = {
        "triggered": EventType.WATCHLIST_TRIGGERED,
        "expired": EventType.WATCHLIST_EXPIRED,
        "removed": EventType.WATCHLIST_REMOVED,
    }
    event = LedgerEvent(
        event_id=_new_event_id(),
        event_type=event_type_map[outcome],
        date=d,
        timestamp=_now_str(),
        ticker=ticker,
        thesis_id=None,
        payload={"outcome": outcome, "outcome_note": outcome_note},
        author=author,
        session_id=session_id,
    )
    _append_event(db, event)
    _save_db(db)


def record_decision(
    decision_type: str,
    question: str,
    regime: str,
    final_stance: str,
    final_confidence: int,
    allocation_change: bool,
    required_actions: list[str],
    watchlist_only: list[str],
    rationale: str,
    signals_considered: Optional[list[dict]] = None,
    specialists_consulted: Optional[list[str]] = None,
    dissent_present: bool = False,
    groupthink_alert: bool = False,
    challenge_questions: Optional[list[str]] = None,
    next_review_trigger: str = "",
    author: str = "cio",
    session_id: Optional[str] = None,
    date_str: Optional[str] = None,
) -> DecisionRecord:
    """Record every CIO decision with its full context."""
    d = date_str or _today_str()
    db = _load_db()

    decision = DecisionRecord(
        decision_id=f"DEC-{uuid.uuid4().hex[:8].upper()}",
        date=d,
        session_id=session_id,
        decision_type=decision_type,
        question=question,
        regime=regime,
        signals_considered=signals_considered or [],
        specialists_consulted=specialists_consulted or [],
        dissent_present=dissent_present,
        groupthink_alert=groupthink_alert,
        final_stance=final_stance,
        final_confidence=final_confidence,
        allocation_change=allocation_change,
        required_actions=required_actions,
        watchlist_only=watchlist_only,
        rationale=rationale,
        challenge_questions=challenge_questions or [],
        next_review_trigger=next_review_trigger,
        author=author,
    )
    db["decision_audit"].append(decision.to_dict())

    event = LedgerEvent(
        event_id=_new_event_id(),
        event_type=EventType.DECISION_RECORDED,
        date=d,
        timestamp=_now_str(),
        ticker=None,
        thesis_id=None,
        payload=decision.to_dict(),
        author=author,
        session_id=session_id,
    )
    _append_event(db, event)
    _save_db(db)
    return decision


# ---------------------------------------------------------------------------
# Query functions — the seven canonical questions
# ---------------------------------------------------------------------------

def why_do_we_own(ticker: str) -> PositionNarrative:
    """
    Why do we own this position?

    Returns the original thesis, current state, invalidation conditions,
    sizing guidance, and a summary of what has changed.
    """
    db = _load_db()
    if ticker not in db["positions"]:
        raise KeyError(f"No position record found for {ticker}.")

    pos = PositionRecord.from_dict(db["positions"][ticker])
    thesis_id = pos.thesis_id
    tr = db["thesis_registry"].get(thesis_id, {})

    # Sizing guidance
    sizing = _lifecycle_sizing_guidance(pos.current_lifecycle_state)

    # Open dissents
    open_dissents = [
        f"[{d['severity'].upper()}] {d['agent']}: {d['argument']}"
        for d in tr.get("dissent_log", [])
        if not d.get("resolved", False)
    ]

    # Key changes summary
    evo_log = tr.get("evolution_log", [])
    if not evo_log:
        changes = "Thesis unchanged since opening."
    else:
        last = evo_log[-1]
        changes = (
            f"{len(evo_log)} evolution(s). Most recent ({last['date']}): "
            f"[{last['evolution_type']}] {last['description'][:100]}"
        )

    # Exit reason
    exit_reason = None
    inv = tr.get("invalidation_event")
    if inv:
        exit_reason = f"Invalidated {inv['date']}: {inv['reason']}"

    return PositionNarrative(
        ticker=ticker,
        name=pos.name,
        is_active=pos.is_active,
        opened_date=pos.opened_date,
        original_thesis=pos.original_thesis,
        current_thesis=pos.current_thesis,
        current_lifecycle_state=pos.current_lifecycle_state,
        current_confidence=pos.current_confidence,
        invalidation_conditions=pos.invalidation_conditions,
        sizing_guidance=sizing,
        key_changes_summary=changes,
        open_dissents=open_dissents,
        exited_date=pos.exited_date,
        exit_reason=exit_reason,
    )


def what_changed(
    ticker: str,
    since_date: Optional[str] = None,
    event_types: Optional[list[str]] = None,
) -> list[LedgerEvent]:
    """
    What changed for this position (and optionally, since when)?

    Returns all ledger events for the ticker, optionally filtered by date and type.
    """
    db = _load_db()
    events = [
        LedgerEvent.from_dict(e)
        for e in db["events"]
        if e.get("ticker") == ticker
    ]
    if since_date:
        events = [e for e in events if e.date >= since_date]
    if event_types:
        events = [e for e in events if e.event_type.value in event_types]
    return sorted(events, key=lambda e: e.timestamp)


def what_were_concerns(ticker: str, include_resolved: bool = False) -> list[dict]:
    """
    What concerns / dissent arguments were raised about this position?

    By default returns only unresolved dissent. Pass include_resolved=True
    to see the full historical concern log.
    """
    db = _load_db()
    if ticker not in db["positions"]:
        raise KeyError(f"No position record for {ticker}.")

    pos = PositionRecord.from_dict(db["positions"][ticker])
    thesis_id = pos.thesis_id
    tr = db["thesis_registry"].get(thesis_id, {})
    dissents = tr.get("dissent_log", [])

    if not include_resolved:
        dissents = [d for d in dissents if not d.get("resolved", False)]

    return [
        {
            "dissent_id": d["dissent_id"],
            "date": d["date"],
            "agent": d["agent"],
            "argument": d["argument"],
            "bias_type": d["bias_type"],
            "severity": d["severity"],
            "resolved": d.get("resolved", False),
            "resolution_date": d.get("resolution_date"),
            "resolution_note": d.get("resolution_note", ""),
        }
        for d in dissents
    ]


def what_invalidated(ticker: str) -> Optional[dict]:
    """
    What caused the thesis to be invalidated?

    Returns None if the thesis is still active.
    Returns the invalidation event if the thesis was invalidated.
    """
    db = _load_db()
    if ticker not in db["positions"]:
        raise KeyError(f"No position record for {ticker}.")

    pos = PositionRecord.from_dict(db["positions"][ticker])
    thesis_id = pos.thesis_id
    tr = db["thesis_registry"].get(thesis_id, {})
    inv = tr.get("invalidation_event")
    if not inv:
        return None

    # Also attach the original invalidation conditions for context
    return {
        **inv,
        "original_invalidation_conditions": tr.get("original_invalidation_conditions", []),
        "current_invalidation_conditions": tr.get("current_invalidation_conditions", []),
        "lifecycle_at_invalidation": pos.current_lifecycle_state,
    }


def what_improved(ticker: str) -> list[dict]:
    """
    What strengthened the case for this position over time?

    Returns only 'strengthening' evolution events.
    """
    db = _load_db()
    if ticker not in db["positions"]:
        raise KeyError(f"No position record for {ticker}.")

    pos = PositionRecord.from_dict(db["positions"][ticker])
    thesis_id = pos.thesis_id
    tr = db["thesis_registry"].get(thesis_id, {})

    return [
        {
            "date": e["date"],
            "evolution_type": e["evolution_type"],
            "description": e["description"],
            "evidence": e["evidence"],
            "author": e.get("author", "system"),
        }
        for e in tr.get("evolution_log", [])
        if e.get("evolution_type") == "strengthening"
    ]


def original_thesis(ticker: str) -> Optional[dict]:
    """
    What was the original thesis when this position was opened?

    Returns all immutable inception-day fields.
    """
    db = _load_db()
    if ticker not in db["positions"]:
        return None

    pos = PositionRecord.from_dict(db["positions"][ticker])
    thesis_id = pos.thesis_id
    tr = db["thesis_registry"].get(thesis_id, {})
    if not tr:
        return None

    return {
        "thesis_id": thesis_id,
        "ticker": ticker,
        "name": pos.name,
        "opened_date": pos.opened_date,
        "original_thesis": tr.get("original_thesis", ""),
        "original_macro_context": tr.get("original_macro_context", ""),
        "original_technical_context": tr.get("original_technical_context", ""),
        "original_sentiment_context": tr.get("original_sentiment_context", ""),
        "original_expected_regime": tr.get("original_expected_regime", ""),
        "original_invalidation_conditions": tr.get("original_invalidation_conditions", []),
        "original_confidence": tr.get("original_confidence", 0),
    }


def did_thesis_evolve_correctly(ticker: str) -> ThesisEvolutionAssessment:
    """
    Did the thesis evolve in a disciplined, evidence-based way?

    Assesses:
    - Whether evolutions were supported by evidence
    - Whether confidence track matches the strengthening/weakening ratio
    - Whether invalidation conditions were upheld or rationalized away
    - Whether the thesis drifted from original without justification
    """
    db = _load_db()
    if ticker not in db["positions"]:
        raise KeyError(f"No position record for {ticker}.")

    pos = PositionRecord.from_dict(db["positions"][ticker])
    thesis_id = pos.thesis_id
    tr = db["thesis_registry"].get(thesis_id, {})

    evo_log = tr.get("evolution_log", [])
    conf_history = tr.get("confidence_history", [])
    dissent_log = tr.get("dissent_log", [])

    strengthening = sum(1 for e in evo_log if e.get("evolution_type") == "strengthening")
    weakening = sum(1 for e in evo_log if e.get("evolution_type") == "weakening")
    invalidation_updates = sum(
        1 for e in evo_log if e.get("evolution_type") == "invalidation_updated"
    )

    # Confidence trend
    if len(conf_history) < 2:
        conf_trend = "Insufficient data"
    else:
        first_c = conf_history[0]["confidence"]
        last_c = conf_history[-1]["confidence"]
        delta = last_c - first_c
        values = [c["confidence"] for c in conf_history]
        variance = (
            sum((v - sum(values) / len(values)) ** 2 for v in values) / len(values)
        )
        if variance > 200:
            conf_trend = "Volatile"
        elif delta > 10:
            conf_trend = "Rising"
        elif delta < -10:
            conf_trend = "Falling"
        else:
            conf_trend = "Stable"

    # Discipline flags
    discipline_flags: list[str] = []

    # Flag: invalidation conditions were updated many times (potential rationalization)
    if invalidation_updates >= 3:
        discipline_flags.append(
            f"Invalidation conditions updated {invalidation_updates} times — "
            "possible goal-post moving."
        )

    # Flag: weakening signals but confidence rose
    orig_conf = tr.get("original_confidence", 50)
    curr_conf = pos.current_confidence
    if weakening >= 2 and curr_conf > orig_conf + 10:
        discipline_flags.append(
            f"{weakening} weakening events recorded but confidence rose from "
            f"{orig_conf}% to {curr_conf}% — review for confirmation bias."
        )

    # Flag: unresolved dissents while confidence high
    open_dissents = [d for d in dissent_log if not d.get("resolved", False)]
    if len(open_dissents) >= 2 and curr_conf >= 70:
        discipline_flags.append(
            f"{len(open_dissents)} unresolved dissent(s) while confidence is {curr_conf}% "
            "— high conviction with open concerns warrants review."
        )

    # Flag: position invalidated but no weakening events preceded it
    inv_event = tr.get("invalidation_event")
    if inv_event and weakening == 0:
        discipline_flags.append(
            "Thesis invalidated with no prior weakening events recorded — "
            "possible surprise or monitoring failure."
        )

    # Regime accuracy
    orig_regime = tr.get("original_expected_regime", "")
    if orig_regime and orig_regime.lower() in ("unknown", "", "[manual input required]"):
        regime_accuracy = "Not assessed — no expected regime specified at inception."
    else:
        regime_accuracy = f"Original expected regime: '{orig_regime}'. Compare to actual."

    # Overall verdict
    if len(evo_log) == 0:
        verdict = "Insufficient data — no evolution events recorded."
    elif discipline_flags:
        verdict = "Drifting" if len(discipline_flags) >= 2 else "Caution"
    elif weakening > strengthening * 2:
        verdict = "Reversed"
    else:
        verdict = "Disciplined"

    assessment_narrative = (
        f"Thesis has {len(evo_log)} evolution event(s) "
        f"({strengthening} strengthening, {weakening} weakening, "
        f"{invalidation_updates} invalidation updates). "
        f"Confidence: {orig_conf}% → {curr_conf}% ({conf_trend}). "
        + (
            f"Concerns: {'; '.join(discipline_flags)}"
            if discipline_flags
            else "No major discipline flags."
        )
    )

    return ThesisEvolutionAssessment(
        ticker=ticker,
        thesis_id=thesis_id,
        overall_verdict=verdict,
        evolution_count=len(evo_log),
        strengthening_events=strengthening,
        weakening_events=weakening,
        invalidation_events=invalidation_updates,
        confidence_trend=conf_trend,
        original_confidence=orig_conf,
        current_confidence=curr_conf,
        regime_accuracy=regime_accuracy,
        discipline_flags=discipline_flags,
        assessment_narrative=assessment_narrative,
    )


# ---------------------------------------------------------------------------
# Convenience read functions
# ---------------------------------------------------------------------------

def get_position(ticker: str) -> Optional[PositionRecord]:
    db = _load_db()
    d = db["positions"].get(ticker)
    return PositionRecord.from_dict(d) if d else None


def get_all_positions(active_only: bool = True) -> list[PositionRecord]:
    db = _load_db()
    positions = [PositionRecord.from_dict(v) for v in db["positions"].values()]
    if active_only:
        positions = [p for p in positions if p.is_active]
    return positions


def get_thesis_record(thesis_id: str) -> Optional[ThesisRecord]:
    db = _load_db()
    d = db["thesis_registry"].get(thesis_id)
    return ThesisRecord.from_dict(d) if d else None


def get_confidence_timeline(ticker: str) -> list[ConfidenceSnapshot]:
    db = _load_db()
    snaps = db["confidence_timeline"].get(ticker, [])
    return [ConfidenceSnapshot(**s) for s in snaps]


def get_watchlist_history(ticker: Optional[str] = None) -> list[WatchEvent]:
    db = _load_db()
    if ticker:
        entries = db["watchlist_history"].get(ticker, [])
        return [WatchEvent.from_dict(e) for e in entries]
    all_entries = []
    for entries in db["watchlist_history"].values():
        all_entries.extend([WatchEvent.from_dict(e) for e in entries])
    return sorted(all_entries, key=lambda e: e.date)


def get_active_watchlist() -> list[WatchEvent]:
    """Return all watchlist entries that have not yet been resolved."""
    return [w for w in get_watchlist_history() if w.outcome is None]


def get_decision_audit(limit: int = 50) -> list[DecisionRecord]:
    db = _load_db()
    records = db["decision_audit"][-limit:]
    return [DecisionRecord.from_dict(d) for d in records]


def get_all_events(
    ticker: Optional[str] = None,
    event_type: Optional[EventType] = None,
    since_date: Optional[str] = None,
    limit: int = 200,
) -> list[LedgerEvent]:
    """Flexible event log query."""
    db = _load_db()
    events = [LedgerEvent.from_dict(e) for e in db["events"]]
    if ticker:
        events = [e for e in events if e.ticker == ticker]
    if event_type:
        events = [e for e in events if e.event_type == event_type]
    if since_date:
        events = [e for e in events if e.date >= since_date]
    return sorted(events, key=lambda e: e.timestamp)[-limit:]


def portfolio_summary() -> dict:
    """High-level portfolio health snapshot from the ledger."""
    db = _load_db()
    positions = [PositionRecord.from_dict(v) for v in db["positions"].values()]
    active = [p for p in positions if p.is_active]
    exited = [p for p in positions if not p.is_active]

    total_events = len(db["events"])
    total_decisions = len(db["decision_audit"])

    open_dissents = 0
    for ticker in [p.ticker for p in positions]:
        try:
            open_dissents += len(what_were_concerns(ticker, include_resolved=False))
        except Exception:
            pass

    return {
        "active_positions": len(active),
        "exited_positions": len(exited),
        "total_events": total_events,
        "total_decisions": total_decisions,
        "open_dissents": open_dissents,
        "active_watchlist_items": len(get_active_watchlist()),
        "positions": [
            {
                "ticker": p.ticker,
                "lifecycle_state": p.current_lifecycle_state,
                "confidence": p.current_confidence,
                "exposure_pct": p.current_exposure_pct,
                "trim_count": p.trim_count,
                "add_count": p.add_count,
                "dissent_count": p.dissent_count,
                "evolution_count": p.evolution_count,
            }
            for p in active
        ],
    }


def import_from_yaml(portfolio_yaml: dict, date_str: Optional[str] = None) -> list[str]:
    """
    Bootstrap the ledger from an existing current_portfolio.yaml.

    Creates position + thesis records for each position in the YAML.
    Idempotent — skips positions already in the ledger.
    Returns list of imported tickers.
    """
    imported: list[str] = []
    d = date_str or _today_str()
    db = _load_db()

    for bucket_key, bucket_data in portfolio_yaml.items():
        if not isinstance(bucket_data, dict) or "positions" not in bucket_data:
            continue
        for pos_yaml in bucket_data["positions"]:
            ticker = pos_yaml.get("ticker", "")
            if not ticker or ticker in db["positions"]:
                continue

            thesis_id = f"THESIS-{ticker}-{uuid.uuid4().hex[:6].upper()}"
            open_position(
                ticker=ticker,
                name=pos_yaml.get("name", ticker),
                bucket=pos_yaml.get("bucket", bucket_key),
                thesis_id=thesis_id,
                original_thesis=pos_yaml.get("thesis", f"No thesis recorded for {ticker}."),
                macro_context="[Imported from portfolio YAML — macro context not recorded]",
                technical_context="[Imported from portfolio YAML — technical context not recorded]",
                sentiment_context="[Imported from portfolio YAML — sentiment context not recorded]",
                expected_regime="[Unknown — imported from static YAML]",
                invalidation_conditions=[pos_yaml.get("invalidation", "Not specified")],
                initial_exposure_pct=float(pos_yaml.get("portfolio_pct", 0)),
                initial_confidence=int(pos_yaml.get("confidence", 50)),
                author="system_import",
                date_str=pos_yaml.get("opened_date", d),
                cost_basis_note=(
                    f"cost_basis_per_share={pos_yaml.get('cost_basis_per_share', 0)}"
                ),
            )
            imported.append(ticker)

    return imported
