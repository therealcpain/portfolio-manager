"""
daily_loop.py — Ten-phase daily operating loop.

Orchestrates: ingest → regime → routing → memos → dissent →
  portfolio construction → CIO decision → learning → org review → report.

Each phase returns a typed result. Phase failures are caught and stored;
the loop continues. Results are persisted to data/processed/daily_loops/.

Usage:
  from daily_loop import run_daily_loop, DailyLoopConfig
  result = run_daily_loop(DailyLoopConfig(date="2026-05-13", mock=True))

Advisory only — no live trading.
"""

from __future__ import annotations

import json
import os
import sys
import time
from dataclasses import asdict, dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Any, Optional

ROOT_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT_DIR / "src"))

# Load .env so ANTHROPIC_API_KEY and FRED_API_KEY are available
_env_path = ROOT_DIR / ".env"
if _env_path.exists():
    for _line in _env_path.read_text().splitlines():
        _line = _line.strip()
        if _line and not _line.startswith("#") and "=" in _line:
            _k, _v = _line.split("=", 1)
            if _v.strip():  # only set non-empty values
                os.environ[_k.strip()] = _v.strip()

DISCLAIMER = (
    "ADVISORY ONLY. All outputs are advisory model recommendations requiring human review. "
    "Not financial advice. Not a registered investment adviser."
)

DAILY_LOOPS_DIR = ROOT_DIR / "data" / "processed" / "daily_loops"
REPORTS_DAILY_DIR = ROOT_DIR / "reports" / "daily"


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

@dataclass
class DailyLoopConfig:
    date: str = ""                     # ISO date; defaults to today
    mock: bool = True                  # False = call live Claude API
    decision_type: str = "full_committee"
    decision_question: str = (
        "Evaluate current portfolio positioning given today's market data "
        "and recommend any allocation adjustments."
    )
    skip_phases: list[str] = field(default_factory=list)  # phase names to skip
    verbose: bool = False

    def resolved_date(self) -> str:
        return self.date or str(date.today())


# ---------------------------------------------------------------------------
# Phase result dataclasses
# ---------------------------------------------------------------------------

@dataclass
class PhaseResult:
    phase: str
    status: str        # "ok" | "skipped" | "error"
    elapsed_s: float
    error: str = ""
    data: dict = field(default_factory=dict)

    def ok(self) -> bool:
        return self.status == "ok"


@dataclass
class IngestResult:
    as_of_date: str
    prices: dict[str, float]              # ticker → price
    returns_1d: dict[str, float]
    returns_5d: dict[str, float]
    returns_20d: dict[str, float]
    returns_ytd: dict[str, float]
    vix: float
    dxy: float
    btc_price: float
    gold_price: float
    macro_snapshot: dict                  # raw yaml if available
    overnight_summary: str
    data_source: str


@dataclass
class RegimeSubAssessment:
    name: str
    label: str
    confidence: int
    rationale: str


@dataclass
class RegimeResult:
    macro_regime: str
    macro_confidence: int
    macro_rationale: str
    equity_stance: str
    btc_crypto_stance: str
    gold_stance: str
    sub_assessments: list[RegimeSubAssessment]
    data_source: str


@dataclass
class RoutingResult:
    decision_type: str
    decision_question: str
    engaged_specialists: list[str]
    skipped_specialists: list[str]
    routing_rationale: str
    coordinator_notes: str


@dataclass
class SpecialistMemoResult:
    memos: list[dict]          # serialised AgentMemo dicts
    memo_count: int
    mock_mode: bool


@dataclass
class DissentResult:
    groupthink_alert: bool
    groupthink_reason: str
    dissent_suppressed: bool
    dissenting_agents: list[str]
    majority_position: str
    majority_pct: float
    sentiment_state: str
    sentiment_rationale: str
    recommendations: list[str]


@dataclass
class PortfolioConstructionResult:
    allocation_changes: list[dict]     # [{"ticker", "action", "rationale"}]
    options_changes: list[dict]
    watchlist_additions: list[str]
    watchlist_removals: list[str]
    derisking_triggered: bool
    risk_on_triggered: bool
    regime_persistence_blocks: list[str]
    coordinator_summary: str


@dataclass
class CIODecisionResult:
    final_stance: str
    final_confidence: int
    required_actions: list[str]         # act today
    watchlist_only: list[str]           # watch but don't act
    signals: list[dict]                 # SignalObservation dicts
    actions: list[dict]                 # ActionDecision dicts
    dissent_acknowledged: bool
    challenge_questions: list[str]
    next_review_trigger: str
    allocation_change: bool


@dataclass
class LearningResult:
    votes_recorded: int
    thesis_updates: int
    regime_attributions_recorded: int
    benchmark_snapshot_recorded: bool
    alternative_portfolio_snapshots: int
    notes: list[str]


@dataclass
class OrgReviewResult:
    complexity_score: float
    health_score: float
    alerts: list[str]
    actionable_observations: int
    pending_proposals: int
    complexity_breach: bool
    recommendations: list[str]


@dataclass
class FinalReportResult:
    front_page: str
    appendix: str
    report_path: str
    word_count: int


@dataclass
class DailyLoopResult:
    config: DailyLoopConfig
    run_id: str
    started_at: str
    completed_at: str
    total_elapsed_s: float
    phase_results: list[PhaseResult]
    ingest: Optional[IngestResult] = None
    regime: Optional[RegimeResult] = None
    routing: Optional[RoutingResult] = None
    memos: Optional[SpecialistMemoResult] = None
    dissent: Optional[DissentResult] = None
    portfolio_construction: Optional[PortfolioConstructionResult] = None
    cio_decision: Optional[CIODecisionResult] = None
    learning: Optional[LearningResult] = None
    org_review: Optional[OrgReviewResult] = None
    final_report: Optional[FinalReportResult] = None
    error_summary: list[str] = field(default_factory=list)

    def phase(self, name: str) -> Optional[PhaseResult]:
        return next((p for p in self.phase_results if p.phase == name), None)

    def phases_ok(self) -> list[str]:
        return [p.phase for p in self.phase_results if p.ok()]

    def phases_failed(self) -> list[str]:
        return [p.phase for p in self.phase_results if p.status == "error"]


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _timer(fn):
    """Return (result, elapsed_seconds)."""
    t0 = time.perf_counter()
    result = fn()
    return result, time.perf_counter() - t0


def _safe_phase(name: str, fn, skip: bool = False) -> tuple[PhaseResult, Any]:
    """Execute a phase function, catch exceptions, return (PhaseResult, payload)."""
    if skip:
        return PhaseResult(phase=name, status="skipped", elapsed_s=0.0), None
    t0 = time.perf_counter()
    try:
        payload = fn()
        elapsed = time.perf_counter() - t0
        return PhaseResult(phase=name, status="ok", elapsed_s=round(elapsed, 3)), payload
    except Exception as exc:
        elapsed = time.perf_counter() - t0
        return PhaseResult(
            phase=name, status="error", elapsed_s=round(elapsed, 3), error=str(exc)
        ), None


