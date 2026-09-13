"""FPL source contracts using synthetic stored payloads and mocked HTTP responses."""

import hashlib
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import Mock, call

import pytest
import requests

from fpl_model.config import FPL_BOOTSTRAP, FPL_FIXTURES
from fpl_model.data_sources import fpl_api
from fpl_model.data_sources.fpl_api import FPLContractError, FPLSourceError, fetch_fpl_snapshot
from fpl_model.io import SnapshotStateError, SnapshotWriter, verify_snapshot


NOW = datetime(2026, 9, 13, 10, tzinfo=timezone.utc)
FIXTURES = Path(__file__).parent / "fixtures" / "fpl"
BOOTSTRAP = (FIXTURES / "bootstrap_static.json").read_bytes()
FIXTURE_LIST = (FIXTURES / "fixtures.json").read_bytes()


def response(body, *, status=200, content_type="application/json; charset=utf-8"):
    result = requests.Response()
    result._content = body
    result._content_consumed = True
    result.status_code = status
    if content_type is not None:
        result.headers["Content-Type"] = content_type
    result.close = Mock()
    result.json = Mock(side_effect=AssertionError("Parse stored bytes, not Response.json()"))
    return result


def session_for(*results):
    session = Mock(spec=requests.Session)
    session.get.side_effect = results
    return session


@pytest.fixture
def writer(tmp_path):
    return SnapshotWriter(tmp_path / "raw", clock=lambda: NOW)


def fetch(writer, session):
    fetch_fpl_snapshot(writer, session=session, clock=lambda: NOW)


def manifest_in_staging(writer):
    return json.loads((writer.staging_path / "manifest.json").read_bytes())


def test_two_existing_endpoints_are_required_and_preserve_bytes_before_parsing(writer, monkeypatch):
    # Preserve whitespace, UTF-8 and CRLF rather than reserializing parsed JSON.
    bootstrap = BOOTSTRAP.replace(b"\n", b"\r\n")
    replies = [response(bootstrap), response(FIXTURE_LIST)]
    session = session_for(*replies)
    original_loads = json.loads
    parsed_files = []

    def check_write_precedes_parse(body):
        filename = "bootstrap_static.json" if body == bootstrap else "fixtures.json"
        relative = f"raw/fpl_api/{filename}"
        assert (writer.staging_path / relative).read_bytes() == body
        metadata = original_loads((writer.staging_path / "manifest.json").read_bytes())
        entry = next(entry for entry in metadata["files"] if entry["relative_path"] == relative)
        assert entry["sha256"] == hashlib.sha256(body).hexdigest()
        parsed_files.append(filename)
        return original_loads(body)

    with monkeypatch.context() as context:
        context.setattr(fpl_api.json, "loads", check_write_precedes_parse)
        fetch(writer, session)
    assert parsed_files == ["bootstrap_static.json", "fixtures.json"]
    assert session.get.call_args_list == [
        call(FPL_BOOTSTRAP, timeout=(10, 30), allow_redirects=False),
        call(FPL_FIXTURES, timeout=(10, 30), allow_redirects=False),
    ]
    assert not writer.final_path.exists()  # Caller owns finalization.
    manifest = verify_snapshot(writer.finalize())
    for entry, body, url in zip(manifest["files"], (bootstrap, FIXTURE_LIST),
                                (FPL_BOOTSTRAP, FPL_FIXTURES), strict=True):
        assert entry["source"] == "fpl_api"
        assert entry["required"] is True
        assert entry["http_status"] == 200
        assert entry["outcome"] == "success"
        assert entry["request_url"] == url
        assert entry["size_bytes"] == len(body)
        assert (writer.final_path / entry["relative_path"]).read_bytes() == body
    assert manifest["failures"] == []
    session.close.assert_not_called()  # Borrowed session belongs to caller.
    for reply in replies:
        reply.close.assert_called_once()
        reply.json.assert_not_called()


