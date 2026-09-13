"""Opt-in Core check at a fixed reviewed revision; no branch lookup at runtime.

Run: python -m pytest tests/test_fpl_core_live.py -m live -q
Four public CSV requests, all stored in pytest temporary directories.
"""

import pytest

from fpl_model.data_sources.fpl_core import MASTER_FILES, fetch_fpl_core_master
from fpl_model.io import SnapshotWriter, verify_snapshot


# Inspected 2026-09-13; changing this test pin must be an explicit reviewed edit.
CORE_TEST_COMMIT = "349ffd62a458f0dfcac72901aabdfe55f16a8050"


@pytest.mark.live
def test_pinned_core_master_files_smoke(tmp_path):
    writer = SnapshotWriter(tmp_path / "live-core")
    outcomes = fetch_fpl_core_master(writer, commit_sha=CORE_TEST_COMMIT, season="2026-2027")
    # This particular reference commit is known to contain the optional summary.
    assert outcomes == dict.fromkeys(MASTER_FILES, "success")
    manifest = verify_snapshot(writer.finalize())
    assert manifest["source_commits"] == {"fpl_core": CORE_TEST_COMMIT}
    assert len(manifest["files"]) == 4
    assert all(entry["commit_sha"] == CORE_TEST_COMMIT for entry in manifest["files"])
