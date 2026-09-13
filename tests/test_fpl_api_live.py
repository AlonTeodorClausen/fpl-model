"""Optional integration check: python -m pytest -m live -q.

Makes exactly two public requests. Snapshots go to pytest's temporary directory,
never the project's data folders. No credentials or response bodies are logged.
"""

import pytest

from fpl_model.data_sources.fpl_api import fetch_fpl_snapshot
from fpl_model.io import SnapshotWriter, verify_snapshot


@pytest.mark.live
def test_official_fpl_endpoints_smoke(tmp_path):
    writer = SnapshotWriter(tmp_path / "live-fpl")
    fetch_fpl_snapshot(writer)
    manifest = verify_snapshot(writer.finalize())
    assert len(manifest["files"]) == 2
    assert all(entry["required"] and entry["http_status"] == 200 for entry in manifest["files"])
