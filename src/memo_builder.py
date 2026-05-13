"""
Memo Builder — Phase 3.
Structured inter-agent memo format and context packet assembly.
Prevents full prompt cross-contamination. Preserves specialist isolation.
Advisory only — no live trading.
"""

from __future__ import annotations
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional

ROOT_DIR = Path(__file__).parent.parent
CONSTITUTION_PATH = ROOT_DIR / "constitution" / "fund_constitution.md"

# Relevant constitutional sections surfaced to specialists by article
_CONSTITUTION_EXCERPTS: dict[str, str] = {
    "philosophy": "Articles II.1–II.4: Scarcity thesis, asymmetry focus, macro-technical hierarchy, RSI divergence rule (FIRM — bearish divergence at resistance → WAIT_FOR_CONFIRMATION).",
    "confidence": "Article IV: Confidence 1–100. Mandatory adjustments: −15 if ≥2 strong dissents, −20 if invalidation held, −5 per RSI divergence occurrence, Phase 1 cap at 65.",
    "thesis_lifecycle": "Article V: Emerging→Confirming→High Conviction→Crowded→Distribution Risk→Breakdown Risk→Invalidated. Sizing scales with state.",
    "signal_action": "Article VI: Signal ≠ Action. Most signals → NO immediate action. WAIT_FOR_CONFIRMATION is the default for ambiguous signals.",
    "portfolio_buckets": "Article VII: Core/Structural 50–75%, Tactical 10–30%, Options 10–20%, Experimental ≤20%, Defensive Reserve 0–40%. No margin, no shorts, no 0DTE, no spreads.",
    "constraints": "Article VII.2: No margin. No short selling. No 0DTE options. No spreads. No direct crypto on-chain. Single name <20% without CIO written justification.",
    "isolation": "Article III.4: You must NOT receive other specialists' raw analyses. Your context is intentionally lean to preserve diversity of thought.",
}


# ── Memo data structure ────────────────────────────────────────────────────

@dataclass
class AgentMemo:
    """Structured output from a single specialist or coordinator."""
    agent: str
    decision_type: str
    date: str
    stance: str          # Bullish / Bearish / Neutral / Hold / Trim / Wait / No Action
    confidence: int      # 1–100
    key_points: list[str]         # max 5 bullets
    recommendation: str           # 1–2 sentences
    dissent_flag: bool = False     # True if disagreeing with apparent consensus
    dissent_reason: str = ""
    risk_flags: list[str] = field(default_factory=list)
    invalidation_signals: list[str] = field(default_factory=list)
    raw_response: str = ""

    def to_summary(self, max_points: int = 3) -> str:
        """Compact summary for coordinator synthesis — NOT full raw response."""
        points = "\n".join(f"  - {p}" for p in self.key_points[:max_points])
        dissent = f"\n  DISSENT: {self.dissent_reason}" if self.dissent_flag else ""
        risks = f"\n  RISKS: {' | '.join(self.risk_flags)}" if self.risk_flags else ""
        return (
            f"[{self.agent.upper()}] Stance: {self.stance} | Confidence: {self.confidence}\n"
            f"{points}\n"
            f"  Recommendation: {self.recommendation}"
            f"{dissent}{risks}"
        )

    def to_dict(self) -> dict:
        return {
            "agent": self.agent,
            "decision_type": self.decision_type,
            "date": self.date,
            "stance": self.stance,
            "confidence": self.confidence,
            "key_points": self.key_points,
            "recommendation": self.recommendation,
            "dissent_flag": self.dissent_flag,
            "dissent_reason": self.dissent_reason,
            "risk_flags": self.risk_flags,
            "invalidation_signals": self.invalidation_signals,
        }


# ── Context packet assembly ────────────────────────────────────────────────

@dataclass
class PortfolioSnapshot:
    """Lean portfolio state passed to specialists."""
    total_value: float
    cash_pct: float
    positions: list[dict]   # [{"ticker": "SPY", "pct": 20.0, "bucket": "core_structural", "thesis_state": "Confirming"}]
    active_theses: list[dict]  # [{"id": "THESIS-001", "asset": "SPY", "state": "Confirming", "confidence": 60}]
    latest_nav_return_pct: float = 0.0
    options_premium_at_risk_pct: float = 0.0


