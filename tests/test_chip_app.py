from pathlib import Path
from streamlit.testing.v1 import AppTest
from test_my_team_app import setup
from test_chips import ready_profile
from fpl_model.my_team import save_profile,load_profile

ROOT=Path(__file__).resolve().parents[1]


def test_standard_main_and_chip_workflow(monkeypatch,tmp_path):
    setup(monkeypatch,tmp_path)
    import requests
    monkeypatch.setattr(requests.sessions.Session,'request',lambda *a,**k: (_ for _ in ()).throw(AssertionError('network')))
    save_profile(ready_profile(),tmp_path/'data/processed/my_team.json')
    app=AppTest.from_file(str(ROOT/'app.py')).run(timeout=30)
    assert not app.exception
    assert not any(w.label=='Prognosemodel' for w in app.selectbox)
    assert any('Standardprognose' in w.value for w in app.info)
    widget=next(w for w in app.selectbox if w.label=='Chip · GW5')
    widget.set_value('triple_captain').run()
    next(b for b in app.button if b.label=='Sammenlign transferforslag').click().run(timeout=60)
    assert not app.exception
    assert app.session_state['transfer_result']['config']['chip_plan']=={5:'triple_captain'}
    assert app.session_state['transfer_result']['forecast']['model_version']=='component_baseline_v1'
    assert any('Triple Captain' in d.value.to_string() for d in app.dataframe)
    next(b for b in app.button if b.label=='Gem hold').click().run()
    assert load_profile(tmp_path/'data/processed/my_team.json')['chip_inventory']['halves']['first']['wildcard']['status']=='available'


def test_analysis_still_has_model_choices(monkeypatch,tmp_path):
    setup(monkeypatch,tmp_path);save_profile(ready_profile(),tmp_path/'data/processed/my_team.json')
    app=AppTest.from_file(str(ROOT/'app.py')).run(timeout=30)
    next(w for w in app.radio if w.label=='Side').set_value('Analyse og eksperimenter').run(timeout=30)
    next(w for w in app.radio if w.label=='Analysevisning').set_value('Transferlaboratorium').run(timeout=30)
    assert not app.exception
    assert len(next(w for w in app.selectbox if w.label=='Prognosemodel').options)==6


def test_unsaved_chip_choice_provenance_is_stable_across_reruns(monkeypatch,tmp_path):
    setup(monkeypatch,tmp_path)
    from test_my_team import profile
    save_profile(profile(),tmp_path/'data/processed/my_team.json')
    app=AppTest.from_file(str(ROOT/'app.py')).run(timeout=30)
    next(w for w in app.selectbox if w.label=='Triple Captain · Første sæt · GW1–19').set_value('available').run()
    next(w for w in app.selectbox if w.label=='Chip · GW5').set_value('triple_captain').run()
    next(b for b in app.button if b.label=='Sammenlign transferforslag').click().run(timeout=60)
    assert not app.exception
    app.run(timeout=30)
    assert not any('Viser en gemt beregning' in w.value for w in app.warning)


def test_recommended_plan_is_initially_displayed_and_report_labels_are_clear(monkeypatch,tmp_path):
    setup(monkeypatch,tmp_path);save_profile(ready_profile(),tmp_path/'data/processed/my_team.json')
    app=AppTest.from_file(str(ROOT/'app.py')).run(timeout=30)
    next(w for w in app.selectbox if w.label=='Chip · GW5').set_value('triple_captain').run()
    next(b for b in app.button if b.label=='Sammenlign transferforslag').click().run(timeout=60)
    r=app.session_state['transfer_result'];selected=next(w for w in app.selectbox if w.label=='Strategi – se ugeplan').value
    assert r['packages'][selected]['plan_id']==r['recommendation']['plan_id']
    assert not any('bench_contribution_kind' in d.value.columns for d in app.dataframe)
