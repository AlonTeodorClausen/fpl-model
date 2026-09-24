"""Small retrospective diagnostic, explicitly NOT a prospective backtest."""
import copy
import numpy as np
from fpl_model.label_contracts import utc
from fpl_model.simulation import simulate


def evaluate_sample(data, config, *, draws=1000, seed=42):
    final=[r for r in data['histories'] if r['label_state']=='final']
    records=[]
    for event in sorted({r['event'] for r in final}):
        deadline=utc(next(e['deadline_time'] for e in data['events'] if e['id']==event))
        past=[r for r in final if r['event']<event and utc(r['kickoff_time'])<deadline]
        targets=[r for r in final if r['event']==event and sum(p['player_id']==r['player_id'] for p in past)>=2]
        if not targets: continue
        ids=sorted({r['player_id'] for r in targets})
        run=copy.deepcopy(data)
        by_id={p['id']:p for p in data['players']}
        run['players']=[dict(id=i,element_type=by_id[i]['element_type'],team=max(
            (r for r in past if r['player_id']==i),key=lambda r:utc(r['kickoff_time']))['team_id']) for i in ids]
        run['histories']=past
        scenario=simulate(run,event,config,draws=draws,seed=seed+event,retrospective=True)
        for i,pid in enumerate(ids):
            own_targets=[r for r in targets if r['player_id']==pid]
            observed=[r for r in data['histories'] if r['event']==event and r['player_id']==pid]
            scheduled=[f for f in data['fixtures'] if f.get('event')==event and run['players'][i]['team'] in (f['team_h'],f['team_a'])]
            if any(r['label_state']!='final' for r in observed) or {r['fixture_id'] for r in own_targets}!={f['id'] for f in scheduled}: continue
            actual=sum(r['total_points'] for r in own_targets)
            reference=np.mean([r['total_points'] for r in past if r['player_id']==pid])*len(own_targets)
            samples=scenario.points[:,i].astype(float);ordered=np.sort(samples);n=len(samples)
            crps=np.abs(samples-actual).mean()-np.sum((2*np.arange(1,n+1)-n-1)*ordered)/(n*n)
            records.append(dict(event=event,player_id=pid,actual=actual,predicted=float(samples.mean()),
                                reference=float(reference),crps=float(crps),prior_rows=sum(r['player_id']==pid for r in past)))
    def metrics(key):
        errors=np.array([r[key]-r['actual'] for r in records])
        return dict(mae=float(np.abs(errors).mean()),rmse=float(np.sqrt((errors**2).mean())))
    return dict(status='retrospective_limited' if records else 'insufficient_data',n=len(records),rows=records,
                model={**metrics('predicted'),'crps':float(np.mean([r['crps'] for r in records]))} if records else None,
                reference=metrics('reference') if records else None,
                limitations=['Small nonrepresentative captured sample; diagnostic only.',
                             'Historical final-row revisions retrieved later; availability at old deadlines not proven.',
                             'Position and fixture schedule are captured current versions; team context comes from official labels.',
                             'Only earlier GWs/kickoffs used; no current season aggregates, injury news or odds in historical inputs.',
                             'Missing rows are not DNP; incomplete/moved fixture sets are excluded.'])
