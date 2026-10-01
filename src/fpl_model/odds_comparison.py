"""Offline current-forecast comparison from immutable official/odds captures."""
import hashlib
import json
from pathlib import Path
from datetime import datetime, timezone
from uuid import uuid4
from zoneinfo import ZoneInfo
from fpl_model.io import verify_snapshot
from fpl_model.label_contracts import utc
from fpl_model.prototype_data import load_data
from fpl_model.prototype import run_prototype
from fpl_model.defensive_odds import read_csv, build_coverage, COLUMNS, PROB_KEYS, goal_probabilities


def _ref(root,manifest):
    return dict(snapshot_path=str(root),snapshot_id=manifest['run_id'],
        manifest_sha256=hashlib.sha256((root/'manifest.json').read_bytes()).hexdigest())


def load_inputs(history_snapshot,context_snapshot,forecast_origin_at):
    """Keep captured player histories/prices/status; refresh only fixtures/deadlines/teams.

    as_of_at is the information cutoff, never a rewritten source retrieval time.
    All original source times/paths remain under input_sources.
    """
    d=load_data(history_snapshot);origin=utc(forecast_origin_at)
    root=Path(context_snapshot).resolve();manifest=verify_snapshot(root)
    entries=[f for f in manifest['files'] if f['source']=='fpl_api' and f['outcome']=='success']
    def read(name):
        found=[f for f in entries if f['relative_path'].endswith('/'+name)]
        if len(found)!=1:raise ValueError('Missing/ambiguous official context')
        return json.loads((root/found[0]['relative_path']).read_bytes())
    bootstrap=read('bootstrap_static.json');fixtures=read('fixtures.json')
    if utc(d['as_of_at'])>origin or any(utc(f.get('available_at',f['retrieved_at']))>origin for f in entries):
        raise ValueError('Official context/history captured after forecast origin')
    old={t['id']:t['name'] for t in d['teams']};new={t['id']:t['name'] for t in bootstrap['teams']}
    if old!=new:raise ValueError('Official team identities changed; explicit review needed')
    current={p['id']:p for p in bootstrap['elements']}
    if any(p['id'] not in current or p['team']!=current[p['id']]['team'] for p in d['players']):
        raise ValueError('Player/team membership changed; cannot reuse stale identities safely')
    old_events={e['id']:e for e in d['events']}
    revisions=[dict(event=e['id'],old_deadline=old_events[e['id']]['deadline_time'],new_deadline=e['deadline_time'])
               for e in bootstrap['events'] if e['id'] in old_events and old_events[e['id']]['deadline_time']!=e['deadline_time']]
    d['input_sources']=dict(history=dict(snapshot_id=d['snapshot_id'],snapshot_path=d['snapshot_path'],
        manifest_sha256=d['manifest_sha256'],available_at=d['as_of_at']),
        official_context=dict(**_ref(root,manifest),files=entries),deadline_revisions=revisions,
        player_metadata_note='Player histories, prices and injury/status fields are reused at their original capture time; not refreshed.')
    d.update(fixtures=fixtures,events=bootstrap['events'],teams=bootstrap['teams'],as_of_at=origin.isoformat())
    return d


def load_odds(snapshot):
    root=Path(snapshot).resolve();manifest=verify_snapshot(root)
    failures=[f for f in manifest['failures'] if f['source']=='football_data_uk']
    bad_paths={f.get('relative_path') for f in failures}
    entries=[f for f in manifest['files'] if f['source']=='football_data_uk' and f['outcome']=='success'
             and f['relative_path'] not in bad_paths]
    reference=_ref(root,manifest)
    if len(entries)!=1:
        return [],dict(**reference,source='football_data_uk',source_published_at=None,
                       failure='no_unique_valid_odds_response',failures=failures)
    entry=entries[0]
    return read_csv((root/entry['relative_path']).read_bytes()),{**reference,**entry,
        'raw_path':entry['relative_path'],'available_at':entry.get('available_at',entry['retrieved_at']),'source_published_at':None}


