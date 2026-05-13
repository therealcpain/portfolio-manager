"""
Thesis Memory — Phase 3 Governance.

Persistent strategic memory for every position thesis.
Separates signal (observation) from action (decision) explicitly.
Supports "watch but don't act" discipline with setup tracking and trigger conditions.

Core design principles:
- Every thesis has full historical context — never lose why you owned something
- Signal ≠ Action. Observation ≠ Decision. Momentum improving ≠ Buy more.
- Patience is a position. Wait for confirmation; avoid forcing trades.
- Invalidation must be defined BEFORE the trade, not rationalized after.
- Thesis evolution is tracked — how and why a thesis changed over time.

Advisory only — no live trading.
"""

from __future__ import annotations
import json
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, date, timedelta
from enum import Enum
from pathlib import Path
from typing import Optional

ROOT_DIR = Path(__file__).parent.parent
THESIS_MEMORY_PATH = ROOT_DIR / "data" / "processed" / "thesis_memory.json"

DISCLAIMER = "ADVISORY ONLY. All outputs are simulated. Not financial advice."

# ── Lifecycle states (matches thesis_engine.ThesisState) ─────────────────────

class LifecycleState(str, Enum):
    EMERGING = "Emerging"
    CONFIRMING = "Confirming"
    HIGH_CONVICTION = "High Conviction"
    CROWDED = "Crowded"
    DISTRIBUTION_RISK = "Distribution Risk"
    BREAKDOWN_RISK = "Breakdown Risk"
    INVALIDATED = "Invalidated"


TERMINAL_STATES = {LifecycleState.INVALIDATED.value}
WARNING_STATES = {
    LifecycleState.CROWDED.value,
    LifecycleState.DISTRIBUTION_RISK.value,
    LifecycleState.BREAKDOWN_RISK.value,
}
ACTIVE_STATES = {
    LifecycleState.EMERGING.value,
    LifecycleState.CONFIRMING.value,
    LifecycleState.HIGH_CONVICTION.value,
}

LIFECYCLE_SIZING_GUIDANCE = {
    LifecycleState.EMERGING.value:           "1/3 to 1/2 of target — thesis forming, not confirmed",
    LifecycleState.CONFIRMING.value:         "1/2 to 3/4 of target — evidence accumulating",
    LifecycleState.HIGH_CONVICTION.value:    "Full target — thesis confirmed across macro/technical/sentiment",
    LifecycleState.CROWDED.value:            "50–75% of peak — begin gradual trimming",
    LifecycleState.DISTRIBUTION_RISK.value:  "25–50% of peak — trim on bounces, prepare exit",
    LifecycleState.BREAKDOWN_RISK.value:     "10–20% max — active exit plan; consider protection",
    LifecycleState.INVALIDATED.value:        "Zero — exit fully; document lessons",
}


# ── Thesis evolution types ────────────────────────────────────────────────────

class ThesisEvolutionType(str, Enum):
    REFINEMENT = "refinement"           # Thesis stated more precisely
    STRENGTHENING = "strengthening"     # New evidence supports thesis
    WEAKENING = "weakening"             # Evidence against thesis emerges
    CONTEXT_CHANGE = "context_change"   # Macro/technical/sentiment backdrop changed
    REGIME_UPDATE = "regime_update"     # Expected market regime revised
    INVALIDATION_UPDATED = "invalidation_updated"  # Invalidation conditions revised


# ── Review trigger types ──────────────────────────────────────────────────────

class ReviewTriggerType(str, Enum):
    MACRO_REGIME_CHANGE = "macro_regime_change"
    TECHNICAL_BREAKDOWN = "technical_breakdown"
    LIQUIDITY_CONTRACTION = "liquidity_contraction"
    SENTIMENT_EUPHORIA = "sentiment_euphoria"
    VALUATION_COMPRESSION = "valuation_compression"
    INVALIDATION_OF_ASSUMPTIONS = "invalidation_of_assumptions"


