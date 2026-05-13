"""Tests for nav_tracker.py — uses temp files."""

import sys
import json
import tempfile
from pathlib import Path
from datetime import date
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))


def _temp_nav_file():
    f = tempfile.NamedTemporaryFile(suffix=".json", mode="w", delete=False)
    json.dump({"inception_date": "2026-05-13", "starting_capital": 100000.0, "snapshots": {}}, f)
    return Path(f.name)


def test_record_and_retrieve_nav():
    tmp = _temp_nav_file()
    with patch("nav_tracker.NAV_FILE", tmp):
        import nav_tracker
        nav_tracker.record_snapshot(nav=102500.0, snapshot_date=date(2026, 5, 14))
        nav_tracker.record_snapshot(nav=105000.0, snapshot_date=date(2026, 5, 15))
        series = nav_tracker.get_nav_series()
        assert len(series) == 2
        assert float(series.iloc[-1]) == 105000.0


def test_get_latest_nav_empty():
    tmp = _temp_nav_file()
    with patch("nav_tracker.NAV_FILE", tmp):
        import nav_tracker
        nav = nav_tracker.get_latest_nav()
        assert nav == 100_000.0  # falls back to starting capital


def test_total_return_positive():
    tmp = _temp_nav_file()
    with patch("nav_tracker.NAV_FILE", tmp):
        import nav_tracker
        nav_tracker.record_snapshot(nav=112000.0, snapshot_date=date(2026, 6, 1))
        ret = nav_tracker.get_total_return()
        assert ret["pct_return"] == 12.0
        assert ret["dollar_return"] == 12000.0


def test_total_return_negative():
    tmp = _temp_nav_file()
    with patch("nav_tracker.NAV_FILE", tmp):
        import nav_tracker
        nav_tracker.record_snapshot(nav=88000.0, snapshot_date=date(2026, 6, 1))
        ret = nav_tracker.get_total_return()
        assert ret["pct_return"] == -12.0
        assert ret["dollar_return"] == -12000.0
