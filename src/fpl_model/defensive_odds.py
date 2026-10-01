"""Optional Bet365 defensive goal-rate overlay; never an offensive-rate input.

London local times and aliases are checked against exact official kickoffs.
Evidence and limitations: notes/defensive_odds.md. No fuzzy matching or nearest time.
"""
import csv
from datetime import datetime, timezone
import io
import math
from zoneinfo import ZoneInfo
import numpy as np
from scipy.optimize import least_squares
from scipy.stats import poisson, skellam
from fpl_model.label_contracts import utc
from fpl_model.models.baseline import fixture_goal_means

MODEL_VERSION='component_defensive_odds_v1'
COLUMNS=('B365H','B365D','B365A','B365>2.5','B365<2.5')
PROB_KEYS=('home','draw','away','over25','under25')
ALIASES={'Coventry':'Coventry City','Hull':'Hull City','Ipswich':'Ipswich Town',
         'Man United':'Man Utd','Tottenham':'Spurs'}
MAX_FIT_ERROR=.06 # Operational rejection threshold, not a calibrated statistical bound.


def read_csv(body):
    try: text=body.decode('utf-8-sig')
    except UnicodeDecodeError: text=body.decode('cp1252')
    return list(csv.DictReader(io.StringIO(text)))


def remove_margin(prices):
    odds=np.asarray(prices,dtype=float)
    if not len(odds) or not np.all(np.isfinite(odds)) or np.any(odds<=1):
        raise ValueError('Invalid decimal odds')
    inverse=1/odds
    return (inverse/inverse.sum()).tolist(),float(inverse.sum()-1)


def goal_probabilities(home,away):
    if not all(math.isfinite(v) and v>0 for v in (home,away)): raise ValueError('Positive finite goal rates required')
    under=float(poisson.cdf(2,home+away))
    return dict(home=float(skellam.sf(0,home,away)),draw=float(skellam.pmf(0,home,away)),
                away=float(skellam.cdf(-1,home,away)),over25=1-under,under25=under)


def fit_market(row):
    try:
        prices={k:float(row[k]) for k in COLUMNS}
        one,margin_one=remove_margin([prices[k] for k in COLUMNS[:3]])
        totals,margin_totals=remove_margin([prices[k] for k in COLUMNS[3:]])
    except (KeyError,TypeError,ValueError): raise ValueError('missing_or_invalid_bet365_market') from None
    market=dict(zip(PROB_KEYS,one+totals))
    def residual(log_rates):
        fitted=goal_probabilities(*np.exp(log_rates))
        return [fitted[k]-market[k] for k in PROB_KEYS]
    # Fixed initial guess/bounds, no parameter search. Equal weight for five quoted outcomes.
    fit=least_squares(residual,np.log([1.5,1.2]),bounds=(np.log([.05,.05]),np.log([6.,6.])),
                      max_nfev=200,ftol=1e-10,xtol=1e-10,gtol=1e-10)
    h,a=map(float,np.exp(fit.x));errors=residual(fit.x)
    if not fit.success or max(map(abs,errors))>MAX_FIT_ERROR or min(h,a)<=.050001 or max(h,a)>=5.99999:
        raise ValueError('poisson_fit_rejected')
    return dict(home_goals=h,away_goals=a,home_clean_sheet=math.exp(-a),away_clean_sheet=math.exp(-h),
        prices=prices,columns=list(COLUMNS),market_probabilities=market,model_probabilities=goal_probabilities(h,a),
        probability_errors=dict(zip(PROB_KEYS,errors)),max_probability_error=max(map(abs,errors)),
        margins={'1x2':margin_one,'over_under25':margin_totals},
        method='Independent Poisson; least squares on five normalized probabilities; log rates in [0.05,6]; max error <=0.06')


def local_kickoff(date,time):
    naive=None
    for fmt in ('%d/%m/%Y %H:%M','%d/%m/%y %H:%M'):
        try: naive=datetime.strptime(date+' '+time,fmt);break
        except ValueError: pass
    if naive is None: raise ValueError('Invalid date/time')
    zone=ZoneInfo('Europe/London');a=naive.replace(tzinfo=zone,fold=0);b=naive.replace(tzinfo=zone,fold=1)
    if a.utcoffset()!=b.utcoffset() or a.astimezone(timezone.utc).astimezone(zone).replace(tzinfo=None)!=naive:
        raise ValueError('Ambiguous/nonexistent local time')
    return a.astimezone(timezone.utc)


