"""Offline integration of the real adapters and one writer, with mocked HTTP only."""

import importlib.util
import json
import sys
from dataclasses import replace
from datetime import date, datetime, timezone
from functools import partial
from pathlib import Path
from unittest.mock import MagicMock

import pytest
import requests

from fpl_model.io import SnapshotIntegrityError, SnapshotStateError, SnapshotWriter, verify_snapshot


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "fetch_snapshot.py"
SPEC = importlib.util.spec_from_file_location("fetch_snapshot_runner", SCRIPT)
runner = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = runner
SPEC.loader.exec_module(runner)
FIXTURES = Path(__file__).parent / "fixtures"
SHA = "a" * 40
TOKEN = "synthetic-secret-do-not-print"
PL = "https://api.football-data.org/v4/competitions/PL/matches"
CL = "https://api.football-data.org/v4/competitions/CL/matches"
ELO = "http://api.clubelo.com/2026-09-12"
ODDS = "https://www.football-data.co.uk/fixtures.csv"
FPL_BOOTSTRAP = "https://fantasy.premierleague.com/api/bootstrap-static/"
FPL_FIXTURES = "https://fantasy.premierleague.com/api/fixtures/"
CORE = f"https://raw.githubusercontent.com/olbauday/FPL-Core-Insights/{SHA}/data/2026-2027/"


def reply(body, status=200, content_type="application/json"):
    response = requests.Response()
    response.status_code = status
    response._content = body
    response._content_consumed = True
    response.headers["Content-Type"] = content_type
    return response


@pytest.fixture
def config(tmp_path):
    return runner.RunConfig("2026-2027", tmp_path, SHA, date(2026, 9, 12))


@pytest.fixture
def http(monkeypatch):
    """Exercise real adapter validation/storage; no HTTP calls or retry sleeps."""
    monkeypatch.setenv("FOOTBALL_DATA_ORG_TOKEN", TOKEN)
    payloads = {
        FPL_BOOTSTRAP: ((FIXTURES / "fpl/bootstrap_static.json").read_bytes(), "application/json"),
        FPL_FIXTURES: ((FIXTURES / "fpl/fixtures.json").read_bytes(), "application/json"),
        ODDS: ((FIXTURES / "football_data_uk/fixtures.csv").read_bytes(), "text/csv"),
        PL: (b'{"competition":{"code":"PL"},"matches":[]}', "application/json"),
        CL: (b'{"competition":{"code":"CL"},"matches":[]}', "application/json"),
        ELO: (b"Club,Country,Elo,Level\nExample,ENG,1700,1\n", "text/csv"),
    }
    for name in ("players.csv", "teams.csv", "playerstats.csv", "gameweek_summaries.csv"):
        payloads[CORE + name] = ((FIXTURES / "fpl_core" / name).read_bytes(), "text/plain")
    overrides, calls = {}, []

    def get(url, **kwargs):
        calls.append(url)
        assert kwargs["allow_redirects"] is False
        assert kwargs["timeout"] == (10, 30)
        if url in {PL, CL}:
            assert kwargs["headers"] == {"X-Auth-Token": TOKEN}
        if url in overrides:
            value = overrides[url]
            if isinstance(value, list):
                value = value.pop(0)
            if isinstance(value, BaseException):
                raise value
            return value
        body, content_type = payloads[url]
        return reply(body, content_type=content_type)

    def session():
        client = MagicMock()
        client.__enter__.return_value = client
        client.get.side_effect = get
        return client

    monkeypatch.setattr(requests, "Session", session)
    for name in ("fetch_upcoming_odds", "fetch_competition_matches", "fetch_clubelo"):
        monkeypatch.setattr(runner, name, partial(getattr(runner, name), sleep=lambda _: None))
    return overrides, calls


