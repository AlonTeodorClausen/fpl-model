"""Offline source contracts for the optional upcoming feed; fixture data is synthetic."""

import hashlib
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import Mock, call

import pytest
import requests

from fpl_model.config import FOOTBALL_DATA_UK_FIXTURES
from fpl_model.data_sources import football_data_uk as adapter
from fpl_model.io import SnapshotIntegrityError, SnapshotWriter, verify_snapshot


NOW = datetime(2026, 9, 13, 10, tzinfo=timezone.utc)
BODY = (Path(__file__).parent / "fixtures/football_data_uk/fixtures.csv").read_bytes()


def response(body=BODY, *, status=200, content_type="text/csv; charset=utf-8", **headers):
    result = requests.Response()
    result._content = body
    result._content_consumed = True
    result.status_code = status
    if content_type is not None:
        result.headers["Content-Type"] = content_type
    result.headers.update(headers)
    result.close = Mock()
    return result


def session_for(*responses):
    session = Mock(spec=requests.Session)
    session.get.side_effect = responses
    return session


@pytest.fixture
def writer(tmp_path):
    return SnapshotWriter(tmp_path / "raw", clock=lambda: NOW)


def fetch(writer, session, *, sleep=None):
    return adapter.fetch_upcoming_odds(
        writer, session=session, clock=lambda: NOW, sleep=Mock() if sleep is None else sleep,
    )


def manifest(writer):
    return json.loads((writer.staging_path / "manifest.json").read_bytes())


def add_required_baseline(writer):
    writer.write_raw("baseline.json", b"{}", source="baseline", required=True,
                     request_started_at=NOW, retrieved_at=NOW)


def test_configured_download_url_and_canonical_redirect_are_explicit(writer):
    assert FOOTBALL_DATA_UK_FIXTURES == "https://www.football-data.co.uk/fixtures.csv"
    assert adapter.CANONICAL_URL == "https://football-data.co.uk/fixtures.csv"
    session = session_for(
        response(b"", status=302, Location="https://football-data.co.uk/fixtures.csv"),
        response(),
    )
    assert fetch(writer, session).status == "success"
    expected_urls = [
        "https://www.football-data.co.uk/fixtures.csv",
        "https://football-data.co.uk/fixtures.csv",
    ]
    assert [c.args[0] for c in session.get.call_args_list] == expected_urls
    assert [entry["request_url"] for entry in manifest(writer)["files"]] == expected_urls


@pytest.mark.parametrize("status,content_type,expected", [
    (404, "text/html", "http_error"),
    (200, "text/html", "contract_failed"),
])
def test_new_url_failure_does_not_fall_back_to_old_feed_or_scraping(
    writer, status, content_type, expected
):
    session = session_for(response(b"<html>download page</html>", status=status,
                                   content_type=content_type))
    assert fetch(writer, session).status == expected
    session.get.assert_called_once_with(
        "https://www.football-data.co.uk/fixtures.csv",
        timeout=(10, 30), allow_redirects=False,
    )
    assert manifest(writer)["failures"][-1]["required"] is False


def test_success_preserves_bytes_before_parse_and_records_complete_provenance(writer, monkeypatch):
    body = b"\xef\xbb\xbf" + BODY.replace(b"\n", b"\r\n")
    reply = response(body)
    session = session_for(reply)
    original = adapter._validate_csv
    checked = []

    def after_storage(payload, content_type):
        entry = manifest(writer)["files"][0]
        assert (writer.staging_path / entry["relative_path"]).read_bytes() == payload
        assert entry["sha256"] == hashlib.sha256(payload).hexdigest()
        checked.append(True)
        original(payload, content_type)

    monkeypatch.setattr(adapter, "_validate_csv", after_storage)
    result = fetch(writer, session)
    assert checked == [True]
    assert result == adapter.OddsFetchResult(
        "success", "raw/football_data_uk/attempt_01/fixtures.csv", 1
    )
    assert not writer.final_path.exists()  # Caller still owns finalization.
    assert manifest(writer)["status"] == "staging"
    final = writer.finalize()
    data = verify_snapshot(final)
    assert data["files"] == [{
        "source": "football_data_uk", "request_url": FOOTBALL_DATA_UK_FIXTURES,
        "request_started_at": "2026-09-13T10:00:00.000000+00:00",
        "retrieved_at": "2026-09-13T10:00:00.000000+00:00",
        "available_at": "2026-09-13T10:00:00.000000+00:00",
        "relative_path": result.raw_path, "required": False,
        "content_type": "text/csv; charset=utf-8", "http_status": 200, "outcome": "success",
        "sha256": hashlib.sha256(body).hexdigest(), "size_bytes": len(body),
    }]
    assert (final / result.raw_path).read_bytes() == body
    assert b"D1," in body and b"E0," in body  # All leagues remain in the same raw response.
    session.get.assert_called_once_with(
        FOOTBALL_DATA_UK_FIXTURES, timeout=(10, 30), allow_redirects=False
    )
    session.close.assert_not_called()
    reply.close.assert_called_once()


