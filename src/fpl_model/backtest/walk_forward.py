"""Chronological diagnostic on later-captured official labels, NOT prospective."""
from collections import Counter
from dataclasses import asdict
import numpy as np

from fpl_model.label_contracts import utc
from fpl_model.history_coverage import history_window
from fpl_model.simulation import simulate
from fpl_model.diagnostics import minute_diagnostics

MODEL_VERSION='component_baseline_v1'
EVALUATION_VERSION='chronological_coverage_v2'


def _errors(actual, predicted):
    error=np.asarray(predicted)-np.asarray(actual)
    return dict(mae=float(np.abs(error).mean()),rmse=float(np.sqrt((error**2).mean())))


def _metrics(rows):
    if not rows: return dict(n=0,model=None,reference=None,minutes=None,dnp=None)
    actual=[r['actual'] for r in rows]
    minutes={**_errors([r['actual_minutes'] for r in rows],[r['predicted_minutes'] for r in rows]),
             'n':len(rows),'reference':_errors([r['actual_minutes'] for r in rows],[r['reference_minutes'] for r in rows])}
    dnp=dict(n=len(rows),brier=float(np.mean([(r['p_no_play']-r['actual_dnp'])**2 for r in rows])),
             reference_brier=float(np.mean([(r['reference_dnp']-r['actual_dnp'])**2 for r in rows])),
             observed_rate=float(np.mean([r['actual_dnp'] for r in rows])),
             predicted_rate=float(np.mean([r['p_no_play'] for r in rows])))
    return dict(n=len(rows),model={**_errors(actual,[r['predicted'] for r in rows]),
                                    'crps':float(np.mean([r['crps'] for r in rows]))},
                reference=_errors(actual,[r['reference'] for r in rows]),minutes=minutes,dnp=dnp)


def evaluate_sample(data, config, *, draws=1000, seed=42):
    """Keep baseline v1; compare identical, explicitly observed final player-GWs.

    Rows with unsafe prior denominators are excluded, not imputed or scored as
    DNP. This selection intentionally excludes many transfers/new registrations.
    """
    final=[r for r in data['histories'] if r['label_state']=='final']
    records=[];excluded=[]
    by_id={p['id']:p for p in data['players']}
    for event in sorted({r['event'] for r in final}):
        deadline=utc(next(e['deadline_time'] for e in data['events'] if e['id']==event))
        past=[r for r in final if r['event']<event and utc(r['kickoff_time'])<deadline]
        prior_fixtures=[f for f in data['fixtures'] if f.get('finished') and f.get('kickoff_time')
            and (f.get('event') or 999)<event and utc(f['kickoff_time'])<deadline]
        selected=[];targets={};priors={}
        for pid in sorted(by_id):
            own=[r for r in past if r['player_id']==pid]
            reason=None
            if len(own)<2:
                reason='insufficient_prior_rows'
            else:
                team=max(own,key=lambda r:utc(r['kickoff_time']))['team_id']
                coverage=history_window(own,prior_fixtures,team)
                if not coverage['usable']:
                    reason='incomplete_prior_history' if coverage['state']!='unresolved_team_membership' else coverage['state']
                observed=[r for r in data['histories'] if r['event']==event and r['player_id']==pid]
                scheduled=[f for f in data['fixtures'] if f.get('event')==event and team in (f['team_h'],f['team_a'])]
                if reason is None and (not observed or not scheduled or any(r['label_state']!='final' for r in observed)
                    or len(observed)!=len(scheduled) or {r['fixture_id'] for r in observed}!={f['id'] for f in scheduled}):
                    reason='missing_provisional_or_moved_target'
                if reason is None:
                    selected.append(dict(id=pid,element_type=by_id[pid]['element_type'],team=team))
                    targets[pid]=observed;priors[pid]=own
            if reason: excluded.append(dict(player_id=pid,event=event,reason=reason))
        if not selected: continue
        # Shallow context copy: model is read-only; avoid copying every raw history
        # and its provenance for every fold of the complete player pool.
        run={**data,'players':selected,'histories':past}
        scenario=simulate(run,event,config,draws=draws,seed=seed+event,retrospective=True)
        for i,p in enumerate(selected):
            pid=p['id'];own=priors[pid];target=targets[pid];count=len(target)
            actual=sum(r['total_points'] for r in target);minutes=sum(r['minutes'] for r in target)
            samples=scenario.points[:,i].astype(float);ordered=np.sort(samples);n=len(samples)
            crps=np.abs(samples-actual).mean()-np.sum((2*np.arange(1,n+1)-n-1)*ordered)/(n*n)
            records.append(dict(event=event,player_id=pid,position=p['element_type'],
                fixture_ids=sorted(r['fixture_id'] for r in target),forecast_origin_at=deadline.isoformat(),
                actual=actual,predicted=float(samples.mean()),reference=float(np.mean([r['total_points'] for r in own])*count),
                actual_minutes=minutes,predicted_minutes=float(scenario.minutes[:,i].mean()),
                reference_minutes=float(np.mean([r['minutes'] for r in own])*count),
                actual_dnp=int(minutes==0),p_no_play=float((scenario.minutes[:,i]==0).mean()),
                reference_dnp=float(np.mean([r['minutes']==0 for r in own])**count),
                crps=float(crps),prior_rows=len(own)))
    summary=_metrics(records)
    if records:
        bins=[]
        for k in range(10):
            subset=[r for r in records if min(int(r['p_no_play']*10),9)==k]
            bins.append(dict(lower=k/10,upper=(k+1)/10,n=len(subset),
                predicted_rate=float(np.mean([r['p_no_play'] for r in subset])) if subset else None,
                observed_rate=float(np.mean([r['actual_dnp'] for r in subset])) if subset else None))
        summary['dnp']['bins']=bins
    return dict(**summary,status='retrospective_limited' if records else 'insufficient_data',
        evaluation_version=EVALUATION_VERSION,model_version=MODEL_VERSION,
        config=asdict(config),draws=draws,seed=seed,snapshot_id=data['snapshot_id'],
        manifest_sha256=data.get('manifest_sha256'),player_count=len({r['player_id'] for r in records}),
        gameweeks=sorted({r['event'] for r in records}),rows=records,
        minute_diagnostics=minute_diagnostics(records,data,config),
        by_position=[dict(position=p,**_metrics([r for r in records if r['position']==p])) for p in sorted({r['position'] for r in records})],
        by_gameweek=[dict(event=e,**_metrics([r for r in records if r['event']==e])) for e in sorted({r['event'] for r in records})],
        excluded=excluded,excluded_counts=dict(sorted(Counter(r['reason'] for r in excluded).items())),
        limitations=['Current player pool and conservative complete-history selection cause survivorship/coverage bias.',
            'Historical final-row revisions retrieved later; availability at old deadlines not proven. Not a prospective test.',
            'Position and fixture schedule are captured current versions; team context comes only from prior official labels.',
            'Only earlier GWs/kickoffs used; no current season aggregates, injury news or odds in historical inputs.',
            'No DNP from absence: incomplete prior histories, transfer uncertainty and incomplete/provisional targets excluded.',
            'Minutes diagnostics are player-GW totals; DNP means explicitly zero minutes across all observed GW fixtures.',
            'Reference minutes/points use prior per-match means times GW fixtures; reference DNP assumes independent fixtures.'])
