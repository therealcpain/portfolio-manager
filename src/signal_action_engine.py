"""
Signal vs Action Engine — Phase 2.
Persistent JSON log of all signals and actions.
Enforces separation of signal from action. Prevents overtrading.
Advisory only — no live trading.
"""

from __future__ import annotations
import json
from dataclasses import dataclass, field, asdict
from datetime import date, datetime
from pathlib import Path
from typing import Optional

ROOT_DIR = Path(__file__).parent.parent
SIGNAL_LOG_FILE = ROOT_DIR / "data" / "processed" / "signal_log.json"


# ─── Enums as string constants ────────────────────────────────────────────────

class SignalType:
    # Macro
    LIQUIDITY_EXPANSION = "Liquidity_Expansion"
    LIQUIDITY_CONTRACTION = "Liquidity_Contraction"
    FED_PIVOT = "Fed_Pivot_Signal"
    RECESSION_RISK_RISING = "Recession_Risk_Rising"
    INFLATION_REACCEL = "Inflation_Re_Acceleration"
    # Technical
    BREAKOUT_CONFIRMED = "Breakout_Above_Resistance"
    BREAKDOWN_CONFIRMED = "Breakdown_Below_Support"
    RSI_DIVERGENCE_BEARISH = "RSI_Divergence_Bearish"
    RSI_DIVERGENCE_BULLISH = "RSI_Divergence_Bullish"
    VOLUME_CONFIRMED = "Volume_Confirmed_Move"
    LOW_VOLUME_WARNING = "Low_Volume_Warning"
    # Momentum
    MOMENTUM_BREAKOUT_EARLY = "Momentum_Breakout_Early"
    MOMENTUM_FADING = "Momentum_Fading"
    MOMENTUM_EXHAUSTION = "Momentum_Exhaustion"
    # Sentiment
    EXTREME_FEAR = "Extreme_Fear"
    EXTREME_GREED = "Extreme_Greed"
    CAPITULATION = "Capitulation"
    EUPHORIA = "Euphoria"
    CROWDED_TRADE = "Crowded_Trade_Detected"
    RETAIL_MANIA = "Retail_Mania"
    # Options
    OPTIONS_DECAY_ALERT = "Options_Decay_Alert"
    PROFIT_TARGET_HIT = "Profit_Target_Hit"
    INVALIDATION_TRIGGERED = "Invalidation_Triggered"
    # Risk
    CONCENTRATION_RISK = "Concentration_Risk_Flag"
    CATASTROPHIC_RISK = "Catastrophic_Risk_Alert"


class ActionType:
    BUY_FULL = "Buy_Full"
    BUY_PARTIAL = "Buy_Partial"
    BUY_ADD = "Buy_Add"
    SELL_FULL = "Sell_Full"
    SELL_TRIM = "Sell_Trim"
    HOLD = "Hold"
    WATCH = "Watch"
    WAIT_FOR_CONFIRMATION = "Wait_For_Confirmation"
    OPEN_OPTION = "Open_Option"
    CLOSE_OPTION = "Close_Option"
    ROLL_OPTION = "Roll_Option"
    TAKE_PARTIAL_PROFIT = "Take_Partial_Profit_Option"
    MOVE_TO_STRC = "Move_To_STRC"
    WATCHLIST_ADD = "Watchlist_Add"


# ─── Data classes ─────────────────────────────────────────────────────────────

@dataclass
class Signal:
    id: str
    date: str
    asset: str
    signal_type: str
    strength: str  # Weak | Moderate | Strong | Very Strong
    source_agent: str
    description: str
    timeframe: str  # Tactical | Strategic | Structural
    confirmation_required: bool = True
    confirmation_status: str = "Pending"  # Pending | Confirmed | Not Confirmed | Expired


@dataclass
class Action:
    id: str
    signal_id: str
    date: str
    action: str
    asset: str
    size_description: str
    rationale: str
    why_not_earlier: str = ""
    why_not_later: str = ""
    urgency: str = "Medium"  # High | Medium | Low
    invalidation_of_action: str = ""


@dataclass
class SignalActionRecord:
    signal: Signal
    action: Optional[Action] = None
    no_action_reason: str = ""

    def summary(self) -> dict:
        return {
            "signal_id": self.signal.id,
            "signal": self.signal.signal_type,
            "asset": self.signal.asset,
            "strength": self.signal.strength,
            "action": self.action.action if self.action else "No Action",
            "no_action_reason": self.no_action_reason,
            "urgency": self.action.urgency if self.action else "N/A",
        }


