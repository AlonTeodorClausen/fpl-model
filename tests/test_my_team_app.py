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
    monkeypatch.setattr(ui,'read_active_public_data',lambda raw,published:dict(
        publication_id='offline-test',context_path=tmp_path/'snapshot',
        history_path=tmp_path/'snapshot'),raising=False)
    st.cache_data.clear()
    return ui


def test_new_context_only_snapshot_is_default(monkeypatch,tmp_path):
    import json
    import fpl_model.prototype_data as source
    setup(monkeypatch,tmp_path)
    old=tmp_path/'snapshot'
    new=tmp_path/'new-context'
    old.mkdir();new.mkdir()
    (old/'manifest.json').write_text(json.dumps({'files':[
        {'source':'fpl_api','outcome':'success','relative_path':'raw/fpl_api/element_summary/1.json'}]}))
    (new/'manifest.json').write_text(json.dumps({'files':[
        {'source':'fpl_api','outcome':'success','relative_path':'raw/fpl_api/bootstrap_static.json'}]}))
    monkeypatch.setattr(source,'snapshot_paths',lambda root:[new,old])
    app=AppTest.from_file(str(Path(__file__).resolve().parents[1]/'app.py')).run(timeout=30)
    assert not app.exception
    assert any('Kontekst: new-context' in c.value for c in app.code)
    assert not any(s.label=='Officielt datagrundlag' for s in app.selectbox)


def test_selected_incomplete_context_recovers_to_usable_snapshot(monkeypatch,tmp_path):
    import json
    import fpl_model.prototype_data as source
    ui=setup(monkeypatch,tmp_path)
    old=tmp_path/'snapshot';new=tmp_path/'new-context'
    old.mkdir();new.mkdir()
    (old/'manifest.json').write_text(json.dumps({'files':[
        {'source':'fpl_api','outcome':'success','relative_path':'raw/fpl_api/element_summary/1.json'}]}))
    (new/'manifest.json').write_text(json.dumps({'files':[
        {'source':'fpl_api','outcome':'success','relative_path':'raw/fpl_api/bootstrap_static.json'}]}))
    monkeypatch.setattr(source,'snapshot_paths',lambda root:[new,old])
    data=source.load_data(old)
    def load(path,*args):
        if Path(path)==new:
            raise ValueError('History source is incomplete; select a complete full-pool capture')
        return data
    monkeypatch.setattr(ui,'_load_data',load)
    app=AppTest.from_file(str(Path(__file__).resolve().parents[1]/'app.py')).run(timeout=30)
    assert not app.error and not app.exception
    assert any('Kontekst: snapshot' in c.value for c in app.code)
    assert any('History source is incomplete' in w.value for w in app.warning)


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
    def smart(root,**kwargs):
        chosen=capture(root,**kwargs)
        return dict(status='context_only',context_snapshot=chosen,selected_snapshot=chosen,
                    history_snapshot=old,history_required=False,changed_fixture_ids=[])
    monkeypatch.setattr(refresh,'refresh_official_data',smart,raising=False)
    monkeypatch.setattr(refresh,'capture_official_context',lambda *a,**k:(_ for _ in ()).throw(
        AssertionError('The button must use smart refresh')))
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
    assert any('Kontekst: new-context' in c.value for c in app.code)
    assert any('Kampvis historik' in x.value for x in app.markdown)


def test_my_team_shows_deadline_readiness_and_review_lives_in_analysis(monkeypatch,tmp_path):
    from datetime import datetime,timezone
    setup(monkeypatch,tmp_path)
    import fpl_model.prototype_data as source
    data=source.load_data(None)
    data['as_of_at']=datetime.now(timezone.utc).isoformat()
    data['input_sources']=dict(history=dict(snapshot_id='h',available_at=data['as_of_at']),
                               official_context=dict(snapshot_id='c',available_at=data['as_of_at']))
    app=AppTest.from_file(str(Path(__file__).resolve().parents[1]/'app.py')).run(timeout=30)
    assert not app.exception
    assert any('Klar til GW' in x.value for x in app.success)
    assert not any('Efter runden' in e.label for e in app.expander)
    next(r for r in app.radio if r.label=='Side').set_value('Analyse og eksperimenter').run(timeout=30)
    assert any('Efter runden' in e.label for e in app.expander)