TRIGGER_SEVERITY = {
    ReviewTriggerType.MACRO_REGIME_CHANGE.value:       "high",
    ReviewTriggerType.TECHNICAL_BREAKDOWN.value:        "high",
    ReviewTriggerType.LIQUIDITY_CONTRACTION.value:      "high",
    ReviewTriggerType.SENTIMENT_EUPHORIA.value:         "medium",
    ReviewTriggerType.VALUATION_COMPRESSION.value:      "medium",
    ReviewTriggerType.INVALIDATION_OF_ASSUMPTIONS.value: "critical",
}


# ── Dissent types ─────────────────────────────────────────────────────────────

class DissentType(str, Enum):
    DIRECTIONAL = "directional"     # Disagrees with bullish/bearish stance
    TIMING = "timing"               # Right direction, wrong timing
    SIZING = "sizing"               # Direction ok, position too large/small
    RISK = "risk"                   # Additional risks not captured in thesis
    REGIME = "regime"               # Assumes wrong market regime
    THESIS_QUALITY = "thesis_quality"  # Thesis premise is flawed


# ── Watch setup status ────────────────────────────────────────────────────────

class WatchStatus(str, Enum):
    WATCHING = "watching"           # Monitoring for entry conditions
    TRIGGERED = "triggered"         # Entry conditions met; awaiting action decision
    ACTED = "acted"                 # Action was taken on this setup
    EXPIRED = "expired"             # Setup expired without triggering
    INVALIDATED = "invalidated"     # Setup premise is no longer valid


# ── Sub-record dataclasses ────────────────────────────────────────────────────

@dataclass
class ConfidenceSnapshot:
    date: str
    confidence_score: int           # 0–100
    regime: str
    key_factors: list[str]          # factors driving this confidence level
    note: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class DissentRecord:
    id: str
    date: str
    agent: str
    dissent_type: str               # DissentType value
    description: str
    resolved: bool = False
    resolution_notes: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class ThesisEvolutionEntry:
    id: str
    date: str
    evolution_type: str             # ThesisEvolutionType value
    description: str                # What changed and why
    triggered_by: str               # What prompted this update

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class LifecycleStateChange:
    from_state: str
    to_state: str
    date: str
    reason: str
    triggered_by: str               # agent, review trigger type, or human

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class PositionAdjustment:
    id: str
    date: str
    action: str                     # add / reduce / exit / rebalance
    size_pct: float                 # percentage of portfolio affected
    reason: str
    confidence_at_time: int
    signal_id: str = ""             # linked signal if applicable

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class ReviewAlert:
    position_id: str
    ticker: str
    trigger_type: str               # ReviewTriggerType value
    description: str
    severity: str                   # critical / high / medium / low
    recommended_action: str
    generated_at: str

    def to_dict(self) -> dict:
        return asdict(self)


# ── Core thesis memory ────────────────────────────────────────────────────────

@dataclass
class ThesisMemory:
    """
    Complete persistent memory for a single position thesis.
    This is the source of truth for WHY we own something,
    how that thesis has evolved, and what would invalidate it.
    """
    position_id: str
    ticker: str
    name: str

    # Context at thesis inception (all 11 required fields)
    original_thesis: str            # Core thesis premise — immutable after creation
    macro_context: str              # Macro backdrop when thesis was opened
    technical_context: str          # Technical setup when thesis was opened
    sentiment_context: str          # Sentiment conditions when thesis was opened
    expected_regime: str            # Market regime the thesis is designed for
    invalidation_conditions: list[str]  # Specific conditions that invalidate the thesis

    # Dynamic state
    lifecycle_state: str            # Current LifecycleState value
    lifecycle_history: list[dict]   # list of LifecycleStateChange.to_dict()
    thesis_evolution: list[dict]    # list of ThesisEvolutionEntry.to_dict()
    historical_adjustments: list[dict]  # list of PositionAdjustment.to_dict()
    associated_dissent: list[dict]  # list of DissentRecord.to_dict()
    confidence_history: list[dict]  # list of ConfidenceSnapshot.to_dict()

    # Metadata
    opened_date: str
    last_updated: str
    is_active: bool = True

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "ThesisMemory":
        return cls(**{k: d[k] for k in cls.__dataclass_fields__ if k in d})

    @property
    def current_confidence(self) -> Optional[int]:
        if not self.confidence_history:
            return None
        return self.confidence_history[-1].get("confidence_score")

    @property
    def is_warning(self) -> bool:
        return self.lifecycle_state in WARNING_STATES

    @property
    def is_terminal(self) -> bool:
        return self.lifecycle_state in TERMINAL_STATES

    @property
    def unresolved_dissent(self) -> list[dict]:
        return [d for d in self.associated_dissent if not d.get("resolved", False)]

    def sizing_guidance(self) -> str:
        return LIFECYCLE_SIZING_GUIDANCE.get(self.lifecycle_state, "Unknown state")

    def daily_status(self) -> dict:
        return {
            "position_id": self.position_id,
            "ticker": self.ticker,
            "name": self.name,
            "lifecycle_state": self.lifecycle_state,
            "sizing_guidance": self.sizing_guidance(),
            "is_warning": self.is_warning,
            "is_terminal": self.is_terminal,
            "current_confidence": self.current_confidence,
            "unresolved_dissent_count": len(self.unresolved_dissent),
            "thesis_evolution_count": len(self.thesis_evolution),
            "last_updated": self.last_updated,
            "expected_regime": self.expected_regime,
        }


