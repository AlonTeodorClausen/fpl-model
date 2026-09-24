"""Streamlit smoke test uses synthetic offline data, not local user snapshots."""
from pathlib import Path
from streamlit.testing.v1 import AppTest
from test_prototype import data


def test_app_runs_forecasts_optimization_and_evaluation(monkeypatch,tmp_path):
    import fpl_model.prototype_data as source
    d=data();d['teams']=[dict(id=i,short_name=f'T{i}') for i in range(1,11)]
    d['quarantine']=[]
    monkeypatch.setattr(source,'snapshot_paths',lambda root:[tmp_path])
    monkeypatch.setattr(source,'load_data',lambda path:d)
    app=AppTest.from_file(str(Path(__file__).resolve().parents[1]/'app.py')).run(timeout=30)
    assert not app.exception
    app.button[0].click().run(timeout=60)
    assert not app.exception
    assert len(app.metric)==4 and len(app.dataframe)>=2
    next(w for w in app.number_input if w.label=='Budget (£m, ny trup)').set_value(90.).run()
    assert any('Indstillingerne er ændret' in w.value for w in app.warning)
