"""
Committee Session Orchestrator — Phase 3.
4-wave hierarchical committee runner with routing, isolation, and coordinator synthesis.
Advisory only — no live trading.
"""

from __future__ import annotations
import json
import os
import sys
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional

ROOT_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT_DIR / "src"))

# Load .env so ANTHROPIC_API_KEY is available regardless of how this module is imported
_env_path = ROOT_DIR / ".env"
if _env_path.exists():
    for _line in _env_path.read_text().splitlines():
        _line = _line.strip()
        if _line and not _line.startswith("#") and "=" in _line:
            _k, _v = _line.split("=", 1)
            if _v.strip():
                os.environ[_k.strip()] = _v.strip()

SESSIONS_DIR = ROOT_DIR / "data" / "processed" / "committee_sessions"
AGENTS_DIR = ROOT_DIR / "agents"
CONSTITUTION_PATH = ROOT_DIR / "constitution" / "fund_constitution.md"

from memo_builder import (
    AgentMemo,
    PortfolioSnapshot,
    build_cio_brief,
    build_context_packet,
    parse_memo_from_response,
    summarize_memos_for_coordinator,
)
from routing_engine import (
    DecisionType,
    RoutingContext,
    RoutingPlan,
    describe_routing_plan,
    route_decision,
)

DISCLAIMER = "ADVISORY ONLY. All outputs are simulated. Not financial advice."


# ── Session data structures ────────────────────────────────────────────────

@dataclass
class CIODecision:
    final_stance: str
    final_confidence: int
    allocation_change: bool
    allocation_detail: str
    action_orders: list[str]
    dissent_acknowledged: bool
    challenge_questions: list[str]
    next_review_trigger: str
    raw_response: str = ""

    def to_dict(self) -> dict:
        return {
            "final_stance": self.final_stance,
            "final_confidence": self.final_confidence,
            "allocation_change": self.allocation_change,
            "allocation_detail": self.allocation_detail,
            "action_orders": self.action_orders,
            "dissent_acknowledged": self.dissent_acknowledged,
            "challenge_questions": self.challenge_questions,
            "next_review_trigger": self.next_review_trigger,
        }


@dataclass
class CommitteeSession:
    session_id: str
    decision_type: str
    decision_question: str
    date: str
    routing_plan: dict
    specialist_memos: list[dict]
    research_summary: str
    bear_case_summary: str
    portfolio_construction_notes: str
    cio_decision: Optional[dict]
    disclaimer: str = DISCLAIMER

    def to_dict(self) -> dict:
        return {
            "session_id": self.session_id,
            "decision_type": self.decision_type,
            "decision_question": self.decision_question,
            "date": self.date,
            "routing_plan": self.routing_plan,
            "specialist_memos_count": len(self.specialist_memos),
            "specialists_engaged": [m["agent"] for m in self.specialist_memos],
            "research_summary": self.research_summary,
            "bear_case_summary": self.bear_case_summary,
            "portfolio_construction_notes": self.portfolio_construction_notes,
            "cio_decision": self.cio_decision,
            "disclaimer": self.disclaimer,
        }


# ── Agent prompt loader ────────────────────────────────────────────────────

def _load_agent_prompt(agent: str) -> str:
    """Load agent system prompt from agents/ directory."""
    # Check coordinators subdirectory first, then root agents/
    paths = [
        AGENTS_DIR / "coordinators" / f"{agent}.md",
        AGENTS_DIR / f"{agent}.md",
    ]
    for path in paths:
        if path.exists():
            return path.read_text()
    return f"# {agent}\nNo system prompt found at {paths}."


def _load_constitution_excerpt() -> str:
    if CONSTITUTION_PATH.exists():
        full = CONSTITUTION_PATH.read_text()
        # Return Articles I–IV (mission, philosophy, governance, confidence) as excerpt
        lines = full.splitlines()
        excerpt_lines = []
        in_scope = False
        for line in lines:
            if line.startswith("## Article I"):
                in_scope = True
            if line.startswith("## Article V") and in_scope:
                break
            if in_scope:
                excerpt_lines.append(line)
        return "\n".join(excerpt_lines)
    return "Constitution not found."


