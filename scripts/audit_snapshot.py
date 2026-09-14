"""Read-only, offline source coverage audit. No mappings, imputation or datasets.

CSV values remain strings. Lexical type hints describe their representation;
they are not a proposed canonical schema. JSON absent/null/empty are distinct.
Exact identity comparisons are diagnostics, never accepted mapping tables.
"""

import argparse
import csv
import hashlib
import json
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime
from decimal import Decimal
from io import StringIO
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from fpl_model.io import verify_snapshot


def lexical_type(value):
    if value == "":
        return "empty"
    if value in {"True", "False", "true", "false"}:
        return "boolean_text"
    if re.fullmatch(r"-?\d+", value):
        return "integer_text"
    if re.fullmatch(r"-?\d+\.\d+", value):
        return "decimal_text"
    if re.fullmatch(r"\d{4}-\d\d-\d\d", value):
        return "iso_date_text"
    if re.match(r"\d{4}-\d\d-\d\dT", value):
        return "timestamp_text"
    return "text"


def profile(rows, *, csv_values=False, columns=None):
    fields = sorted(set(columns or []) | {key for row in rows for key in row})
    result = {"row_count": len(rows), "columns": fields, "fields": {}}
    for field in fields:
        values = [row[field] for row in rows if field in row]
        p = {
            "absent": len(rows) - len(values), "null": sum(v is None for v in values),
            "empty_string": sum(v == "" for v in values),
            "empty_list": sum(isinstance(v, list) and not v for v in values),
            "empty_object": sum(isinstance(v, dict) and not v for v in values),
            "types": dict(sorted(Counter(type(v).__name__ for v in values).items())),
        }
        if csv_values:
            p["lexical_types"] = dict(sorted(Counter(lexical_type(v) for v in values).items()))
            p["literal_null_tokens"] = sum(v in {"NaN", "nan", "None", "null", "NA"} for v in values)
        objects = [v for v in values if isinstance(v, dict)]
        if objects:
            p["object_fields"] = profile(objects)
        lists = [v for v in values if isinstance(v, list)]
        if lists:
            items = [item for value in lists for item in value]
            p["list_item_count"] = len(items)
            p["list_item_types"] = dict(sorted(Counter(type(item).__name__ for item in items).items()))
            objects = [item for item in items if isinstance(item, dict)]
            if objects:
                p["list_object_fields"] = profile(objects)
        result["fields"][field] = p
    return result


def distribution(rows, field):
    return dict(sorted(Counter(str(row.get(field)) for row in rows).items()))


def date_range(values, *, day_first=False):
    present = [v for v in values if v not in (None, "")]
    parsed = []
    invalid = []
    for value in present:
        try:
            parsed.append(datetime.strptime(value, "%d/%m/%Y").date().isoformat() if day_first
                          else datetime.fromisoformat(value.replace("Z", "+00:00")).isoformat())
        except (ValueError, TypeError):
            invalid.append(value)
    return {"min": min(parsed) if parsed else None, "max": max(parsed) if parsed else None,
            "present": len(present), "invalid": sorted(set(invalid))}


def keys(rows, *fields):
    counts = Counter(tuple(str(row.get(field)) for field in fields) for row in rows)
    return {"fields": list(fields), "distinct": len(counts),
            "duplicate_groups": sum(n > 1 for n in counts.values()),
            "duplicate_excess_rows": sum(n - 1 for n in counts.values()),
            "duplicate_examples": [{"key": list(k), "rows": n} for k, n in sorted(counts.items()) if n > 1][:20]}


def exact_compare(left, right, left_key, right_key, compare_fields=()):
    """String equality only; duplicate keys stay ambiguous, never choose a winner."""
    a, b = defaultdict(list), defaultdict(list)
    for row in left:
        if row.get(left_key) not in (None, ""):
            a[str(row[left_key])].append(row)
    for row in right:
        if row.get(right_key) not in (None, ""):
            b[str(row[right_key])].append(row)
    shared = sorted(a.keys() & b.keys())
    unique = [key for key in shared if len(a[key]) == len(b[key]) == 1]
    conflicts = []
    for key in unique:
        differences = {f"{lk}/{rk}": [a[key][0].get(lk), b[key][0].get(rk)]
                       for lk, rk in compare_fields if str(a[key][0].get(lk)) != str(b[key][0].get(rk))}
        if differences:
            conflicts.append({"key": key, "differences": differences})
    return {"left_key": left_key, "right_key": right_key, "shared": len(shared),
            "unique_shared": len(unique), "unique_shared_keys": unique,
            "left_only": sorted(a.keys() - b.keys()), "right_only": sorted(b.keys() - a.keys()),
            "ambiguous_left": sorted(k for k in a if len(a[k]) > 1),
            "ambiguous_right": sorted(k for k in b if len(b[k]) > 1), "conflicts": conflicts}