# ─── Persistence ──────────────────────────────────────────────────────────────

def _load() -> dict:
    if SIGNAL_LOG_FILE.exists():
        with open(SIGNAL_LOG_FILE) as f:
            return json.load(f)
    return {"signals": [], "actions": [], "records": []}


def _save(data: dict) -> None:
    SIGNAL_LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(SIGNAL_LOG_FILE, "w") as f:
        json.dump(data, f, indent=2)


def log_signal(signal: Signal) -> None:
    data = _load()
    data["signals"].append(asdict(signal))
    _save(data)


def log_action(action: Action) -> None:
    data = _load()
    data["actions"].append(asdict(action))
    _save(data)


def log_record(record: SignalActionRecord) -> None:
    data = _load()
    log_signal(record.signal)
    if record.action:
        log_action(record.action)
    data["records"].append({
        "signal_id": record.signal.id,
        "action_id": record.action.id if record.action else None,
        "no_action_reason": record.no_action_reason,
        "timestamp": datetime.now().isoformat(),
    })
    _save(data)


# ─── Query helpers ────────────────────────────────────────────────────────────

def get_signals_for_asset(asset: str) -> list[dict]:
    return [s for s in _load()["signals"] if s["asset"] == asset]


def get_pending_confirmations() -> list[dict]:
    return [s for s in _load()["signals"] if s.get("confirmation_status") == "Pending"]


def get_no_action_signals(lookback_days: int = 30) -> list[dict]:
    """Signals where no action was taken — review for missed opportunities."""
    data = _load()
    records = data.get("records", [])
    no_action = [r for r in records if r.get("action_id") is None]
    return no_action[-20:]  # last 20


def get_todays_signals() -> list[dict]:
    today = str(date.today())
    return [s for s in _load()["signals"] if s.get("date") == today]


def get_signal_action_table(limit: int = 20) -> list[dict]:
    """Return the last N signal/action pairs for reporting."""
    data = _load()
    signals_by_id = {s["id"]: s for s in data.get("signals", [])}
    actions_by_signal = {a["signal_id"]: a for a in data.get("actions", [])}

    result = []
    for record in reversed(data.get("records", []))[:limit]:
        sig_id = record.get("signal_id")
        sig = signals_by_id.get(sig_id, {})
        act = actions_by_signal.get(sig_id)
        result.append({
            "date": sig.get("date", ""),
            "asset": sig.get("asset", ""),
            "signal": sig.get("signal_type", ""),
            "strength": sig.get("strength", ""),
            "action": act["action"] if act else "No Action",
            "no_action_reason": record.get("no_action_reason", ""),
            "urgency": act.get("urgency", "N/A") if act else "N/A",
        })
    return result


# ─── Validation ───────────────────────────────────────────────────────────────

RSI_DIVERGENCE_SIGNALS = {SignalType.RSI_DIVERGENCE_BEARISH, SignalType.RSI_DIVERGENCE_BULLISH}


def validate_action(action: Action) -> list[str]:
    """Validate action has required fields. Returns list of issues."""
    issues = []
    if not action.rationale or len(action.rationale) < 15:
        issues.append("Rationale too brief — must explain WHY NOW specifically.")
    if not action.invalidation_of_action:
        issues.append("Missing invalidation condition.")
    if action.action in (ActionType.OPEN_OPTION, ActionType.BUY_FULL, ActionType.BUY_ADD) and not action.size_description:
        issues.append("Missing size for buy/options action.")
    return issues


def rsi_divergence_default_action(asset: str, signal_id: str) -> Action:
    """Per investor preference: RSI divergence at resistance → wait for confirmation."""
    return Action(
        id=f"ACT-RSI-{signal_id}",
        signal_id=signal_id,
        date=str(date.today()),
        action=ActionType.WAIT_FOR_CONFIRMATION,
        asset=asset,
        size_description="No action until confirmation",
        rationale=(
            "RSI divergence at resistance per investor preference: "
            "trim, wait, or require breakout confirmation over 1–2 weeks before adding."
        ),
        urgency="Medium",
        invalidation_of_action="RSI resets and price breaks out with volume confirmation",
    )