# ── Mock agent response (for testing without API key) ─────────────────────

def _mock_specialist_response(agent: str, decision_type: str) -> str:
    """Generate a plausible mock memo for testing purposes."""
    stances = {
        "macro_strategist": "Bullish",
        "scarcity_strategist": "Bullish",
        "technical_chart_expert": "Wait",
        "momentum_trader": "Bullish",
        "crypto_strategist": "Bullish",
        "commodity_specialist": "Neutral",
        "options_specialist": "Neutral",
        "valuation_analyst": "Neutral",
        "sentiment_analyst": "Neutral",
        "bear_case_analyst": "Bearish",
        "risk_officer": "Hold",
        "portfolio_historian": "Neutral",
        "benchmark_analyst": "Neutral",
        "technology_structural_change": "Bullish",
        "meta_philosophy_auditor": "Wait",
        "psychological_agent": "Hold",
    }
    stance = stances.get(agent, "Neutral")
    confidence = 60 if stance == "Bullish" else 40 if stance == "Bearish" else 50

    return f"""STANCE: {stance}
CONFIDENCE: {confidence}
KEY POINTS:
- Mock analysis from {agent} for {decision_type}
- Domain-specific insight would appear here in live mode
- Risk factors considered within specialist domain
RECOMMENDATION: Maintain current posture pending further data. Monitor key indicators.
DISSENT: {"Yes" if stance == "Bearish" else "No"}
DISSENT REASON: {"Bear case analyst maintains cautious view as counterweight to consensus." if stance == "Bearish" else ""}
RISK FLAGS: {"elevated volatility risk | tail risk unpriced" if agent == "risk_officer" else "none"}
INVALIDATION SIGNALS: {"price breaks key support | volume divergence" if stance != "Neutral" else "none"}
"""


# ── Live agent call (requires ANTHROPIC_API_KEY) ──────────────────────────

def _call_agent_live(agent: str, context_packet: str) -> str:
    """Call Claude API with agent system prompt + context packet. Returns raw text."""
    try:
        import anthropic
        import os

        api_key = os.environ.get("ANTHROPIC_API_KEY", "")
        if not api_key:
            raise RuntimeError("ANTHROPIC_API_KEY not set")

        client = anthropic.Anthropic(api_key=api_key)
        system_prompt = _load_agent_prompt(agent)

        _AGENT_MODELS = {
            "cio": "claude-sonnet-4-6",
            "research_coordinator": "claude-sonnet-4-6",
        }
        model = _AGENT_MODELS.get(agent, "claude-haiku-4-5-20251001")

        # CIO needs more tokens: allocation table + metadata + challenge questions
        if agent == "cio":
            max_tok = 2048
        elif model.startswith("claude-haiku"):
            max_tok = 512
        else:
            max_tok = 1024

        response = client.messages.create(
            model=model,
            max_tokens=max_tok,
            system=system_prompt,
            messages=[{"role": "user", "content": context_packet}],
        )
        return response.content[0].text

    except ImportError:
        raise RuntimeError("anthropic package not installed. Run: pip install anthropic")


# ── CIO decision parser ────────────────────────────────────────────────────

