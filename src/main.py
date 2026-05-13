"""
Hedge Fund OS — Main CLI Entry Point (Phase 3)
Advisory only — no live trading.

Usage:
  python src/main.py                     # Full morning run
  python src/main.py --sim-only          # Simulation + charts only
  python src/main.py --report            # Generate daily report only
  python src/main.py --thesis            # Thesis lifecycle monitor only
  python src/main.py --charts            # Regenerate charts only
  python src/main.py --scorecards        # Agent scorecards only
  python src/main.py --committee         # Run mock committee session (no API key needed)
  python src/main.py --committee --live  # Run live committee session (requires ANTHROPIC_API_KEY)
  python src/main.py --committee --type crypto_change --question "Should we increase MSTR?"
  python src/main.py --sessions          # List recent committee sessions
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
    t.append(" v3.0  |  Phase 3  |  Advisory Only", style="dim")
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


def run_committee(console, decision_type_str: str, decision_question: str, live: bool) -> dict:
    """Run an AI committee session (mock or live)."""
    from rich.panel import Panel
    from committee_session import run_committee_session, PortfolioSnapshot
    from routing_engine import DecisionType, describe_routing_plan, route_decision

    try:
        dt = DecisionType(decision_type_str)
    except ValueError:
        valid = [d.value for d in DecisionType]
        console.print(f"[red]Unknown decision type '{decision_type_str}'. Valid: {valid}[/red]")
        return {}

    mode_label = "[bold red]LIVE (Claude API)[/bold red]" if live else "[bold yellow]MOCK (no API call)[/bold yellow]"
    console.print(f"\n[bold cyan]── Committee Session ─────────────────────────────────────[/bold cyan]")
    console.print(f"Decision Type: [bold]{dt.value}[/bold]")
    console.print(f"Question:      {decision_question}")
    console.print(f"Mode:          {mode_label}")

    # Show routing plan first
    plan = route_decision(dt)
    console.print(f"\n[dim]Routing: {plan.rationale}[/dim]")
    console.print(f"[dim]Specialists: {', '.join(plan.specialists)}[/dim]")
    console.print(f"[dim]Skipping {len(plan.skipped)} agents to preserve isolation[/dim]")

    portfolio = PortfolioSnapshot(
        total_value=100_000.0,
        cash_pct=30.0,
        positions=[
            {"ticker": "SPY", "pct": 20.0, "bucket": "core_structural", "thesis_state": "Confirming"},
            {"ticker": "QQQ", "pct": 15.0, "bucket": "core_structural", "thesis_state": "Confirming"},
            {"ticker": "MSTR", "pct": 10.0, "bucket": "core_structural", "thesis_state": "Confirming"},
            {"ticker": "GLD", "pct": 10.0, "bucket": "core_structural", "thesis_state": "High Conviction"},
            {"ticker": "URNM", "pct": 5.0, "bucket": "core_structural", "thesis_state": "Confirming"},
        ],
        active_theses=[
            {"id": "THESIS-001", "asset": "SPY", "state": "Confirming", "confidence": 60},
            {"id": "THESIS-002", "asset": "BTC", "state": "High Conviction", "confidence": 72},
            {"id": "THESIS-003", "asset": "GLD", "state": "High Conviction", "confidence": 68},
            {"id": "THESIS-004", "asset": "URNM", "state": "Confirming", "confidence": 58},
        ],
        latest_nav_return_pct=5.2,
        options_premium_at_risk_pct=0.0,
    )

    from rich.progress import Progress, SpinnerColumn, TextColumn
    with Progress(SpinnerColumn(), TextColumn("[progress.description]{task.description}"), transient=True) as p:
        task = p.add_task("Running committee session...", total=None)
        session = run_committee_session(
            decision_type=dt,
            decision_question=decision_question,
            portfolio=portfolio,
            live=live,
            save_session=True,
        )

    cio = session.cio_decision or {}
    console.print(f"\n[bold]Session ID:[/bold] {session.session_id}")
    console.print(f"[bold]Specialists Engaged:[/bold] {len(session.specialist_memos)}")
    console.print(f"\n[bold cyan]── CIO Decision ──────────────────────────────────────────[/bold cyan]")
    stance_color = "green" if cio.get("final_stance") in ("Bullish", "Hold") else "red" if cio.get("final_stance") == "Bearish" else "yellow"
    console.print(f"Stance:     [{stance_color}]{cio.get('final_stance', '?')}[/{stance_color}]")
    console.print(f"Confidence: {cio.get('final_confidence', '?')}/100")
    console.print(f"Allocation Change: {'Yes' if cio.get('allocation_change') else 'No'}")

    if cio.get("action_orders"):
        console.print("\n[bold]Action Orders:[/bold]")
        for order in cio.get("action_orders", []):
            console.print(f"  • {order}")

    if cio.get("challenge_questions"):
        console.print("\n[bold]CIO Challenge Questions:[/bold]")
        for q in cio.get("challenge_questions", []):
            console.print(f"  [italic]• {q}[/italic]")

    console.print(f"\n[dim]Session saved → data/processed/committee_sessions/{session.session_id}.json[/dim]")
    return session.to_dict()


def run_sessions_list(console, limit: int = 10) -> None:
    """List recent committee sessions."""
    from rich.table import Table
    from committee_session import list_sessions

    console.print("\n[bold cyan]── Recent Committee Sessions ─────────────────────────────[/bold cyan]")
    sessions = list_sessions(limit=limit)

    if not sessions:
        console.print("[dim]No committee sessions found. Run with --committee to create one.[/dim]")
        return

    table = Table(show_lines=False)
    table.add_column("Session ID", min_width=26)
    table.add_column("Date", justify="center")
    table.add_column("Type")
    table.add_column("Specialists", justify="right")
    table.add_column("CIO Stance")
    table.add_column("Confidence", justify="right")

    for s in sessions:
        color = "green" if s["cio_stance"] in ("Bullish", "Hold") else "red" if s["cio_stance"] == "Bearish" else "yellow"
        table.add_row(
            s["session_id"],
            s["date"],
            s["decision_type"],
            str(len(s.get("specialists_engaged", []))),
            f"[{color}]{s['cio_stance']}[/{color}]",
            str(s["cio_confidence"]),
        )
    console.print(table)


def print_quick_ref(console) -> None:
    """Print quick reference for next steps."""
    from rich.panel import Panel
    content = (
        "[bold]Next Steps:[/bold]\n"
        "1. Fill [cyan]data/manual_inputs/macro_snapshot.yaml[/cyan] with today's macro readings\n"
        "2. Run [cyan]python src/main.py --committee[/cyan] for a mock committee session\n"
        "3. Run [cyan]python src/main.py --committee --live[/cyan] with ANTHROPIC_API_KEY for live AI\n"
        "4. Use [cyan]src/vote_db.py[/cyan] to record agent votes on recommendations\n"
        "5. Open [cyan]reports/charts/[/cyan] in browser for interactive charts\n"
        "\n[bold]Phase 3 Architecture:[/bold]\n"
        "  Constitution → Coordinators → Specialists → CIO\n"
        "  Routing engine prevents unnecessary agent engagement\n"
        "  Memo isolation preserves diversity of specialist thought\n"
        "\n[bold]Phase 4:[/bold] Options chains, sentiment feeds, on-chain data"
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
    # Phase 3: committee session flags
    parser.add_argument("--committee", action="store_true", help="Run an AI committee session")
    parser.add_argument("--live", action="store_true", help="Use live Claude API (requires ANTHROPIC_API_KEY)")
    parser.add_argument("--type", dest="decision_type", default="full_committee",
                        help="Decision type for committee session (default: full_committee)")
    parser.add_argument("--question", dest="decision_question",
                        default="Evaluate current portfolio positioning and recommend any adjustments.",
                        help="Decision question for committee session")
    parser.add_argument("--sessions", action="store_true", help="List recent committee sessions")
    args = parser.parse_args()

    console = _console()
    _print_header(console)

    sim_results = {}

    # ── Committee session ────────────────────────────────
    if args.committee:
        run_committee(console, args.decision_type, args.decision_question, live=args.live)
        return

    # ── Sessions list ─────────────────────────────────────
    if args.sessions:
        run_sessions_list(console)
        return

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
