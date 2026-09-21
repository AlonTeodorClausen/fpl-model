"""Step 2B experiment only: fixed 12-player sample and six pinned Core CSVs.

Does not extend the production runner or enumerate the FPL player universe.
Every response body is stored before validation; no historical availability is
inferred. Fresh bootstrap/fixtures provide completion and identity context for
the live histories. The first snapshot remains unchanged.
"""

import argparse
import csv
import json
import sys
import time
from datetime import datetime, timezone
from io import StringIO
from pathlib import Path
from urllib.parse import quote

import requests

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from fpl_model.io import SnapshotWriter, verify_snapshot


PLAYER_IDS = (1, 2, 4, 5, 12, 26, 109, 115, 124, 126, 426, 439)
CORE_FILES = tuple(
    f"data/2026-2027/{folder}/{name}.csv"
    for folder in ("By Gameweek/GW3", "By Gameweek/GW4", "By Tournament/Champions League/GW4")
    for name in ("matches", "playermatchstats")
)
EXPECTED_SHA = "907f666f2dc6796d417e49287fd31f88263f1d67"


class CaptureError(RuntimeError):
    pass


def utc_now():
    return datetime.now(timezone.utc)


def capture(writer, client, *, source, url, relative, required, kind, context=None,
            commit_sha=None, clock=utc_now, sleep=time.sleep):
    """At most three GETs; no redirects, headers/secrets or exception text persisted.

    Optional requests use 1s/2s backoff on transport errors and 5xx only.
    Required requests fail closed on the first failure: SnapshotWriter retains
    every required failure and cannot publish it as complete after a retry.
    A 429 is preserved and stops the probe rather than retrying before a server
    waiting requirement. This is not a general ingestion retry framework.
    """
    provenance = {"source": source, "required": required, "request_url": url,
                  "request_params": {}, "request_context": context or {}}
    if commit_sha:
        provenance["commit_sha"] = commit_sha
    for attempt in range(1, 4):
        started = clock()
        try:
            with client.get(url, timeout=(10, 30), allow_redirects=False) as response:
                body = response.content
                retrieved = clock()
                status = response.status_code
                content_type = response.headers.get("Content-Type", "")
        except requests.RequestException:
            writer.record_failure(**provenance, request_started_at=started, error_code="transport_error")
            if attempt < 3 and not required:
                sleep(float(attempt))
                continue
            raise CaptureError("sample transport failure") from None
        path = f"{source}/attempt_{attempt:02d}/{relative}"
        writer.write_raw(path, body, **provenance, request_started_at=started,
                         retrieved_at=retrieved, available_at=retrieved,
                         http_status=status, content_type=content_type)
        if status != 200:
            writer.record_failure(**provenance, request_started_at=started,
                                  relative_path="raw/" + path, error_code="http_error")
            if 500 <= status < 600 and attempt < 3 and not required:
                sleep(float(attempt))
                continue
            raise CaptureError(f"sample HTTP {status}")
        try:
            if "html" in content_type.lower():
                raise ValueError
            if kind == "json":
                parsed = json.loads(body)
                if not isinstance(parsed, (dict, list)):
                    raise ValueError
            else:
                reader = csv.reader(StringIO(body.decode("utf-8-sig"), newline=""), strict=True)
                header = next(reader)
                if not header or len(header) != len(set(header)) or len(header) < 2:
                    raise ValueError
                if any(len(row) != len(header) for row in reader if row):
                    raise ValueError
        except (ValueError, csv.Error, StopIteration):
            writer.record_failure(**provenance, request_started_at=started,
                                  relative_path="raw/" + path, error_code="invalid_payload")
            raise CaptureError("sample contract failure") from None
        return "raw/" + path


def run(baseline, raw_root):
    previous = verify_snapshot(baseline)
    sha = previous["source_commits"]["fpl_core"]
    if sha != EXPECTED_SHA:
        raise ValueError("Step 2B must use the Step 1 audited Core commit")
    writer = SnapshotWriter(raw_root)
    writer.set_run_metadata({"purpose": "step2b_label_sample", "baseline_snapshot_id": previous["run_id"],
                             "core_commit_sha": sha, "player_ids": ",".join(map(str, PLAYER_IDS))})
    optional_failed = False
    try:
        with requests.Session() as client:
            for endpoint, relative in (("bootstrap-static/", "bootstrap_static.json"), ("fixtures/", "fixtures.json")):
                capture(writer, client, source="fpl_api", url="https://fantasy.premierleague.com/api/" + endpoint,
                        relative=relative, required=True, kind="json")
            for player_id in PLAYER_IDS:
                capture(writer, client, source="fpl_api", url=f"https://fantasy.premierleague.com/api/element-summary/{player_id}/",
                        relative=f"element_summary/{player_id}.json", required=True, kind="json",
                        context={"element_id": str(player_id)})
            writer.pin_source_commit("fpl_core", sha)
            for path in CORE_FILES:
                try:
                    capture(writer, client, source="fpl_core",
                            url=f"https://raw.githubusercontent.com/olbauday/FPL-Core-Insights/{sha}/" + quote(path),
                            relative=sha + "/" + path, required=False, kind="csv", commit_sha=sha)
                except CaptureError:
                    optional_failed = True
        return writer.finalize(), optional_failed
    except BaseException:
        writer.mark_failed()
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("baseline", type=Path)
    parser.add_argument("--raw-root", type=Path, required=True)
    args = parser.parse_args()
    path, partial = run(args.baseline, args.raw_root)
    print(f"snapshot_path: {path}\ncoverage: {'partial' if partial else 'complete'}")


if __name__ == "__main__":
    main()