def test_observation_time_is_retrieval_time_not_fixture_date(tmp_path):
    ticks = iter(NOW + timedelta(seconds=index) for index in range(4))

    def clock():
        return next(ticks)

    writer = SnapshotWriter(tmp_path, clock=clock)
    result = adapter.fetch_upcoming_odds(writer, session=session_for(response()), clock=clock)
    entry = verify_snapshot(writer.finalize())["files"][0]
    assert result.status == "success"
    assert entry["request_started_at"] == "2026-09-13T10:00:01.000000+00:00"
    assert entry["retrieved_at"] == entry["available_at"] == "2026-09-13T10:00:02.000000+00:00"


@pytest.mark.parametrize("body,content_type", [
    (b"", "text/csv"), (b" \r\n", "text/plain"),
    (b"<!doctype html><html>upstream error</html>", "text/html; charset=UTF-8"),
    (b"<html>upstream error</html>", "text/csv"),
    (BODY, "text/html"),
    (b"Div,Date,HomeTeam,AwayTeam\nE0,14/09/2026,Home\n", "text/csv"),
    (b'Div,Date,HomeTeam,AwayTeam\nE0,14/09/2026,"unclosed', "text/csv"),
    (b"Div,Date,HomeTeam,AwayTeam\nE0,14/09/2026,Home,Away,extra\n", "text/csv"),
    (b"Div,Date,HomeTeam,AwayTeam\nE0,14/09/2026,Home,\n", "text/csv"),
    (b"Div,Date,HomeTeam,AwayTeam,Div\n", "text/csv"),
    (b"Div,Date,HomeTeam,AwayTeam\nE0,14/09/2026,\x00,Away\n", "text/csv"),
])
def test_invalid_payload_is_stored_and_explicitly_optional_not_an_empty_dataset(
    writer, body, content_type
):
    add_required_baseline(writer)
    session = session_for(response(body, content_type=content_type))
    sleep = Mock()
    result = fetch(writer, session, sleep=sleep)
    assert result.status == "contract_failed" and result.raw_path is None
    sleep.assert_not_called()
    session.get.assert_called_once()
    data = verify_snapshot(writer.finalize())  # Optional failure does not block the baseline.
    entry = data["files"][-1]
    assert (writer.final_path / entry["relative_path"]).read_bytes() == body
    assert entry["required"] is False and entry["http_status"] == 200
    failure = data["failures"][-1]
    assert failure["required"] is False and failure["error_code"] == "invalid_payload"
    assert failure["relative_path"] == entry["relative_path"]


@pytest.mark.parametrize("missing", ["Div", "Date", "HomeTeam", "AwayTeam"])
def test_minimum_columns_are_required(writer, missing):
    columns = [name for name in ("Div", "Date", "HomeTeam", "AwayTeam") if name != missing]
    result = fetch(writer, session_for(response((",".join(columns) + "\n").encode())))
    assert result.status == "contract_failed"


@pytest.mark.parametrize("body", [
    b"Div,Date,HomeTeam,AwayTeam\n",  # Header-only feed is different from an empty response.
    b"Div,Date,HomeTeam,AwayTeam\nE0,14/09/2026,Home,Away\n",  # No odds or Time needed.
    b'Div,Date,HomeTeam,AwayTeam,NewBook\nD1,14/09/26,"Home, FC",Away,"new\nvalue"\n',
    BODY.decode("utf-8").encode("cp1252"),
])
def test_unknown_columns_header_only_feeds_and_legacy_encoding_are_tolerated(writer, body):
    result = fetch(writer, session_for(response(body, content_type="text/plain")))
    assert result.status == "success"
    assert (writer.staging_path / result.raw_path).read_bytes() == body


def test_absent_content_type_is_explicitly_recorded_as_unknown(writer):
    result = fetch(writer, session_for(response(content_type=None)))
    assert result.status == "success"
    assert manifest(writer)["files"][0]["content_type"] == ""


