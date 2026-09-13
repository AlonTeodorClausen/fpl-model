"""Offline contract tests; all snapshots live in pytest's temporary directories."""

import hashlib
import json
import socket
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import UUID

import pytest

from fpl_model import io
from fpl_model.io import (
    SnapshotIntegrityError,
    SnapshotStateError,
    SnapshotWriter,
    snapshot_dir,
    verify_snapshot,
)


NOW = datetime(2026, 9, 13, 10, 0, 0, tzinfo=timezone.utc)
RAW = b'\xef\xbb\xbf{ "value": 1 }\r\n\x00\xff\x80'


@pytest.fixture(autouse=True)
def prohibit_network(monkeypatch):
    def blocked(*args, **kwargs):
        pytest.fail("Snapshot I/O tests must not access the network")

    monkeypatch.setattr(socket.socket, "connect", blocked)
    monkeypatch.setattr(socket, "create_connection", blocked)


@pytest.fixture
def writer(tmp_path):
    return SnapshotWriter(tmp_path / "snapshots", clock=lambda: NOW)


def write_response(writer, data=RAW, **overrides):
    metadata = {
        "source": "fpl_api",
        "request_started_at": NOW - timedelta(seconds=1),
        "retrieved_at": NOW,
        "required": True,
        "http_status": 200,
    }
    metadata.update(overrides)
    writer.write_raw("fpl_api/response.bin", data, **metadata)


def read_staging_manifest(writer):
    return json.loads((writer.staging_path / "manifest.json").read_bytes())


def test_runs_in_same_second_have_distinct_ids_and_paths(tmp_path):
    first = SnapshotWriter(tmp_path, clock=lambda: NOW)
    second = SnapshotWriter(tmp_path, clock=lambda: NOW)
    assert first.run_id != second.run_id
    assert first.staging_path != second.staging_path
    assert first.final_path != second.final_path
    for writer in (first, second):
        assert UUID(writer.run_id).version == 4
        assert read_staging_manifest(writer)["status"] == "staging"
        assert not writer.final_path.exists()
        write_response(writer)
        assert verify_snapshot(writer.finalize())["status"] == "complete"


def test_raw_bytes_and_required_manifest_metadata(writer):
    write_response(writer)
    assert (writer.staging_path / "raw/fpl_api/response.bin").read_bytes() == RAW
    final = writer.finalize()
    manifest = verify_snapshot(final)
    assert manifest["run_id"] == writer.run_id
    assert manifest["schema_version"] == 1
    assert manifest["created_at"] == "2026-09-13T10:00:00.000000+00:00"
    assert manifest["completed_at"] == manifest["created_at"]
    assert manifest["files"] == [{
        "source": "fpl_api",
        "request_started_at": "2026-09-13T09:59:59.000000+00:00",
        "retrieved_at": "2026-09-13T10:00:00.000000+00:00",
        "relative_path": "raw/fpl_api/response.bin",
        "sha256": hashlib.sha256(RAW).hexdigest(),
        "size_bytes": len(RAW),
        "http_status": 200,
        "outcome": "success",
        "required": True,
    }]
    assert (final / manifest["files"][0]["relative_path"]).read_bytes() == RAW
    assert not writer.staging_path.exists()


def test_finalized_manifest_and_payload_cannot_be_changed_by_api(writer):
    write_response(writer)
    final = writer.finalize()
    before = {p.relative_to(final): p.read_bytes() for p in final.rglob("*") if p.is_file()}
    with pytest.raises(SnapshotStateError):
        write_response(writer, b"replacement")
    with pytest.raises(SnapshotStateError):
        writer.finalize()
    with pytest.raises(SnapshotStateError):
        writer.record_failure(source="optional_api", required=False)
    detached_manifest = verify_snapshot(final)
    detached_manifest["files"][0]["source"] = "edited"
    assert before == {
        p.relative_to(final): p.read_bytes() for p in final.rglob("*") if p.is_file()
    }
    assert verify_snapshot(final)["files"][0]["source"] == "fpl_api"


def test_cannot_recreate_finalized_run(writer, monkeypatch):
    write_response(writer)
    final = writer.finalize()
    manifest_before = (final / "manifest.json").read_bytes()
    monkeypatch.setattr(io, "uuid4", lambda: UUID(writer.run_id))
    with pytest.raises(FileExistsError):
        SnapshotWriter(final.parent, clock=lambda: NOW)
    assert (final / "manifest.json").read_bytes() == manifest_before
    verify_snapshot(final)


