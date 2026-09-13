"""Offline football-data.org contracts using synthetic responses, never real tokens."""

import hashlib
import json
from datetime import datetime, timedelta, timezone
from unittest.mock import Mock, call

import pytest
import requests

from fpl_model.data_sources import football_data_org as adapter
from fpl_model.io import SnapshotIntegrityError, SnapshotWriter, verify_snapshot


NOW = datetime(2026, 9, 13, 12, tzinfo=timezone.utc)
TOKEN = "synthetic-private-token"


def payload(code="PL"):
    return json.dumps({
        "filters": {}, "resultSet": {"count": 1}, "competition": {"code": code},
        "matches": [{"id": 123, "competition": {"code": code},
                     "utcDate": "2020-01-01T15:00:00Z", "status": "FINISHED",
                     "homeTeam": {"name": "Example Home"},
                     "awayTeam": {"name": "Example Away"}}],
    }, indent=2).encode() + b"\r\n"


def response(body=None, *, status=200, content_type="application/json", **headers):
    reply = requests.Response()
    reply.status_code = status
    reply._content = payload() if body is None else body
    reply._content_consumed = True
    if content_type is not None:
        reply.headers["Content-Type"] = content_type
    reply.headers.update(headers)
    reply.close = Mock()
    return reply


def session_for(*replies):
    session = Mock(spec=requests.Session)
    session.get.side_effect = replies
    return session


@pytest.fixture(autouse=True)
def synthetic_token(monkeypatch):
    monkeypatch.setenv("FOOTBALL_DATA_ORG_TOKEN", TOKEN)


@pytest.fixture
def writer(tmp_path):
    return SnapshotWriter(tmp_path / "raw", clock=lambda: NOW)


def fetch(writer, session, code="PL", sleep=None):
    return adapter.fetch_competition_matches(
        code, writer, session=session, clock=lambda: NOW,
        sleep=Mock() if sleep is None else sleep,
    )


def manifest(writer):
    return json.loads((writer.staging_path / "manifest.json").read_bytes())


def baseline(writer):
    writer.write_raw("baseline.json", b"{}", source="baseline", required=True,
                     request_started_at=NOW, retrieved_at=NOW)


@pytest.mark.parametrize("token", [None, "", "   "])
def test_missing_token_is_optional_skip_with_no_request_or_fake_file(writer, monkeypatch, token):
    if token is None:
        monkeypatch.delenv("FOOTBALL_DATA_ORG_TOKEN")
    else:
        monkeypatch.setenv("FOOTBALL_DATA_ORG_TOKEN", token)
    session = session_for()
    for code in ("PL", "CL"):
        assert fetch(writer, session, code) == adapter.MatchesFetchResult("skipped", None, 0)
    session.get.assert_not_called()
    data = manifest(writer)
    assert data["files"] == [] and data["status"] == "staging"
    assert [f["request_context"] for f in data["failures"]] == [
        {"competition_code": "PL"}, {"competition_code": "CL"},
    ]
    for failure in data["failures"]:
        assert failure["outcome"] == "skipped" and failure["error_code"] == "missing_token"
        assert failure["required"] is False and failure["request_params"] == {}
        assert "request_started_at" not in failure
    baseline(writer)
    verify_snapshot(writer.finalize())  # Skips do not block a valid baseline.


@pytest.mark.parametrize("code", ["PL", "CL"])
def test_success_stores_exact_bytes_before_validation_and_complete_provenance(
    writer, monkeypatch, code, caplog, capsys
):
    body = b"\xef\xbb\xbf" + payload(code)
    reply = response(body, content_type="application/json; charset=utf-8")
    session = session_for(reply)
    original = adapter._validate_json
    validated = []

    def validate_after_storage(raw, content_type, competition):
        entry = manifest(writer)["files"][0]
        assert (writer.staging_path / entry["relative_path"]).read_bytes() == raw
        validated.append(True)
        original(raw, content_type, competition)

    monkeypatch.setattr(adapter, "_validate_json", validate_after_storage)
    result = fetch(writer, session, code)
    assert result == adapter.MatchesFetchResult(
        "success", f"raw/football_data_org/{code}/attempt_01/matches.json", 1,
    )
    assert validated == [True]
    assert not writer.final_path.exists() and manifest(writer)["status"] == "staging"
    url = f"https://api.football-data.org/v4/competitions/{code}/matches"
    session.get.assert_called_once_with(
        url, params={}, headers={"X-Auth-Token": TOKEN}, timeout=(10, 30), allow_redirects=False,
    )
    data = verify_snapshot(writer.finalize())
    assert data["failures"] == []
    entry = data["files"][0]
    assert entry == {
        "source": "football_data_org", "request_url": url, "request_params": {},
        "request_context": {"competition_code": code}, "required": False,
        "request_started_at": NOW.isoformat(timespec="microseconds"),
        "retrieved_at": NOW.isoformat(timespec="microseconds"),
        "available_at": NOW.isoformat(timespec="microseconds"),
        "http_status": 200, "content_type": "application/json; charset=utf-8",
        "outcome": "success", "relative_path": result.raw_path,
        "sha256": hashlib.sha256(body).hexdigest(), "size_bytes": len(body),
    }
    assert (writer.final_path / result.raw_path).read_bytes() == body
    assert TOKEN not in json.dumps(data) + caplog.text + str(capsys.readouterr())
    reply.close.assert_called_once()
    session.close.assert_not_called()


