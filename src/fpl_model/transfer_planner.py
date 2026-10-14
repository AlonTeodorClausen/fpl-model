"""Offline forecast cache and comparison of immediate transfers; no model fitting."""
from copy import deepcopy
from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from uuid import uuid4

import numpy as np

from fpl_model.defensive_odds import build_coverage
from fpl_model.label_contracts import utc
from fpl_model.models.baseline import model_version
from fpl_model.my_team import validate_profile
from fpl_model.optimizer.squad import evaluate_squad
from fpl_model.optimizer.transfers import optimize_transfers, NoTransferSolution
from fpl_model.simulation import simulate

VERSION = 'immediate_transfers_autosubs_v2'


def _json(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False)


def _safe_root(path):
    from fpl_model.config import RAW
    path = Path(path).resolve()
    if path.is_relative_to(RAW.resolve()):
        raise ValueError('Genererede resultater må ikke skrives i rå snapshots.')
    return path


def _read_bundle(path):
    bundle = json.loads((path/'bundle.json').read_text())
    arrays_path = path/'scenarios.npz'
    if hashlib.sha256(arrays_path.read_bytes()).hexdigest() != bundle['scenarios_sha256']:
        raise ValueError('Prognosecache har forkert checksum.')
    with np.load(arrays_path, allow_pickle=False) as arrays:
        bundle['scenarios'] = {e: dict(points=arrays[f'points_{e}'], played=arrays[f'played_{e}'])
                               for e in bundle['events']}
        if all(f'planning_points_{e}' in arrays for e in bundle['events']):
            bundle['planning_scenarios']={e:dict(points=arrays[f'planning_points_{e}'],played=arrays[f'planning_played_{e}'])
                                          for e in bundle['events']}
    for key in ('rows', 'coverage', 'explanations'):
        bundle[key] = {int(e): value for e,value in bundle[key].items()}
    if 'assist_models' in bundle:bundle['assist_models']={int(e):v for e,v in bundle['assist_models'].items()}
    if 'bonus_models' in bundle:bundle['bonus_models']={int(e):v for e,v in bundle['bonus_models'].items()}
    return bundle


