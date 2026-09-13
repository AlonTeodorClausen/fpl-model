"""Offline ClubElo source contracts; all payloads are synthetic."""

import hashlib
import json
from datetime import date, datetime, timedelta, timezone
from unittest.mock import Mock, call

import pytest
import requests

from fpl_model.data_sources import clubelo as adapter
from fpl_model.io import SnapshotWriter, verify_snapshot


DAY = date(2026, 9, 12)
NOW = datetime(2026, 9, 13, 12, tzinfo=timezone.utc)
BODY = (
    "Rank,Club,Country,Level,Elo,From,To\r\n"
    "1,Example United,ENG,1,1800.25,2026-09-10,2026-09-14\r\n"
    "2,Example Köln,GER,1,1700.5,2026-09-11,2026-09-15\r\n"
).encode()
URL = "http://api.clubelo.com/2026-09-12"


def response(body=BODY, *, status=200, content_type="text/csv", **headers):
    reply = requests.Response()
    reply._content = body
    reply._content_consumed = True
    reply.status_code = status
    if content_type is not None:
        reply.headers["Content-Type"] = content_type
    reply.headers.update(headers)
    reply.close = Mock()
    return reply


def session_for(*responses):
    session = Mock(spec=requests.Session)
    session.get.side_effect = responses
    return session


@pytest.fixture
def writer(tmp_path):
    return SnapshotWriter(tmp_path / "raw", clock=lambda: NOW)


def fetch(writer, session, day=DAY, sleep=None):
    return adapter.fetch_clubelo(writer, day, session=session, clock=lambda: NOW,
                                 sleep=Mock() if sleep is None else sleep)


def manifest(writer):
    return json.loads((writer.staging_path / "manifest.json").read_bytes())


def baseline(writer):
    writer.write_raw("baseline.json", b"{}", source="baseline", required=True,
                     request_started_at=NOW, retrieved_at=NOW)


def test_success_preserves_exact_bytes_before_validation_and_provenance(writer, monkeypatch):
    body = b"\xef\xbb\xbf" + BODY
    reply = response(body, content_type="text/csv; charset=utf-8")
    session = session_for(reply)
    original = adapter._validate_csv
    checked = []

    def validate_after_storage(raw, content_type):
        entry = manifest(writer)["files"][0]
        assert (writer.staging_path / entry["relative_path"]).read_bytes() == raw
        checked.append(True)
        original(raw, content_type)

    monkeypatch.setattr(adapter, "_validate_csv", validate_after_storage)
    result = fetch(writer, session)
    assert result == adapter.ClubEloFetchResult(
        "success", "raw/clubelo/2026-09-12/attempt_01/ratings.csv", 1,
    )
    assert checked == [True]
    assert not writer.final_path.exists() and manifest(writer)["status"] == "staging"
    session.get.assert_called_once_with(URL, timeout=(10, 30), allow_redirects=False)
    final = writer.finalize()
    data = verify_snapshot(final)
    assert data["failures"] == []
    assert data["files"] == [{
        "source": "clubelo", "required": False, "request_url": URL,
        "request_params": {}, "request_context": {"requested_rating_date": "2026-09-12"},
        "request_started_at": NOW.isoformat(timespec="microseconds"),
        "retrieved_at": NOW.isoformat(timespec="microseconds"),
        "available_at": NOW.isoformat(timespec="microseconds"),
        "http_status": 200, "content_type": "text/csv; charset=utf-8", "outcome": "success",
        "relative_path": result.raw_path, "sha256": hashlib.sha256(body).hexdigest(),
        "size_bytes": len(body),
    }]
    assert (final / result.raw_path).read_bytes() == body
    reply.close.assert_called_once()
    session.close.assert_not_called()