# ── Signal/Action record (explicit separation) ────────────────────────────────

@dataclass
class SignalObservation:
    """
    Pure observation — what was seen in the market.
    Must be stated as fact, not conclusion.

    Example: "BTC 4-hour RSI divergence confirmed. Momentum improving."
    NOT: "BTC looks like it's going to break out."
    """
    id: str
    date: str
    ticker: str
    signal_type: str                # from SignalType constants
    signal_description: str         # What was observed. Fact, not conclusion.
    regime_at_signal: str
    source: str                     # agent or data source


@dataclass
class ActionDecision:
    """
    Explicit decision about what to do (or NOT do) about a signal.
    Must state the decision AND the reason for NOT acting if applicable.

    Example:
    signal_description: "BTC momentum improving on 4-hour chart."
    action_taken: "No portfolio change."
    action_rationale: "Resistance at $95k unconfirmed. Wait for weekly close above."
    watch_triggers: ["Weekly close above $95k with volume >150% of 20d avg"]
    """
    signal_id: str
    date: str
    ticker: str
    action_taken: str               # What was decided (including "No action")
    action_rationale: str           # Why this decision (especially important for no-action)
    watch_triggers: list[str]       # Conditions that would change this decision
    requires_immediate_action: bool = False  # True only for invalidation/breakdown
    sizing_implication: str = ""    # If action involves sizing, state it explicitly


@dataclass
class SignalActionRecord:
    """
    Paired signal + action. The action may be 'no action' — that is a valid decision.
    The pairing makes the discipline explicit: every observation must be consciously
    addressed, not reflexively traded.
    """
    signal: SignalObservation
    action: ActionDecision

    def to_dict(self) -> dict:
        return {
            "signal": asdict(self.signal),
            "action": asdict(self.action),
        }

    def summary(self) -> dict:
        return {
            "date": self.signal.date,
            "ticker": self.signal.ticker,
            "signal": self.signal.signal_description,
            "action": self.action.action_taken,
            "rationale": self.action.action_rationale,
            "watch_triggers": self.action.watch_triggers,
            "requires_immediate_action": self.action.requires_immediate_action,
        }


# ── Watch setup (patience mechanism) ─────────────────────────────────────────

@dataclass
class WatchSetup:
    """
    A defined setup we are monitoring but not yet acting on.
    Patience is a position — define the trigger conditions before they arrive.

    Example:
    - Watching MSTR for a break above $600 with volume confirmation
    - Entry triggers: Weekly close above $600, MSTR/BTC ratio improving
    - Exit triggers: Weekly close below $520, BTC dominance falling below 55%
    - Patience note: "Do not enter on intraday spike — wait for weekly confirmation"
    """
    id: str
    ticker: str
    name: str
    setup_description: str          # What setup we're monitoring
    entry_triggers: list[str]       # Conditions that must be met to enter
    exit_triggers: list[str]        # Conditions that invalidate the setup
    patience_note: str              # Explicit reminder of WHY we're waiting
    status: str                     # WatchStatus value
    created_date: str
    expiry_date: Optional[str]      # Optional: setup expires if not triggered by this date
    triggered_date: Optional[str] = None
    acted_date: Optional[str] = None
    invalidation_reason: str = ""
    position_id: str = ""           # Linked to ThesisMemory if related to existing position

    def to_dict(self) -> dict:
        return asdict(self)

    @property
    def is_active(self) -> bool:
        return self.status == WatchStatus.WATCHING.value

    @property
    def days_watching(self) -> int:
        try:
            start = datetime.strptime(self.created_date, "%Y-%m-%d").date()
            return (date.today() - start).days
        except (ValueError, TypeError):
            return 0


