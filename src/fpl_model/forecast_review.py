"""Outcome-only review of saved predictions. Never simulates or rebuilds inputs."""
from collections import Counter
from datetime import datetime, timezone
import json
import math
from pathlib import Path

from fpl_model.diagnostics import REGULAR_RULE
from fpl_model.io import verify_snapshot
from fpl_model.label_contracts import utc
from fpl_model.prediction_evaluation import (
    _metrics, _sha, evaluate_predictions, load_forecasts, select_player_outcome,
)
from fpl_model.transfer_planner import save_report


def read_official_context(path):
    root=Path(path).resolve();manifest=verify_snapshot(root)
    files=[];payloads={}
    for name in ('bootstrap_static.json','fixtures.json'):
        entries=[f for f in manifest['files'] if f['source']=='fpl_api'
                 and f['outcome']=='success' and f['relative_path'].endswith('/'+name)]
        if len(entries)!=1:raise ValueError('Missing or ambiguous official context: '+name)
        files.extend(entries);payloads[name]=json.loads((root/entries[0]['relative_path']).read_bytes())
    return dict(events=payloads['bootstrap_static.json']['events'],fixtures=payloads['fixtures.json'],
        source=dict(snapshot_id=manifest['run_id'],snapshot_path=str(root),manifest_sha256=_sha(root/'manifest.json'),
            available_at=max(utc(f.get('available_at',f['retrieved_at'])) for f in files).isoformat(),files=files))


def event_readiness(context,event):
    """Elapsed kickoff is not evidence that official player outcomes are final."""
    events=[e for e in context['events'] if e['id']==event]
    fixtures=sorted((f for f in context['fixtures'] if f.get('event')==event),key=lambda f:f['id'])
    e=events[0] if len(events)==1 else {}
    final=[f for f in fixtures if f.get('finished') is True]
    ready=bool(e.get('finished') is True and e.get('data_checked') is True and len(final)==len(fixtures))
    return dict(event=event,status='context_final_labels_still_required' if ready else 'awaiting_official_finality',
        event_finished=e.get('finished'),event_data_checked=e.get('data_checked'),fixtures=len(fixtures),
        finished=len(final),provisionally_finished=sum(f.get('finished_provisional') is True for f in fixtures),
        remaining_fixture_ids=[f['id'] for f in fixtures if not f.get('finished')],
        remaining=[dict(fixture_id=f['id'],kickoff_at=f.get('kickoff_time'),
                        finished_provisional=f.get('finished_provisional',False)) for f in fixtures if not f.get('finished')],
        context_source=context.get('source'))


def history_group(explanation,event):
    """Use only the forecast's stored history; never classify using the target."""
    h=explanation.get('captured_history',{})
    if (explanation.get('history_coverage')!='complete_observed_window'
        or any(e>=event for e in h.get('events',[]))
        or any(h.get(k) is None for k in ('matches','mean_minutes','played_frequency'))):return 'unresolved'
    return 'regular' if h['matches']>=2 and h['mean_minutes']>=60 and h['played_frequency']>=.75 else 'other'


def _add_groups(result,explanations,event):
    for r in result['rows']:r['history_group']=history_group(explanations.get(str(r['player_id']),{}),event)
    result['by_history_group']={group:_metrics([r for r in result['rows'] if r['history_group']==group])
                                for group in ('regular','other','unresolved')}
    result['pending_reasons']=dict(sorted(Counter(p['reason'] for p in result['pending']).items()))
    return result