def match_fixture(row,teams,fixtures):
    if row.get('Div')!='E0': return dict(status='not_premier_league')
    ids=[]
    for field in ('HomeTeam','AwayTeam'):
        name=ALIASES.get(row.get(field),row.get(field))
        found=[t['id'] for t in teams if t['name']==name]
        if len(found)!=1:return dict(status='unknown_or_ambiguous_team')
        ids.append(found[0])
    try: kickoff=local_kickoff(row.get('Date',''),row.get('Time',''))
    except (ValueError,TypeError):return dict(status='invalid_kickoff')
    matches=[f for f in fixtures if (f['team_h'],f['team_a'])==tuple(ids)
             and f.get('kickoff_time') and utc(f['kickoff_time'])==kickoff]
    if len(matches)!=1:return dict(status='ambiguous_fixture' if matches else 'no_exact_official_kickoff')
    return dict(status='matched',fixture_id=matches[0]['id'],kickoff_utc=kickoff.isoformat(),timezone_policy='Europe/London')


def build_coverage(data,rows,source,event,config,forecast_origin_at):
    origin=utc(forecast_origin_at)
    deadline=utc(next(e['deadline_time'] for e in data['events'] if e['id']==event))
    pl=[r for r in rows if r.get('Div')=='E0']
    matches=[dict(row_index=i,home=r.get('HomeTeam'),away=r.get('AwayTeam'),
                  **match_fixture(r,data['teams'],data['fixtures'])) for i,r in enumerate(pl)]
    past=[f for f in data['fixtures'] if f.get('finished') and f.get('kickoff_time') and utc(f['kickoff_time'])<origin]
    temporal_reason=None
    try:
        available=utc(source['available_at']);retrieved=utc(source['retrieved_at'])
        if available<retrieved:temporal_reason='invalid_time_provenance'
        elif available>origin:temporal_reason='odds_after_forecast_origin'
        elif available>=deadline:temporal_reason='odds_not_before_deadline'
    except (ValueError,KeyError,TypeError):temporal_reason='missing_time_provenance'
    result=[]
    for fixture in sorted((f for f in data['fixtures'] if f.get('event')==event),key=lambda f:f['id']):
        h,a=fixture_goal_means(fixture,past,config)
        entry=dict(fixture_id=fixture['id'],team_h=fixture['team_h'],team_a=fixture['team_a'],
            kickoff_time=fixture.get('kickoff_time'),baseline_home_goals=h,baseline_away_goals=a,
            baseline_home_clean_sheet=math.exp(-a),baseline_away_clean_sheet=math.exp(-h),
            home_goals=h,away_goals=a,home_clean_sheet=math.exp(-a),away_clean_sheet=math.exp(-h),
            status='baseline_fallback',reason=None)
        matching=[m for m in matches if m.get('fixture_id')==fixture['id']]
        reason=source.get('failure') or temporal_reason
        if not reason:
            if not pl:reason='no_premier_league_rows'
            elif not matching:reason='no_exact_fixture_market'
            elif len(matching)>1:reason='duplicate_fixture_markets'
        if not reason:
            row=pl[matching[0]['row_index']]
            try:
                fit=fit_market(row)
                entry.update(fit,status='odds',csv_row=matching[0]['row_index'],kickoff_match=matching[0])
            except (ValueError,RuntimeError,FloatingPointError) as exc:
                reason=str(exc) if isinstance(exc,ValueError) else 'poisson_fit_failed'
        entry['reason']=reason;result.append(entry)
    return dict(event=event,forecast_origin_at=origin.isoformat(),deadline_at=deadline.isoformat(),
        source=source,policy='Bet365 only: '+', '.join(COLUMNS),source_published_at=None,
        total_source_rows=len(rows),premier_league_rows=len(pl),usable=sum(f['status']=='odds' for f in result),
        expected_fixtures=len(result),fixtures=result,matches=matches,
        timezone_policy='Europe/London, empirically verified; require exact UTC FPL kickoff; reject DST ambiguity')


def eligible_overrides(coverage,event,origin,deadline,fixtures):
    if coverage['event']!=event or utc(coverage['forecast_origin_at'])!=origin or utc(coverage['deadline_at'])!=deadline:
        raise ValueError('Odds context differs from forecast/deadline')
    out={}
    for f in coverage['fixtures']:
        if f['status']!='odds':continue
        matched=[row for row in fixtures if row['id']==f['fixture_id'] and row.get('event')==event]
        if len(matched)!=1 or any(matched[0][key]!=f[key] for key in ('team_h','team_a','kickoff_time')):
            raise ValueError('Official fixture context changed; rematch odds')
        source=coverage['source'];available=utc(source['available_at'])
        if utc(source['retrieved_at'])>available or available>origin or available>=deadline:
            raise ValueError('Odds outside permitted forecast/deadline boundary')
        if f['fixture_id'] in out:raise ValueError('Duplicate odds override')
        rates=(f['home_goals'],f['away_goals'])
        if not all(math.isfinite(x) and x>0 for x in rates):raise ValueError('Invalid odds goal rates')
        out[f['fixture_id']]=rates
    return out