# ── Persistence ───────────────────────────────────────────────────────────────

def _load_db() -> dict:
    if not THESIS_MEMORY_PATH.exists():
        return {"theses": {}, "signals": [], "watch_setups": []}
    with open(THESIS_MEMORY_PATH) as f:
        return json.load(f)


def _save_db(db: dict) -> None:
    THESIS_MEMORY_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(THESIS_MEMORY_PATH, "w") as f:
        json.dump(db, f, indent=2, default=str)


def load_all_theses() -> list[ThesisMemory]:
    db = _load_db()
    return [ThesisMemory.from_dict(v) for v in db.get("theses", {}).values()]


def load_thesis(position_id: str) -> Optional[ThesisMemory]:
    db = _load_db()
    raw = db.get("theses", {}).get(position_id)
    return ThesisMemory.from_dict(raw) if raw else None


def _save_thesis(thesis: ThesisMemory) -> None:
    db = _load_db()
    db.setdefault("theses", {})[thesis.position_id] = thesis.to_dict()
    _save_db(db)


def load_watch_setups() -> list[WatchSetup]:
    db = _load_db()
    return [WatchSetup(**d) for d in db.get("watch_setups", [])]


def _save_watch_setup(setup: WatchSetup) -> None:
    db = _load_db()
    setups = db.get("watch_setups", [])
    setups = [s for s in setups if s["id"] != setup.id]
    setups.append(setup.to_dict())
    db["watch_setups"] = setups
    _save_db(db)


def load_signal_records() -> list[dict]:
    db = _load_db()
    return db.get("signals", [])


def _save_signal_record(record: SignalActionRecord) -> None:
    db = _load_db()
    db.setdefault("signals", []).append(record.to_dict())
    _save_db(db)


# ── Public API: Thesis lifecycle ──────────────────────────────────────────────

def create_thesis(
    ticker: str,
    name: str,
    original_thesis: str,
    macro_context: str,
    technical_context: str,
    sentiment_context: str,
    expected_regime: str,
    invalidation_conditions: list[str],
    initial_confidence: int = 50,
    position_id: Optional[str] = None,
) -> ThesisMemory:
    """
    Open a new persistent thesis memory record.
    All context fields are captured at inception — never lost.
    """
    assert len(original_thesis.strip()) >= 50, "Thesis is too brief — state the full argument."
    assert len(invalidation_conditions) >= 1, "At least one invalidation condition is required."

    pid = position_id or f"POS-{ticker.upper()}-{uuid.uuid4().hex[:6].upper()}"
    now_date = datetime.now().strftime("%Y-%m-%d")

    thesis = ThesisMemory(
        position_id=pid,
        ticker=ticker.upper(),
        name=name,
        original_thesis=original_thesis,
        macro_context=macro_context,
        technical_context=technical_context,
        sentiment_context=sentiment_context,
        expected_regime=expected_regime,
        invalidation_conditions=invalidation_conditions,
        lifecycle_state=LifecycleState.EMERGING.value,
        lifecycle_history=[LifecycleStateChange(
            from_state="none",
            to_state=LifecycleState.EMERGING.value,
            date=now_date,
            reason="Thesis opened.",
            triggered_by="human",
        ).to_dict()],
        thesis_evolution=[],
        historical_adjustments=[],
        associated_dissent=[],
        confidence_history=[ConfidenceSnapshot(
            date=now_date,
            confidence_score=initial_confidence,
            regime=expected_regime,
            key_factors=["Initial assessment at thesis open"],
        ).to_dict()],
        opened_date=now_date,
        last_updated=now_date,
    )
    _save_thesis(thesis)
    return thesis