def _load_macro_snapshot(auto_fetch: bool = True) -> dict:
    """Load macro snapshot YAML, auto-fetching fresh data if requested."""
    path = ROOT_DIR / "data" / "manual_inputs" / "macro_snapshot.yaml"

    if auto_fetch:
        try:
            from macro_fetcher import fetch_macro_snapshot
            fetch_macro_snapshot(write=True)
        except Exception:
            pass  # fall through to cached file

    if not path.exists():
        return {}
    try:
        import yaml
        with open(path) as f:
            return yaml.safe_load(f) or {}
    except Exception:
        return {}


def _load_portfolio_yaml() -> dict:
    """Load current portfolio YAML."""
    path = ROOT_DIR / "portfolio" / "current_portfolio.yaml"
    if not path.exists():
        return {}
    try:
        import yaml
        with open(path) as f:
            return yaml.safe_load(f) or {}
    except Exception:
        return {}


# ---------------------------------------------------------------------------
# Phase 1 — Morning Ingest
# ---------------------------------------------------------------------------

INGEST_TICKERS = {
    "SPY": "SPY",
    "QQQ": "QQQ",
    "BTC": "BTC-USD",
    "ETH": "ETH-USD",
    "GLD": "GLD",
    "MSTR": "MSTR",
    "URNM": "URNM",
    "NVDA": "NVDA",
    "COIN": "COIN",
    "DXY": "DX-Y.NYB",
    "VIX": "^VIX",
    "TLT": "TLT",
    "AGG": "AGG",
    "GC": "GC=F",
    "IBIT": "IBIT",
}


def _run_ingest(cfg: DailyLoopConfig) -> IngestResult:
    """
    Phase 1: fetch market data via macro_fetcher (live) or mock stubs.

    Live mode auto-fetches prices, yields, CPI, FRED macro, and writes
    macro_snapshot.yaml before reading it back. Mock mode skips network calls.
    """
    today_str = cfg.resolved_date()

    if cfg.mock:
        macro = _load_macro_snapshot(auto_fetch=False)
        prices = {
            "SPY": 525.0, "QQQ": 445.0, "BTC": 65000.0, "ETH": 3200.0,
            "GLD": 230.0, "MSTR": 1400.0, "URNM": 38.0, "NVDA": 890.0,
            "COIN": 215.0, "DXY": 104.5, "VIX": 18.2, "TLT": 95.0,
            "AGG": 99.0, "GC": 2300.0, "IBIT": 38.5,
        }
        r1 = {k: 0.4 for k in prices}
        r5 = {k: 1.2 for k in prices}
        r20 = {k: 4.5 for k in prices}
        ytd = {k: 12.0 for k in prices}
        source = "mock"
    else:
        # Auto-fetch all data and write macro_snapshot.yaml
        macro = _load_macro_snapshot(auto_fetch=True)
        # Pull prices + returns from the freshly-written snapshot
        prices = macro.get("market", {})
        # Supplement with full ticker list from snapshot prices section
        snap_prices = macro.get("prices", {})
        if snap_prices:
            prices = snap_prices
        r1  = macro.get("returns_1d", {})
        r5  = macro.get("returns_5d", {})
        r20 = macro.get("returns_20d", {})
        ytd = macro.get("returns_ytd", {})
        source = macro.get("metadata", {}).get("source", "live")

    overnight = macro.get("overnight_developments", "No overnight developments logged.")

    return IngestResult(
        as_of_date=today_str,
        prices=prices,
        returns_1d=r1,
        returns_5d=r5,
        returns_20d=r20,
        returns_ytd=ytd,
        vix=prices.get("VIX", 0.0),
        dxy=prices.get("DXY", 0.0),
        btc_price=prices.get("BTC", 0.0),
        gold_price=prices.get("GLD", 0.0),
        macro_snapshot=macro,
        overnight_summary=str(overnight),
        data_source=source,
    )


# ---------------------------------------------------------------------------
# Phase 2 — Regime Assessment
# ---------------------------------------------------------------------------

def _classify_liquidity(macro: dict, ingest: IngestResult) -> RegimeSubAssessment:
    m2 = macro.get("liquidity", {}).get("m2_yoy_pct", "[MANUAL]")
    fed_stance = macro.get("fed", {}).get("stance", "unknown")
    if isinstance(m2, (int, float)):
        if m2 > 5 and fed_stance == "Cutting":
            label, rationale = "Expansionary", "M2 growing + Fed cutting → ample liquidity"
        elif m2 < 0:
            label, rationale = "Contractionary", "M2 negative YoY → liquidity draining"
        else:
            label, rationale = "Neutral", "M2 flat-to-modest growth; stance unclear"
    else:
        label, rationale = "Unknown", "M2 data not available — manual input required"
    return RegimeSubAssessment("Liquidity", label, 40 if "Unknown" in label else 65, rationale)


def _classify_risk_appetite(ingest: IngestResult) -> RegimeSubAssessment:
    vix = ingest.vix
    if vix == 0.0:
        return RegimeSubAssessment("Risk Appetite", "Unknown", 0, "VIX data unavailable")
    if vix < 15:
        label, rationale = "Risk-On (Complacency)", f"VIX {vix:.1f} — extremely low fear"
    elif vix < 20:
        label, rationale = "Risk-On", f"VIX {vix:.1f} — calm conditions"
    elif vix < 28:
        label, rationale = "Cautious", f"VIX {vix:.1f} — elevated uncertainty"
    elif vix < 35:
        label, rationale = "Risk-Off", f"VIX {vix:.1f} — significant fear"
    else:
        label, rationale = "Extreme Risk-Off", f"VIX {vix:.1f} — market stress"
    conf = 75 if vix > 0 else 0
    return RegimeSubAssessment("Risk Appetite", label, conf, rationale)


def _classify_technical(ingest: IngestResult) -> RegimeSubAssessment:
    spy_20d = ingest.returns_20d.get("SPY", 0.0)
    if spy_20d > 5:
        label, rationale = "Bullish Momentum", f"SPY +{spy_20d:.1f}% over 20d"
    elif spy_20d > 0:
        label, rationale = "Neutral-Positive", f"SPY +{spy_20d:.1f}% over 20d — mild uptrend"
    elif spy_20d > -5:
        label, rationale = "Neutral-Negative", f"SPY {spy_20d:.1f}% over 20d — mild pullback"
    else:
        label, rationale = "Bearish", f"SPY {spy_20d:.1f}% over 20d — downtrend"
    return RegimeSubAssessment("Technical", label, 60, rationale)


def _classify_volatility(ingest: IngestResult) -> RegimeSubAssessment:
    vix = ingest.vix
    if vix == 0.0:
        return RegimeSubAssessment("Volatility", "Unknown", 0, "VIX unavailable")
    if vix < 15:
        label = "Low Vol"
    elif vix < 25:
        label = "Moderate Vol"
    elif vix < 35:
        label = "Elevated Vol"
    else:
        label = "Crisis Vol"
    return RegimeSubAssessment("Volatility", label, 80, f"VIX {vix:.1f}")


