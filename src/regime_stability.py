"""
regime_stability.py — Track regime history and compute flip stability.

Persists daily regime classifications to data/processed/regime_history.json.
Requires 3 consecutive days of a new regime before it's "confirmed" as a flip.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, asdict
from datetime import date, timedelta
from pathlib import Path
from typing import Optional

ROOT_DIR = Path(__file__).parent.parent
HISTORY_PATH = ROOT_DIR / "data" / "processed" / "regime_history.json"
CONFIRMATION_DAYS = 3  # days at new regime before flip is "official"


@dataclass
class RegimeDayRecord:
    date: str
    regime: str
    confidence: int


@dataclass
class RegimeStability:
    current_regime: str
    days_at_regime: int
    is_stable: bool                    # True if confirmed ≥ CONFIRMATION_DAYS
    pending_flip: Optional[str]        # new regime candidate if not yet confirmed
    pending_days: int                  # days we've seen the candidate
    history: list[RegimeDayRecord]     # last 30 days, newest first
    status_label: str                  # human-readable for report header


def _load() -> list[dict]:
    if not HISTORY_PATH.exists():
        return []
    try:
        return json.loads(HISTORY_PATH.read_text())
    except Exception:
        return []


def _save(records: list[dict]) -> None:
    HISTORY_PATH.parent.mkdir(parents=True, exist_ok=True)
    HISTORY_PATH.write_text(json.dumps(records, indent=2))


def record_regime(date_str: str, regime: str, confidence: int) -> None:
    """Append today's regime to history (replaces any existing entry for same date)."""
    records = _load()
    records = [r for r in records if r.get("date") != date_str]
    records.append({"date": date_str, "regime": regime, "confidence": confidence})
    records = sorted(records, key=lambda r: r["date"], reverse=True)[:90]
    _save(records)


def get_stability(as_of: Optional[str] = None) -> RegimeStability:
    """
    Compute regime stability as of `as_of` date (defaults to today).
    """
    target = as_of or str(date.today())
    records = _load()
    # Only look at records on or before target date, newest first
    relevant = [r for r in records if r.get("date", "") <= target]
    relevant = sorted(relevant, key=lambda r: r["date"], reverse=True)

    if not relevant:
        empty = RegimeDayRecord(date=target, regime="UNKNOWN", confidence=0)
        return RegimeStability(
            current_regime="UNKNOWN",
            days_at_regime=0,
            is_stable=False,
            pending_flip=None,
            pending_days=0,
            history=[empty],
            status_label="No history — first run",
        )

    # The "current" regime is whatever we recorded most recently
    # (may be today, or the last recorded day if today hasn't run yet)
    latest = relevant[0]
    current_regime = latest["regime"]

    # Count consecutive days at current regime (from newest backward)
    days_at = 0
    for r in relevant:
        if r["regime"] == current_regime:
            days_at += 1
        else:
            break

    is_stable = days_at >= CONFIRMATION_DAYS

    # Check for pending flip: look at the most recent entry that is NOT current_regime
    # If there are recent entries with a different regime after a current-regime run, that's a flip candidate
    # Actually: look at the last CONFIRMATION_DAYS entries — if they're not all current_regime, something is pending
    recent_window = relevant[:CONFIRMATION_DAYS]
    non_current = [r for r in recent_window if r["regime"] != current_regime]

    if non_current and days_at < CONFIRMATION_DAYS:
        # We're in the middle of a potential flip: current_regime hasn't been confirmed yet
        # The regime before the current run is the "old" one
        prior_regimes = [r["regime"] for r in relevant[days_at:] if r["regime"] != current_regime]
        prior_regime  = prior_regimes[0] if prior_regimes else "UNKNOWN"
        # In this case: "pending_flip" = current_regime (trying to flip to it)
        # The stable one is still prior_regime
        pending_flip = current_regime
        pending_days = days_at
        # Override: show prior regime as "current" until confirmed
        confirmed_regime = prior_regime
        confirmed_days   = len([r for r in relevant[days_at:] if r["regime"] == prior_regime])
    else:
        confirmed_regime = current_regime
        confirmed_days   = days_at
        pending_flip     = None
        pending_days     = 0

    # Build status label
    if pending_flip:
        label = (
            f"Day {confirmed_days}  ·  ⚠ pending flip → {pending_flip.replace('_',' ')} "
            f"({pending_days}/{CONFIRMATION_DAYS} days)"
        )
    else:
        label = f"Day {confirmed_days}"
        if confirmed_days >= 30:
            label += "  ·  Entrenched"
        elif confirmed_days >= 10:
            label += "  ·  Established"
        elif confirmed_days >= CONFIRMATION_DAYS:
            label += "  ·  Confirmed"

    history = [RegimeDayRecord(**r) for r in relevant[:30]]

    return RegimeStability(
        current_regime=confirmed_regime,
        days_at_regime=confirmed_days,
        is_stable=is_stable,
        pending_flip=pending_flip,
        pending_days=pending_days,
        history=history,
        status_label=label,
    )
