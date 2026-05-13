"""
Hedge Fund OS — Main CLI Entry Point (Phase 2)
Advisory only — no live trading.

Usage:
  python src/main.py              # Full morning run
  python src/main.py --sim-only   # Simulation + charts only
  python src/main.py --report     # Generate daily report only
  python src/main.py --thesis     # Thesis lifecycle monitor only
  python src/main.py --charts     # Regenerate charts only
  python src/main.py --scorecards # Agent scorecards only
"""

from __future__ import annotations
import sys
import argparse
from datetime import date
from pathlib import Path

ROOT_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT_DIR / "src"))
sys.path.insert(0, str(ROOT_DIR / "simulations"))

DISCLAIMER = (
    "ADVISORY ONLY — No live trading. All outputs require human review. Not financial advice."
)


def _console():
    from rich.console import Console
    return Console()


def _print_header(console):
    from rich.panel import Panel
    from rich.text import Text
    t = Text()
    t.append("Hedge Fund OS", style="bold magenta")
    t.append(" v2.0  |  Phase 2  |  Advisory Only", style="dim")
    console.print(Panel(t, border_style="magenta"))
    console.print(f"[dim]{DISCLAIMER}[/dim]\n")


def run_simulation(console) -> dict:
    """Run all portfolio simulations and return results."""
    from rich.progress import Progress, SpinnerColumn, TextColumn
    from simulate_portfolios import simulate_all, print_summary_table

    console.print("[bold cyan]── Portfolio Simulation ──────────────────────────────────[/bold cyan]")
    with Progress(SpinnerColumn(), TextColumn("[progress.description]{task.description}"), transient=True) as p:
        p.add_task("Fetching price data and simulating portfolios...", total=None)
        results = simulate_all()

    print_summary_table(results)
    return results


def run_thesis_monitor(console) -> dict:
    """Run thesis lifecycle monitor."""
    from rich.table import Table
    from thesis_engine import load_all_theses, lifecycle_monitor_report

    console.print("\n[bold cyan]── Thesis Lifecycle Monitor ──────────────────────────────[/bold cyan]")

    theses = load_all_theses()
    report = lifecycle_monitor_report(theses)

    # Health score
    score = report["health_score"]
    color = "green" if score >= 70 else "yellow" if score >= 50 else "red"
    console.print(f"Lifecycle Health Score: [{color}]{score}/100[/{color}]")
    console.print(f"Active Theses: {report['total_theses']} | "
                  f"Action Required: [{'red' if report['action_required_count'] else 'green'}]"
                  f"{report['action_required_count']}[/{'red' if report['action_required_count'] else 'green'}] | "
                  f"Overdue Reviews: [{'yellow' if report['overdue_review_count'] else 'green'}]"
                  f"{report['overdue_review_count']}[/{'yellow' if report['overdue_review_count'] else 'green'}]")

    # Thesis table
    table = Table(show_lines=True)
    table.add_column("ID", style="dim")
    table.add_column("Thesis", min_width=30)
    table.add_column("State", min_width=18)
    table.add_column("Confidence", justify="center")
    table.add_column("Horizon")
    table.add_column("Days Open", justify="right")
    table.add_column("Review In", justify="right")

    STATE_STYLES = {
        "Emerging": "yellow",
        "Confirming": "cyan",
        "High Conviction": "green",
        "Crowded": "orange1",
        "Distribution Risk": "red",
        "Breakdown Risk": "bold red",
        "Invalidated": "dim red",
    }

    for t in report["thesis_table"]:
        style = STATE_STYLES.get(t["state"], "white")
        days_to_review = t["days_to_review"]
        review_str = f"{days_to_review}d" if days_to_review >= 0 else f"[red]{abs(days_to_review)}d overdue[/red]"
        table.add_row(
            t["id"],
            t["name"],
            f"[{style}]{t['state']}[/{style}]",
            f"{t['confidence']}/100",
            t["horizon"],
            str(t["days_open"]),
            review_str,
        )
    console.print(table)

    # Alerts
    if report["alerts"]:
        console.print("\n[bold red]⚠ Thesis Alerts:[/bold red]")
        for alert in report["alerts"]:
            a_type = alert["type"]
            if a_type == "ACTION_REQUIRED":
                console.print(
                    f"  [red]ACTION REQUIRED[/red] [{alert['urgency']}] "
                    f"[bold]{alert['thesis_name']}[/bold] — {alert['state']}\n"
                    f"    Sizing: {alert['sizing_guidance']}\n"
                    f"    Positions: {', '.join(alert['positions'])}"
                )
            elif a_type == "REVIEW_OVERDUE":
                console.print(
                    f"  [yellow]REVIEW OVERDUE[/yellow] [bold]{alert['thesis_name']}[/bold] "
                    f"— {alert['days_overdue']} days past review date"
                )
    else:
        console.print("\n[green]✓ No thesis alerts.[/green]")

    return report


