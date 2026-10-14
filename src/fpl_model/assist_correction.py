"""Pooled, shrunk FPL-assist/xA correction; not an event-level assist rules engine.

The ratio mixes definition differences, finishing and sampling noise. It is an
experimental multiplicative correction, never a known count of extra assists.
"""
from collections import Counter
from dataclasses import dataclass,asdict
import hashlib
import json
import math
from fpl_model.label_contracts import utc
from fpl_model.models.baseline import number

VERSION='fpl_assist_correction_v1'


@dataclass(frozen=True)
class AssistConfig:
    prior_xa: float = 20.0
    min_rows: int = 100
    min_xa: float = 5.0

    def __post_init__(self):
        if any(isinstance(v,bool) or not isinstance(v,(int,float)) or not math.isfinite(v) or v<=0 for v in (self.prior_xa,self.min_xa)):
            raise ValueError('Positive finite assist prior/exposure required')
        if type(self.min_rows) is not int or self.min_rows<20:raise ValueError('At least 20 matched rows required')


def fit_correction(data,event,cutoff_at,config,*,retrospective=False):
    cutoff=utc(cutoff_at)
    pool={p['id'] for p in data.get('assist_training_players',data['players'])}
    rows=[];seen=set();rejected=Counter()
    for r in data['histories']:
        if r.get('source')!='fpl_api' or r.get('label_state')!='final':continue
        if r['event']>=event or utc(r['kickoff_time'])>=cutoff:continue
        if not retrospective and (not r.get('available_at') or utc(r['available_at'])>cutoff):continue
        key=(r['player_id'],r['fixture_id'])
        if key in seen:raise ValueError('Duplicate assist training player-fixture; select observation versions first')
        seen.add(key)
        if key[0] not in pool:rejected['unknown_identity']+=1;continue
        minutes=r.get('minutes');assists=r.get('assists');xa=number(r.get('expected_assists'))
        if (type(minutes) is not int or not 0<=minutes<=90 or type(assists) is not int or assists<0
                or xa is None or isinstance(r.get('expected_assists'),bool)):
            rejected['missing_or_invalid_fields']+=1;continue
        if minutes==0:
            rejected['explicit_dnp']+=1;continue
        rows.append(dict(player_id=key[0],fixture_id=key[1],event=r['event'],minutes=minutes,
            fpl_assists=assists,expected_assists=xa,observation_id=r.get('observation_id'),
            snapshot_id=r.get('source_snapshot_id'),available_at=r.get('available_at'),kickoff_time=r['kickoff_time']))
    rows.sort(key=lambda r:(r['event'],r['fixture_id'],r['player_id']))
    total_a=sum(r['fpl_assists'] for r in rows);total_xa=math.fsum(r['expected_assists'] for r in rows)
    report=dict(version=VERSION,status='baseline_fallback',reason='insufficient_training',factor=1.,
        config=asdict(config),training_rows=len(rows),training_gameweeks=sorted({r['event'] for r in rows}),
        training_observations=rows,training_sha256=hashlib.sha256(json.dumps(rows,sort_keys=True,allow_nan=False).encode()).hexdigest(),
        fpl_assists=total_a,expected_assists=total_xa,raw_ratio=total_a/total_xa if total_xa else None,
        rejected=dict(sorted(rejected.items())),cutoff_at=cutoff.isoformat(),
        availability_contract='later_captured_labels_prior_events_only' if retrospective else 'available_by_origin')
    if len(rows)<config.min_rows:return report
    if total_xa<config.min_xa:return dict(report,reason='insufficient_xa_exposure')
    return dict(report,status='fitted',reason=None,factor=(total_a+config.prior_xa)/(total_xa+config.prior_xa))


def apply_correction(parameters,model):
    before=parameters['assists'];after=before*model['factor']
    parameters['assists']=after
    parameters['explanation']['assist_correction']={k:model[k] for k in
        ('version','status','reason','factor','training_rows','training_gameweeks','training_sha256','availability_contract')}
    parameters['explanation']['assist_correction'].update(xa_proxy_per90=before,corrected_fpl_assists_per90=after)
    # Keep the observed xA and its smoothing distinct from the FPL rate.
    if model['status']=='baseline_fallback':
        parameters['fallbacks']=sorted(set(parameters['fallbacks']+['assist_correction_'+model['reason']]))
