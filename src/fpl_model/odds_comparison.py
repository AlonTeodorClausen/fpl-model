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


def load_inputs(history_snapshot,context_snapshot,forecast_origin_at,*,include_season_history=False):
    """Keep captured player histories/prices/status; refresh only fixtures/deadlines/teams.

    as_of_at is the information cutoff, never a rewritten source retrieval time.
    All original source times/paths remain under input_sources.
    """
    d=load_data(history_snapshot,include_season_history=True) if include_season_history else load_data(history_snapshot);origin=utc(forecast_origin_at)
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
        manifest_sha256=d['manifest_sha256'],available_at=d['as_of_at'],
        age_hours_at_forecast=(origin-utc(d['as_of_at'])).total_seconds()/3600),
        official_context=dict(**_ref(root,manifest),files=entries,
            age_hours_at_forecast={f['relative_path']:(origin-utc(f.get('available_at',f['retrieved_at']))).total_seconds()/3600 for f in entries}),deadline_revisions=revisions,
        player_metadata_note='Player histories, prices and injury/status fields are reused at their original capture time; not refreshed.')
    d.update(fixtures=fixtures,events=bootstrap['events'],teams=bootstrap['teams'],as_of_at=origin.isoformat())
    return d


def load_odds(snapshot,source_name='football_data_uk'):
    if source_name not in ('football_data_uk','the_odds_api'):raise ValueError('Unknown odds source')
    root=Path(snapshot).resolve();manifest=verify_snapshot(root)
    failures=[f for f in manifest['failures'] if f['source']==source_name]
    bad_paths={f.get('relative_path') for f in failures}
    entries=[f for f in manifest['files'] if f['source']==source_name and f['outcome']=='success'
             and f['relative_path'] not in bad_paths]
    reference=_ref(root,manifest)
    if len(entries)!=1:
        return [],dict(**reference,source=source_name,source_published_at=None,
                       failure='no_unique_valid_odds_response',failures=failures)
    entry=entries[0]
    body=(root/entry['relative_path']).read_bytes()
    source={**reference,**entry,
        'raw_path':entry['relative_path'],'available_at':entry.get('available_at',entry['retrieved_at']),'source_published_at':None}
    if source_name=='the_odds_api':
        try:
            rows=json.loads(body)
            if not isinstance(rows,list) or any(not isinstance(e,dict) for e in rows):raise ValueError()
        except (ValueError,UnicodeError):return [],dict(source,failure='invalid_api_payload')
    else:rows=read_csv(body)
    return rows,source