def update_lifecycle_state(
    position_id: str,
    new_state: str,
    reason: str,
    triggered_by: str,
) -> ThesisMemory:
    """
    Transition a thesis to a new lifecycle state.
    INVALIDATED is terminal — no further transitions allowed.
    """
    assert new_state in {s.value for s in LifecycleState}, f"Invalid state: {new_state}"

    thesis = load_thesis(position_id)
    if thesis is None:
        raise KeyError(f"Thesis '{position_id}' not found.")
    if thesis.lifecycle_state in TERMINAL_STATES:
        raise ValueError(
            f"Thesis '{position_id}' is in terminal state '{thesis.lifecycle_state}'. "
            "Cannot transition from a terminal state."
        )

    now_date = datetime.now().strftime("%Y-%m-%d")
    change = LifecycleStateChange(
        from_state=thesis.lifecycle_state,
        to_state=new_state,
        date=now_date,
        reason=reason,
        triggered_by=triggered_by,
    )
    thesis.lifecycle_history.append(change.to_dict())
    thesis.lifecycle_state = new_state
    thesis.last_updated = now_date
    _save_thesis(thesis)
    return thesis


def add_thesis_evolution(
    position_id: str,
    evolution_type: str,
    description: str,
    triggered_by: str,
) -> ThesisMemory:
    """Record how the thesis understanding has evolved."""
    assert evolution_type in {e.value for e in ThesisEvolutionType}, f"Invalid type: {evolution_type}"

    thesis = load_thesis(position_id)
    if thesis is None:
        raise KeyError(f"Thesis '{position_id}' not found.")

    entry = ThesisEvolutionEntry(
        id=f"EVO-{uuid.uuid4().hex[:8].upper()}",
        date=datetime.now().strftime("%Y-%m-%d"),
        evolution_type=evolution_type,
        description=description,
        triggered_by=triggered_by,
    )
    thesis.thesis_evolution.append(entry.to_dict())
    thesis.last_updated = datetime.now().strftime("%Y-%m-%d")
    _save_thesis(thesis)
    return thesis


def record_confidence_snapshot(
    position_id: str,
    confidence_score: int,
    regime: str,
    key_factors: list[str],
    note: str = "",
) -> ThesisMemory:
    """Record a confidence snapshot for daily tracking."""
    assert 0 <= confidence_score <= 100, "Confidence must be 0–100."

    thesis = load_thesis(position_id)
    if thesis is None:
        raise KeyError(f"Thesis '{position_id}' not found.")

    snapshot = ConfidenceSnapshot(
        date=datetime.now().strftime("%Y-%m-%d"),
        confidence_score=confidence_score,
        regime=regime,
        key_factors=key_factors,
        note=note,
    )
    thesis.confidence_history.append(snapshot.to_dict())
    thesis.last_updated = datetime.now().strftime("%Y-%m-%d")
    _save_thesis(thesis)
    return thesis


def record_dissent(
    position_id: str,
    agent: str,
    dissent_type: str,
    description: str,
) -> ThesisMemory:
    """Record a dissent against the thesis from a committee agent."""
    assert dissent_type in {d.value for d in DissentType}, f"Invalid dissent type: {dissent_type}"

    thesis = load_thesis(position_id)
    if thesis is None:
        raise KeyError(f"Thesis '{position_id}' not found.")

    entry = DissentRecord(
        id=f"DIS-{uuid.uuid4().hex[:8].upper()}",
        date=datetime.now().strftime("%Y-%m-%d"),
        agent=agent,
        dissent_type=dissent_type,
        description=description,
    )
    thesis.associated_dissent.append(entry.to_dict())
    thesis.last_updated = datetime.now().strftime("%Y-%m-%d")
    _save_thesis(thesis)
    return thesis