def _parse_cio_decision(response_text: str) -> CIODecision:
    """Extract structured CIO decision from response."""
    import re

    def _extract(pattern: str, default: str = "") -> str:
        m = re.search(pattern, response_text, re.IGNORECASE | re.DOTALL)
        return m.group(1).strip() if m else default

    final_stance = _extract(r"FINAL_STANCE:\s*(.+?)(?:\n|$)", "Hold")
    confidence_str = _extract(r"FINAL_CONFIDENCE:\s*(\d+)", "50")
    final_confidence = max(1, min(100, int(confidence_str)))

    allocation_raw = _extract(r"ALLOCATION_CHANGE:\s*(.+?)(?:\n|$)", "No").strip().lower()
    allocation_change = allocation_raw.startswith("yes")
    allocation_detail = _extract(r"ALLOCATION_DETAIL:\s*(.+?)(?:\nACTION|$)", "No changes.")

    action_raw = _extract(r"ACTION_ORDERS:\s*(.+?)(?:\nDISSENT|$)", "Hold all positions.")
    action_orders = [a.strip().lstrip("-•* ") for a in action_raw.splitlines() if a.strip()]

    dissent_raw = _extract(r"DISSENT_ACKNOWLEDGED:\s*(.+?)(?:\n|$)", "Yes").strip().lower()
    dissent_acknowledged = not dissent_raw.startswith("no")

    challenge_raw = _extract(r"CHALLENGE_QUESTIONS:\s*(.+?)(?:\nNEXT|$)", "")
    challenge_questions = [
        q.strip().lstrip("-•* ")
        for q in challenge_raw.splitlines()
        if q.strip()
    ][:3]

    next_review_trigger = _extract(
        r"NEXT_REVIEW_TRIGGER:\s*(.+?)(?:\n|$)",
        "Next scheduled review."
    )

    return CIODecision(
        final_stance=final_stance,
        final_confidence=final_confidence,
        allocation_change=allocation_change,
        allocation_detail=allocation_detail.strip(),
        action_orders=action_orders or ["Hold all positions."],
        dissent_acknowledged=dissent_acknowledged,
        challenge_questions=challenge_questions,
        next_review_trigger=next_review_trigger,
        raw_response=response_text,
    )


def _mock_cio_decision(decision_question: str) -> str:
    return f"""FINAL_STANCE: Hold
FINAL_CONFIDENCE: 58
ALLOCATION_CHANGE: No
ALLOCATION_DETAIL: No changes to current allocations pending additional confirmation.
ACTION_ORDERS:
- Hold all current positions at existing sizing
- Monitor RSI and volume for confirmation signals
- Re-evaluate if macro regime shift confirmed by two additional data points
DISSENT_ACKNOWLEDGED: Yes
CHALLENGE_QUESTIONS:
- Are we holding because the thesis is intact, or because we are anchored to our entry price?
- What single piece of data would most change this assessment?
- Is the bear case analyst's concern about crowding supported by positioning data?
NEXT_REVIEW_TRIGGER: Any invalidation condition within 20% of trigger, or major macro data release
"""


# ── Main orchestration ─────────────────────────────────────────────────────

