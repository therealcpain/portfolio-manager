"""
Report Generator — produces daily, weekly, and monthly reports.
Phase 1: generates template-filled markdown with placeholders.
Phase 3: fills in live data automatically.
Advisory only — no live trading.
"""

from __future__ import annotations
from datetime import date, datetime
from pathlib import Path
import os

from config import REPORTS_DIR, ADVISORY_DISCLAIMER, load_config


TEMPLATES_DIR = REPORTS_DIR / "templates"


def _is_market_day(d: date) -> bool:
    """Simple check — weekday. Does not account for US market holidays."""
    return d.weekday() < 5  # Mon–Fri


def _get_market_session(d: date) -> str:
    if d.weekday() >= 5:
        return "Weekend (Crypto/Prediction Markets Only — Equity Markets Closed)"
    return "Regular Trading Day"


def generate_daily_report(
    report_date: Optional[date] = None,
    output_dir: Optional[Path] = None,
) -> str:
    """
    Generate a daily morning report.
    Phase 1: fills template with placeholder values.
    Phase 3: populates from live data engines.
    """
    from typing import Optional

    d = report_date or date.today()
    session = _get_market_session(d)
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    template_path = TEMPLATES_DIR / "daily.md"
    with open(template_path) as f:
        template = f.read()

    # Phase 1 substitutions — all placeholders
    substitutions = {
        "{{DATE}}": str(d),
        "{{TIMESTAMP}}": timestamp,
        "{{MARKET_SESSION}}": session,
        "{{CONFIDENCE_SCORE}}": "55",
        "{{REGIME_LABEL}}": "[LIVE DATA REQUIRED]",
        "{{REGIME_SUMMARY_PARAGRAPH}}": (
            "Phase 1 — live macro data not yet integrated. "
            "Regime classification will populate automatically in Phase 3. "
            "Manually assess macro regime using indicators listed in agents/macro_strategist.md."
        ),
        # Add more substitutions as engines are built in Phase 2+
    }

    report = template
    for key, value in substitutions.items():
        report = report.replace(key, value)

    # Save report
    if output_dir is None:
        output_dir = REPORTS_DIR / "daily"
    output_dir.mkdir(parents=True, exist_ok=True)

    filename = output_dir / f"daily_{d.isoformat()}.md"
    with open(filename, "w") as f:
        f.write(report)

    return str(filename)


def generate_weekly_report(
    week_start: Optional[date] = None,
    output_dir: Optional[Path] = None,
) -> str:
    """Generate weekly report."""
    from typing import Optional

    d = week_start or date.today()
    template_path = TEMPLATES_DIR / "weekly.md"
    with open(template_path) as f:
        template = f.read()

    report = template.replace("{{WEEK_START_DATE}}", str(d))
    report = report.replace("{{REPORT_DATE}}", str(date.today()))

    if output_dir is None:
        output_dir = REPORTS_DIR / "weekly"
    output_dir.mkdir(parents=True, exist_ok=True)

    filename = output_dir / f"weekly_{d.isoformat()}.md"
    with open(filename, "w") as f:
        f.write(report)

    return str(filename)


def generate_monthly_report(
    month: int,
    year: int,
    output_dir: Optional[Path] = None,
) -> str:
    """Generate monthly benchmark review."""
    from typing import Optional
    import calendar

    month_name = calendar.month_name[month]
    template_path = TEMPLATES_DIR / "monthly.md"
    with open(template_path) as f:
        template = f.read()

    report = template.replace("{{MONTH}}", month_name)
    report = report.replace("{{YEAR}}", str(year))
    report = report.replace("{{REPORT_DATE}}", str(date.today()))

    if output_dir is None:
        output_dir = REPORTS_DIR / "monthly"
    output_dir.mkdir(parents=True, exist_ok=True)

    filename = output_dir / f"monthly_{year}_{month:02d}.md"
    with open(filename, "w") as f:
        f.write(report)

    return str(filename)


if __name__ == "__main__":
    from typing import Optional
    path = generate_daily_report()
    print(f"Daily report generated: {path}")
    print(f"\n{ADVISORY_DISCLAIMER}")