def test_incomplete_history_needs_opt_in_and_saved_report_records_it(monkeypatch,tmp_path):
    import json
    ui=setup(monkeypatch,tmp_path)
    from fpl_model.my_team import save_profile
    import fpl_model.prototype_data as source

    save_profile(profile(),tmp_path/'data/processed/my_team.json')
    data=source.load_data(None)
    data['histories']=[row for row in data['histories'] if row['player_id']!=1]
    data['coverage']=dict(history_refresh_required=True,missing_response_players=[1],
                          quarantined_rows=0,newly_finished_fixture_ids=[],
                          newly_started_fixture_ids=[],revised_result_fixture_ids=[])
    app=AppTest.from_file(str(Path(__file__).resolve().parents[1]/'app.py')).run(timeout=30)
    assert not app.exception
    action=next(b for b in app.button if b.label=='Sammenlign transferforslag')
    assert action.disabled
    assert any('1 spillerhistorik mangler' in w.value for w in app.warning)
    next(c for c in app.checkbox if 'ufuldstændige' in c.label.lower()).check().run(timeout=30)
    action=next(b for b in app.button if b.label=='Sammenlign transferforslag')
    assert not action.disabled
    action.click().run(timeout=60)
    assert not app.exception
    saved=list((tmp_path/'artifacts/transfers').glob('*/report.json'))
    assert len(saved)==1
    report=json.loads(saved[0].read_text())
    assert report['input_readiness']['new_forecast_status']=='limited'
    assert report['input_readiness']['explicitly_accepted'] is True
    assert report['input_readiness']['missing_player_ids']==[1]
    first=next(iter(report['players_by_event'].values()))
    missing_player=next(row for row in first if row['player_id']==1)
    assert missing_player['history_rows']==0
    assert 'no_observed_history' in missing_player['fallbacks']
    assert any('foreløbig' in w.value.lower() for w in app.warning)
    assert any(e.label=='Berørte input i denne beregning' for e in app.expander)


def test_quarantine_scope_is_visible_and_identity_conflicts_block_opt_in(monkeypatch,tmp_path):
    import fpl_model.prototype_data as source
    setup(monkeypatch,tmp_path)
    data=source.load_data(None)
    data['coverage']=dict(data.get('coverage') or {},quarantined_rows=2)
    data['quarantine']=[dict(requested_player_id=1,reasons=['fixture_not_started']),
                        dict(requested_player_id=2,reasons=['unknown_fixture_team_id'])]
    app=AppTest.from_file(str(Path(__file__).resolve().parents[1]/'app.py')).run(timeout=30)
    assert not app.exception
    assert any('identitet' in e.value.lower() for e in app.error)
    assert not any('ufuldstændige data (foreløbig)' in c.label.lower() for c in app.checkbox)
    assert any('2 historikrækker i karantæne' in x.value for x in app.error)


def test_provisional_quarantine_count_and_reason_are_visible(monkeypatch,tmp_path):
    import fpl_model.prototype_data as source
    setup(monkeypatch,tmp_path)
    data=source.load_data(None)
    data['coverage']=dict(data.get('coverage') or {},quarantined_rows=2)
    data['quarantine']=[dict(requested_player_id=1,reasons=['fixture_not_started']),
                        dict(requested_player_id=2,reasons=['fixture_not_started'])]
    app=AppTest.from_file(str(Path(__file__).resolve().parents[1]/'app.py')).run(timeout=30)
    assert not app.exception
    assert any('2 historikrækker i karantæne' in w.value for w in app.warning)
    assert any('Kampens officielle status' in x.value for x in app.caption)


def test_saved_proposal_can_be_opened_without_a_future_deadline(monkeypatch,tmp_path):
    import fpl_model.prototype_data as source
    from fpl_model.transfer_planner import forecast_bundle,compare_packages,save_report
    from fpl_model.models.baseline import BaselineConfig

    setup(monkeypatch,tmp_path)
    data=source.load_data(None)
    forecast=forecast_bundle(data,[5],BaselineConfig(),origin_at='2026-09-09T13:00:00Z',
                             cache_root=tmp_path/'cache',draws=100,seed=42)
    report=compare_packages(forecast,profile(),max_transfers=0)
    save_report(report,tmp_path/'artifacts/transfers')
    data['events']=[dict(event,deadline_time='2020-01-01T10:00:00Z') for event in data['events']]
    app=AppTest.from_file(str(Path(__file__).resolve().parents[1]/'app.py')).run(timeout=30)
    assert not app.exception
    assert any(e.label=='Åbn tidligere transferforslag' for e in app.expander)
    next(b for b in app.button if b.label=='Åbn gemt sammenligning').click().run(timeout=30)
    assert not app.exception
    assert any('Beregnet' in c.value for c in app.caption)
    assert any('tidligere' in w.value.lower() or 'gemt' in w.value.lower() for w in app.warning)