def resolve_dissent(
    position_id: str,
    dissent_id: str,
    resolution_notes: str,
) -> ThesisMemory:
    """Mark a dissent as resolved with notes."""
    thesis = load_thesis(position_id)
    if thesis is None:
        raise KeyError(f"Thesis '{position_id}' not found.")

    for d in thesis.associated_dissent:
        if d.get("id") == dissent_id:
            d["resolved"] = True
            d["resolution_notes"] = resolution_notes
            break
    else:
        raise KeyError(f"Dissent '{dissent_id}' not found in thesis '{position_id}'.")

    thesis.last_updated = datetime.now().strftime("%Y-%m-%d")
    _save_thesis(thesis)
    return thesis


def record_position_adjustment(
    position_id: str,
    action: str,
    size_pct: float,
    reason: str,
    confidence_at_time: int,
    signal_id: str = "",
) -> ThesisMemory:
    """Record a position adjustment with the reasoning at time of decision."""
    assert action in ("add", "reduce", "exit", "rebalance"), f"Invalid action: {action}"
    assert 0.0 <= size_pct <= 100.0

    thesis = load_thesis(position_id)
    if thesis is None:
        raise KeyError(f"Thesis '{position_id}' not found.")

    adj = PositionAdjustment(
        id=f"ADJ-{uuid.uuid4().hex[:8].upper()}",
        date=datetime.now().strftime("%Y-%m-%d"),
        action=action,
        size_pct=round(size_pct, 2),
        reason=reason,
        confidence_at_time=confidence_at_time,
        signal_id=signal_id,
    )
    thesis.historical_adjustments.append(adj.to_dict())
    thesis.last_updated = datetime.now().strftime("%Y-%m-%d")

    if action == "exit":
        thesis.is_active = False

    _save_thesis(thesis)
    return thesis


# ── Public API: Signal/Action separation ─────────────────────────────────────

def record_signal_action(
    ticker: str,
    signal_type: str,
    signal_description: str,
    action_taken: str,
    action_rationale: str,
    watch_triggers: list[str],
    regime_at_signal: str = "",
    source: str = "committee",
    requires_immediate_action: bool = False,
    sizing_implication: str = "",
) -> SignalActionRecord:
    """
    Record a signal (observation) paired with an explicit action decision.

    The action may be 'No portfolio change' — this is a valid and important decision.
    Every signal MUST be paired with an explicit action or no-action rationale.
    This pairing is what prevents reflexive overtrading.

    Example:
        signal_description="BTC 4h RSI divergence confirmed. Momentum improving."
        action_taken="No portfolio change."
        action_rationale="Weekly resistance at $95k unconfirmed. Waiting for close above."
        watch_triggers=["Weekly close above $95k with volume >150% of 20-day average"]
    """
    now = datetime.now().strftime("%Y-%m-%d")
    signal_id = f"SIG-{ticker.upper()[:4]}-{uuid.uuid4().hex[:6].upper()}"

    signal = SignalObservation(
        id=signal_id,
        date=now,
        ticker=ticker.upper(),
        signal_type=signal_type,
        signal_description=signal_description,
        regime_at_signal=regime_at_signal,
        source=source,
    )
    action = ActionDecision(
        signal_id=signal_id,
        date=now,
        ticker=ticker.upper(),
        action_taken=action_taken,
        action_rationale=action_rationale,
        watch_triggers=watch_triggers,
        requires_immediate_action=requires_immediate_action,
        sizing_implication=sizing_implication,
    )
    record = SignalActionRecord(signal=signal, action=action)
    _save_signal_record(record)
    return record


# ── Public API: Watch setups ──────────────────────────────────────────────────

