"""
Signal vs Action Engine — enforces separation of signal from action.
Prevents overtrading. Every signal must justify an action explicitly.
Implements schemas/signal_action_schema.yaml.
Advisory only — no live trading.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from datetime import date
from enum import Enum
from typing import Optional


class SignalType(str, Enum):
    # Macro
    LIQUIDITY_EXPANSION = "Liquidity_Expansion"
    LIQUIDITY_CONTRACTION = "Liquidity_Contraction"
    FED_PIVOT = "Fed_Pivot_Signal"
    RECESSION_RISK_RISING = "Recession_Risk_Rising"
    INFLATION_REACCELERATION = "Inflation_Re_Acceleration"

    # Technical
    BREAKOUT_CONFIRMED = "Breakout_Above_Resistance"
    BREAKDOWN_CONFIRMED = "Breakdown_Below_Support"
    RSI_DIVERGENCE_BEARISH = "RSI_Divergence_Bearish"
    RSI_DIVERGENCE_BULLISH = "RSI_Divergence_Bullish"
    VOLUME_CONFIRMED_MOVE = "Volume_Confirmed_Move"
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


class ActionType(str, Enum):
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
    TAKE_PARTIAL_PROFIT_OPTION = "Take_Partial_Profit_Option"
    MOVE_TO_STRC = "Move_To_STRC"
    WATCHLIST_ADD = "Watchlist_Add"


class SignalStrength(str, Enum):
    WEAK = "Weak"
    MODERATE = "Moderate"
    STRONG = "Strong"
    VERY_STRONG = "Very Strong"


class Urgency(str, Enum):
    HIGH = "High"
    MEDIUM = "Medium"
    LOW = "Low"


@dataclass
class Signal:
    id: str
    date: str
    asset: str
    signal_type: SignalType
    strength: SignalStrength
    source_agent: str
    description: str  # What is happening — factual, not prescriptive
    timeframe: str  # Tactical | Strategic | Structural
    confirmation_required: bool = True
    confirmation_status: str = "Pending"


@dataclass
class Action:
    id: str
    signal_id: str
    date: str
    action: ActionType
    asset: str
    size_description: str  # e.g. "25% of position" or "$5,000"
    rationale: str  # Why act NOW — specific, not generic
    why_not_earlier: str = ""
    why_not_later: str = ""
    urgency: Urgency = Urgency.MEDIUM
    invalidation_of_action: str = ""


@dataclass
class SignalActionRecord:
    signal: Signal
    action: Optional[Action] = None
    no_action_reason: str = ""  # If signal present but no action taken

    def is_signal_without_action(self) -> bool:
        return self.action is None

    def summary(self) -> dict:
        return {
            "signal": self.signal.signal_type.value,
            "asset": self.signal.asset,
            "strength": self.signal.strength.value,
            "action": self.action.action.value if self.action else "No Action",
            "no_action_reason": self.no_action_reason,
            "urgency": self.action.urgency.value if self.action else "N/A",
        }


def validate_action_has_rationale(action: Action) -> list[str]:
    """Validate that an action has the required fields. Returns list of issues."""
    issues = []
    if not action.rationale or len(action.rationale) < 20:
        issues.append("Rationale is too brief — must explain WHY NOW specifically.")
    if not action.invalidation_of_action:
        issues.append("Missing invalidation condition — what would prove this action wrong?")
    if action.action in {ActionType.OPEN_OPTION, ActionType.BUY_FULL} and not action.size_description:
        issues.append("Missing size — required for buy and options actions.")
    return issues


RSI_DIVERGENCE_DEFAULT_ACTION = ActionType.WAIT_FOR_CONFIRMATION
RSI_DIVERGENCE_RATIONALE = (
    "RSI divergence at resistance per investor preference: "
    "trim, wait, or require breakout confirmation over 1–2 weeks."
)
