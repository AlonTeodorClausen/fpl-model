"""One immutable multi-source run; no datasets or modelling.

Canonical manifest status=complete means safely published. run_metadata.overall
distinguishes complete coverage (success/expected skips) from partial coverage
(optional failures). Both are verified, published snapshots. Required failures
leave status=failed in staging, without COMPLETE. No new publication states.

CLI exit codes: 0 complete/partial (required baseline usable), 1 failed including
storage/publication errors, 2 invalid CLI configuration, 130 interrupted.
Only disabled sources and missing football-data.org credentials are expected
skips. Retries that eventually succeed count as success; attempt errors remain.
"""

import argparse
import json
import re
import sys
from dataclasses import dataclass
from datetime import date
from pathlib import Path

# Support direct invocation from an uninstalled checkout as well as module use.
if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from fpl_model.config import DATA
from fpl_model.io import SnapshotError, SnapshotWriter
from fpl_model.data_sources.fpl_api import fetch_fpl_snapshot
from fpl_model.data_sources.fpl_core import fetch_fpl_core_master
from fpl_model.data_sources.football_data_uk import fetch_upcoming_odds
from fpl_model.data_sources.football_data_org import fetch_competition_matches
from fpl_model.data_sources.clubelo import fetch_clubelo


SOURCE_POLICY = {
    "fpl_api": True,
    "fpl_core": False,
    "football_data_uk": False,
    "football_data_org": False,
    "clubelo": False,
}
LABELS = {
    "fpl_api": "FPL API", "fpl_core": "FPL Core",
    "football_data_uk": "Football-Data.co.uk", "football_data_org": "football-data.org",
    "clubelo": "ClubElo",
}
OPTIONAL_SOURCES = tuple(source for source, required in SOURCE_POLICY.items() if not required)


@dataclass(frozen=True)
class RunConfig:
    season: str
    data_root: Path
    core_commit_sha: str | None = None
    clubelo_date: date | None = None
    disabled: frozenset[str] = frozenset()

    def validate(self) -> None:
        if (
            not re.fullmatch(r"[0-9]{4}-[0-9]{4}", self.season)
            or int(self.season[5:]) != int(self.season[:4]) + 1
        ):
            raise ValueError("season must be consecutive YYYY-YYYY")
        if not self.disabled.issubset(OPTIONAL_SOURCES):
            raise ValueError("only optional sources may be disabled")
        if "fpl_core" not in self.disabled and (
            self.core_commit_sha is None or not re.fullmatch(r"[0-9a-fA-F]{40}", self.core_commit_sha)
        ):
            raise ValueError("enabled FPL Core requires --core-commit with a full Git SHA")
        if "clubelo" not in self.disabled and type(self.clubelo_date) is not date:
            raise ValueError("enabled ClubElo requires an explicit --clubelo-date")


@dataclass(frozen=True)
class SourceOutcome:
    status: str
    detail: str = ""


@dataclass(frozen=True)
class RunResult:
    snapshot_id: str
    path: Path
    sources: dict[str, SourceOutcome]
    overall: str
    exit_code: int


def _manifest(writer: SnapshotWriter) -> dict:
    return json.loads((writer.staging_path / "manifest.json").read_bytes())


def _failure_detail(writer: SnapshotWriter, source: str) -> str:
    # Only locally generated labels and integer HTTP codes, never exception text.
    data = _manifest(writer)
    files = [entry for entry in data["files"] if entry["source"] == source]
    failures = [entry for entry in data["failures"] if entry["source"] == source]
    if files and files[-1]["outcome"] == "http_error":
        return f"HTTP {files[-1]['http_status']}"
    if any(entry.get("error_code") == "invalid_payload" for entry in failures):
        return "invalid payload"
    if any(entry.get("error_code") == "timeout" for entry in failures):
        return "timeout"
    return "source error"


def _invoke(source: str, writer: SnapshotWriter, config: RunConfig) -> SourceOutcome:
    if source == "fpl_api":
        fetch_fpl_snapshot(writer)
        return SourceOutcome("success")
    if source == "fpl_core":
        outcomes = fetch_fpl_core_master(
            writer, season=config.season, commit_sha=config.core_commit_sha,
        )
        return SourceOutcome("success" if all(v == "success" for v in outcomes.values()) else "failed")
    if source == "football_data_uk":
        result = fetch_upcoming_odds(writer)
    elif source == "football_data_org":
        results = [fetch_competition_matches(code, writer) for code in ("PL", "CL")]
        if all(r.status == "skipped" for r in results):
            failures = [f for f in _manifest(writer)["failures"] if f["source"] == source]
            if len(failures) == 2 and all(
                f["outcome"] == "skipped" and f.get("error_code") == "missing_token"
                for f in failures
            ):
                return SourceOutcome("skipped", "missing token")
        return SourceOutcome("success" if all(r.status == "success" for r in results) else "failed")
    else:
        result = fetch_clubelo(writer, config.clubelo_date)
    return SourceOutcome("success" if result.status == "success" else "failed")