def compare_forecasts(data,coverage,config,*,draws=3000,seed=42,budget=100,kind='current_forecast_comparison'):
    if config.frequency_prior_games!=1 or config.minutes_prior_games!=1:
        raise ValueError('This bounded odds comparison retains both minutes priors at 1.0')
    event=coverage['event']
    baseline,base_sim,_=run_prototype(data,event,config,draws=draws,seed=seed,budget=budget,evaluate_history=False)
    variant,odds_sim,_=run_prototype(data,event,config,draws=draws,seed=seed,budget=budget,
                                    defensive_odds=coverage,evaluate_history=False)
    defensive_components=('clean_sheets','goals_conceded','saves','defensive_contribution','penalties_saved')
    changes=[]
    for before,after in zip(baseline['players'],variant['players']):
        pid=before['player_id']
        base_def=sum(base_sim.explanations[pid]['point_components'][k] for k in defensive_components)
        odds_def=sum(odds_sim.explanations[pid]['point_components'][k] for k in defensive_components)
        changes.append(dict(player_id=pid,name=before['name'],position=before['position'],team_id=before['team_id'],
            baseline_defensive_points=base_def,odds_defensive_points=odds_def,defensive_points_delta=odds_def-base_def,
            baseline_xp=before['xp'],odds_xp=after['xp'],xp_delta=after['xp']-before['xp'],
            minutes_delta=after['expected_minutes']-before['expected_minutes']))
    bt,ot=baseline['team'],variant['team']
    return dict(kind=kind,default_model_changed=False,event=event,forecast_origin_at=data['as_of_at'],
        deadline_at=coverage['deadline_at'],source_history_snapshot_id=data['snapshot_id'],
        input_sources=data.get('input_sources'),coverage=coverage,baseline=baseline,odds_variant=variant,
        defensive_point_components=list(defensive_components),player_changes=changes,team_changes=dict(added=sorted(set(ot['squad'])-set(bt['squad'])),
            removed=sorted(set(bt['squad'])-set(ot['squad'])),baseline_starters=bt['starters'],odds_starters=ot['starters'],
            baseline_captain=bt['captain'],odds_captain=ot['captain']),
        scope='Only clean sheets and conceded-goal point deductions use odds. Minutes, attacks, saves, bonus and all other components unchanged.',
        limitations=['Forecast comparison, not evidence of which variant is better; no historical evaluation with these odds.',
            'Independent Poisson goal rates/clean sheets are model-derived; bookmaker probabilities need not be exactly Poisson-consistent.',
            'Separate defensive random stream; individual defensive deltas include Monte Carlo noise.',
            'No publication timestamp or price age supplied by provider. available_at = retrieved_at.',
            'Player metadata/history is reused, with its original timestamps; missing markets explicitly use baseline.'])


def synthetic_demo(data,event,config,*,draws=3000,seed=42,budget=100):
    """One deliberately invented market on one official fixture; NOT a live quote."""
    fixture=min((f for f in data['fixtures'] if f.get('event')==event and f.get('kickoff_time')),key=lambda f:f['id'])
    teams={t['id']:t['name'] for t in data['teams']}
    when=utc(fixture['kickoff_time']).astimezone(ZoneInfo('Europe/London'))
    probabilities=goal_probabilities(1.8,.7)
    row=dict(Div='E0',Date=when.strftime('%d/%m/%Y'),Time=when.strftime('%H:%M'),
        HomeTeam=teams[fixture['team_h']],AwayTeam=teams[fixture['team_a']],
        **dict(zip(COLUMNS,[str(1/(probabilities[k]*1.04)) for k in PROB_KEYS])))
    source=dict(source='synthetic_offline_example',synthetic=True,available_at=data['as_of_at'],retrieved_at=data['as_of_at'],
        source_published_at=None,description='Invented rates 1.8/0.7, converted to prices with 4% overround; not provider data',rows=[row])
    coverage=build_coverage(data,[row],source,event,config,data['as_of_at'])
    return compare_forecasts(data,coverage,config,draws=draws,seed=seed,budget=budget,kind='synthetic_offline_example_NOT_CURRENT_FORECAST')


def save_comparison(report,output=None):
    from fpl_model.config import ROOT, RAW
    import pandas as pd
    out=Path(output) if output else ROOT/'artifacts/defensive_odds'/(
        datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')+'_'+uuid4().hex[:8])
    if out.resolve().is_relative_to(RAW.resolve()):raise ValueError('Cannot write outputs into raw storage')
    out.mkdir(parents=True,exist_ok=False)
    (out/'comparison.json').write_text(json.dumps(report,indent=2,ensure_ascii=False,allow_nan=False)+'\n')
    pd.DataFrame(report['player_changes']).to_csv(out/'player_changes.csv',index=False)
    pd.DataFrame(report['coverage']['fixtures']).to_csv(out/'fixture_coverage.csv',index=False)
    return out


def comparison_paths(root):
    return sorted(Path(root).glob('*/comparison.json'),reverse=True)
