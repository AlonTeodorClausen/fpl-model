"""Experimental conditional 0–3 bonus, not a BPS ranking or match bonus budget.

Fit only earlier final official observations. At prediction time the covariates
are SIMULATED events, never actual outcomes of the fixture being forecast.
"""
from collections import Counter
from dataclasses import asdict, dataclass
import hashlib
import json
import math

import numpy as np
from scipy.optimize import minimize
from scipy.special import expit
from fpl_model.label_contracts import utc

VERSION='conditional_bonus_v1'
FEATURES=('intercept','minutes_90','goals_capped3','assists_capped3',
          'keeper_defender_clean_sheet','defcon_award','goalkeeper','defender','midfielder')


@dataclass(frozen=True)
class BonusConfig:
    ridge: float = 1.0
    min_rows: int = 100

    def __post_init__(self):
        if isinstance(self.ridge,bool) or not math.isfinite(self.ridge) or self.ridge<=0:
            raise ValueError('Positive finite bonus regularization required')
        if type(self.min_rows) is not int or self.min_rows<20:
            raise ValueError('At least 20 training rows required')


def _features(position,minutes,goals,assists,clean,defcon):
    arrays=np.broadcast_arrays(position,minutes,goals,assists,clean,defcon)
    p,m,g,a,c,d=[np.atleast_1d(x).astype(float) for x in arrays]
    return np.column_stack([np.ones_like(m),m/90,np.minimum(g,3),np.minimum(a,3),
        c*(p<=2)*(m>=60),d,p==1,p==2,p==3])


def fit_bonus(data,event,cutoff_at,config,*,retrospective=False):
    cutoff=utc(cutoff_at)
    # Historical evaluation must not restrict this pool to players whose TARGET
    # later exists; target availability is not a training-selection criterion.
    players={p['id']:p for p in data.get('bonus_training_players',data['players'])}
    rows=[];rejected=Counter();seen=set()
    fields=('minutes','goals_scored','assists','clean_sheets','defensive_contribution','bonus')
    for r in data['histories']:
        if r.get('label_state')!='final' or r.get('source')!='fpl_api':continue
        if r['event']>=event or utc(r['kickoff_time'])>=cutoff:continue
        if not retrospective and (r.get('available_at') is None or utc(r['available_at'])>cutoff):continue
        key=(r['player_id'],r['fixture_id'])
        if key in seen:raise ValueError('Duplicate bonus training player-fixture; select observation versions first')
        seen.add(key)
        if r['player_id'] not in players:
            rejected['unknown_identity']+=1;continue
        pos=players[r['player_id']]['element_type']
        vals=[r.get(k) for k in fields]
        if pos not in (1,2,3,4) or any(isinstance(v,bool) or not isinstance(v,(int,float)) or
                not math.isfinite(v) or v<0 or v!=int(v) for v in vals) or vals[0]>90 or vals[3]>1 or vals[-1]>3:
            rejected['missing_or_invalid_fields']+=1;continue
        m,g,a,c,d,b=vals
        if m==0:
            rejected['explicit_dnp']+=1;continue
        rows.append(dict(player_id=key[0],fixture_id=key[1],event=r['event'],position=pos,
            observation_id=r.get('observation_id'),snapshot_id=r.get('source_snapshot_id'),
            available_at=r.get('available_at'),kickoff_time=r['kickoff_time'],
            values=vals))
    rows.sort(key=lambda r:(r['event'],r['fixture_id'],r['player_id']))
    digest=hashlib.sha256(json.dumps(rows,sort_keys=True,allow_nan=False).encode()).hexdigest()
    report=dict(version=VERSION,status='baseline_fallback',reason='insufficient_training',
        config=asdict(config),feature_names=list(FEATURES),training_rows=len(rows),
        sub60_rows=sum(r['values'][0]<60 for r in rows),training_sha256=digest,
        training_observations=rows,rejected=dict(sorted(rejected.items())),cutoff_at=cutoff.isoformat(),
        training_gameweeks=sorted({r['event'] for r in rows}),
        availability_contract='later_captured_labels_prior_events_only' if retrospective else 'available_by_origin',
        coefficients=None)
    if len(rows)<config.min_rows or sum(r['values'][-1]>0 for r in rows)<5:return report
    vals=np.array([r['values'] for r in rows]);pos=np.array([r['position'] for r in rows])
    X=_features(pos,vals[:,0],vals[:,1],vals[:,2],vals[:,3],
        (pos!=1)*(vals[:,4]>=np.where(pos==2,10,12)))
    y=vals[:,-1];penalty=np.ones(X.shape[1]);penalty[0]=0
    def loss(beta):
        z=X@beta
        return (float(np.sum(3*np.logaddexp(0,z)-y*z)+.5*config.ridge*np.sum(penalty*beta**2)),
                X.T@(3*expit(z)-y)+config.ridge*penalty*beta)
    initial=np.zeros(X.shape[1]);p=(y.sum()+1)/(3*len(y)+2);initial[0]=math.log(p/(1-p))
    # More goals/assists/defensive awards cannot lower bonus holding other
    # covariates constant. Fixed regularization, no hyperparameter search.
    bounds=[(None,None)]*len(initial)
    for i in (1,2,3,4,5):bounds[i]=(0,None)
    result=minimize(loss,initial,jac=True,method='L-BFGS-B',bounds=bounds,
                    options=dict(maxiter=500,ftol=1e-12,gtol=1e-7))
    if not result.success or not np.isfinite(result.x).all():
        report['reason']='fit_failed';return report
    report.update(status='fitted',reason=None,coefficients=result.x.tolist(),iterations=int(result.nit),
        method='Ridge binomial GLM: mean = 3 * logistic(X beta); conditional on played')
    return report


def expected_bonus(model,position,minutes,components):
    if model['status']!='fitted':raise ValueError('Use unchanged baseline on bonus fallback')
    X=_features(position,minutes,np.asarray(components['goals'])/{1:10,2:6,3:5,4:4}[position],
        np.asarray(components['assists'])/3,np.asarray(components['clean_sheets'])>0,
        np.asarray(components['defensive_contribution'])>0)
    return 3*expit(X@np.asarray(model['coefficients']))*(np.atleast_1d(minutes)>0)


def sample_bonus(model,position,minutes,components,*,seed,fixture_id,player_id):
    rng=np.random.default_rng(np.random.SeedSequence([seed,fixture_id,player_id,57721]) if seed is not None else None)
    return rng.binomial(3,expected_bonus(model,position,minutes,components)/3)
