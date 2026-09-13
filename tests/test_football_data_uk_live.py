"""Opt-in check of the configured upcoming feed, not historical data.

No assumptions about teams, row counts, dates or bookmaker values. Provider
outages/HTML/schema errors fail visibly; they are not skipped or treated as CSV.
"""

import pytest

from fpl_model.data_sources.football_data_uk import fetch_upcoming_odds
from fpl_model.io import SnapshotWriter, verify_snapshot


@pytest.mark.live
def test_upcoming_fixtures_feed_smoke(tmp_path):
    writer = SnapshotWriter(tmp_path / "live-football-data-uk")
    result = fetch_upcoming_odds(writer)
    assert result.status == "success", f"Upcoming feed source contract failed: {result.status}"
    manifest = verify_snapshot(writer.finalize())
    entry = next(entry for entry in manifest["files"] if entry["relative_path"] == result.raw_path)
    assert entry["source"] == "football_data_uk" and entry["required"] is False
    assert entry["available_at"] == entry["retrieved_at"]
