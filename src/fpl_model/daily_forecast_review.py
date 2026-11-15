"""Score saved daily transfer forecasts against outcome-only official labels."""
import json
from datetime import datetime, timezone
from pathlib import Path
import numpy as np

from fpl_model.label_contracts import utc
from fpl_model.prediction_evaluation import _metrics, _sha, select_player_outcome
from fpl_model.transfer_planner import load_cached_bundle, save_report
from fpl_model.optimizer.squad import evaluate_squad
from fpl_model.io import verify_snapshot
from fpl_model.player_fixture_labels import normalize_snapshot

DAILY_REVIEW_VERSION = 'forecast_review_v3'


def prior_reference(player_id, event, origin_at, history, coverage_state, *, fixture_count=1):
    """Prior final official matches from the forecast's original history capture."""
    if coverage_state!='complete_observed_window':
        return None
    origin=utc(origin_at)
    prior=[r for r in history if r.get('player_id')==player_id and r.get('label_state')=='final'
           and type(r.get('event')) is int and r['event']<event
           and r.get('available_at') and utc(r['available_at'])<=origin
           and r.get('kickoff_time') and utc(r['kickoff_time'])<origin]
    if not prior or len({r['fixture_id'] for r in prior})!=len(prior):
        return None
    # Same simple per-match reference as the retrospective evaluation: additive
    # means and independent nonparticipation across the GW's scheduled fixtures.
    return dict(points=float(np.mean([r['total_points'] for r in prior]))*fixture_count,
                minutes=float(np.mean([r['minutes'] for r in prior]))*fixture_count,
                p_no_play=float(np.mean([r['minutes']==0 for r in prior]))**fixture_count,n=len(prior))


def score_plan_outcome(plan,event,rows,actuals):
    """Score a fixed saved XI/bench/chip only after all 15 outcomes are known."""
    lineup=plan.get('lineups',{}).get(str(event)) or plan.get('lineups',{}).get(event)
    if not lineup or len(lineup.get('starters',[]))!=11 or len(lineup.get('bench',[]))!=4:
        return dict(status='pending',reason='incomplete_saved_lineup',missing_player_ids=[])
    required=set(lineup['starters']+lineup['bench'])
    if len(required)!=15 or not required<={r['player_id'] for r in rows}:
        return dict(status='pending',reason='invalid_saved_squad',missing_player_ids=[])
    missing=sorted(required-actuals.keys())
    if missing:
        return dict(status='pending',reason='missing_final_player_outcome',missing_player_ids=missing)
    steps=[s for s in plan.get('steps',[]) if s['event']==event]
    if plan.get('steps') and len(steps)!=1:
        raise ValueError('Saved plan has ambiguous GW step')
    summary=[s for s in plan['per_gw'] if s['event']==event]
    if len(summary)!=1:
        raise ValueError('Saved plan has ambiguous GW summary')
    hits=steps[0]['hits'] if steps else summary[0]['hits']
    chip=steps[0].get('chip') if steps else None
    points=np.array([[actuals[r['player_id']]['points'] if r['player_id'] in required else 0
                      for r in rows]],dtype=float)
    played=np.array([[actuals[r['player_id']].get('participated',actuals[r['player_id']]['minutes']>0)
                      if r['player_id'] in actuals else False
                      for r in rows]],dtype=bool)
    scored=evaluate_squad(lineup,rows,points,played,chip=chip)
    return dict(status='scored',net_points=float(scored['points'][0]-hits),
                gross_points=float(scored['points'][0]),hits=hits,chip=chip)


def _saved_cache(path,metadata):
    key=metadata.get('cache_key')
    if not key:return None,'unavailable_no_cache_key'
    cache_root=path.parents[2]/'transfer_forecasts'
    if not (cache_root/key/'bundle.json').is_file():return None,'unavailable_original_cache_missing'
    bundle=load_cached_bundle(cache_root,key)
    if bundle['metadata']!=metadata:
        raise ValueError('Saved forecast cache identity mismatch')
    return bundle,'verified_saved_scenarios'


def _point_crps(values,actual):
    values=np.asarray(values,dtype=float)
    ordered=np.sort(values);n=len(values)
    return float(np.abs(values-actual).mean()-
                 np.sum((2*np.arange(1,n+1)-n-1)*ordered)/(n*n))