def test_main_page_uses_readable_dates_and_keeps_technical_ids_in_details(monkeypatch,tmp_path):
    from datetime import datetime,timezone
    setup(monkeypatch,tmp_path)
    import fpl_model.prototype_data as source
    data=source.load_data(None)
    data['as_of_at']=datetime.now(timezone.utc).isoformat()
    data['input_sources']=dict(history=dict(snapshot_id='h',available_at=data['as_of_at']),
                               official_context=dict(snapshot_id='c',available_at=data['as_of_at']))
    app=AppTest.from_file(str(Path(__file__).resolve().parents[1]/'app.py')).run(timeout=30)
    assert not app.exception
    assert any('dansk tid' in x.value for x in app.success)
    assert not any('snapshot' in x.value.lower() for x in app.success)
    assert not any('offline-test' in x.value for x in app.caption)
    assert any('Data og hentetider' in e.label for e in app.expander)
    assert any('Teknisk reference' in x.value for x in app.caption)


def test_experimental_odds_model_shows_fallback_coverage_before_planning(monkeypatch,tmp_path):
    setup(monkeypatch,tmp_path)
    app=AppTest.from_file(str(Path(__file__).resolve().parents[1]/'app.py')).run(timeout=30)
    next(r for r in app.radio if r.label=='Side').set_value('Analyse og eksperimenter').run(timeout=30)
    next(r for r in app.radio if r.label=='Analysevisning').set_value('Transferlaboratorium').run(timeout=30)
    next(w for w in app.selectbox if w.label=='Prognosemodel').set_value(
        'Defensiv oddsvariant · William Hill').run(timeout=30)
    assert not app.exception
    assert any('Odds-dækning GW5' in x.value and '0/' in x.value for x in app.caption)
    assert any('baseline-fallback' in x.value for x in app.warning)


def test_finished_fixture_requires_explicit_provisional_choice_before_plan(monkeypatch,tmp_path):
    setup(monkeypatch,tmp_path)
    import fpl_model.prototype_data as source
    d=source.load_data(None)
    d['coverage']=dict(d.get('coverage') or {},history_refresh_required=True,
                       newly_finished_fixture_ids=[12],new_player_ids_without_history=[])
    app=AppTest.from_file(str(Path(__file__).resolve().parents[1]/'app.py')).run(timeout=30)
    assert not app.exception
    assert any('ufuldstændig' in w.value.lower() or 'ufuldstændige' in w.value.lower()
               for w in app.warning)
    assert not any('0 spillerhistorik mangler' in w.value for w in app.warning)
    assert next(b for b in app.button if b.label=='Sammenlign transferforslag').disabled
    next(c for c in app.checkbox if 'ufuldstændige' in c.label.lower()).check().run(timeout=30)
    assert not next(b for b in app.button if b.label=='Sammenlign transferforslag').disabled


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
    assert any('Kontekst: complete-history' in c.value for c in app.code)


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


def test_first_time_planning_keeps_horizon_visible_and_advanced_options_closed(monkeypatch,tmp_path):
    setup(monkeypatch,tmp_path)
    app=AppTest.from_file(str(Path(__file__).resolve().parents[1]/'app.py')).run(timeout=30)
    assert not app.exception
    assert any(w.label=='Horisont (GWs)' for w in app.selectbox)
    advanced=next(e for e in app.expander if e.label=='Tilpas transferplan, chips og antagelser')
    assert not advanced.proto.expanded
    assert any(w.label=='Maksimalt antal transfers pr. GW' for w in app.number_input)
    assert any(w.label=='Tillad pointfradrag (−4 pr. ekstra transfer)' for w in app.checkbox)


def test_loaded_team_keeps_bank_visible_and_player_price_editor_collapsed(monkeypatch,tmp_path):
    setup(monkeypatch,tmp_path)
    from fpl_model.my_team import save_profile
    save_profile(profile(),tmp_path/'data/processed/my_team.json')
    app=AppTest.from_file(str(Path(__file__).resolve().parents[1]/'app.py')).run(timeout=30)
    assert not app.exception
    assert next(w for w in app.number_input if w.label=='Bank (£m)').value==1.0
    editor=next(e for e in app.expander if e.label=='Ret spillere og salgsværdier')
    assert not editor.proto.expanded
    assert any(w.label=='Målmand 1' for w in app.selectbox)
    assert any(b.label=='Gem hold' for b in app.button)


