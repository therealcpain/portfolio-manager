"""
Portfolio Intelligence — Phase 3.

Evolutionary learning from alternative portfolio performance.
Conservative by design: understand WHY, not just THAT, portfolios outperform.

Key principles:
- Minimum 10 observations before drawing conclusions
- Regime-conditional analysis (bull/bear/sideways performance differs)
- Drawdown and benchmark-relative comparison, not just raw return
- Learning proposals require evidence base — no pattern from N<10
- 90-day outperformance trigger is constitutional mandate (Article VIII)
Advisory only — no live trading.
"""

from __future__ import annotations
import json
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

import pandas as pd
import numpy as np

ROOT_DIR = Path(__file__).parent.parent
INTELLIGENCE_LOG_PATH = ROOT_DIR / "data" / "processed" / "alternative_portfolios" / "intelligence_log.json"

MIN_OBSERVATIONS_FOR_CONCLUSION = 10
OUTPERFORMANCE_REVIEW_DAYS = 90
UNDERPERFORMANCE_ALERT_THRESHOLD_PCT = -10.0  # trigger review if >10% behind CIO
CONSERVATIVE_LEARNING_NOTE = (
    "NOTE: Based on N<{n} observations. Treat as tentative signal, not conclusion."
)


# ── Regime classification ─────────────────────────────────────────────────

def classify_regime(
    spy_return_20d: float,
    vix_level: Optional[float] = None,
    credit_spread_bps: Optional[float] = None,
) -> str:
    """
    Classify current market regime from available signals.
    Returns one of: bull, bear, sideways, risk_off, stagflation, reflation.
    """
    if spy_return_20d > 0.05:
        regime = "bull"
    elif spy_return_20d < -0.05:
        regime = "bear" if (vix_level is None or vix_level < 40) else "risk_off"
    else:
        regime = "sideways"

    # Override for stagflation signature (high inflation proxy — not directly measurable here)
    # Caller can pass regime directly if FRED data is available

    return regime


# ── Performance attribution ────────────────────────────────────────────────

@dataclass
class RegimePerformance:
    regime: str
    observations: int
    portfolio_return_pct: float
    cio_return_pct: float
    alpha_pct: float
    max_drawdown_pct: float
    win_rate_pct: float    # % of periods portfolio beat CIO
    note: str = ""

    def to_dict(self) -> dict:
        return {
            "regime": self.regime,
            "observations": self.observations,
            "portfolio_return_pct": round(self.portfolio_return_pct, 4),
            "cio_return_pct": round(self.cio_return_pct, 4),
            "alpha_pct": round(self.alpha_pct, 4),
            "max_drawdown_pct": round(self.max_drawdown_pct, 4),
            "win_rate_pct": round(self.win_rate_pct, 2),
            "note": self.note,
        }


@dataclass
class WhyAnalysis:
    """Conservative causal attribution of performance vs CIO."""
    portfolio_id: str
    period_start: str
    period_end: str
    n_observations: int
    is_conclusive: bool          # False if n_observations < MIN_OBSERVATIONS_FOR_CONCLUSION

    # Attribution factors
    asset_selection_contribution: float   # % pts from asset picks vs CIO
    concentration_contribution: float     # % pts from being more/less concentrated
    regime_fit_contribution: float        # % pts from operating in intended regime
    cash_drag_contribution: float         # % pts from cash/STRC weighting

    # What the analysis found
    primary_driver: str                   # "asset_selection" | "regime_fit" | "concentration" | "cash_drag" | "unclear"
    confidence_in_attribution: str        # "high" | "medium" | "low"
    key_finding: str                      # 1–2 sentence plain-language summary
    caveats: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "portfolio_id": self.portfolio_id,
            "period_start": self.period_start,
            "period_end": self.period_end,
            "n_observations": self.n_observations,
            "is_conclusive": self.is_conclusive,
            "asset_selection_contribution_pct": round(self.asset_selection_contribution, 4),
            "concentration_contribution_pct": round(self.concentration_contribution, 4),
            "regime_fit_contribution_pct": round(self.regime_fit_contribution, 4),
            "cash_drag_contribution_pct": round(self.cash_drag_contribution, 4),
            "primary_driver": self.primary_driver,
            "confidence_in_attribution": self.confidence_in_attribution,
            "key_finding": self.key_finding,
            "caveats": self.caveats,
        }


