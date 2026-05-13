"""Tests for signal_action_engine.py"""

import sys
import tempfile
import json
from pathlib import Path

# Point signal log at a temp file for testing
import os
os.environ["SIGNAL_LOG_OVERRIDE"] = ""

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from signal_action_engine import (
    Signal, Action, SignalActionRecord,
    validate_action, rsi_divergence_default_action,
    SignalType, ActionType,
)


def _make_signal(signal_type=SignalType.RSI_DIVERGENCE_BEARISH, asset="GLD") -> Signal:
    return Signal(
        id="SIG-TEST-001",
        date="2026-05-13",
        asset=asset,
        signal_type=signal_type,
        strength="Strong",
        source_agent="technical_chart_expert",
        description="RSI divergence at resistance.",
        timeframe="Tactical",
    )


def _make_valid_action(signal_id="SIG-TEST-001") -> Action:
    return Action(
        id="ACT-TEST-001",
        signal_id=signal_id,
        date="2026-05-13",
        action=ActionType.WAIT_FOR_CONFIRMATION,
        asset="GLD",
        size_description="No action until confirmation",
        rationale="RSI divergence at resistance — wait per investor preference.",
        invalidation_of_action="RSI resets with volume breakout.",
        urgency="Medium",
    )


def test_validate_action_valid():
    action = _make_valid_action()
    issues = validate_action(action)
    assert len(issues) == 0


def test_validate_action_missing_rationale():
    action = _make_valid_action()
    action.rationale = "Too short"
    issues = validate_action(action)
    assert any("rationale" in i.lower() for i in issues)


def test_validate_action_missing_invalidation():
    action = _make_valid_action()
    action.invalidation_of_action = ""
    issues = validate_action(action)
    assert any("invalidation" in i.lower() for i in issues)


def test_validate_action_buy_without_size():
    action = _make_valid_action()
    action.action = ActionType.BUY_FULL
    action.size_description = ""
    issues = validate_action(action)
    assert any("size" in i.lower() for i in issues)


def test_rsi_divergence_default_action():
    action = rsi_divergence_default_action("GLD", "SIG-001")
    assert action.action == ActionType.WAIT_FOR_CONFIRMATION
    assert "RSI" in action.rationale
    issues = validate_action(action)
    assert len(issues) == 0


def test_signal_action_record_summary():
    sig = _make_signal()
    act = _make_valid_action()
    record = SignalActionRecord(signal=sig, action=act)
    summary = record.summary()
    assert summary["asset"] == "GLD"
    assert summary["action"] == ActionType.WAIT_FOR_CONFIRMATION


def test_no_action_record():
    sig = _make_signal()
    record = SignalActionRecord(signal=sig, action=None, no_action_reason="Signal weak, awaiting confirmation.")
    assert record.signal.signal_type == SignalType.RSI_DIVERGENCE_BEARISH
    summary = record.summary()
    assert summary["action"] == "No Action"