def run_committee_session(
    decision_type: DecisionType,
    decision_question: str,
    portfolio: PortfolioSnapshot,
    routing_context: Optional[RoutingContext] = None,
    asset_context: Optional[dict] = None,
    live: bool = False,
    save_session: bool = True,
) -> CommitteeSession:
    """
    Run a full orchestrated committee session.

    Wave 1: Specialists (isolated context packets, no cross-contamination)
    Wave 2: Research Coordinator + Risk & Dissent Coordinator synthesis
    Wave 3: CIO receives coordinator briefs (not raw specialist memos)

    Args:
        live: If True, calls Claude API. If False, uses mock responses (for testing).
        save_session: If True, saves session JSON to data/processed/committee_sessions/.
    """
    session_id = f"SESSION-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
    date_str = datetime.now().strftime("%Y-%m-%d")

    # ── Route ─────────────────────────────────────────────────────────────
    plan = route_decision(decision_type, routing_context)

    # ── Wave 1: Specialists ────────────────────────────────────────────────
    specialist_memos: list[AgentMemo] = []

    # Determine which constitution articles are relevant per decision type
    constitution_articles = _articles_for_decision(decision_type)

    for specialist in plan.specialists:
        context_packet = build_context_packet(
            agent=specialist,
            decision_type=decision_type.value,
            decision_question=decision_question,
            portfolio=portfolio,
            relevant_constitution_articles=constitution_articles,
            asset_context=asset_context,
        )

        if live:
            raw_response = _call_agent_live(specialist, context_packet)
        else:
            raw_response = _mock_specialist_response(specialist, decision_type.value)

        memo = parse_memo_from_response(specialist, decision_type.value, raw_response)
        specialist_memos.append(memo)

    # ── Wave 2a: Research Coordinator synthesis ────────────────────────────
    # Only non-bear-case memos go to the research summary
    research_memos = [m for m in specialist_memos if m.agent != "bear_case_analyst"]
    research_summary = summarize_memos_for_coordinator(research_memos)

    # ── Wave 2b: Risk & Dissent Coordinator ───────────────────────────────
    bear_memos = specialist_memos  # risk coordinator sees all memos
    bear_case_summary = _build_bear_case_summary(bear_memos)

    # ── Wave 2c: Portfolio Construction notes (simple pass-through for now) ──
    portfolio_construction_notes = _build_portfolio_notes(portfolio, plan)

    # ── Wave 3: CIO ───────────────────────────────────────────────────────
    cio_brief = build_cio_brief(
        research_summary=research_summary,
        bear_case_summary=bear_case_summary,
        portfolio_construction_notes=portfolio_construction_notes,
        decision_question=decision_question,
        routing_rationale=describe_routing_plan(plan),
    )

    if live:
        cio_raw = _call_agent_live("cio", cio_brief)
    else:
        cio_raw = _mock_cio_decision(decision_question)

    cio_decision = _parse_cio_decision(cio_raw)

    # ── Assemble session ───────────────────────────────────────────────────
    session = CommitteeSession(
        session_id=session_id,
        decision_type=decision_type.value,
        decision_question=decision_question,
        date=date_str,
        routing_plan={
            "specialists_engaged": plan.specialists,
            "coordinators_engaged": plan.coordinators,
            "skipped": plan.skipped,
            "conditional_additions": plan.conditional_additions,
            "rationale": plan.rationale,
        },
        specialist_memos=[m.to_dict() for m in specialist_memos],
        research_summary=research_summary,
        bear_case_summary=bear_case_summary,
        portfolio_construction_notes=portfolio_construction_notes,
        cio_decision=cio_decision.to_dict(),
    )

    if save_session:
        _save_session(session)

    return session


def _articles_for_decision(decision_type: DecisionType) -> list[str]:
    mapping = {
        DecisionType.FULL_COMMITTEE: ["philosophy", "confidence", "thesis_lifecycle", "signal_action", "portfolio_buckets", "constraints"],
        DecisionType.CRYPTO_CHANGE: ["philosophy", "confidence", "signal_action", "constraints"],
        DecisionType.COMMODITY_CHANGE: ["philosophy", "signal_action", "constraints"],
        DecisionType.OPTIONS_REVIEW: ["signal_action", "constraints", "portfolio_buckets"],
        DecisionType.TECHNICAL_SIGNAL: ["philosophy", "signal_action"],
        DecisionType.THESIS_REVIEW: ["thesis_lifecycle", "confidence", "signal_action"],
        DecisionType.MACRO_UPDATE: ["philosophy", "confidence", "portfolio_buckets"],
        DecisionType.RISK_ALERT: ["confidence", "portfolio_buckets", "constraints"],
        DecisionType.LEARNING_REVIEW: ["thesis_lifecycle", "confidence"],
    }
    return mapping.get(decision_type, ["philosophy", "signal_action", "constraints"])


