"""The bounded experiment must preserve v1 and the existing comparison basis."""
import copy
import importlib.util
from dataclasses import asdict, replace
import pytest
from test_history_coverage_evaluation import history_data
from fpl_model.models.baseline import BaselineConfig, player_parameters
from fpl_model.backtest.walk_forward import evaluate_sample


def experiment():
    assert importlib.util.find_spec('fpl_model.minutes_experiment'), 'experiment missing'
    from fpl_model import minutes_experiment
    return minutes_experiment


def anchor():
    d=history_data();d['manifest_sha256']='digest'
    return d,dict(snapshot_id=d['snapshot_id'],manifest_sha256='digest',
                  evaluation=evaluate_sample(d,BaselineConfig(),draws=100,seed=42))


def test_prior_strengths_are_independent_and_preserve_empty_history_fallback():
    assert 'frequency_prior_games' in asdict(BaselineConfig())
    d=history_data();own=[r for r in d['histories'] if r['player_id']==1]
    c=BaselineConfig();a=player_parameters(d['players'][0],own,4,c)
    b=player_parameters(d['players'][0],own,4,replace(c,frequency_prior_games=.1))
    assert b['p_start']==pytest.approx((4+.1*.45)/4.1)
    assert b['start_minutes']==a['start_minutes'] and b['sub_minutes']==a['sub_minutes']
    assert b['goals']==a['goals'] and b['fallbacks']==a['fallbacks']
    k=player_parameters(d['players'][0],own,4,replace(c,minutes_prior_games=3))
    assert k['p_start']==a['p_start'] and k['start_minutes']!=a['start_minutes']
    for strength in (1,.25,.1):
        p=player_parameters(dict(element_type=3),[],4,replace(c,frequency_prior_games=strength))
        assert p['p_start']==pytest.approx(.45) and p['p_sub']==pytest.approx(.1)
        assert p['basis']=='explicit_priors' and 'minutes_explicit_prior' in p['fallbacks']
    with pytest.raises(ValueError): replace(c,frequency_prior_games=0)


def test_fixed_variants_share_all_rows_and_reference_and_preserve_anchor():
    m=experiment();d,a=anchor();original=copy.deepcopy(a)
    r=m.run_experiment(d,a,seeds=[42])
    assert a==original
    assert len(r['runs'])==3 and [x['frequency_prior_games'] for x in r['variants']]==[1,.25,.1]
    assert all(x['minutes_prior_games']==1 for x in r['variants'])
    assert r['runs'][0]['evaluation']['rows']==a['evaluation']['rows']
    expected={(x['event'],x['player_id']) for x in a['evaluation']['rows']}
    for run in r['runs']:
        assert {(x['event'],x['player_id']) for x in run['evaluation']['rows']}==expected
        assert run['evaluation']['model_version']==run['model_version']
    overall=[x for x in r['metrics'] if x['dimension']=='scope' and x['group']=='all']
    assert len(overall)==4 and all(x['n']==4 for x in overall)
    assert all('dnp_observed' in x and 'minutes_bias' in x and 'point_crps' in x for x in overall)
    assert r['data_role']=='development' and r['default_model_changed'] is False
    assert r==m.run_experiment(d,a,seeds=[42])


def test_mismatched_snapshot_or_rows_are_rejected():
    m=experiment();d,a=anchor()
    bad=copy.deepcopy(a);bad['manifest_sha256']='different'
    with pytest.raises(ValueError,match='snapshot'): m.run_experiment(d,bad,seeds=[42])
    bad=copy.deepcopy(a);bad['evaluation']['rows'][0]['actual_minutes']+=1
    with pytest.raises(ValueError,match='rows'): m.run_experiment(d,bad,seeds=[42])
    with pytest.raises(ValueError,match='seeds'): m.run_experiment(d,a,seeds=[1,2,3,4])


def test_groups_and_pair_counts_include_regular_players_and_seed_spread():
    m=experiment();d,a=anchor();r=m.run_experiment(d,a,seeds=[42,43,44])
    groups={(x['dimension'],x['group']) for x in r['metrics']}
    assert ('scope','regular') in groups and ('start_history','never_started') in groups
    assert ('position','1') in groups and ('gameweek','3') in groups
    regular=[x for x in r['metrics'] if x['dimension']=='scope' and x['group']=='regular']
    assert all(x['n']==2 for x in regular)
    assert r['seed_sensitivity'] and all(x['seeds']==3 for x in r['seed_sensitivity'])
    assert all('point_crps_delta_min' in x for x in r['seed_sensitivity'])


