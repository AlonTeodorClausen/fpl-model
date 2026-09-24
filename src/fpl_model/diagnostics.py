"""Read-only explanations of baseline v1; groups use prior labels, never targets."""
import numpy as np
from fpl_model.label_contracts import utc

DIAGNOSTICS_VERSION = 'explanations_minutes_v1'
REGULAR_RULE = 'At least 2 prior matches, mean minutes >= 60, played in >= 75% of prior matches.'


def history_summary(rows):
    """Observed frequencies, not inferred starts or a repaired missing-row denominator."""
    n=len(rows)
    times=sorted(r['kickoff_time'] for r in rows if r.get('kickoff_time'))
    starts_known=all(r.get('starts') in (0,1) for r in rows)
    return dict(matches=n,minutes=sum(r['minutes'] for r in rows),
        first_kickoff_at=times[0] if times else None,last_kickoff_at=times[-1] if times else None,
        events=sorted({r['event'] for r in rows}),
        mean_minutes=float(np.mean([r['minutes'] for r in rows])) if n else None,
        start_frequency=sum(r['starts'] for r in rows)/n if n and starts_known else None,
        sub_frequency=sum(r['minutes']>0 and r['starts']==0 for r in rows)/n if n and starts_known else None,
        dnp_frequency=sum(r['minutes']==0 for r in rows)/n if n else None,
        played_frequency=sum(r['minutes']>0 for r in rows)/n if n else None,
        starts_known=bool(n and starts_known))


def _group_metrics(rows):
    result=dict(n=len(rows),players=len({r['player_id'] for r in rows}))
    for label,key in [('model','predicted_minutes'),('reference','reference_minutes')]:
        errors=np.array([r[key]-r['actual_minutes'] for r in rows])
        result[label]=dict(bias=float(errors.mean()),mae=float(np.abs(errors).mean()),
                           rmse=float(np.sqrt(np.mean(errors**2)))) if len(rows) else None
    result['observed_minutes']=float(np.mean([r['actual_minutes'] for r in rows])) if rows else None
    result['model_minutes']=float(np.mean([r['predicted_minutes'] for r in rows])) if rows else None
    result['reference_minutes']=float(np.mean([r['reference_minutes'] for r in rows])) if rows else None
    for key in ('observed_start','observed_sub','model_start','model_sub','prior_mean_minutes'):
        values=[r[key] for r in rows if r[key] is not None]
        result[key]=float(np.mean(values)) if values else None
    return result


def minute_diagnostics(evaluation_rows, data, config):
    """Enrich existing evaluation predictions. No prediction or target is recomputed.

    Historical final rows are later-retrieved evidence, not proven as-of versions.
    Refuse unsafe denominators rather than inventing a history group.
    """
    from fpl_model.models.baseline import player_parameters
    from fpl_model.history_coverage import history_window
    records=[]
    for r in sorted(evaluation_rows,key=lambda r:(r['event'],r['player_id'])):
        deadline=utc(r['forecast_origin_at'])
        own=[h for h in data['histories'] if h['player_id']==r['player_id'] and h['label_state']=='final'
             and h['event']<r['event'] and utc(h['kickoff_time'])<deadline]
        team=max(own,key=lambda h:utc(h['kickoff_time']))['team_id'] if own else None
        past=[f for f in data['fixtures'] if f.get('finished') and f.get('kickoff_time')
              and (f.get('event') or 999)<r['event'] and utc(f['kickoff_time'])<deadline]
        coverage=history_window(own,past,team)
        if len(own)<2 or not coverage['usable']:
            raise ValueError('Evaluation row lacks a safe prior-history denominator')
        h=history_summary(own); start=h['start_frequency']; mean=h['mean_minutes']
        start_group=('unknown_starts' if start is None else 'never_started' if start==0
                     else 'occasional_starter' if start<.75 else 'regular_starter')
        minute_group='zero_minutes' if mean==0 else 'under_30' if mean<30 else '30_to_under_60' if mean<60 else '60_plus'
        regular=h['matches']>=2 and mean>=60 and h['played_frequency']>=.75
        par=player_parameters(dict(element_type=r['position']),own,len(own),config,allow_aggregates=False)
        records.append(dict(player_id=r['player_id'],event=r['event'],position=r['position'],
            forecast_origin_at=r['forecast_origin_at'],prior=h,start_group=start_group,minute_group=minute_group,
            regular=regular,actual_minutes=r['actual_minutes'],predicted_minutes=r['predicted_minutes'],
            reference_minutes=r['reference_minutes'],observed_start=start,observed_sub=h['sub_frequency'],
            model_start=par['p_start'],model_sub=par['p_sub'],prior_mean_minutes=mean))
    def grouped(key,rows):
        return [dict(group=g,**_group_metrics([r for r in rows if r[key]==g])) for g in sorted({r[key] for r in rows})]
    regular=[r for r in records if r['regular']]
    return dict(version=DIAGNOSTICS_VERSION,regular_rule=REGULAR_RULE,
        bias_definition='predicted - actual minutes; positive = overprediction; player-GW totals',
        start_group_rule='Never = 0%; occasional = >0% and <75%; regular = >=75%; unknown kept separate.',
        minute_group_rule='Prior mean minutes per observed fixture: 0, (0,30), [30,60), >=60.',
        scopes={'all':_group_metrics(records),'regular':_group_metrics(regular)},
        by_position=grouped('position',records),by_start_history=grouped('start_group',records),
        by_minute_history=grouped('minute_group',records),regular_by_position=grouped('position',regular),
        by_position_start_history=[dict(position=p,**g) for p in sorted({r['position'] for r in records})
            for g in grouped('start_group',[r for r in records if r['position']==p])],rows=records)
