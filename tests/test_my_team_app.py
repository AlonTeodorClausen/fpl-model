from pathlib import Path
from streamlit.testing.v1 import AppTest
import streamlit as st
from test_transfer_planner import context
from test_my_team import profile


def setup(monkeypatch,tmp_path):
    import fpl_model.prototype_data as source
    import fpl_model.config as cfg
    d=context();d['events']=[dict(e,deadline_time='2099-10-10T10:00:00Z' if e['id']==5 else '2099-10-17T10:00:00Z') for e in d['events'] if e['id']>=5]
    d['teams']=[dict(id=i,name=f'T{i}',short_name=f'T{i}') for i in range(1,11)]
    monkeypatch.setattr(source,'snapshot_paths',lambda root:[tmp_path/'snapshot'])
    monkeypatch.setattr(source,'load_data',lambda path,**kwargs:d)
    import fpl_model.quick_refresh as refresh
    monkeypatch.setattr(refresh,'select_history_snapshot',lambda paths,chosen,**kwargs:chosen)
    # UI storage paths are injectable without touching user profiles/caches.
    import fpl_model.ui.my_team as ui
    monkeypatch.setattr(ui,'LOCAL_ROOT',tmp_path)
    st.cache_data.clear()
    return ui


def test_explicit_refresh_button_selects_new_context_and_displays_separate_history_age(monkeypatch,tmp_path):
    ui=setup(monkeypatch,tmp_path)
    import fpl_model.quick_refresh as refresh
    import fpl_model.prototype_data as source
    old=tmp_path/'snapshot';fresh=tmp_path/'new-context'
    available=[old];calls=[]
    monkeypatch.setattr(source,'snapshot_paths',lambda root:list(reversed(available)))
    monkeypatch.setattr(refresh,'select_history_snapshot',lambda paths,chosen,**kwargs:old)
    def capture(root,**kwargs):
        calls.append(kwargs['season']);available.append(fresh);return fresh
    monkeypatch.setattr(refresh,'capture_official_context',capture)
    base=source.load_data(old)
    def composite(context,history,**kwargs):
        assert context==fresh and history==old
        return dict(base,snapshot_id='fresh',as_of_at='2098-01-01T00:00:00Z',
            input_sources=dict(history=dict(snapshot_id='old',available_at='2026-10-10T00:00:00Z'),
                               official_context=dict(snapshot_id='fresh',available_at='2098-01-01T00:00:00Z')),
            coverage=dict(base.get('coverage') or {},history_refresh_required=False,
                          new_player_ids_without_history=[],newly_finished_fixture_ids=[]))
    monkeypatch.setattr(refresh,'load_current_inputs',composite)
    app=AppTest.from_file(str(Path(__file__).resolve().parents[1]/'app.py')).run(timeout=30)
    assert not app.exception and calls==[]
    next(b for b in app.button if b.label=='Hent seneste data').click().run(timeout=30)
    assert not app.exception and calls==['2026-2027']
    assert next(s for s in app.selectbox if s.label=='Officielt datagrundlag').value==fresh
    assert any('Kampvis historik' in x.value for x in app.caption)


def test_finished_fixture_warns_and_blocks_plan_until_full_history(monkeypatch,tmp_path):
    setup(monkeypatch,tmp_path)
    import fpl_model.prototype_data as source
    d=source.load_data(None)
    d['coverage']=dict(d.get('coverage') or {},history_refresh_required=True,
                       newly_finished_fixture_ids=[12],new_player_ids_without_history=[])
    app=AppTest.from_file(str(Path(__file__).resolve().parents[1]/'app.py')).run(timeout=30)
    assert not app.exception
    assert any('nyligt afsluttede kampe' in w.value for w in app.warning)
    assert next(b for b in app.button if b.label=='Sammenlign transferforslag').disabled