@pytest.mark.parametrize("body,content_type", [
    (b"", "application/json"), (b" \r\n", "application/json"),
    (b"{broken", "application/json"), (b"\xff", "application/json"),
    (b"<html>error</html>", "application/json"),
    (payload(), "text/html; charset=utf-8"),
    (b"<html>error</html>", "application/xhtml+xml"),
    (b"[]", "application/json"), (b"null", "application/json"),
    (b"{}", "application/json"), (b'{"matches": null}', "application/json"),
    (b'{"matches": {}}', "application/json"), (b'{"matches": [1]}', "application/json"),
    (b'{"matches": [], "errorCode": 403}', "application/json"),
    (b'{"message": "Access denied", "errorCode": 403}', "application/json"),
    (b'{"matches": [], "unknown": NaN}', "application/json"),
    (b'{"matches": [], "competition": {"code": "CL"}}', "application/json"),
    (b'{"matches": [{"competition": {"code": "CL"}}]}', "application/json"),
    (b'{"matches": [], "competition": "PL"}', "application/json"),
])
def test_invalid_response_remains_raw_with_explicit_optional_failure(writer, body, content_type):
    session = session_for(response(body, content_type=content_type))
    assert fetch(writer, session) == adapter.MatchesFetchResult("contract_failed", None, 1)
    session.get.assert_called_once()
    data = verify_snapshot(writer.finalize())
    entry, failure = data["files"][0], data["failures"][0]
    assert (writer.final_path / entry["relative_path"]).read_bytes() == body
    assert entry["http_status"] == 200 and entry["required"] is False
    assert failure["error_code"] == "invalid_payload" and failure["required"] is False
    assert failure["relative_path"] == entry["relative_path"]


@pytest.mark.parametrize("body", [
    b'{"matches": []}',
    b'{"matches": [{"newField": {"anything": true}}], "newTopLevel": [1]}',
    b'{"matches": [], "competition": null}',
])
def test_empty_list_and_unknown_fields_are_valid_without_detail_field_dependencies(writer, body):
    assert fetch(writer, session_for(response(body))).status == "success"


@pytest.mark.parametrize("status", [301, 302, 401, 403, 404])
def test_nontransient_http_errors_and_redirects_are_not_retried(writer, status, caplog, capsys):
    reply = response(b'{"message":"Unavailable"}', status=status,
                     Location="https://unrelated.example/" + TOKEN)
    session = session_for(reply)
    sleep = Mock()
    assert fetch(writer, session, sleep=sleep).status == "http_error"
    session.get.assert_called_once()
    sleep.assert_not_called()
    data = verify_snapshot(writer.finalize())
    assert data["files"][0]["http_status"] == status
    assert data["failures"][0]["error_code"] == "http_error"
    assert TOKEN not in json.dumps(data) + caplog.text + str(capsys.readouterr())


@pytest.mark.parametrize("status", [429, 500, 503, 599])
def test_transient_response_then_success_retains_both_attempts(writer, status):
    first = b'{"message":"Try later"}'
    session = session_for(response(first, status=status), response())
    sleep = Mock()
    result = fetch(writer, session, sleep=sleep)
    assert result == adapter.MatchesFetchResult(
        "success", "raw/football_data_org/PL/attempt_02/matches.json", 2,
    )
    sleep.assert_called_once_with(1.0)
    data = verify_snapshot(writer.finalize())
    assert [e["http_status"] for e in data["files"]] == [status, 200]
    assert (writer.final_path / data["files"][0]["relative_path"]).read_bytes() == first
    assert len(data["failures"]) == 1


@pytest.mark.parametrize("status", [429, 500, 503])
def test_http_retries_are_bounded_and_do_not_create_valid_empty_data(writer, status):
    session = session_for(*(response(b"busy", status=status) for _ in range(3)))
    sleep = Mock()
    assert fetch(writer, session, sleep=sleep) == adapter.MatchesFetchResult("http_error", None, 3)
    assert session.get.call_count == 3 and sleep.call_args_list == [call(1.0), call(2.0)]
    data = verify_snapshot(writer.finalize())
    assert len(data["files"]) == len(data["failures"]) == 3


