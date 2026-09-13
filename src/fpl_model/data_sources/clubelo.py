"""Optional ClubElo raw snapshots for one caller-supplied rating date.

The minimum CSV columns are Club, Country (identity) and Elo (rating). Rank,
Level, From, To and additional columns remain untouched when present. Contract
validation does not establish complete league coverage or publication history.
available_at is retrieved_at, never the requested rating date or From/To fields.

No implicit current date, second-date fallback, club merging or normalization.
Any future nearest-prior-rating fallback belongs in the processed/as-of layer,
with the actual rating date and staleness retained. The caller owns finalization.
"""

import csv
import math
import re
import time
from collections.abc import Callable
from contextlib import nullcontext
from dataclasses import dataclass
from datetime import date, datetime, timezone
from email.utils import parsedate_to_datetime
from io import StringIO
from typing import Literal

import requests

from fpl_model.config import CLUBELO
from fpl_model.io import SnapshotWriter


MINIMUM_COLUMNS = frozenset({"Club", "Country", "Elo"})
TIMEOUT = (10, 30)  # Connect / read-inactivity seconds, not total elapsed time.
MAX_ATTEMPTS = 3
BACKOFF_SECONDS = (1.0, 2.0)
MAX_RETRY_DELAY = 30.0


@dataclass(frozen=True)
class ClubEloFetchResult:
    status: Literal["success", "http_error", "request_failed", "contract_failed"]
    raw_path: str | None  # Only a validated CSV yields a usable path.
    request_count: int


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _validate_csv(body: bytes, content_type: str) -> None:
    """Check shape and finite ratings, without filtering clubs or changing bytes.

    Header-only CSV is structurally valid; coverage must be assessed separately.
    UTF-8 (optional BOM), then Windows-1252 accommodate text export encodings.
    """
    if not body.strip():
        raise ValueError("Empty response body")
    if content_type.partition(";")[0].strip().lower() in {"text/html", "application/xhtml+xml"}:
        raise ValueError("HTML response instead of CSV")
    try:
        text = body.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = body.decode("cp1252")
    if text.lstrip().startswith("<") or any(
        ord(char) < 32 and char not in "\r\n\t" for char in text
    ):
        raise ValueError("Markup or binary response instead of CSV")
    reader = csv.reader(StringIO(text, newline=""), strict=True)
    header = next(reader, None)
    if (
        not header or any(not column.strip() for column in header)
        or len(set(header)) != len(header) or not MINIMUM_COLUMNS.issubset(header)
    ):
        raise ValueError("Missing, empty or duplicate rating columns")
    indexes = [header.index(column) for column in MINIMUM_COLUMNS]
    elo_index = header.index("Elo")
    for row in reader:
        if not row:
            continue
        if len(row) != len(header) or any(not row[index].strip() for index in indexes):
            raise ValueError("Invalid rating row structure")
        if not math.isfinite(float(row[elo_index])):
            raise ValueError("Invalid Elo rating")


def _retry_delay(retry_after: str, attempt: int, retrieved_at: datetime) -> float | None:
    """Honor numeric/date Retry-After; stop rather than truncate delays over 30s."""
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


def fetch_clubelo(
    writer: SnapshotWriter, requested_date: date, *, session: requests.Session | None = None,
    clock: Callable[[], datetime] = _utc_now, sleep: Callable[[float], None] = time.sleep,
) -> ClubEloFetchResult:
    """Fetch exactly the supplied date with at most three attempts, no redirects.

    Only 429/5xx/timeouts/connection errors are retried. Owned sessions have no
    automatic retries; injected sessions must disable hidden retries too. HTTP
    bodies are saved before validation. Transport errors create explicit optional
    records without fake files. Storage failures and interrupts propagate.
    """
    if not isinstance(writer, SnapshotWriter):
        raise TypeError("fetch_clubelo requires a SnapshotWriter")
    if type(requested_date) is not date:
        raise TypeError("requested_date must be an explicit datetime.date, not a datetime or string")
    day = requested_date.isoformat()
    url = f"{CLUBELO}/{day}"
    provenance = {
        "source": "clubelo", "required": False, "request_url": url,
        "request_params": {}, "request_context": {"requested_rating_date": day},
    }
    context = requests.Session() if session is None else nullcontext(session)
    with context as client:
        for attempt in range(1, MAX_ATTEMPTS + 1):
            started = clock()
            if started.tzinfo is None or started.utcoffset() is None:
                raise ValueError("Request clock must be timezone-aware")
            try:
                with client.get(url, timeout=TIMEOUT, allow_redirects=False) as response:
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
                return ClubEloFetchResult("request_failed", None, attempt)

            relative = f"clubelo/{day}/attempt_{attempt:02d}/ratings.csv"
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
                return ClubEloFetchResult("http_error", None, attempt)
            try:
                _validate_csv(body, content_type)
            except (ValueError, csv.Error):
                writer.record_failure(
                    **provenance, request_started_at=started, relative_path=raw_path,
                    error_code="invalid_payload",
                )
                return ClubEloFetchResult("contract_failed", None, attempt)
            return ClubEloFetchResult("success", raw_path, attempt)
    raise AssertionError("Bounded request loop ended without an outcome")