def build_context_packet(
    agent: str,
    decision_type: str,
    decision_question: str,
    portfolio: PortfolioSnapshot,
    relevant_constitution_articles: Optional[list[str]] = None,
    prior_coordinator_summary: str = "",
    asset_context: Optional[dict] = None,
) -> str:
    """
    Assemble a lean, isolated context packet for a specialist.

    The packet intentionally excludes other specialists' raw analyses.
    Constitution sections are included only where relevant.
    """
    if relevant_constitution_articles is None:
        relevant_constitution_articles = ["philosophy", "signal_action", "constraints"]

    constitution_block = "\n".join(
        f"- {_CONSTITUTION_EXCERPTS[a]}"
        for a in relevant_constitution_articles
        if a in _CONSTITUTION_EXCERPTS
    )

    positions_table = _format_positions_table(portfolio.positions)
    theses_table = _format_theses_table(portfolio.active_theses)

    asset_block = ""
    if asset_context:
        asset_block = "\n## Asset Context\n" + "\n".join(
            f"- **{k}:** {v}" for k, v in asset_context.items()
        )

    coordinator_block = ""
    if prior_coordinator_summary:
        coordinator_block = f"\n## Coordinator Summary (Factual Context Only)\n{prior_coordinator_summary}\n"

    isolation_notice = (
        "\n---\n"
        "**ISOLATION NOTICE:** You are receiving a lean context packet. "
        "Other specialists' analyses are intentionally excluded to preserve your independent judgment. "
        "Do not attempt to infer consensus from this context. "
        "Give your honest, domain-specific assessment."
    )

    return f"""# Specialist Briefing — {agent.replace('_', ' ').title()}
Date: {datetime.now().strftime('%Y-%m-%d')}
Decision Type: {decision_type}

## Your Decision Question
{decision_question}

## Constitutional Principles Relevant to This Decision
{constitution_block}

## Current Portfolio State
- Total Value: ${portfolio.total_value:,.0f}
- Cash / Defensive Reserve: {portfolio.cash_pct:.1f}%
- Options Premium at Risk: {portfolio.options_premium_at_risk_pct:.1f}%
- Portfolio Return (latest): {portfolio.latest_nav_return_pct:+.2f}%

### Positions
{positions_table}

### Active Theses
{theses_table}
{asset_block}{coordinator_block}{isolation_notice}

## Required Output Format
Respond ONLY in the following structured format:

```
STANCE: [Bullish / Bearish / Neutral / Hold / Trim / Wait / No Action]
CONFIDENCE: [integer 1–100]
KEY POINTS:
- [point 1 — your domain-specific insight]
- [point 2]
- [point 3]
RECOMMENDATION: [1–2 sentences: specific action or non-action recommendation]
DISSENT: [Yes/No]
DISSENT REASON: [If Yes: why you disagree with what you expect the consensus to be]
RISK FLAGS: [pipe-separated list, or "none"]
INVALIDATION SIGNALS: [what would change your view — pipe-separated, or "none"]
```
"""


def _format_positions_table(positions: list[dict]) -> str:
    if not positions:
        return "No positions (100% cash/STRC proxy)"
    header = "| Ticker | % Portfolio | Bucket | Thesis State |"
    sep = "|---|---|---|---|"
    rows = [
        f"| {p.get('ticker', '?')} | {p.get('pct', 0):.1f}% "
        f"| {p.get('bucket', '?')} | {p.get('thesis_state', '?')} |"
        for p in positions
    ]
    return "\n".join([header, sep] + rows)


def _format_theses_table(theses: list[dict]) -> str:
    if not theses:
        return "No active theses"
    header = "| ID | Asset | State | Confidence |"
    sep = "|---|---|---|---|"
    rows = [
        f"| {t.get('id', '?')} | {t.get('asset', '?')} "
        f"| {t.get('state', '?')} | {t.get('confidence', '?')} |"
        for t in theses
    ]
    return "\n".join([header, sep] + rows)


# ── Memo parsing ───────────────────────────────────────────────────────────