def run_nav_snapshot(console) -> float:
    """Record today's NAV from portfolio YAML."""
    from nav_tracker import compute_nav_from_portfolio, record_snapshot, get_latest_nav, get_total_return
    from config import load_portfolio

    portfolio = load_portfolio()
    nav = compute_nav_from_portfolio(portfolio)
    if nav > 0:
        record_snapshot(nav=nav, snapshot_date=date.today(), note="Daily run")

    latest = get_latest_nav()
    ret = get_total_return()
    color = "green" if ret["pct_return"] >= 0 else "red"
    console.print(f"\n[bold cyan]── Portfolio NAV ─────────────────────────────────────────[/bold cyan]")
    console.print(f"Current NAV:    [bold]${latest:,.2f}[/bold]")
    console.print(f"Starting Cap:   $100,000.00")
    console.print(f"Total Return:   [{color}]{ret['pct_return']:+.2f}%  (${ret['dollar_return']:+,.2f})[/{color}]")
    console.print(f"Inception:      {ret['inception_date']}")
    return latest


def run_scorecards(console) -> list:
    """Display agent scorecards."""
    from rich.table import Table
    from vote_db import get_all_scorecards

    console.print("\n[bold cyan]── Agent Scorecards ──────────────────────────────────────[/bold cyan]")
    scorecards = get_all_scorecards()

    table = Table(show_lines=False)
    table.add_column("Agent", min_width=30)
    table.add_column("Votes", justify="right")
    table.add_column("Hit Rate", justify="right")
    table.add_column("Avg Win %", justify="right")
    table.add_column("Avg Loss %", justify="right")
    table.add_column("Pending", justify="right")

    for s in scorecards:
        hr = s["hit_rate_pct"]
        color = "green" if hr >= 60 else "yellow" if hr >= 40 else "red"
        table.add_row(
            s["agent"].replace("_", " ").title(),
            str(s["total_votes"]),
            f"[{color}]{hr:.1f}%[/{color}]" if s["total_votes"] > 0 else "[dim]—[/dim]",
            f"{s['avg_return_when_correct']:+.2f}%" if s["total_votes"] > 0 else "[dim]—[/dim]",
            f"{s['avg_return_when_incorrect']:+.2f}%" if s["total_votes"] > 0 else "[dim]—[/dim]",
            str(s["pending_votes"]),
        )
    console.print(table)
    if all(s["total_votes"] == 0 for s in scorecards):
        console.print("[dim]No resolved recommendations yet. Use vote_db.py to record agent votes and outcomes.[/dim]")

    return scorecards


