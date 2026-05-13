#!/bin/bash
# run_daily.sh — Run the daily portfolio loop and email the brief.
# Scheduled via crontab: 30 6 * * 1-5 (6:30 AM PT, Mon–Fri)
#
# To install:
#   crontab -e
#   30 6 * * 1-5 /Users/christianacosta/Documents/GitHub/portfolio-manager/scripts/run_daily.sh

set -e

REPO="/Users/christianacosta/Documents/GitHub/portfolio-manager"
VENV="$REPO/.venv/bin/python3"
LOG="$REPO/logs/daily_$(date +%Y-%m-%d).log"

mkdir -p "$REPO/logs"

echo "=== Daily loop starting at $(date) ===" >> "$LOG" 2>&1

cd "$REPO"
"$VENV" -c "
import sys
sys.path.insert(0, 'src')
from daily_loop import run_daily_loop, DailyLoopConfig
result = run_daily_loop(DailyLoopConfig(mock=False, verbose=True))
ok = result.phases_ok()
failed = result.phases_failed()
print(f'Phases OK: {ok}')
print(f'Phases failed: {failed}')
print(f'Total elapsed: {result.total_elapsed_s:.1f}s')
" >> "$LOG" 2>&1

echo "=== Done at $(date) ===" >> "$LOG" 2>&1