def test_all_sources_succeed_one_writer_one_finalization_and_deterministic_order(config, http, monkeypatch):
    writers, adapter_writers, finalizations = [], [], []
    original_finalize = SnapshotWriter.finalize

    def factory(root):
        writer = SnapshotWriter(root)
        writers.append(writer)
        return writer

    def finalize(writer):
        finalizations.append(writer)
        return original_finalize(writer)

    monkeypatch.setattr(runner, "SnapshotWriter", factory)
    monkeypatch.setattr(SnapshotWriter, "finalize", finalize)
    for name in ("fetch_fpl_snapshot", "fetch_fpl_core_master", "fetch_upcoming_odds",
                 "fetch_competition_matches", "fetch_clubelo"):
        original = getattr(runner, name)

        def observed(*args, _fn=original, _name=name, **kwargs):
            adapter_writers.append(args[1] if _name == "fetch_competition_matches" else args[0])
            return _fn(*args, **kwargs)

        monkeypatch.setattr(runner, name, observed)
    result = runner.run_snapshot(config)
    assert len(writers) == 1 and finalizations == writers
    assert len(adapter_writers) == 6 and all(w is writers[0] for w in adapter_writers)
    assert result.overall == "complete" and result.exit_code == 0
    data = verify_snapshot(result.path)
    assert data["status"] == data["run_metadata"]["overall"] == "complete"
    assert all(v.status == "success" for v in result.sources.values())
    assert http[1] == [FPL_BOOTSTRAP, FPL_FIXTURES] + [CORE + name for name in (
        "players.csv", "teams.csv", "playerstats.csv", "gameweek_summaries.csv",
    )] + [ODDS, PL, CL, ELO]
    assert len(data["files"]) == 10
    assert all(e["required"] == (e["source"] == "fpl_api") for e in data["files"])
    core = [e for e in data["files"] if e["source"] == "fpl_core"]
    assert all(e["adapter_required"] is True for e in core[:3])
    assert data["source_commits"] == {"fpl_core": SHA}
    assert data["run_metadata"]["season"] == config.season
    assert data["run_metadata"]["clubelo_requested_rating_date"] == "2026-09-12"
    assert result.path.parent == config.data_root / "raw"
    assert not writers[0].staging_path.exists()


@pytest.mark.parametrize("url", [CORE + "players.csv", CORE + "gameweek_summaries.csv", ODDS, PL, CL, ELO])
def test_each_optional_source_http_failure_is_partial_and_later_sources_continue(config, http, url):
    http[0][url] = reply(b"unavailable", 403)
    result = runner.run_snapshot(config)
    assert result.overall == "partial" and result.exit_code == 0
    data = verify_snapshot(result.path)
    assert data["status"] == "complete" and data["run_metadata"]["overall"] == "partial"
    assert (result.path / "raw/fpl_api/bootstrap_static.json").read_bytes() == (
        FIXTURES / "fpl/bootstrap_static.json"
    ).read_bytes()
    entry = next(e for e in data["files"] if e["request_url"] == url)
    assert entry["required"] is False
    assert (result.path / entry["relative_path"]).read_bytes() == b"unavailable"
    assert any(f["source"] == entry["source"] for f in data["failures"])
    assert all(f["required"] is False for f in data["failures"])
    assert http[1][-1] == ELO
    assert PL in http[1] and CL in http[1]


def test_retry_eventual_success_is_complete_with_attempt_failures_retained(config, http):
    body = (FIXTURES / "football_data_uk/fixtures.csv").read_bytes()
    http[0][ODDS] = [reply(b"busy", 429), reply(body, content_type="text/csv")]
    result = runner.run_snapshot(config)
    data = verify_snapshot(result.path)
    assert result.overall == "complete" and result.sources["football_data_uk"].status == "success"
    assert any(e["http_status"] == 429 for e in data["files"])
    assert any(f["source"] == "football_data_uk" for f in data["failures"])


def test_missing_token_is_explicit_expected_skip_and_complete(config, http, monkeypatch):
    monkeypatch.delenv("FOOTBALL_DATA_ORG_TOKEN")
    result = runner.run_snapshot(config)
    assert result.overall == "complete" and result.sources["football_data_org"] == runner.SourceOutcome("skipped", "missing token")
    data = verify_snapshot(result.path)
    skips = [f for f in data["failures"] if f["source"] == "football_data_org"]
    assert len(skips) == 2 and all(f["outcome"] == "skipped" for f in skips)
    assert PL not in http[1] and CL not in http[1]


