"""Immutable scenario records and outcome-only scoring. Never rewrites inputs."""
from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from uuid import uuid4
import numpy as np
from fpl_model.label_contracts import utc
from fpl_model.observation_selection import select_outcome


def _dump(value):return json.dumps(value,sort_keys=True,ensure_ascii=False,allow_nan=False,indent=2)+'\n'
def _sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def save_forecasts(data,event,simulations,config,evolution,coverage,root,*,set_piece_config=None,bonus_config=None,season_prior_config=None,assist_config=None):
    from fpl_model.transfer_planner import _safe_root
    from fpl_model.io import verify_snapshot
    now=datetime.now(timezone.utc);origin=utc(data['as_of_at'])
    deadline=utc(next(e['deadline_time'] for e in data['events'] if e['id']==event))
    sources=data.get('input_sources') or dict(history={k:data.get(k) for k in ('snapshot_id','snapshot_path','manifest_sha256')})
    references=[]
    for source in (sources.get('history'),sources.get('official_context'),sources.get('set_piece_roles'),coverage.get('source') if coverage else None):
        if not source:continue
        if source.get('snapshot_path'):
            path=Path(source['snapshot_path']);manifest=verify_snapshot(path)
            if source.get('manifest_sha256')!=_sha(path/'manifest.json'):raise ValueError('Source manifest checksum changed')
            files=[f for f in manifest['files'] if f['outcome']=='success']
            # References retain original available_at; nothing is backdated to the origin.
            if any(utc(f.get('available_at',f['retrieved_at']))>origin for f in files):raise ValueError('Source after forecast origin')
            references.append(dict(snapshot_path=str(path),snapshot_id=manifest['run_id'],manifest_sha256=source['manifest_sha256'],files=files))
    status='recorded_pre_deadline' if origin<=now<deadline and references else 'not_pre_deadline' if now>=deadline else 'unverified_provenance'
    root=_safe_root(root);root.mkdir(parents=True,exist_ok=True)
    name=now.strftime('%Y%m%dT%H%M%S%fZ')+'_'+uuid4().hex[:8]
    stage=root/('.building_'+name);stage.mkdir(exist_ok=False)
    first=next(iter(simulations.values()));ids=[p['id'] for p in first.players]
    arrays={};variants={}
    for name_,sim in simulations.items():
        if not name_.replace('_','').isalnum():raise ValueError('Invalid variant name')
        if [p['id'] for p in sim.players]!=ids or sim.event!=event:raise ValueError('Variants must share identities and GW')
        arrays[name_+'_points']=sim.points;arrays[name_+'_minutes']=sim.minutes
        variants[name_]=dict(seed=sim.seed,draws=len(sim.points),players=sim.summary(),explanations=sim.explanations,
            match_audit=[dict(fixture_id=f['fixture_id'],teams=[dict(team_id=t['team_id'],
                mean_goals=float(t['goals'].mean()),mean_credited_goals=float(t['credited_goals'].mean()),
                mean_unattributed_goals=float(t['unattributed_goals'].mean()),mean_assists=float(t['credited_assists'].mean())) for t in f['teams']]) for f in sim.match_audit])
        if sim.assist_model is not None:variants[name_]['assist_model']=sim.assist_model
        if sim.bonus_model is not None:variants[name_]['bonus_model']=sim.bonus_model
    np.savez_compressed(stage/'scenarios.npz',**arrays)
    code_root=Path(__file__).parent
    report=dict(version='saved_predictions_v1',season=data.get('season','2026-2027'),event=event,
        forecast_origin_at=origin.isoformat(),created_at=now.isoformat(),deadline_at=deadline.isoformat(),
        provenance_status=status,input_sources=sources,verified_raw_references=references,
        config=asdict(config),evolution=asdict(evolution) if evolution else None,coverage=coverage,
        players=[dict(player_id=p['id'],position=p['element_type'],fixture_ids=sorted(f['id'] for f in data['fixtures'] if f.get('event')==event and p['team'] in (f['team_h'],f['team_a']))) for p in first.players],
        variants=variants,scenarios_sha256=_sha(stage/'scenarios.npz'),
        code_sha256={f:_sha(code_root/f) for f in ('simulation.py','model_evolution.py','role_minutes.py','set_piece_roles.py','conditional_bonus.py','season_priors.py','assist_correction.py','attacking_odds.py','models/baseline.py','scoring.py','prediction_evaluation.py')},
        limitations=['No external clock attestation; timestamps and hashes are local records.',
            'Shared goals still use independent player minutes, not a legal team XI. Bonus remains marginal, not BPS ranking.',
            'Own goals omitted only in shared-goal variant. Event-type penalty/set-piece decomposition is unavailable.',
            'News probabilities and manual return restrictions are assumptions, not calibrated diagnoses.'])
    if set_piece_config is not None:
        report['set_piece_config']=asdict(set_piece_config)
        report['limitations'].append('Set-piece variant only reallocates existing goal/assist budgets under explicit assumptions. No measured non-penalty xG decomposition; no performance claim.')
    if bonus_config is not None:
        report['bonus_config']=asdict(bonus_config)
        report['limitations'].append('Conditional bonus uses simulated events and earlier final labels. No joint BPS ranking or fixed match bonus budget; experimental, not calibrated.')
    if season_prior_config is not None:
        report['season_prior_config']=asdict(season_prior_config)
        report['limitations'].append('Previous-season xG/xA only; old team/role/position may differ. No transfer or ageing adjustment; experimental, baseline remains default.')
    if assist_config is not None:
        report['assist_config']=asdict(assist_config)
        report['limitations'].append('Pooled FPL-assist/xA ratio mixes rules, finishing and sampling. No event-level assist rules or shot/rebound redistribution; isolated experimental correction.')
    (stage/'forecast.json').write_text(_dump(report))
    (stage/'integrity.json').write_text(_dump(dict(forecast_sha256=_sha(stage/'forecast.json'))))
    path=root/name;stage.rename(path)
    return path


