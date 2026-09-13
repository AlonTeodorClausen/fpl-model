"""Required ingestion for the two existing official FPL endpoints.

Usage: writer = SnapshotWriter(raw_root); fetch_fpl_snapshot(writer);
writer.finalize(). The legacy multi-source script is not migrated here.
Response.content bytes (HTTP transfer/content decoding handled by requests) are
stored before JSON parsing. No response.text/json reserialization is performed.
"""

import json
from collections.abc import Callable
from contextlib import nullcontext
from datetime import datetime, timezone

import requests

from fpl_model.config import FPL_BOOTSTRAP, FPL_FIXTURES
from fpl_model.io import SnapshotWriter


class FPLSourceError(RuntimeError):
    """Required FPL request failed; detailed response bytes remain in staging."""


class FPLContractError(FPLSourceError):
    """The response does not satisfy the minimal ingestion contract."""


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _rows(value: object) -> list[dict]:
    if not isinstance(value, list) or not all(isinstance(row, dict) for row in value):
        raise ValueError("Expected a list of objects")
    return value


def _id(value: object) -> None:
    if type(value) is not int or value <= 0:
        raise ValueError("Expected a positive integer ID")


def _time(value: object, *, nullable: bool = False) -> None:
    if value is None and nullable:
        return
    if not isinstance(value, str):
        raise ValueError("Expected an ISO timestamp")
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("Expected a timezone-aware timestamp")


def _validate_payload(filename: str, payload: object) -> None:
    """Check structure and a few core fields; tolerate new fields and empty fixtures.

    These are source contracts, not canonical schemas or cross-table joins.
    """
    if filename == "bootstrap_static.json":
        if not isinstance(payload, dict):
            raise ValueError("Expected a bootstrap object")
        for key in ("elements", "teams", "events", "element_types"):
            for row in _rows(payload[key]):
                _id(row["id"])
                if key == "elements":
                    _id(row["team"])
                    _id(row["element_type"])
                elif key == "events":
                    _time(row["deadline_time"])
    else:
        for row in _rows(payload):
            for field in ("id", "team_h", "team_a"):
                _id(row[field])
            if row["event"] is not None:
                _id(row["event"])
            _time(row["kickoff_time"], nullable=True)
            if type(row["finished"]) is not bool:
                raise ValueError("Expected a boolean finished flag")


def _fetch_endpoint(
    writer: SnapshotWriter, session: requests.Session, filename: str, url: str,
    clock: Callable[[], datetime],
) -> None:
    started = clock()
    if started.tzinfo is None or started.utcoffset() is None:
        raise ValueError("Request clock must be timezone-aware")
    try:
        # No redirects or automatic retries: both can obscure which request was
        # actually observed. A failed required request needs a new snapshot run.
        with session.get(url, timeout=(10, 30), allow_redirects=False) as response:
            body = response.content
            retrieved = clock()  # Only after the whole response body is available.
            status = response.status_code
            content_type = response.headers.get("Content-Type", "")
    except (requests.RequestException, KeyboardInterrupt, SystemExit) as error:
        writer.record_failure(
            source="fpl_api", required=True, request_url=url, request_started_at=started,
        )
        if not isinstance(error, requests.RequestException):
            raise
        # Never include request/exception text, URLs from errors, or credentials.
        raise FPLSourceError("Required FPL transport request failed") from None

    writer.write_raw(
        f"fpl_api/{filename}", body, source="fpl_api", required=True,
        request_started_at=started, retrieved_at=retrieved, http_status=status,
        request_url=url,
    )
    if not 200 <= status < 300:
        # write_raw already records this as a required HTTP failure.
        raise FPLSourceError(f"Required FPL endpoint returned HTTP {status}")
    try:
        media_type = content_type.partition(";")[0].strip().lower()
        if media_type != "application/json":
            raise ValueError("Expected application/json")
        payload = json.loads(body)
        _validate_payload(filename, payload)
    except (ValueError, TypeError, KeyError):
        # A 200 response with invalid content must not be eligible for completion.
        writer.record_failure(
            source="fpl_api", required=True, request_url=url, request_started_at=started,
        )
        raise FPLContractError("Required FPL response failed its source contract") from None


def fetch_fpl_snapshot(
    writer: SnapshotWriter, *, session: requests.Session | None = None,
    clock: Callable[[], datetime] = _utc_now,
) -> None:
    """Write and validate bootstrap-static and fixtures; caller finalizes the run.

    Use a new writer per run. A caller-supplied session remains caller-owned.
    Normal tests inject a session; production uses a short-lived requests Session.
    """
    if not isinstance(writer, SnapshotWriter):
        raise TypeError("fetch_fpl_snapshot requires a SnapshotWriter")
    context = requests.Session() if session is None else nullcontext(session)
    with context as client:
        for filename, url in (
            ("bootstrap_static.json", FPL_BOOTSTRAP),
            ("fixtures.json", FPL_FIXTURES),
        ):
            _fetch_endpoint(writer, client, filename, url, clock)
