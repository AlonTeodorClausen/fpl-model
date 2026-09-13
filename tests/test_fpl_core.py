"""Core source contracts: synthetic stored CSVs, no network or pandas required."""

import hashlib
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import Mock, call

import pytest
import requests

from fpl_model.config import FPL_CORE_RAW
from fpl_model.data_sources import fpl_core
from fpl_model.data_sources.fpl_core import (
    MASTER_FILES,
    OPTIONAL_FILES,
    REQUIRED_FILES,
    CoreContractError,
    CoreSourceError,
    fetch_fpl_core_master,
)
from fpl_model.io import SnapshotIntegrityError, SnapshotStateError, SnapshotWriter, verify_snapshot


NOW = datetime(2026, 9, 13, 10, tzinfo=timezone.utc)
SHA = "a" * 40
OTHER_SHA = "b" * 40
SEASON = "2026-2027"
FIXTURE_DIR = Path(__file__).parent / "fixtures" / "fpl_core"
PAYLOADS = {name: (FIXTURE_DIR / name).read_bytes() for name in MASTER_FILES}


def response(body, *, status=200):
    result = requests.Response()
    result._content = body
    result._content_consumed = True
    result.status_code = status
    result.headers["Content-Type"] = "text/plain; charset=utf-8"
    result.close = Mock()
    return result


def session_for(*responses):
    session = Mock(spec=requests.Session)
    session.get.side_effect = responses
    return session


def good_session():
    return session_for(*(response(PAYLOADS[name]) for name in MASTER_FILES))


@pytest.fixture
def writer(tmp_path):
    return SnapshotWriter(tmp_path / "raw", clock=lambda: NOW)


def fetch(writer, session, **kwargs):
    return fetch_fpl_core_master(
        writer, commit_sha=SHA, session=session, clock=lambda: NOW, **kwargs
    )


def staging_manifest(writer):
    return json.loads((writer.staging_path / "manifest.json").read_bytes())


def source_url(name):
    return f"{FPL_CORE_RAW}/{SHA}/data/{SEASON}/{name}"


def test_pinned_files_are_saved_before_parsing_with_provenance(writer, monkeypatch):
    bodies = dict(PAYLOADS)
    bodies["players.csv"] = b"\xef\xbb\xbf" + bodies["players.csv"].replace(b"\n", b"\r\n")
    replies = [response(bodies[name]) for name in MASTER_FILES]
    session = session_for(*replies)
    original_validate = fpl_core._validate_csv
    parsed = []

    def validate_after_write(name, body):
        relative = f"raw/fpl_core/{SHA}/data/{SEASON}/{name}"
        assert (writer.staging_path / relative).read_bytes() == body
        manifest = staging_manifest(writer)
        assert manifest["source_commits"] == {"fpl_core": SHA}
        entry = manifest["files"][-1]
        assert entry["relative_path"] == relative
        assert entry["sha256"] == hashlib.sha256(body).hexdigest()
        parsed.append(name)
        original_validate(name, body)

    monkeypatch.setattr(fpl_core, "_validate_csv", validate_after_write)
    outcomes = fetch(writer, session)
    assert outcomes == dict.fromkeys(MASTER_FILES, "success")
    assert parsed == list(MASTER_FILES)
    assert session.get.call_args_list == [
        call(source_url(name), timeout=(10, 30), allow_redirects=False) for name in MASTER_FILES
    ]
    assert not writer.final_path.exists()
    manifest = verify_snapshot(writer.finalize())
    assert manifest["source_commits"] == {"fpl_core": SHA}
    for entry, name in zip(manifest["files"], MASTER_FILES, strict=True):
        assert entry["source"] == "fpl_core"
        assert entry["request_url"] == source_url(name)
        assert entry["commit_sha"] == SHA
        assert entry["required"] == (name in REQUIRED_FILES)
        assert entry["http_status"] == 200 and entry["outcome"] == "success"
        assert entry["size_bytes"] == len(bodies[name])
        assert (writer.final_path / entry["relative_path"]).read_bytes() == bodies[name]
    session.close.assert_not_called()
    for reply in replies:
        reply.close.assert_called_once()