def _classify_crypto(ingest: IngestResult) -> RegimeSubAssessment:
    btc_20d = ingest.returns_20d.get("BTC", 0.0)
    eth_20d = ingest.returns_20d.get("ETH", 0.0)
    if btc_20d > 10 and eth_20d > 8:
        label, rationale = "Risk-On Crypto", f"BTC +{btc_20d:.1f}%, ETH +{eth_20d:.1f}% — broad rally"
    elif btc_20d > 5:
        label, rationale = "BTC-Led", f"BTC +{btc_20d:.1f}% leading; ETH {eth_20d:.1f}%"
    elif btc_20d < -10:
        label, rationale = "Risk-Off Crypto", f"BTC {btc_20d:.1f}% — significant drawdown"
    else:
        label, rationale = "Sideways", f"BTC {btc_20d:.1f}% — consolidation"
    return RegimeSubAssessment("Crypto", label, 65, rationale)


def _run_regime(ingest: IngestResult) -> RegimeResult:
    from regime_engine import RegimeSignals, classify_regime, MacroRegime
    macro = ingest.macro_snapshot

    def _get(keys: list[str], fallback=None):
        d = macro
        for k in keys:
            if not isinstance(d, dict):
                return fallback
            d = d.get(k, fallback)
        return d

    signals = RegimeSignals(
        m2_yoy_pct=_get(["m2_yoy_pct"]) or _get(["liquidity", "m2_yoy_pct"]),
        fed_stance=_get(["fed", "funds_rate"]),
        real_rates=_get(["real_rate_10y_tips"]) or _get(["rates", "real_rate_10y_tips"]),
        yield_curve_2_10=_get(["yield_curve_2_10"]) or _get(["rates", "yield_curve_2_10"]),
        ism_manufacturing=_get(["ism_manufacturing"]) or _get(["growth", "ism_manufacturing"]),
        credit_spread_hy=_get(["hy_credit_spread_bps"]) or _get(["credit", "hy_credit_spread_bps"]),
        vix=ingest.vix if ingest.vix and ingest.vix > 0 else None,
        cpi_yoy=_get(["cpi_yoy_pct"]) or _get(["inflation", "cpi_yoy_pct"]),
        gdp_growth=_get(["gdp_real_qoq_pct"]) or _get(["growth", "gdp_last_reading_pct"]),
        data_source=macro.get("metadata", {}).get("source", "auto"),
    )

    try:
        assessment = classify_regime(signals)
    except NotImplementedError:
        assessment = None

    # Auto-classified regime from macro_fetcher takes priority
    auto_regime = _get(["manual_regime_assessment", "regime"], "")
    auto_rationale = _get(["manual_regime_assessment", "rationale"], "")
    auto_confidence = _get(["manual_regime_assessment", "confidence"], 0)
    auto_signals = _get(["manual_regime_assessment", "signals"], [])

    if assessment and assessment.regime != MacroRegime.UNKNOWN:
        macro_regime = assessment.regime.value
        macro_confidence = assessment.confidence
        macro_rationale = assessment.rationale
        equity_stance = assessment.equity_stance
        btc_stance = assessment.btc_crypto_stance
        gold_stance = assessment.gold_stance
    elif auto_regime and auto_regime not in ("[MANUAL INPUT REQUIRED]", "", "Unknown"):
        macro_regime = auto_regime
        macro_confidence = int(auto_confidence) if isinstance(auto_confidence, (int, float)) else 50
        macro_rationale = str(auto_rationale)
        # Derive stances from regime label
        _stance_map = {
            "RISK_ON_GROWTH":       ("Overweight equities, reduce cash",   "Bullish",   "Neutral"),
            "LATE_CYCLE_CAUTIOUS":  ("Selective — quality over beta",       "Cautious",  "Mild overweight"),
            "TRANSITIONAL":         ("Balanced, reduce extremes",           "Neutral",   "Mild overweight"),
            "RISK_OFF_TIGHTENING":  ("Underweight equities, raise cash",    "Bearish",   "Overweight"),
            "DEFENSIVE_CONTRACTION":("Defensive — bonds and cash",          "Avoid",     "Overweight"),
        }
        stances = _stance_map.get(macro_regime, ("Hold current positions", "Neutral", "Neutral"))
        equity_stance, btc_stance, gold_stance = stances
    else:
        macro_regime = "Transitional"
        macro_confidence = 40
        macro_rationale = "Regime unclear — defaulting to cautious transitional."
        equity_stance = "Hold — await regime clarity"
        btc_stance = "Neutral"
        gold_stance = "Mild overweight"

    sub = [
        _classify_liquidity(macro, ingest),
        _classify_risk_appetite(ingest),
        _classify_technical(ingest),
        _classify_volatility(ingest),
        _classify_crypto(ingest),
    ]

    return RegimeResult(
        macro_regime=macro_regime,
        macro_confidence=macro_confidence,
        macro_rationale=macro_rationale,
        equity_stance=equity_stance,
        btc_crypto_stance=btc_stance,
        gold_stance=gold_stance,
        sub_assessments=sub,
        data_source=signals.data_source,
    )


# ---------------------------------------------------------------------------
# Phase 3 — Research Routing
# ---------------------------------------------------------------------------

def _select_decision_type(cfg: DailyLoopConfig, ingest: IngestResult) -> str:
    """Auto-select decision type if caller left the default."""
    if cfg.decision_type != "full_committee":
        return cfg.decision_type
    # Escalate to full committee on major moves
    btc_1d = abs(ingest.returns_1d.get("BTC", 0.0))
    spy_1d = abs(ingest.returns_1d.get("SPY", 0.0))
    if spy_1d > 2.5 or btc_1d > 5.0:
        return "risk_alert"
    return "full_committee"


def _run_routing(cfg: DailyLoopConfig, ingest: IngestResult, regime: RegimeResult) -> RoutingResult:
    from routing_engine import route_decision, DecisionType, RoutingContext, describe_routing_plan

    decision_type_str = _select_decision_type(cfg, ingest)
    try:
        dt = DecisionType(decision_type_str)
    except ValueError:
        dt = DecisionType.FULL_COMMITTEE

    ctx = RoutingContext(
        aggregate_confidence=70,
        sessions_same_asset=0,
        asset_class=None,
    )

    plan = route_decision(dt, ctx)
    engaged = plan.specialists
    skipped = list(plan.skipped.keys())
    rationale = describe_routing_plan(plan)

    return RoutingResult(
        decision_type=dt.value,
        decision_question=cfg.decision_question,
        engaged_specialists=engaged,
        skipped_specialists=skipped,
        routing_rationale=rationale,
        coordinator_notes=(
            f"Research Coordinator engaged {len(engaged)} specialist(s). "
            f"Decision type: {dt.value}. Regime context: {regime.macro_regime}."
        ),
    )


# ---------------------------------------------------------------------------
# Phase 4 — Specialist Memos
# ---------------------------------------------------------------------------

