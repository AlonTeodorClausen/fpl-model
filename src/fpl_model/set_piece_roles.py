"""Opt-in budget sensitivity, NOT an identified penalty/open-play decomposition.

FPL provides role order, not calibrated taking probabilities or historical npxG.
Replace a fraction of existing shares; never add a second penalty xG component.
"""
from copy import deepcopy
from dataclasses import dataclass, asdict
import hashlib
import json
import math
from pathlib import Path
from fpl_model.label_contracts import utc
from fpl_model.io import verify_snapshot

VERSION='component_set_piece_sensitivity_v1'
FIELDS=('penalties_order','direct_freekicks_order','corners_and_indirect_freekicks_order')


@dataclass(frozen=True)
class SetPieceConfig:
    # Operational sensitivity assumptions, not estimated event frequencies.
    penalty_goal_share: float = .10
    direct_goal_share: float = .02
    indirect_assist_share: float = .15
    role_confidence: float = .5

    def __post_init__(self):
        if any(isinstance(v,bool) or not math.isfinite(v) or not 0<=v<=1 for v in asdict(self).values()):
            raise ValueError('Set-piece sensitivity assumptions must be finite fractions in [0,1]')
        if self.penalty_goal_share+self.direct_goal_share>1:raise ValueError('Goal shares exceed existing budget')


def load_roles(snapshot):
    root=Path(snapshot).resolve();manifest=verify_snapshot(root)
    files=[f for f in manifest['files'] if f['source']=='fpl_api' and f['outcome']=='success'
        and f['relative_path'].endswith('/bootstrap_static.json')]
    if len(files)!=1:raise ValueError('Need one verified official bootstrap for roles')
    f=files[0];body=(root/f['relative_path']).read_bytes();players=json.loads(body)['elements']
    source=dict(snapshot_id=manifest['run_id'],snapshot_path=str(root),raw_path=f['relative_path'],
        sha256=hashlib.sha256(body).hexdigest(),manifest_sha256=hashlib.sha256((root/'manifest.json').read_bytes()).hexdigest(),
        retrieved_at=f['retrieved_at'],available_at=f.get('available_at') or f['retrieved_at'],source_published_at=None)
    return dict(source=source,players=[dict(player_id=p['id'],team_id=p['team'],
        **{k:p.get(k) for k in FIELDS}) for p in players])


def validate_source(record,players,origin):
    if not record or not record.get('source'):raise ValueError('Explicit captured role provenance required')
    s=record['source']
    if not all(s.get(k) for k in ('snapshot_id','raw_path','sha256','retrieved_at','available_at')):raise ValueError('Incomplete role provenance')
    if max(utc(s['retrieved_at']),utc(s['available_at']))>utc(origin):raise ValueError('Roles observed after forecast origin/deadline')
    if utc(s['available_at'])<utc(s['retrieved_at']):raise ValueError('Role availability cannot predate retrieval')
    by_id={r['player_id']:r for r in record['players']}
    if len(by_id)!=len(record['players']):raise ValueError('Duplicate role identity')
    if any(p['id'] not in by_id or by_id[p['id']]['team_id']!=p['team'] for p in players):
        raise ValueError('Role player/team identity differs; no guessed cross-team mapping')


def _claims(rates,records,field):
    known=[r for r in records if r['player_id'] in rates and r.get(field) is not None]
    if not known:return {},dict(status='unknown',reason='no_documented_order',claimed=0.)
    ranks=[r[field] for r in known]
    if any(type(v) is not int or v<1 for v in ranks) or len(ranks)!=len(set(ranks)):
        return {},dict(status='conflicted',reason='invalid_or_duplicate_order',claimed=0.)
    if min(ranks)!=1:return {},dict(status='unknown',reason='missing_first_choice',claimed=0.)
    if sorted(ranks)!=list(range(1,len(ranks)+1)):
        return {},dict(status='unknown',reason='missing_order_slot',claimed=0.)
    claims={};remaining=1.
    for r in sorted(known,key=lambda r:r[field]):
        exposure=min(1.,max(0.,rates[r['player_id']]['expected_exposure_90s']))
        claims[r['player_id']]=remaining*exposure;remaining*=1-exposure
    return claims,dict(status='assumed',reason=None,claimed=1-remaining,
        policy='ordered_priority_independent_on_pitch_exposure',unassigned_fraction=remaining)


def allocate_roles(rates,records,config):
    """Reallocate existing budgets, with residual unknown duty retaining old shares.

    Exposure products approximate who is on the pitch; no joint team XI claim.
    Goal and assist budgets are unchanged, including the original assist proxy.
    """
    out=deepcopy(rates);claims={};markets={}
    for field in FIELDS:claims[field],markets[field]=_claims(rates,records,field)
    weights={FIELDS[0]:config.penalty_goal_share*config.role_confidence,
             FIELDS[1]:config.direct_goal_share*config.role_confidence,
             FIELDS[2]:config.indirect_assist_share*config.role_confidence}
    for pid,r in out.items():
        def components(base,fields):
            used=sum(weights[f]*sum(claims[f].values()) for f in fields)
            return dict(historical_residual=(1-used)*base,
                **{f:weights[f]*claims[f].get(pid,0.) for f in fields})
        goal=components(r['goal_share'],FIELDS[:2]);assist=components(r['assist_share'],FIELDS[2:])
        g=sum(goal.values());a=sum(assist.values());exposure=r['expected_exposure_90s']
        # Preserve bit-identical fallback (including unused per90 priors for DNP).
        if any(weights[f] and claims[f] for f in FIELDS[:2]):
            r.update(goal_share=g,expected_goals=r['team_goal_mean']*g,
                goals_per90=r['team_goal_mean']*g/exposure if exposure>0 else 0.)
        if weights[FIELDS[2]] and claims[FIELDS[2]]:
            budget=r['team_goal_mean']*r['team_assist_fraction']
            r.update(assist_share=a,expected_assists=budget*a,assists_per90=budget*a/exposure if exposure>0 else 0.)
        r['set_pieces']=dict(kind='assumed_budget_reallocation',historical_nonpenalty_xg_known=False,
            config=asdict(config),markets=markets,goal_share_components=goal,assist_share_components=assist,
            original_goal_share=rates[pid]['goal_share'],original_assist_share=rates[pid]['assist_share'],
            orders={f:next((x.get(f) for x in records if x['player_id']==pid),None) for f in FIELDS})
    return out