def test_timestamps_are_observed_per_file_not_inferred_from_git(tmp_path):
    ticks = iter(NOW + timedelta(seconds=index) for index in range(10))

    def clock():
        return next(ticks)

    writer = SnapshotWriter(tmp_path, clock=clock)
    fetch_fpl_core_master(writer, commit_sha=SHA, session=good_session(), clock=clock)
    manifest = verify_snapshot(writer.finalize())
    for index, entry in enumerate(manifest["files"]):
        assert entry["request_started_at"] == (
            NOW + timedelta(seconds=1 + 2 * index)
        ).isoformat(timespec="microseconds")
        assert entry["retrieved_at"] == (
            NOW + timedelta(seconds=2 + 2 * index)
        ).isoformat(timespec="microseconds")


@pytest.mark.parametrize("sha", ["main", "HEAD", "a" * 7, "a" * 39, "a" * 41,
                                  "g" * 40, "token=SECRET", None])
def test_only_explicit_full_shas_are_accepted_before_network(writer, sha):
    session = good_session()
    with pytest.raises(ValueError) as caught:
        fetch_fpl_core_master(writer, commit_sha=sha, session=session)
    session.get.assert_not_called()
    assert "SECRET" not in str(caught.value)
    assert staging_manifest(writer)["files"] == []


def test_commit_is_mandatory(writer):
    with pytest.raises(TypeError):
        fetch_fpl_core_master(writer)


def test_uppercase_sha_is_normalized_once(writer):
    fetch_fpl_core_master(writer, commit_sha=SHA.upper(), session=good_session(), clock=lambda: NOW)
    manifest = verify_snapshot(writer.finalize())
    assert manifest["source_commits"] == {"fpl_core": SHA}
    assert all(entry["commit_sha"] == SHA for entry in manifest["files"])


@pytest.mark.parametrize("season", ["main", "2026-2028", "2026/2027", "../2026-2027", None])
def test_invalid_seasons_are_rejected_before_network(writer, season):
    session = good_session()
    with pytest.raises(ValueError):
        fetch(writer, session, season=season)
    session.get.assert_not_called()


def test_an_explicit_other_season_changes_every_url_without_fallback(writer):
    session = good_session()
    fetch(writer, session, season="2025-2026")
    assert all(f"/{SHA}/data/2025-2026/" in c.args[0] for c in session.get.call_args_list)
    verify_snapshot(writer.finalize())


def test_same_run_cannot_mix_commits_even_across_adapter_invocations(writer):
    fetch(writer, good_session())
    before = (writer.staging_path / "manifest.json").read_bytes()
    second = good_session()
    with pytest.raises(ValueError, match="mix Git commits"):
        fetch_fpl_core_master(writer, commit_sha=OTHER_SHA, session=second)
    second.get.assert_not_called()
    assert (writer.staging_path / "manifest.json").read_bytes() == before
    assert verify_snapshot(writer.finalize())["source_commits"] == {"fpl_core": SHA}


@pytest.mark.parametrize("name", REQUIRED_FILES)
@pytest.mark.parametrize("status", [302, 404, 429, 503])
def test_required_http_failure_never_silently_continues(writer, name, status):
    index = MASTER_FILES.index(name)
    body = b"upstream error\r\n"
    replies = [response(PAYLOADS[n]) for n in MASTER_FILES[:index]]
    session = session_for(*replies, response(body, status=status))
    with pytest.raises(CoreSourceError, match=f"HTTP {status}"):
        fetch(writer, session)
    assert session.get.call_count == index + 1
    entry = staging_manifest(writer)["files"][-1]
    assert entry["commit_sha"] == SHA and entry["request_url"] == source_url(name)
    assert entry["required"] is True and entry["outcome"] == "http_error"
    assert (writer.staging_path / entry["relative_path"]).read_bytes() == body
    with pytest.raises(SnapshotStateError):
        writer.finalize()
    assert not writer.final_path.exists()


