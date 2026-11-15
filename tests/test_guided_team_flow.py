"""A guest must never inherit another visitor's team or saved strategy."""
from pathlib import Path

from streamlit.testing.v1 import AppTest

from test_my_team import profile
from test_my_team_app import setup


APP = str(Path(__file__).resolve().parents[1] / 'app.py')


def test_guest_starts_with_own_empty_team_and_no_shared_files(monkeypatch, tmp_path):
    setup(monkeypatch, tmp_path)
    monkeypatch.setenv('FPL_PUBLIC_GUEST_MODE', '1')
    from fpl_model.my_team import save_profile
    shared = tmp_path / 'data/processed/my_team.json'
    save_profile(profile(), shared)
    original = shared.read_bytes()
    report = tmp_path / 'artifacts/transfers/previous/report.json'
    report.parent.mkdir(parents=True)
    report.write_text('{}')

    first = AppTest.from_file(APP).run(timeout=30)
    second = AppTest.from_file(APP).run(timeout=30)
    assert not first.exception and not second.exception
    assert next(w for w in first.number_input if w.label == 'Bank (£m)').value is None
    assert next(w for w in second.number_input if w.label == 'Bank (£m)').value is None
    assert not any(b.label in ('Hent seneste data', 'Hent fuld spillerhistorik') for b in first.button)
    assert not any(e.label == 'Åbn tidligere transferforslag' for e in first.expander)
    assert next(r for r in first.radio if r.label == 'Side').options == ['Mit hold', 'Model']
    assert not any('Analyse og eksperimenter' in i.value for i in first.info)
    assert not any('Redigér hold' in i.value for i in first.info)
    assert shared.read_bytes() == original


def test_guest_save_is_session_only_and_profile_can_be_exported(monkeypatch, tmp_path):
    setup(monkeypatch, tmp_path)
    monkeypatch.setenv('FPL_PUBLIC_GUEST_MODE', '1')
    from fpl_model.my_team import save_profile, load_profile
    shared = tmp_path / 'data/processed/my_team.json'
    old = profile()
    save_profile(old, shared)
    app = AppTest.from_file(APP).run(timeout=30)
    app.session_state['team_draft'] = dict(old, bank=20)
    app.run(timeout=30)
    next(b for b in app.button if b.label == 'Gem hold').click().run(timeout=30)
    assert not app.exception
    assert load_profile(shared)['bank'] == old['bank']
    assert app.session_state['team_draft']['bank'] == 20
    other = AppTest.from_file(APP).run(timeout=30)
    assert next(w for w in other.number_input if w.label == 'Bank (£m)').value is None


def test_guest_strategy_stays_in_session_and_private_cache(monkeypatch, tmp_path):
    setup(monkeypatch, tmp_path)
    monkeypatch.setenv('FPL_PUBLIC_GUEST_MODE', '1')
    app = AppTest.from_file(APP)
    app.session_state['team_draft'] = profile()
    app.run(timeout=30)
    next(b for b in app.button if b.label == 'Sammenlign transferforslag').click().run(timeout=60)
    assert not app.exception
    assert app.session_state['transfer_result']['scope'] == 'transfer_sequences'
    assert not list((tmp_path / 'artifacts/transfers').glob('*/report.json'))
    assert not (tmp_path / 'artifacts/transfer_forecasts').exists()
    assert Path(app.session_state['_guest_temp_directory'].name).is_dir()
    other = AppTest.from_file(APP).run(timeout=30)
    assert 'transfer_result' not in other.session_state


