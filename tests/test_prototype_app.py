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
