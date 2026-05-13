"""
Routing Engine — Phase 3.
Maps decision types to specialist sets. Prevents every specialist from running on every decision.
Advisory only — no live trading.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class DecisionType(str, Enum):
    FULL_COMMITTEE = "full_committee"
    CRYPTO_CHANGE = "crypto_change"
    COMMODITY_CHANGE = "commodity_change"
    OPTIONS_REVIEW = "options_review"
    TECHNICAL_SIGNAL = "technical_signal"
    THESIS_REVIEW = "thesis_review"
    MACRO_UPDATE = "macro_update"
    RISK_ALERT = "risk_alert"
    LEARNING_REVIEW = "learning_review"


# All 13 domain specialists (excludes CIO, coordinators, meta-auditor, psychological)
ALL_SPECIALISTS = [
    "macro_strategist",
    "scarcity_strategist",
    "technology_structural_change",
    "technical_chart_expert",
    "options_specialist",
    "momentum_trader",
    "crypto_strategist",
    "commodity_specialist",
    "valuation_analyst",
    "sentiment_analyst",
    "bear_case_analyst",
    "risk_officer",
    "portfolio_historian",
    "benchmark_analyst",
]

# Coordinators (always available, engaged based on session type)
COORDINATORS = [
    "research_coordinator",
    "portfolio_construction_coordinator",
    "risk_dissent_coordinator",
    "learning_coordinator",
]

# Base specialist sets per decision type
_BASE_SPECIALIST_SETS: dict[DecisionType, list[str]] = {
    DecisionType.FULL_COMMITTEE: ALL_SPECIALISTS[:],

    DecisionType.CRYPTO_CHANGE: [
        "macro_strategist",
        "crypto_strategist",
        "scarcity_strategist",
        "sentiment_analyst",
        "risk_officer",
        "meta_philosophy_auditor",
    ],

    DecisionType.COMMODITY_CHANGE: [
        "commodity_specialist",
        "scarcity_strategist",
        "macro_strategist",
        "technical_chart_expert",
        "risk_officer",
    ],

    DecisionType.OPTIONS_REVIEW: [
        "options_specialist",
        "technical_chart_expert",
        "risk_officer",
        "sentiment_analyst",
    ],

    DecisionType.TECHNICAL_SIGNAL: [
        "technical_chart_expert",
        "momentum_trader",
        "risk_officer",
    ],

    DecisionType.THESIS_REVIEW: [
        # Dynamic — caller should add domain-specific specialist via context
        "bear_case_analyst",
        "risk_officer",
        "portfolio_historian",
    ],

    DecisionType.MACRO_UPDATE: [
        "macro_strategist",
        "scarcity_strategist",
        "valuation_analyst",
        "risk_officer",
        "benchmark_analyst",
    ],

    DecisionType.RISK_ALERT: [
        "risk_officer",
        "bear_case_analyst",
    ],

    DecisionType.LEARNING_REVIEW: [
        "portfolio_historian",
        "benchmark_analyst",
    ],
}

# Coordinator set per decision type
_COORDINATOR_SETS: dict[DecisionType, list[str]] = {
    DecisionType.FULL_COMMITTEE: [
        "research_coordinator",
        "portfolio_construction_coordinator",
        "risk_dissent_coordinator",
        "learning_coordinator",
    ],
    DecisionType.CRYPTO_CHANGE: [
        "research_coordinator",
        "risk_dissent_coordinator",
        "portfolio_construction_coordinator",
    ],
    DecisionType.COMMODITY_CHANGE: [
        "research_coordinator",
        "risk_dissent_coordinator",
        "portfolio_construction_coordinator",
    ],
    DecisionType.OPTIONS_REVIEW: [
        "research_coordinator",
        "risk_dissent_coordinator",
    ],
    DecisionType.TECHNICAL_SIGNAL: [
        "research_coordinator",
    ],
    DecisionType.THESIS_REVIEW: [
        "research_coordinator",
        "risk_dissent_coordinator",
    ],
    DecisionType.MACRO_UPDATE: [
        "research_coordinator",
        "risk_dissent_coordinator",
    ],
    DecisionType.RISK_ALERT: [
        "risk_dissent_coordinator",
    ],
    DecisionType.LEARNING_REVIEW: [
        "learning_coordinator",
    ],
}


@dataclass
class RoutingContext:
    """Optional context that can trigger additional specialist engagement."""
    aggregate_confidence: Optional[float] = None
    sessions_same_asset: int = 0          # triggers Psychological Agent at >=3
    asset_class: Optional[str] = None    # "crypto", "commodity", "equity", "options"
    thesis_domain_specialists: list[str] = field(default_factory=list)
    has_breakout_signal: bool = False
    has_rsi_divergence: bool = False


@dataclass
class RoutingPlan:
    decision_type: DecisionType
    specialists: list[str]
    coordinators: list[str]
    conditional_additions: list[str]
    skipped: dict[str, str]   # specialist -> reason skipped
    wave_sequence: list[list[str]]  # ordered waves for execution
    rationale: str

    @property
    def all_agents(self) -> list[str]:
        return self.specialists + self.coordinators


def route_decision(
    decision_type: DecisionType,
    context: Optional[RoutingContext] = None,
) -> RoutingPlan:
    """
    Determine which specialists and coordinators engage for a given decision.
    Returns a RoutingPlan with ordered wave_sequence.
    """
    if context is None:
        context = RoutingContext()

    base_specialists = _BASE_SPECIALIST_SETS[decision_type][:]
    coordinators = _COORDINATOR_SETS[decision_type][:]
    conditional_additions: list[str] = []
    skipped: dict[str, str] = {}

    # Add thesis-domain specialists for thesis reviews
    if decision_type == DecisionType.THESIS_REVIEW:
        for specialist in context.thesis_domain_specialists:
            if specialist not in base_specialists:
                base_specialists.append(specialist)
                conditional_additions.append(specialist)

    # Constitutional rules for conditional engagement
    if context.aggregate_confidence is not None and context.aggregate_confidence >= 75:
        if "meta_philosophy_auditor" not in base_specialists:
            base_specialists.append("meta_philosophy_auditor")
            conditional_additions.append("meta_philosophy_auditor")

    if context.sessions_same_asset >= 3:
        if "psychological_agent" not in base_specialists:
            base_specialists.append("psychological_agent")
            conditional_additions.append("psychological_agent")

    if context.has_breakout_signal and decision_type == DecisionType.CRYPTO_CHANGE:
        if "technical_chart_expert" not in base_specialists:
            base_specialists.append("technical_chart_expert")
            conditional_additions.append("technical_chart_expert")

    if context.asset_class == "commodity" and decision_type == DecisionType.THESIS_REVIEW:
        if "commodity_specialist" not in base_specialists:
            base_specialists.append("commodity_specialist")
            conditional_additions.append("commodity_specialist")

    # Record which specialists were explicitly excluded
    all_possible = set(ALL_SPECIALISTS + ["meta_philosophy_auditor", "psychological_agent"])
    engaged = set(base_specialists)
    for specialist in all_possible - engaged:
        skipped[specialist] = _skip_reason(specialist, decision_type)

    # Build wave sequence: wave 1 = specialists, wave 2 = coordinators, wave 3 = CIO
    wave1 = [s for s in base_specialists if s not in COORDINATORS]
    wave2 = coordinators
    wave3 = ["cio"]

    rationale = (
        f"Decision type '{decision_type.value}' requires {len(wave1)} specialists "
        f"and {len(wave2)} coordinators. "
        f"{len(skipped)} specialists skipped to preserve isolation and reduce noise."
    )
    if conditional_additions:
        rationale += f" Conditionally added: {', '.join(conditional_additions)}."

    return RoutingPlan(
        decision_type=decision_type,
        specialists=wave1,
        coordinators=wave2,
        conditional_additions=conditional_additions,
        skipped=skipped,
        wave_sequence=[wave1, wave2, wave3],
        rationale=rationale,
    )


def _skip_reason(specialist: str, decision_type: DecisionType) -> str:
    """Return a brief reason why a specialist was not engaged."""
    reasons: dict[str, str] = {
        "commodity_specialist": "No commodity signal or position in scope",
        "options_specialist": "No options under active consideration",
        "crypto_strategist": "No crypto allocation change in scope",
        "technology_structural_change": "No AI/semiconductor structural question present",
        "valuation_analyst": "Valuation not primary driver for this decision type",
        "momentum_trader": "Momentum not primary driver for this decision type",
        "sentiment_analyst": "Sentiment not primary driver for this decision type",
        "portfolio_historian": "Historical pattern review not required for this decision type",
        "benchmark_analyst": "Benchmark comparison not required for this decision type",
        "meta_philosophy_auditor": "Aggregate confidence below 75 — no groupthink risk",
        "psychological_agent": "Asset has appeared fewer than 3 consecutive sessions",
        "bear_case_analyst": "Covered by risk_dissent_coordinator for this decision type",
        "risk_officer": "Risk synthesis delegated to risk_dissent_coordinator",
        "scarcity_strategist": "No scarcity dimension in this decision",
        "macro_strategist": "Macro not primary driver for this technical/options decision",
    }
    return reasons.get(specialist, f"Not in base set for {decision_type.value}")


def describe_routing_plan(plan: RoutingPlan) -> str:
    """Human-readable summary of a routing plan for logging/reporting."""
    lines = [
        f"Decision Type: {plan.decision_type.value}",
        f"Rationale: {plan.rationale}",
        "",
        f"Wave 1 — Specialists ({len(plan.specialists)}):",
        *[f"  • {s}" for s in plan.specialists],
        "",
        f"Wave 2 — Coordinators ({len(plan.coordinators)}):",
        *[f"  • {c}" for c in plan.coordinators],
        "",
        "Wave 3 — Decision:",
        "  • cio",
        "",
        f"Skipped ({len(plan.skipped)}):",
        *[f"  ✗ {s}: {r}" for s, r in plan.skipped.items()],
    ]
    if plan.conditional_additions:
        lines += ["", f"Conditionally added: {', '.join(plan.conditional_additions)}"]
    return "\n".join(lines)