def forecast_bundle(data, events, config, *, origin_at, cache_root, draws=3000, seed=42,
                    odds=None, progress=None, availability=None, availability_policy='hold_current', odds_scope='defence', evolution=None, role_assumptions=None, set_piece_config=None, set_piece_source=None, bonus_config=None, season_prior_config=None, assist_config=None):
    """Compute each GW once per immutable inputs/config/origin, never per proposal.

    Forecast scenarios choose teams; independent evaluation scenarios are shared
    by every proposal. Across-GW injury evolution/correlation is not modelled.
    """
    from fpl_model.attacking_odds import variant_version
    variant_version(odds_scope)
    if assist_config is not None and any(x is not None for x in (evolution,set_piece_config,bonus_config,season_prior_config)):
        raise ValueError('Assist correction is an isolated experiment')
    if season_prior_config is not None and any(x is not None for x in (evolution,set_piece_config,bonus_config)):
        raise ValueError("Previous-season priors are an isolated experiment")
    if bonus_config is not None and (evolution is not None or set_piece_config is not None):
        raise ValueError('Conditional bonus is an isolated experiment')
    if set_piece_config is not None:
        from fpl_model.set_piece_roles import VERSION as set_piece_version, validate_source
        if odds_scope!='attack_and_defence' or evolution is not None:raise ValueError('Set-piece sensitivity requires isolated attacking-odds model')
        validate_source(set_piece_source,data['players'],origin_at)
    if odds_scope=='attack_and_defence' and odds is None:raise ValueError('Attacking odds require explicit odds source/fallback')
    role_assumptions=role_assumptions or []
    if role_assumptions and evolution is None:raise ValueError('Role assumptions need experimental model')
    seen=set()
    for r in role_assumptions:
        key=(r['player_id'],r['event'])
        if key in seen or key[0] not in {p['id'] for p in data['players']} or key[1] not in events:raise ValueError('Unknown/duplicate role assumption')
        seen.add(key)
    events = sorted(events)
    if not 1 <= len(events) <= 4 or events != list(range(events[0], events[0]+len(events))):
        raise ValueError('Vælg 1–4 sammenhængende gameweeks.')
    origin = utc(origin_at)
    from fpl_model.availability import validate_assumptions, resolve_horizon_availability
    availability=validate_assumptions(availability,{p['id'] for p in data['players']},events,origin)
    resolved,derived=resolve_horizon_availability(data['players'],events,availability,origin,availability_policy)
    if utc(data['as_of_at']) > origin:
        raise ValueError('Officielle data er hentet efter prognosetidspunktet.')
    official = {e['id']: e for e in data['events']}
    if any(e not in official or utc(official[e]['deadline_time']) <= origin for e in events):
        raise ValueError('Alle valgte GWs skal have en fremtidig officiel deadline.')
    next_event = min(e for e in official if utc(official[e]['deadline_time']) > origin)
    if events[0] != next_event:
        raise ValueError('Transfers nu skal starte i næste officielle GW; senere transfersekvenser er ikke understøttet.')
    rules = data.get('rules', {})
    if rules.get('max_extra_free_transfers',4)!=4 or rules.get('transfers_cap',20)!=20:
        raise ValueError('Transferregler i snapshot er ændret; kræver eksplicit understøttelse.')
    code_root = Path(__file__).parent
    files = ['transfer_planner.py','models/baseline.py','simulation.py','scoring.py',
             'history_coverage.py','attacking_odds.py','diagnostics.py','defensive_odds.py','odds_api_markets.py','availability.py','model_evolution.py','role_minutes.py','set_piece_roles.py','conditional_bonus.py','season_priors.py','assist_correction.py']
    code = {name: hashlib.sha256((code_root/name).read_bytes()).hexdigest() for name in files}
    key = hashlib.sha256(_json(dict(data=data, events=events, config=asdict(config), origin=origin.isoformat(),
                                   draws=draws, seed=seed, odds=odds, code=code, availability=availability,
                                   availability_policy=availability_policy,odds_scope=odds_scope,evolution=asdict(evolution) if evolution else None,role_assumptions=role_assumptions,
                                   set_piece_config=asdict(set_piece_config) if set_piece_config else None,set_piece_source=set_piece_source,
                                   bonus_config=asdict(bonus_config) if bonus_config else None,
                                   season_prior_config=asdict(season_prior_config) if season_prior_config else None,
                                   assist_config=asdict(assist_config) if assist_config else None)).encode()).hexdigest()
    root = _safe_root(cache_root); path = root/key
    if (path/'bundle.json').is_file():
        if progress: progress('Genbruger gemte prognoser og scenarier.')
        return _read_bundle(path)
    d = deepcopy(data)
    sources=data.get('input_sources',{})
    d['player_metadata_available_at']=sources.get('player_metadata',{}).get(
        'available_at',sources.get('history',{}).get('available_at',data['as_of_at']))
    d['as_of_at'] = origin.isoformat()
    metadata = dict(cache_key=key, version=VERSION, forecast_origin_at=origin.isoformat(),
                    source_available_at=data['as_of_at'], snapshot_id=data['snapshot_id'],
                    snapshot_path=data.get('snapshot_path'), manifest_sha256=data.get('manifest_sha256'),
                    model_version=variant_version(odds_scope) if odds else model_version(config),odds_scope=odds_scope,
                    config=asdict(config), draws=draws, seed=seed, code_sha256=code,
                    scenario_streams=dict(planning='SeedSequence([seed, event, 0])',evaluation='SeedSequence([seed, event, 1])'),
                    availability_policy='current_availability_held_constant', prices_policy='fixed_current_prices',
                    deadlines={e: official[e]['deadline_time'] for e in events},
                    unassigned_fixture_ids=[f['id'] for f in data['fixtures'] if f.get('event') is None],
                    undated_fixture_ids=[f['id'] for f in data['fixtures'] if f.get('event') in events and not f.get('kickoff_time')],
                    input_sources=data.get('input_sources'), capture_coverage=data.get('coverage'))
    if evolution:
        metadata['model_version']=evolution.version
        metadata['evolution']=asdict(evolution)
        metadata['role_assumptions']=role_assumptions
        metadata['limitations']=['Independent minutes: no coherent team XI. Injury/return assumptions are not calibrated.',
            'Bonus still marginal. Own goals omitted.' if evolution.shared_goals else
            'Only playing time changes; per-minute event rates and scoring unchanged. Incomplete history retains baseline.']
    if set_piece_config is not None:
        metadata.update(model_version=set_piece_version,set_piece_config=asdict(set_piece_config),set_piece_source=set_piece_source['source'])
    if bonus_config is not None:
        metadata['model_version']+='__conditional_bonus_v1'
        metadata['bonus_config']=asdict(bonus_config)
        metadata['bonus_training']={}
    if season_prior_config is not None:
        metadata['model_version']+='__previous_season_attack_prior_v1'
        metadata['season_prior_config']=asdict(season_prior_config)
    if assist_config is not None:
        metadata['model_version']+='__fpl_assist_correction_v1'
        metadata['assist_config']=asdict(assist_config)
        metadata['assist_training']={}
    metadata['availability_assumptions']=availability
    metadata['derived_availability_assumptions']=derived
    if availability:
        metadata['base_model_version']=metadata['model_version']
        metadata['model_version']+='__manual_availability_v1'
        metadata['availability_policy']='explicit_gw_overrides_else_current_factor'
    if availability_policy!='hold_current':
        metadata.setdefault('base_model_version',metadata['model_version'])
        metadata['model_version']+='__short_doubt_scenario_v1'
        metadata['availability_policy']=availability_policy
    bundle = dict(cache_key=key, events=events, metadata=metadata, players=data['players'],
                  season=data.get('season','2026-2027'), rows={}, coverage={}, explanations={})
    if bonus_config is not None:bundle['bonus_models']={}
    if assist_config is not None:bundle['assist_models']={}
    arrays = {}
    for event in events:
        if progress: progress(f'Prognoser og fælles evalueringsscenarier for GW{event} …')
        coverage = build_coverage(d, odds[0], odds[1], event, config, origin.isoformat()) if odds else None
        # GW-specific fixed streams avoid accidental identical outcomes across weeks.
        event_seed = int(np.random.SeedSequence([seed,event,0]).generate_state(1)[0])
        eval_seed = int(np.random.SeedSequence([seed,event,1]).generate_state(1)[0])
        factors={r['player_id']:r['factor'] for r in resolved if r['event']==event}
        roles={r['player_id']:r for r in role_assumptions if r['event']==event}
        forecast = simulate(d,event,config,draws=draws,seed=event_seed,defensive_odds=coverage,availability_overrides=factors,odds_scope=odds_scope,evolution=evolution,role_overrides=roles,set_piece_config=set_piece_config,set_piece_source=set_piece_source,bonus_config=bonus_config,season_prior_config=season_prior_config,assist_config=assist_config)
        evaluation = simulate(d,event,config,draws=draws,seed=eval_seed,defensive_odds=coverage,availability_overrides=factors,odds_scope=odds_scope,evolution=evolution,role_overrides=roles,set_piece_config=set_piece_config,set_piece_source=set_piece_source,bonus_config=bonus_config,season_prior_config=season_prior_config,assist_config=assist_config)
        if bonus_config is not None:
            bundle['bonus_models'][event]=forecast.bonus_model
            metadata['bonus_training'][str(event)]={k:forecast.bonus_model[k] for k in
                ('status','reason','training_rows','sub60_rows','training_gameweeks','training_sha256')}
        if assist_config is not None:
            bundle['assist_models'][event]=forecast.assist_model
            metadata['assist_training'][str(event)]={k:forecast.assist_model[k] for k in
                ('status','reason','factor','training_rows','training_gameweeks','training_sha256')}
        rows = forecast.summary()
        for row in rows:
            explanation=forecast.explanations[row['player_id']]
            row['availability_factor']=explanation['injury_factor']
            if evolution:
                row['p_start_given_available']=explanation['pre_injury_start']
                row['p_sub_given_available']=explanation['pre_injury_sub']
                row['start_minutes']=explanation['start_minutes']
                row['return_assumption']=explanation.get('return_assumption')
                row['role_model']=explanation.get('role')
            row['p_start']=forecast.parameters[row['player_id']]['p_start']
            row['fixture_ids'] = [f['id'] for f in data['fixtures'] if f.get('event')==event
                                  and row['team_id'] in (f['team_h'],f['team_a'])]
            row['availability_assumption']=next((r['reason'] for r in resolved
                if r['event']==event and r['player_id']==row['player_id']),
                'Aktuel officiel faktor videreført; fremtidig tilgængelighed er ikke verificeret.' if event!=events[0]
                else 'Aktuel officiel faktor til næste GW.')
        bundle['rows'][event] = rows
        bundle['explanations'][event] = forecast.explanations
        bundle['coverage'][event] = coverage
        arrays[f'points_{event}'] = evaluation.points
        arrays[f'played_{event}'] = evaluation.minutes > 0
        arrays[f'planning_points_{event}'] = forecast.points
        arrays[f'planning_played_{event}'] = forecast.minutes > 0
    root.mkdir(parents=True, exist_ok=True)
    # A partial cache has no final key directory and cannot be mistaken for valid data.
    staging = root/('.building_'+uuid4().hex)
    staging.mkdir()
    np.savez_compressed(staging/'scenarios.npz', **arrays)
    bundle['scenarios_sha256'] = hashlib.sha256((staging/'scenarios.npz').read_bytes()).hexdigest()
    (staging/'bundle.json').write_text(_json(bundle)+'\n')
    try:
        staging.rename(path)
    except FileExistsError:
        # Another process completed exactly this content-addressed key.
        import shutil
        shutil.rmtree(staging)
    return _read_bundle(path)


