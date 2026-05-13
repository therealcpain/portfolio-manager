"""
allocation_tracker.py — Daily allocation snapshot store.

Persists target allocations from each CIO run and computes deltas
vs yesterday, 1 week ago, and 1 month ago.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field, asdict
from datetime import date, timedelta
from pathlib import Path
from typing import Optional

ROOT_DIR = Path(__file__).parent.parent
SNAPSHOTS_PATH = ROOT_DIR / "data" / "processed" / "allocation_snapshots.json"


@dataclass
class PositionSnapshot:
    ticker: str
    target_pct: float
    action: str        # ADD | TRIM | HOLD | EXIT | INITIATE
    confidence: Optional[int]
    reason: str


@dataclass
class AllocationSnapshot:
    date: str
    positions: list[PositionSnapshot]
    overall_confidence: int
    regime: str
    raw_cio_text: str = ""

    def by_ticker(self) -> dict[str, PositionSnapshot]:
        return {p.ticker: p for p in self.positions}

    def total_pct(self) -> float:
        return sum(p.target_pct for p in self.positions)


@dataclass
class PositionDelta:
    ticker: str
    current_pct: float
    prev_1d: Optional[float]
    prev_1w: Optional[float]
    prev_1m: Optional[float]
    delta_1d: Optional[float]
    delta_1w: Optional[float]
    delta_1m: Optional[float]
    action: str
    confidence: Optional[int]
    reason: str

    def arrow(self, delta: Optional[float]) -> str:
        if delta is None or abs(delta) < 0.5:
            return "—"
        return f"+{delta:.1f}%" if delta > 0 else f"{delta:.1f}%"


def _load_snapshots() -> list[dict]:
    if not SNAPSHOTS_PATH.exists():
        return []
    try:
        return json.loads(SNAPSHOTS_PATH.read_text())
    except Exception:
        return []


def _save_snapshots(snapshots: list[dict]) -> None:
    SNAPSHOTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    SNAPSHOTS_PATH.write_text(json.dumps(snapshots, indent=2))


def save_snapshot(snap: AllocationSnapshot) -> None:
    snapshots = _load_snapshots()
    # Replace existing entry for same date
    snapshots = [s for s in snapshots if s.get("date") != snap.date]
    snapshots.append(asdict(snap))
    # Keep last 90 days
    snapshots = sorted(snapshots, key=lambda s: s["date"], reverse=True)[:90]
    _save_snapshots(snapshots)


def load_snapshot(date_str: str) -> Optional[AllocationSnapshot]:
    for s in _load_snapshots():
        if s.get("date") == date_str:
            positions = [PositionSnapshot(**p) for p in s.get("positions", [])]
            return AllocationSnapshot(
                date=s["date"],
                positions=positions,
                overall_confidence=s.get("overall_confidence", 0),
                regime=s.get("regime", ""),
                raw_cio_text=s.get("raw_cio_text", ""),
            )
    return None


def load_nearest_snapshot(target_date: str) -> Optional[AllocationSnapshot]:
    """Load the snapshot closest to (but not after) target_date."""
    snapshots = sorted(_load_snapshots(), key=lambda s: s["date"], reverse=True)
    for s in snapshots:
        if s["date"] <= target_date:
            positions = [PositionSnapshot(**p) for p in s.get("positions", [])]
            return AllocationSnapshot(
                date=s["date"],
                positions=positions,
                overall_confidence=s.get("overall_confidence", 0),
                regime=s.get("regime", ""),
            )
    return None


def compute_deltas(current: AllocationSnapshot) -> list[PositionDelta]:
    today = date.fromisoformat(current.date)
    snap_1d = load_nearest_snapshot((today - timedelta(days=1)).isoformat())
    snap_1w = load_nearest_snapshot((today - timedelta(days=7)).isoformat())
    snap_1m = load_nearest_snapshot((today - timedelta(days=30)).isoformat())

    def pct(snap: Optional[AllocationSnapshot], ticker: str) -> Optional[float]:
        if snap is None:
            return None
        return snap.by_ticker().get(ticker, PositionSnapshot(ticker, 0, "—", None, "")).target_pct

    deltas = []
    for pos in sorted(current.positions, key=lambda p: -p.target_pct):
        p1d = pct(snap_1d, pos.ticker)
        p1w = pct(snap_1w, pos.ticker)
        p1m = pct(snap_1m, pos.ticker)
        deltas.append(PositionDelta(
            ticker=pos.ticker,
            current_pct=pos.target_pct,
            prev_1d=p1d,
            prev_1w=p1w,
            prev_1m=p1m,
            delta_1d=round(pos.target_pct - p1d, 1) if p1d is not None else None,
            delta_1w=round(pos.target_pct - p1w, 1) if p1w is not None else None,
            delta_1m=round(pos.target_pct - p1m, 1) if p1m is not None else None,
            action=pos.action,
            confidence=pos.confidence,
            reason=pos.reason,
        ))
    return deltas


# ---------------------------------------------------------------------------
# Parse target allocation from raw CIO text
# ---------------------------------------------------------------------------

def parse_allocation_from_cio(raw: str, date_str: str, regime: str,
                               overall_confidence: int) -> Optional[AllocationSnapshot]:
    """
    Extract the TARGET ALLOCATION table from CIO output.
    Expects rows like: TICKER | PCT% | ACTION | CONF% | REASON
    Returns None if no allocation block found.
    """
    positions = []

    # Find the allocation block
    block_match = re.search(
        r"TARGET ALLOCATION.*?```(.*?)```",
        raw, re.DOTALL | re.IGNORECASE
    )
    if not block_match:
        # Try without code fences
        block_match = re.search(
            r"TARGET ALLOCATION\s*\n((?:.*\|.*\n?)+)",
            raw, re.IGNORECASE
        )

    if block_match:
        block = block_match.group(1)
        for line in block.splitlines():
            line = line.strip()
            if not line or line.startswith("TICKER") or set(line) <= set("-| "):
                continue
            parts = [p.strip() for p in line.split("|")]
            if len(parts) < 3:
                continue
            ticker = parts[0].upper()
            if not ticker or ticker in ("TICKER",):
                continue
            # Parse percentage
            pct_str = re.sub(r"[^\d.]", "", parts[1])
            try:
                pct = float(pct_str)
            except ValueError:
                continue
            # Parse action (ADD, TRIM, HOLD, EXIT, INITIATE, RAISE)
            action_raw = parts[2].upper() if len(parts) > 2 else "HOLD"
            action = next((a for a in ("ADD", "TRIM", "HOLD", "EXIT", "INITIATE", "RAISE", "REDUCE")
                           if a in action_raw), "HOLD")
            # Parse confidence
            conf = None
            if len(parts) > 3:
                conf_str = re.sub(r"[^\d]", "", parts[3])
                conf = int(conf_str) if conf_str else None
            # Reason
            reason = parts[4].strip() if len(parts) > 4 else ""

            positions.append(PositionSnapshot(
                ticker=ticker,
                target_pct=pct,
                action=action,
                confidence=conf,
                reason=reason[:120],
            ))

    if not positions:
        return None

    return AllocationSnapshot(
        date=date_str,
        positions=positions,
        overall_confidence=overall_confidence,
        regime=regime,
        raw_cio_text=raw[:2000],
    )
