"""Artifact tests use synthetic Step 2C captures, never network or live fixtures."""
import importlib.util
import json
from datetime import timedelta
from pathlib import Path

import pytest

from fpl_model.player_fixture_labels import normalize_snapshot,write_report


def load(path,name):
    spec=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m


@pytest.fixture
def reports(tmp_path):
    helpers=load(Path(__file__).with_name('test_player_fixture_labels.py'),'label_fixtures')
    paths=[helpers.snapshot(tmp_path,{'history':[{}],'event_patch':{'data_checked':False}}),
           helpers.snapshot(tmp_path,now=helpers.NOW+timedelta(days=1))]
    return [write_report(normalize_snapshot(p,season='2026-2027',element_ids=[1]),tmp_path/'reports') for p in paths]


def audit_module():
    path=Path(__file__).resolve().parents[1]/'scripts/audit_observations.py'
    assert path.exists(),'Step 2D offline audit not implemented'
    return load(path,'audit_observations')


def test_verified_audit_is_deterministic_readonly_and_separates_targets(reports,tmp_path):
    m=audit_module();before={p:p.read_bytes() for d in reports for p in d.iterdir()}
    r=m.audit_reports(reports,cutoff_at='2026-09-21T12:00:00Z',events=[4])
    assert r==m.audit_reports(list(reversed(reports)),cutoff_at='2026-09-21T12:00:00Z',events=[4])
    assert r['summary']['unique_player_fixtures']==1
    assert r['summary']['observations']==2
    assert r['as_of_examples'][0]['label_state']=='provisional'
    assert r['outcome_examples'][0]['label_state']=='final'
    assert r['transitions']['transitions'][0]['earlier_state']=='provisional'
    out=m.write_audit(r,tmp_path/'out')
    assert (out/'COMPLETE.json').exists()
    other=m.write_audit(r,tmp_path/'reproduced')
    assert {p.name:p.read_bytes() for p in out.iterdir()}=={p.name:p.read_bytes() for p in other.iterdir()}
    with pytest.raises(FileExistsError):m.write_audit(r,tmp_path/'out')
    assert before=={p:p.read_bytes() for d in reports for p in d.iterdir()}


def test_corrupt_or_duplicate_reports_rejected(reports):
    m=audit_module()
    with pytest.raises(ValueError):m.audit_reports([reports[0],reports[0]],cutoff_at='2026-09-21T12:00:00Z',events=[4])
    (reports[0]/'labels.jsonl').write_text('{}\n')
    with pytest.raises(ValueError):m.audit_reports(reports,cutoff_at='2026-09-21T12:00:00Z',events=[4])
