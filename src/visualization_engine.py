"""
Visualization Engine — Phase 2.
Generates interactive Plotly charts saved as HTML.
Advisory only — no live trading.
"""

from __future__ import annotations
import sys
from pathlib import Path
from datetime import date
from typing import Optional

import pandas as pd
import numpy as np

ROOT_DIR = Path(__file__).parent.parent
CHARTS_DIR = ROOT_DIR / "reports" / "charts"
CHARTS_DIR.mkdir(parents=True, exist_ok=True)

DISCLAIMER = "ADVISORY ONLY. Simulated performance. Not financial advice."

ENIGMA_COLORS = {
    "main_cio": "#a855f7",
    "benchmark_SPY": "#3b82f6",
    "benchmark_QQQ": "#06b6d4",
    "benchmark_BTC": "#f59e0b",
    "benchmark_STRC": "#10b981",
    "benchmark_60_40": "#6b7280",
    "aggressive_scarcity": "#ef4444",
    "defensive_macro": "#84cc16",
    "momentum_heavy": "#f97316",
    "technical_confirmation_only": "#8b5cf6",
    "contrarian_sentiment": "#ec4899",
    "crypto_heavy": "#fbbf24",
    "commodities_scarcity": "#78716c",
    "ai_structural_change": "#14b8a6",
    "strc_defensive": "#94a3b8",
}


def _nav_series_from_result(result: dict) -> pd.Series:
    nav_dict = result.get("nav_series", {})
    if not nav_dict:
        return pd.Series(dtype=float)
    s = pd.Series({pd.Timestamp(k): float(v) for k, v in nav_dict.items()})
    return s.sort_index()


def plot_portfolio_vs_benchmarks(
    simulation_results: dict[str, dict],
    output_path: Optional[str] = None,
) -> str:
    """Line chart: main CIO portfolio vs primary benchmarks."""
    import plotly.graph_objects as go

    fig = go.Figure()
    targets = ["main_cio", "benchmark_SPY", "benchmark_QQQ", "benchmark_BTC", "benchmark_STRC"]

    for name in targets:
        result = simulation_results.get(name)
        if not result:
            continue
        nav = _nav_series_from_result(result)
        if nav.empty:
            continue
        display = name.replace("benchmark_", "").upper()
        fig.add_trace(go.Scatter(
            x=nav.index.tolist(),
            y=nav.values.tolist(),
            name=display if name != "main_cio" else "Main CIO Portfolio",
            line=dict(color=ENIGMA_COLORS.get(name, "#999"), width=2.5 if name == "main_cio" else 1.5),
            hovertemplate=f"<b>{display}</b><br>Date: %{{x|%Y-%m-%d}}<br>Value: $%{{y:,.0f}}<extra></extra>",
        ))

    fig.update_layout(
        title=dict(text="Portfolio vs Benchmarks — $100,000 Starting Capital", font=dict(size=18)),
        xaxis_title="Date",
        yaxis_title="Portfolio Value ($)",
        yaxis_tickformat="$,.0f",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        hovermode="x unified",
        template="plotly_dark",
        annotations=[dict(
            text=DISCLAIMER, showarrow=False,
            xref="paper", yref="paper", x=0, y=-0.12,
            font=dict(size=10, color="#666"), align="left",
        )],
        height=500,
    )

    path = output_path or str(CHARTS_DIR / "portfolio_vs_benchmarks.html")
    fig.write_html(path)
    return path


def plot_all_portfolios(
    simulation_results: dict[str, dict],
    output_path: Optional[str] = None,
) -> str:
    """Line chart: all 10 alternative portfolios + main CIO."""
    import plotly.graph_objects as go

    fig = go.Figure()
    for name, result in simulation_results.items():
        if name.startswith("benchmark_"):
            continue
        nav = _nav_series_from_result(result)
        if nav.empty:
            continue
        is_main = name == "main_cio"
        fig.add_trace(go.Scatter(
            x=nav.index.tolist(), y=nav.values.tolist(),
            name=name.replace("_", " ").title(),
            line=dict(color=ENIGMA_COLORS.get(name, "#999"), width=3 if is_main else 1),
            opacity=1.0 if is_main else 0.7,
            hovertemplate=f"<b>{name}</b><br>$%{{y:,.0f}}<extra></extra>",
        ))

    fig.update_layout(
        title="All Alternative Portfolios vs Main CIO",
        xaxis_title="Date", yaxis_title="Value ($)", yaxis_tickformat="$,.0f",
        template="plotly_dark", hovermode="x unified", height=550,
        annotations=[dict(text=DISCLAIMER, showarrow=False, xref="paper", yref="paper",
                          x=0, y=-0.12, font=dict(size=10, color="#666"))],
    )
    path = output_path or str(CHARTS_DIR / "all_portfolios.html")
    fig.write_html(path)
    return path


