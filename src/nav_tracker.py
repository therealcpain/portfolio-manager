"""
NAV Tracker — records and retrieves daily portfolio net asset value.
Stores snapshots in data/processed/nav_history.json.
Advisory only — no live trading.
"""

from __future__ import annotations
import json
from datetime import date, datetime
from pathlib import Path
from typing import Optional

import pandas as pd

ROOT_DIR = Path(__file__).parent.parent
NAV_FILE = ROOT_DIR / "data" / "processed" / "nav_history.json"
INCEPTION_DATE = "2026-05-13"
STARTING_CAPITAL = 100_000.0


def _load_raw() -> dict:
    if NAV_FILE.exists():
        with open(NAV_FILE) as f:
            return json.load(f)
    return {"inception_date": INCEPTION_DATE, "starting_capital": STARTING_CAPITAL, "snapshots": {}}


def _save_raw(data: dict) -> None:
    NAV_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(NAV_FILE, "w") as f:
        json.dump(data, f, indent=2)


def record_snapshot(
    nav: float,
    snapshot_date: Optional[date] = None,
    positions: Optional[dict] = None,
    confidence_score: Optional[int] = None,
    regime: Optional[str] = None,
    note: str = "",
) -> None:
    """Record a daily NAV snapshot."""
    d = str(snapshot_date or date.today())
    data = _load_raw()
    data["snapshots"][d] = {
        "nav": round(nav, 2),
        "timestamp": datetime.now().isoformat(),
        "confidence_score": confidence_score,
        "regime": regime,
        "positions": positions or {},
        "note": note,
    }
    _save_raw(data)


def get_nav_series() -> pd.Series:
    """Return NAV history as a pandas Series indexed by date."""
    data = _load_raw()
    snapshots = data.get("snapshots", {})
    if not snapshots:
        return pd.Series(dtype=float, name="Portfolio NAV")
    s = pd.Series(
        {pd.Timestamp(d): v["nav"] for d, v in snapshots.items()},
        name="Portfolio NAV",
    )
    return s.sort_index()


def get_latest_nav() -> float:
    """Get the most recent NAV value."""
    s = get_nav_series()
    if s.empty:
        return STARTING_CAPITAL
    return float(s.iloc[-1])


def get_total_return() -> dict:
    """Calculate total return vs starting capital."""
    current = get_latest_nav()
    dollar_return = current - STARTING_CAPITAL
    pct_return = (dollar_return / STARTING_CAPITAL) * 100
    return {
        "starting_capital": STARTING_CAPITAL,
        "current_nav": current,
        "dollar_return": round(dollar_return, 2),
        "pct_return": round(pct_return, 2),
        "inception_date": INCEPTION_DATE,
    }


def compute_nav_from_portfolio(portfolio_yaml: dict) -> float:
    """
    Compute current model NAV from portfolio YAML using live prices.
    Falls back to book value if prices unavailable.
    """
    from data_loader import get_current_price

    total = 0.0
    summary = portfolio_yaml.get("summary", {})

    # Cash / STRC (book value)
    cash = float(summary.get("cash_and_strc", 0))
    total += cash

    # Equity positions
    for bucket in ["core_structural", "tactical_strategic", "options_convexity", "experimental", "defensive_reserve"]:
        bucket_data = portfolio_yaml.get(bucket, {})
        for pos in bucket_data.get("positions", []):
            ticker = pos.get("ticker", "")
            shares = pos.get("shares", 0)
            book_value = float(pos.get("market_value", 0))

            if shares and shares > 0 and ticker not in ("STRC_PROXY", "STRC"):
                price = get_current_price(ticker)
                if price > 0:
                    total += shares * price
                    continue
            # fallback to book value
            total += book_value

    return round(total, 2)


def initialize_inception_snapshot(portfolio_yaml: dict) -> None:
    """Create inception day NAV snapshot if none exists."""
    data = _load_raw()
    if INCEPTION_DATE not in data.get("snapshots", {}):
        nav = compute_nav_from_portfolio(portfolio_yaml)
        if nav == 0:
            nav = STARTING_CAPITAL
        record_snapshot(
            nav=nav,
            snapshot_date=date.fromisoformat(INCEPTION_DATE),
            note="Inception snapshot",
        )