def run_charts(console, simulation_results: dict, thesis_data: list, scorecards: list) -> dict:
    """Generate all Plotly charts."""
    from visualization_engine import generate_all_charts

    console.print("\n[bold cyan]── Generating Charts ─────────────────────────────────────[/bold cyan]")

    allocations = {"SPY": 20, "QQQ": 15, "MSTR": 10, "GLD": 10, "URNM": 5, "STRC": 40}
    charts = generate_all_charts(
        simulation_results=simulation_results,
        thesis_data=thesis_data,
        scorecards=scorecards,
        allocations=allocations,
    )
    for name, path in charts.items():
        console.print(f"  [green]✓[/green] {name:<35} → {path}")

    return charts


def run_report(console, simulation_results: dict) -> str:
    """Generate today's daily report."""
    from report_generator import generate_daily_report
    from signal_action_engine import get_signal_action_table

    console.print("\n[bold cyan]── Generating Daily Report ───────────────────────────────[/bold cyan]")
    signal_table = get_signal_action_table(limit=10)
    path = generate_daily_report(
        report_date=date.today(),
        simulation_results=simulation_results,
        signal_table=signal_table,
    )
    console.print(f"  [green]✓[/green] Daily report → {path}")
    return path


def print_quick_ref(console) -> None:
    """Print quick reference for next steps."""
    from rich.panel import Panel
    content = (
        "[bold]Next Steps:[/bold]\n"
        "1. Fill [cyan]data/manual_inputs/macro_snapshot.yaml[/cyan] with today's macro readings\n"
        "2. Fill [cyan]data/manual_inputs/agent_inputs.yaml[/cyan] with qualitative assessment\n"
        "3. Update [cyan]portfolio/current_portfolio.yaml[/cyan] with actual position sizes\n"
        "4. Use [cyan]src/vote_db.py[/cyan] to record agent votes on recommendations\n"
        "5. Open [cyan]reports/charts/[/cyan] in browser for interactive charts\n"
        "\n[bold]Phase 3:[/bold] Live data (yfinance auto-pull, FRED, CoinGecko)\n"
        "[bold]Phase 4:[/bold] Options chains, sentiment feeds, on-chain data"
    )
    console.print(Panel(content, title="Quick Reference", border_style="dim"))


def main():
    parser = argparse.ArgumentParser(description="Hedge Fund OS — Advisory Investment Committee")
    parser.add_argument("--sim-only", action="store_true", help="Simulation + charts only")
    parser.add_argument("--report", action="store_true", help="Generate daily report only")
    parser.add_argument("--thesis", action="store_true", help="Thesis lifecycle monitor only")
    parser.add_argument("--charts", action="store_true", help="Regenerate all charts")
    parser.add_argument("--scorecards", action="store_true", help="Show agent scorecards")
    parser.add_argument("--no-sim", action="store_true", help="Skip simulation (fast startup)")
    args = parser.parse_args()

    console = _console()
    _print_header(console)

    sim_results = {}

    # ── Thesis only ──────────────────────────────────────
    if args.thesis:
        run_thesis_monitor(console)
        return

    # ── Scorecards only ──────────────────────────────────
    if args.scorecards:
        run_scorecards(console)
        return

    # ── Report only ──────────────────────────────────────
    if args.report:
        run_report(console, sim_results)
        return

    # ── Full morning run ─────────────────────────────────
    nav = run_nav_snapshot(console)

    if not args.no_sim:
        try:
            sim_results = run_simulation(console)
        except Exception as e:
            console.print(f"[yellow]⚠ Simulation error: {e}[/yellow]")
            console.print("[dim]Continuing without simulation data...[/dim]")

    thesis_report = run_thesis_monitor(console)
    scorecards = run_scorecards(console)

    if args.sim_only:
        return

    thesis_data = thesis_report.get("thesis_table", [])
    charts = run_charts(console, sim_results, thesis_data, scorecards)
    report_path = run_report(console, sim_results)

    print_quick_ref(console)
    console.print(f"\n[bold green]✓ Morning run complete — {date.today()}[/bold green]")
    console.print(f"[dim]{DISCLAIMER}[/dim]\n")


if __name__ == "__main__":
    main()