def analyze_regime_performance(
    portfolio_nav: pd.Series,
    cio_nav: pd.Series,
    spy_nav: pd.Series,
) -> list[RegimePerformance]:
    """
    Break portfolio performance down by market regime.
    Returns one RegimePerformance per regime observed.
    """
    if portfolio_nav.empty or cio_nav.empty or spy_nav.empty:
        return []

    # Align series
    combined = pd.DataFrame({
        "portfolio": portfolio_nav,
        "cio": cio_nav,
        "spy": spy_nav,
    }).dropna()

    if len(combined) < 2:
        return []

    # SPY 20-day rolling return as regime signal
    spy_20d = combined["spy"].pct_change(20).fillna(0)
    regimes = spy_20d.apply(lambda r: classify_regime(r))

    results = []
    for regime_label in regimes.unique():
        mask = regimes == regime_label
        subset = combined[mask]
        n = len(subset)

        if n < 2:
            continue

        port_ret = (subset["portfolio"].iloc[-1] / subset["portfolio"].iloc[0] - 1) * 100
        cio_ret = (subset["cio"].iloc[-1] / subset["cio"].iloc[0] - 1) * 100
        alpha = port_ret - cio_ret

        # Drawdown
        peak = subset["portfolio"].cummax()
        drawdown = ((subset["portfolio"] - peak) / peak).min() * 100

        # Win rate: % of daily periods where portfolio beat CIO
        port_daily = subset["portfolio"].pct_change().dropna()
        cio_daily = subset["cio"].pct_change().dropna()
        aligned = pd.concat([port_daily, cio_daily], axis=1).dropna()
        win_rate = (aligned.iloc[:, 0] > aligned.iloc[:, 1]).mean() * 100 if len(aligned) > 0 else 0.0

        note = ""
        if n < MIN_OBSERVATIONS_FOR_CONCLUSION:
            note = CONSERVATIVE_LEARNING_NOTE.format(n=MIN_OBSERVATIONS_FOR_CONCLUSION)

        results.append(RegimePerformance(
            regime=regime_label,
            observations=n,
            portfolio_return_pct=round(port_ret, 4),
            cio_return_pct=round(cio_ret, 4),
            alpha_pct=round(alpha, 4),
            max_drawdown_pct=round(abs(drawdown), 4),
            win_rate_pct=round(win_rate, 2),
            note=note,
        ))

    return results


