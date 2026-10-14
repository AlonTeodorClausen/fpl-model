import importlib.util
import json
from pathlib import Path
from streamlit.testing.v1 import AppTest
from test_role_minutes import pool


def test_report_uses_identical_rows_and_prior_groups_and_local_cli(monkeypatch,tmp_path):
    spec=importlib.util.spec_from_file_location('compare_role_minutes',Path(__file__).resolve().parents[1]/'scripts/compare_role_minutes.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    monkeypatch.setattr(module,'load_data',lambda p:pool())
    assert module.main(['--snapshot',str(tmp_path/'snapshot'),'--output-root',str(tmp_path/'artifacts/role_minutes'),'--draws','100'])==0
    paths=list((tmp_path/'artifacts/role_minutes').glob('*/comparison.json'));assert len(paths)==1
    report=json.loads(paths[0].read_text())
    assert report['kind']=='retrospective_development'
    assert len(report['summary'])==4
    assert {r['model'] for r in report['summary']}=={'baseline','recent_role','role_transitions','reference'}
    assert len({r['n'] for r in report['summary']})==1
    assert {'starter','reserve','substitute','rotation'}<={r['group'] for r in report['by_role']}
    assert report['metadata']['candidate_options']['shared_goals'] is False
    # Show saved report without recomputing predictions or needing saved live forecasts.
    from fpl_model.ui.model_quality import show_role_comparison
    app=AppTest.from_function(show_role_comparison,args=(tmp_path,)).run()
    assert not app.exception
    assert any('Ny rollespecifik model' in f.value.to_string() for f in app.dataframe)


def test_app_keeps_baseline_default_and_new_variant_has_no_implicit_odds(monkeypatch,tmp_path):
    from test_my_team_app import setup
    setup(monkeypatch,tmp_path)
    from fpl_model.my_team import save_profile
    from test_my_team import profile
    save_profile(profile(),tmp_path/'data/processed/my_team.json')
    app=AppTest.from_file(str(Path(__file__).resolve().parents[1]/'app.py')).run(timeout=30)
    next(w for w in app.radio if w.label=='Side').set_value('Analyse og eksperimenter')
    app.run(timeout=30)
    next(w for w in app.radio if w.label=='Analysevisning').set_value('Transferlaboratorium').run(timeout=30)
    model=next(w for w in app.selectbox if w.label=='Prognosemodel')
    assert model.value=='Baseline'
    model.set_value('Eksperiment · rollespecifik spilletid').run()
    assert not app.exception
    assert not any(w.label=='Gemt odds-snapshot' for w in app.selectbox)
    import fpl_model.ui.my_team as ui
    actual=ui.forecast_bundle
    def checked(*args,**kw):
        assert kw['evolution'].minutes_method=='role_transitions_v2'
        assert not kw['evolution'].shared_goals and kw['odds'] is None
        return actual(*args,**kw)
    monkeypatch.setattr(ui,'forecast_bundle',checked)
    next(b for b in app.button if b.label=='Sammenlign transferforslag').click().run(timeout=60)
    assert not app.exception
    assert list((tmp_path/'artifacts/transfers').glob('*/report.json'))