def test_save_is_exclusive_and_generated_report_is_loadable(tmp_path):
    import json
    m=experiment();d,a=anchor();r=m.run_experiment(d,a,seeds=[42])
    out=m.save_experiment(r,tmp_path/'run')
    assert json.loads((out/'comparison.json').read_text())==r
    assert (out/'metrics.csv').is_file()
    with pytest.raises(FileExistsError): m.save_experiment(r,out)


def test_future_target_changes_cannot_change_group_assignment_or_earlier_predictions():
    m=experiment();d,a=anchor()
    before=m.run_experiment(d,a,seeds=[42])
    changed=copy.deepcopy(d)
    for row in changed['histories']:
        if row['event']==4: row.update(minutes=20,starts=0,total_points=99)
    updated={**a,'evaluation':evaluate_sample(changed,BaselineConfig(),draws=100,seed=42)}
    after=m.run_experiment(changed,updated,seeds=[42])
    for old,new in zip(before['runs'],after['runs']):
        assert [r for r in old['evaluation']['rows'] if r['event']==3]==[r for r in new['evaluation']['rows'] if r['event']==3]
        for x,y in zip(old['evaluation']['minute_diagnostics']['rows'],new['evaluation']['minute_diagnostics']['rows']):
            for key in ('regular','start_group','minute_group','prior'):
                assert x[key]==y[key]


def test_cli_uses_saved_anchor_and_writes_reproducible_metadata(monkeypatch,tmp_path,capsys):
    import importlib.util
    import json
    from pathlib import Path
    spec=importlib.util.spec_from_file_location('compare_minutes_priors',Path(__file__).resolve().parents[1]/'scripts/compare_minutes_priors.py')
    cli=importlib.util.module_from_spec(spec);spec.loader.exec_module(cli)
    d,a=anchor();a['snapshot_path']=str(tmp_path/'raw'/'snapshot')
    d['snapshot_path']=a['snapshot_path']
    path=tmp_path/'anchor.json';path.write_text(json.dumps(a))
    monkeypatch.setattr(cli,'load_data',lambda p:d)
    out=tmp_path/'result'
    assert cli.main(['--reference-run',str(path),'--output',str(out)])==0
    r=json.loads((out/'comparison.json').read_text())
    assert r['anchor_file_sha256'] and r['anchor_path']==str(path)
    assert r['seeds']==[42,43,44] and r['draws']==100
    assert json.loads(capsys.readouterr().out)['data_role']=='development'
    with pytest.raises(ValueError,match='raw storage'):
        experiment().save_experiment(r,tmp_path/'raw'/'forbidden')


def test_seed_summary_reuses_metrics_and_does_not_multiply_observation_counts():
    m=experiment()
    assert hasattr(m,'summarize_seeds')
    rows=[dict(seed=seed,model_version='baseline',dimension='scope',group='all',n=10,players=4,
               **{key:value for key in m.METRICS}) for seed,value in [(42,1.),(43,3.),(44,2.)]]
    original=copy.deepcopy(rows)
    result=m.summarize_seeds(rows)
    assert result==m.summarize_seeds(list(reversed(rows)))
    assert rows==original and len(result)==1
    x=result[0]
    assert x['n']==10 and x['seed_count']==3
    assert x['minutes_mae_mean']==2 and x['minutes_mae_min']==1 and x['minutes_mae_max']==3
    with pytest.raises(ValueError): m.summarize_seeds(rows+[rows[0]])
    rows[0]['n']=11
    with pytest.raises(ValueError): m.summarize_seeds(rows)


def test_saved_comparison_summary_never_simulates_or_loads_snapshot(monkeypatch,tmp_path,capsys):
    import json
    import importlib.util
    from pathlib import Path
    m=experiment();d,a=anchor();report=m.run_experiment(d,a,seeds=[42])
    source=m.save_experiment(report,tmp_path/'source')/'comparison.json'
    original=source.read_bytes()
    spec=importlib.util.spec_from_file_location('compare_minutes_priors_saved',Path(__file__).resolve().parents[1]/'scripts/compare_minutes_priors.py')
    cli=importlib.util.module_from_spec(spec);spec.loader.exec_module(cli)
    def forbidden(*args,**kwargs): raise AssertionError('Must reuse saved results')
    monkeypatch.setattr(cli,'run_experiment',forbidden);monkeypatch.setattr(cli,'load_data',forbidden)
    out=tmp_path/'summary'
    assert cli.main(['--saved-comparison',str(source),'--output',str(out)])==0
    saved=json.loads((out/'comparison.json').read_text())
    assert saved['runs']==report['runs'] and saved['metrics']==report['metrics']
    assert saved['seed_summary'] and saved['derived_from_sha256']
    assert (out/'seed_summary.csv').is_file() and source.read_bytes()==original