def analyze_why_outperformed(
    portfolio_id: str,
    portfolio_nav: pd.Series,
    cio_nav: pd.Series,
    portfolio_weights: dict[str, float],
    cio_weights: dict[str, float],
    price_data: pd.DataFrame,           # columns = tickers, rows = dates
    intended_regime: str,
    actual_regime: str,
) -> WhyAnalysis:
    """
    Conservative causal attribution of why a portfolio outperformed the CIO.
    Requires price_data for individual ticker attribution.
    """
    n = len(portfolio_nav)
    is_conclusive = n >= MIN_OBSERVATIONS_FOR_CONCLUSION

    period_start = str(portfolio_nav.index[0].date()) if not portfolio_nav.empty else ""
    period_end = str(portfolio_nav.index[-1].date()) if not portfolio_nav.empty else ""

    caveats: list[str] = []
    if not is_conclusive:
        caveats.append(f"Only {n} observations — below threshold of {MIN_OBSERVATIONS_FOR_CONCLUSION} for conclusions.")

    # Overall alpha
    if portfolio_nav.empty or cio_nav.empty or len(portfolio_nav) < 2 or len(cio_nav) < 2:
        return WhyAnalysis(
            portfolio_id=portfolio_id,
            period_start=period_start,
            period_end=period_end,
            n_observations=n,
            is_conclusive=False,
            asset_selection_contribution=0.0,
            concentration_contribution=0.0,
            regime_fit_contribution=0.0,
            cash_drag_contribution=0.0,
            primary_driver="unclear",
            confidence_in_attribution="low",
            key_finding="Insufficient data for attribution analysis.",
            caveats=["Insufficient price data."],
        )

    port_return = portfolio_nav.iloc[-1] / portfolio_nav.iloc[0] - 1
    cio_return = cio_nav.iloc[-1] / cio_nav.iloc[0] - 1
    total_alpha = (port_return - cio_return) * 100

    # 1. Asset selection contribution — which tickers were different?
    port_tickers = set(portfolio_weights.keys())
    cio_tickers = set(cio_weights.keys())
    unique_to_portfolio = port_tickers - cio_tickers
    unique_to_cio = cio_tickers - port_tickers

    asset_selection = 0.0
    if price_data is not None and not price_data.empty:
        for ticker in unique_to_portfolio:
            if ticker in price_data.columns:
                col = price_data[ticker].dropna()
                if len(col) >= 2:
                    ticker_return = col.iloc[-1] / col.iloc[0] - 1
                    asset_selection += portfolio_weights.get(ticker, 0) * ticker_return * 100

    # 2. Concentration contribution — Herfindahl index difference
    def herfindahl(w: dict) -> float:
        return sum(v**2 for v in w.values())

    h_portfolio = herfindahl(portfolio_weights)
    h_cio = herfindahl(cio_weights)
    concentration_contribution = (h_portfolio - h_cio) * total_alpha * 0.5  # heuristic

    # 3. Regime fit contribution — was this the intended regime?
    regime_fit_contribution = 0.0
    if actual_regime == intended_regime:
        regime_fit_contribution = total_alpha * 0.4  # credit 40% to regime fit
        caveats.append(f"Regime fit positive: actual regime '{actual_regime}' matched intended '{intended_regime}'.")
    else:
        caveats.append(f"Regime mismatch: actual '{actual_regime}' vs intended '{intended_regime}' — performance may not repeat in intended regime.")

    # 4. Cash drag contribution
    port_cash = portfolio_weights.get("STRC_PROXY", 0) + portfolio_weights.get("CASH", 0)
    cio_cash = cio_weights.get("STRC_PROXY", 0) + cio_weights.get("CASH", 0)
    cash_drag_contribution = (cio_cash - port_cash) * total_alpha * 0.3  # heuristic

    # Primary driver heuristic
    contributions = {
        "asset_selection": abs(asset_selection),
        "regime_fit": abs(regime_fit_contribution),
        "concentration": abs(concentration_contribution),
        "cash_drag": abs(cash_drag_contribution),
    }
    primary_driver = max(contributions, key=contributions.__getitem__) if any(v > 0 for v in contributions.values()) else "unclear"

    confidence = "high" if is_conclusive and abs(total_alpha) > 2.0 else "medium" if is_conclusive else "low"

    key_finding = (
        f"Portfolio generated {total_alpha:+.2f}% alpha vs CIO over {n} days. "
        f"Primary driver appears to be {primary_driver.replace('_', ' ')}. "
        f"{'Conclusive at this sample size.' if is_conclusive else 'Tentative — insufficient observations.'}"
    )

    return WhyAnalysis(
        portfolio_id=portfolio_id,
        period_start=period_start,
        period_end=period_end,
        n_observations=n,
        is_conclusive=is_conclusive,
        asset_selection_contribution=round(asset_selection, 4),
        concentration_contribution=round(concentration_contribution, 4),
        regime_fit_contribution=round(regime_fit_contribution, 4),
        cash_drag_contribution=round(cash_drag_contribution, 4),
        primary_driver=primary_driver,
        confidence_in_attribution=confidence,
        key_finding=key_finding,
        caveats=caveats,
    )


# ── Constitutional triggers ────────────────────────────────────────────────

@dataclass
class IntelligenceAlert:
    alert_type: str     # "outperformance_review" | "underperformance_alert" | "thesis_quality_concern"
    portfolio_id: str
    portfolio_name: str
    message: str
    evidence: dict
    triggered_at: str
    severity: str       # "info" | "warning" | "action_required"

    def to_dict(self) -> dict:
        return {
            "alert_type": self.alert_type,
            "portfolio_id": self.portfolio_id,
            "portfolio_name": self.portfolio_name,
            "message": self.message,
            "evidence": self.evidence,
            "triggered_at": self.triggered_at,
            "severity": self.severity,
        }


