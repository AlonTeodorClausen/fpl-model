"""Local, single-writer raw snapshots. No network calls or credential metadata.

Consumers must use verify_snapshot: a directory or manifest alone is not complete.
Immutability is enforced by this API, not OS permissions. Hashes detect external
edits; this is not a tamper-proof or archival WORM filesystem.
"""

import hashlib
import json
import os
import re
import shutil
from collections.abc import Callable
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from urllib.parse import urlsplit
from uuid import UUID, uuid4


class SnapshotError(RuntimeError):
    """Snapshot lifecycle or integrity failure."""


class SnapshotStateError(SnapshotError):
    """An operation is not allowed for this run's state."""


class SnapshotIntegrityError(SnapshotError):
    """A snapshot is incomplete, corrupt, or inconsistent."""


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _timestamp(value: datetime) -> str:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("Timestamps must be timezone-aware")
    return value.astimezone(timezone.utc).isoformat(timespec="microseconds")


def _parse_timestamp(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    if _timestamp(parsed) != value:
        raise ValueError("Expected a canonical UTC timestamp")
    return parsed


def _source(value: str) -> None:
    # Accept an identifier, never a URL, auth header or exception message.
    if not isinstance(value, str) or not re.fullmatch(r"[a-z][a-z0-9_-]{0,63}", value):
        raise ValueError("Source must be a short lowercase identifier")


def _relative_path(value: str) -> str:
    path = PurePosixPath(value)
    if (
        not value or path.is_absolute() or ".." in path.parts or "\\" in value
        or "\x00" in value or str(path) != value or value == "."
    ):
        raise ValueError("Expected a normalized relative POSIX file path")
    return value


def _request_url(value: str) -> str:
    """Only accept public endpoint URLs, never credentials or query parameters.

    Callers must use fixed public paths, not paths containing secrets. Headers,
    redirect locations and exception messages are deliberately not accepted.
    """
    if not isinstance(value, str) or any(character.isspace() for character in value):
        raise ValueError("Expected a public HTTP endpoint URL")
    try:
        parsed = urlsplit(value)
    except ValueError:
        # Some urllib errors echo the supplied authority, potentially including
        # credentials. Keep validation failures as safe as stored metadata.
        raise ValueError("Expected a public HTTP endpoint URL") from None
    if (
        parsed.scheme not in {"http", "https"} or not parsed.hostname
        or parsed.username is not None or parsed.password is not None
        or "?" in value or "#" in value
    ):
        raise ValueError("Endpoint URL cannot contain credentials, query or fragment")
    return value


def _outcome(http_status: int | None) -> str:
    if http_status is None:
        return "success"
    if type(http_status) is not int or not 100 <= http_status <= 599:
        raise ValueError("HTTP status must be an integer from 100 to 599")
    return "success" if 200 <= http_status < 300 else "http_error"


def _public_request_metadata(
    request_params: dict[str, str] | None, request_context: dict[str, str] | None,
) -> dict:
    """Copy public, caller-allowlisted request metadata, never headers or credentials.

    Adapters must construct these mappings from known public fields; passing an
    arbitrary request/header/environment mapping is forbidden. The key check is
    defense in depth, not a general-purpose secret detector.
    """
    result = {}
    for name, values in (("request_params", request_params), ("request_context", request_context)):
        if values is None:
            continue
        if not isinstance(values, dict):
            raise ValueError("Expected public request metadata mappings")
        for key, value in values.items():
            if (
                not isinstance(key, str) or not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{0,63}", key)
                or any(word in key.lower() for word in ("token", "auth", "password", "secret", "cookie", "key"))
                or not isinstance(value, str) or len(value) > 128
                or any(ord(char) < 32 for char in value)
            ):
                raise ValueError("Invalid public request metadata")
        result[name] = dict(values)
    return result


def _commit_sha(value: str) -> str:
    if not isinstance(value, str) or not re.fullmatch(r"[0-9a-fA-F]{40}", value):
        raise ValueError("Expected an explicit full 40-character Git commit SHA")
    return value.lower()


def _write_new(path: Path, data: bytes) -> None:
    """Exclusive writes leave interrupted files for diagnosis, never for reuse."""
    with path.open("xb") as stream:
        if stream.write(data) != len(data):
            raise OSError("Incomplete snapshot write")
        stream.flush()
        os.fsync(stream.fileno())


def _digest(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def _verify_files(directory: Path, files: list[dict], control_files: set[str]) -> None:
    actual = set()
    for path in directory.rglob("*"):
        if path.is_symlink():
            raise ValueError("Symlinks are not allowed inside snapshots")
        if path.is_file():
            actual.add(path.relative_to(directory).as_posix())
    expected = set(control_files)
    for entry in files:
        relative = _relative_path(entry["relative_path"])
        if not relative.startswith("raw/") or relative in expected:
            raise ValueError("Invalid or duplicate raw file path")
        expected.add(relative)
        path = directory / relative
        if type(entry["size_bytes"]) is not int or entry["size_bytes"] < 0:
            raise ValueError("Invalid byte size")
        if not re.fullmatch(r"[0-9a-f]{64}", entry["sha256"]):
            raise ValueError("Invalid SHA-256")
        if path.stat().st_size != entry["size_bytes"] or _digest(path) != entry["sha256"]:
            raise ValueError("Raw file checksum or size mismatch")
    if actual != expected:
        raise ValueError("Missing or untracked snapshot files")


class SnapshotWriter:
    """Create a run; write raw bytes; finalize once; verify before consumption.

    No append/resume API exists. Failed runs require a new run ID. Required
    failures prevent completion; optional failures are retained in the manifest.
    Callers must record every intended request, including failures/skips.
    """

    def __init__(self, raw_root: Path, *, clock: Callable[[], datetime] = _utc_now):
        self._clock = clock
        self._created_at = _timestamp(clock())
        self._run_id = uuid4().hex
        stamp = _parse_timestamp(self._created_at).strftime("%Y-%m-%d_%H%M%S%fZ")
        name = f"{stamp}_{self._run_id}"
        root = Path(raw_root).resolve()
        if (root / ".staging").is_symlink():
            raise ValueError("Staging root cannot be a symlink")
        self._staging_path = root / ".staging" / name
        self._final_path = root / name
        self._files: list[dict] = []
        self._failures: list[dict] = []
        self._source_commits: dict[str, str] = {}
        self._active_source: tuple[str, bool] | None = None
        self._run_metadata: dict[str, str] = {}
        self._state = "staging"
        self._completed_at: str | None = None
        if self.final_path.exists():
            raise FileExistsError("Snapshot destination already exists")
        self.staging_path.mkdir(parents=True, exist_ok=False)
        self._write_manifest()

    @property
    def run_id(self) -> str:
        return self._run_id

    @property
    def staging_path(self) -> Path:
        return self._staging_path

    @property
    def final_path(self) -> Path:
        return self._final_path

    def _ensure_open(self) -> None:
        if self._state != "staging":
            raise SnapshotStateError("Run is closed; create a new snapshot")

    @contextmanager
    def source_scope(self, source: str, *, required: bool):
        """Bind adapter writes to one namespace and explicit run criticality.

        The same writer is passed to every adapter. Local file requirements are
        retained as adapter_required when overridden by an optional source policy.
        This is an API guard, not a sandbox against arbitrary filesystem access.
        """
        self._ensure_open()
        _source(source)
        if type(required) is not bool or self._active_source is not None:
            raise SnapshotStateError("Invalid or nested source scope")
        self._active_source = (source, required)
        try:
            yield self
        finally:
            self._active_source = None

    def _source_requirement(self, source: str, required: bool) -> tuple[bool, dict]:
        if self._active_source is None:
            return required, {}
        active, source_required = self._active_source
        if source != active:
            raise SnapshotStateError("Adapter cannot write another source's provenance")
        effective = source_required and required
        return effective, ({"adapter_required": required} if effective != required else {})

    def set_run_metadata(self, values: dict[str, str]) -> None:
        """Store detached public orchestration settings/report before publication."""
        self._ensure_open()
        if self._active_source is not None:
            raise SnapshotStateError("Only the runner may change run metadata")
        metadata = _public_request_metadata(None, values)["request_context"]
        self._run_metadata = metadata
        try:
            self._write_manifest()
        except BaseException:
            self._mark_failed()
            raise

    def mark_failed(self, *, run_metadata: dict[str, str] | None = None) -> None:
        """Close a run, retaining bytes and optionally recording its failure report.

        Failed staging runs may receive their final runner report even when an
        I/O/integrity error already closed the writer. Published runs cannot.
        """
        if self._active_source is not None:
            raise SnapshotStateError("Only the runner may close the run")
        if self._state != "failed":
            self._ensure_open()
        if run_metadata is not None:
            self._run_metadata = _public_request_metadata(None, run_metadata)["request_context"]
        elif self._state == "failed":
            return
        self._mark_failed()

    def pin_source_commit(self, source: str, commit_sha: str) -> str:
        """Fix a source's commit for this entire run, before requesting its files.

        A second commit or previously unversioned files from that source are
        rejected. The pin also survives requests which return no response body.
        """
        self._ensure_open()
        _source(source)
        if self._active_source is not None and source != self._active_source[0]:
            raise SnapshotStateError("Adapter cannot pin another source")
        sha = _commit_sha(commit_sha)
        if source in self._source_commits:
            if self._source_commits[source] != sha:
                raise ValueError("A source cannot mix Git commits within one snapshot run")
            return sha
        if any(entry["source"] == source for entry in [*self._files, *self._failures]):
            raise ValueError("Cannot pin a source after recording unversioned observations")
        self._source_commits[source] = sha
        try:
            self._write_manifest()
        except BaseException:
            self._mark_failed()
            raise
        return sha

    def _commit_provenance(self, source: str, commit_sha: str | None) -> dict:
        if commit_sha is None:
            if source in self._source_commits:
                raise ValueError("Pinned source observations require a commit SHA")
            return {}
        return {"commit_sha": self.pin_source_commit(source, commit_sha)}

    def _write_manifest(self) -> None:
        manifest = {
            "schema_version": 1,
            "run_id": self.run_id,
            "status": self._state,
            "created_at": self._created_at,
            "completed_at": self._completed_at,
            "files": self._files,
            "failures": self._failures,
            **({"source_commits": self._source_commits} if self._source_commits else {}),
            **({"run_metadata": self._run_metadata} if self._run_metadata else {}),
        }
        payload = (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode("utf-8")
        temporary = self.staging_path / f".manifest-{uuid4().hex}.tmp"
        _write_new(temporary, payload)
        # Replacement is permitted only in staging, never in a published run.
        os.replace(temporary, self.staging_path / "manifest.json")

    def _mark_failed(self) -> None:
        self._state = "failed"
        self._completed_at = None
        try:
            self._write_manifest()
        except OSError:
            # Disk failure may prevent recording status. Staging/no COMPLETE
            # still distinguishes the run. Never log exception text.
            pass

    def write_raw(
        self,
        relative_path: str,
        data: bytes,
        *,
        source: str,
        request_started_at: datetime,
        retrieved_at: datetime,
        required: bool,
        http_status: int | None = None,
        request_url: str | None = None,
        commit_sha: str | None = None,
        content_type: str | None = None,
        available_at: datetime | None = None,
        request_params: dict[str, str] | None = None,
        request_context: dict[str, str] | None = None,
    ) -> None:
        self._ensure_open()
        _source(source)
        relative = "raw/" + _relative_path(relative_path)
        if not isinstance(data, bytes) or type(required) is not bool:
            raise TypeError("Expected raw bytes and a boolean required flag")
        required, policy = self._source_requirement(source, required)
        if self._active_source is not None and not relative.startswith(f"raw/{source}/"):
            raise SnapshotStateError("Adapter raw files must stay in their source namespace")
        started, retrieved = _timestamp(request_started_at), _timestamp(retrieved_at)
        if retrieved < started:
            raise ValueError("Retrieval cannot precede request start")
        outcome = _outcome(http_status)
        provenance = {} if request_url is None else {"request_url": _request_url(request_url)}
        provenance.update(_public_request_metadata(request_params, request_context))
        provenance.update(policy)
        if content_type is not None:
            if not isinstance(content_type, str) or "\r" in content_type or "\n" in content_type:
                raise ValueError("Expected a single Content-Type header value")
            provenance["content_type"] = content_type
        if available_at is not None:
            available = _timestamp(available_at)
            if available < retrieved:
                raise ValueError("Availability cannot precede local retrieval")
            provenance["available_at"] = available
        provenance.update(self._commit_provenance(source, commit_sha))
        path = self.staging_path / relative
        try:
            if any(parent.is_symlink() for parent in (path, *path.parents)):
                raise ValueError("Symlinks are not allowed in snapshot write paths")
            path.parent.mkdir(parents=True, exist_ok=True)
            _write_new(path, data)
            self._files.append({
                "source": source,
                "request_started_at": started,
                "retrieved_at": retrieved,
                "relative_path": relative,
                "sha256": hashlib.sha256(data).hexdigest(),
                "size_bytes": len(data),
                "http_status": http_status,
                "outcome": outcome,
                "required": required,
                **provenance,
            })
            self._write_manifest()
        except BaseException:
            self._mark_failed()
            raise

    def record_failure(
        self, *, source: str, required: bool, outcome: str = "request_failed",
        request_url: str | None = None, request_started_at: datetime | None = None,
        commit_sha: str | None = None,
        error_code: str | None = None, relative_path: str | None = None,
        request_params: dict[str, str] | None = None,
        request_context: dict[str, str] | None = None,
    ) -> None:
        """Record request_failed or skipped without a body or exception message.

        Raw HTTP bodies must be stored with write_raw first. Optional error_code
        is a short identifier, never exception text. relative_path can associate
        a validation/error record with an already stored response from this source.
        """
        self._ensure_open()
        _source(source)
        if type(required) is not bool or outcome not in {"request_failed", "skipped"}:
            raise ValueError("Invalid request failure metadata")
        required, policy = self._source_requirement(source, required)
        provenance = {} if request_url is None else {"request_url": _request_url(request_url)}
        provenance.update(policy)
        provenance.update(_public_request_metadata(request_params, request_context))
        if error_code is not None:
            _source(error_code)
            provenance["error_code"] = error_code
        if relative_path is not None:
            _relative_path(relative_path)
            if not any(
                entry["relative_path"] == relative_path and entry["source"] == source
                for entry in self._files
            ):
                raise ValueError("Failure must reference a stored response from the same source")
            provenance["relative_path"] = relative_path
        recorded_at = _timestamp(self._clock())
        if request_started_at is not None:
            started_at = _timestamp(request_started_at)
            if started_at > recorded_at:
                raise ValueError("Failure cannot precede request start")
            provenance["request_started_at"] = started_at
        provenance.update(self._commit_provenance(source, commit_sha))
        self._failures.append({
            "source": source,
            "required": required,
            "outcome": outcome,
            "recorded_at": recorded_at,
            **provenance,
        })
        try:
            self._write_manifest()
        except BaseException:
            self._mark_failed()
            raise

    def finalize(self) -> Path:
        """Publish with exclusive hard links and a completion marker linked last.

        Staging and destination share a filesystem. Reserving the destination
        with mkdir avoids rename's ability to replace an existing empty directory.
        Interrupted publication may leave a destination without COMPLETE; reject
        it. Hard links never replace existing files. Successful staging is removed.
        """
        self._ensure_open()
        if self._active_source is not None:
            raise SnapshotStateError("Only the runner may finalize the snapshot")
        try:
            if not self._files or any(
                entry["required"] and entry["outcome"] != "success"
                for entry in [*self._files, *self._failures]
            ):
                raise SnapshotStateError("Completion requires raw files and no required failures")
            _verify_files(self.staging_path, self._files, {"manifest.json"})
            completed_at = _timestamp(self._clock())
            latest_input = max(
                [self._created_at]
                + [entry["retrieved_at"] for entry in self._files]
                + [entry["recorded_at"] for entry in self._failures]
            )
            if completed_at < latest_input:
                raise ValueError("Completion cannot precede input timestamps")
            self._state = "complete"
            self._completed_at = completed_at
            self._write_manifest()
            digest = _digest(self.staging_path / "manifest.json")
            _write_new(self.staging_path / "COMPLETE", (digest + "\n").encode("ascii"))
            self.final_path.mkdir(exist_ok=False)
            for relative in [entry["relative_path"] for entry in self._files] + ["manifest.json"]:
                target = self.final_path / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                os.link(self.staging_path / relative, target)
            os.link(self.staging_path / "COMPLETE", self.final_path / "COMPLETE")
        except BaseException:
            self._mark_failed()
            raise
        # Publication succeeded. Cleanup failure must not change that outcome.
        try:
            shutil.rmtree(self.staging_path)
        except OSError:
            pass
        return self.final_path


def verify_snapshot(directory: Path) -> dict:
    """Verify completion, manifest digest, file hashes, sizes and metadata.

    Returns detached metadata; editing it cannot change the stored manifest.
    Raises SnapshotIntegrityError for staging, partial or corrupt snapshots.
    """
    directory = Path(directory)
    try:
        if ".staging" in directory.resolve().parts or directory.is_symlink():
            raise ValueError("Not a published snapshot directory")
        payload = (directory / "manifest.json").read_bytes()
        marker = (directory / "COMPLETE").read_bytes()
        if marker != (hashlib.sha256(payload).hexdigest() + "\n").encode("ascii"):
            raise ValueError("Manifest checksum mismatch")
        manifest = json.loads(payload)
        if manifest["schema_version"] != 1 or manifest["status"] != "complete":
            raise ValueError("Snapshot is not complete or schema is unsupported")
        if UUID(manifest["run_id"]).hex != manifest["run_id"]:
            raise ValueError("Invalid run ID")
        if "run_metadata" in manifest:
            _public_request_metadata(None, manifest["run_metadata"])
        pins = manifest.get("source_commits", {})
        if not isinstance(pins, dict):
            raise ValueError("Invalid source commit pins")
        for source, sha in pins.items():
            _source(source)
            if _commit_sha(sha) != sha:
                raise ValueError("Noncanonical commit SHA")
        for entry in [*manifest["files"], *manifest["failures"]]:
            if "adapter_required" in entry and type(entry["adapter_required"]) is not bool:
                raise ValueError("Invalid adapter file requirement")
            _public_request_metadata(entry.get("request_params"), entry.get("request_context"))
            source = entry["source"]
            if "commit_sha" in entry or source in pins:
                if source not in pins or entry.get("commit_sha") != pins[source]:
                    raise ValueError("Source observation does not match its pinned commit")
        created = _parse_timestamp(manifest["created_at"])
        completed = _parse_timestamp(manifest["completed_at"])
        if completed < created or not manifest["files"]:
            raise ValueError("Invalid completion metadata")
        for entry in manifest["files"]:
            _source(entry["source"])
            if "request_url" in entry:
                _request_url(entry["request_url"])
            if type(entry["required"]) is not bool:
                raise ValueError("Invalid required flag")
            started = _parse_timestamp(entry["request_started_at"])
            retrieved = _parse_timestamp(entry["retrieved_at"])
            if not started <= retrieved <= completed:
                raise ValueError("Invalid request timestamps")
            if "content_type" in entry:
                value = entry["content_type"]
                if not isinstance(value, str) or "\r" in value or "\n" in value:
                    raise ValueError("Invalid Content-Type metadata")
            if "available_at" in entry and _parse_timestamp(entry["available_at"]) < retrieved:
                raise ValueError("Availability cannot precede retrieval")
            if entry["outcome"] != _outcome(entry["http_status"]):
                raise ValueError("Inconsistent HTTP outcome")
            if entry["required"] and entry["outcome"] != "success":
                raise ValueError("Required request failed")
        for failure in manifest["failures"]:
            _source(failure["source"])
            if "error_code" in failure:
                _source(failure["error_code"])
            if "relative_path" in failure:
                _relative_path(failure["relative_path"])
                if not any(
                    entry["relative_path"] == failure["relative_path"]
                    and entry["source"] == failure["source"] for entry in manifest["files"]
                ):
                    raise ValueError("Failure references a missing or unrelated raw response")
            if "request_url" in failure:
                _request_url(failure["request_url"])
            if failure["required"] is not False:
                raise ValueError("Required request failed")
            if failure["outcome"] not in {"request_failed", "skipped"}:
                raise ValueError("Invalid failure outcome")
            recorded = _parse_timestamp(failure["recorded_at"])
            if recorded > completed:
                raise ValueError("Invalid failure timestamp")
            if (
                "request_started_at" in failure
                and _parse_timestamp(failure["request_started_at"]) > recorded
            ):
                raise ValueError("Invalid failure request timestamp")
        _verify_files(directory, manifest["files"], {"manifest.json", "COMPLETE"})
        return manifest
    except (OSError, ValueError, TypeError, KeyError, AttributeError):
        raise SnapshotIntegrityError(
            "Snapshot is incomplete or failed integrity verification"
        ) from None


def snapshot_dir(raw_root: Path) -> Path:
    """Legacy path-only entry point; always returns an INCOMPLETE staging run.

    Existing adapters are not yet migrated. Their writes cannot produce a valid
    completed snapshot; new callers must use SnapshotWriter and finalize explicitly.
    """
    return SnapshotWriter(raw_root).staging_path