@pytest.mark.parametrize("body,content_type", [
    (b"", "text/csv"), (b" \r\n", "text/csv"),
    (b"<html>unavailable</html>", "text/csv"),
    (BODY, "text/html; charset=utf-8"), (BODY, "application/xhtml+xml"),
    (b'Club,Country,Elo\n"unclosed', "text/csv"),
    (b"Club,Country,Elo\nExample,ENG\n", "text/csv"),
    (b"Club,Country,Elo\nExample,ENG,1800,extra\n", "text/csv"),
    (b"Club,Country,Elo\n,ENG,1800\n", "text/csv"),
    (b"Club,Country,Elo\nExample,ENG,not-a-rating\n", "text/csv"),
    (b"Club,Country,Elo\nExample,ENG,NaN\n", "text/csv"),
    (b"Club,Country,Elo\nExample,ENG,Infinity\n", "text/csv"),
    (b"Club,Country,Elo,Elo\n", "text/csv"),
    (b"Club,Country,Elo,\n", "text/csv"),
    (b"Club,Country,Elo\nExam\x00ple,ENG,1800\n", "text/csv"),
])
def test_invalid_payload_is_preserved_as_explicit_optional_failure(writer, body, content_type):
    baseline(writer)
    session = session_for(response(body, content_type=content_type))
    result = fetch(writer, session)
    assert result == adapter.ClubEloFetchResult("contract_failed", None, 1)
    session.get.assert_called_once_with(URL, timeout=(10, 30), allow_redirects=False)
    data = verify_snapshot(writer.finalize())
    entry, failure = data["files"][-1], data["failures"][0]
    assert (writer.final_path / entry["relative_path"]).read_bytes() == body
    assert failure["required"] is False and failure["error_code"] == "invalid_payload"
    assert failure["relative_path"] == entry["relative_path"]
    assert failure["request_context"] == {"requested_rating_date": DAY.isoformat()}


@pytest.mark.parametrize("missing", ["Club", "Country", "Elo"])
def test_missing_minimum_columns_rejected(writer, missing):
    columns = [c for c in ("Club", "Country", "Elo") if c != missing]
    body = (",".join(columns) + "\n").encode()
    assert fetch(writer, session_for(response(body))).status == "contract_failed"


@pytest.mark.parametrize("body", [
    b"Club,Country,Elo\n",  # Structural validity does not establish date coverage.
    b"Club,Country,Elo,FutureField\nExample,ENG,1500,new\n",
    b'Club,Country,Elo\n"Example, FC",ENG,1500\n',
    BODY.decode().encode("cp1252"),
])
def test_unknown_columns_minimal_schema_and_legacy_encoding_tolerated(writer, body):
    result = fetch(writer, session_for(response(body)))
    assert result.status == "success"
    assert (writer.staging_path / result.raw_path).read_bytes() == body


@pytest.mark.parametrize("content_type", [None, "text/plain", "application/octet-stream"])
def test_csv_validation_does_not_depend_on_one_mime_type(writer, content_type):
    assert fetch(writer, session_for(response(content_type=content_type))).status == "success"
    assert manifest(writer)["files"][0]["content_type"] == (content_type or "")


@pytest.mark.parametrize("body", [BODY, b"Club,Country,Elo\nOnly One Club,ENG,1500\n"])
def test_partial_club_coverage_does_not_trigger_21_day_fallback(writer, body):
    session = session_for(response(body))
    assert fetch(writer, session).status == "success"
    session.get.assert_called_once_with(URL, timeout=(10, 30), allow_redirects=False)
    assert len(manifest(writer)["files"]) == 1


@pytest.mark.parametrize("status", [301, 302, 403, 404])
def test_http_errors_and_redirects_do_not_trigger_another_date_or_endpoint(writer, status):
    session = session_for(response(b"unavailable", status=status,
                                   Location="http://api.clubelo.com/2026-08-22"))
    sleep = Mock()
    assert fetch(writer, session, sleep=sleep).status == "http_error"
    session.get.assert_called_once_with(URL, timeout=(10, 30), allow_redirects=False)
    sleep.assert_not_called()
    data = verify_snapshot(writer.finalize())
    assert data["files"][0]["http_status"] == status
    assert data["failures"][0]["error_code"] == "http_error"


@pytest.mark.parametrize("status", [429, 500, 503, 599])
def test_transient_retry_success_keeps_same_date_and_all_bytes(writer, status):
    session = session_for(response(b"busy", status=status), response())
    sleep = Mock()
    result = fetch(writer, session, sleep=sleep)
    assert result == adapter.ClubEloFetchResult(
        "success", "raw/clubelo/2026-09-12/attempt_02/ratings.csv", 2,
    )
    assert session.get.call_args_list == [call(URL, timeout=(10, 30), allow_redirects=False)] * 2
    sleep.assert_called_once_with(1.0)
    data = verify_snapshot(writer.finalize())
    assert [e["http_status"] for e in data["files"]] == [status, 200]
    assert (writer.final_path / data["files"][0]["relative_path"]).read_bytes() == b"busy"
    assert data["failures"][0]["required"] is False