def _report_metadata(config: RunConfig, outcomes: dict[str, SourceOutcome], overall: str | None) -> dict:
    values = {
        "season": config.season,
        "required_sources": "fpl_api", "optional_sources": ",".join(OPTIONAL_SOURCES),
        "disabled_optional_sources": ",".join(s for s in OPTIONAL_SOURCES if s in config.disabled),
        **{source: result.status for source, result in outcomes.items()},
    }
    if "fpl_core" not in config.disabled:
        values["core_commit_sha"] = config.core_commit_sha.lower()
    if "clubelo" not in config.disabled:
        values["clubelo_requested_rating_date"] = config.clubelo_date.isoformat()
    if overall is not None:
        values["overall"] = overall
    return values


def run_snapshot(config: RunConfig) -> RunResult:
    config.validate()  # Reject configuration before creating a run or making requests.
    writer = SnapshotWriter(Path(config.data_root) / "raw")
    outcomes = {source: SourceOutcome("not_run") for source in SOURCE_POLICY}
    fatal = False
    try:
        writer.set_run_metadata(_report_metadata(config, outcomes, None))
        for source, required in SOURCE_POLICY.items():
            if fatal or source in config.disabled:
                reason = "required source failed" if fatal else "disabled"
                writer.record_failure(
                    source=source, required=required, outcome="skipped",
                    error_code="required_source_failed" if fatal else "disabled",
                )
                outcomes[source] = SourceOutcome("skipped", reason)
                continue
            with writer.source_scope(source, required=required):
                try:
                    outcome = _invoke(source, writer, config)
                except (OSError, KeyboardInterrupt, SystemExit) as error:
                    detail = "interrupted" if isinstance(error, (KeyboardInterrupt, SystemExit)) else "storage error"
                    outcomes[source] = SourceOutcome("failed", detail)
                    try:
                        pin = _manifest(writer).get("source_commits", {}).get(source)
                        writer.record_failure(
                            source=source, required=required, commit_sha=pin,
                            error_code="interrupted" if detail == "interrupted" else "storage_error",
                        )
                    except (OSError, SnapshotError):
                        pass
                    raise  # Storage/interruption is a run failure, never optional coverage loss.
                except Exception:
                    outcome = SourceOutcome("failed")
                if outcome.status == "failed":
                    outcome = SourceOutcome("failed", _failure_detail(writer, source))
                    # Aggregate source failure also covers adapter exceptions before an HTTP record.
                    pin = _manifest(writer).get("source_commits", {}).get(source)
                    writer.record_failure(
                        source=source, required=required, error_code="source_failed", commit_sha=pin,
                    )
                    fatal = required
                outcomes[source] = outcome
        overall = "failed" if fatal else (
            "partial" if any(result.status == "failed" for result in outcomes.values()) else "complete"
        )
        writer.set_run_metadata(_report_metadata(config, outcomes, overall))
        if fatal:
            writer.mark_failed()
            path = writer.staging_path
        else:
            path = writer.finalize()  # Sole publication call, exactly once on complete/partial runs.
        return RunResult(writer.run_id, path, outcomes, overall, 1 if fatal else 0)
    except (OSError, SnapshotError, ValueError, KeyboardInterrupt, SystemExit) as error:
        interrupted = isinstance(error, (KeyboardInterrupt, SystemExit))
        # A storage failure may already have closed the writer. Preserve whatever
        # could be written, and never turn publication/storage failure into partial.
        writer.mark_failed(run_metadata=_report_metadata(config, outcomes, "failed"))
        return RunResult(writer.run_id, writer.staging_path, outcomes, "failed", 130 if interrupted else 1)


def _rating_date(value: str) -> date:
    try:
        parsed = date.fromisoformat(value)
        if parsed.isoformat() != value:
            raise ValueError
        return parsed
    except ValueError:
        raise argparse.ArgumentTypeError("expected YYYY-MM-DD") from None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--season", required=True, help="Core season as YYYY-YYYY")
    parser.add_argument("--data-root", type=Path, default=DATA, help="snapshot runs go under DATA_ROOT/raw")
    parser.add_argument("--core-commit", help="explicit full Git SHA; required unless fpl_core is disabled")
    parser.add_argument("--clubelo-date", type=_rating_date, help="explicit rating date YYYY-MM-DD")
    parser.add_argument("--disable", action="append", default=[], choices=OPTIONAL_SOURCES)
    args = parser.parse_args(argv)
    config = RunConfig(args.season, args.data_root, args.core_commit, args.clubelo_date, frozenset(args.disable))
    try:
        config.validate()
    except ValueError as error:
        parser.error(str(error))  # Only fixed configuration validation messages.
    try:
        result = run_snapshot(config)
    except OSError:
        print("overall: failed (snapshot storage unavailable)")
        return 1
    print(f"snapshot_id: {result.snapshot_id}")
    for source, outcome in result.sources.items():
        detail = f" ({outcome.detail})" if outcome.detail else ""
        print(f"{LABELS[source]}: {outcome.status}{detail}")
    print(f"overall: {result.overall}")
    print(f"snapshot_path: {result.path}")
    return result.exit_code


if __name__ == "__main__":
    raise SystemExit(main())
