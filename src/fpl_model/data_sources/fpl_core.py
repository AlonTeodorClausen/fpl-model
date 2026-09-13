"""Pinned, raw CSV ingestion of the four existing Core season master files.

The caller supplies a full Git SHA and finalizes its SnapshotWriter. No branch
resolution, directory discovery, GW/tournament traversal, or Parquet conversion
occurs here. See notes/fpl_core_contract.md for observed upstream ambiguities.
"""

import csv
import re
from collections.abc import Callable
from contextlib import nullcontext
from datetime import datetime, timezone
from io import StringIO

import requests

from fpl_model.config import FPL_CORE_RAW
from fpl_model.io import SnapshotWriter


REQUIRED_FILES = ("players.csv", "teams.csv", "playerstats.csv")
OPTIONAL_FILES = ("gameweek_summaries.csv",)
MASTER_FILES = REQUIRED_FILES + OPTIONAL_FILES
REQUIRED_COLUMNS = {
    "players.csv": {"player_id", "player_code", "team_code", "position"},
    "teams.csv": {"id", "code", "name"},
    "playerstats.csv": {"id", "gw", "minutes", "total_points"},
    "gameweek_summaries.csv": {"id", "deadline_time"},
}


class CoreSourceError(RuntimeError):
    """A required Core source failed; response bytes remain in staging if received."""


class CoreContractError(CoreSourceError):
    """A required CSV failed the minimal source contract."""


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _integer(value: str, *, minimum: int = 1) -> None:
    if not re.fullmatch(r"[0-9]+", value) or int(value) < minimum:
        raise ValueError("Expected an integer source identifier")


def _validate_csv(filename: str, body: bytes) -> None:
    """Validate stored CSV bytes without normalizing or returning a dataset.

    Unknown columns and header-only tables are allowed. Row counts, joins and
    duplicate player IDs across gameweeks are deliberately not dataset validation.
    """
    reader = csv.reader(StringIO(body.decode("utf-8-sig"), newline=""), strict=True)
    header = next(reader, None)
    if (
        not header or any(not column or not column.strip() for column in header)
        or len(header) != len(set(header))
        or not REQUIRED_COLUMNS[filename].issubset(header)
    ):
        raise ValueError("Missing, empty or duplicate CSV columns")
    for values in reader:
        if not values:  # CSV exporters may leave blank lines between/trailing rows.
            continue
        if len(values) != len(header):
            raise ValueError("CSV row width does not match its header")
        row = dict(zip(header, values, strict=True))
        if filename == "players.csv":
            for key in ("player_id", "player_code", "team_code"):
                _integer(row[key])
            if not row["position"].strip():
                raise ValueError("Missing player position")
        else:
            _integer(row["id"])
            if filename == "teams.csv":
                _integer(row["code"])
                if not row["name"].strip():
                    raise ValueError("Missing team name")
            elif filename == "playerstats.csv":
                _integer(row["gw"], minimum=0)
            else:
                deadline = datetime.fromisoformat(row["deadline_time"])
                if deadline.tzinfo is None or deadline.utcoffset() is None:
                    raise ValueError("Deadline must be timezone-aware")


def _fetch_file(
    writer: SnapshotWriter, client: requests.Session, filename: str, *,
    season: str, commit_sha: str, clock: Callable[[], datetime],
) -> str:
    required = filename in REQUIRED_FILES
    url = f"{FPL_CORE_RAW}/{commit_sha}/data/{season}/{filename}"
    started = clock()
    if started.tzinfo is None or started.utcoffset() is None:
        raise ValueError("Request clock must be timezone-aware")
    try:
        with client.get(url, timeout=(10, 30), allow_redirects=False) as response:
            body = response.content
            retrieved = clock()
            status = response.status_code
    except (requests.RequestException, KeyboardInterrupt, SystemExit) as error:
        writer.record_failure(
            source="fpl_core", required=required, request_url=url,
            request_started_at=started, commit_sha=commit_sha,
        )
        if not isinstance(error, requests.RequestException):
            raise
        if required:
            raise CoreSourceError(f"Required Core request failed: {filename}") from None
        return "request_failed"

    # Response.content bytes are stored unchanged BEFORE decoding or CSV parsing.
    writer.write_raw(
        f"fpl_core/{commit_sha}/data/{season}/{filename}", body,
        source="fpl_core", required=required, request_started_at=started,
        retrieved_at=retrieved, http_status=status, request_url=url, commit_sha=commit_sha,
    )
    if not 200 <= status < 300:
        if required:
            raise CoreSourceError(f"Required Core file returned HTTP {status}: {filename}")
        return "http_error"
    try:
        # GitHub Raw serves CSV as text/plain; the CSV contract checks the body.
        _validate_csv(filename, body)
    except (UnicodeError, ValueError, csv.Error):
        writer.record_failure(
            source="fpl_core", required=required, request_url=url,
            request_started_at=started, commit_sha=commit_sha,
        )
        if required:
            raise CoreContractError(f"Required Core CSV failed its contract: {filename}") from None
        return "contract_failed"
    return "success"


def fetch_fpl_core_master(
    writer: SnapshotWriter, *, commit_sha: str, season: str = "2026-2027",
    session: requests.Session | None = None, clock: Callable[[], datetime] = _utc_now,
) -> dict[str, str]:
    """Fetch the fixed file set at one explicit commit; return each file's outcome.

    Required failures raise and prevent finalization. Optional failures remain
    visible in both this report and the raw manifest. Never fall back to main,
    another season, file path or commit. HTTP retries are not automatic.
    """
    if not isinstance(writer, SnapshotWriter):
        raise TypeError("fetch_fpl_core_master requires a SnapshotWriter")
    if (
        not isinstance(season, str) or not re.fullmatch(r"[0-9]{4}-[0-9]{4}", season)
        or int(season[5:]) != int(season[:4]) + 1
    ):
        raise ValueError("Expected a consecutive YYYY-YYYY season")
    # Persist the pin before any network call; enforce it across repeated calls
    # using the same writer, not merely within this function invocation.
    sha = writer.pin_source_commit("fpl_core", commit_sha)
    context = requests.Session() if session is None else nullcontext(session)
    with context as client:
        return {
            filename: _fetch_file(
                writer, client, filename, season=season, commit_sha=sha, clock=clock,
            )
            for filename in MASTER_FILES
        }