def _legacy_variants(report):
    if report.get('kind')!='current_forecast_comparison':
        raise ValueError('Synthetic or unsupported report; only real forecast comparisons may be scored')
    variants={name:report[name] for name in ('baseline','odds_variant','defensive_reference') if name in report}
    if 'baseline' not in variants or 'odds_variant' not in variants:raise ValueError('Missing comparison variant')
    baseline=variants['baseline'];identities=None
    for v in variants.values():
        if any(v.get(k)!=baseline.get(k) for k in ('event','config','seed','draws','as_of_at')):
            raise ValueError('Variants must share configuration, seed, draws, event and origin')
        if v['event']!=report['event'] or utc(v['as_of_at'])!=utc(report['forecast_origin_at']):
            raise ValueError('Inconsistent forecast origin/event')
        players=v['players'];ids=[p['player_id'] for p in players]
        if not ids or len(set(ids))!=len(ids) or any(type(i)!=int or i<1 for i in ids):raise ValueError('Invalid player universe')
        identity={}
        for p in players:
            if p['position'] not in (1,2,3,4):raise ValueError('Invalid position')
            values=[p[k] for k in ('xp','expected_minutes','p_no_play','p10','p90')]
            if not all(isinstance(v,(int,float)) and math.isfinite(v) for v in values):raise ValueError('Invalid forecast values')
            if not 0<=p['p_no_play']<=1 or p['expected_minutes']<0 or p['p10']>p['p90']:raise ValueError('Invalid forecast summary')
            e=v['player_explanations'][str(p['player_id'])];fids=[f['fixture_id'] for f in e['fixtures']]
            if len(fids)!=len(set(fids)) or any(type(f)!=int or f<1 for f in fids):raise ValueError('Invalid fixture universe')
            identity[p['player_id']]=(p['position'],tuple(sorted(fids)),e.get('captured_history'),e.get('history_coverage'))
        if identities is not None and identity!=identities:raise ValueError('Variants must share player, fixture and prior-history universe')
        identities=identity
    return variants


def _legacy_provenance(report,variants):
    origin=utc(report['forecast_origin_at']);deadline=utc(report['deadline_at'])
    created=[utc(v['created_at']) for v in variants.values()]
    if origin>=deadline or any(t>=deadline or t<origin for t in created):return 'not_pre_deadline',[]
    sources=report.get('input_sources',{})
    refs=[sources.get('history'),sources.get('official_context'),(report.get('coverage') or {}).get('source')]
    if not all(ref and ref.get('snapshot_path') and ref.get('manifest_sha256') for ref in refs):
        return 'unverified_provenance',[]
    verified=[]
    for ref in refs:
        path=Path(ref['snapshot_path']);manifest=verify_snapshot(path)
        if _sha(path/'manifest.json')!=ref['manifest_sha256']:raise ValueError('Source manifest checksum changed')
        available=max(utc(f.get('available_at',f['retrieved_at'])) for f in manifest['files'] if f['outcome']=='success')
        if available>origin:raise ValueError('Forecast used source captured after its origin')
        verified.append(dict(snapshot_id=manifest['run_id'],snapshot_path=str(path),manifest_sha256=ref['manifest_sha256'],available_at=available.isoformat()))
    context=read_official_context(sources['official_context']['snapshot_path'])
    deadlines=[e['deadline_time'] for e in context['events'] if e['id']==report['event']]
    if len(deadlines)!=1 or utc(deadlines[0])!=deadline:raise ValueError('Deadline disagrees with captured official context')
    # Legacy JSON was not accompanied by an immutable integrity record at creation.
    return 'legacy_declared_pre_deadline',verified