def test_main_page_shows_one_recommendation_but_keeps_strategy_details(monkeypatch, tmp_path):
    setup(monkeypatch, tmp_path)
    from fpl_model.my_team import save_profile
    save_profile(profile(), tmp_path / 'data/processed/my_team.json')
    app = AppTest.from_file(APP).run(timeout=30)
    next(b for b in app.button if b.label == 'Sammenlign transferforslag').click().run(timeout=60)
    assert not app.exception
    assert not any('Strategi uge for uge' in s.value for s in app.subheader)
    assert any(w.label == 'Strategi – se ugeplan' for w in app.selectbox)
    assert any(r.label == 'Opstillingsvisning' for r in app.radio)
    assert any('Hvorfor dette forslag?' in h.value for h in app.subheader)
    assert any('Samme evalueringsscenarier' in c.value for c in app.caption)
    assert any('mod behold' in c.value.lower() for c in app.caption)


def test_guest_team_import_captures_outside_shared_raw_data(monkeypatch, tmp_path):
    setup(monkeypatch, tmp_path)
    monkeypatch.setenv('FPL_PUBLIC_GUEST_MODE', '1')
    import fpl_model.ui.team_import as importer
    captured_roots = []

    def capture(_value, raw_root):
        captured_roots.append(raw_root)
        raise ValueError('Import unavailable in offline test')

    monkeypatch.setattr(importer, 'capture_team', capture)
    app = AppTest.from_file(APP).run(timeout=30)
    next(w for w in app.text_input if w.label == 'Hold-ID eller FPL-link').set_value('3533723')
    next(b for b in app.button if b.label == 'Hent hold fra FPL').click().run(timeout=30)
    assert not app.exception and len(captured_roots) == 1
    assert captured_roots[0] == Path(app.session_state['_guest_temp_directory'].name) / 'data/raw'
    assert captured_roots[0] != tmp_path / 'data/raw'


def test_guest_requires_an_explicit_active_publication(monkeypatch, tmp_path):
    ui = setup(monkeypatch, tmp_path)
    monkeypatch.setenv('FPL_PUBLIC_GUEST_MODE', '1')

    def absent(*_args):
        raise ValueError('No active public data publication')

    monkeypatch.setattr(ui, 'read_active_public_data', absent)
    app = AppTest.from_file(APP).run(timeout=30)
    assert not app.exception
    assert any('publiceret' in e.value for e in app.error)
    assert not any(b.label == 'Sammenlign transferforslag' for b in app.button)


def test_guest_uses_pinned_context_instead_of_newest_raw_snapshot(monkeypatch, tmp_path):
    ui = setup(monkeypatch, tmp_path)
    monkeypatch.setenv('FPL_PUBLIC_GUEST_MODE', '1')
    import fpl_model.prototype_data as source

    selected = tmp_path / 'older-published'
    monkeypatch.setattr(source, 'snapshot_paths', lambda *_: [tmp_path / 'newer-unpublished'])
    monkeypatch.setattr(ui, 'read_active_public_data', lambda *_: dict(
        publication_id='published-version', context_path=selected, history_path=selected))
    seen = []
    original = source.load_data

    def load(path, **kwargs):
        seen.append(path)
        return original(path, **kwargs)

    monkeypatch.setattr(source, 'load_data', load)
    app = AppTest.from_file(APP).run(timeout=30)
    assert not app.exception and seen == [selected]
    assert not any('published-version' in c.value for c in app.caption)


def test_guided_homepage_shows_import_and_clear_decision_before_details(monkeypatch, tmp_path):
    setup(monkeypatch, tmp_path)
    app = AppTest.from_file(APP).run(timeout=30)
    assert not app.exception
    labels = [s.value for s in app.subheader]
    assert any('1. Dit hold' in label for label in labels)
    assert any('2. Planlæg' in label for label in labels)
    assert any('3. Forslag' in label for label in labels)
    assert any(w.label == 'Hold-ID eller FPL-link' for w in app.text_input)


