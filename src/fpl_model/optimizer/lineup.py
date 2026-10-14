"""Exact fixed-squad lineup search on planning draws, including legal autosubs.

Captain/vice and goalkeeper choices separate from outfield bench ordering. Equal
participation patterns are aggregated without losing their point correlations.
No evaluation draws or per-scenario hindsight choices enter the search.
"""
from collections import Counter
from copy import deepcopy
from itertools import combinations, permutations
import numpy as np
from fpl_model.optimizer.squad import MINIMUM, MAXIMUM, COUNTS, evaluate_squad, validate_squad

VERSION='autosub_lineup_chips_v2'


def optimize_lineup(squad, rows, points, played, *, chip=None):
    from fpl_model.chips import CHIPS
    if chip not in (None,*CHIPS):raise ValueError('Ukendt chip.')
    ids=sorted(squad);lookup={r['player_id']:r for r in rows}
    if len(ids)!=15 or len(set(ids))!=15 or not set(ids)<=set(lookup):
        raise ValueError('Opstillingsvalg kræver 15 kendte, unikke spillere.')
    positions=np.array([lookup[i]['position'] for i in ids])
    if Counter(positions)!=COUNTS:raise ValueError('Ugyldige positioner i truppen.')
    points=np.asarray(points);played=np.asarray(played,dtype=bool)
    if points.shape!=played.shape or points.ndim!=2 or points.shape[1]!=len(rows) or not len(points) or not np.isfinite(points).all():
        raise ValueError('Ugyldige planlægningsscenarier.')
    index={r['player_id']:i for i,r in enumerate(rows)}
    ix=[index[i] for i in ids];active=played[:,ix];pts=points[:,ix]*active;n=len(pts)
    patterns,inverse=np.unique(active,axis=0,return_inverse=True)
    totals=np.zeros((len(patterns),15));np.add.at(totals,inverse,pts)
    means=pts.mean(axis=0)
    # Additional captain points, with vice only when captain has no appearance.
    bonus=np.array([[np.where(active[:,c],pts[:,c],pts[:,v]).mean()
                     for v in range(15)] for c in range(15)])
    if chip=='triple_captain':bonus*=2
    np.fill_diagonal(bonus,-np.inf)
    keepers=np.flatnonzero(positions==1).tolist();outfield=np.flatnonzero(positions!=1).tolist()
    minimum=np.array([MINIMUM[p] for p in (2,3,4)])
    maximum=np.array([MAXIMUM[p] for p in (2,3,4)])
    best=None;best_score=-np.inf;searched=0
    for bench_set in combinations(outfield,3):
        xi_out=[i for i in outfield if i not in bench_set]
        formation=np.array([sum(positions[i]==p for i in xi_out) for p in (2,3,4)])
        if np.any(formation<minimum) or np.any(formation>maximum):continue
        missing=np.stack([(~patterns[:,[i for i in xi_out if positions[i]==p]]).sum(axis=1) for p in (2,3,4)],axis=1)
        bench_best=-np.inf;order_best=None
        for order in permutations(bench_set):
            added=np.zeros_like(missing);count=np.zeros(len(patterns),dtype=int);contribution=0.
            for sub in order:
                candidate=added.copy();candidate[:,positions[sub]-2]+=1
                lower=np.maximum(0,formation+candidate-maximum)
                upper=np.minimum(missing,formation+candidate-minimum)
                feasible=(patterns[:,sub] & np.all(upper>=lower,axis=1)
                          & (lower.sum(axis=1)<=count+1) & (upper.sum(axis=1)>=count+1))
                added[feasible]=candidate[feasible];count+=feasible
                contribution+=totals[feasible,sub].sum()/n
            if contribution>bench_best+1e-12:bench_best=contribution;order_best=order
        for gk in keepers:
            reserve=next(i for i in keepers if i!=gk);xi=sorted(xi_out+[gk])
            cap_values=bonus[np.ix_(xi,xi)];c,v=np.unravel_index(np.argmax(cap_values),cap_values.shape)
            cap,vice=xi[c],xi[v]
            gk_sub=totals[~patterns[:,gk],reserve].sum()/n
            bench_value=means[list(order_best)+[reserve]].sum() if chip=='bench_boost' else bench_best+gk_sub
            score=means[xi].sum()+bonus[cap,vice]+bench_value
            searched+=6
            if score>best_score+1e-12:
                best_score=score
                best=dict(squad=ids,starters=[ids[i] for i in xi],bench=[ids[reserve]]+[ids[i] for i in order_best],
                          captain=ids[cap],vice_captain=ids[vice],objective=float(score),
                          chip=chip,planning_bench_points=float(bench_value),planning_captain_bonus=float(bonus[cap,vice]),
                          expected_xi_captain=float(means[xi].sum()+bonus[cap,vice]))
    if best is None:raise ValueError('Ingen lovlig opstilling.')
    best['lineup_search']=dict(version=VERSION,exhaustive=True,lineups=searched,
                               scope='fixed_squad_planning_scenarios',captain_vice='all_legal_pairs')
    validate_squad(best,[dict(r,can_select=True) for r in rows],budget=sum(lookup[i]['price'] for i in ids)/10)
    # Independent implementation is also the scoring oracle for the chosen XI.
    evaluated=evaluate_squad(best,rows,points,played,chip=chip)
    if not np.isclose(best['objective'],evaluated['points'].mean(),atol=1e-9,rtol=0):
        raise RuntimeError('Opstillingens autosub-målværdi kunne ikke valideres.')
    return best


def refine_plan(plan,bundle,cache):
    if 'planning_scenarios' not in bundle:
        raise ValueError('Mangler separate scenarier til planlægning; genberegn prognosecache.')
    plan['candidate_objective']=plan['objective']
    plan['candidate_lineups']=deepcopy(plan['lineups'])
    plan['lineup_policy']=VERSION
    for event,lineup in list(plan['lineups'].items()):
        e=int(event);chip=next((s.get('chip') for s in plan.get('steps',[]) if s['event']==e),None)
        key=(e,tuple(sorted(lineup['squad'])),chip)
        if key not in cache:
            s=bundle['planning_scenarios'][e]
            cache[key]=optimize_lineup(lineup['squad'],bundle['rows'][e],s['points'],s['played'],chip=chip)
        plan['lineups'][event]=deepcopy(cache[key])
        s=bundle['planning_scenarios'][e]
        previous=evaluate_squad(lineup,bundle['rows'][e],s['points'],s['played'],chip=chip)
        plan['lineups'][event]['previous_planning_points']=float(previous['points'].mean())
    plan['objective']=sum(l['objective'] for l in plan['lineups'].values())-plan['hits']
