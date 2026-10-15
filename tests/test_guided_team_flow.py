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
    assert next(r for r in first.radio if r.label == 'Side').options == ['Mit hold']
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
