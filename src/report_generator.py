"""
Report Generator — Phase 2.
Produces daily, weekly, and monthly reports populated with real data.
Advisory only — no live trading.
"""

from __future__ import annotations
import sys
import json
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Optional
import calendar

ROOT_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT_DIR / "src"))

REPORTS_DIR = ROOT_DIR / "reports"
TEMPLATES_DIR = REPORTS_DIR / "templates"
ADVISORY_DISCLAIMER = (
    "All outputs are advisory model recommendations requiring human review. "
    "Not financial advice. Past simulated performance does not predict future results."
)

US_HOLIDAYS_2026 = {
    "2026-01-01", "2026-01-19", "2026-02-16", "2026-05-25",
    "2026-07-03", "2026-09-07", "2026-11-26", "2026-11-27", "2026-12-25",
}


def _is_market_day(d: date) -> bool:
    if d.weekday() >= 5:
        return False
    return str(d) not in US_HOLIDAYS_2026


def _market_session(d: date) -> str:
    if d.weekday() >= 5:
        return "Weekend — Equity Markets Closed | Crypto & Prediction Markets Active"
    if str(d) in US_HOLIDAYS_2026:
        return "US Market Holiday — Equity Markets Closed | Crypto Active"
    return "Regular Trading Day"


def _load_portfolio() -> dict:
    path = ROOT_DIR / "portfolio" / "current_portfolio.yaml"
    import yaml
    with open(path) as f:
        return yaml.safe_load(f)


def _load_thesis_log() -> dict:
    path = ROOT_DIR / "portfolio" / "thesis_log.yaml"
    import yaml
    with open(path) as f:
        return yaml.safe_load(f)


def _load_nav_series() -> dict:
    nav_file = ROOT_DIR / "data" / "processed" / "nav_history.json"
    if nav_file.exists():
        with open(nav_file) as f:
            return json.load(f)
    return {"snapshots": {}}


def _format_pct(v: float, plus: bool = True) -> str:
    sign = "+" if v >= 0 and plus else ""
    return f"{sign}{v:.2f}%"


def _format_dollar(v: float) -> str:
    return f"${v:,.0f}"