def test_disabled_sources_are_explicit_skips_without_core_sha_or_clubelo_date(config, http):
    config = replace(config, disabled=frozenset(runner.OPTIONAL_SOURCES), core_commit_sha=None, clubelo_date=None)
    result = runner.run_snapshot(config)
    assert result.overall == "complete" and result.exit_code == 0
    assert http[1] == [FPL_BOOTSTRAP, FPL_FIXTURES]
    data = verify_snapshot(result.path)
    assert len(data["failures"]) == 4
    assert all(f["outcome"] == "skipped" and f["error_code"] == "disabled" for f in data["failures"])


@pytest.mark.parametrize("response", [reply(b"bad", 500), reply(b"not json"), requests.Timeout(TOKEN)])
def test_required_fpl_failure_preserves_first_response_and_marks_failed(config, http, response, monkeypatch):
    http[0][FPL_FIXTURES] = response
    finalize = MagicMock(side_effect=AssertionError("Failed runs must not publish"))
    monkeypatch.setattr(SnapshotWriter, "finalize", finalize)
    result = runner.run_snapshot(config)
    assert result.overall == "failed" and result.exit_code == 1
    assert http[1] == [FPL_BOOTSTRAP, FPL_FIXTURES]
    data = json.loads((result.path / "manifest.json").read_bytes())
    assert data["status"] == data["run_metadata"]["overall"] == "failed"
    assert any(f["source"] == "fpl_api" and f["required"] for f in data["failures"])
    assert (result.path / "raw/fpl_api/bootstrap_static.json").read_bytes() == (FIXTURES / "fpl/bootstrap_static.json").read_bytes()
    assert not (result.path / "COMPLETE").exists()
    finalize.assert_not_called()
    with pytest.raises(SnapshotIntegrityError):
        verify_snapshot(result.path)


def cli_args(config):
    return ["--season", config.season, "--data-root", str(config.data_root),
            "--core-commit", SHA, "--clubelo-date", "2026-09-12"]


def test_cli_required_failure_returns_nonzero_without_secret(config, http, capsys):
    http[0][FPL_FIXTURES] = requests.Timeout(TOKEN)
    assert runner.main(cli_args(config)) == 1
    output = capsys.readouterr().out
    assert "FPL API: failed" in output and "overall: failed" in output and TOKEN not in output


def test_cli_partial_summary_and_manifest_never_include_token(config, http, monkeypatch, capsys):
    http[0][ELO] = reply(b"", 502, "")
    assert runner.main(cli_args(config)) == 0
    output = capsys.readouterr().out
    assert "ClubElo: failed (HTTP 502)" in output and "overall: partial" in output
    assert "football-data.org: success" in output
    path = next((config.data_root / "raw").glob("*/COMPLETE")).parent
    assert TOKEN not in output + (path / "manifest.json").read_text()


def test_unexpected_optional_exception_is_safe_partial_and_preserves_required_files(config, http, monkeypatch, capsys):
    def broken(writer):
        raise RuntimeError(TOKEN)

    monkeypatch.setattr(runner, "fetch_upcoming_odds", broken)
    assert runner.main(cli_args(config)) == 0
    output = capsys.readouterr().out
    path = next((config.data_root / "raw").glob("*/COMPLETE")).parent
    data = verify_snapshot(path)
    assert data["run_metadata"]["overall"] == "partial"
    assert TOKEN not in output + json.dumps(data)
    assert any(f["source"] == "football_data_uk" and f["error_code"] == "source_failed" for f in data["failures"])


@pytest.mark.parametrize("spoof_source", ["fpl_api", "football_data_uk"])
def test_adapter_cannot_overwrite_other_source_even_with_spoofed_metadata(config, http, monkeypatch, spoof_source):
    def broken(writer):
        now = datetime.now(timezone.utc)
        writer.write_raw("fpl_api/bootstrap_static.json", b"overwrite", source=spoof_source,
                         required=False, request_started_at=now, retrieved_at=now)

    monkeypatch.setattr(runner, "fetch_upcoming_odds", broken)
    result = runner.run_snapshot(config)
    assert result.overall == "partial"
    verify_snapshot(result.path)
    assert (result.path / "raw/fpl_api/bootstrap_static.json").read_bytes() == (FIXTURES / "fpl/bootstrap_static.json").read_bytes()


def test_adapter_cannot_finalize_the_shared_writer(config, http, monkeypatch):
    def broken(writer):
        writer.finalize()

    monkeypatch.setattr(runner, "fetch_upcoming_odds", broken)
    result = runner.run_snapshot(config)
    assert result.overall == "partial"
    data = verify_snapshot(result.path)
    assert any(e["source"] == "clubelo" for e in data["files"])


