"""Compare one previous-season attack prior on existing captures; no downloads."""
import argparse
from collections import Counter
from dataclasses import asdict
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path
import sys
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from fpl_model.season_priors import SeasonPriorConfig,VERSION
from fpl_model.models.baseline import BaselineConfig
from fpl_model.prototype_data import load_data
from fpl_model.backtest.walk_forward import evaluate_sample
from fpl_model.simulation import simulate
from fpl_model.transfer_planner import save_report


def metrics(rows,reference=False):
    if not rows:return dict(n=0,players=0,point_MAE=None,point_RMSE=None,CRPS=None)
    errors=np.array([r['reference' if reference else 'predicted']-r['actual'] for r in rows])
    return dict(n=len(rows),players=len({r['player_id'] for r in rows}),
        point_MAE=float(abs(errors).mean()),point_RMSE=float(np.sqrt(np.mean(errors**2))),
        CRPS=None if reference else float(np.mean([r['crps'] for r in rows])))


def compare_evaluation(data,options,*,draws=3000,seed=42):
    cfg=BaselineConfig()
    evaluations={name:evaluate_sample(data,cfg,draws=draws,seed=seed,season_prior_config=option)
        for name,option in [('baseline',None),('previous_season',options)]}
    b=evaluations['baseline'];c=evaluations['previous_season'];key=lambda r:(r['event'],r['player_id'])
    if [key(r) for r in b['rows']]!=[key(r) for r in c['rows']]:raise ValueError('Different evaluation rows')
    if any(x['predicted_minutes']!=y['predicted_minutes'] or x['p_no_play']!=y['p_no_play'] for x,y in zip(b['rows'],c['rows'])):
        raise ValueError('Attack prior changed playing time')
    variants={**evaluations,'prior_average':b};regular={key(r):r['regular'] for r in b['minute_diagnostics']['rows']}
    coverage={key(r):r['season_prior']['status'] for r in c['rows']}
    grouped={}
    for dim,fn in dict(by_position=lambda r:r['position'],by_gameweek=lambda r:r['event'],
            by_prior_history=lambda r:'regular' if regular[key(r)] else 'other',
            by_prior_coverage=lambda r:coverage[key(r)]).items():
        grouped[dim]=[dict(model=name,group=g,**metrics([r for r in v['rows'] if fn(r)==g],name=='prior_average'))
            for name,v in variants.items() for g in sorted({fn(r) for r in v['rows']})]
    return dict(kind='retrospective_development',version=VERSION,config=asdict(cfg),season_prior_config=asdict(options),
        snapshot_id=data['snapshot_id'],snapshot_path=data.get('snapshot_path'),manifest_sha256=data.get('manifest_sha256'),
        data_available_at=data['as_of_at'],draws=draws,seed=seed,seed_strategy='seed + event',gameweeks=b['gameweeks'],
        summary=[dict(model=k,**metrics(v['rows'],k=='prior_average')) for k,v in variants.items()],
        **grouped,evaluations=evaluations,regular_rule=b['minute_diagnostics']['regular_rule'],
        prior_coverage=dict(Counter(coverage.values())),
        limitations=b['limitations']+['GW3–5 are development data, not independent validation.',
            'Last season aggregates were captured later; publication times at old deadlines are unknown.',
            'Only xG/xA prior means change; fixed weight of baseline prior_90s, no tuning.',
            'Former club, role, position and penalties may differ. No automatic age or transfer adjustment.'])