@pytest.mark.parametrize("name", REQUIRED_FILES)
@pytest.mark.parametrize("exception", [requests.Timeout, requests.ConnectionError])
def test_required_transport_failure_has_pin_and_safe_diagnostics(
    writer, name, exception, capsys, caplog
):
    index = MASTER_FILES.index(name)
    replies = [response(PAYLOADS[n]) for n in MASTER_FILES[:index]]
    session = session_for(*replies, exception("https://user:SECRET@example.test"))
    with pytest.raises(CoreSourceError) as caught:
        fetch(writer, session)
    manifest = staging_manifest(writer)
    failure = manifest["failures"][-1]
    assert failure["required"] is True
    assert failure["commit_sha"] == SHA and failure["request_url"] == source_url(name)
    assert "SECRET" not in str(caught.value) + json.dumps(manifest)
    assert caught.value.__suppress_context__
    assert capsys.readouterr() == ("", "") and not caplog.records
    with pytest.raises(SnapshotStateError):
        writer.finalize()


@pytest.mark.parametrize("exception", [KeyboardInterrupt, SystemExit])
def test_interrupted_required_request_cannot_finalize_partial_core(writer, exception):
    with pytest.raises(exception):
        fetch(writer, session_for(response(PAYLOADS["players.csv"]), exception()))
    with pytest.raises(SnapshotStateError):
        writer.finalize()


@pytest.mark.parametrize("kind", ["http", "transport", "contract"])
def test_optional_summary_failure_is_explicit_and_does_not_block_required_files(writer, kind):
    replies = [response(PAYLOADS[n]) for n in REQUIRED_FILES]
    if kind == "http":
        replies.append(response(b"not found", status=404))
        expected_outcome = "http_error"
    elif kind == "transport":
        replies.append(requests.Timeout("request unavailable"))
        expected_outcome = "request_failed"
    else:
        replies.append(response(b"id,deadline_time\n1,invalid-time\n"))
        expected_outcome = "contract_failed"
    outcomes = fetch(writer, session_for(*replies))
    name = OPTIONAL_FILES[0]
    assert outcomes[name] == expected_outcome
    assert all(outcomes[n] == "success" for n in REQUIRED_FILES)
    manifest = verify_snapshot(writer.finalize())
    observations = [entry for entry in manifest["files"] + manifest["failures"]
                    if entry["request_url"] == source_url(name)]
    assert observations and all(entry["required"] is False for entry in observations)
    assert all(entry["commit_sha"] == SHA for entry in observations)


@pytest.mark.parametrize("body", [
    b"", b"<html>unavailable</html>", b"\xff\xfe\x80", b"player_id\n1\n",
    b"player_id,player_code,team_code,position,position\n1,2,3,MID,MID\n",
    b"player_id,player_code,team_code,position\n1,2,3\n",
    b"player_id,player_code,team_code,position\n1,2,3,MID,extra\n",
    b'player_id,player_code,team_code,position\n1,2,3,"unclosed',
    b"player_id,player_code,team_code,position\n1,2,3,\n",
    b"player_id,player_code,team_code,position\ninvalid,2,3,MID\n",
])
def test_required_invalid_csv_is_preserved_but_cannot_publish(writer, body):
    with pytest.raises(CoreContractError):
        fetch(writer, session_for(response(body)))
    manifest = staging_manifest(writer)
    assert manifest["files"][0]["http_status"] == 200
    assert manifest["failures"][0]["required"] is True
    assert (writer.staging_path / manifest["files"][0]["relative_path"]).read_bytes() == body
    with pytest.raises(SnapshotStateError):
        writer.finalize()