def generate_daily_report(
    report_date: Optional[date] = None,
    simulation_results: Optional[dict] = None,
    thesis_report: Optional[dict] = None,
    signal_table: Optional[list] = None,
) -> str:
    """Generate a fully populated daily morning report."""
    d = report_date or date.today()
    session = _market_session(d)
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # Load data
    portfolio = _load_portfolio()
    thesis_log = _load_thesis_log()
    nav_data = _load_nav_series()
    snapshots = nav_data.get("snapshots", {})

    # Current NAV
    latest_nav = 100_000.0
    if snapshots:
        latest_snap = max(snapshots.keys())
        latest_nav = snapshots[latest_snap]["nav"]

    total_return_pct = (latest_nav - 100_000) / 100_000 * 100

    # Portfolio summary from YAML
    summary = portfolio.get("summary", {})
    confidence = summary.get("portfolio_confidence_score", 55)
    regime = summary.get("regime", "[Live data required — fill macro_snapshot.yaml]")

    # Bucket allocations
    core_pct = portfolio.get("core_structural", {}).get("current_pct", 60.0)
    tactical_pct = portfolio.get("tactical_strategic", {}).get("current_pct", 10.0)
    options_pct = portfolio.get("options_convexity", {}).get("current_pct", 0.0)
    experimental_pct = portfolio.get("experimental", {}).get("current_pct", 0.0)
    defensive_pct = portfolio.get("defensive_reserve", {}).get("current_pct", 0.0)

    # Simulation benchmark comparison
    sim_table = ""
    if simulation_results:
        rows = []
        benchmarks = ["benchmark_SPY", "benchmark_QQQ", "benchmark_BTC", "benchmark_STRC"]
        for name in ["main_cio"] + benchmarks:
            r = simulation_results.get(name, {})
            tr = r.get("total_return_pct", 0)
            color = "+" if tr >= 0 else ""
            rows.append(f"| {name:<30} | {color}{tr:.2f}% |")
        sim_table = "\n".join(rows)

    # Thesis summary
    active_theses = thesis_log.get("active_theses", [])
    thesis_rows = []
    for t in active_theses:
        state = t.get("lifecycle_state", "Unknown")
        conf = t.get("confidence_score", "N/A")
        thesis_rows.append(f"| {t.get('name',''):<35} | {state:<18} | {conf}/100 | {t.get('time_horizon','')} |")
    thesis_table = "\n".join(thesis_rows) if thesis_rows else "| No active theses | — | — | — |"

    # Signal/action table
    sa_rows = ""
    if signal_table:
        for row in signal_table[:8]:
            sa_rows += f"| {row.get('asset',''):<8} | {row.get('signal',''):<30} | {row.get('action',''):<25} | {row.get('no_action_reason','')[:40]} |\n"
    if not sa_rows:
        sa_rows = "| — | No signals logged today | — | — |\n"

    # Thesis review alerts
    overdue_theses = [t for t in active_theses if t.get("next_review_date", "9999-99-99") < str(d)]
    alerts = ""
    if overdue_theses:
        alerts = "\n".join([f"- ⚠️  **{t['name']}** — review overdue (was due {t['next_review_date']})" for t in overdue_theses])
    else:
        alerts = "- No overdue thesis reviews."

    report = f"""# Daily Morning Report — {d}
> **ADVISORY DISCLAIMER**: {ADVISORY_DISCLAIMER}

**Market Session**: {session}
**Report Generated**: {timestamp}
**Portfolio Confidence Score**: {confidence} / 100

---

# ═══ FRONT PAGE ═══════════════════════════════════════

## 1. Regime Summary

**Current Macro Regime**: {regime}

*Populate `data/manual_inputs/macro_snapshot.yaml` with today's readings for automated regime classification in Phase 3.*
*Key signals to assess: M2 YoY, Fed stance, real rates, yield curve shape, ISM, VIX, credit spreads.*

---

## 2. Portfolio Stance

| Bucket | Target | Current |
|--------|--------|---------|
| Core / Structural | 50–75% | {core_pct:.1f}% |
| Tactical / Strategic | 10–30% | {tactical_pct:.1f}% |
| Options / Convexity | 10–20% | {options_pct:.1f}% |
| Experimental | 0–20% | {experimental_pct:.1f}% |
| Defensive Reserve | 0–40% | {defensive_pct:.1f}% |

**Current NAV**: {_format_dollar(latest_nav)} | **Total Return**: {_format_pct(total_return_pct)}
**Starting Capital**: $100,000 | **Inception**: 2026-05-13

---

## 3. Recommended Changes Today

*No automated recommendations in Phase 2 — human review required.*
*Complete `data/manual_inputs/agent_inputs.yaml` with today's qualitative assessment.*
*Reference agents in `/agents/` for each specialist's analytical framework.*

---

## 4. Active Theses — Lifecycle Status

| Thesis | State | Confidence | Horizon |
|--------|-------|------------|---------|
{thesis_table}

**Thesis Alerts**:
{alerts}

---

## 5. Signal vs Action Log (Recent)

| Asset | Signal | Action | No-Action Reason |
|-------|--------|--------|-----------------|
{sa_rows}

---

## 6. Options Book

**Total Options Exposure**: {_format_dollar(float(summary.get('options_premium_at_risk', 0)))} ({options_pct:.1f}%)
**Net Theta Drag/Day**: $0 (no open options)
*See `portfolio/options_positions.yaml` for position details.*

---

## 7. Portfolio Confidence Score

**Score**: {confidence} / 100
*Phase 2 confidence score is manually set in `portfolio/current_portfolio.yaml`.*
*Phase 3 will auto-compute from live data across all confidence factors.*

**Low Confidence Protocol** (< 40): Diagnose cause → move toward STRC / core holdings.

---

## 8. Human Challenge Questions

1. **Is the current allocation consistent with the macro regime?** Assess using `agents/macro_strategist.md` framework.
2. **Are any theses overdue for review?** Check the alerts above and update `portfolio/thesis_log.yaml`.
3. **Is the STRC/cash position earning yield?** Confirm STRC is deployed in a yield-bearing instrument, not idle.
4. **Does the Meta-Philosophy Auditor have any open challenges?** Review `agents/meta_philosophy_auditor.md` questions.

---

# ═══ APPENDIX ══════════════════════════════════════════

## A1. Benchmark Comparison (Simulated)
"""
    if simulation_results:
        report += "\n| Portfolio | Total Return | Ann. Return | Max DD | Sharpe |\n"
        report += "|-----------|-------------|-------------|--------|--------|\n"
        order = ["main_cio", "benchmark_SPY", "benchmark_QQQ", "benchmark_BTC", "benchmark_60_40", "benchmark_STRC"]
        for name in order:
            r = simulation_results.get(name, {})
            tr = r.get("total_return_pct", 0)
            ann = r.get("annualized_return_pct", 0)
            dd = r.get("max_drawdown_pct", 0)
            sh = r.get("sharpe_ratio", 0)
            report += f"| {name:<30} | {tr:+.2f}% | {ann:+.2f}% | {dd:.2f}% | {sh:.3f} |\n"
    else:
        report += "\n*Run `python simulations/simulate_portfolios.py` to generate comparison data.*\n"

    report += f"""
## A2. Alternative Portfolio Comparison (Simulated)
"""
    if simulation_results:
        report += "\n| Portfolio | Total Return | Max DD | Sharpe |\n"
        report += "|-----------|-------------|--------|--------|\n"
        alts = ["aggressive_scarcity", "defensive_macro", "momentum_heavy", "technical_confirmation_only",
                "contrarian_sentiment", "crypto_heavy", "commodities_scarcity", "ai_structural_change", "strc_defensive"]
        for name in alts:
            r = simulation_results.get(name, {})
            tr = r.get("total_return_pct", 0)
            dd = r.get("max_drawdown_pct", 0)
            sh = r.get("sharpe_ratio", 0)
            report += f"| {name:<35} | {tr:+.2f}% | {dd:.2f}% | {sh:.3f} |\n"
    else:
        report += "\n*Simulation data not available — run simulate_portfolios.py.*\n"

    report += f"""
## A3. Manual Data Entry Status

Fill these files to improve report quality:
- `data/manual_inputs/macro_snapshot.yaml` — macro readings
- `data/manual_inputs/agent_inputs.yaml` — qualitative assessments
- `portfolio/current_portfolio.yaml` — actual position sizes

*Phase 3 will automate all data collection from free public sources.*

---
*Advisory only. Not financial advice.*
"""

    # Save report
    output_dir = REPORTS_DIR / "daily"
    output_dir.mkdir(parents=True, exist_ok=True)
    filename = output_dir / f"daily_{d.isoformat()}.md"
    with open(filename, "w") as f:
        f.write(report)

    return str(filename)