def test_request_and_retrieval_timestamps_are_per_response_and_utc(tmp_path):
    ticks = iter(NOW + timedelta(seconds=index) for index in range(6))
    clock = lambda: next(ticks)
    writer = SnapshotWriter(tmp_path, clock=clock)
    session = session_for(response(BOOTSTRAP), response(FIXTURE_LIST))
    fetch_fpl_snapshot(writer, session=session, clock=clock)
    manifest = verify_snapshot(writer.finalize())
    assert manifest["created_at"] == "2026-09-13T10:00:00.000000+00:00"
    assert manifest["completed_at"] == "2026-09-13T10:00:05.000000+00:00"
    for entry, start, end in zip(manifest["files"], (1, 3), (2, 4), strict=True):
        assert entry["request_started_at"] == f"2026-09-13T10:00:0{start}.000000+00:00"
        assert entry["retrieved_at"] == f"2026-09-13T10:00:0{end}.000000+00:00"


@pytest.mark.parametrize("status", [301, 403, 429, 500, 503])
@pytest.mark.parametrize("endpoint", [0, 1])
def test_http_failures_preserve_error_bytes_and_block_partial_completion(writer, status, endpoint):
    body = b"upstream unavailable\r\n"
    replies = ([response(BOOTSTRAP)] if endpoint else []) + [response(body, status=status)]
    session = session_for(*replies)
    with pytest.raises(FPLSourceError, match=f"HTTP {status}"):
        fetch(writer, session)
    manifest = manifest_in_staging(writer)
    entry = manifest["files"][-1]
    assert entry["request_url"] == (FPL_BOOTSTRAP, FPL_FIXTURES)[endpoint]
    assert entry["outcome"] == "http_error" and entry["required"] is True
    assert (writer.staging_path / entry["relative_path"]).read_bytes() == body
    assert session.get.call_count == endpoint + 1  # Fail fast; no hidden retry/redirect.
    with pytest.raises(SnapshotStateError):
        writer.finalize()
    assert not writer.final_path.exists()


@pytest.mark.parametrize("exception", [requests.Timeout, requests.ConnectionError])
@pytest.mark.parametrize("endpoint", [0, 1])
def test_transport_failure_is_required_without_leaking_error_text(
    writer, exception, endpoint, capsys, caplog
):
    replies = ([response(BOOTSTRAP)] if endpoint else []) + [exception("token=SECRET")]
    session = session_for(*replies)
    with pytest.raises(FPLSourceError) as caught:
        fetch(writer, session)
    manifest = manifest_in_staging(writer)
    assert len(manifest["files"]) == endpoint
    assert manifest["failures"][-1] == {
        "source": "fpl_api", "required": True, "outcome": "request_failed",
        "request_url": (FPL_BOOTSTRAP, FPL_FIXTURES)[endpoint],
        "request_started_at": "2026-09-13T10:00:00.000000+00:00",
        "recorded_at": "2026-09-13T10:00:00.000000+00:00",
    }
    assert "SECRET" not in str(caught.value)
    assert "SECRET" not in json.dumps(manifest)
    assert caught.value.__suppress_context__
    assert capsys.readouterr() == ("", "")
    assert not caplog.records
    with pytest.raises(SnapshotStateError):
        writer.finalize()


@pytest.mark.parametrize("exception", [KeyboardInterrupt, SystemExit])
def test_interrupted_second_request_cannot_leave_completable_partial_run(writer, exception):
    session = session_for(response(BOOTSTRAP), exception())
    with pytest.raises(exception):
        fetch(writer, session)
    with pytest.raises(SnapshotStateError):
        writer.finalize()


@pytest.mark.parametrize("body,content_type", [
    (b"", "application/json"),
    (b"{invalid-json", "application/json"),
    (b"\xff\x80", "application/json"),
    (b"<html>unavailable</html>", "text/html"),
    (b"<html>unavailable</html>", "application/json"),
    (BOOTSTRAP, None),
    (BOOTSTRAP, "text/html"),
    (b"[]", "application/json"),
    (b"{}", "application/json"),
    (b"null", "application/json"),
])
def test_malformed_bootstrap_is_preserved_but_never_publishable(writer, body, content_type):
    session = session_for(response(body, content_type=content_type))
    with pytest.raises(FPLContractError):
        fetch(writer, session)
    assert (writer.staging_path / "raw/fpl_api/bootstrap_static.json").read_bytes() == body
    manifest = manifest_in_staging(writer)
    assert manifest["files"][0]["http_status"] == 200
    assert manifest["failures"][0]["required"] is True
    assert manifest["failures"][0]["request_url"] == FPL_BOOTSTRAP
    with pytest.raises(SnapshotStateError):
        writer.finalize()