def plot_allocation_pie(
    allocations: dict[str, float],
    output_path: Optional[str] = None,
) -> str:
    """Donut chart: current portfolio allocation by position."""
    import plotly.graph_objects as go

    labels = list(allocations.keys())
    values = list(allocations.values())

    fig = go.Figure(go.Pie(
        labels=labels, values=values, hole=0.45,
        marker=dict(colors=["#a855f7", "#8b5cf6", "#6d28d9", "#c084fc",
                             "#7c3aed", "#e879f9", "#4c1d95", "#ddd6fe"]),
        textinfo="label+percent",
        hovertemplate="<b>%{label}</b><br>%{value:.1f}%<extra></extra>",
    ))
    fig.update_layout(
        title="Portfolio Allocation",
        template="plotly_dark",
        annotations=[dict(text="Portfolio", x=0.5, y=0.5, font_size=14, showarrow=False)],
        height=450,
    )
    path = output_path or str(CHARTS_DIR / "allocation_pie.html")
    fig.write_html(path)
    return path


def plot_drawdown_comparison(
    simulation_results: dict[str, dict],
    output_path: Optional[str] = None,
) -> str:
    """Underwater equity curves for all portfolios."""
    import plotly.graph_objects as go

    fig = go.Figure()
    targets = ["main_cio", "benchmark_SPY", "benchmark_BTC"]
    for name in targets:
        result = simulation_results.get(name)
        if not result:
            continue
        nav = _nav_series_from_result(result)
        if nav.empty or len(nav) < 2:
            continue
        peak = nav.cummax()
        drawdown = ((nav - peak) / peak * 100)
        label = name.replace("benchmark_", "").upper() if name != "main_cio" else "Main CIO"
        fig.add_trace(go.Scatter(
            x=drawdown.index.tolist(), y=drawdown.values.tolist(),
            name=label, fill="tozeroy",
            line=dict(color=ENIGMA_COLORS.get(name, "#999")),
            hovertemplate=f"<b>{label}</b><br>Drawdown: %{{y:.2f}}%<extra></extra>",
        ))

    fig.update_layout(
        title="Drawdown Comparison",
        xaxis_title="Date", yaxis_title="Drawdown (%)",
        template="plotly_dark", hovermode="x unified", height=400,
        annotations=[dict(text=DISCLAIMER, showarrow=False, xref="paper", yref="paper",
                          x=0, y=-0.15, font=dict(size=10, color="#666"))],
    )
    path = output_path or str(CHARTS_DIR / "drawdown_comparison.html")
    fig.write_html(path)
    return path


def plot_thesis_lifecycle(
    thesis_data: list[dict],
    output_path: Optional[str] = None,
) -> str:
    """Color-coded table of all active theses with lifecycle state."""
    import plotly.graph_objects as go

    STATE_COLORS = {
        "Emerging": "#fbbf24",
        "Confirming": "#60a5fa",
        "High Conviction": "#34d399",
        "Crowded": "#fb923c",
        "Distribution Risk": "#f97316",
        "Breakdown Risk": "#ef4444",
        "Invalidated": "#6b7280",
    }

    if not thesis_data:
        thesis_data = [{"name": "No active theses", "lifecycle_state": "—", "confidence": "—", "horizon": "—", "days_open": 0}]

    names = [t["name"] for t in thesis_data]
    states = [t["lifecycle_state"] for t in thesis_data]
    confs = [str(t["confidence"]) for t in thesis_data]
    horizons = [t["horizon"] for t in thesis_data]
    days = [str(t["days_open"]) for t in thesis_data]
    colors = [[STATE_COLORS.get(s, "#999") for s in states]]

    fig = go.Figure(go.Table(
        header=dict(
            values=["<b>Thesis</b>", "<b>State</b>", "<b>Confidence</b>", "<b>Horizon</b>", "<b>Days Open</b>"],
            fill_color="#1a0533", font=dict(color="white", size=13), align="left",
        ),
        cells=dict(
            values=[names, states, confs, horizons, days],
            fill_color=["#0f0018"] * 4 + colors,
            font=dict(color="white", size=12), align="left",
        ),
    ))
    fig.update_layout(title="Thesis Lifecycle Dashboard", template="plotly_dark", height=350)
    path = output_path or str(CHARTS_DIR / "thesis_lifecycle.html")
    fig.write_html(path)
    return path


