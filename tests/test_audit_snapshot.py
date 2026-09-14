"""Offline audit tests; synthetic snapshots and literal comparisons only."""

import csv
import hashlib
import importlib.util
import io
import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from fpl_model.io import SnapshotIntegrityError, SnapshotWriter


SPEC = importlib.util.spec_from_file_location("audit_snapshot", Path(__file__).resolve().parents[1] / "scripts/audit_snapshot.py")
audit_module = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(audit_module)
NOW = datetime(2026, 9, 13, 15, tzinfo=timezone.utc)


def test_profile_keeps_missing_null_empty_and_zero_distinct():
    rows = [{"x": None, "nested": {"a": 0}, "items": []},
            {"x": "", "nested": {}, "items": [{"a": False}]}, {"x": 0}, {}]
    p = audit_module.profile(rows)
    x = p["fields"]["x"]
    assert x["absent"] == x["null"] == x["empty_string"] == 1
    assert x["types"] == {"NoneType": 1, "int": 1, "str": 1}
    assert p["fields"]["nested"]["empty_object"] == 1
    assert p["fields"]["nested"]["object_fields"]["fields"]["a"]["absent"] == 1
    assert p["fields"]["items"]["empty_list"] == 1
    assert p["fields"]["items"]["list_object_fields"]["fields"]["a"]["types"] == {"bool": 1}


def test_csv_types_are_lexical_only_without_imputation():
    rows = [{"x": v} for v in ["", "0", "1.2", "False", "NaN", "2026-09-13"]]
    p = audit_module.profile(rows, csv_values=True)["fields"]["x"]
    assert p["types"] == {"str": 6} and p["null"] == 0
    assert p["literal_null_tokens"] == 1 and p["empty_string"] == 1
    assert rows[4]["x"] == "NaN"
    assert audit_module.profile([], csv_values=True, columns=["id"])["columns"] == ["id"]


def test_identity_audit_reports_conflicts_and_ambiguity_without_guessing():
    a = [{"id": 1, "name": "Spurs"}, {"id": 2, "name": "Same"}, {"id": 3, "name": "Same"}]
    b = [{"id": "1", "name": "Tottenham"}, {"id": "2", "name": "Same"}, {"id": "2", "name": "Same"}]
    ids = audit_module.exact_compare(a, b, "id", "id", [("name", "name")])
    assert ids["shared"] == 2 and ids["unique_shared"] == 1
    assert ids["ambiguous_right"] == ["2"] and ids["left_only"] == ["3"]
    assert ids["conflicts"] == [{"key": "1", "differences": {"name/name": ["Spurs", "Tottenham"]}}]
    names = audit_module.exact_compare(a, b, "name", "name")
    assert names["left_only"] == ["Spurs"] and names["right_only"] == ["Tottenham"]
    assert names["unique_shared"] == 0


def test_composite_keys_and_day_first_dates():
    rows = [{"id": 1, "gw": 1}, {"id": 1, "gw": 2}, {"id": 1, "gw": 2}]
    assert audit_module.keys(rows, "id", "gw")["duplicate_excess_rows"] == 1
    dates = audit_module.date_range(["12/09/2026", "01/10/2026", "invalid", ""], day_first=True)
    assert dates["min"] == "2026-09-12" and dates["max"] == "2026-10-01"
    assert dates["invalid"] == ["invalid"]