def test_team_and_result_default_to_list_with_optional_pitch(monkeypatch,tmp_path):
    setup(monkeypatch,tmp_path)
    from fpl_model.my_team import save_profile
    save_profile(profile(),tmp_path/'data/processed/my_team.json')
    app=AppTest.from_file(str(Path(__file__).resolve().parents[1]/'app.py')).run(timeout=30)
    squad=next(r for r in app.radio if r.label=='Holdvisning')
    assert squad.value=='Liste' and squad.options==['Liste','Bane']
    squad.set_value('Bane').run(timeout=30)
    assert not app.exception
    assert any('Skub banen vandret' in c.value for c in app.caption)
    next(b for b in app.button if b.label=='Sammenlign transferforslag').click().run(timeout=60)
    assert not app.exception
    lineup=next(r for r in app.radio if r.label=='Opstillingsvisning')
    assert lineup.value=='Liste' and lineup.options==['Liste','Bane']
    lineup.set_value('Bane').run(timeout=30)
    assert not app.exception
    assert any('Skub banen vandret' in c.value for c in app.caption)


def test_clickable_owned_player_opens_projection_without_running_optimizer(monkeypatch,tmp_path):
    import numpy as np
    ui = setup(monkeypatch,tmp_path)
    from fpl_model.my_team import save_profile
    import fpl_model.prototype_data as source

    save_profile(profile(),tmp_path/'data/processed/my_team.json')
    data = source.load_data(None)
    players = sorted(data['players'], key=lambda p:p['id'])
    rows = [dict(player_id=p['id'], name=p['web_name'], team_id=p['team'],
                 position=p['element_type'], price=p['now_cost'], xp=4.25,
                 expected_minutes=71.0, p10=1.0, p50=4.0, p90=9.0,
                 p_no_play=.12, fixture_ids=[5], history_rows=4,
                 p_start=.60,
                 basis='player_fixture_history', fallbacks='') for p in players]
    calls=[]
    def fake_forecast(*args,**kwargs):
        calls.append(kwargs['origin_at'])
        return dict(players=players,events=[5],rows={5:rows},
                    explanations={5:{p['id']:dict(point_components={'appearance':1.5,'goals':2.75},
                        p_sub=.20,start_minutes=80.,sub_minutes=25.) for p in players}},
                    planning_scenarios={5:dict(points=np.full((4,len(players)),4,dtype=int))},
                    metadata=dict(model_version='component_baseline_v1',forecast_origin_at=kwargs['origin_at'],draws=4))
    monkeypatch.setattr(ui,'forecast_bundle',fake_forecast)
    monkeypatch.setattr(ui,'compare_packages',lambda *a,**k:(_ for _ in ()).throw(
        AssertionError('Player view must not run transfer optimization')))
    app=AppTest.from_file(str(Path(__file__).resolve().parents[1]/'app.py'))
    app.query_params['player_id']='1'
    app.run(timeout=30)
    assert not app.exception and len(calls)==1
    assert any('Spillerprognose ·' in h.value for h in app.subheader)
    assert any('4.25' in str(x.value) for x in app.metric)
    assert any('Sammenlign med andre spillere' in x.label for x in app.multiselect)
    assert any('Startchance pr. kamp' in c.value and '80' in c.value for c in app.caption)
    app.run(timeout=30)
    assert not app.exception and len(calls)==1  # Widget reruns reuse the same forecast.
    app.query_params['player_id']='2'
    app.run(timeout=30)
    assert not app.exception and len(calls)==1  # Another player shares the forecast.
    second_name=next(p['web_name'] for p in data['players'] if p['id']==2)
    assert any('Spillerprognose ·' in h.value and second_name in h.value
               for h in app.subheader)