def check_outperformance_trigger(
    portfolio_id: str,
    portfolio_name: str,
    portfolio_nav: pd.Series,
    cio_nav: pd.Series,
    intended_regime: str,
) -> Optional[IntelligenceAlert]:
    """
    Constitution Article VIII mandate: if alternative outperforms CIO for 90+ consecutive days,
    trigger formal strategy review.
    """
    if portfolio_nav.empty or cio_nav.empty:
        return None

    combined = pd.DataFrame({
        "portfolio": portfolio_nav,
        "cio": cio_nav,
    }).dropna()

    if len(combined) < OUTPERFORMANCE_REVIEW_DAYS:
        return None

    # Check if portfolio has been outperforming for last 90 days
    recent = combined.tail(OUTPERFORMANCE_REVIEW_DAYS)
    port_daily = recent["portfolio"].pct_change().dropna()
    cio_daily = recent["cio"].pct_change().dropna()
    aligned = pd.concat([port_daily, cio_daily], axis=1).dropna()

    if aligned.empty:
        return None

    # Consecutive outperformance: cumulative return comparison over 90-day window
    port_cumret = (recent["portfolio"].iloc[-1] / recent["portfolio"].iloc[0] - 1) * 100
    cio_cumret = (recent["cio"].iloc[-1] / recent["cio"].iloc[0] - 1) * 100

    if port_cumret <= cio_cumret:
        return None

    alpha_90d = port_cumret - cio_cumret

    return IntelligenceAlert(
        alert_type="outperformance_review",
        portfolio_id=portfolio_id,
        portfolio_name=portfolio_name,
        message=(
            f"'{portfolio_name}' has outperformed main CIO by {alpha_90d:+.2f}% "
            f"over the past {OUTPERFORMANCE_REVIEW_DAYS} days. "
            "Constitutional mandate: formal strategy review required. "
            "Understand WHY before drawing conclusions."
        ),
        evidence={
            "portfolio_90d_return_pct": round(port_cumret, 4),
            "cio_90d_return_pct": round(cio_cumret, 4),
            "alpha_90d_pct": round(alpha_90d, 4),
            "observation_days": OUTPERFORMANCE_REVIEW_DAYS,
            "intended_regime": intended_regime,
            "warning": "Do not rebalance CIO toward this portfolio based on recent outperformance alone.",
        },
        triggered_at=datetime.now().strftime("%Y-%m-%d"),
        severity="action_required",
    )


def check_underperformance_alert(
    portfolio_id: str,
    portfolio_name: str,
    portfolio_nav: pd.Series,
    cio_nav: pd.Series,
    intended_regime: str,
) -> Optional[IntelligenceAlert]:
    """Flag severe underperformance relative to CIO for retirement consideration."""
    if portfolio_nav.empty or cio_nav.empty or len(portfolio_nav) < 2:
        return None

    port_total = (portfolio_nav.iloc[-1] / portfolio_nav.iloc[0] - 1) * 100
    cio_total = (cio_nav.iloc[-1] / cio_nav.iloc[0] - 1) * 100
    lag = port_total - cio_total

    if lag >= UNDERPERFORMANCE_ALERT_THRESHOLD_PCT:
        return None

    return IntelligenceAlert(
        alert_type="underperformance_alert",
        portfolio_id=portfolio_id,
        portfolio_name=portfolio_name,
        message=(
            f"'{portfolio_name}' trails main CIO by {lag:.2f}% since inception. "
            "Review retirement criteria against actual performance."
        ),
        evidence={
            "portfolio_total_return_pct": round(port_total, 4),
            "cio_total_return_pct": round(cio_total, 4),
            "lag_pct": round(lag, 4),
            "intended_regime": intended_regime,
        },
        triggered_at=datetime.now().strftime("%Y-%m-%d"),
        severity="warning",
    )


# ── Full intelligence report ──────────────────────────────────────────────

@dataclass
class PortfolioIntelligenceReport:
    generated_at: str
    n_portfolios_analyzed: int
    alerts: list[dict]
    regime_analyses: dict[str, list[dict]]  # portfolio_id -> [RegimePerformance.to_dict()]
    why_analyses: dict[str, dict]           # portfolio_id -> WhyAnalysis.to_dict()
    learning_proposals: list[str]           # Conservative proposals for Learning Coordinator review
    conservative_learning_note: str