@pytest.mark.parametrize("existing_file", [False, True])
def test_publication_never_replaces_existing_destination(writer, existing_file):
    write_response(writer)
    writer.final_path.mkdir()
    if existing_file:
        (writer.final_path / "keep.txt").write_bytes(b"existing")
    with pytest.raises(FileExistsError):
        writer.finalize()
    if existing_file:
        assert (writer.final_path / "keep.txt").read_bytes() == b"existing"
    else:
        assert list(writer.final_path.iterdir()) == []
    assert read_staging_manifest(writer)["status"] == "failed"


@pytest.mark.parametrize("replacement", [b"x" * len(RAW), b"short"])
def test_verification_detects_raw_checksum_and_size_changes(writer, replacement):
    write_response(writer)
    final = writer.finalize()
    (final / "raw/fpl_api/response.bin").write_bytes(replacement)
    with pytest.raises(SnapshotIntegrityError):
        verify_snapshot(final)


def test_verification_detects_external_manifest_edit(writer):
    write_response(writer)
    final = writer.finalize()
    manifest = verify_snapshot(final)
    manifest["files"][0]["required"] = False
    (final / "manifest.json").write_text(json.dumps(manifest))
    with pytest.raises(SnapshotIntegrityError):
        verify_snapshot(final)


@pytest.mark.parametrize("exception", [OSError, KeyboardInterrupt])
def test_interrupted_raw_write_stays_failed_and_unpublishable(writer, monkeypatch, exception):
    original = io._write_new

    def interrupt(path, data):
        if path.name == "response.bin":
            with path.open("xb") as stream:
                stream.write(data[:3])
            raise exception("simulated interruption")
        original(path, data)

    monkeypatch.setattr(io, "_write_new", interrupt)
    with pytest.raises(exception):
        write_response(writer)
    assert (writer.staging_path / "raw/fpl_api/response.bin").read_bytes() == RAW[:3]
    assert read_staging_manifest(writer)["status"] == "failed"
    assert read_staging_manifest(writer)["files"] == []
    assert not writer.final_path.exists()
    with pytest.raises(SnapshotStateError):
        writer.finalize()
    with pytest.raises(SnapshotIntegrityError):
        verify_snapshot(writer.staging_path)


def test_interrupted_publication_has_no_valid_completion_marker(writer, monkeypatch):
    write_response(writer)
    original = io.os.link

    def interrupt(source, destination):
        if destination.name == "COMPLETE":
            # Even though all other files exist, this is not yet consumable.
            with pytest.raises(SnapshotIntegrityError):
                verify_snapshot(writer.final_path)
            with monkeypatch.context() as context:
                context.chdir(writer.staging_path)
                with pytest.raises(SnapshotIntegrityError):
                    verify_snapshot(Path("."))
            raise OSError("simulated publication failure")
        original(source, destination)

    monkeypatch.setattr(io.os, "link", interrupt)
    with pytest.raises(OSError):
        writer.finalize()
    assert writer.final_path.exists()
    assert not (writer.final_path / "COMPLETE").exists()
    assert read_staging_manifest(writer)["status"] == "failed"
    with pytest.raises(SnapshotIntegrityError):
        verify_snapshot(writer.final_path)


def test_manifest_disk_failure_cannot_publish(writer, monkeypatch):
    def disk_failure(*args):
        raise OSError("disk unavailable")

    monkeypatch.setattr(io.os, "replace", disk_failure)
    with pytest.raises(OSError):
        write_response(writer)
    assert read_staging_manifest(writer)["status"] == "staging"
    assert not writer.final_path.exists()
    with pytest.raises(SnapshotStateError):
        writer.finalize()


def test_staging_and_abandoned_runs_are_not_complete(writer):
    write_response(writer)
    assert not writer.final_path.exists()
    with pytest.raises(SnapshotIntegrityError):
        verify_snapshot(writer.staging_path)


def test_empty_run_cannot_complete(writer):
    with pytest.raises(SnapshotStateError):
        writer.finalize()
    assert read_staging_manifest(writer)["status"] == "failed"


def test_duplicate_raw_path_is_not_overwritten(writer):
    write_response(writer)
    with pytest.raises(FileExistsError):
        write_response(writer, b"replacement")
    assert (writer.staging_path / "raw/fpl_api/response.bin").read_bytes() == RAW
    with pytest.raises(SnapshotStateError):
        writer.finalize()


@pytest.mark.parametrize("extra", [False, True])
def test_finalization_rechecks_payload_integrity(writer, extra):
    write_response(writer)
    if extra:
        (writer.staging_path / "untracked.bin").write_bytes(b"untracked")
    else:
        (writer.staging_path / "raw/fpl_api/response.bin").write_bytes(b"corrupt")
    with pytest.raises(ValueError):
        writer.finalize()
    assert not writer.final_path.exists()