@pytest.mark.parametrize("name", REQUIRED_FILES)
def test_every_required_file_has_a_header_contract(writer, name):
    replies = [response(b"wrong,header\n1,2\n" if n == name else PAYLOADS[n])
               for n in MASTER_FILES]
    with pytest.raises(CoreContractError):
        fetch(writer, session_for(*replies))
    with pytest.raises(SnapshotStateError):
        writer.finalize()


def test_repeated_player_ids_and_missing_stats_are_not_rewritten_as_match_data(writer):
    fetch(writer, good_session())
    final = writer.finalize()
    assert (final / f"raw/fpl_core/{SHA}/data/{SEASON}/playerstats.csv").read_bytes() == (
        PAYLOADS["playerstats.csv"]
    )
    assert not list(final.rglob("*.parquet"))


def test_header_only_tables_are_schema_valid_not_claims_of_data_coverage(writer):
    replies = [response(PAYLOADS[name].split(b"\n", 1)[0] + b"\n") for name in MASTER_FILES]
    assert fetch(writer, session_for(*replies)) == dict.fromkeys(MASTER_FILES, "success")
    verify_snapshot(writer.finalize())


def test_old_path_api_is_rejected_before_network(tmp_path):
    session = good_session()
    with pytest.raises(TypeError, match="SnapshotWriter"):
        fetch_fpl_core_master(tmp_path, commit_sha=SHA, session=session)
    session.get.assert_not_called()


def test_pinned_source_cannot_add_unversioned_records(writer):
    writer.pin_source_commit("fpl_core", SHA)
    with pytest.raises(ValueError, match="require a commit"):
        writer.write_raw("unversioned.csv", b"body", source="fpl_core", required=True,
                         request_started_at=NOW, retrieved_at=NOW)
    with pytest.raises(ValueError, match="require a commit"):
        writer.record_failure(source="fpl_core", required=False)


def test_preexisting_unversioned_source_cannot_be_relabelled_with_commit(writer):
    writer.write_raw("old.csv", b"old", source="fpl_core", required=True,
                     request_started_at=NOW, retrieved_at=NOW)
    with pytest.raises(ValueError, match="unversioned"):
        writer.pin_source_commit("fpl_core", SHA)


@pytest.mark.parametrize("target", ["file", "failure", "pin"])
def test_verification_rejects_mixed_commit_provenance_even_with_new_manifest_digest(writer, target):
    replies = [response(PAYLOADS[n]) for n in REQUIRED_FILES]
    fetch(writer, session_for(*replies, requests.Timeout()))
    final = writer.finalize()
    manifest = verify_snapshot(final)
    if target == "file":
        manifest["files"][0]["commit_sha"] = OTHER_SHA
    elif target == "failure":
        manifest["failures"][0]["commit_sha"] = OTHER_SHA
    else:
        manifest["source_commits"]["fpl_core"] = OTHER_SHA
    encoded = json.dumps(manifest).encode()
    (final / "manifest.json").write_bytes(encoded)
    (final / "COMPLETE").write_text(hashlib.sha256(encoded).hexdigest() + "\n")
    with pytest.raises(SnapshotIntegrityError):
        verify_snapshot(final)


def test_finalized_source_pin_cannot_be_modified(writer):
    fetch(writer, good_session())
    final = writer.finalize()
    before = (final / "manifest.json").read_bytes()
    with pytest.raises(SnapshotStateError):
        writer.pin_source_commit("fpl_core", OTHER_SHA)
    assert (final / "manifest.json").read_bytes() == before


def test_core_commit_pin_does_not_require_git_metadata_for_other_sources(writer):
    writer.write_raw("fpl_api/example.json", b"{}", source="fpl_api", required=True,
                     request_started_at=NOW, retrieved_at=NOW, http_status=200)
    fetch(writer, good_session())
    manifest = verify_snapshot(writer.finalize())
    assert manifest["source_commits"] == {"fpl_core": SHA}
    assert "commit_sha" not in manifest["files"][0]