@pytest.mark.parametrize("status", [429, 500, 502, 503, 599])
def test_transient_http_error_then_success_preserves_both_attempts(writer, status):
    session = session_for(response(b"busy", status=status), response())
    sleep = Mock()
    result = fetch(writer, session, sleep=sleep)
    assert result == adapter.OddsFetchResult(
        "success", "raw/football_data_uk/attempt_02/fixtures.csv", 2
    )
    sleep.assert_called_once_with(1.0)
    data = verify_snapshot(writer.finalize())
    assert [entry["http_status"] for entry in data["files"]] == [status, 200]
    assert len({entry["relative_path"] for entry in data["files"]}) == 2
    assert (writer.final_path / data["files"][0]["relative_path"]).read_bytes() == b"busy"
    assert data["failures"][0]["relative_path"] == data["files"][0]["relative_path"]


@pytest.mark.parametrize("status", [429, 500, 503])
def test_retries_are_bounded_and_all_exhausted_errors_remain_optional(writer, status):
    session = session_for(*(response(f"error {n}".encode(), status=status) for n in range(3)))
    sleep = Mock()
    result = fetch(writer, session, sleep=sleep)
    assert result == adapter.OddsFetchResult("http_error", None, 3)
    assert sleep.call_args_list == [call(1.0), call(2.0)]
    assert session.get.call_count == 3
    data = verify_snapshot(writer.finalize())
    assert len(data["files"]) == len(data["failures"]) == 3
    assert all(entry["required"] is False for entry in data["files"] + data["failures"])


@pytest.mark.parametrize("status", [301, 304, 400, 403, 404])
def test_nontransient_statuses_are_not_retried(writer, status):
    session = session_for(response(b"unavailable", status=status))
    sleep = Mock()
    result = fetch(writer, session, sleep=sleep)
    assert result.status == "http_error" and result.request_count == 1
    sleep.assert_not_called()


@pytest.mark.parametrize("retry_after,delay", [
    ("4", 4.0), ("Sun, 13 Sep 2026 10:00:03 GMT", 3.0), ("nonsense", 1.0), ("0", 1.0),
])
def test_retry_after_is_respected_with_bounded_fallback(writer, retry_after, delay):
    session = session_for(response(b"busy", status=429, **{"Retry-After": retry_after}), response())
    sleep = Mock()
    assert fetch(writer, session, sleep=sleep).status == "success"
    sleep.assert_called_once_with(delay)


def test_retry_after_exceeding_budget_stops_without_retrying_early(writer):
    session = session_for(response(b"busy", status=429, **{"Retry-After": "3600"}))
    sleep = Mock()
    assert fetch(writer, session, sleep=sleep).status == "http_error"
    sleep.assert_not_called()
    session.get.assert_called_once()


@pytest.mark.parametrize("exception", [requests.Timeout, requests.ConnectionError])
def test_transport_retries_do_not_create_fake_empty_csvs_or_leak_exception_text(
    writer, exception, capsys, caplog
):
    add_required_baseline(writer)
    session = session_for(*(exception("token=SECRET") for _ in range(3)))
    sleep = Mock()
    result = fetch(writer, session, sleep=sleep)
    assert result == adapter.OddsFetchResult("request_failed", None, 3)
    assert sleep.call_args_list == [call(1.0), call(2.0)]
    data = verify_snapshot(writer.finalize())
    assert len(data["files"]) == 1  # Only the independent baseline payload.
    assert len(data["failures"]) == 3
    assert all("relative_path" not in failure for failure in data["failures"])
    assert "SECRET" not in json.dumps(data)
    assert capsys.readouterr() == ("", "") and not caplog.records


def test_transport_failure_then_success_keeps_attempt_number_and_failure_record(writer):
    result = fetch(writer, session_for(requests.Timeout(), response()))
    assert result.status == "success" and result.request_count == 2
    assert result.raw_path == "raw/football_data_uk/attempt_02/fixtures.csv"
    data = verify_snapshot(writer.finalize())
    assert len(data["files"]) == len(data["failures"]) == 1
    assert data["failures"][0]["error_code"] == "timeout"


def test_other_request_exceptions_are_not_retried(writer):
    session = session_for(requests.RequestException("bad request"))
    sleep = Mock()
    assert fetch(writer, session, sleep=sleep).status == "request_failed"
    sleep.assert_not_called()


@pytest.mark.parametrize("exception", [KeyboardInterrupt, SystemExit])
def test_interruptions_propagate_and_are_recorded(writer, exception):
    with pytest.raises(exception):
        fetch(writer, session_for(exception()))
    assert not writer.final_path.exists()
    assert manifest(writer)["failures"][0]["required"] is False


