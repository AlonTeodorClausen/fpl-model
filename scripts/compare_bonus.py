"""One conditional-bonus experiment on existing snapshots; no downloads/tuning."""
import argparse
from dataclasses import asdict
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path
import sys
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from fpl_model.conditional_bonus import BonusConfig,VERSION
from fpl_model.models.baseline import BaselineConfig
from fpl_model.prototype_data import load_data
from fpl_model.backtest.walk_forward import evaluate_sample
from fpl_model.simulation import simulate
from fpl_model.transfer_planner import save_report


def metrics(rows,reference=False):
    def error(actual,pred):
        valid=[r for r in rows if r.get(actual) is not None and r.get(pred) is not None]
        if not valid:return dict(n=0,bias=None,mae=None,rmse=None)
        e=np.array([r[pred]-r[actual] for r in valid])
        return dict(n=len(e),bias=float(e.mean()),mae=float(abs(e).mean()),rmse=float(np.sqrt(np.mean(e*e))))
    points=error('actual','reference' if reference else 'predicted')
    bonus=error('actual_bonus','reference_bonus' if reference else 'predicted_bonus')
    return dict(n=len(rows),players=len({r['player_id'] for r in rows}),
        point_MAE=points['mae'],point_RMSE=points['rmse'],
        CRPS=None if reference or not rows else float(np.mean([r['crps'] for r in rows])),
        bonus_n=bonus['n'],bonus_bias=bonus['bias'],bonus_MAE=bonus['mae'],bonus_RMSE=bonus['rmse'])


def compare_evaluation(data,options,*,draws=3000,seed=42):
    cfg=BaselineConfig();evaluations={}
    for name,option in [('baseline',None),('conditional_bonus',options)]:
        evaluations[name]=evaluate_sample(data,cfg,draws=draws,seed=seed,bonus_config=option,bonus_diagnostics=True)
    b=evaluations['baseline'];c=evaluations['conditional_bonus']
    key=lambda r:(r['event'],r['player_id'])
    if [key(r) for r in b['rows']]!=[key(r) for r in c['rows']]:raise ValueError('Different evaluation rows')
    for before,after in zip(b['rows'],c['rows']):
        if before['predicted_minutes']!=after['predicted_minutes'] or before['p_no_play']!=after['p_no_play']:
            raise ValueError('Bonus changed playing time')
        if not np.isclose(after['predicted']-before['predicted'],after['predicted_bonus']-before['predicted_bonus']):
            raise ValueError('Bonus comparison did not reconcile')
    variants={**evaluations,'prior_average':b}
    regular={key(r):r['regular'] for r in b['minute_diagnostics']['rows']}
    grouped={}
    for dim,fn in dict(by_position=lambda r:r['position'],by_gameweek=lambda r:r['event'],
            by_prior_history=lambda r:'regular' if regular[key(r)] else 'other').items():
        grouped[dim]=[dict(model=name,group=g,**metrics([r for r in v['rows'] if fn(r)==g],name=='prior_average'))
            for name,v in variants.items() for g in sorted({fn(r) for r in v['rows']})]
    return dict(kind='retrospective_development',version=VERSION,config=asdict(cfg),bonus_config=asdict(options),
        snapshot_id=data['snapshot_id'],snapshot_path=data.get('snapshot_path'),manifest_sha256=data.get('manifest_sha256'),
        data_available_at=data['as_of_at'],draws=draws,seed=seed,seed_strategy='seed + event',gameweeks=b['gameweeks'],
        summary=[dict(model=k,**metrics(v['rows'],k=='prior_average')) for k,v in variants.items()],
        **grouped,evaluations=evaluations,regular_rule=b['minute_diagnostics']['regular_rule'],
        limitations=b['limitations']+['GW3–5 are development data, not independent validation.',
            'Training uses realized events of earlier matches; predictions use simulated events only.',
            'Independent binomial 0–3 bonuses, no BPS competition or fixed match bonus budget.',
            'Fixed ridge=1 and minimum training coverage; no parameter search. Baseline stays default.'])