def teams_from_matches(matches):
    variants = defaultdict(dict)
    for match in matches:
        for field in ("homeTeam", "awayTeam"):
            team = match[field]
            variants[str(team["id"])][json.dumps(team, sort_keys=True)] = team
    return [team for key in sorted(variants) for team in variants[key].values()]


def field_roles(name, columns):
    """Conservative audit labels, not feature selection or historical eligibility."""
    aggregate = set("minutes starts total_points goals_scored assists clean_sheets goals_conceded own_goals penalties_saved penalties_missed yellow_cards red_cards saves bonus bps tackles clearances_blocks_interceptions recoveries defensive_contribution influence creativity threat ict_index".split())
    state = set("status news news_added chance_of_playing_next_round chance_of_playing_this_round now_cost selected_by_percent form transfers_in transfers_out transfers_in_event transfers_out_event can_select can_transact removed".split())
    context = set("id code player_id player_code team team_code element_type position first_name second_name web_name name short_name pulse_id gw event matchday stage competition season area homeTeam awayTeam utcDate kickoff_time team_h team_a deadline_time Date Time HomeTeam AwayTeam Div".split())
    roles = {}
    for column in columns:
        role = "not_yet_verified"
        if column in context:
            role = "context_only"
        if name in {"fpl_elements", "core_playerstats"}:
            if column in state or column.endswith("_order"):
                role = "candidate_input_after_retrieval"
            if column in aggregate or column.startswith("expected_") or column.endswith("_per_90"):
                role = "post_match_aggregate; candidate_input_after_retrieval; not_fixture_label"
            if column == "event_points":
                role = "current_gw_aggregate_label; provisional; not_fixture_label"
            if column in {"ep_this", "ep_next"}:
                role = "provider_prediction; not_yet_verified; not_target_label"
        if name in {"fpl_fixtures", "org_PL", "org_CL"} and column in {"stats", "team_h_score", "team_a_score", "score", "minutes"}:
            role = "post_match_label_candidate; require_completion; sparse_or_provisional"
        if name in {"fpl_events", "core_gameweek_summaries"} and column in {"average_entry_score", "highest_score", "top_element", "top_element_info", "chip_plays", "ranked_count"}:
            role = "post_deadline_context; not_player_match_label"
        if name == "odds" and column not in {"Div", "Date", "Time", "HomeTeam", "AwayTeam", "Referee"}:
            role = "candidate_odds_input_after_retrieval; publication_time_unverified"
        roles[column] = role
    return roles