def create_watch_setup(
    ticker: str,
    name: str,
    setup_description: str,
    entry_triggers: list[str],
    exit_triggers: list[str],
    patience_note: str,
    expiry_days: Optional[int] = None,
    position_id: str = "",
) -> WatchSetup:
    """
    Create a watch setup — a defined situation we are monitoring but NOT acting on yet.
    Patience is a position. Define triggers before they arrive.

    Example:
        setup_description="MSTR consolidation above $450 support — potential breakout setup"
        entry_triggers=["Weekly close above $600", "MSTR/BTC ratio above 30-day average"]
        exit_triggers=["Weekly close below $420", "BTC drops below $75k"]
        patience_note="Do not enter on intraday spikes — wait for weekly confirmation only"
    """
    assert len(entry_triggers) >= 1, "At least one entry trigger is required."
    assert len(exit_triggers) >= 1, "At least one exit trigger is required."
    assert len(patience_note.strip()) >= 10, "Patience note must explain WHY we are waiting."

    now = datetime.now().strftime("%Y-%m-%d")
    expiry = None
    if expiry_days:
        expiry = (datetime.now() + timedelta(days=expiry_days)).strftime("%Y-%m-%d")

    setup = WatchSetup(
        id=f"WATCH-{ticker.upper()[:4]}-{uuid.uuid4().hex[:6].upper()}",
        ticker=ticker.upper(),
        name=name,
        setup_description=setup_description,
        entry_triggers=entry_triggers,
        exit_triggers=exit_triggers,
        patience_note=patience_note,
        status=WatchStatus.WATCHING.value,
        created_date=now,
        expiry_date=expiry,
        position_id=position_id,
    )
    _save_watch_setup(setup)
    return setup


def trigger_watch_setup(setup_id: str, note: str = "") -> WatchSetup:
    """Mark a watch setup as triggered (entry conditions met)."""
    setups = load_watch_setups()
    setup = next((s for s in setups if s.id == setup_id), None)
    if setup is None:
        raise KeyError(f"Watch setup '{setup_id}' not found.")
    setup.status = WatchStatus.TRIGGERED.value
    setup.triggered_date = datetime.now().strftime("%Y-%m-%d")
    _save_watch_setup(setup)
    return setup


def expire_watch_setup(setup_id: str, reason: str = "Conditions not met within expiry window.") -> WatchSetup:
    """Expire a watch setup that did not trigger."""
    setups = load_watch_setups()
    setup = next((s for s in setups if s.id == setup_id), None)
    if setup is None:
        raise KeyError(f"Watch setup '{setup_id}' not found.")
    setup.status = WatchStatus.EXPIRED.value
    setup.invalidation_reason = reason
    _save_watch_setup(setup)
    return setup


def invalidate_watch_setup(setup_id: str, reason: str) -> WatchSetup:
    """Invalidate a watch setup — the premise is no longer valid."""
    setups = load_watch_setups()
    setup = next((s for s in setups if s.id == setup_id), None)
    if setup is None:
        raise KeyError(f"Watch setup '{setup_id}' not found.")
    setup.status = WatchStatus.INVALIDATED.value
    setup.invalidation_reason = reason
    _save_watch_setup(setup)
    return setup


# ── Review trigger checking ───────────────────────────────────────────────────

