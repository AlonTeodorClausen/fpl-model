"""One fixed role-transition candidate vs existing models; offline, no tuning."""
import argparse
from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys
from uuid import uuid4
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from fpl_model.prototype_data import load_data
from fpl_model.models.baseline import BaselineConfig
from fpl_model.model_evolution import EvolutionConfig
from fpl_model.backtest.walk_forward import evaluate_sample
from fpl_model.transfer_planner import _safe_root


def metrics(rows,name,reference=False):
    def errors(actual,pred):
        e=np.array([r[pred]-r[actual] for r in rows])
        return float(e.mean()),float(abs(e).mean()),float(np.sqrt(np.mean(e*e)))
    if not rows:return dict(model=name,n=0)
    bias,m_mae,m_rmse=errors('actual_minutes','reference_minutes' if reference else 'predicted_minutes')
    _,p_mae,p_rmse=errors('actual','reference' if reference else 'predicted')
    probs=[r['reference_dnp'] if reference else r['p_no_play'] for r in rows]
    return dict(model=name,n=len(rows),players=len({r['player_id'] for r in rows}),minutes_bias=bias,
        minutes_mae=m_mae,minutes_rmse=m_rmse,points_mae=p_mae,points_rmse=p_rmse,
        dnp_brier=float(np.mean([(p-r['actual_dnp'])**2 for p,r in zip(probs,rows)])),
        dnp_predicted=float(np.mean(probs)),dnp_observed=float(np.mean([r['actual_dnp'] for r in rows])),
        crps=None if reference else float(np.mean([r['crps'] for r in rows])))


def comparison(evaluations):
    baseline=evaluations['baseline']
    key=lambda r:(r['event'],r['player_id'])
    keys=[key(r) for r in baseline['rows']]
    if not keys or len(keys)!=len(set(keys)):raise ValueError('Need unique, nonempty evaluation rows')
    if any([key(r) for r in e['rows']]!=keys for e in evaluations.values()):raise ValueError('Models must share evaluation rows')
    groups={key(r):r for r in baseline['minute_diagnostics']['rows']}
    def role(r):
        h=groups[key(r)]['prior']
        if h['start_frequency'] is None:return 'unknown'
        if h['start_frequency']>=.75:return 'starter'
        if h['played_frequency']<=.25:return 'reserve'
        if h['start_frequency']<=.25 and h['played_frequency']>=.5:return 'substitute'
        return 'rotation'
    variants={**evaluations,'reference':baseline}
    summary=[metrics(e['rows'],name,name=='reference') for name,e in variants.items()]
    grouped={}
    dimensions=dict(by_position=lambda r:r['position'],by_gameweek=lambda r:r['event'],by_role=role,
        by_regular_history=lambda r:'regular' if groups[key(r)]['regular'] else 'other',
        by_minute_history=lambda r:groups[key(r)]['minute_group'])
    for dim,fn in dimensions.items():
        grouped[dim]=[dict(group=g,**metrics([r for r in e['rows'] if fn(r)==g],name,name=='reference'))
            for name,e in variants.items() for g in sorted({fn(r) for r in e['rows']})]
    return dict(summary=summary,**grouped,regular_rule=baseline['minute_diagnostics']['regular_rule'])


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--snapshot',required=True,type=Path)
    parser.add_argument('--draws',type=int,default=2000)
    parser.add_argument('--seed',type=int,default=42)
    parser.add_argument('--output-root',type=Path,default=Path('artifacts/role_minutes'))
    args=parser.parse_args(argv)
    data=load_data(args.snapshot);config=BaselineConfig()
    options=EvolutionConfig(shared_goals=False,minutes_method='role_transitions_v2')
    evaluations={}
    for name,opt in [('baseline',None),('recent_role',EvolutionConfig(shared_goals=False)),('role_transitions',options)]:
        print(f'Evaluating {name} on closed GWs (development data)',flush=True)
        evaluations[name]=evaluate_sample(data,config,draws=args.draws,seed=args.seed,evolution=opt)
    tables=comparison(evaluations)
    project=Path(__file__).resolve().parents[1]
    sources=['scripts/compare_role_minutes.py','src/fpl_model/role_minutes.py','src/fpl_model/model_evolution.py',
        'src/fpl_model/simulation.py','src/fpl_model/models/baseline.py','src/fpl_model/backtest/walk_forward.py',
        'src/fpl_model/diagnostics.py','src/fpl_model/history_coverage.py','src/fpl_model/scoring.py']
    report=dict(version='role_transition_comparison_v1',kind='retrospective_development',
        metadata=dict(created_at=datetime.now(timezone.utc).isoformat(),snapshot_path=str(args.snapshot.resolve()),
            snapshot_id=data['snapshot_id'],manifest_sha256=data.get('manifest_sha256'),
            config=asdict(config),candidate_options=asdict(options),draws=args.draws,seed=args.seed,
            seed_strategy='seed + event',gameweeks=evaluations['baseline']['gameweeks'],
            code_sha256={p:hashlib.sha256((project/p).read_bytes()).hexdigest() for p in sources}),
        **tables,evaluations=evaluations,limitations=evaluations['baseline']['limitations']+[
            'These GWs have already informed development. No independent validation or significance claim.',
            'One fixed candidate, no parameter search. Transition shrinkage 3 is an untuned assumption.',
            'Roles are observational, not calibrated availability conditional on injury or a jointly legal team XI.',
            'Entire prior history defines roles; abrupt new roles and tactical changes can lag. Baseline stays default.'])
    root=_safe_root(args.output_root);root.mkdir(parents=True,exist_ok=True)
    path=root/(datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')+'_'+uuid4().hex[:8]);path.mkdir()
    with (path/'comparison.json').open('x') as f:json.dump(report,f,ensure_ascii=False,sort_keys=True,allow_nan=False,indent=2)
    print(json.dumps(dict(output=str(path),summary=report['summary']),ensure_ascii=False,indent=2))
    return 0


if __name__=='__main__':raise SystemExit(main())