def test_full_history_can_be_started_explicitly_from_page_after_match(monkeypatch,tmp_path):
    setup(monkeypatch,tmp_path)
    import fpl_model.prototype_data as source
    import fpl_model.full_player_capture as capture
    old=tmp_path/'snapshot';new=tmp_path/'complete-history';paths=[old];calls=[]
    monkeypatch.setattr(source,'snapshot_paths',lambda root:list(reversed(paths)))
    d=source.load_data(old)
    d['coverage']=dict(d.get('coverage') or {},history_refresh_required=True,
                       newly_finished_fixture_ids=[12],new_player_ids_without_history=[])
    def full(root,**kwargs):
        calls.append(kwargs['season']);paths.append(new)
        kwargs['progress'](dict(completed=1,total=1,player_id=1,status='success'))
        return new
    monkeypatch.setattr(capture,'capture_all_players',full)
    app=AppTest.from_file(str(Path(__file__).resolve().parents[1]/'app.py')).run(timeout=30)
    assert not app.exception and calls==[]
    next(b for b in app.button if b.label=='Hent fuld spillerhistorik').click().run(timeout=30)
    assert not app.exception and calls==['2026-2027']
    assert next(s for s in app.selectbox if s.label=='Officielt datagrundlag').value==new


def test_my_team_is_default_and_can_save_reload_and_compare(monkeypatch,tmp_path):
    import importlib.util
    assert importlib.util.find_spec('fpl_model.ui'), 'new app flow missing'
    ui=setup(monkeypatch,tmp_path)
    from fpl_model.my_team import save_profile
    save_profile(profile(),tmp_path/'data/processed/my_team.json')
    app=AppTest.from_file(str(Path(__file__).resolve().parents[1]/'app.py')).run(timeout=30)
    assert not app.exception
    assert 'Mit hold' in app.title[0].value
    assert next(w for w in app.number_input if w.label=='Bank (£m)').value==1.0
    next(w for w in app.number_input if w.label=='Bank (£m)').set_value(2.0)
    next(b for b in app.button if b.label=='Gem hold').click().run()
    assert not app.exception
    from fpl_model.my_team import load_profile
    assert load_profile(tmp_path/'data/processed/my_team.json')['bank']==20
    next(b for b in app.button if b.label=='Sammenlign transferforslag').click().run(timeout=60)
    assert not app.exception
    assert any('Behold holdet' in f.value.to_string() for f in app.dataframe)
    assert any('Autosubs' in x.value or 'autosubs' in x.value for x in app.caption)
    assert list((tmp_path/'artifacts/transfers').glob('*/report.json'))
    assert any('XI' in f.value.to_string() for f in app.dataframe)


def test_empty_profile_cannot_silently_assume_money_or_fetch(monkeypatch,tmp_path):
    import importlib.util
    assert importlib.util.find_spec('fpl_model.ui'), 'new app flow missing'
    setup(monkeypatch,tmp_path)
    import requests
    def forbidden(*a,**k):raise AssertionError('No automatic network')
    monkeypatch.setattr(requests.sessions.Session,'request',forbidden)
    app=AppTest.from_file(str(Path(__file__).resolve().parents[1]/'app.py')).run(timeout=30)
    assert not app.exception
    assert next(w for w in app.number_input if w.label=='Bank (£m)').value is None
    next(b for b in app.button if b.label=='Sammenlign transferforslag').click().run()
    assert not app.exception
    assert app.error


def test_changing_player_clears_previous_owners_sale_value(monkeypatch,tmp_path):
    setup(monkeypatch,tmp_path)
    from fpl_model.my_team import save_profile
    save_profile(profile(),tmp_path/'data/processed/my_team.json')
    app=AppTest.from_file(str(Path(__file__).resolve().parents[1]/'app.py')).run(timeout=30)
    next(w for w in app.selectbox if w.label=='Målmand 1').set_value(3).run()
    assert next(w for w in app.number_input if w.label=='Salgsværdi målmand 1 (£m)').value is None


def test_reload_and_example_replace_existing_widget_values(monkeypatch,tmp_path):
    ui=setup(monkeypatch,tmp_path)
    from fpl_model.my_team import save_profile
    p=profile();save_profile(p,tmp_path/'data/processed/my_team.json')
    monkeypatch.setattr(ui,'EXAMPLE_NAMES',[f'P{r["player_id"]}' for r in p['players']])
    app=AppTest.from_file(str(Path(__file__).resolve().parents[1]/'app.py')).run(timeout=30)
    next(w for w in app.number_input if w.label=='Bank (£m)').set_value(9.0).run()
    next(b for b in app.button if b.label=='Genindlæs gemt hold').click().run()
    assert next(w for w in app.number_input if w.label=='Bank (£m)').value==1.0
    next(b for b in app.button if b.label=='Indlæs eksempelhold fra billedet').click().run()
    assert next(w for w in app.selectbox if w.label=='Målmand 1').value==1
    # A changed default alone updates Python but not an already mounted keyed
    # browser widget. Resets must explicitly send its selected value to the UI.
    assert next(w for w in app.selectbox if w.label=='Målmand 1').proto.set_value
    assert next(w for w in app.number_input if w.label=='Bank (£m)').value is None