@pytest.mark.parametrize("error,exit_code", [(OSError(TOKEN), 1), (KeyboardInterrupt(), 130)])
def test_storage_failure_or_interrupt_marks_failed_without_publishing(config, http, monkeypatch, error, exit_code):
    def broken(writer):
        raise error

    monkeypatch.setattr(runner, "fetch_upcoming_odds", broken)
    result = runner.run_snapshot(config)
    assert result.overall == "failed" and result.exit_code == exit_code
    data = json.loads((result.path / "manifest.json").read_bytes())
    assert data["status"] == "failed" and TOKEN not in json.dumps(data)
    assert not (result.path / "COMPLETE").exists()


def test_publication_failure_returns_failed_and_retains_captured_bytes(config, http, monkeypatch):
    monkeypatch.setattr(SnapshotWriter, "finalize", MagicMock(side_effect=OSError(TOKEN)))
    result = runner.run_snapshot(config)
    assert result.overall == "failed" and result.exit_code == 1
    data = json.loads((result.path / "manifest.json").read_bytes())
    assert data["status"] == "failed" and len(data["files"]) == 10
    assert data["run_metadata"]["overall"] == "failed"


def test_integrity_failure_during_finalization_is_a_failed_run(config, http, monkeypatch):
    original = SnapshotWriter.finalize

    def corrupt_then_finalize(writer):
        # Simulate external disk corruption, outside the writer's namespace API.
        (writer.staging_path / "raw/fpl_api/fixtures.json").write_bytes(b"corrupt")
        return original(writer)

    monkeypatch.setattr(SnapshotWriter, "finalize", corrupt_then_finalize)
    result = runner.run_snapshot(config)
    assert result.overall == "failed" and result.exit_code == 1
    data = json.loads((result.path / "manifest.json").read_bytes())
    assert data["status"] == "failed" and not (result.path / "COMPLETE").exists()
    assert data["run_metadata"]["overall"] == "failed"
    with pytest.raises(SnapshotIntegrityError):
        verify_snapshot(result.path)


@pytest.mark.parametrize("kwargs", [
    {"season": "2026-2028"}, {"core_commit_sha": "main"}, {"clubelo_date": None},
    {"disabled": frozenset({"fpl_api"})},
])
def test_invalid_run_configuration_rejected_before_writer_or_requests(config, http, kwargs):
    with pytest.raises(ValueError):
        runner.run_snapshot(replace(config, **kwargs))
    assert not (config.data_root / "raw").exists() and http[1] == []


def test_cli_invalid_configuration_exit_two_without_requests(config, http):
    with pytest.raises(SystemExit) as error:
        runner.main(["--season", "2026-2027", "--data-root", str(config.data_root)])
    assert error.value.code == 2 and http[1] == []


def test_finalized_run_report_cannot_be_changed(config, http):
    result = runner.run_snapshot(config)
    data = verify_snapshot(result.path)
    assert data["run_metadata"]["overall"] == "complete"
    (result.path / "manifest.json").write_text((result.path / "manifest.json").read_text().replace('"overall": "complete"', '"overall": "partial"'))
    with pytest.raises(SnapshotIntegrityError):
        verify_snapshot(result.path)


def test_scope_and_runner_metadata_are_closed_after_finalization(tmp_path):
    writer = SnapshotWriter(tmp_path)
    now = datetime.now(timezone.utc)
    metadata = {"season": "2026-2027"}
    writer.set_run_metadata(metadata)
    metadata["season"] = "1999-2000"
    with writer.source_scope("test", required=False):
        writer.write_raw("test/file", b"x", source="test", required=True,
                         request_started_at=now, retrieved_at=now)
        with pytest.raises(SnapshotStateError):
            writer.set_run_metadata({})
        with pytest.raises(SnapshotStateError):
            writer.mark_failed()
    data = verify_snapshot(writer.finalize())
    assert data["run_metadata"]["season"] == "2026-2027"
    assert data["files"][0]["required"] is False and data["files"][0]["adapter_required"] is True
    with pytest.raises(SnapshotStateError):
        writer.set_run_metadata({})
    with pytest.raises(SnapshotStateError):
        writer.mark_failed()
