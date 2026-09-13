"""One explicit-date ClubElo probe; no fallback or exact coverage/value assertions."""

import csv
import json
from datetime import date
from io import StringIO

import pytest

from fpl_model.data_sources.clubelo import fetch_clubelo
from fpl_model.io import SnapshotWriter, verify_snapshot


# Fixed recent date chosen for Step 1E2; changing it is a deliberate test update.
RATING_DATE = date(2026, 9, 12)


@pytest.mark.live
def test_explicit_date_clubelo_smoke(tmp_path, capsys):
    writer = SnapshotWriter(tmp_path / "live-clubelo")
    result = fetch_clubelo(writer, RATING_DATE)
    manifest = json.loads((writer.staging_path / "manifest.json").read_bytes())
    report = {
        "requested_rating_date": RATING_DATE.isoformat(), "status": result.status,
        "responses": [{key: entry[key] for key in (
            "request_url", "http_status", "content_type", "relative_path", "size_bytes",
        )} for entry in manifest["files"]],
        "columns": None, "row_count": None, "pl_clubs_present": None,
    }
    if result.status == "success":
        body = (writer.staging_path / result.raw_path).read_bytes()
        try:
            text = body.decode("utf-8-sig")
        except UnicodeDecodeError:
            text = body.decode("cp1252")
        reader = csv.DictReader(StringIO(text, newline=""), strict=True)
        rows = list(reader)
        report["columns"] = reader.fieldnames
        report["row_count"] = len(rows)
        if "Level" in reader.fieldnames:
            # Provider's ENG/Level=1 classification is a coverage indicator,
            # not proof of completeness against an independent PL club roster.
            clubs = sorted({r["Club"] for r in rows
                            if r["Country"].strip() == "ENG" and r["Level"].strip() == "1"})
            report["english_level_1_clubs"] = clubs
            report["pl_clubs_present"] = bool(clubs)
    with capsys.disabled():
        print("\nClubElo observed source contract: " + json.dumps(report, sort_keys=True))
    assert result.status == "success", report
    assert report["row_count"] > 0, "Valid headers but no usable ratings for the requested date"
    assert not writer.final_path.exists()
    data = verify_snapshot(writer.finalize())
    entry = next(e for e in data["files"] if e["relative_path"] == result.raw_path)
    assert entry["source"] == "clubelo" and entry["required"] is False
    assert entry["request_context"] == {"requested_rating_date": RATING_DATE.isoformat()}
    assert entry["available_at"] == entry["retrieved_at"]