def _build_bear_case_summary(memos: list[AgentMemo]) -> str:
    dissenters = [m for m in memos if m.dissent_flag]
    bear_analyst = next((m for m in memos if m.agent == "bear_case_analyst"), None)
    risk_officer = next((m for m in memos if m.agent == "risk_officer"), None)

    lines = ["**Bear Case & Risk Summary**", ""]

    if bear_analyst:
        lines += [f"**Bear Case Analyst:** {bear_analyst.stance} ({bear_analyst.confidence}/100)"]
        for pt in bear_analyst.key_points:
            lines.append(f"  - {pt}")
        lines.append(f"  Recommendation: {bear_analyst.recommendation}")
        lines.append("")

    if risk_officer:
        lines += [f"**Risk Officer:** {risk_officer.stance} ({risk_officer.confidence}/100)"]
        if risk_officer.risk_flags:
            lines.append(f"  Risk Flags: {' | '.join(risk_officer.risk_flags)}")
        lines.append(f"  Recommendation: {risk_officer.recommendation}")
        lines.append("")

    if dissenters:
        lines.append(f"**{len(dissenters)} specialist(s) dissenting:**")
        for d in dissenters:
            lines.append(f"  - {d.agent}: {d.dissent_reason or d.recommendation}")
    else:
        lines.append("**No specialist dissent registered.**")

    all_risks = []
    for m in memos:
        all_risks.extend(m.risk_flags)
    unique_risks = list(dict.fromkeys(all_risks))  # preserve order, deduplicate
    if unique_risks:
        lines.append(f"\n**Aggregated Risk Flags:** {' | '.join(unique_risks)}")

    # Check mandatory confidence adjustments
    n_strong_dissent = sum(1 for m in memos if m.dissent_flag and m.stance in ("Bearish",))
    adjustments = []
    if n_strong_dissent >= 2:
        adjustments.append("−15 (≥2 strong dissents)")
    if adjustments:
        lines.append(f"\n**Mandatory Confidence Adjustments Required:** {', '.join(adjustments)}")

    return "\n".join(lines)


def _build_portfolio_notes(portfolio: PortfolioSnapshot, plan: RoutingPlan) -> str:
    positions_str = ", ".join(
        f"{p.get('ticker', '?')} {p.get('pct', 0):.1f}%"
        for p in portfolio.positions
    ) or "No equity positions"

    return (
        f"Current portfolio: {positions_str}\n"
        f"Cash/Reserve: {portfolio.cash_pct:.1f}% | "
        f"Options at risk: {portfolio.options_premium_at_risk_pct:.1f}%\n"
        f"Decision type '{plan.decision_type.value}' — "
        f"portfolio construction review {'required' if plan.decision_type in (DecisionType.FULL_COMMITTEE, DecisionType.CRYPTO_CHANGE, DecisionType.COMMODITY_CHANGE) else 'not required'} "
        f"for this session type."
    )


def _save_session(session: CommitteeSession) -> None:
    SESSIONS_DIR.mkdir(parents=True, exist_ok=True)
    path = SESSIONS_DIR / f"{session.session_id}.json"
    with open(path, "w") as f:
        json.dump(session.to_dict(), f, indent=2, default=str)


def load_session(session_id: str) -> Optional[dict]:
    path = SESSIONS_DIR / f"{session_id}.json"
    if not path.exists():
        return None
    with open(path) as f:
        return json.load(f)


def list_sessions(limit: int = 20) -> list[dict]:
    if not SESSIONS_DIR.exists():
        return []
    sessions = sorted(SESSIONS_DIR.glob("SESSION-*.json"), reverse=True)[:limit]
    results = []
    for p in sessions:
        with open(p) as f:
            data = json.load(f)
        results.append({
            "session_id": data.get("session_id", ""),
            "date": data.get("date", ""),
            "decision_type": data.get("decision_type", ""),
            "decision_question": data.get("decision_question", "")[:80],
            "specialists_engaged": data.get("specialists_engaged", []),
            "cio_stance": (data.get("cio_decision") or {}).get("final_stance", "?"),
            "cio_confidence": (data.get("cio_decision") or {}).get("final_confidence", 0),
        })
    return results