@pytest.mark.parametrize("status", [429, 500, 503])
def test_http_retries_are_bounded(writer, status):
    session = session_for(*(response(b"busy", status=status) for _ in range(3)))
    sleep = Mock()
    assert fetch(writer, session, sleep=sleep) == adapter.ClubEloFetchResult("http_error", None, 3)
    assert sleep.call_args_list == [call(1.0), call(2.0)] and session.get.call_count == 3
    data = verify_snapshot(writer.finalize())
    assert len(data["files"]) == len(data["failures"]) == 3


@pytest.mark.parametrize("retry_after,delay", [
    ("7", 7.0), ("30", 30.0), ("31", None), ("invalid", 1.0), ("0", 1.0),
    ("Sun, 13 Sep 2026 12:00:10 GMT", 10.0),
    ("Sun, 13 Sep 2026 12:01:00 GMT", None),
])
def test_retry_after_is_respected_with_bounded_wait(writer, retry_after, delay):
    session = session_for(response(status=429, **{"Retry-After": retry_after}), response())
    sleep = Mock()
    result = fetch(writer, session, sleep=sleep)
    if delay is None:
        assert result.status == "http_error" and result.request_count == 1
        sleep.assert_not_called()
    else:
        assert result.status == "success" and result.request_count == 2
        sleep.assert_called_once_with(delay)


@pytest.mark.parametrize("error,count", [
    (requests.Timeout, 3), (requests.ConnectionError, 3), (requests.RequestException, 1),
])
def test_transport_failure_is_optional_without_fake_files_or_exception_text(
    writer, error, count, caplog, capsys
):
    session = session_for(*(error("PRIVATE_EXCEPTION_TEXT") for _ in range(3)))
    sleep = Mock()
    assert fetch(writer, session, sleep=sleep) == adapter.ClubEloFetchResult("request_failed", None, count)
    data = manifest(writer)
    assert data["files"] == [] and len(data["failures"]) == count
    assert sleep.call_count == count - 1
    assert "PRIVATE_EXCEPTION_TEXT" not in json.dumps(data) + caplog.text + str(capsys.readouterr())
    baseline(writer)
    verify_snapshot(writer.finalize())


def test_transport_retry_then_success_retains_attempt_number(writer):
    result = fetch(writer, session_for(requests.Timeout(), response()))
    assert result.raw_path == "raw/clubelo/2026-09-12/attempt_02/ratings.csv"
    data = verify_snapshot(writer.finalize())
    assert len(data["files"]) == len(data["failures"]) == 1


def test_explicit_multiple_dates_are_separate_and_never_combined(writer):
    session = session_for(response(), response())
    first = fetch(writer, session)
    second = fetch(writer, session, date(2026, 8, 22))
    assert first.raw_path != second.raw_path
    assert [c.args[0] for c in session.get.call_args_list] == [URL, "http://api.clubelo.com/2026-08-22"]
    assert len(verify_snapshot(writer.finalize())["files"]) == 2


@pytest.mark.parametrize("invalid_date", [None, "2026-09-12", NOW, 42])
def test_date_must_be_explicit_date_type(writer, invalid_date):
    session = session_for()
    with pytest.raises(TypeError, match="explicit datetime.date"):
        fetch(writer, session, invalid_date)
    session.get.assert_not_called()


def test_no_default_date_or_legacy_path_api(writer, tmp_path):
    session = session_for()
    with pytest.raises(TypeError):
        adapter.fetch_clubelo(writer, session=session)
    with pytest.raises(TypeError, match="SnapshotWriter"):
        fetch(tmp_path, session)
    session.get.assert_not_called()


def test_availability_comes_from_retrieval_not_rating_date_or_from_to(tmp_path):
    ticks = iter(NOW + timedelta(seconds=i) for i in range(4))
    clock = lambda: next(ticks)
    writer = SnapshotWriter(tmp_path, clock=clock)
    adapter.fetch_clubelo(writer, DAY, session=session_for(response()), clock=clock)
    entry = verify_snapshot(writer.finalize())["files"][0]
    assert entry["request_started_at"] == "2026-09-13T12:00:01.000000+00:00"
    assert entry["available_at"] == entry["retrieved_at"] == "2026-09-13T12:00:02.000000+00:00"
    assert entry["request_context"]["requested_rating_date"] == "2026-09-12"


def test_storage_failure_and_interrupts_propagate(writer, monkeypatch):
    monkeypatch.setattr(writer, "write_raw", Mock(side_effect=OSError("disk full")))
    with pytest.raises(OSError, match="disk full"):
        fetch(writer, session_for(response()))
    with pytest.raises(KeyboardInterrupt):
        fetch(writer, session_for(KeyboardInterrupt()))
    assert not writer.final_path.exists()