def compare_forecast(data,coverage,options,*,draws=3000,seed=42):
    common=dict(draws=draws,seed=seed,defensive_odds=coverage,odds_scope='attack_and_defence')
    event=coverage['event'];base='component_attacking_odds_v1'
    b=simulate(data,event,BaselineConfig(),**common)
    c=simulate(data,event,BaselineConfig(),**common,season_prior_config=options)
    if not np.array_equal(b.minutes,c.minutes):raise ValueError('Prior changed minutes')
    changes=[]
    for before,after in zip(b.summary(),c.summary()):
        pid=before['player_id'];old=b.explanations[pid]['point_components'];new=c.explanations[pid]['point_components']
        if any(new[k]!=v for k,v in old.items() if k not in ('goals','assists')):raise ValueError('Prior changed nonattack component')
        delta=after['xp']-before['xp'];goal=new['goals']-old['goals'];assist=new['assists']-old['assists']
        if not np.isclose(delta,goal+assist):raise ValueError('Attack change did not reconcile')
        changes.append(dict(player_id=pid,name=before['name'],position=before['position'],expected_minutes=before['expected_minutes'],
            reference_xp=before['xp'],previous_season_xp=after['xp'],xp_delta=delta,goal_delta=goal,assist_delta=assist,
            prior=c.explanations[pid]['season_prior'],
            rates={k:dict(reference=b.parameters[pid][k],candidate=c.parameters[pid][k]) for k in ('goals','assists')}))
    return {base:b,base+'__'+VERSION:c},dict(kind='forecast_comparison_not_performance',event=event,draws=draws,seed=seed,
        usable_fixtures=coverage['usable'],expected_fixtures=coverage['expected_fixtures'],
        prior_coverage=dict(Counter(r['prior']['status'] for r in changes)),
        fallback_reasons=dict(Counter(r['prior']['reason'] for r in changes if r['prior']['reason'])),
        player_changes=sorted(changes,key=lambda r:(-abs(r['xp_delta']),r['player_id'])),
        invariants=dict(minutes_identical=True,nonattack_components_identical=True))


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--snapshot',type=Path,required=True)
    p.add_argument('--context-snapshot',type=Path);p.add_argument('--odds-snapshot',type=Path)
    p.add_argument('--draws',type=int,default=3000);p.add_argument('--seed',type=int,default=42)
    p.add_argument('--output-root',type=Path,default=Path('artifacts/season_priors'))
    args=p.parse_args(argv)
    if bool(args.context_snapshot)!=bool(args.odds_snapshot):p.error('Provide both context and odds for the prospective comparison')
    data=load_data(args.snapshot,include_season_history=True);options=SeasonPriorConfig()
    print('Previous-season prior comparison: existing captures only, no downloads.',flush=True)
    report=compare_evaluation(data,options,draws=args.draws,seed=args.seed)
    root=Path(__file__).resolve().parents[1]
    files=['scripts/compare_season_priors.py','src/fpl_model/season_priors.py','src/fpl_model/models/baseline.py',
        'src/fpl_model/simulation.py','src/fpl_model/backtest/walk_forward.py','src/fpl_model/prototype_data.py',
        'src/fpl_model/scoring.py','src/fpl_model/history_coverage.py']
    report['code_sha256']={f:hashlib.sha256((root/f).read_bytes()).hexdigest() for f in files}
    out=save_report(report,args.output_root/'development')
    print(json.dumps(dict(development_path=str(out),summary=report['summary'],prior_coverage=report['prior_coverage']),ensure_ascii=False,indent=2),flush=True)
    if args.context_snapshot:
        from fpl_model.odds_comparison import load_inputs,load_odds
        from fpl_model.defensive_odds import build_coverage
        from fpl_model.prediction_evaluation import save_forecasts
        from fpl_model.label_contracts import utc
        origin=datetime.now(timezone.utc).isoformat()
        d=load_inputs(args.snapshot,args.context_snapshot,origin,include_season_history=True)
        event=min(e['id'] for e in d['events'] if utc(e['deadline_time'])>utc(origin))
        odds,source=load_odds(args.odds_snapshot,'the_odds_api')
        coverage=build_coverage(d,odds,source,event,BaselineConfig(),origin)
        sims,comparison=compare_forecast(d,coverage,options,draws=args.draws,seed=args.seed)
        comparison['development_report']=str(out.resolve()/'report.json')
        path=save_forecasts(d,event,sims,BaselineConfig(),None,coverage,args.output_root/'forecasts',season_prior_config=options)
        with (path/'comparison.json').open('x') as f:json.dump(comparison,f,ensure_ascii=False,indent=2,allow_nan=False)
        print(json.dumps(dict(forecast_path=str(path),event=event,odds_coverage=coverage['usable'],prior_coverage=comparison['prior_coverage'],
            top_changes=[{k:r[k] for k in ('name','reference_xp','previous_season_xp','xp_delta')} for r in comparison['player_changes'][:5]]),ensure_ascii=False,indent=2))
    return 0


if __name__=='__main__':raise SystemExit(main())
