"""Offline integration exercises real adapters/writer/normalizer behind fake HTTP."""
import importlib.util
import json
from pathlib import Path

import pytest

SPEC=importlib.util.spec_from_file_location('player_labels_workflow',Path(__file__).resolve().parents[1]/'scripts/player_fixture_labels.py')
workflow=importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(workflow)


class Response:
    def __init__(self, data, status=200):
        self.content=json.dumps(data).encode();self.status_code=status;self.headers={'Content-Type':'application/json'}
    def __enter__(self):return self
    def __exit__(self,*args):pass


class Session:
    def __init__(self, fail=False):self.calls=[];self.fail=fail
    def get(self,url,**kwargs):
        self.calls.append(url)
        if url.endswith('/bootstrap-static/'):
            return Response(dict(elements=[dict(id=1,team=1,element_type=1)],teams=[dict(id=1),dict(id=2)],events=[dict(id=4,finished=True,data_checked=True,deadline_time='2026-09-12T10:00:00Z')],element_types=[dict(id=1)]))
        if url.endswith('/fixtures/'):
            return Response([dict(id=11,event=4,team_h=1,team_a=2,kickoff_time='2026-09-12T14:00:00Z',started=True,finished=True)])
        return Response({'history':[dict(element=1,fixture=11,round=4,opponent_team=2,was_home=True,kickoff_time='2026-09-12T14:00:00Z',minutes=90,starts=1,total_points=6)]},503 if self.fail else 200)


def test_bounded_capture_then_offline_normalization(tmp_path):
    session=Session()
    raw=workflow.capture_sample(tmp_path/'raw',season='2026-2027',element_ids=[1],session=session)
    assert len(session.calls)==3 and session.calls[-1].endswith('/element-summary/1/')
    manifest=json.loads((raw/'manifest.json').read_text())
    assert manifest['status']=='complete' and manifest['run_metadata']['season']=='2026-2027'
    assert workflow.main(['normalize','--snapshot',str(raw),'--season','2026-2027','--elements','1','--output-root',str(tmp_path/'audits')])==0
    output=tmp_path/'audits'/('step2c_'+manifest['run_id'])
    label=json.loads((output/'labels.jsonl').read_text())
    assert label['minutes']==90 and label['label_state']=='final'
    assert (output/'COMPLETE.json').exists()


def test_required_failure_preserves_raw_without_publishing(tmp_path):
    with pytest.raises(workflow.FPLSourceError):
        workflow.capture_sample(tmp_path/'raw',season='2026-2027',element_ids=[1],session=Session(fail=True))
    manifests=list((tmp_path/'raw/.staging').glob('*/manifest.json'))
    assert len(manifests)==1
    manifest=json.loads(manifests[0].read_text())
    assert manifest['status']=='failed' and len(manifest['files'])==3
    assert list((tmp_path/'raw').glob('*/COMPLETE'))==[]