def _evaluate_summary(report,variant,observations,season):
    rows=[];pending=[];event=report['event']
    for p in sorted(variant['players'],key=lambda p:p['player_id']):
        e=variant['player_explanations'][str(p['player_id'])]
        player=dict(player_id=p['player_id'],position=p['position'],fixture_ids=sorted(f['fixture_id'] for f in e['fixtures']))
        targets,reason=select_player_outcome(dict(season=season,event=event),player,observations)
        if reason:
            pending.append(dict(**player,reason=reason));continue
        actual_minutes=sum(t['minutes'] for t in targets)
        rows.append(dict(**player,event=event,actual=sum(t['total_points'] for t in targets),predicted=p['xp'],
            actual_minutes=actual_minutes,predicted_minutes=p['expected_minutes'],actual_dnp=int(actual_minutes==0),
            p_no_play=p['p_no_play'],p10=p['p10'],p90=p['p90'],crps=None,
            target_observation_ids=[t['observation_id'] for t in targets],
            target_available_at=max(utc(t['available_at']) for t in targets).isoformat()))
    return dict(**_metrics(rows),model_version=variant['model_version'],event=event,rows=rows,pending=pending,
        status='awaiting_final_outcomes' if not rows else 'partially_scored' if pending else 'scored',
        crps_status='unavailable_no_saved_scenarios',
        by_position=[dict(position=pos,**_metrics([r for r in rows if r['position']==pos])) for pos in (1,2,3,4)])


def review_forecast(path,observations,output_root,*,season='2026-2027',context=None,outcome_source=None):
    path=Path(path).resolve();now=datetime.now(timezone.utc).isoformat()
    if path.is_dir() or path.name=='forecast.json':
        root=path if path.is_dir() else path.parent;report,arrays=load_forecasts(root)
        if report['season']!=season:raise ValueError('Outcome season differs from forecast season')
        variants={name:_add_groups(evaluate_predictions(report,arrays[name+'_points'],arrays[name+'_minutes'],observations,model_version=name),
                                   v['explanations'],report['event']) for name,v in report['variants'].items()}
        path=root/'forecast.json';format_='saved_scenarios';status=report['provenance_status']
        refs=report.get('verified_raw_references',[])
    else:
        report=json.loads(path.read_bytes());loaded=_legacy_variants(report)
        status,refs=_legacy_provenance(report,loaded);format_='legacy_summary'
        variants={name:_add_groups(_evaluate_summary(report,v,observations,season),v['player_explanations'],report['event']) for name,v in loaded.items()}
    sets=[sorted(r['player_id'] for r in v['rows']) for v in variants.values()]
    if not sets or any(s!=sets[0] for s in sets):raise ValueError('Evaluation rows differ across variants')
    result=dict(version='forecast_review_v1',format=format_,created_at=now,forecast_path=str(path),forecast_sha256=_sha(path),
        event=report['event'],season=season,forecast_origin_at=report['forecast_origin_at'],deadline_at=report['deadline_at'],
        provenance_status=status,verified_input_sources=refs,outcome_source=outcome_source,
        outcome_context=event_readiness(context,report['event']) if context else None,
        same_player_ids=sets[0],variants=variants,regular_rule=REGULAR_RULE,
        limitations=['Only saved predictions are scored. No model refit or forecast recomputation.',
            'Missing, provisional, conflicting and changed-fixture outcomes are excluded, never DNP.',
            'Legacy summary CRPS cannot be recovered from a mean and quantiles.',
            'Legacy timestamps are declarations; source verification cannot prove when the prediction file was created.',
            'No external clock attestation. One GW or partial outcomes cannot establish a reliable improvement.'])
    return save_report(result,output_root),result


def reviewable_forecasts(root):
    """Exclude synthetic examples; do not rank runs by performance."""
    paths=list((Path(root)/'artifacts/defensive_odds').glob('*/comparison.json'))
    paths+=list((Path(root)/'artifacts/model_forecasts').glob('*/forecast.json'))
    result=[]
    for p in sorted(paths,reverse=True):
        if p.parent.name.startswith('.'):continue
        try:r=json.loads(p.read_bytes())
        except (OSError,ValueError):continue
        if r.get('kind')=='current_forecast_comparison' or r.get('version')=='saved_predictions_v1':
            result.append(dict(path=p,event=r['event'],origin=r['forecast_origin_at'],deadline_at=r['deadline_at'],
                               format='saved_scenarios' if p.name=='forecast.json' else 'legacy_summary'))
    return sorted(result,key=lambda r:(r['event'],r['origin'],str(r['path'])))