def check_review_triggers(
    thesis: ThesisMemory,
    current_regime: Optional[str] = None,
    vix_level: Optional[float] = None,
    is_below_support: bool = False,
    sentiment_score: Optional[float] = None,   # 0–100; >80 = euphoria
    liquidity_contracting: bool = False,
    valuation_compressed: bool = False,
    assumptions_violated: Optional[list[str]] = None,
) -> list[ReviewAlert]:
    """
    Check whether any review triggers have fired for a thesis.
    Returns a list of ReviewAlerts; empty list = no triggers.
    """
    alerts: list[ReviewAlert] = []
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    def _alert(trigger_type: str, description: str, recommended_action: str) -> ReviewAlert:
        return ReviewAlert(
            position_id=thesis.position_id,
            ticker=thesis.ticker,
            trigger_type=trigger_type,
            description=description,
            severity=TRIGGER_SEVERITY.get(trigger_type, "medium"),
            recommended_action=recommended_action,
            generated_at=now,
        )

    # 1. Macro regime change
    if current_regime and thesis.expected_regime and current_regime != thesis.expected_regime:
        alerts.append(_alert(
            ReviewTriggerType.MACRO_REGIME_CHANGE.value,
            f"Thesis designed for '{thesis.expected_regime}' but current regime is '{current_regime}'.",
            "Review thesis validity in this regime. Update expected_regime or escalate to Distribution Risk.",
        ))

    # 2. Technical breakdown
    if is_below_support:
        alerts.append(_alert(
            ReviewTriggerType.TECHNICAL_BREAKDOWN.value,
            f"{thesis.ticker} has broken below a key support level.",
            "Evaluate whether this triggers any invalidation conditions. If so, escalate to Breakdown Risk.",
        ))

    # 3. Liquidity contraction
    if liquidity_contracting:
        alerts.append(_alert(
            ReviewTriggerType.LIQUIDITY_CONTRACTION.value,
            "Market liquidity is contracting. Risk assets typically reprice in liquidity contractions.",
            "Reassess position sizing. Review whether thesis holds in a tightening environment.",
        ))

    # 4. Sentiment euphoria
    if sentiment_score is not None and sentiment_score > 80:
        alerts.append(_alert(
            ReviewTriggerType.SENTIMENT_EUPHORIA.value,
            f"Sentiment score of {sentiment_score:.0f}/100 is in euphoric territory (>80).",
            "Thesis may be crowded. Review for Crowded or Distribution Risk state transition.",
        ))

    # 5. Valuation compression
    if valuation_compressed:
        alerts.append(_alert(
            ReviewTriggerType.VALUATION_COMPRESSION.value,
            f"{thesis.ticker} valuation metrics have compressed significantly.",
            "Reassess thesis asymmetry. A compressed valuation changes the risk/reward profile.",
        ))

    # 6. Invalidation of core assumptions
    if assumptions_violated:
        for assumption in assumptions_violated:
            # Check if it matches a known invalidation condition
            is_listed = any(
                assumption.lower() in cond.lower() or cond.lower() in assumption.lower()
                for cond in thesis.invalidation_conditions
            )
            alerts.append(_alert(
                ReviewTriggerType.INVALIDATION_OF_ASSUMPTIONS.value,
                f"Core assumption violated: '{assumption}'"
                + (" [matches thesis invalidation condition]" if is_listed else ""),
                "Immediately review thesis. If assumption is core, escalate to Invalidated state.",
            ))

    # Also fire if already in a warning/terminal state to ensure daily visibility
    if thesis.lifecycle_state in WARNING_STATES and vix_level and vix_level > 30:
        alerts.append(_alert(
            ReviewTriggerType.LIQUIDITY_CONTRACTION.value,
            f"{thesis.ticker} is in '{thesis.lifecycle_state}' with elevated VIX ({vix_level:.0f}).",
            "Warning state + elevated VIX = elevated exit urgency. Review immediately.",
        ))

    return alerts


# ── Daily report ──────────────────────────────────────────────────────────────

def generate_thesis_daily_report(
    current_regime: Optional[str] = None,
    **trigger_kwargs,
) -> dict:
    """
    Generate the daily thesis memory update report for all active theses.
    Includes lifecycle status, confidence trends, review alerts, and watch setups.
    """
    theses = load_all_theses()
    active = [t for t in theses if t.is_active]
    inactive = [t for t in theses if not t.is_active]

    position_reports = []
    all_alerts: list[dict] = []

    for thesis in active:
        alerts = check_review_triggers(thesis, current_regime=current_regime, **trigger_kwargs)
        all_alerts.extend([a.to_dict() for a in alerts])
        position_reports.append({
            **thesis.daily_status(),
            "alerts": [a.to_dict() for a in alerts],
        })

    # Sort: warnings first, then by confidence descending
    position_reports.sort(
        key=lambda r: (0 if r["is_warning"] else 1, -(r.get("current_confidence") or 0))
    )

    watch_setups = load_watch_setups()
    active_watches = [s.to_dict() for s in watch_setups if s.is_active]
    triggered_watches = [s.to_dict() for s in watch_setups if s.status == WatchStatus.TRIGGERED.value]

    return {
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "current_regime": current_regime or "unknown",
        "active_theses": len(active),
        "inactive_theses": len(inactive),
        "positions": position_reports,
        "total_alerts": len(all_alerts),
        "critical_alerts": [a for a in all_alerts if a.get("severity") == "critical"],
        "high_alerts": [a for a in all_alerts if a.get("severity") == "high"],
        "active_watch_setups": active_watches,
        "triggered_watch_setups": triggered_watches,
        "signal_records_count": len(load_signal_records()),
        "disciplined_patience_note": (
            "Signals require explicit action decisions. "
            "'Watch but don't act' is a valid and important decision. "
            "Every observation must be addressed, not reflexively traded."
        ),
    }