def _run_memos(cfg: DailyLoopConfig, routing: RoutingResult, ingest: IngestResult,
               regime: RegimeResult) -> SpecialistMemoResult:
    from memo_builder import build_context_packet, PortfolioSnapshot, parse_memo_from_response
    from committee_session import _mock_specialist_response, _call_agent_live

    portfolio_yaml = _load_portfolio_yaml()
    positions = []
    total_value = float(portfolio_yaml.get("total_value", 100_000))
    for pos in portfolio_yaml.get("positions", []):
        pct = pos.get("portfolio_pct", 0)
        positions.append({
            "ticker": pos.get("ticker", ""),
            "pct": float(pct),
            "bucket": pos.get("bucket", ""),
            "thesis_state": pos.get("thesis_lifecycle", "Unknown"),
        })

    snapshot = PortfolioSnapshot(
        total_value=total_value,
        cash_pct=float(portfolio_yaml.get("cash_pct", 10.0)),
        positions=positions,
        active_theses=[],
        latest_nav_return_pct=0.0,
        options_premium_at_risk_pct=0.0,
    )

    memos: list[dict] = []
    for specialist in routing.engaged_specialists:
        try:
            context_packet = build_context_packet(
                agent=specialist,
                decision_type=routing.decision_type,
                decision_question=routing.decision_question,
                portfolio=snapshot,
                asset_context={
                    "vix": ingest.vix,
                    "btc_1d_return": ingest.returns_1d.get("BTC", 0.0),
                    "spy_1d_return": ingest.returns_1d.get("SPY", 0.0),
                    "dxy": ingest.dxy,
                    "macro_regime": regime.macro_regime,
                    "macro_regime_confidence": regime.macro_confidence,
                },
            )
            if cfg.mock:
                raw = _mock_specialist_response(specialist, routing.decision_type)
            else:
                raw = _call_agent_live(specialist, context_packet)

            memo = parse_memo_from_response(specialist, routing.decision_type, raw)
            memos.append({
                "agent": memo.agent,
                "decision_type": memo.decision_type,
                "stance": memo.stance,
                "confidence": memo.confidence,
                "key_points": memo.key_points,
                "recommendation": memo.recommendation,
                "dissent": memo.dissent,
                "timestamp": memo.timestamp,
            })
        except Exception as exc:
            memos.append({
                "agent": specialist,
                "stance": "error",
                "confidence": 0,
                "key_points": [f"Memo generation failed: {exc}"],
                "recommendation": "",
                "dissent": "",
            })

    return SpecialistMemoResult(
        memos=memos,
        memo_count=len(memos),
        mock_mode=cfg.mock,
    )


# ---------------------------------------------------------------------------
# Phase 5 — Dissent / Risk
# ---------------------------------------------------------------------------

def _run_dissent(ingest: IngestResult, regime: RegimeResult,
                 memos: SpecialistMemoResult) -> DissentResult:
    from governance_tightening import (
        evaluate_dissent_health,
        classify_sentiment_state,
        SentimentState,
    )

    votes = []
    for m in memos.memos:
        stance = m.get("stance", "hold")
        if stance not in ("error", ""):
            votes.append({"agent": m["agent"], "vote": stance, "confidence": m.get("confidence", 50)})

    session_id = f"daily-{ingest.as_of_date}"
    health = evaluate_dissent_health(session_id, votes)

    fgi = None
    macro = ingest.macro_snapshot
    vix = ingest.vix
    btc_20d = ingest.returns_20d.get("BTC", 0.0)
    spy_20d = ingest.returns_20d.get("SPY", 0.0)

    sentiment_state, sentiment_rationale = classify_sentiment_state(
        fear_greed_index=fgi,
        price_momentum_20d=spy_20d / 100 if spy_20d else None,
    )

    return DissentResult(
        groupthink_alert=health.groupthink_alert,
        groupthink_reason=health.groupthink_reason,
        dissent_suppressed=health.dissent_suppressed,
        dissenting_agents=health.dissenting_agents,
        majority_position=health.majority_position,
        majority_pct=health.majority_pct,
        sentiment_state=sentiment_state.value,
        sentiment_rationale=sentiment_rationale,
        recommendations=health.recommendations,
    )


# ---------------------------------------------------------------------------
# Phase 6 — Portfolio Construction
# ---------------------------------------------------------------------------

def _run_portfolio_construction(
    ingest: IngestResult,
    regime: RegimeResult,
    memos: SpecialistMemoResult,
    dissent: DissentResult,
) -> PortfolioConstructionResult:
    from governance_tightening import (
        SentimentState,
        build_gradual_deallocation,
        check_regime_persistence,
    )

    allocation_changes: list[dict] = []
    options_changes: list[dict] = []
    watchlist_additions: list[str] = []
    watchlist_removals: list[str] = []
    regime_persistence_blocks: list[str] = []
    derisking = False
    risk_on = False

    # Count bullish vs bearish signals from memos
    bullish = sum(1 for m in memos.memos if m.get("stance") in ("bullish", "buy", "strong_buy"))
    bearish = sum(1 for m in memos.memos if m.get("stance") in ("bearish", "sell", "reduce"))
    total = len(memos.memos)

    # Check if euphoric conditions warrant gradual deallocation
    sentiment = dissent.sentiment_state
    if sentiment in ("euphoric_melt_up", "narrative_saturation"):
        portfolio_yaml = _load_portfolio_yaml()
        for pos in portfolio_yaml.get("positions", []):
            ticker = pos.get("ticker", "")
            exposure = pos.get("portfolio_pct", 0)
            if exposure > 15:
                # Check regime persistence before trimming
                check = check_regime_persistence(
                    regime_label=regime.macro_regime.lower().replace(" ", "_"),
                    regime_start_date="2024-01-01",  # placeholder — use actual from thesis memory
                    current_date=ingest.as_of_date,
                    days_elapsed=120,               # placeholder
                    fade_signal_present=True,
                    confirmation_signals=[],         # no confirmations yet → will block
                )
                if check.verdict == "too_early_to_fade":
                    regime_persistence_blocks.append(
                        f"{ticker}: {check.rationale}"
                    )
                else:
                    policy = build_gradual_deallocation(
                        position_id=ticker,
                        ticker=ticker,
                        current_exposure_pct=exposure,
                        desired_reduction_pct=exposure * 0.20,
                        sentiment_state=SentimentState(sentiment),
                        regime_persistence_check=check,
                        n_steps=3,
                    )
                    if not policy.blocked and policy.steps:
                        step = policy.steps[0]
                        allocation_changes.append({
                            "ticker": ticker,
                            "action": f"trim_{step.trim_amount_pct:.1f}pct",
                            "rationale": step.rationale,
                        })
                        derisking = True

    # Simple de-risk / risk-on signals based on memo consensus
    if total > 0:
        bull_pct = bullish / total
        bear_pct = bearish / total
        vix = ingest.vix

        if bear_pct > 0.6 or vix > 30:
            derisking = True
            options_changes.append({
                "action": "add_protective_puts",
                "rationale": (
                    f"Bear memo dominance {bear_pct:.0%} or VIX {vix:.1f} > 30 — "
                    "Portfolio Construction Coordinator recommends protective hedges."
                ),
            })

        if bull_pct > 0.7 and vix < 18 and not derisking:
            risk_on = True

    # Watchlist from bear memos that are 'watch only'
    for m in memos.memos:
        rec = m.get("recommendation", "").lower()
        if "watch" in rec or "monitor" in rec:
            tickers = [w for w in rec.split() if w.isupper() and len(w) <= 5]
            watchlist_additions.extend(tickers)

    watchlist_additions = list(set(watchlist_additions))

    summary_parts = [f"Portfolio Construction phase: {len(allocation_changes)} allocation change(s)"]
    if derisking:
        summary_parts.append("de-risking triggered")
    if risk_on:
        summary_parts.append("risk-on bias")
    if regime_persistence_blocks:
        summary_parts.append(f"{len(regime_persistence_blocks)} regime persistence block(s)")
    if dissent.groupthink_alert:
        summary_parts.append("GROUPTHINK ALERT — soliciting additional dissent before finalizing")

    return PortfolioConstructionResult(
        allocation_changes=allocation_changes,
        options_changes=options_changes,
        watchlist_additions=watchlist_additions,
        watchlist_removals=watchlist_removals,
        derisking_triggered=derisking,
        risk_on_triggered=risk_on,
        regime_persistence_blocks=regime_persistence_blocks,
        coordinator_summary=". ".join(summary_parts) + ".",
    )