@pytest.mark.parametrize("required", [False, True])
@pytest.mark.parametrize("outcome", ["request_failed", "skipped"])
def test_required_failures_block_completion_optional_failures_are_recorded(
    writer, required, outcome
):
    write_response(writer)
    writer.record_failure(source="additional_api", required=required, outcome=outcome)
    if required:
        with pytest.raises(SnapshotStateError):
            writer.finalize()
    else:
        manifest = verify_snapshot(writer.finalize())
        assert manifest["failures"][0] == {
            "source": "additional_api", "required": False, "outcome": outcome,
            "recorded_at": "2026-09-13T10:00:00.000000+00:00",
        }


@pytest.mark.parametrize("required", [False, True])
def test_http_error_body_is_preserved_with_outcome(writer, required):
    write_response(writer, b"service unavailable", http_status=503, required=required)
    if required:
        with pytest.raises(SnapshotStateError):
            writer.finalize()
    else:
        manifest = verify_snapshot(writer.finalize())
        assert manifest["files"][0]["outcome"] == "http_error"
        assert manifest["files"][0]["http_status"] == 503
        body = (writer.final_path / "raw/fpl_api/response.bin").read_bytes()
        assert body == b"service unavailable"


def test_non_http_file_and_empty_response_are_supported(writer):
    write_response(writer, b"", http_status=None)
    record = verify_snapshot(writer.finalize())["files"][0]
    assert record["http_status"] is None
    assert record["size_bytes"] == 0
    assert record["sha256"] == hashlib.sha256(b"").hexdigest()


def test_timezone_offsets_are_normalized_to_utc(writer):
    local = NOW.astimezone(timezone(timedelta(hours=2)))
    write_response(writer, request_started_at=local - timedelta(seconds=1), retrieved_at=local)
    record = verify_snapshot(writer.finalize())["files"][0]
    assert record["retrieved_at"] == "2026-09-13T10:00:00.000000+00:00"


@pytest.mark.parametrize("field", ["request_started_at", "retrieved_at"])
def test_naive_request_timestamps_are_rejected(writer, field):
    with pytest.raises(ValueError, match="timezone-aware"):
        write_response(writer, **{field: NOW.replace(tzinfo=None)})


def test_naive_clock_rejected_before_directory_creation(tmp_path):
    with pytest.raises(ValueError, match="timezone-aware"):
        SnapshotWriter(tmp_path / "raw", clock=lambda: NOW.replace(tzinfo=None))
    assert not (tmp_path / "raw").exists()


def test_request_timestamp_order_and_future_retrieval_are_rejected(writer):
    with pytest.raises(ValueError, match="precede"):
        write_response(writer, request_started_at=NOW + timedelta(seconds=1))
    write_response(writer, retrieved_at=NOW + timedelta(seconds=1))
    with pytest.raises(ValueError, match="precede"):
        writer.finalize()


@pytest.mark.parametrize("path", ["../escape", "/absolute", "a/../b", "a//b", "", ".", "a\\b"])
def test_unsafe_paths_rejected(writer, path):
    with pytest.raises(ValueError):
        writer.write_raw(path, RAW, source="fpl_api", request_started_at=NOW,
                         retrieved_at=NOW, required=True)
    assert read_staging_manifest(writer)["files"] == []


def test_symlink_cannot_redirect_raw_write(writer, tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    (writer.staging_path / "raw").symlink_to(outside, target_is_directory=True)
    with pytest.raises(ValueError, match="Symlinks"):
        write_response(writer)
    assert list(outside.iterdir()) == []


def test_credentials_are_not_logged_or_accepted_as_request_metadata(writer, capsys, caplog):
    secret = "https://example.test/?token=SECRET"
    with pytest.raises(ValueError) as error:
        write_response(writer, source=secret)
    assert "SECRET" not in str(error.value)
    with pytest.raises(ValueError):
        writer.record_failure(source="fpl_api", required=False, outcome=secret)
    write_response(writer, b"response bytes may contain SECRET")
    final = writer.finalize()
    assert "SECRET" not in (final / "manifest.json").read_text()
    assert capsys.readouterr() == ("", "")
    assert not caplog.records


def test_legacy_path_helper_creates_only_incomplete_staging_runs(tmp_path):
    first, second = snapshot_dir(tmp_path), snapshot_dir(tmp_path)
    assert first != second
    assert first.parent.name == ".staging"
    with pytest.raises(SnapshotIntegrityError):
        verify_snapshot(first)