def generate_intelligence_report(
    simulation_results: dict,
    active_portfolios: list,    # list[PortfolioProposal]
    price_data: Optional[pd.DataFrame] = None,
    actual_regime: str = "sideways",
) -> PortfolioIntelligenceReport:
    """
    Generate a full intelligence report across all active alternative portfolios.
    Conservative: warns rather than concludes when data is sparse.
    """
    alerts: list[dict] = []
    regime_analyses: dict[str, list[dict]] = {}
    why_analyses: dict[str, dict] = {}
    learning_proposals: list[str] = []

    cio_result = simulation_results.get("main_cio", {})
    cio_nav_dict = cio_result.get("nav_series", {})
    if cio_nav_dict:
        cio_nav = pd.Series(cio_nav_dict)
        cio_nav.index = pd.to_datetime(cio_nav.index)
    else:
        cio_nav = pd.Series(dtype=float)

    spy_result = simulation_results.get("benchmark_SPY", simulation_results.get("SPY", {}))
    spy_nav_dict = spy_result.get("nav_series", {})
    if spy_nav_dict:
        spy_nav = pd.Series(spy_nav_dict)
        spy_nav.index = pd.to_datetime(spy_nav.index)
    else:
        spy_nav = pd.Series(dtype=float)

    cio_weights = active_portfolios[0].weights if active_portfolios else {}  # placeholder

    for portfolio in active_portfolios:
        pid = portfolio.id
        pname = portfolio.name

        sim_key = pname.lower().replace(" ", "_")
        port_result = simulation_results.get(sim_key, simulation_results.get(pid, {}))
        nav_dict = port_result.get("nav_series", {})

        if not nav_dict:
            continue

        port_nav = pd.Series(nav_dict)
        port_nav.index = pd.to_datetime(port_nav.index)

        # Regime analysis
        regime_perf = analyze_regime_performance(port_nav, cio_nav, spy_nav)
        regime_analyses[pid] = [r.to_dict() for r in regime_perf]

        # Constitutional outperformance trigger
        outperf_alert = check_outperformance_trigger(pid, pname, port_nav, cio_nav, portfolio.intended_regime)
        if outperf_alert:
            alerts.append(outperf_alert.to_dict())

        # Underperformance alert
        underperf_alert = check_underperformance_alert(pid, pname, port_nav, cio_nav, portfolio.intended_regime)
        if underperf_alert:
            alerts.append(underperf_alert.to_dict())

        # Why analysis
        why = analyze_why_outperformed(
            portfolio_id=pid,
            portfolio_nav=port_nav,
            cio_nav=cio_nav,
            portfolio_weights=portfolio.weights,
            cio_weights=cio_weights,
            price_data=price_data if price_data is not None else pd.DataFrame(),
            intended_regime=portfolio.intended_regime,
            actual_regime=actual_regime,
        )
        why_analyses[pid] = why.to_dict()

        # Conservative learning proposals
        if why.is_conclusive and abs(why.asset_selection_contribution) > 3.0:
            learning_proposals.append(
                f"[CONCLUSIVE — N={why.n_observations}] '{pname}': Asset selection "
                f"contributed {why.asset_selection_contribution:+.2f}% alpha. "
                f"Review which tickers drove this and whether the CIO should consider similar exposure."
            )
        elif why.n_observations > 0 and not why.is_conclusive:
            learning_proposals.append(
                f"[TENTATIVE — N={why.n_observations}/{MIN_OBSERVATIONS_FOR_CONCLUSION}] '{pname}': "
                f"Early signal but insufficient data. Monitor for {MIN_OBSERVATIONS_FOR_CONCLUSION - why.n_observations} more observations."
            )

    _log_intelligence_report(alerts, learning_proposals)

    return PortfolioIntelligenceReport(
        generated_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        n_portfolios_analyzed=len(active_portfolios),
        alerts=alerts,
        regime_analyses=regime_analyses,
        why_analyses=why_analyses,
        learning_proposals=learning_proposals,
        conservative_learning_note=(
            f"All conclusions require N≥{MIN_OBSERVATIONS_FOR_CONCLUSION} observations. "
            "Tentative signals are flagged but should NOT drive allocation changes. "
            "Constitutional mandate: 90-day outperformance triggers review, not rebalancing."
        ),
    )


def _log_intelligence_report(alerts: list[dict], proposals: list[str]) -> None:
    INTELLIGENCE_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    existing = []
    if INTELLIGENCE_LOG_PATH.exists():
        with open(INTELLIGENCE_LOG_PATH) as f:
            existing = json.load(f)

    existing.append({
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "alerts": alerts,
        "learning_proposals": proposals,
    })
    existing = existing[-100:]  # keep last 100 runs

    with open(INTELLIGENCE_LOG_PATH, "w") as f:
        json.dump(existing, f, indent=2, default=str)
