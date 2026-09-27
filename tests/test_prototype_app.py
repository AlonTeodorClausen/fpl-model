"""Streamlit smoke test uses synthetic offline data, not local user snapshots."""
from pathlib import Path
from streamlit.testing.v1 import AppTest
from test_prototype import data


def test_app_runs_forecasts_optimization_and_evaluation(monkeypatch,tmp_path):
    import fpl_model.prototype_data as source
    import fpl_model.prototype as service
    d=data();d['teams']=[dict(id=i,short_name=f'T{i}') for i in range(1,11)]
    d['quarantine']=[]
    monkeypatch.setattr(source,'snapshot_paths',lambda root:[tmp_path])
    monkeypatch.setattr(source,'load_data',lambda path:d)
    monkeypatch.setattr(service,'save_run',lambda report,output=None:tmp_path/'saved')
    app=AppTest.from_file(str(Path(__file__).resolve().parents[1]/'app.py')).run(timeout=30)
    assert not app.exception
    app.button[0].click().run(timeout=60)
    assert not app.exception
    assert len(app.metric)==4 and len(app.dataframe)>=2
    next(w for w in app.number_input if w.label=='Budget (£m, ny trup)').set_value(90.).run()
    assert any('Indstillingerne er ændret' in w.value for w in app.warning)


def test_app_shows_coverage_and_grouped_evaluation_without_fetching(monkeypatch,tmp_path):
    from test_history_coverage_evaluation import history_data
    import fpl_model.prototype_data as source
    import fpl_model.prototype as service
    d=history_data();d['teams']=[dict(id=i,short_name=f'T{i}') for i in range(1,11)]
    d['coverage']=dict(attempted_players=3,successful_responses=2,empty_history_players=[9],
        failed_players=[10],missing_response_players=[10],quarantined_rows=0,
        accepted_rows=8,explicit_zero_minute_rows=4,players=[])
    monkeypatch.setattr(source,'snapshot_paths',lambda root:[tmp_path])
    monkeypatch.setattr(source,'load_data',lambda path:d)
    # Artifact writing is separately integration-tested; no writes into user data.
    assert hasattr(service,'save_run')
    monkeypatch.setattr(service,'save_run',lambda report,output=None:tmp_path/'saved')
    app=AppTest.from_file(str(Path(__file__).resolve().parents[1]/'app.py')).run(timeout=30)
    assert not app.exception
    assert any('Dækning' in e.value for e in app.markdown)
    app.button[0].click().run(timeout=60)
    assert not app.exception
    assert any('Pr. position' in e.value for e in app.markdown)
    assert any('Pr. gameweek' in e.value for e in app.markdown)
    assert any('Brier' in e.value for e in app.markdown)
    assert any('Spillerforklaring' in e.value for e in app.markdown)
    assert any('Minutdiagnostik' in e.value for e in app.markdown)
    assert any('regelmæssig' in e.value.lower() for e in app.markdown)
    assert any('dobbelt' in e.value for e in app.markdown)
    player_picker=next(w for w in app.selectbox if w.label=='Pointfordeling for spiller')
    player_picker.set_value(5).run(timeout=30)
    assert not app.exception
    assert app.session_state['result'][1].explanations[5]['history']['dnp_frequency']==1


def test_app_can_show_saved_experiment_without_running_forecast(monkeypatch,tmp_path):
    import json
    import fpl_model.prototype_data as source
    import fpl_model.minutes_experiment as experiments
    from test_minutes_experiment import anchor
    d,a=anchor();d['teams']=[dict(id=i,short_name=f'T{i}') for i in range(1,11)]
    report=experiments.run_experiment(d,a,seeds=[42])
    path=experiments.save_experiment(report,tmp_path/'experiment')/'comparison.json'
    monkeypatch.setattr(source,'snapshot_paths',lambda root:[tmp_path])
    monkeypatch.setattr(source,'load_data',lambda path:d)
    assert hasattr(experiments,'comparison_paths')
    monkeypatch.setattr(experiments,'comparison_paths',lambda root:[path])
    app=AppTest.from_file(str(Path(__file__).resolve().parents[1]/'app.py')).run(timeout=30)
    assert not app.exception
    assert any('udviklingsdata' in w.value.lower() for w in app.warning)
    assert any('component_frequency_010_v1' in f.value.to_string() for f in app.dataframe)
    assert any('minutes_bias' in f.value.columns for f in app.dataframe)