# ---------------------------------------------------------------------------
# Phase 7 — CIO Decision
# ---------------------------------------------------------------------------

def _run_cio_decision(
    cfg: DailyLoopConfig,
    ingest: IngestResult,
    regime: RegimeResult,
    memos: SpecialistMemoResult,
    dissent: DissentResult,
    pc: PortfolioConstructionResult,
) -> CIODecisionResult:
    from memo_builder import build_cio_brief, AgentMemo, summarize_memos_for_coordinator
    from committee_session import _mock_cio_decision, _parse_cio_decision, _call_agent_live

    # Reconstruct AgentMemo objects for the brief
    today_str = cfg.resolved_date()
    agent_memos = []
    for m in memos.memos:
        dissent_text = m.get("dissent", "")
        agent_memos.append(AgentMemo(
            agent=m.get("agent", ""),
            decision_type=m.get("decision_type", "full_committee"),
            date=today_str,
            stance=m.get("stance", "hold"),
            confidence=m.get("confidence", 50),
            key_points=m.get("key_points", []),
            recommendation=m.get("recommendation", ""),
            dissent_flag=bool(dissent_text and dissent_text.lower() not in ("no", "false", "")),
            dissent_reason=dissent_text if dissent_text else "",
        ))

    if cfg.mock:
        raw = _mock_cio_decision(cfg.decision_question)
    else:
        research_summary = summarize_memos_for_coordinator(agent_memos)
        cio_brief = build_cio_brief(
            decision_question=cfg.decision_question,
            research_summary=research_summary,
            bear_case_summary=dissent.groupthink_reason or "No groupthink detected.",
            portfolio_construction_notes=pc.coordinator_summary,
            routing_rationale=getattr(pc, "routing_rationale", "Full committee engaged."),
        )
        raw = _call_agent_live("cio", cio_brief)

    cio = _parse_cio_decision(raw)

    # Parse and persist target allocation from CIO text
    try:
        from allocation_tracker import parse_allocation_from_cio, save_snapshot, compute_deltas
        alloc_snap = parse_allocation_from_cio(
            raw=raw,
            date_str=cfg.resolved_date(),
            regime=regime.macro_regime,
            overall_confidence=cio.final_confidence,
        )
        if alloc_snap:
            save_snapshot(alloc_snap)
            cio._allocation_snapshot = alloc_snap
            cio._allocation_deltas = compute_deltas(alloc_snap)
        else:
            cio._allocation_snapshot = None
            cio._allocation_deltas = []
    except Exception:
        cio._allocation_snapshot = None
        cio._allocation_deltas = []

    # Signal vs action separation
    signals: list[dict] = []
    actions: list[dict] = []

    for memo in memos.memos:
        stance = memo.get("stance", "hold")
        if stance not in ("hold", "error", ""):
            signals.append({
                "source": memo["agent"],
                "signal_type": stance,
                "description": memo.get("recommendation", ""),
                "regime": regime.macro_regime,
            })

    # Actions today = CIO action orders; watchlist only = everything else
    required = cio.action_orders
    watchlist: list[str] = []
    for s in signals:
        desc = s.get("description", "").lower()
        if "watch" in desc or "monitor" in desc:
            watchlist.append(s["source"] + ": " + s.get("description", ""))

    return CIODecisionResult(
        final_stance=cio.final_stance,
        final_confidence=cio.final_confidence,
        required_actions=required,
        watchlist_only=watchlist,
        signals=signals,
        actions=actions,
        dissent_acknowledged=cio.dissent_acknowledged,
        challenge_questions=cio.challenge_questions,
        next_review_trigger=cio.next_review_trigger,
        allocation_change=cio.allocation_change,
    )


# ---------------------------------------------------------------------------
# Phase 8 — Learning
# ---------------------------------------------------------------------------

def _run_learning(
    ingest: IngestResult,
    regime: RegimeResult,
    memos: SpecialistMemoResult,
    cio: CIODecisionResult,
) -> LearningResult:
    import uuid
    from vote_db import record_recommendation, record_vote

    notes: list[str] = []
    votes_recorded = 0
    thesis_updates = 0

    # Record today's CIO recommendation
    rec_id = f"daily-{ingest.as_of_date}-{uuid.uuid4().hex[:6]}"
    try:
        record_recommendation(
            rec_id=rec_id,
            date_str=ingest.as_of_date,
            asset="PORTFOLIO",
            action=cio.final_stance,
            thesis_summary=f"Daily loop: {cio.final_stance} at confidence {cio.final_confidence}",
            confidence=cio.final_confidence,
            time_horizon="short_term",
            invalidation=cio.next_review_trigger,
            regime=regime.macro_regime,
        )
    except Exception as exc:
        notes.append(f"vote_db record_recommendation failed: {exc}")

    # Record individual specialist votes
    for memo in memos.memos:
        agent = memo.get("agent", "")
        stance = memo.get("stance", "hold")
        confidence = memo.get("confidence", 50)
        if agent and stance not in ("error", ""):
            try:
                record_vote(
                    rec_id=rec_id,
                    agent=agent,
                    vote=stance,
                    confidence=confidence,
                    rationale=memo.get("recommendation", ""),
                    regime=regime.macro_regime,
                )
                votes_recorded += 1
            except Exception as exc:
                notes.append(f"vote for {agent} failed: {exc}")

    # Benchmark NAV snapshot
    benchmark_ok = False
    try:
        from nav_tracker import record_snapshot
        record_snapshot(
            date_str=ingest.as_of_date,
            nav=None,  # will use portfolio YAML
            spy_price=ingest.prices.get("SPY", 0.0),
            btc_price=ingest.prices.get("BTC", 0.0),
        )
        benchmark_ok = True
    except Exception as exc:
        notes.append(f"nav_tracker snapshot failed: {exc}")

    # Regime attribution note
    try:
        from agent_learning_engine import classify_regime_from_context
        classified = classify_regime_from_context(
            spy_return_20d=ingest.returns_20d.get("SPY", 0.0) / 100,
            vix_level=ingest.vix,
        )
        notes.append(f"Regime attribution: {classified.value}")
    except Exception:
        pass

    return LearningResult(
        votes_recorded=votes_recorded,
        thesis_updates=thesis_updates,
        regime_attributions_recorded=1 if votes_recorded > 0 else 0,
        benchmark_snapshot_recorded=benchmark_ok,
        alternative_portfolio_snapshots=0,
        notes=notes,
    )


