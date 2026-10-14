"""Optional previous-season xG/xA means; official IDs, original capture provenance.

No old season minutes are interpreted as current participation probabilities.
Only the immediately preceding season is used: no stale-season fallback.
"""
from dataclasses import dataclass
import json
import math
import re
from pathlib import Path
from fpl_model.label_contracts import utc
from fpl_model.models.baseline import number

VERSION='previous_season_attack_prior_v1'


@dataclass(frozen=True)
class SeasonPriorConfig:
    position_prior_90s: float = 3.0

    def __post_init__(self):
        if isinstance(self.position_prior_90s,bool) or not math.isfinite(self.position_prior_90s) or self.position_prior_90s<=0:
            raise ValueError('Positive finite position prior exposure required')


def read_season_histories(root,manifest,players):
    """Called after verify_snapshot; do not deduce identity from player names."""
    root=Path(root);pool={p['id'] for p in players};result=[]
    contexts=[f for f in manifest['files'] if f['source']=='fpl_api' and f['outcome']=='success'
              and f['relative_path'].endswith('/bootstrap_static.json')]
    if len(contexts)!=1:raise ValueError('Missing/ambiguous bootstrap identity provenance')
    bootstrap_time=utc(contexts[0].get('available_at',contexts[0]['retrieved_at']))
    for f in manifest['files']:
        match=re.search(r'/element_summary/(\d+)\.json$',f.get('relative_path',''))
        if not match or f['source']!='fpl_api' or f['outcome']!='success':continue
        pid=int(match[1])
        if pid not in pool:continue
        payload=json.loads((root/f['relative_path']).read_bytes())
        rows=payload.get('history_past')
        source=dict(snapshot_id=manifest['run_id'],relative_path=f['relative_path'],sha256=f['sha256'],
            identity_relative_path=contexts[0]['relative_path'],identity_sha256=contexts[0]['sha256'])
        common=dict(player_id=pid,source='fpl_api',retrieved_at=f['retrieved_at'],
            available_at=max(bootstrap_time,utc(f.get('available_at',f['retrieved_at']))).isoformat(timespec='microseconds'),
            provenance=source)
        if not isinstance(rows,list):
            result.append(dict(**common,reason='missing_or_invalid_history_past'));continue
        if not rows:
            result.append(dict(**common,reason='empty_history_past'));continue
        for row in rows:
            if not isinstance(row,dict):
                result.append(dict(**common,reason='invalid_history_past_row'));continue
            result.append(dict(**{k:row.get(k) for k in ('season_name','element_code','minutes','expected_goals','expected_assists')},**common))
    return sorted(result,key=lambda r:(r['player_id'],str(r.get('season_name')),r['provenance']['relative_path']))


def player_prior(data,player,cutoff_at,config,*,retrospective=False):
    cutoff=utc(cutoff_at)
    result=dict(version=VERSION,status='position_fallback',reason=None,rates={},
        availability_contract='later_captured_previous_season' if retrospective else 'available_at_lte_forecast_origin')
    def fallback(reason):return dict(result,reason=reason)
    season=data.get('season','')
    match=re.fullmatch(r'(\d{4})-(\d{4})',season)
    if not match or int(match[2])!=int(match[1])+1:return fallback('unresolved_current_season')
    start=int(match[1]);previous=f'{start-1}/{start%100:02d}'
    result['season_name']=previous
    # Older API seasons may have placeholder zero xG/xA. This experiment only
    # supports recent expected-stat seasons; do not invent historical coverage.
    if start-1<2022:return fallback('expected_stats_coverage_unverified')
    own=[r for r in data.get('season_histories',[]) if r.get('player_id')==player['id']]
    candidates=[r for r in own if r.get('season_name')==previous]
    if not candidates:return fallback('no_previous_season' if own else 'missing_response_or_unloaded_history')
    eligible=[]
    for r in candidates:
        try:observed=utc(r['available_at'])
        except (KeyError,ValueError,TypeError):continue
        if retrospective or observed<=cutoff:eligible.append(r)
    if not eligible:return fallback('post_cutoff_or_unknown_time' if any(not r.get('available_at') for r in candidates) else 'post_cutoff')
    # Multiple versions are not silently selected or merged in this bounded loader.
    if len(eligible)!=1:return fallback('conflicting_previous_season')
    r=eligible[0]
    if r.get('source')!='fpl_api' or type(player.get('code')) is not int or type(r.get('element_code')) is not int or r['element_code']!=player['code']:
        return fallback('identity_mismatch')
    if not r.get('provenance',{}).get('sha256'):return fallback('missing_provenance')
    minutes=number(r.get('minutes'))
    if isinstance(r.get('minutes'),bool) or minutes is None or minutes<=0:return fallback('no_positive_minutes')
    result.update(available_at=r['available_at'],retrieved_at=r.get('retrieved_at'),provenance=r['provenance'],
        element_code=r['element_code'],minutes=minutes,exposure_90s=minutes/90)
    defaults={'goals':{1:.002,2:.06,3:.20,4:.38}[player['element_type']],
              'assists':{1:.005,2:.09,3:.16,4:.12}[player['element_type']]}
    for key,field in [('goals','expected_goals'),('assists','expected_assists')]:
        value=number(r.get(field));default=defaults[key]
        valid=value is not None and not isinstance(r.get(field),bool)
        result['rates'][key]=dict(status='used' if valid else 'position_fallback',
            reason=None if valid else 'missing_or_invalid_'+field,field=field,count=value if valid else None,
            observed_per90=value/(minutes/90) if valid else None,position_prior_per90=default,
            position_prior_90s=config.position_prior_90s,
            prior_per90=(value+config.position_prior_90s*default)/(minutes/90+config.position_prior_90s) if valid else default)
    n=sum(r['status']=='used' for r in result['rates'].values())
    result.update(status='used' if n==2 else 'partial' if n else 'position_fallback',reason=None if n==2 else 'missing_expected_stats')
    return result


def apply_prior(parameters,prior):
    parameters['explanation']['season_prior']=prior
    if prior['status']!='used':
        parameters['fallbacks']=sorted(set(parameters['fallbacks']+['season_prior_'+prior['reason']]))
    for key,r in prior['rates'].items():
        if r['status']!='used':continue
        detail=parameters['explanation']['rates'][key]
        detail['position_prior_per90']=detail['prior_per90']
        detail['prior_per90']=r['prior_per90']
        detail['prior_source']=VERSION
        rate=(detail['count']+detail['prior_90s']*r['prior_per90'])/(detail['exposure_90s']+detail['prior_90s'])
        detail['smoothed_per90']=parameters[key]=rate