def compare_forecast(data,coverage,options,*,draws=3000,seed=42):
    common=dict(draws=draws,seed=seed,defensive_odds=coverage,odds_scope='attack_and_defence')
    event=coverage['event'];base='component_attacking_odds_v1'
    b=simulate(data,event,BaselineConfig(),**common)
    c=simulate(data,event,BaselineConfig(),**common,bonus_config=options)
    if not np.array_equal(b.minutes,c.minutes):raise ValueError('Bonus changed minutes')
    changes=[]
    for before,after in zip(b.summary(),c.summary()):
        pid=before['player_id'];old=b.explanations[pid]['point_components'];new=c.explanations[pid]['point_components']
        if any(new[k]!=v for k,v in old.items() if k!='bonus'):raise ValueError('Bonus changed another component')
        delta=after['xp']-before['xp']
        if not np.isclose(delta,new['bonus']-old['bonus']):raise ValueError('Bonus difference not reconciled')
        changes.append(dict(player_id=pid,name=before['name'],position=before['position'],expected_minutes=before['expected_minutes'],
            reference_xp=before['xp'],conditional_bonus_xp=after['xp'],xp_delta=delta,
            reference_bonus=old['bonus'],conditional_bonus=new['bonus'],bonus_delta=new['bonus']-old['bonus']))
    return {base:b,base+'__'+VERSION:c},dict(kind='forecast_comparison_not_performance',event=event,draws=draws,seed=seed,
        usable_fixtures=coverage['usable'],expected_fixtures=coverage['expected_fixtures'],
        player_changes=sorted(changes,key=lambda r:(-abs(r['xp_delta']),r['player_id'])),
        invariants=dict(minutes_identical=True,other_components_identical=True))


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--snapshot',type=Path,required=True)
    p.add_argument('--context-snapshot',type=Path)
    p.add_argument('--odds-snapshot',type=Path)
    p.add_argument('--draws',type=int,default=3000);p.add_argument('--seed',type=int,default=42)
    p.add_argument('--output-root',type=Path,default=Path('artifacts/conditional_bonus'))
    args=p.parse_args(argv)
    if bool(args.context_snapshot)!=bool(args.odds_snapshot):p.error('Provide both context and odds for the prospective comparison')
    data=load_data(args.snapshot);options=BonusConfig()
    print('Comparing bonus only on the same chronological development rows; no downloads.',flush=True)
    report=compare_evaluation(data,options,draws=args.draws,seed=args.seed)
    root=Path(__file__).resolve().parents[1]
    files=['scripts/compare_bonus.py','src/fpl_model/conditional_bonus.py','src/fpl_model/models/baseline.py',
        'src/fpl_model/simulation.py','src/fpl_model/backtest/walk_forward.py','src/fpl_model/diagnostics.py',
        'src/fpl_model/scoring.py','src/fpl_model/history_coverage.py']
    report['code_sha256']={f:hashlib.sha256((root/f).read_bytes()).hexdigest() for f in files}
    out=save_report(report,args.output_root/'development')
    print(json.dumps(dict(development_path=str(out),summary=report['summary']),ensure_ascii=False,indent=2),flush=True)
    if args.context_snapshot:
        from fpl_model.odds_comparison import load_inputs,load_odds
        from fpl_model.defensive_odds import build_coverage
        from fpl_model.prediction_evaluation import save_forecasts
        from fpl_model.label_contracts import utc
        origin=datetime.now(timezone.utc).isoformat();d=load_inputs(args.snapshot,args.context_snapshot,origin)
        event=min(e['id'] for e in d['events'] if utc(e['deadline_time'])>utc(origin))
        odds,source=load_odds(args.odds_snapshot,'the_odds_api')
        coverage=build_coverage(d,odds,source,event,BaselineConfig(),origin)
        sims,comparison=compare_forecast(d,coverage,options,draws=args.draws,seed=args.seed)
        comparison['development_report']=str(out.resolve()/'report.json')
        path=save_forecasts(d,event,sims,BaselineConfig(),None,coverage,args.output_root/'forecasts',bonus_config=options)
        with (path/'comparison.json').open('x') as f:json.dump(comparison,f,ensure_ascii=False,indent=2,allow_nan=False)
        print(json.dumps(dict(forecast_path=str(path),event=event,odds_coverage=coverage['usable'],top_changes=comparison['player_changes'][:5]),ensure_ascii=False,indent=2))
    return 0


if __name__=='__main__':raise SystemExit(main())
