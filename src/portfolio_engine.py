"""
Portfolio Engine — core portfolio state management.
Reads/writes portfolio YAML. Calculates allocations, bucket health, drift.
Phase 1: manual data. Phase 2: simulation. Phase 3: live data.
Advisory only — no live trading.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional
import yaml

from config import load_portfolio, load_config, STARTING_CAPITAL, ADVISORY_DISCLAIMER


@dataclass
class Position:
    ticker: str
    name: str
    bucket: str
    market_value: float
    portfolio_pct: float
    thesis_lifecycle: str
    time_horizon: str
    thesis: str
    invalidation: str
    cost_basis_per_share: float = 0.0
    current_price: float = 0.0
    shares: int = 0
    unrealized_pnl: float = 0.0
    unrealized_pnl_pct: float = 0.0


@dataclass
class PortfolioState:
    total_value: float
    cash_and_strc: float
    options_premium_at_risk: float
    positions: list[Position] = field(default_factory=list)
    confidence_score: int = 0
    regime: str = "[LIVE DATA REQUIRED]"
    as_of_date: str = ""

    @property
    def total_equity_value(self) -> float:
        return sum(p.market_value for p in self.positions if "option" not in p.bucket)

    @property
    def bucket_allocations(self) -> dict[str, float]:
        buckets: dict[str, float] = {}
        for pos in self.positions:
            buckets[pos.bucket] = buckets.get(pos.bucket, 0) + pos.market_value
        return {k: v / self.total_value * 100 for k, v in buckets.items()}

    def is_bucket_in_range(self, bucket: str) -> bool:
        """Check if a bucket allocation is within target range."""
        config = load_config()["portfolio"]["buckets"]
        pct = self.bucket_allocations.get(bucket, 0)
        bucket_config = config.get(bucket, {})
        min_pct = bucket_config.get("target_min", 0)
        max_pct = bucket_config.get("target_max", 100)
        return min_pct <= pct <= max_pct

    def get_concentration_flags(self, single_name_threshold: float = 15.0) -> list[str]:
        """Flag any positions above single-name concentration threshold."""
        flags = []
        for pos in self.positions:
            if pos.portfolio_pct > single_name_threshold:
                flags.append(
                    f"CONCENTRATION: {pos.ticker} at {pos.portfolio_pct:.1f}% "
                    f"(threshold: {single_name_threshold}%)"
                )
        return flags


def load_portfolio_state() -> PortfolioState:
    """Load current portfolio from YAML into PortfolioState."""
    raw = load_portfolio()
    positions = []

    for bucket_key in ["core_structural", "tactical_strategic", "options_convexity", "experimental", "defensive_reserve"]:
        bucket_data = raw.get(bucket_key, {})
        for pos_data in bucket_data.get("positions", []):
            pos = Position(
                ticker=pos_data.get("ticker", ""),
                name=pos_data.get("name", ""),
                bucket=bucket_key,
                market_value=float(pos_data.get("market_value", 0)),
                portfolio_pct=float(pos_data.get("portfolio_pct", 0)),
                thesis_lifecycle=pos_data.get("thesis_lifecycle", "Unknown"),
                time_horizon=pos_data.get("time_horizon", "Unknown"),
                thesis=pos_data.get("thesis", ""),
                invalidation=pos_data.get("invalidation", ""),
                cost_basis_per_share=float(pos_data.get("cost_basis_per_share", 0)),
                current_price=float(pos_data.get("current_price", 0)),
            )
            positions.append(pos)

    summary = raw.get("summary", {})
    return PortfolioState(
        total_value=float(summary.get("total_market_value", STARTING_CAPITAL)),
        cash_and_strc=float(summary.get("cash_and_strc", 0)),
        options_premium_at_risk=float(summary.get("options_premium_at_risk", 0)),
        positions=positions,
        confidence_score=int(summary.get("portfolio_confidence_score", 0)),
        regime=summary.get("regime", "[LIVE DATA REQUIRED]"),
        as_of_date=raw.get("metadata", {}).get("as_of_date", ""),
    )


def calculate_total_return(
    current_value: float,
    starting_capital: float = STARTING_CAPITAL,
) -> dict:
    """Calculate total return vs starting capital."""
    dollar_return = current_value - starting_capital
    pct_return = (dollar_return / starting_capital) * 100
    return {
        "starting_capital": starting_capital,
        "current_value": current_value,
        "dollar_return": dollar_return,
        "pct_return": round(pct_return, 2),
    }


def get_portfolio_summary(state: PortfolioState) -> dict:
    """Generate a human-readable portfolio summary."""
    return {
        "disclaimer": ADVISORY_DISCLAIMER,
        "as_of_date": state.as_of_date,
        "total_value": state.total_value,
        "cash_and_strc": state.cash_and_strc,
        "options_at_risk": state.options_premium_at_risk,
        "confidence_score": state.confidence_score,
        "regime": state.regime,
        "bucket_allocations": state.bucket_allocations,
        "concentration_flags": state.get_concentration_flags(),
        "position_count": len(state.positions),
        "total_return": calculate_total_return(state.total_value),
        "note": "Phase 1 — all values are placeholders until live data integrated in Phase 3.",
    }
