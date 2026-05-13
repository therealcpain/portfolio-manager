"""Tests for vote_db.py — uses a temp file to avoid touching real data."""

import sys
import json
import tempfile
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))


def _temp_votes_file():
    return tempfile.NamedTemporaryFile(suffix=".json", delete=False)


def test_get_agent_scorecard_no_data():
    """Scorecard returns zeroed metrics when no votes exist."""
    with tempfile.NamedTemporaryFile(suffix=".json", mode="w", delete=False) as f:
        json.dump({"recommendations": {}, "votes": []}, f)
        tmp_path = Path(f.name)

    with patch("vote_db.VOTES_FILE", tmp_path):
        import vote_db
        scorecard = vote_db.get_agent_scorecard("cio")
        assert scorecard["total_votes"] == 0
        assert scorecard["hit_rate_pct"] == 0.0
        assert scorecard["correct"] == 0


def test_record_and_retrieve_recommendation():
    with tempfile.NamedTemporaryFile(suffix=".json", mode="w", delete=False) as f:
        json.dump({"recommendations": {}, "votes": []}, f)
        tmp_path = Path(f.name)

    with patch("vote_db.VOTES_FILE", tmp_path):
        import vote_db
        vote_db.record_recommendation(
            rec_id="REC-001",
            date_str="2026-05-13",
            asset="SPY",
            action="Buy_Partial",
            thesis_summary="Macro risk-on continuation.",
            confidence=65,
            time_horizon="Strategic",
            invalidation="SPY breaks 200d MA",
        )
        pending = vote_db.list_pending_recommendations()
        assert len(pending) == 1
        assert pending[0]["asset"] == "SPY"


def test_record_and_resolve_vote():
    with tempfile.NamedTemporaryFile(suffix=".json", mode="w", delete=False) as f:
        json.dump({"recommendations": {}, "votes": []}, f)
        tmp_path = Path(f.name)

    with patch("vote_db.VOTES_FILE", tmp_path):
        import vote_db
        vote_db.record_recommendation(
            rec_id="REC-002", date_str="2026-05-13", asset="GLD",
            action="Hold", thesis_summary="Gold monetary hedge.", confidence=65,
            time_horizon="Structural", invalidation="Real rates spike >2%",
        )
        vote_db.record_vote("REC-002", "macro_strategist", "Agree", 70, "Gold supported by falling real rates.")
        vote_db.resolve_outcome("REC-002", "Correct", return_pct=8.5, benchmark_return_pct=4.2)

        scorecard = vote_db.get_agent_scorecard("macro_strategist")
        assert scorecard["total_votes"] == 1
        assert scorecard["correct"] == 1
        assert scorecard["hit_rate_pct"] == 100.0


def test_all_scorecards_returns_17():
    with tempfile.NamedTemporaryFile(suffix=".json", mode="w", delete=False) as f:
        json.dump({"recommendations": {}, "votes": []}, f)
        tmp_path = Path(f.name)

    with patch("vote_db.VOTES_FILE", tmp_path):
        import vote_db
        cards = vote_db.get_all_scorecards()
        assert len(cards) == 17
        agents = {c["agent"] for c in cards}
        assert "cio" in agents
        assert "meta_philosophy_auditor" in agents