@pytest.mark.parametrize("retry_after,delay", [
    ("7", 7.0), ("30", 30.0), ("0", 1.0), ("invalid", 1.0),
    ("Sun, 13 Sep 2026 12:00:10 GMT", 10.0), ("31", None),
    ("Sun, 13 Sep 2026 12:01:00 GMT", None),
])
def test_retry_after_is_honored_with_a_bounded_wait(writer, retry_after, delay):
    session = session_for(response(status=429, **{"Retry-After": retry_after}), response())
    sleep = Mock()
    result = fetch(writer, session, sleep=sleep)
    if delay is None:
        assert result.status == "http_error" and result.request_count == 1
        sleep.assert_not_called()
    else:
        assert result.status == "success" and result.request_count == 2
        sleep.assert_called_once_with(delay)


@pytest.mark.parametrize("error,retried", [
    (requests.Timeout, True), (requests.ConnectionError, True), (requests.RequestException, False),
])
def test_transport_failures_are_safe_optional_records_without_fake_bodies(
    writer, error, retried, caplog, capsys
):
    session = session_for(*(error(TOKEN) for _ in range(3)))
    sleep = Mock()
    result = fetch(writer, session, sleep=sleep)
    assert result == adapter.MatchesFetchResult("request_failed", None, 3 if retried else 1)
    data = manifest(writer)
    assert data["files"] == [] and len(data["failures"]) == result.request_count
    assert sleep.call_count == (2 if retried else 0)
    assert TOKEN not in json.dumps(data) + caplog.text + str(capsys.readouterr())
    baseline(writer)
    verify_snapshot(writer.finalize())


def test_transport_retry_success_and_both_competitions_share_one_snapshot(writer):
    session = session_for(requests.Timeout(TOKEN), response(), response(payload("CL")))
    pl, cl = fetch(writer, session), fetch(writer, session, "CL")
    assert pl.raw_path == "raw/football_data_org/PL/attempt_02/matches.json"
    assert cl.raw_path == "raw/football_data_org/CL/attempt_01/matches.json"
    assert not writer.final_path.exists()
    assert len(verify_snapshot(writer.finalize())["files"]) == 2


def test_availability_uses_completed_retrieval_not_event_time(tmp_path):
    ticks = iter(NOW + timedelta(seconds=i) for i in range(4))
    clock = lambda: next(ticks)
    writer = SnapshotWriter(tmp_path, clock=clock)
    adapter.fetch_competition_matches("PL", writer, session=session_for(response()), clock=clock)
    entry = verify_snapshot(writer.finalize())["files"][0]
    assert entry["request_started_at"] == "2026-09-13T12:00:01.000000+00:00"
    assert entry["available_at"] == entry["retrieved_at"] == "2026-09-13T12:00:02.000000+00:00"


def test_storage_errors_and_interrupts_propagate(writer, monkeypatch):
    monkeypatch.setattr(writer, "write_raw", Mock(side_effect=OSError("disk full")))
    with pytest.raises(OSError, match="disk full"):
        fetch(writer, session_for(response()))
    with pytest.raises(KeyboardInterrupt):
        fetch(writer, session_for(KeyboardInterrupt()))
    assert manifest(writer)["failures"][-1]["error_code"] == "transport_error"


def test_unsupported_scope_and_legacy_writer_rejected_before_network(writer, tmp_path):
    session = session_for()
    with pytest.raises(ValueError, match="Only PL and CL"):
        fetch(writer, session, "PD")
    with pytest.raises(TypeError, match="SnapshotWriter"):
        fetch(tmp_path, session)
    session.get.assert_not_called()


def test_public_metadata_is_copied_and_verified(writer):
    params, context = {"season": "2026"}, {"competition_code": "PL"}
    writer.write_raw("test.json", b"{}", source="test", required=False,
                     request_started_at=NOW, retrieved_at=NOW,
                     request_params=params, request_context=context)
    writer.record_failure(source="test", required=False, outcome="skipped",
                          request_params=params, request_context=context)
    params["season"], context["competition_code"] = "1999", "CL"
    final = writer.finalize()
    data = verify_snapshot(final)
    for entry in [*data["files"], *data["failures"]]:
        assert entry["request_params"] == {"season": "2026"}
        assert entry["request_context"] == {"competition_code": "PL"}
    data["files"][0]["request_params"] = {"X_Auth_Token": TOKEN}
    raw = json.dumps(data).encode()
    (final / "manifest.json").write_bytes(raw)
    (final / "COMPLETE").write_text(hashlib.sha256(raw).hexdigest() + "\n")
    with pytest.raises(SnapshotIntegrityError):
        verify_snapshot(final)


@pytest.mark.parametrize("values", [{"token": TOKEN}, {"x": 42}, {"x": "bad\nvalue"}, []])
@pytest.mark.parametrize("field", ["request_params", "request_context"])
def test_unsafe_or_malformed_public_metadata_rejected(writer, values, field):
    with pytest.raises(ValueError):
        writer.write_raw("bad.json", b"{}", source="test", required=False,
                         request_started_at=NOW, retrieved_at=NOW, **{field: values})
    with pytest.raises(ValueError):
        writer.record_failure(source="test", required=False, **{field: values})
    assert manifest(writer)["files"] == manifest(writer)["failures"] == []