def test_opened_saved_proposal_player_uses_saved_forecast_without_recalculation(monkeypatch,tmp_path):
    from test_transfer_planner import bundle
    from fpl_model.transfer_planner import compare_packages,save_report
    from fpl_model.my_team import save_profile
    ui=setup(monkeypatch,tmp_path)
    save_profile(profile(),tmp_path/'data/processed/my_team.json')
    saved_profile=(tmp_path/'data/processed/my_team.json').read_bytes()
    frozen=bundle(tmp_path/'artifacts/transfer_forecasts')
    report=compare_packages(frozen,profile(),max_transfers=0)
    save_report(report,tmp_path/'artifacts/transfers')
    monkeypatch.setattr(ui,'forecast_bundle',lambda *a,**k:(_ for _ in ()).throw(
        AssertionError('A saved forecast must not be recomputed')))
    app=AppTest.from_file(str(Path(__file__).resolve().parents[1]/'app.py')).run(timeout=30)
    next(b for b in app.button if b.label=='Åbn gemt sammenligning').click().run(timeout=30)
    app.query_params['player_id']='1'
    app.run(timeout=30)
    assert not app.exception
    assert any('Spillerprognose ·' in h.value for h in app.subheader)
    assert any('gemte prognose' in c.value.lower() for c in app.caption)
    assert any('Hvorfor dette forslag?' in h.value for h in app.subheader)
    next(w for w in app.selectbox if w.label=='Horisont (GWs)').set_value(2).run(timeout=30)
    assert not app.exception
    assert any('GW5 ·' in c.value and report['forecast']['model_version'] in c.value
               for c in app.caption)
    assert (tmp_path/'data/processed/my_team.json').read_bytes()==saved_profile


def test_immediate_report_opens_its_recommended_package_not_hold(monkeypatch,tmp_path):
    ui=setup(monkeypatch,tmp_path)
    from fpl_model.my_team import save_profile
    save_profile(profile(),tmp_path/'data/processed/my_team.json')
    original=ui.compare_packages
    def recommend_transfer(*args,**kwargs):
        report=original(*args,**kwargs)
        assert len(report['packages'])>1
        report['packages'][1]['objective']=report['packages'][0]['objective']+10
        return report
    monkeypatch.setattr(ui,'compare_packages',recommend_transfer)
    app=AppTest.from_file(str(Path(__file__).resolve().parents[1]/'app.py')).run(timeout=30)
    next(w for w in app.selectbox if w.label=='Planlægning').set_value('Alle transfers nu').run(timeout=30)
    next(b for b in app.button if b.label=='Sammenlign transferforslag').click().run(timeout=60)
    assert not app.exception
    selector=next(w for w in app.selectbox if w.label=='Forslag – se opstillinger')
    assert selector.value==1


def test_incoming_player_on_saved_lineup_opens_that_reports_projection(monkeypatch,tmp_path):
    from test_transfer_planner import bundle
    from fpl_model.transfer_planner import compare_packages,save_report
    from fpl_model.my_team import save_profile
    ui=setup(monkeypatch,tmp_path)
    save_profile(profile(),tmp_path/'data/processed/my_team.json')
    frozen=bundle(tmp_path/'artifacts/transfer_forecasts')
    report=compare_packages(frozen,profile(),max_transfers=1)
    incoming=report['packages'][1]['in'][0]
    assert incoming not in {r['player_id'] for r in profile()['players']}
    save_report(report,tmp_path/'artifacts/transfers')
    monkeypatch.setattr(ui,'forecast_bundle',lambda *a,**k:(_ for _ in ()).throw(
        AssertionError('The saved report must not trigger a new simulation')))
    app=AppTest.from_file(str(Path(__file__).resolve().parents[1]/'app.py')).run(timeout=30)
    next(b for b in app.button if b.label=='Åbn gemt sammenligning').click().run(timeout=30)
    app.query_params['player_id']=str(incoming)
    app.run(timeout=30)
    assert not app.exception
    assert any('Spillerprognose ·' in h.value for h in app.subheader)
    assert any('gemte prognose' in c.value.lower() for c in app.caption)


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


def test_normal_selection_ignores_stale_session_and_follows_new_local_capture(monkeypatch,tmp_path):
    setup(monkeypatch,tmp_path)
    import fpl_model.prototype_data as source
    from fpl_model.my_team import save_profile
    save_profile(profile(),tmp_path/'data/processed/my_team.json')
    old=tmp_path/'snapshot';new=tmp_path/'new-context'
    available=[old]
    monkeypatch.setattr(source,'snapshot_paths',lambda root:list(reversed(available)))
    app=AppTest.from_file(str(Path(__file__).resolve().parents[1]/'app.py'))
    app.session_state['official_snapshot_choice']=old
    app.run(timeout=30)
    next(w for w in app.number_input if w.label=='Bank (£m)').set_value(2.0).run(timeout=30)
    draft=dict(app.session_state['team_draft'])
    available.append(new)
    app.run(timeout=30)
    assert not app.exception
    assert any('Kontekst: new-context' in c.value for c in app.code)
    assert next(w for w in app.number_input if w.label=='Bank (£m)').value==2.0
    assert app.session_state['team_draft']==draft