def compare_packages(bundle, profile, *, max_transfers=1, locked=(), excluded=(), allow_hits=False,
                     bench_weight=.1, time_limit=30, progress=None):
    from fpl_model.optimizer.lineup import refine_plan
    if 'planning_scenarios' not in bundle:raise ValueError('Mangler separate scenarier til planlægning; genberegn prognosecache.')
    lineup_cache={}
    validate_profile(profile, bundle['players'], season=bundle['season'])
    if type(max_transfers) is not int or not 0 <= max_transfers <= 15:
        raise ValueError('Maksimalt antal transfers skal være 0–15.')
    owned = {p['player_id'] for p in profile['players']}
    ids = {p['id'] for p in bundle['players']}
    if not set(locked)<=owned or not set(excluded)<=ids or set(locked)&set(excluded):
        raise ValueError('Ukendte eller modstridende behold/udeluk-valg.')
    maximum = min(max_transfers,20-profile['transfers_made'],15,
                  15 if allow_hits else profile['free_transfers'])
    proposals, failures = [], []
    hold_values = None
    for count in range(maximum+1):
        if progress: progress('Vurderer uændret hold …' if count==0 else f'Søger pakke med {count} transfers …')
        try:
            proposal = optimize_transfers(bundle['rows'], profile, count=count,
                locked=locked if count else (), excluded=excluded if count else (), allow_hits=allow_hits,
                bench_weight=bench_weight, time_limit=time_limit)
        except NoTransferSolution as exc:
            if count==0: raise
            failures.append(dict(count=count, reason=str(exc)))
            continue
        refine_plan(proposal,bundle,lineup_cache)
        values_by_gw = []
        proposal['per_gw'] = []
        for index,event in enumerate(bundle['events']):
            scenario = bundle['scenarios'][event]
            evaluated = evaluate_squad(proposal['lineups'][event],bundle['rows'][event],
                                       scenario['points'],scenario['played'])
            hits = proposal['hits'] if index==0 else 0
            values = evaluated['points']-hits
            values_by_gw.append(values)
            proposal['per_gw'].append(dict(event=event, mean=float(values.mean()),
                p10=float(np.quantile(values,.1)), p90=float(np.quantile(values,.9)),
                bench_mean=float(evaluated['bench_points'].mean()),hits=hits,
                objective=proposal['lineups'][event]['objective']-hits))
        if count==0:
            hold_values = values_by_gw
        for index,row in enumerate(proposal['per_gw']):
            row['gain'] = float((values_by_gw[index]-hold_values[index]).mean())
        proposal['total_points'] = sum(row['mean'] for row in proposal['per_gw'])
        proposal['total_gain'] = sum(row['gain'] for row in proposal['per_gw'])
        proposal['next_gw_gain'] = proposal['per_gw'][0]['gain']
        proposal['objective_gain'] = proposal['objective']-(proposals[0]['objective'] if proposals else proposal['objective'])
        proposals.append(proposal)
    return dict(version=VERSION,created_at=datetime.now(timezone.utc).isoformat(),
                scope='transfers_now_then_hold',profile=deepcopy(profile), forecast=bundle['metadata'],
                config=dict(max_transfers=max_transfers,effective_max_transfers=maximum,locked=sorted(locked),
                            excluded=sorted(excluded),allow_hits=allow_hits,bench_weight=bench_weight,time_limit=time_limit),
                players_by_event=bundle['rows'], odds_coverage=bundle['coverage'],
                packages=proposals, unavailable_packages=failures,
                limitations=[
                    'Alle transfers foretages nu; truppen beholdes gennem hele horisonten. Ingen chips.',
                    'Fremtidig tilgængelighed følger den gemte politik og GW-antagelser; ingen medicinsk model for raskmelding eller ny skade.',
                    'Faste fremtidige priser. Opsparede transfers vises, men værdien af at vente er ikke optimeret.',
                    'Kandidattrupper findes med vægtet bænk. Opstillinger optimeres udtømmende inkl. autosubs/vice på separate planlægningsscenarier.',
                    'Bedste fundne pakke pr. transferantal, ikke alle pakker eller et optimum af simulerede holdpoint.',
                    'Faste opstillinger vælges nu uden fremtidig information. Uafhængige minutter og GWs; foreløbige sandsynligheder.'])


def save_report(report, output_root):
    root = _safe_root(output_root)
    path = root/(datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')+'_'+uuid4().hex[:8])
    path.mkdir(parents=True, exist_ok=False)
    (path/'report.json').write_text(_json(report)+'\n')
    return path