def plot_performance_bar(
    simulation_results: dict[str, dict],
    output_path: Optional[str] = None,
) -> str:
    """Bar chart: total return comparison across all portfolios."""
    import plotly.graph_objects as go

    names, returns, colors = [], [], []
    order = (
        list(k for k in simulation_results if not k.startswith("benchmark_")) +
        list(k for k in simulation_results if k.startswith("benchmark_"))
    )
    for name in order:
        r = simulation_results[name].get("total_return_pct", 0)
        names.append(name.replace("benchmark_", "BM: ").replace("_", " ").title())
        returns.append(r)
        colors.append("#34d399" if r >= 0 else "#ef4444")

    fig = go.Figure(go.Bar(
        x=names, y=returns,
        marker_color=colors,
        hovertemplate="<b>%{x}</b><br>Return: %{y:.2f}%<extra></extra>",
    ))
    fig.update_layout(
        title="Total Return — All Portfolios vs Benchmarks",
        xaxis_title="Portfolio", yaxis_title="Total Return (%)",
        xaxis_tickangle=-35, template="plotly_dark", height=500,
        shapes=[dict(type="line", x0=-0.5, x1=len(names)-0.5, y0=0, y1=0,
                     line=dict(color="white", width=1, dash="dot"))],
        annotations=[dict(text=DISCLAIMER, showarrow=False, xref="paper", yref="paper",
                          x=0, y=-0.25, font=dict(size=10, color="#666"))],
    )
    path = output_path or str(CHARTS_DIR / "performance_bar.html")
    fig.write_html(path)
    return path


def plot_agent_scorecards(
    scorecards: list[dict],
    output_path: Optional[str] = None,
) -> str:
    """Horizontal bar: agent hit rates."""
    import plotly.graph_objects as go

    agents = [s["agent"].replace("_", " ").title() for s in scorecards]
    hit_rates = [s["hit_rate_pct"] for s in scorecards]
    totals = [s["total_votes"] for s in scorecards]

    fig = go.Figure(go.Bar(
        x=hit_rates, y=agents, orientation="h",
        marker_color=["#34d399" if h >= 50 else "#ef4444" for h in hit_rates],
        hovertemplate="<b>%{y}</b><br>Hit Rate: %{x:.1f}%<br>Votes: %{customdata}<extra></extra>",
        customdata=totals,
    ))
    fig.update_layout(
        title="Agent Hit Rates (Resolved Recommendations)",
        xaxis_title="Hit Rate (%)", xaxis_range=[0, 100],
        template="plotly_dark", height=550,
        annotations=[dict(text="No resolved recommendations yet — tracking starts once outcomes are logged.",
                          showarrow=False, xref="paper", yref="paper",
                          x=0.5, y=0.5, font=dict(size=12, color="#888"))]
        if all(h == 0 for h in hit_rates) else [],
    )
    path = output_path or str(CHARTS_DIR / "agent_scorecards.html")
    fig.write_html(path)
    return path


def generate_all_charts(
    simulation_results: Optional[dict] = None,
    thesis_data: Optional[list] = None,
    scorecards: Optional[list] = None,
    allocations: Optional[dict] = None,
) -> dict[str, str]:
    """Generate all Phase 2 charts. Returns dict of chart_name → file_path."""
    generated = {}

    if simulation_results:
        generated["portfolio_vs_benchmarks"] = plot_portfolio_vs_benchmarks(simulation_results)
        generated["all_portfolios"] = plot_all_portfolios(simulation_results)
        generated["drawdown_comparison"] = plot_drawdown_comparison(simulation_results)
        generated["performance_bar"] = plot_performance_bar(simulation_results)

    if thesis_data is not None:
        generated["thesis_lifecycle"] = plot_thesis_lifecycle(thesis_data)

    if scorecards is not None:
        generated["agent_scorecards"] = plot_agent_scorecards(scorecards)

    if allocations:
        generated["allocation_pie"] = plot_allocation_pie(allocations)

    return generated