def audit(snapshot, evidence_dir=None):
    snapshot = Path(snapshot).resolve()
    manifest = verify_snapshot(snapshot)
    manifest_hash = hashlib.sha256((snapshot / "manifest.json").read_bytes()).hexdigest()
    report = {"audit_schema_version": 1, "audit_id": "step2a_" + manifest["run_id"],
              "snapshot": str(snapshot), "manifest_sha256": manifest_hash,
              "manifest": manifest, "datasets": {}, "identity": {}}
    tables = {}
    envelopes = {}
    for entry in manifest["files"]:
        if entry["outcome"] != "success":
            continue
        path = entry["relative_path"]
        body = (snapshot / path).read_bytes()
        availability = {"recorded_available_at": entry.get("available_at"),
                        "effective_available_at": entry.get("available_at", entry["retrieved_at"]),
                        "availability_basis": "manifest" if "available_at" in entry else "retrieval_fallback_for_audit_only"}
        csv_values = path.endswith(".csv")
        if csv_values:
            try:
                text = body.decode("utf-8-sig")
            except UnicodeDecodeError:
                text = body.decode("cp1252")
            reader = csv.DictReader(StringIO(text, newline=""), strict=True)
            rows = list(reader)
            if any(None in row or None in row.values() for row in rows):
                raise ValueError("Non-rectangular CSV in snapshot")
            name = "core_" + Path(path).stem if entry["source"] == "fpl_core" else "odds"
            parts = {name: rows}
        else:
            data = json.loads(body)
            if entry["source"] == "fpl_api":
                if isinstance(data, list):
                    parts = {"fpl_fixtures": data}
                else:
                    envelopes["fpl_bootstrap"] = {"top_level_keys": sorted(data)}
                    parts = {"fpl_" + name: data[name] for name in ("elements", "teams", "events", "element_types")}
            else:
                code = entry["request_context"]["competition_code"]
                envelopes["org_" + code] = {k: v for k, v in data.items() if k != "matches"}
                envelopes["org_" + code]["top_level_keys"] = sorted(data)
                parts = {"org_" + code: data["matches"], "org_" + code + "_teams": teams_from_matches(data["matches"])}
        for name, rows in parts.items():
            tables[name] = rows
            report["datasets"][name] = {"raw_file": path, "retrieved_at": entry["retrieved_at"],
                                       **availability, **profile(rows, csv_values=csv_values,
                                                               columns=reader.fieldnames if csv_values else None)}
            report["datasets"][name]["field_roles"] = field_roles(name, report["datasets"][name]["columns"])
    d = report["datasets"]
    fpl, core, fixtures = tables["fpl_elements"], tables["core_players"], tables["fpl_fixtures"]
    for name, fields in {"fpl_elements": ("id",), "fpl_teams": ("id",), "fpl_events": ("id",),
                         "fpl_fixtures": ("id",), "core_players": ("player_id",), "core_teams": ("code",),
                         "core_playerstats": ("id", "gw"), "core_gameweek_summaries": ("id",),
                         "odds": ("Div", "Date", "HomeTeam", "AwayTeam"),
                         "org_PL": ("id",), "org_CL": ("id",)}.items():
        d[name]["key_audit"] = keys(tables[name], *fields)
    d["fpl_elements"]["status_counts"] = distribution(fpl, "status")
    d["fpl_elements"]["id_range"] = [min(r["id"] for r in fpl), max(r["id"] for r in fpl)]
    d["fpl_elements"]["expected_fields"] = [k for k in d["fpl_elements"]["columns"] if k.startswith("expected_") or k.startswith("ep_")]
    d["fpl_teams"]["entities"] = tables["fpl_teams"]
    d["fpl_events"]["deadlines"] = [{k: r[k] for k in ("id", "deadline_time", "finished", "data_checked", "is_current", "is_next")} for r in tables["fpl_events"]]
    effective = datetime.fromisoformat(d["fpl_elements"]["effective_available_at"])
    d["fpl_events"]["deadline_ids_before_retrieval"] = [r["id"] for r in tables["fpl_events"] if datetime.fromisoformat(r["deadline_time"].replace("Z", "+00:00")) <= effective]
    d["fpl_fixtures"].update({"kickoff_range": date_range([r["kickoff_time"] for r in fixtures]),
        "event_counts": distribution(fixtures, "event"), "finished_counts": distribution(fixtures, "finished"),
        "started_counts": distribution(fixtures, "started"), "id_range": [min(r["id"] for r in fixtures), max(r["id"] for r in fixtures)],
        "stats_identifiers": dict(sorted(Counter(s["identifier"] for r in fixtures for s in r["stats"]).items())),
        "stats_element_ids": sorted({v["element"] for r in fixtures for s in r["stats"] for side in ("a", "h") for v in s[side]})})
    stats = tables["core_playerstats"]
    d["core_playerstats"]["gw_counts"] = distribution(stats, "gw")
    d["core_playerstats"]["distinct_player_ids"] = len({r["id"] for r in stats})
    d["core_playerstats"]["per_gw"] = {}
    official = {str(r["id"]): r for r in fpl}
    metrics = ["minutes", "starts", "total_points", "expected_goals", "expected_assists", "tackles", "clearances_blocks_interceptions", "recoveries"]
    for gw in sorted({r["gw"] for r in stats}, key=int):
        rows = [r for r in stats if r["gw"] == gw]
        d["core_playerstats"]["per_gw"][gw] = {
            "row_count": len(rows), "missing_current_player_ids": sorted(official.keys() - {r["id"] for r in rows}, key=int),
            "metric_max": {k: str(max(Decimal(r[k]) for r in rows if r[k])) for k in metrics},
            "minutes_over_90": sum(Decimal(r["minutes"]) > 90 for r in rows if r["minutes"]),
        }
    latest = [r for r in stats if int(r["gw"]) == max(int(s["gw"]) for s in stats)]
    d["core_playerstats"]["latest_vs_fpl"] = {
        key: {"equal": sum(Decimal(r[key]) == Decimal(str(official[r["id"]][key])) for r in latest if r[key] and r["id"] in official),
              "compared": sum(bool(r[key]) and r["id"] in official for r in latest)} for key in metrics}
    d["core_playerstats"]["cost_scale_check"] = {
        "compared": len(latest), "core_times_10_equals_fpl": sum(Decimal(r["now_cost"]) * 10 == Decimal(official[r["id"]]["now_cost"]) for r in latest if r["id"] in official)}
    summaries = tables["core_gameweek_summaries"]
    d["core_gameweek_summaries"]["snapshot_times"] = distribution(summaries, "snapshot_time")
    d["core_gameweek_summaries"]["deadline_range"] = date_range([r["deadline_time"] for r in summaries])
    d["core_gameweek_summaries"]["finished_counts"] = distribution(summaries, "finished")
    odds = tables["odds"]
    pl_odds = [r for r in odds if r["Div"] == "E0"]
    d["odds"].update({"league_counts": distribution(odds, "Div"), "date_range": date_range([r["Date"] for r in odds], day_first=True),
        "pl_row_count": len(pl_odds), "pl_date_range": date_range([r["Date"] for r in pl_odds], day_first=True),
        "pl_rows": pl_odds, "pl_teams": sorted({r[k] for r in pl_odds for k in ("HomeTeam", "AwayTeam")}),
        "pl_profile": profile(pl_odds, csv_values=True)})
    for code in ("PL", "CL"):
        name = "org_" + code
        matches = tables[name]
        d[name].update({"envelope": envelopes[name], "utcDate_range": date_range([r["utcDate"] for r in matches]),
            "lastUpdated_range": date_range([r["lastUpdated"] for r in matches]), "status_counts": distribution(matches, "status"),
            "stage_counts": distribution(matches, "stage"), "matchday_counts": distribution(matches, "matchday"),
            "match_ids": sorted(r["id"] for r in matches), "teams": tables[name + "_teams"]})
    identity = report["identity"]
    identity["fpl_team_core_by_code"] = exact_compare(tables["fpl_teams"], tables["core_teams"], "code", "code", [(k, k) for k in ("id", "name", "short_name")])
    identity["fpl_player_core_by_id"] = exact_compare(fpl, core, "id", "player_id", [("code", "player_code"), ("team_code", "team_code"), ("first_name", "first_name"), ("second_name", "second_name"), ("web_name", "web_name")])
    identity["fpl_player_core_by_code"] = exact_compare(fpl, core, "code", "player_code", [("id", "player_id")])
    identity["fpl_player_core_latest_stats"] = exact_compare(fpl, latest, "id", "id", [(k,k) for k in ("first_name", "second_name", "web_name")])
    identity["fpl_fixture_core_match"] = {"status": "not_auditable", "reason": "No Core matches or playermatchstats file in this snapshot"}
    identity["fpl_team_odds_exact_name"] = exact_compare(tables["fpl_teams"], [{"name": n} for n in d["odds"]["pl_teams"]], "name", "name")
    for code in ("PL", "CL"):
        for key in ("name", "shortName", "tla"):
            identity[f"fpl_team_org_{code}_{key}"] = exact_compare(tables["fpl_teams"], tables["org_" + code + "_teams"], "short_name" if key == "tla" else "name", key)
    report["bootstrap_top_level_keys"] = envelopes["fpl_bootstrap"]["top_level_keys"]
    if evidence_dir is not None:
        evidence_dir = Path(evidence_dir)
        index = json.loads((evidence_dir / "index.json").read_bytes())
        for entry in index:
            if Path(entry["file"]).name != entry["file"]:
                raise ValueError("Evidence must use flat filenames")
            if hashlib.sha256((evidence_dir / entry["file"]).read_bytes()).hexdigest() != entry["sha256"]:
                raise ValueError("Evidence checksum mismatch")
        commit = json.loads((evidence_dir / "core_commit.json").read_bytes())
        if commit["sha"] != manifest["source_commits"]["fpl_core"]:
            raise ValueError("Upstream evidence does not match snapshot Core commit")
        tree = json.loads((evidence_dir / "core_tree.json").read_bytes())
        prefix = "data/" + manifest["run_metadata"]["season"] + "/"
        report["upstream_evidence"] = {
            "not_snapshot_data": True, "index": index, "core_commit_sha": commit["sha"],
            "core_commit_time_not_availability": commit["commit"]["committer"]["date"],
            "tree_truncated": tree.get("truncated"),
            "season_tree": [{k: row[k] for k in ("path", "type", "sha", "size") if k in row}
                            for row in tree["tree"] if row["path"].startswith(prefix)],
        }
    verify_snapshot(snapshot)  # Detect any input mutation while auditing.
    if hashlib.sha256((snapshot / "manifest.json").read_bytes()).hexdigest() != manifest_hash:
        raise ValueError("Snapshot manifest changed during audit")
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("snapshot", type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--evidence", type=Path, help="optional already-downloaded metadata/docs; never fetched")
    args = parser.parse_args(argv)
    if args.output.resolve().is_relative_to(args.snapshot.resolve()):
        parser.error("audit output must be outside the immutable snapshot")
    report = audit(args.snapshot, args.evidence)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x") as stream:
        stream.write(json.dumps(report, indent=2, sort_keys=True, ensure_ascii=False) + "\n")
    print(args.output)


if __name__ == "__main__":
    main()