@pytest.fixture
def snapshot(tmp_path):
    writer = SnapshotWriter(tmp_path / "raw", clock=lambda: NOW)

    def raw(path, data, source):
        writer.write_raw(path, data, source=source, required=source == "fpl_api",
                         request_started_at=NOW, retrieved_at=NOW, http_status=200,
                         **({"available_at": NOW} if source == "football_data_org" else {}))

    def csv_file(path, rows, source):
        stream = io.StringIO(newline="")
        out = csv.DictWriter(stream, fieldnames=list(rows[0]))
        out.writeheader()
        out.writerows(rows)
        raw(path, stream.getvalue().encode(), source)

    metrics = dict.fromkeys(["minutes", "starts", "total_points", "expected_goals", "expected_assists", "tackles", "clearances_blocks_interceptions", "recoveries"], 0)
    player = {"id": 1, "code": 10, "team_code": 3, "first_name": "Test", "second_name": "Player", "web_name": "Test", "status": "a", "now_cost": 50, **metrics}
    team = {"id": 1, "code": 3, "name": "Team", "short_name": "TEA"}
    event = {"id": 1, "deadline_time": "2026-09-12T10:00:00Z", "finished": False, "data_checked": False, "is_current": True, "is_next": False}
    raw("fpl_api/bootstrap_static.json", json.dumps({"elements": [player], "teams": [team], "events": [event], "element_types": [{"id": 1}]}).encode(), "fpl_api")
    raw("fpl_api/fixtures.json", json.dumps([{"id": 1, "event": 1, "kickoff_time": "2026-09-14T14:00:00Z", "finished": False, "started": False, "stats": []}]).encode(), "fpl_api")
    csv_file("fpl_core/players.csv", [{"player_id": 1, "player_code": 10, "team_code": 3, "first_name": "Test", "second_name": "Player", "web_name": "Test"}], "fpl_core")
    csv_file("fpl_core/teams.csv", [team], "fpl_core")
    csv_file("fpl_core/playerstats.csv", [{"id": 1, "gw": 1, "first_name": "Test", "second_name": "Player", "web_name": "Test", "now_cost": "5.0", **metrics}], "fpl_core")
    csv_file("fpl_core/gameweek_summaries.csv", [{**event, "snapshot_time": "2026-07-01T00:00:00Z"}], "fpl_core")
    csv_file("football_data_uk/fixtures.csv", [{"Div": "E0", "Date": "14/09/2026", "HomeTeam": "Team", "AwayTeam": "Other"}], "football_data_uk")
    org_team = {"id": 10, "name": "Team FC", "shortName": "Team", "tla": "TEA"}
    for code in ("PL", "CL"):
        data = {"matches": [{"id": 10, "utcDate": "2026-09-14T14:00:00Z", "lastUpdated": "2026-09-12T00:00:00Z", "homeTeam": org_team, "awayTeam": {**org_team, "id": 11, "name": "Other FC", "shortName": "Other"}, "status": "TIMED", "stage": "REGULAR_SEASON", "matchday": 1}]}
        writer.write_raw(f"football_data_org/{code}/matches.json", json.dumps(data).encode(), source="football_data_org", required=False, request_started_at=NOW, retrieved_at=NOW, available_at=NOW, request_context={"competition_code": code})
    return writer.finalize()


def test_full_offline_audit_is_deterministic_and_does_not_change_raw(snapshot):
    before = {p: hashlib.sha256(p.read_bytes()).hexdigest() for p in snapshot.rglob("*") if p.is_file()}
    report = audit_module.audit(snapshot)
    assert report == audit_module.audit(snapshot)
    d = report["datasets"]
    assert d["fpl_elements"]["recorded_available_at"] is None
    assert d["fpl_elements"]["effective_available_at"] == NOW.isoformat(timespec="microseconds")
    assert d["org_PL"]["availability_basis"] == "manifest"
    assert d["core_playerstats"]["cost_scale_check"]["core_times_10_equals_fpl"] == 1
    assert d["fpl_events"]["deadline_ids_before_retrieval"] == [1]
    assert report["identity"]["fpl_fixture_core_match"]["status"] == "not_auditable"
    assert before == {p: hashlib.sha256(p.read_bytes()).hexdigest() for p in snapshot.rglob("*") if p.is_file()}


def test_audit_rejects_corrupt_input(snapshot):
    (snapshot / "raw/fpl_api/fixtures.json").write_bytes(b"[]")
    with pytest.raises(SnapshotIntegrityError):
        audit_module.audit(snapshot)


def test_cli_cannot_write_into_snapshot_or_overwrite_report(snapshot, tmp_path):
    with pytest.raises(SystemExit):
        audit_module.main([str(snapshot), "--output", str(snapshot / "coverage.json")])
    output = tmp_path / "audit/coverage.json"
    audit_module.main([str(snapshot), "--output", str(output)])
    with pytest.raises(FileExistsError):
        audit_module.main([str(snapshot), "--output", str(output)])
    assert json.loads(output.read_text())["audit_id"].startswith("step2a_")