# ---------------------------------------------------------------------------
# Phase 9 — Organizational Review
# ---------------------------------------------------------------------------

def _run_org_review(ingest: IngestResult, memos: SpecialistMemoResult) -> OrgReviewResult:
    from org_evolution_engine import generate_org_improvement_report

    sessions = [
        {
            "agents": [m["agent"] for m in memos.memos],
            "redundant_outputs": 0,
            "unnecessary_outputs": 0,
            "report_sections": len(memos.memos),
        }
    ]

    try:
        report = generate_org_improvement_report(
            n_active_agents=len(memos.memos),
            sessions=sessions,
        )

        alerts = report.complexity_metrics.alerts
        actionable = sum(1 for o in report.actionable_observations if o.observation_count >= 3)
        pending = len(report.pending_proposals)
        complexity_breach = report.complexity_metrics.complexity_score > 70

        recommendations: list[str] = []
        if complexity_breach:
            recommendations.append(
                f"Complexity score {report.complexity_metrics.complexity_score:.0f} > 70 — "
                "consider merging or retiring agents."
            )
        for obs in report.actionable_observations:
            if obs.observation_count >= 3:
                recommendations.append(obs.suggested_remedy)

        return OrgReviewResult(
            complexity_score=report.complexity_metrics.complexity_score,
            health_score=report.org_health_score,
            alerts=alerts,
            actionable_observations=actionable,
            pending_proposals=pending,
            complexity_breach=complexity_breach,
            recommendations=recommendations[:5],
        )
    except Exception as exc:
        return OrgReviewResult(
            complexity_score=0.0,
            health_score=0.0,
            alerts=[f"Org review error: {exc}"],
            actionable_observations=0,
            pending_proposals=0,
            complexity_breach=False,
            recommendations=[],
        )


# ---------------------------------------------------------------------------
# Phase 10 — Final Report
# ---------------------------------------------------------------------------

def _format_front_page(
    cfg: DailyLoopConfig,
    ingest: IngestResult,
    regime: RegimeResult,
    routing: RoutingResult,
    dissent: DissentResult,
    cio: CIODecisionResult,
    org: OrgReviewResult,
) -> str:
    date_str = cfg.resolved_date()
    lines = [
        "=" * 72,
        f"  ENIGMA CAPITAL — DAILY INVESTMENT BRIEF",
        f"  {date_str}  |  {DISCLAIMER[:60]}...",
        "=" * 72,
        "",
        f"MACRO REGIME:   {regime.macro_regime}  (confidence: {regime.macro_confidence}%)",
        f"EQUITY STANCE:  {regime.equity_stance}",
        f"BTC/CRYPTO:     {regime.btc_crypto_stance}",
        f"GOLD:           {regime.gold_stance}",
        "",
        "── MARKET SNAPSHOT ────────────────────────────────────────────────",
        f"  SPY:   ${ingest.prices.get('SPY', 0):>8.2f}   1d: {ingest.returns_1d.get('SPY', 0):+.2f}%   20d: {ingest.returns_20d.get('SPY', 0):+.2f}%",
        f"  BTC:   ${ingest.prices.get('BTC', 0):>8,.0f}   1d: {ingest.returns_1d.get('BTC', 0):+.2f}%   20d: {ingest.returns_20d.get('BTC', 0):+.2f}%",
        f"  GLD:   ${ingest.prices.get('GLD', 0):>8.2f}   1d: {ingest.returns_1d.get('GLD', 0):+.2f}%   20d: {ingest.returns_20d.get('GLD', 0):+.2f}%",
        f"  VIX:   {ingest.vix:>8.2f}   DXY: {ingest.dxy:.2f}",
        "",
        "── REGIME DETAIL ──────────────────────────────────────────────────",
    ]
    for sub in regime.sub_assessments:
        lines.append(f"  {sub.name:<15} {sub.label:<25} ({sub.confidence}% conf)")
    lines += [
        "",
        "── CIO DECISION ───────────────────────────────────────────────────",
        f"  Stance:     {cio.final_stance}",
        f"  Confidence: {cio.final_confidence}%",
        f"  Allocation change: {'YES' if cio.allocation_change else 'No'}",
        "",
        "  REQUIRED ACTIONS TODAY:",
    ]
    if cio.required_actions:
        for a in cio.required_actions:
            lines.append(f"    • {a}")
    else:
        lines.append("    (none)")
    lines += [
        "",
        "  WATCHLIST (observe, don't act):",
    ]
    if cio.watchlist_only:
        for w in cio.watchlist_only[:5]:
            lines.append(f"    ◦ {w}")
    else:
        lines.append("    (none)")
    lines += [
        "",
        "── DISSENT HEALTH ─────────────────────────────────────────────────",
        f"  Groupthink alert: {'⚠ YES' if dissent.groupthink_alert else 'No'}",
        f"  Dissent suppressed: {'⚠ YES' if dissent.dissent_suppressed else 'No'}",
        f"  Majority: {dissent.majority_position} ({dissent.majority_pct:.0%} of votes)",
        f"  Sentiment: {dissent.sentiment_state}",
        "",
        "── ORG HEALTH ─────────────────────────────────────────────────────",
        f"  Complexity score: {org.complexity_score:.0f}/100  Health: {org.health_score:.0f}/100",
        f"  Complexity breach: {'⚠ YES' if org.complexity_breach else 'No'}",
        "",
        "── OVERNIGHT ──────────────────────────────────────────────────────",
        f"  {ingest.overnight_summary[:200]}",
        "",
        f"  Specialists engaged: {routing.engaged_specialists}",
        "",
        "=" * 72,
        DISCLAIMER,
        "=" * 72,
    ]
    return "\n".join(lines)


