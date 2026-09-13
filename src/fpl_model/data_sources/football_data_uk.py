"""Optional upcoming fixtures/odds ingestion, with an immutable record of attempts.

Minimum fixture-identification columns: Div (competition), Date (fixture date),
HomeTeam, AwayTeam. Time and bookmaker columns are not required. No league
filtering, date conversion, odds normalization or dataset construction occurs.

Today's upcoming odds MUST NOT be used as historical pre-deadline odds.
available_at is the local retrieved_at, never a fixture date or page timestamp.

Each complete HTTP response is saved under
raw/football_data_uk/attempt_NN/fixtures.csv before decoding/validation, including
error/redirect bodies. A transport failure has a manifest record but no fake file.
The returned raw_path identifies a usable CSV only when status == "success".
The caller, not this adapter, finalizes the overall snapshot.
"""

import csv
import re
import time
from collections.abc import Callable
from contextlib import nullcontext
from dataclasses import dataclass
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from io import StringIO
from typing import Literal

import requests

from fpl_model.config import FOOTBALL_DATA_UK_FIXTURES
from fpl_model.io import SnapshotWriter


MINIMUM_COLUMNS = frozenset({"Div", "Date", "HomeTeam", "AwayTeam"})
TIMEOUT = (10, 30)  # Connect timeout, then read-inactivity timeout, in seconds.
MAX_ATTEMPTS = 3
BACKOFF_SECONDS = (1.0, 2.0)
MAX_RETRY_DELAY = 30.0
# Only this same-resource canonical-host redirect is allowed, at most once.
CANONICAL_URL = FOOTBALL_DATA_UK_FIXTURES.replace("https://www.", "https://", 1)


@dataclass(frozen=True)
class OddsFetchResult:
    status: Literal["success", "http_error", "request_failed", "contract_failed"]
    raw_path: str | None
    request_count: int


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _validate_csv(body: bytes, content_type: str) -> None:
    """Source shape only; CSV with headers but no rows is valid, unlike an empty body.

    UTF-8 (optional BOM) is attempted first; Windows-1252 accommodates legacy
    exports. Neither decoding changes stored bytes. Unknown columns are retained.
    """
    if not body.strip():
        raise ValueError("Empty response body")
    if content_type.partition(";")[0].strip().lower() in {"text/html", "application/xhtml+xml"}:
        raise ValueError("HTML response instead of CSV")
    try:
        text = body.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = body.decode("cp1252")
    if any(ord(char) < 32 and char not in "\r\n\t" for char in text):
        raise ValueError("Binary control characters in CSV")
    if text.lstrip().startswith("<"):
        raise ValueError("Markup response instead of CSV")
    reader = csv.reader(StringIO(text, newline=""), strict=True)
    header = next(reader, None)
    if (
        not header or any(not column.strip() for column in header)
        or len(set(header)) != len(header) or not MINIMUM_COLUMNS.issubset(header)
    ):
        raise ValueError("Missing, empty or duplicate fixture columns")
    indexes = [header.index(column) for column in MINIMUM_COLUMNS]
    for row in reader:
        if not row:
            continue
        if len(row) != len(header) or any(not row[index].strip() for index in indexes):
            raise ValueError("Invalid fixture row structure")


def _retry_delay(retry_after: str, attempt: int, retrieved_at: datetime) -> float | None:
    """Honor Retry-After without sleeping indefinitely or retrying too early.

    Unparseable values use exponential backoff. A server delay exceeding our
    30-second waiting budget stops the optional fetch, rather than shortening it.
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


def fetch_upcoming_odds(
    writer: SnapshotWriter, *, session: requests.Session | None = None,
    clock: Callable[[], datetime] = _utc_now, sleep: Callable[[float], None] = time.sleep,
) -> OddsFetchResult:
    """Fetch only the configured upcoming feed; report optional failures explicitly.

    Three attempts for 429, 5xx, timeouts or connection errors. One canonical
    redirect may add one GET (four maximum). All GETs disable automatic redirects;
    owned requests sessions have no automatic retries. Injected sessions should
    likewise disable adapter-level retries. Storage errors/interrupts propagate.
    """
    if not isinstance(writer, SnapshotWriter):
        raise TypeError("fetch_upcoming_odds requires a SnapshotWriter")
    context = requests.Session() if session is None else nullcontext(session)
    url = FOOTBALL_DATA_UK_FIXTURES
    redirected = False
    attempt = 0
    request_count = 0
    with context as client:
        while attempt < MAX_ATTEMPTS:
            attempt += 1
            request_count += 1
            started = clock()
            if started.tzinfo is None or started.utcoffset() is None:
                raise ValueError("Request clock must be timezone-aware")
            try:
                with client.get(url, timeout=TIMEOUT, allow_redirects=False) as response:
                    body = response.content
                    retrieved = clock()  # Whole response received; no CSV-derived availability.
                    status = response.status_code
                    content_type = response.headers.get("Content-Type", "")
                    retry_after = response.headers.get("Retry-After", "")
                    location = response.headers.get("Location", "")
            except (requests.RequestException, KeyboardInterrupt, SystemExit) as error:
                error_code = "timeout" if isinstance(error, requests.Timeout) else "transport_error"
                writer.record_failure(
                    source="football_data_uk", required=False, request_url=url,
                    request_started_at=started, error_code=error_code,
                )
                if not isinstance(error, requests.RequestException):
                    raise
                if attempt < MAX_ATTEMPTS and isinstance(
                    error, (requests.Timeout, requests.ConnectionError)
                ):
                    sleep(BACKOFF_SECONDS[attempt - 1])
                    continue
                return OddsFetchResult("request_failed", None, request_count)

            relative = f"football_data_uk/attempt_{request_count:02d}/fixtures.csv"
            raw_path = "raw/" + relative
            writer.write_raw(
                relative, body, source="football_data_uk", required=False, request_url=url,
                request_started_at=started, retrieved_at=retrieved, http_status=status,
                content_type=content_type, available_at=retrieved,
            )
            if (
                status in {301, 302, 303, 307, 308} and not redirected
                and url == FOOTBALL_DATA_UK_FIXTURES and location == CANONICAL_URL
            ):
                redirected = True
                url = CANONICAL_URL
                attempt -= 1  # One redirect is separate from the bounded retry budget.
                continue
            if not 200 <= status < 300:
                writer.record_failure(
                    source="football_data_uk", required=False, request_url=url,
                    request_started_at=started, relative_path=raw_path, error_code="http_error",
                )
                if attempt < MAX_ATTEMPTS and (status == 429 or 500 <= status < 600):
                    delay = _retry_delay(retry_after, attempt, retrieved)
                    if delay is not None:
                        sleep(delay)
                        continue
                return OddsFetchResult("http_error", None, request_count)
            try:
                _validate_csv(body, content_type)
            except (ValueError, csv.Error):
                writer.record_failure(
                    source="football_data_uk", required=False, request_url=url,
                    request_started_at=started, relative_path=raw_path,
                    error_code="invalid_payload",
                )
                return OddsFetchResult("contract_failed", None, request_count)
            return OddsFetchResult("success", raw_path, request_count)
    raise AssertionError("Bounded request loop ended without an outcome")