@pytest.mark.parametrize("field", ["elements", "teams", "events", "element_types"])
def test_missing_bootstrap_required_collections_fail(writer, field):
    payload = json.loads(BOOTSTRAP)
    del payload[field]
    with pytest.raises(FPLContractError):
        fetch(writer, session_for(response(json.dumps(payload).encode())))
    with pytest.raises(SnapshotStateError):
        writer.finalize()


@pytest.mark.parametrize("mutation", ["collection", "row", "id", "team", "deadline"])
def test_bootstrap_required_field_types_are_checked(writer, mutation):
    payload = json.loads(BOOTSTRAP)
    if mutation == "collection":
        payload["elements"] = {}
    elif mutation == "row":
        payload["teams"] = ["not an object"]
    elif mutation == "id":
        payload["elements"][0]["id"] = True
    elif mutation == "team":
        payload["elements"][0]["team"] = "1"
    else:
        payload["events"][0]["deadline_time"] = "2026-09-13T10:00:00"
    with pytest.raises(FPLContractError):
        fetch(writer, session_for(response(json.dumps(payload).encode())))


@pytest.mark.parametrize("body", [b"{}", b"[{}]", b"[1]", b"[null]", b""])
def test_bad_second_payload_cannot_finalize_first_payload_alone(writer, body):
    with pytest.raises(FPLContractError):
        fetch(writer, session_for(response(BOOTSTRAP), response(body)))
    manifest = manifest_in_staging(writer)
    assert len(manifest["files"]) == 2
    assert manifest["failures"][0]["request_url"] == FPL_FIXTURES
    with pytest.raises(SnapshotStateError):
        writer.finalize()


def test_empty_fixtures_are_valid_and_no_fixed_season_counts_are_assumed(writer):
    fetch(writer, session_for(response(BOOTSTRAP), response(b"[]\n")))
    assert len(verify_snapshot(writer.finalize())["files"]) == 2


@pytest.mark.parametrize("field,bad_value", [
    ("id", 0), ("event", "1"), ("team_h", None), ("team_a", False),
    ("finished", "false"), ("kickoff_time", "2026-09-13T12:00:00"),
])
def test_fixture_field_types_are_checked(writer, field, bad_value):
    payload = json.loads(FIXTURE_LIST)
    payload[0][field] = bad_value
    with pytest.raises(FPLContractError):
        fetch(writer, session_for(response(BOOTSTRAP), response(json.dumps(payload).encode())))
    with pytest.raises(SnapshotStateError):
        writer.finalize()


def test_legacy_path_argument_fails_before_making_requests(tmp_path):
    session = session_for()
    with pytest.raises(TypeError, match="SnapshotWriter"):
        fetch_fpl_snapshot(tmp_path, session=session)
    session.get.assert_not_called()


@pytest.mark.parametrize("url", [
    "https://user:SECRET@example.test/api/", "https://example.test/?token=SECRET",
    "https://example.test/api/#SECRET", "file:///SECRET", "https://example.test/ SECRET",
    "https://SECRET／@example.test/api/",
])
def test_manifest_provenance_rejects_credential_urls(writer, url):
    with pytest.raises(ValueError) as caught:
        writer.write_raw("response.json", BOOTSTRAP, source="fpl_api", required=True,
                         request_started_at=NOW, retrieved_at=NOW, request_url=url)
    assert "SECRET" not in str(caught.value)
    assert manifest_in_staging(writer)["files"] == []


def test_offline_network_guard_is_active():
    import socket

    with pytest.raises(pytest.fail.Exception, match="Network access is forbidden"):
        socket.create_connection(("example.test", 443))