def load_forecasts(path):
    path=Path(path);integrity=json.loads((path/'integrity.json').read_text())
    if integrity['forecast_sha256']!=_sha(path/'forecast.json'):raise ValueError('Forecast checksum mismatch')
    report=json.loads((path/'forecast.json').read_text())
    if report['scenarios_sha256']!=_sha(path/'scenarios.npz'):raise ValueError('Scenario checksum mismatch')
    with np.load(path/'scenarios.npz',allow_pickle=False) as arrays:return report,{k:arrays[k] for k in arrays.files}


def _metrics(rows):
    if not rows:return dict(n=0,points=None,minutes=None,dnp=None,interval_80=None)
    def errors(field,pred):
        x=np.array([r[pred]-r[field] for r in rows]);return dict(bias=float(x.mean()),mae=float(abs(x).mean()),rmse=float(np.sqrt(np.mean(x*x))))
    return dict(n=len(rows),points=dict(**errors('actual','predicted'),crps=float(np.mean([r['crps'] for r in rows])) if all(r.get('crps') is not None for r in rows) else None),
        minutes=errors('actual_minutes','predicted_minutes'),
        dnp=dict(brier=float(np.mean([(r['p_no_play']-r['actual_dnp'])**2 for r in rows])),
                 predicted=float(np.mean([r['p_no_play'] for r in rows])),observed=float(np.mean([r['actual_dnp'] for r in rows]))),
        interval_80=dict(n=len(rows),coverage=float(np.mean([r['p10']<=r['actual']<=r['p90'] for r in rows]))))


def select_player_outcome(report,p,observations):
    """Share finality, conflict and changed-fixture rules for stored forecast formats."""
    targets=[];reason=None
    observed_fixtures={o['fixture_id'] for o in observations if o.get('season')==report['season'] and o.get('player_id')==p['player_id'] and o.get('event')==report['event']}
    if observed_fixtures-set(p['fixture_ids']):reason='fixture_universe_changed'
    if not p['fixture_ids']:reason='blank_at_forecast_not_scored'
    for fid in ([] if reason else p['fixture_ids']):
        selected=select_outcome(observations,season=report['season'],player_id=p['player_id'],fixture_id=fid)
        if selected.status!='selected':reason=selected.status;break
        if selected.observation['event']!=report['event']:reason='fixture_moved_event';break
        targets.append(selected.observation)
    return targets,reason


def evaluate_predictions(report,points,minutes,observations,*,model_version):
    """Final outcome availability may exceed origin. No feature recomputation."""
    points=np.asarray(points);minutes=np.asarray(minutes)
    if points.ndim!=2 or minutes.shape!=points.shape or points.shape[1]!=len(report['players']):raise ValueError('Wrong forecast shape')
    if not np.isfinite(points).all() or not np.isfinite(minutes).all():raise ValueError('Nonfinite scenarios')
    rows=[];pending=[]
    for i,p in enumerate(report['players']):
        targets,reason=select_player_outcome(report,p,observations)
        if reason:
            pending.append(dict(player_id=p['player_id'],fixture_ids=p['fixture_ids'],reason=reason));continue
        actual=sum(t['total_points'] for t in targets);actual_minutes=sum(t['minutes'] for t in targets)
        x=points[:,i].astype(float);ordered=np.sort(x);n=len(x)
        crps=float(np.abs(x-actual).mean()-np.sum((2*np.arange(1,n+1)-n-1)*ordered)/(n*n))
        q=np.quantile(x,[.1,.9])
        rows.append(dict(player_id=p['player_id'],position=p['position'],event=report['event'],fixture_ids=p['fixture_ids'],
            actual=actual,predicted=float(x.mean()),actual_minutes=actual_minutes,predicted_minutes=float(minutes[:,i].mean()),
            p_no_play=float((minutes[:,i]==0).mean()),actual_dnp=int(actual_minutes==0),crps=crps,p10=float(q[0]),p90=float(q[1]),
            target_observation_ids=[t['observation_id'] for t in targets],target_available_at=max(t['available_at'] for t in targets)))
    bins=[]
    for k in range(10):
        subset=[r for r in rows if min(9,int(r['p_no_play']*10))==k]
        bins.append(dict(lower=k/10,upper=(k+1)/10,n=len(subset),
            predicted=float(np.mean([r['p_no_play'] for r in subset])) if subset else None,
            observed=float(np.mean([r['actual_dnp'] for r in subset])) if subset else None))
    return dict(**_metrics(rows),model_version=model_version,event=report['event'],
        status='awaiting_final_outcomes' if not rows else 'partially_scored' if pending else 'scored',
        provenance_status=report['provenance_status'],rows=rows,pending=pending,dnp_calibration=bins,
        by_position=[dict(position=pos,**_metrics([r for r in rows if r['position']==pos])) for pos in sorted({r['position'] for r in rows})])


def evaluate_saved(path,observations,output_root):
    from fpl_model.transfer_planner import save_report
    report,arrays=load_forecasts(path)
    result=dict(kind='saved_forecast_outcomes',forecast_path=str(Path(path).resolve()),
        forecast_sha256=_sha(Path(path)/'forecast.json'),event=report['event'],
        forecast_origin_at=report['forecast_origin_at'],provenance_status=report['provenance_status'],
        variants={name:evaluate_predictions(report,arrays[name+'_points'],arrays[name+'_minutes'],observations,model_version=name) for name in report['variants']})
    return save_report(result,output_root),result