def test_only_one_canonical_redirect_is_allowed_and_recorded(writer):
    session = session_for(
        response(b"", status=302, content_type="text/html", Location=adapter.CANONICAL_URL),
        response(b"busy", status=429), response(b"busy again", status=503), response(),
    )
    sleep = Mock()
    result = fetch(writer, session, sleep=sleep)
    assert result.status == "success" and result.request_count == 4
    assert result.raw_path == "raw/football_data_uk/attempt_04/fixtures.csv"
    assert [c.args[0] for c in session.get.call_args_list] == [
        FOOTBALL_DATA_UK_FIXTURES,
        adapter.CANONICAL_URL, adapter.CANONICAL_URL, adapter.CANONICAL_URL,
    ]
    assert sleep.call_args_list == [call(1.0), call(2.0)]
    data = verify_snapshot(writer.finalize())
    assert [entry["http_status"] for entry in data["files"]] == [302, 429, 503, 200]
    assert data["files"][0]["size_bytes"] == 0


@pytest.mark.parametrize("location", [
    "https://unrelated.example/fixtures.csv",
    "http://football-data.co.uk/matches/resources/fixtures.csv",
    "https://www.football-data.co.uk/matches/resources/fixtures.csv",
    "https://football-data.co.uk/matches/resources/fixtures.csv",
    "http://football-data.co.uk/fixtures.csv",
    adapter.CANONICAL_URL + "?token=SECRET", FOOTBALL_DATA_UK_FIXTURES,
])
def test_unapproved_redirects_are_not_followed_or_logged(writer, location):
    session = session_for(response(b"redirect", status=302, Location=location))
    assert fetch(writer, session).status == "http_error"
    session.get.assert_called_once()
    assert "SECRET" not in json.dumps(manifest(writer))


def test_redirect_loop_is_bounded(writer):
    redirect = lambda: response(b"", status=302, Location=adapter.CANONICAL_URL)
    session = session_for(redirect(), redirect())
    assert fetch(writer, session).status == "http_error"
    assert session.get.call_count == 2


def test_observed_html_after_canonical_redirect_is_a_visible_contract_failure(writer):
    session = session_for(response(b"", status=302, Location=adapter.CANONICAL_URL),
                          response(b"<html>download page</html>", content_type="text/html"))
    result = fetch(writer, session)
    assert result == adapter.OddsFetchResult("contract_failed", None, 2)
    data = verify_snapshot(writer.finalize())
    assert data["failures"][-1]["error_code"] == "invalid_payload"
    assert data["failures"][-1]["relative_path"] == "raw/football_data_uk/attempt_02/fixtures.csv"


def test_storage_failure_propagates_instead_of_becoming_optional_source_failure(
    writer, monkeypatch
):
    monkeypatch.setattr(writer, "write_raw", Mock(side_effect=OSError("disk full")))
    with pytest.raises(OSError, match="disk full"):
        fetch(writer, session_for(response()))


def test_old_path_api_is_rejected_before_network(tmp_path):
    session = session_for()
    with pytest.raises(TypeError, match="SnapshotWriter"):
        adapter.fetch_upcoming_odds(tmp_path, session=session)
    session.get.assert_not_called()


def test_shared_provenance_rejects_backdating_and_unrelated_error_links(writer):
    with pytest.raises(ValueError, match="Availability"):
        writer.write_raw("bad.csv", BODY, source="football_data_uk", required=False,
                         request_started_at=NOW, retrieved_at=NOW,
                         available_at=NOW - timedelta(days=1))
    add_required_baseline(writer)
    with pytest.raises(ValueError, match="same source"):
        writer.record_failure(source="football_data_uk", required=False,
                              error_code="invalid_payload", relative_path="raw/baseline.json")


@pytest.mark.parametrize("change", ["availability", "content_type", "error_link"])
def test_verifier_checks_new_metadata_even_if_manifest_digest_is_recomputed(writer, change):
    fetch(writer, session_for(response(b"<html>error</html>", content_type="text/html")))
    final = writer.finalize()
    data = verify_snapshot(final)
    if change == "availability":
        data["files"][0]["available_at"] = "2025-01-01T00:00:00.000000+00:00"
    elif change == "content_type":
        data["files"][0]["content_type"] = "text/csv\r\nAuthorization: SECRET"
    else:
        data["failures"][0]["relative_path"] = "raw/nonexistent.csv"
    encoded = json.dumps(data).encode()
    (final / "manifest.json").write_bytes(encoded)
    (final / "COMPLETE").write_text(hashlib.sha256(encoded).hexdigest() + "\n")
    with pytest.raises(SnapshotIntegrityError):
        verify_snapshot(final)