def test_sequence_decision_uses_recommended_plan_and_same_hold_reference():
    from fpl_model.ui.decision_summary import sequence_decision
    report = dict(recommendation=dict(plan_id='first_1'), packages=[
        dict(plan_id='hold', label='Behold', comparison_family='hold', total_points=30.,
             total_gain=0., next_gw_gain=0., objective=30., hits=0,
             steps=[dict(event=7, count=0, out=[], **{'in': []}, bank_after=10, hits=0)],
             per_gw=[dict(event=7, mean=30., gain=0.)]),
        dict(plan_id='first_1', label='Én transfer', comparison_family='ordinary',
             total_points=34., total_gain=4., next_gw_gain=4., objective=35., hits=0,
             steps=[dict(event=7, count=1, out=[2], **{'in': [3]}, bank_after=5, hits=0)],
             per_gw=[dict(event=7, mean=34., gain=4.)])])
    summary = sequence_decision(report)
    assert summary['plan_id'] == 'first_1'
    assert summary['out'] == [2] and summary['in'] == [3]
    assert summary['next_gw_gain'] == 4. and summary['horizon_gain'] == 4.
    assert summary['hold_points'] == 30. and summary['plan_points'] == 34.
    assert summary['bank_after'] == 5 and summary['hits'] == 0


def test_compact_alternatives_hide_duplicate_first_actions_with_same_gain():
    from fpl_model.ui.decision_summary import alternative_previews

    hold = dict(plan_id='hold', label='Behold', objective=50., next_gw_gain=0.,
                total_gain=0., hits=0, steps=[dict(out=[], **{'in': []}, chip=None)])
    duplicate = dict(plan_id='wait', label='0 nu → fortsættelse', objective=50.,
                     next_gw_gain=0., total_gain=0., hits=0,
                     steps=[dict(out=[], **{'in': []}, chip=None)])
    transfer = dict(plan_id='move', label='Én transfer', objective=49.,
                    next_gw_gain=-.2, total_gain=.4, hits=0,
                    steps=[dict(out=[7], **{'in': [8]}, chip=None)])
    rows = alternative_previews([hold, duplicate, transfer], hold)
    assert [row['label'] for row in rows] == ['Én transfer']
    assert rows[0]['total_gain'] == .4


def test_decision_evidence_reconciles_team_contributions_hits_and_autosub():
    from fpl_model.ui.decision_summary import decision_evidence
    hold=dict(plan_id='hold',count=0,objective=9.,total_gain=0.,total_points=9.,hits=0,
              squad=[1,2],per_gw=[dict(event=8,mean=9.,gain=0.,bench_mean=1.,hits=0,
                player_mean_points={1:dict(xi=4.,autosub=1.,captain=0.,total=5.),
                                    2:dict(xi=3.,autosub=0.,captain=1.,total=4.)})])
    move=dict(plan_id='move',count=1,objective=11.,total_gain=-2.,total_points=7.,hits=4,
              squad=[2,3],per_gw=[dict(event=8,mean=7.,gain=-2.,bench_mean=3.,hits=4,
                player_mean_points={2:dict(xi=1.,autosub=0.,captain=0.,total=1.),
                                    3:dict(xi=6.,autosub=3.,captain=1.,total=10.)})])
    report=dict(packages=[hold,move],players_by_event={8:[dict(player_id=i,name=f'P{i}') for i in (1,2,3)]})
    evidence=decision_evidence(report,move)
    assert evidence['available']
    assert evidence['next_gw']['bench_delta']==2
    assert evidence['horizon']['xi_delta']+evidence['horizon']['autosub_delta']+evidence['horizon']['captain_delta']-evidence['horizon']['hits_delta']==-2
    assert [(x['player_id'],x['change']) for x in evidence['drivers']]==[(3,10.),(2,-3.),(1,-5.)]
    assert evidence['drivers'][0]['kind']=='ind'
    assert evidence['drivers'][-1]['kind']=='ud'


def test_legacy_decision_report_does_not_invent_contribution_breakdown():
    from fpl_model.ui.decision_summary import decision_evidence
    hold=dict(plan_id='hold',count=0,per_gw=[dict(event=8,mean=9.,gain=0.)])
    move=dict(plan_id='move',count=1,per_gw=[dict(event=8,mean=10.,gain=1.)])
    assert decision_evidence(dict(packages=[hold,move]),move)==dict(available=False)