def _format_appendix(
    ingest: IngestResult,
    regime: RegimeResult,
    routing: RoutingResult,
    memos: SpecialistMemoResult,
    dissent: DissentResult,
    pc: PortfolioConstructionResult,
    cio: CIODecisionResult,
    learning: LearningResult,
    org: OrgReviewResult,
    phase_results: list[PhaseResult],
) -> str:
    lines = [
        "",
        "=" * 72,
        "  APPENDIX — FULL PHASE DETAIL",
        "=" * 72,
        "",
        "── PHASE 1: INGEST ─────────────────────────────────────────────────",
        f"  Data source: {ingest.data_source}",
        f"  Prices fetched: {len(ingest.prices)} tickers",
        "",
        "── PHASE 2: REGIME ─────────────────────────────────────────────────",
        f"  {regime.macro_rationale}",
        "",
        "── PHASE 3: ROUTING ────────────────────────────────────────────────",
        routing.routing_rationale,
        f"  Coordinator: {routing.coordinator_notes}",
        "",
        "── PHASE 4: SPECIALIST MEMOS ───────────────────────────────────────",
    ]
    for m in memos.memos:
        lines.append(
            f"  [{m.get('agent','?'):30s}] {m.get('stance','?'):12s} conf:{m.get('confidence',0):3d}%  "
            f"{(m.get('recommendation','')[:60])}{'...' if len(m.get('recommendation','')) > 60 else ''}"
        )
    lines += [
        "",
        "── PHASE 5: DISSENT ────────────────────────────────────────────────",
    ]
    for r in dissent.recommendations:
        lines.append(f"  • {r}")
    lines += [
        "",
        "── PHASE 6: PORTFOLIO CONSTRUCTION ─────────────────────────────────",
        f"  {pc.coordinator_summary}",
    ]
    for ch in pc.allocation_changes:
        lines.append(f"  ▶ {ch['ticker']}: {ch['action']} — {ch['rationale'][:60]}")
    for block in pc.regime_persistence_blocks:
        lines.append(f"  ✗ BLOCKED: {block[:80]}")
    lines += [
        "",
        "── PHASE 7: CIO DECISION ───────────────────────────────────────────",
        f"  Next review trigger: {cio.next_review_trigger}",
    ]
    if cio.challenge_questions:
        lines.append("  Challenge questions for investor:")
        for q in cio.challenge_questions[:3]:
            lines.append(f"    ? {q}")
    lines += [
        "",
        "── PHASE 8: LEARNING ───────────────────────────────────────────────",
        f"  Votes recorded: {learning.votes_recorded}",
        f"  Benchmark snapshot: {'OK' if learning.benchmark_snapshot_recorded else 'FAILED'}",
    ]
    for n in learning.notes:
        lines.append(f"  [note] {n}")
    lines += [
        "",
        "── PHASE 9: ORG REVIEW ─────────────────────────────────────────────",
    ]
    for rec in org.recommendations:
        lines.append(f"  → {rec[:80]}")
    lines += [
        "",
        "── PHASE TIMING ────────────────────────────────────────────────────",
    ]
    for pr in phase_results:
        status_icon = "✓" if pr.ok() else ("⊖" if pr.status == "skipped" else "✗")
        lines.append(f"  {status_icon} {pr.phase:<28} {pr.elapsed_s:.3f}s  {pr.error[:40] if pr.error else ''}")
    return "\n".join(lines)


def _run_final_report(
    cfg: DailyLoopConfig,
    ingest: IngestResult,
    regime: RegimeResult,
    routing: RoutingResult,
    memos: SpecialistMemoResult,
    dissent: DissentResult,
    pc: PortfolioConstructionResult,
    cio: CIODecisionResult,
    learning: LearningResult,
    org: OrgReviewResult,
    phase_results: list[PhaseResult],
) -> FinalReportResult:
    front = _format_front_page(cfg, ingest, regime, routing, dissent, cio, org)
    appendix = _format_appendix(
        ingest, regime, routing, memos, dissent, pc, cio, learning, org, phase_results
    )
    full_report = front + "\n" + appendix

    REPORTS_DAILY_DIR.mkdir(parents=True, exist_ok=True)
    report_path = REPORTS_DAILY_DIR / f"daily_brief_{cfg.resolved_date()}.txt"
    report_path.write_text(full_report, encoding="utf-8")

    return FinalReportResult(
        front_page=front,
        appendix=appendix,
        report_path=str(report_path),
        word_count=len(full_report.split()),
    )


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------

def _persist_result(result: DailyLoopResult) -> None:
    DAILY_LOOPS_DIR.mkdir(parents=True, exist_ok=True)
    path = DAILY_LOOPS_DIR / f"{result.config.resolved_date()}.json"
    # Serialize only the safe-to-serialize parts
    payload = {
        "run_id": result.run_id,
        "date": result.config.resolved_date(),
        "mock": result.config.mock,
        "started_at": result.started_at,
        "completed_at": result.completed_at,
        "total_elapsed_s": result.total_elapsed_s,
        "phases_ok": result.phases_ok(),
        "phases_failed": result.phases_failed(),
        "error_summary": result.error_summary,
        "phase_timing": [
            {"phase": p.phase, "status": p.status, "elapsed_s": p.elapsed_s, "error": p.error}
            for p in result.phase_results
        ],
    }
    if result.regime:
        payload["macro_regime"] = result.regime.macro_regime
        payload["macro_confidence"] = result.regime.macro_confidence
    if result.cio_decision:
        payload["cio_stance"] = result.cio_decision.final_stance
        payload["cio_confidence"] = result.cio_decision.final_confidence
    if result.final_report:
        payload["report_path"] = result.final_report.report_path

    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def load_daily_result(date_str: str) -> Optional[dict]:
    """Load a persisted daily loop result."""
    path = DAILY_LOOPS_DIR / f"{date_str}.json"
    if not path.exists():
        return None
    with open(path) as f:
        return json.load(f)


def list_daily_results(limit: int = 20) -> list[dict]:
    """List recent daily loop results, most recent first."""
    DAILY_LOOPS_DIR.mkdir(parents=True, exist_ok=True)
    files = sorted(DAILY_LOOPS_DIR.glob("*.json"), reverse=True)[:limit]
    results = []
    for f in files:
        try:
            with open(f) as fh:
                results.append(json.load(fh))
        except Exception:
            pass
    return results


# ---------------------------------------------------------------------------
# Main orchestrator
# ---------------------------------------------------------------------------

