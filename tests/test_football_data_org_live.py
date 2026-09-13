"""One opt-in free-account contract probe; no token means a clean skip.

Reports observed field names only, not an assertion of universal free-plan
coverage. No expectations about teams, scores, counts or rounds.
"""

import json
import os

import pytest

from fpl_model.data_sources.football_data_org import fetch_competition_matches
from fpl_model.io import SnapshotWriter, verify_snapshot


@pytest.mark.live
def test_pl_and_cl_matches_smoke(tmp_path, capsys):
    if not os.getenv("FOOTBALL_DATA_ORG_TOKEN", "").strip():
        pytest.skip("FOOTBALL_DATA_ORG_TOKEN is not configured")
    writer = SnapshotWriter(tmp_path / "live-football-data-org")
    results = {code: fetch_competition_matches(code, writer) for code in ("PL", "CL")}
    # Inspect preserved bytes outside ingestion, even if the other competition failed.
    data = json.loads((writer.staging_path / "manifest.json").read_bytes())
    report = {}
    for code, result in results.items():
        entries = [e for e in data["files"] if e["request_context"]["competition_code"] == code]
        observation = {"status": result.status, "http_statuses": [e["http_status"] for e in entries]}
        if result.status == "success":
            payload = json.loads((writer.staging_path / result.raw_path).read_bytes())
            observation["top_level_keys"] = sorted(payload)
            observation["representative_match_fields"] = (
                sorted(payload["matches"][0]) if payload["matches"] else []
            )
            observation["representative_match_available"] = bool(payload["matches"])
        report[code] = observation
    with capsys.disabled():
        print("\nfootball-data.org observed source contract: " + json.dumps(report, sort_keys=True))
    assert all(r.status == "success" for r in results.values()), report
    assert not writer.final_path.exists()
    manifest = verify_snapshot(writer.finalize())
    for code, result in results.items():
        entry = next(e for e in manifest["files"] if e["relative_path"] == result.raw_path)
        assert entry["source"] == "football_data_org" and entry["required"] is False
        assert entry["request_context"] == {"competition_code": code}
        assert entry["request_params"] == {}
        assert entry["available_at"] == entry["retrieved_at"]
