from copy import deepcopy
from pathlib import Path
from streamlit.testing.v1 import AppTest
from test_my_team_app import setup
from test_my_team import profile
from test_team_import import payloads
from fpl_model.my_team import save_profile, load_profile

APP=str(Path(__file__).resolve().parents[1]/'app.py')


def prepare(monkeypatch,tmp_path):
    setup(monkeypatch,tmp_path)
    import fpl_model.prototype_data as data_source
    import fpl_model.ui.team_import as importer
    data=data_source.load_data(None)
    boot,entry,picks=payloads()
    for p in data['players']:p['code']=10000+p['id']
    result=dict(entry_id=3533723,name='Example Team',event=5,season='2026-2027',
                observed_at='2026-09-13T12:00:00+00:00',deadline_at='2026-09-01T10:00:00+00:00',
                bank_at_deadline=7,picks=picks['picks'],players=[p for p in boot['elements'] if p['id'] in {r['element'] for r in picks['picks']}],
                snapshot_id='mock-snapshot',snapshot_path=str(tmp_path/'raw/mock-snapshot'))
    calls=[]
    def capture(value,root):calls.append(value);return deepcopy(result)
    monkeypatch.setattr(importer,'capture_team',capture)
    path=tmp_path/'data/processed/my_team.json';save_profile(profile(),path)
    return result,calls,path,importer


def button(app,label):return next(b for b in app.button if b.label==label)
def number(app,label):return next(w for w in app.number_input if w.label==label)


def test_import_preview_apply_and_unknown_money_are_explicit(monkeypatch,tmp_path):
    result,calls,path,_=prepare(monkeypatch,tmp_path);before=path.read_bytes()
    app=AppTest.from_file(APP).run()
    assert calls==[]
    app.text_input(key='team_import_id').set_value('3533723')
    button(app,'Hent hold fra FPL').click().run()
    assert not app.exception and calls==['3533723']
    assert any(len(t.value)==15 and 'Aktuel købspris £m' in t.value for t in app.dataframe)
    assert path.read_bytes()==before and number(app,'Bank (£m)').value==1.0
    button(app,'Brug dette hold').click().run()
    assert not app.exception and calls==['3533723']
    assert number(app,'Bank (£m)').value==.7
    assert number(app,'Salgsværdi målmand 1 (£m)').value is None
    assert number(app,'Resterende gratis transfers').value is None
    assert number(app,'Transfers allerede foretaget denne GW').value is None
    ids={w.value for w in app.selectbox if (w.key or '').startswith('owned_id_')}
    assert ids=={p['id'] for p in result['players']}
    button(app,'Gem hold').click().run()
    assert app.error and path.read_bytes()==before
    button(app,'Sammenlign transferforslag').click().run()
    assert app.error and not list((tmp_path/'artifacts/transfers').glob('*/report.json'))


def test_explicit_reuse_save_and_reload_preserves_import_provenance(monkeypatch,tmp_path):
    _,calls,path,_=prepare(monkeypatch,tmp_path)
    app=AppTest.from_file(APP).run()
    app.text_input(key='team_import_id').set_value('3533723')
    button(app,'Hent hold fra FPL').click().run()
    next(w for w in app.checkbox if w.label.startswith('Genbrug mine')).check().run()
    button(app,'Brug dette hold').click().run()
    assert number(app,'Bank (£m)').value==1.0
    assert number(app,'Resterende gratis transfers').value==1
    button(app,'Gem hold').click().run()
    assert not app.exception
    saved=load_profile(path)
    assert saved['players']==profile()['players']
    assert saved['import_provenance']['entry_id']==3533723
    app=AppTest.from_file(APP).run()
    assert app.text_input(key='team_import_id').value=='3533723'
    assert calls==['3533723']


def test_failed_fetch_clears_preview_but_not_local_team(monkeypatch,tmp_path):
    _,calls,path,importer=prepare(monkeypatch,tmp_path);before=path.read_bytes()
    app=AppTest.from_file(APP).run()
    app.text_input(key='team_import_id').set_value('3533723')
    button(app,'Hent hold fra FPL').click().run()
    def fail(*a,**k):raise ValueError('FPL svarede HTTP 503.')
    monkeypatch.setattr(importer,'capture_team',fail)
    button(app,'Hent hold fra FPL').click().run()
    assert not app.exception and any('503' in e.value for e in app.error)
    assert not any(b.label=='Brug dette hold' for b in app.button)
    assert number(app,'Bank (£m)').value==1.0 and path.read_bytes()==before


def test_mismatched_player_identity_prevents_applying_import(monkeypatch,tmp_path):
    result,_,path,_=prepare(monkeypatch,tmp_path);before=path.read_bytes()
    result['players'][0]['code']+=1
    app=AppTest.from_file(APP).run()
    app.text_input(key='team_import_id').set_value('3533723')
    button(app,'Hent hold fra FPL').click().run()
    assert not app.exception and any('identitet' in e.value for e in app.error)
    assert not any(b.label=='Brug dette hold' for b in app.button)
    assert path.read_bytes()==before
