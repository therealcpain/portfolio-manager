"""
Hedge Fund OS — Main Entry Point
Advisory only — no live trading.
"""

from datetime import date

from config import load_config, ADVISORY_DISCLAIMER
from portfolio_engine import load_portfolio_state, get_portfolio_summary
from thesis_engine import load_all_theses, get_theses_requiring_action
from report_generator import generate_daily_report


def main():
    config = load_config()
    print(f"\n{'=' * 60}")
    print(f"  {config['system']['name']} v{config['system']['version']}")
    print(f"  Phase {config['system']['phase']}")
    print(f"{'=' * 60}")
    print(f"\n⚠️  {ADVISORY_DISCLAIMER}\n")

    # Load portfolio state
    state = load_portfolio_state()
    summary = get_portfolio_summary(state)

    print(f"Portfolio as of: {summary['as_of_date']}")
    print(f"Total Value:     ${summary['total_value']:,.0f}")
    print(f"Confidence:      {summary['confidence_score']} / 100")
    print(f"Regime:          {summary['regime']}")
    print()

    # Bucket allocations
    print("Bucket Allocations:")
    for bucket, pct in summary["bucket_allocations"].items():
        print(f"  {bucket:<25} {pct:.1f}%")
    print()

    # Concentration flags
    if summary["concentration_flags"]:
        print("⚠️  Concentration Flags:")
        for flag in summary["concentration_flags"]:
            print(f"  {flag}")
        print()

    # Thesis status
    theses = load_all_theses()
    action_required = get_theses_requiring_action(theses)
    print(f"Active Theses: {len(theses)}")
    if action_required:
        print(f"⚠️  Theses requiring action: {len(action_required)}")
        for t in action_required:
            print(f"  [{t.lifecycle_state.value}] {t.name}")
    print()

    # Generate daily report
    report_path = generate_daily_report(report_date=date.today())
    print(f"Daily report generated: {report_path}")
    print(f"\n{'=' * 60}")
    print("Phase 1 complete. Live data integration begins in Phase 3.")
    print(f"{'=' * 60}\n")


if __name__ == "__main__":
    main()