def compare_forecasts(data,coverage,config,*,draws=3000,seed=42,budget=100,kind='current_forecast_comparison',odds_scope='defence'):
    if config.frequency_prior_games!=1 or config.minutes_prior_games!=1:
        raise ValueError('This bounded odds comparison retains both minutes priors at 1.0')
    event=coverage['event']
    baseline,base_sim,_=run_prototype(data,event,config,draws=draws,seed=seed,budget=budget,evaluate_history=False)
    variant,odds_sim,_=run_prototype(data,event,config,draws=draws,seed=seed,budget=budget,
                                    defensive_odds=coverage,evaluate_history=False,odds_scope=odds_scope)
    defensive_reference=None
    if odds_scope=='attack_and_defence':
        defensive_reference,defensive_sim,_=run_prototype(data,event,config,draws=draws,seed=seed,budget=budget,
                                                          defensive_odds=coverage,evaluate_history=False)
        for pid,e in odds_sim.explanations.items():
            for key,value in e['point_components'].items():
                if key not in ('goals','assists') and value!=defensive_sim.explanations[pid]['point_components'][key]:
                    raise ValueError('Attacking odds changed a nonattacking component versus defensive reference')
    # Verify every actual comparison, not only the test fixtures. The model/RNG
    # is unchanged; these checks reject any accidental expansion of the scope.
    import numpy as np
    if not np.array_equal(base_sim.minutes,odds_sim.minutes):raise ValueError('Odds changed simulated minutes')
    for pid,before in base_sim.explanations.items():
        after=odds_sim.explanations[pid]
        if odds_scope=='defence' and before['fixtures']!=after['fixtures']:raise ValueError('Odds changed offensive fixture assumptions')
        for key,value in before['point_components'].items():
            if key not in (('clean_sheets','goals_conceded','goals','assists') if odds_scope=='attack_and_defence' else ('clean_sheets','goals_conceded')) and value!=after['point_components'][key]:
                raise ValueError('Odds changed a nondefensive point component')
    defensive_components=('clean_sheets','goals_conceded','saves','defensive_contribution','penalties_saved')
    changes=[]
    for before,after in zip(baseline['players'],variant['players']):
        pid=before['player_id']
        base_def=sum(base_sim.explanations[pid]['point_components'][k] for k in defensive_components)
        odds_def=sum(odds_sim.explanations[pid]['point_components'][k] for k in defensive_components)
        changes.append(dict(player_id=pid,name=before['name'],position=before['position'],team_id=before['team_id'],
            baseline_defensive_points=base_def,odds_defensive_points=odds_def,defensive_points_delta=odds_def-base_def,
            baseline_attacking_points=sum(base_sim.explanations[pid]['point_components'][k] for k in ('goals','assists')),
            odds_attacking_points=sum(odds_sim.explanations[pid]['point_components'][k] for k in ('goals','assists')),
            attacking_points_delta=sum(odds_sim.explanations[pid]['point_components'][k]-base_sim.explanations[pid]['point_components'][k] for k in ('goals','assists')),
            baseline_xp=before['xp'],odds_xp=after['xp'],xp_delta=after['xp']-before['xp'],
            minutes_delta=after['expected_minutes']-before['expected_minutes']))
        if defensive_reference is not None:
            reference_xp=defensive_sim.explanations[pid]['expected_points']
            changes[-1].update(defensive_variant_xp=reference_xp,attack_extension_xp_delta=after['xp']-reference_xp)
    attack_coverage=None
    if odds_scope=='attack_and_defence':
        teams={p['id']:p['team'] for p in data['players']};budgets={}
        for pid,e in odds_sim.explanations.items():
            for f in e['fixtures']:
                a=f['attack_odds'];key=(f['fixture_id'],teams[pid])
                row=budgets.setdefault(key,dict(fixture_id=key[0],team_id=key[1],status=a['status'],
                    reason=a.get('reason'),expected_player_goals=0. if a['status']=='odds' else None,
                    expected_player_assists=0. if a['status']=='odds' else None,
                    market_team_goals=a.get('team_goal_mean')))
                if a['status']=='odds':
                    row['expected_player_goals']+=a['expected_goals']
                    row['expected_player_assists']+=a['expected_assists']
        applied={row['fixture_id'] for row in coverage['fixtures'] if
            sum(b['status']=='odds' for b in budgets.values() if b['fixture_id']==row['fixture_id'])==2}
        attack_coverage=dict(fully_applied=len(applied),expected_fixtures=coverage['expected_fixtures'],
                             team_budgets=list(budgets.values()))
    bt,ot=baseline['team'],variant['team']
    return dict(kind=kind,odds_scope=odds_scope,default_model_changed=False,event=event,forecast_origin_at=data['as_of_at'],
        deadline_at=coverage['deadline_at'],source_history_snapshot_id=data['snapshot_id'],
        input_sources=data.get('input_sources'),coverage=coverage,baseline=baseline,odds_variant=variant,
        defensive_reference=defensive_reference,attack_coverage=attack_coverage,
        defensive_point_components=list(defensive_components),player_changes=changes,team_changes=dict(added=sorted(set(ot['squad'])-set(bt['squad'])),
            removed=sorted(set(bt['squad'])-set(ot['squad'])),baseline_starters=bt['starters'],odds_starters=ot['starters'],
            starters_added=sorted(set(ot['starters'])-set(bt['starters'])),starters_removed=sorted(set(bt['starters'])-set(ot['starters'])),
            baseline_captain=bt['captain'],odds_captain=ot['captain']),
        invariants=dict(minutes_identical=True,nondefensive_components_identical=odds_scope=='defence',offensive_fixture_assumptions_identical=odds_scope=='defence',non_goal_assist_defensive_components_identical=True),
        scope=('Team odds goal budgets are allocated by smoothed xG/xA and expected minutes; defence also uses odds. Minutes/bonus/other events unchanged.' if odds_scope=='attack_and_defence' else 'Only clean sheets and conceded-goal point deductions use odds. Minutes, attacks, saves, bonus and all other components unchanged.'),
        limitations=['Forecast comparison, not evidence of which variant is better; no historical evaluation with these odds.',
            'Independent Poisson goal rates/clean sheets are model-derived; bookmaker probabilities need not be exactly Poisson-consistent.',
            'Separate odds random streams; point deltas include Monte Carlo noise.',
            'Attacking variant: xA/xG gives a capped assist-fraction proxy, not a calibrated FPL-assist probability. Player event counts remain independent; no shared team-score constraint.',
            'Attacking shares require the full official player pool; injured/inactive players alter other players shares. Historical/prior rates do not separately identify penalties or set pieces.',
            'Exact price publication time unknown. Provider last_update, when present, is separate from local available_at = retrieved_at.',
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