def _input_sources(metadata):
    sources=metadata.get('input_sources') or {}
    if sources:
        return sources
    # Single-snapshot forecasts already record this exact source at the top
    # level. Resolve that reference; never substitute a newer local snapshot.
    if all(metadata.get(k) for k in ('snapshot_path','snapshot_id','manifest_sha256','source_available_at')):
        ref={k:metadata[k] for k in ('snapshot_path','snapshot_id','manifest_sha256')}
        ref['available_at']=metadata['source_available_at']
        return dict(history=ref,official_context=ref)
    return {}


def _verified_inputs(metadata,origin,events):
    sources=_input_sources(metadata)
    verified=[]
    for name,ref in sorted(sources.items()):
        if not isinstance(ref,dict) or not ref.get('snapshot_path'):
            continue
        path=Path(ref['snapshot_path'])
        manifest=verify_snapshot(path)
        if _sha(path/'manifest.json')!=ref.get('manifest_sha256') or manifest['run_id']!=ref.get('snapshot_id'):
            raise ValueError('Original input snapshot identity or checksum changed')
        if utc(ref['available_at'])>origin:
            raise ValueError('Forecast used source after its origin')
        observed=[utc(f.get('available_at',f['retrieved_at'])) for f in manifest['files']
                  if f['source']=='fpl_api' and f['outcome']=='success']
        if not observed or max(observed)>utc(ref['available_at']):
            raise ValueError('Source availability precedes captured raw data')
        verified.append(dict(source=name,snapshot_id=manifest['run_id'],
                             snapshot_path=str(path),manifest_sha256=ref['manifest_sha256'],
                             available_at=ref['available_at']))
    context_ref=sources.get('official_context') or {}
    if context_ref.get('snapshot_path'):
        from fpl_model.forecast_review import read_official_context
        captured=read_official_context(context_ref['snapshot_path'])
        for event in events:
            deadlines=[e['deadline_time'] for e in captured['events'] if e['id']==event]
            if len(deadlines)!=1 or utc(deadlines[0])!=utc(metadata['deadlines'][str(event)]):
                raise ValueError('Deadline disagrees with captured official context')
    return verified


def _prior_history(metadata,events,season):
    source=_input_sources(metadata).get('history') or {}
    if not source.get('snapshot_path'):
        return [],'unavailable_no_original_history'
    ids=sorted({p['player_id'] for event in events
                for p in events[event]})
    normalized=normalize_snapshot(source['snapshot_path'],season=season,
                                  element_ids=ids,allow_missing=True)
    return normalized['labels'],'verified_original_history'


def _summarize(rows):
    from fpl_model.forecast_review import REGULAR_RULE
    return dict(**_metrics(rows),rows=rows,
                by_position=[dict(position=p,**_metrics([r for r in rows if r['position']==p]))
                             for p in (1,2,3,4)],
                by_history_group=_empty_groups(rows),regular_rule=REGULAR_RULE)


def _team_comparison(report,by_event,actuals):
    packages=report['packages']
    hold=next((p for p in packages if p.get('plan_id')=='hold' or
               p.get('count')==0 and not p.get('steps')),None)
    if hold is None:
        raise ValueError('Daily report has no saved unchanged-team comparator')
    chosen=(next((p for p in packages if p.get('plan_id')==
                  (report.get('recommendation') or {}).get('plan_id')),None)
            if report.get('scope')=='transfer_sequences' else
            max(packages,key=lambda p:(p['objective'],-p['count'])))
    if chosen is None:
        raise ValueError('Daily report has no saved recommendation')
    comparisons=[]
    for event in sorted(by_event,key=int):
        e=int(event);rows=report['players_by_event'][event]
        if by_event[event]['official_context_status']=='awaiting_official_finality':
            comparisons.append(dict(event=e,status='pending',reason='awaiting_official_finality',
                                    missing_player_ids=[]));continue
        held=score_plan_outcome(hold,e,rows,actuals[e])
        selected=score_plan_outcome(chosen,e,rows,actuals[e])
        if held['status']!='scored' or selected['status']!='scored':
            comparisons.append(dict(event=e,status='pending',reason='missing_final_player_outcome',
                missing_player_ids=sorted(set(held.get('missing_player_ids',[]))|
                                          set(selected.get('missing_player_ids',[])))));continue
        saved=[r for r in chosen['per_gw'] if r['event']==e]
        comparisons.append(dict(event=e,status='scored',hold_net_points=held['net_points'],
            suggested_net_points=selected['net_points'],
            actual_gain=selected['net_points']-held['net_points'],
            predicted_gain=saved[0]['gain'] if saved else None,
            hold_hits=held['hits'],suggested_hits=selected['hits']))
    complete=all(r['status']=='scored' for r in comparisons)
    return dict(plan_id=chosen.get('plan_id'),hold_plan_id=hold.get('plan_id','hold'),
                status='scored' if complete else 'partially_scored' if any(r['status']=='scored' for r in comparisons) else 'pending',
                per_gw=comparisons,
                horizon_actual_gain=sum(r['actual_gain'] for r in comparisons) if complete else None,
                interpretation='Fixed saved hypothetical plans, not actual manager transfers or a new optimisation.')