def generate_weekly_report(
    week_start: Optional[date] = None,
    simulation_results: Optional[dict] = None,
) -> str:
    """Generate weekly report with performance data."""
    d = week_start or (date.today() - timedelta(days=date.today().weekday()))
    template_path = TEMPLATES_DIR / "weekly.md"
    with open(template_path) as f:
        template = f.read()

    report = template.replace("{{WEEK_START_DATE}}", str(d))
    report = report.replace("{{REPORT_DATE}}", str(date.today()))
    report = report.replace("{{YEAR}}", str(d.year))
    report = report.replace("{{WEEK_NUMBER}}", str(d.isocalendar()[1]))
    report = report.replace("{{CONFIDENCE_SCORE}}", "55")

    output_dir = REPORTS_DIR / "weekly"
    output_dir.mkdir(parents=True, exist_ok=True)
    filename = output_dir / f"weekly_{d.isoformat()}.md"
    with open(filename, "w") as f:
        f.write(report)
    return str(filename)


def generate_monthly_report(month: int, year: int) -> str:
    """Generate monthly benchmark review."""
    month_name = calendar.month_name[month]
    template_path = TEMPLATES_DIR / "monthly.md"
    with open(template_path) as f:
        template = f.read()

    report = template.replace("{{MONTH}}", month_name)
    report = report.replace("{{YEAR}}", str(year))
    report = report.replace("{{REPORT_DATE}}", str(date.today()))

    output_dir = REPORTS_DIR / "monthly"
    output_dir.mkdir(parents=True, exist_ok=True)
    filename = output_dir / f"monthly_{year}_{month:02d}.md"
    with open(filename, "w") as f:
        f.write(report)
    return str(filename)