def parse_memo_from_response(agent: str, decision_type: str, response_text: str) -> AgentMemo:
    """
    Extract structured AgentMemo from a specialist's markdown response.
    Tolerant parser — falls back gracefully on malformed output.
    """
    def _extract(pattern: str, default: str = "") -> str:
        m = re.search(pattern, response_text, re.IGNORECASE | re.DOTALL)
        return m.group(1).strip() if m else default

    stance = _extract(r"STANCE:\s*(.+?)(?:\n|$)", "Unknown")
    confidence_str = _extract(r"CONFIDENCE:\s*(\d+)", "50")
    confidence = max(1, min(100, int(confidence_str)))

    # Extract bullet points under KEY POINTS
    key_points_block = _extract(r"KEY POINTS:\s*((?:[-•*].+\n?)+)", "")
    key_points = [
        re.sub(r"^[-•*]\s*", "", line).strip()
        for line in key_points_block.splitlines()
        if line.strip() and re.match(r"^[-•*]", line.strip())
    ][:5]

    recommendation = _extract(r"RECOMMENDATION:\s*(.+?)(?:\nDISSENT:|$)", "No recommendation provided.")
    recommendation = re.sub(r"\s+", " ", recommendation).strip()

    dissent_raw = _extract(r"DISSENT:\s*(.+?)(?:\n|$)", "No").strip().lower()
    dissent_flag = dissent_raw.startswith("yes")
    dissent_reason = _extract(r"DISSENT REASON:\s*(.+?)(?:\nRISK|$)", "").strip()

    risk_flags_raw = _extract(r"RISK FLAGS:\s*(.+?)(?:\n|$)", "none")
    risk_flags = [] if risk_flags_raw.lower() == "none" else [f.strip() for f in risk_flags_raw.split("|")]

    invalidation_raw = _extract(r"INVALIDATION SIGNALS:\s*(.+?)(?:\n|$)", "none")
    invalidation_signals = [] if invalidation_raw.lower() == "none" else [s.strip() for s in invalidation_raw.split("|")]

    return AgentMemo(
        agent=agent,
        decision_type=decision_type,
        date=datetime.now().strftime("%Y-%m-%d"),
        stance=stance,
        confidence=confidence,
        key_points=key_points,
        recommendation=recommendation,
        dissent_flag=dissent_flag,
        dissent_reason=dissent_reason,
        risk_flags=risk_flags,
        invalidation_signals=invalidation_signals,
        raw_response=response_text,
    )


# ── Coordinator synthesis ──────────────────────────────────────────────────

def summarize_memos_for_coordinator(
    memos: list[AgentMemo],
    max_points_per_agent: int = 2,
) -> str:
    """
    Produces a compact coordinator-level summary of specialist memos.
    This summary (NOT raw memos) is what flows to the next wave.
    """
    if not memos:
        return "No specialist memos received."

    stances = [m.stance for m in memos]
    confidences = [m.confidence for m in memos]
    avg_confidence = sum(confidences) / len(confidences)
    dissenters = [m for m in memos if m.dissent_flag]

    # Stance consensus
    stance_counts: dict[str, int] = {}
    for s in stances:
        stance_counts[s] = stance_counts.get(s, 0) + 1
    dominant_stance = max(stance_counts, key=stance_counts.__getitem__)

    lines = [
        f"**Specialists engaged:** {len(memos)}",
        f"**Dominant stance:** {dominant_stance} ({stance_counts[dominant_stance]}/{len(memos)} specialists)",
        f"**Average confidence:** {avg_confidence:.0f}/100",
        f"**Dissenters:** {len(dissenters)} ({', '.join(d.agent for d in dissenters) or 'none'})",
        "",
        "**Specialist Summaries:**",
    ]
    for memo in memos:
        lines.append(memo.to_summary(max_points=max_points_per_agent))
        lines.append("")

    if dissenters:
        lines.append("**Dissent Detail:**")
        for d in dissenters:
            lines.append(f"- {d.agent}: {d.dissent_reason}")

    all_risks = []
    for m in memos:
        all_risks.extend(m.risk_flags)
    if all_risks:
        lines.append(f"\n**Aggregated Risk Flags:** {' | '.join(set(all_risks))}")

    return "\n".join(lines)


def build_cio_brief(
    research_summary: str,
    bear_case_summary: str,
    portfolio_construction_notes: str,
    decision_question: str,
    routing_rationale: str,
) -> str:
    """
    Assemble the final brief the CIO receives — coordinator outputs only, no raw specialist memos.
    """
    return f"""# CIO Decision Brief
Date: {datetime.now().strftime('%Y-%m-%d')}

## Decision Question
{decision_question}

## Routing
{routing_rationale}

---

## Research Coordinator Summary
{research_summary}

---

## Risk & Dissent Coordinator Summary
{bear_case_summary}

---

## Portfolio Construction Notes
{portfolio_construction_notes}

---

## Constitutional Reference
- Confidence scoring: Article IV
- Thesis lifecycle: Article V
- Signal vs Action: Article VI
- Portfolio constraints: Article VII

## CIO Required Output
```
FINAL_STANCE: [Bullish / Bearish / Neutral / Hold / Trim / Wait / No Action]
FINAL_CONFIDENCE: [integer 1–100]
ALLOCATION_CHANGE: [Yes/No]
ALLOCATION_DETAIL: [If Yes: specific changes with $ amounts and % of portfolio]
ACTION_ORDERS: [List of specific actions, or "Hold all positions"]
DISSENT_ACKNOWLEDGED: [Yes/No — confirm dissenting views were considered]
CHALLENGE_QUESTIONS: [2–3 questions the CIO is asking itself before committing]
NEXT_REVIEW_TRIGGER: [What specific event would trigger early re-evaluation]
```
"""