def run_daily_loop(cfg: Optional[DailyLoopConfig] = None) -> DailyLoopResult:
    """
    Execute all ten phases of the daily operating loop.

    Returns a DailyLoopResult with every phase result and typed outputs.
    Persists a summary JSON to data/processed/daily_loops/.
    """
    import uuid
    if cfg is None:
        cfg = DailyLoopConfig()

    run_id = f"LOOP-{cfg.resolved_date()}-{uuid.uuid4().hex[:6].upper()}"
    started_at = datetime.now().isoformat()
    phase_results: list[PhaseResult] = []
    errors: list[str] = []

    ingest: Optional[IngestResult] = None
    regime_result: Optional[RegimeResult] = None
    routing: Optional[RoutingResult] = None
    memos: Optional[SpecialistMemoResult] = None
    dissent: Optional[DissentResult] = None
    pc: Optional[PortfolioConstructionResult] = None
    cio: Optional[CIODecisionResult] = None
    learning: Optional[LearningResult] = None
    org: Optional[OrgReviewResult] = None
    final: Optional[FinalReportResult] = None

    skip = set(cfg.skip_phases)

    # ── Phase 1: Ingest ──────────────────────────────────────────────────
    pr, ingest = _safe_phase("ingest", lambda: _run_ingest(cfg), "ingest" in skip)
    phase_results.append(pr)
    if pr.status == "error":
        errors.append(f"ingest: {pr.error}")
        ingest = _run_ingest(DailyLoopConfig(mock=True, date=cfg.resolved_date()))

    # ── Phase 2: Regime ──────────────────────────────────────────────────
    pr, regime_result = _safe_phase(
        "regime", lambda: _run_regime(ingest), "regime" in skip or ingest is None
    )
    phase_results.append(pr)
    if pr.status == "error" or regime_result is None:
        errors.append(f"regime: {pr.error}")
        regime_result = RegimeResult(
            macro_regime="Unknown",
            macro_confidence=0,
            macro_rationale="Regime phase failed — defaulting to Unknown.",
            equity_stance="Unknown",
            btc_crypto_stance="Unknown",
            gold_stance="Unknown",
            sub_assessments=[],
            data_source="error_fallback",
        )

    # ── Phase 3: Routing ─────────────────────────────────────────────────
    pr, routing = _safe_phase(
        "routing",
        lambda: _run_routing(cfg, ingest, regime_result),
        "routing" in skip,
    )
    phase_results.append(pr)
    if pr.status == "error" or routing is None:
        errors.append(f"routing: {pr.error}")
        from routing_engine import ALL_SPECIALISTS
        routing = RoutingResult(
            decision_type=cfg.decision_type,
            decision_question=cfg.decision_question,
            engaged_specialists=ALL_SPECIALISTS[:6],
            skipped_specialists=[],
            routing_rationale="Routing error — using minimal specialist set.",
            coordinator_notes="Routing fallback active.",
        )

    # ── Phase 4: Specialist Memos ────────────────────────────────────────
    pr, memos = _safe_phase(
        "memos",
        lambda: _run_memos(cfg, routing, ingest, regime_result),
        "memos" in skip,
    )
    phase_results.append(pr)
    if pr.status == "error" or memos is None:
        errors.append(f"memos: {pr.error}")
        memos = SpecialistMemoResult(memos=[], memo_count=0, mock_mode=True)

    # ── Phase 5: Dissent ─────────────────────────────────────────────────
    pr, dissent = _safe_phase(
        "dissent",
        lambda: _run_dissent(ingest, regime_result, memos),
        "dissent" in skip,
    )
    phase_results.append(pr)
    if pr.status == "error" or dissent is None:
        errors.append(f"dissent: {pr.error}")
        dissent = DissentResult(
            groupthink_alert=False,
            groupthink_reason="",
            dissent_suppressed=False,
            dissenting_agents=[],
            majority_position="hold",
            majority_pct=0.0,
            sentiment_state="healthy_skepticism",
            sentiment_rationale="Dissent phase error — defaulting to no alert.",
            recommendations=[],
        )

    # ── Phase 6: Portfolio Construction ─────────────────────────────────
    pr, pc = _safe_phase(
        "portfolio_construction",
        lambda: _run_portfolio_construction(ingest, regime_result, memos, dissent),
        "portfolio_construction" in skip,
    )
    phase_results.append(pr)
    if pr.status == "error" or pc is None:
        errors.append(f"portfolio_construction: {pr.error}")
        pc = PortfolioConstructionResult(
            allocation_changes=[],
            options_changes=[],
            watchlist_additions=[],
            watchlist_removals=[],
            derisking_triggered=False,
            risk_on_triggered=False,
            regime_persistence_blocks=[],
            coordinator_summary="Portfolio construction phase error.",
        )

    # ── Phase 7: CIO Decision ────────────────────────────────────────────
    pr, cio = _safe_phase(
        "cio_decision",
        lambda: _run_cio_decision(cfg, ingest, regime_result, memos, dissent, pc),
        "cio_decision" in skip,
    )
    phase_results.append(pr)
    if pr.status == "error" or cio is None:
        errors.append(f"cio_decision: {pr.error}")
        cio = CIODecisionResult(
            final_stance="hold",
            final_confidence=0,
            required_actions=[],
            watchlist_only=[],
            signals=[],
            actions=[],
            dissent_acknowledged=False,
            challenge_questions=[],
            next_review_trigger="Manual review required",
            allocation_change=False,
        )

    # ── Phase 8: Learning ────────────────────────────────────────────────
    pr, learning = _safe_phase(
        "learning",
        lambda: _run_learning(ingest, regime_result, memos, cio),
        "learning" in skip,
    )
    phase_results.append(pr)
    if pr.status == "error" or learning is None:
        errors.append(f"learning: {pr.error}")
        learning = LearningResult(
            votes_recorded=0,
            thesis_updates=0,
            regime_attributions_recorded=0,
            benchmark_snapshot_recorded=False,
            alternative_portfolio_snapshots=0,
            notes=[f"Learning phase failed: {pr.error}"],
        )

    # ── Phase 9: Org Review ──────────────────────────────────────────────
    pr, org = _safe_phase(
        "org_review",
        lambda: _run_org_review(ingest, memos),
        "org_review" in skip,
    )
    phase_results.append(pr)
    if pr.status == "error" or org is None:
        errors.append(f"org_review: {pr.error}")
        org = OrgReviewResult(
            complexity_score=0.0,
            health_score=0.0,
            alerts=[],
            actionable_observations=0,
            pending_proposals=0,
            complexity_breach=False,
            recommendations=[],
        )

    # ── Phase 10: Final Report ───────────────────────────────────────────
    pr, final = _safe_phase(
        "final_report",
        lambda: _run_final_report(
            cfg, ingest, regime_result, routing, memos, dissent, pc, cio, learning, org, phase_results
        ),
        "final_report" in skip,
    )
    phase_results.append(pr)
    if pr.status == "error":
        errors.append(f"final_report: {pr.error}")

    completed_at = datetime.now().isoformat()
    total_elapsed = sum(p.elapsed_s for p in phase_results)

    result = DailyLoopResult(
        config=cfg,
        run_id=run_id,
        started_at=started_at,
        completed_at=completed_at,
        total_elapsed_s=round(total_elapsed, 3),
        phase_results=phase_results,
        ingest=ingest,
        regime=regime_result,
        routing=routing,
        memos=memos,
        dissent=dissent,
        portfolio_construction=pc,
        cio_decision=cio,
        learning=learning,
        org_review=org,
        final_report=final,
        error_summary=errors,
    )

    try:
        _persist_result(result)
    except Exception:
        pass

    # Auto-generate PDF alongside the text report
    if not cfg.mock:
        try:
            from pdf_report import generate_pdf
            pdf_path = generate_pdf(result)
            if cfg.verbose:
                print(f"  PDF: {pdf_path}")
        except Exception:
            pass

    return result