def test_historical_selection_stays_pinned_when_new_local_data_arrives(monkeypatch,tmp_path):
    setup(monkeypatch,tmp_path)
    import fpl_model.prototype_data as source
    old=tmp_path/'snapshot';new=tmp_path/'new-context';later=tmp_path/'later-context'
    available=[new,old]
    monkeypatch.setattr(source,'snapshot_paths',lambda root:list(available))
    app=AppTest.from_file(str(Path(__file__).resolve().parents[1]/'app.py')).run(timeout=30)
    next(c for c in app.checkbox if c.label=='Brug historisk datagrundlag').check().run(timeout=30)
    next(s for s in app.selectbox if s.label=='Historisk datagrundlag').set_value(old).run(timeout=30)
    available.insert(0,later)
    app.run(timeout=30)
    assert not app.exception
    assert next(s for s in app.selectbox if s.label=='Historisk datagrundlag').value==old
    assert any('Historisk visning' in w.value for w in app.warning)
    assert any('Kontekst: snapshot' in c.value for c in app.code)
    next(c for c in app.checkbox if c.label=='Brug historisk datagrundlag').uncheck().run(timeout=30)
    assert any('Kontekst: later-context' in c.value for c in app.code)


def test_unusable_historical_selection_shows_error_without_switching(monkeypatch,tmp_path):
    ui=setup(monkeypatch,tmp_path)
    import fpl_model.prototype_data as source
    old=tmp_path/'snapshot';new=tmp_path/'new-context'
    monkeypatch.setattr(source,'snapshot_paths',lambda root:[new,old])
    data=source.load_data(old)
    def load(path,*args):
        if Path(path)==old:raise ValueError('Unsupported squad rules in snapshot')
        return data
    monkeypatch.setattr(ui,'_load_data',load)
    app=AppTest.from_file(str(Path(__file__).resolve().parents[1]/'app.py')).run(timeout=30)
    next(c for c in app.checkbox if c.label=='Brug historisk datagrundlag').check().run(timeout=30)
    next(s for s in app.selectbox if s.label=='Historisk datagrundlag').set_value(old).run(timeout=30)
    assert not app.exception
    assert next(s for s in app.selectbox if s.label=='Historisk datagrundlag').value==old
    assert any('Unsupported squad rules' in e.value for e in app.error)
    assert not any('Kontekst: new-context' in c.value for c in app.code)


def test_new_local_price_preserves_unsaved_bank_squad_and_chips(monkeypatch,tmp_path):
    from copy import deepcopy
    import fpl_model.prototype_data as source
    from fpl_model.my_team import save_profile
    setup(monkeypatch,tmp_path)
    saved=tmp_path/'data/processed/my_team.json'
    save_profile(profile(),saved)
    original_bytes=saved.read_bytes()
    old=tmp_path/'snapshot';new=tmp_path/'new-context';available=[old]
    original=source.load_data(old);fresh=deepcopy(original)
    fresh['players'][0]['now_cost']=39
    fresh['players'][1]['now_cost']=39
    monkeypatch.setattr(source,'snapshot_paths',lambda root:list(reversed(available)))
    monkeypatch.setattr(source,'load_data',lambda path,**kwargs:fresh if Path(path)==new else original)
    app=AppTest.from_file(str(Path(__file__).resolve().parents[1]/'app.py')).run(timeout=30)
    next(w for w in app.number_input if w.label=='Bank (£m)').set_value(2.0).run(timeout=30)
    next(s for s in app.selectbox if s.key=='owned_chip_first_wildcard').set_value('available').run(timeout=30)
    player=next(s for s in app.selectbox if s.key=='owned_id_0')
    player.set_value(3).run(timeout=30)
    available.append(new)
    app.run(timeout=30)
    assert not app.exception
    assert next(w for w in app.number_input if w.label=='Bank (£m)').value==2.0
    assert next(s for s in app.selectbox if s.key=='owned_id_0').value==3
    assert next(w for w in app.number_input if w.key=='owned_sale_1').value==3.9
    assert next(s for s in app.selectbox if s.key=='owned_chip_first_wildcard').value=='available'
    assert saved.read_bytes()==original_bytes
