"""Optional PL/CL match responses from football-data.org v4.

Store original response.content bytes before JSON contract validation. No dataset
parsing, field normalization or player-minutes inference: schedules/results do
not establish participation. available_at is retrieved_at, never utcDate or
lastUpdated. With no query filters, the provider determines the response period;
this is recorded as request_params={} rather than inventing season/date bounds.

The caller supplies a SnapshotWriter and finalizes it. Credentials are read only
from FOOTBALL_DATA_ORG_TOKEN, sent only as X-Auth-Token, and never logged or put
in provenance. Automatic redirects are disabled to avoid forwarding credentials.
"""

import json
import os
import re
import time
from collections.abc import Callable
from contextlib import nullcontext
from dataclasses import dataclass
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Literal

import requests

from fpl_model.config import FOOTBALL_DATA_ORG
from fpl_model.io import SnapshotWriter


COMPETITIONS = ("PL", "CL")
TIMEOUT = (10, 30)  # Connect / read-inactivity seconds, not total elapsed time.
MAX_ATTEMPTS = 3
BACKOFF_SECONDS = (1.0, 2.0)
MAX_RETRY_DELAY = 30.0


@dataclass(frozen=True)
class MatchesFetchResult:
    status: Literal["success", "skipped", "http_error", "request_failed", "contract_failed"]
    raw_path: str | None  # Only successful contract validation yields a usable path.
    request_count: int


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _reject_nonfinite(value: str) -> None:
    raise ValueError("Non-finite numbers are not JSON")


def _validate_json(body: bytes, content_type: str, code: str) -> None:
    """Validate the matches envelope only; tolerate unknown and absent detail fields.

    An empty matches list is valid. Identity codes are checked at both envelope
    and match level when present; missing/null identity is not invented.
    """
    if not body.strip():
        raise ValueError("Empty response body")
    if content_type.partition(";")[0].strip().lower() in {"text/html", "application/xhtml+xml"}:
        raise ValueError("HTML response instead of JSON")
    payload = json.loads(body, parse_constant=_reject_nonfinite)
    if (
        not isinstance(payload, dict) or not isinstance(payload.get("matches"), list)
        or "error" in payload or "errorCode" in payload
    ):
        raise ValueError("Expected matches response")
    for item in [payload, *payload["matches"]]:
        if not isinstance(item, dict):
            raise ValueError("Expected match objects")
        competition = item.get("competition")
        if competition is not None:
            if not isinstance(competition, dict):
                raise ValueError("Invalid competition identity")
            actual_code = competition.get("code")
            if actual_code is not None and actual_code != code:
                raise ValueError("Unexpected competition identity")


def _retry_delay(retry_after: str, attempt: int, retrieved_at: datetime) -> float | None:
    """Honor numeric/date Retry-After; stop if it exceeds the 30-second budget.

    Invalid/missing headers use 1s/2s backoff. Do not cap a longer server-requested
    delay and then retry prematurely. This matches the immutable attempt policy.
    """
    fallback = BACKOFF_SECONDS[attempt - 1]
    value = retry_after.strip()
    try:
        if re.fullmatch(r"[0-9]+", value):
            delay = float(value)
        elif value:
            resume_at = parsedate_to_datetime(value)
            if resume_at.tzinfo is None:
                resume_at = resume_at.replace(tzinfo=timezone.utc)
            delay = max(0.0, (resume_at - retrieved_at).total_seconds())
        else:
            return fallback
    except (TypeError, ValueError, OverflowError):
        return fallback
    return None if delay > MAX_RETRY_DELAY else max(fallback, delay)


def fetch_competition_matches(
    code: str, writer: SnapshotWriter, *, session: requests.Session | None = None,
    clock: Callable[[], datetime] = _utc_now, sleep: Callable[[float], None] = time.sleep,
) -> MatchesFetchResult:
    """Fetch only PL or CL; explicitly record optional skips and failed attempts.

    At most three GETs for 429/5xx/timeouts/connection errors. Owned sessions have
    no automatic retries; injected sessions must likewise disable hidden retries.
    Storage failures and interrupts propagate. No fallback endpoints are used.
    """
    if not isinstance(writer, SnapshotWriter):
        raise TypeError("fetch_competition_matches requires a SnapshotWriter")
    if code not in COMPETITIONS:
        raise ValueError("Only PL and CL matches are supported")
    url = f"{FOOTBALL_DATA_ORG}/competitions/{code}/matches"
    provenance = {
        "source": "football_data_org", "required": False, "request_url": url,
        "request_params": {}, "request_context": {"competition_code": code},
    }
    token = os.getenv("FOOTBALL_DATA_ORG_TOKEN", "").strip()
    if not token:
        writer.record_failure(**provenance, outcome="skipped", error_code="missing_token")
        return MatchesFetchResult("skipped", None, 0)

    context = requests.Session() if session is None else nullcontext(session)
    with context as client:
        for attempt in range(1, MAX_ATTEMPTS + 1):
            started = clock()
            if started.tzinfo is None or started.utcoffset() is None:
                raise ValueError("Request clock must be timezone-aware")
            try:
                with client.get(
                    url, params={}, headers={"X-Auth-Token": token},
                    timeout=TIMEOUT, allow_redirects=False,
                ) as response:
                    body = response.content
                    retrieved = clock()
                    status = response.status_code
                    content_type = response.headers.get("Content-Type", "")
                    retry_after = response.headers.get("Retry-After", "")
            except (requests.RequestException, KeyboardInterrupt, SystemExit) as error:
                writer.record_failure(
                    **provenance, request_started_at=started,
                    error_code="timeout" if isinstance(error, requests.Timeout) else "transport_error",
                )
                if not isinstance(error, requests.RequestException):
                    raise
                if attempt < MAX_ATTEMPTS and isinstance(
                    error, (requests.Timeout, requests.ConnectionError)
                ):
                    sleep(BACKOFF_SECONDS[attempt - 1])
                    continue
                return MatchesFetchResult("request_failed", None, attempt)

            relative = f"football_data_org/{code}/attempt_{attempt:02d}/matches.json"
            raw_path = "raw/" + relative
            writer.write_raw(
                relative, body, **provenance, request_started_at=started,
                retrieved_at=retrieved, http_status=status, content_type=content_type,
                available_at=retrieved,
            )
            if not 200 <= status < 300:
                writer.record_failure(
                    **provenance, request_started_at=started, relative_path=raw_path,
                    error_code="http_error",
                )
                if attempt < MAX_ATTEMPTS and (status == 429 or 500 <= status < 600):
                    delay = _retry_delay(retry_after, attempt, retrieved)
                    if delay is not None:
                        sleep(delay)
                        continue
                return MatchesFetchResult("http_error", None, attempt)
            try:
                _validate_json(body, content_type, code)
            except (ValueError, UnicodeError):
                writer.record_failure(
                    **provenance, request_started_at=started, relative_path=raw_path,
                    error_code="invalid_payload",
                )
                return MatchesFetchResult("contract_failed", None, attempt)
            return MatchesFetchResult("success", raw_path, attempt)
    raise AssertionError("Bounded request loop ended without an outcome")