def _empty_groups(rows):
    return {group: _metrics([r for r in rows if r.get('history_group')==group])
            for group in ('regular','other','unresolved')}


def review_daily_forecast(path, observations, output_root, *, season='2026-2027',
                          context=None, outcome_source=None):
    """A later final target is permitted; no forecast is simulated or rebuilt."""
    path=Path(path).resolve()
    report=json.loads(path.read_bytes())
    if report.get('scope') not in ('transfer_sequences','transfers_now_then_hold'):
        raise ValueError('Unsupported daily transfer report')
    recorded_season=(report.get('profile') or {}).get('season')
    if recorded_season is not None and recorded_season!=season:
        raise ValueError('Outcome season differs from forecast season')
    metadata=report['forecast']
    origin=utc(metadata['forecast_origin_at'])
    if utc(metadata['source_available_at'])>origin:
        raise ValueError('Forecast used a source after its origin')
    events=sorted(int(e) for e in report['players_by_event'])
    if not events or any(str(event) not in metadata['deadlines'] for event in events):
        raise ValueError('Missing official deadline in daily report')
    verified=_verified_inputs(metadata,origin,events)
    if any(origin>=utc(metadata['deadlines'][str(event)]) for event in events):
        provenance='not_pre_deadline'
    elif not origin<=utc(report['created_at'])<utc(metadata['deadlines'][str(events[0])]):
        provenance='not_pre_deadline'
    elif {'history','official_context'}<={r['source'] for r in verified}:
        provenance='locally_recorded_pre_deadline'
    elif verified:
        provenance='partially_verified_pre_deadline'
    else:
        provenance='unverified_provenance'
    bundle,cache_status=_saved_cache(path,metadata)
    if bundle and bundle.get('season',season)!=season:
        raise ValueError('Outcome season differs from forecast cache season')
    prior_history,prior_status=_prior_history(metadata,
        {e:report['players_by_event'][str(e)] for e in events},season)
    order=({p['id']:i for i,p in enumerate(sorted(bundle['players'],key=lambda p:p['id']))}
           if bundle else {})
    if bundle and set(bundle['events'])!=set(events):
        raise ValueError('Saved forecast cache GW identity mismatch')
    by_event={};all_final=[];all_pending=[];shared_model=[];shared_reference=[];actuals={}
    for event in events:
        rows=[];pending=[];shared=[];references=[];reference_missing=[];actuals[event]={}
        player_rows=report['players_by_event'][str(event)]
        if len({p['player_id'] for p in player_rows})!=len(player_rows):
            raise ValueError('Duplicate saved player identity')
        if bundle and {p['player_id'] for p in player_rows}!=set(order):
            raise ValueError('Saved forecast cache player identity mismatch')
        if bundle and ({p['player_id']:p for p in player_rows}!=
                       {p['player_id']:p for p in bundle['rows'][event]}):
            raise ValueError('Saved report player summaries differ from original cache')
        context_status='unverified_context'
        if context is not None:
            from fpl_model.forecast_review import event_readiness
            context_status=event_readiness(context,event)['status']
        for player in player_rows:
            p=dict(player_id=player['player_id'],position=player['position'],
                   fixture_ids=player['fixture_ids'])
            if context_status=='awaiting_official_finality':
                pending.append(dict(**p,event=event,reason='awaiting_official_finality'));continue
            if context_status=='context_final_labels_still_required' and type(player.get('team_id')) is int:
                schedule=[f for f in context['fixtures'] if f.get('event')==event]
                known_sides=all(type(f.get(k)) is int for f in schedule for k in ('team_h','team_a'))
                current={f['id'] for f in schedule if player['team_id'] in (f.get('team_h'),f.get('team_a'))}
                if known_sides and current!=set(p['fixture_ids']):
                    pending.append(dict(**p,event=event,reason='fixture_universe_changed'));continue
                if known_sides and not current and not p['fixture_ids']:
                    actuals[event][p['player_id']]=dict(points=0,minutes=0,participated=False)
                    continue
            targets,reason=select_player_outcome(dict(season=season,event=event),p,observations)
            if reason:
                pending.append(dict(**p,event=event,reason=reason));continue
            minutes=sum(t['minutes'] for t in targets)
            actual=sum(t['total_points'] for t in targets)
            participated=any(t['minutes']>0 or (t.get('yellow_cards') or 0)>0
                             or (t.get('red_cards') or 0)>0 for t in targets)
            actuals[event][p['player_id']]=dict(points=actual,minutes=minutes,participated=participated)
            crps=(_point_crps(bundle['scenarios'][event]['points'][:,order[p['player_id']]],actual)
                  if bundle else None)
            explanation=(bundle['explanations'][event].get(str(p['player_id']),{}) if bundle else {})
            from fpl_model.forecast_review import history_group
            classified=history_group(explanation,event)
            model_row=dict(**p,event=event,actual=actual,
                predicted=player['xp'],actual_minutes=minutes,
                predicted_minutes=player['expected_minutes'],actual_dnp=int(minutes==0),
                p_no_play=player['p_no_play'],p10=player['p10'],p90=player['p90'],
                crps=crps,history_group=classified,
                target_observation_ids=[t['observation_id'] for t in targets],
                target_available_at=max(utc(t['available_at']) for t in targets).isoformat())
            rows.append(model_row)
            reference=prior_reference(p['player_id'],event,origin,prior_history,
                                       explanation.get('history_coverage'),fixture_count=len(p['fixture_ids']))
            if reference is None:
                reference_missing.append(dict(player_id=p['player_id'],reason='no_verified_prior_reference'))
                continue
            shared.append(model_row)
            references.append(dict(model_row,predicted=reference['points'],
                predicted_minutes=reference['minutes'],p_no_play=reference['p_no_play'],
                p10=None,p90=None,crps=None,prior_matches=reference['n']))
        model_all=_summarize(rows)
        by_event[str(event)]=dict(model_all=model_all,model=_summarize(shared),
                                  reference=_summarize(references),pending=pending,
                                  reference_missing=reference_missing,
                                  official_context_status=context_status)
        all_final.extend(rows);all_pending.extend(pending)
        shared_model.extend(shared);shared_reference.extend(references)
    team=_team_comparison(report,by_event,actuals)
    result=dict(version=DAILY_REVIEW_VERSION,format='daily_transfer',
        created_at=datetime.now(timezone.utc).isoformat(),forecast_path=str(path),forecast_sha256=_sha(path),
        forecast_origin_at=origin.isoformat(),deadline_at=metadata['deadlines'][str(events[0])],
        event=events[0],season=season,model_version=metadata['model_version'],
        report_created_at=report['created_at'],
        forecast_metadata=metadata,provenance_status=provenance,
        verified_input_sources=verified,outcome_source=outcome_source,
        outcome_context_source=context.get('source') if context else None,
        events=by_event,variants={'model':_summarize(shared_model),
                                  'reference':_summarize(shared_reference)},
        cache_status=cache_status,prior_reference_status=prior_status,
        team_comparison=team,
        same_player_ids=sorted({r['player_id'] for r in shared_model}),
        all_final_count=len(all_final),pending=all_pending,
        limitations=['No forecast was recomputed. Missing final labels are never DNP.',
                     'Local timestamps and hashes are recorded evidence, not external clock attestation.',
                     'Comparative metrics use only rows with a verified prior reference from the original history snapshot.',
                     'Reference means scale with fixture count; GW zero-minute probability assumes independent matches.',
                     'Zero-minute diagnostics are distinct from FPL card-only participation for autosubs and captaincy.',
                     'CRPS requires the original saved scenario cache.',
                     'A fixed saved transfer plan is hypothetical; it is not the manager’s realized team.'])
    return save_report(result,output_root),result