def test_previous_season_profile_cannot_be_reinterpreted_as_current(monkeypatch,tmp_path):
    setup(monkeypatch,tmp_path)
    from fpl_model.my_team import save_profile,load_profile
    p=profile();p['season']='2025-2026';path=tmp_path/'data/processed/my_team.json'
    save_profile(p,path)
    app=AppTest.from_file(str(Path(__file__).resolve().parents[1]/'app.py')).run(timeout=30)
    next(b for b in app.button if b.label=='Gem hold').click().run()
    assert load_profile(path)['season']=='2025-2026'
    next(b for b in app.button if b.label=='Sammenlign transferforslag').click().run()
    assert not list((tmp_path/'artifacts/transfers').glob('*/report.json'))


def test_sequence_flow_and_injury_sensitivity_are_saved(monkeypatch,tmp_path):
    setup(monkeypatch,tmp_path)
    from fpl_model.my_team import save_profile
    save_profile(profile(),tmp_path/'data/processed/my_team.json')
    app=AppTest.from_file(str(Path(__file__).resolve().parents[1]/'app.py')).run(timeout=30)
    assert any(w.label=='Planlægning' for w in app.selectbox),'sequence UI missing'
    assert next(w for w in app.selectbox if w.label=='Planlægning').value=='Transfers uge for uge'
    next(w for w in app.selectbox if w.label=='Horisont (GWs)').set_value(2).run()
    next(w for w in app.checkbox if w.label=='Sammenlign to mulige returtidspunkter').check().run()
    next(b for b in app.button if b.label=='Sammenlign transferforslag').click().run(timeout=60)
    assert not app.exception
    report=app.session_state['transfer_result']
    assert report['scope']=='transfer_sequences' and 'sensitivity' in report
    assert report['sensitivity']['alternative']['forecast']['availability_assumptions']
    assert any('Hypotetisk' in x.value for x in app.warning)
    assert any('GW' in d.value.columns and 'Ud' in d.value.columns for d in app.dataframe)
    assert any('Skader' in x.label for x in app.expander)


def test_future_doubt_scenario_is_visible_and_saved(monkeypatch,tmp_path):
    setup(monkeypatch,tmp_path)
    from fpl_model.my_team import save_profile
    import fpl_model.prototype_data as source
    d=source.load_data(None)
    d['players'][0].update(status='d',chance_of_playing_next_round=75)
    save_profile(profile(),tmp_path/'data/processed/my_team.json')
    app=AppTest.from_file(str(Path(__file__).resolve().parents[1]/'app.py')).run(timeout=30)
    next(w for w in app.selectbox if w.label=='Horisont (GWs)').set_value(2).run()
    policy=next(w for w in app.selectbox if w.label=='Tilgængelighed i senere GWs')
    assert policy.value=='short_doubt_next_gw'
    assert any('ikke en verificeret raskmelding' in x.value for x in app.warning)
    next(b for b in app.button if b.label=='Sammenlign transferforslag').click().run(timeout=60)
    assert not app.exception
    report=app.session_state['transfer_result']
    assert report['forecast']['derived_availability_assumptions']
    assert any('Faktor' in d.value.columns for d in app.dataframe)
    rows=report['players_by_event']
    assert next(r for r in rows[5] if r['player_id']==1)['availability_factor']==.75
    assert next(r for r in rows[6] if r['player_id']==1)['availability_factor']==1.
    next(w for w in app.selectbox if w.label=='Tilgængelighed i senere GWs').set_value('hold_current').run()
    next(b for b in app.button if b.label=='Sammenlign transferforslag').click().run(timeout=60)
    assert app.session_state['transfer_result']['forecast']['model_version']=='component_baseline_v1'
