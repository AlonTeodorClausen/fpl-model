"""One-GW new-squad optimization, separate from forecasts. No transfers or chips."""
from collections import Counter
from itertools import combinations
import numpy as np
from scipy.optimize import Bounds, LinearConstraint, milp
from scipy.sparse import lil_matrix

COUNTS = {1:2,2:5,3:5,4:3}
MINIMUM = {1:1,2:3,3:2,4:1}
MAXIMUM = {1:1,2:5,3:5,4:3}


def validate_squad(team, rows, *, budget, locked=(), excluded=()):
    by_id = {r['player_id']:r for r in rows}
    squad, xi, bench = team['squad'],team['starters'],team['bench']
    if len(squad)!=15 or len(set(squad))!=15 or len(xi)!=11 or len(set(xi))!=11 or len(bench)!=4 or set(xi)&set(bench) or set(xi+bench)!=set(squad):
        raise ValueError('Invalid squad/lineup/bench')
    if Counter(by_id[i]['position'] for i in squad) != COUNTS: raise ValueError('Invalid squad positions')
    formation = Counter(by_id[i]['position'] for i in xi)
    if any(not MINIMUM[p]<=formation[p]<=MAXIMUM[p] for p in COUNTS): raise ValueError('Invalid formation')
    if max(Counter(by_id[i]['team_id'] for i in squad).values())>3: raise ValueError('Club limit')
    if sum(by_id[i]['price'] for i in squad)>round(budget*10): raise ValueError('Budget exceeded')
    if any(not by_id[i].get('can_select',True) for i in squad): raise ValueError('Unselectable player')
    if not set(locked)<=set(squad) or set(excluded)&set(squad): raise ValueError('Lock/exclude violation')
    if team['captain'] not in xi or team['vice_captain'] not in xi or team['captain']==team['vice_captain']:
        raise ValueError('Invalid captain/vice')
    if by_id[bench[0]]['position']!=1: raise ValueError('Bench goalkeeper must be first')


def optimize_squad(rows, *, budget=100., locked=(), excluded=(), bench_weight=.1, time_limit=30):
    rows = sorted(rows,key=lambda r:r['player_id']); n=len(rows)
    ids = {r['player_id'] for r in rows}
    if n != len(ids) or n<15 or not np.isfinite(budget) or budget<=0 or not 0<=bench_weight<=1:
        raise ValueError('Invalid optimization inputs')
    if set(locked)&set(excluded) or not (set(locked)|set(excluded))<=ids: raise ValueError('Unknown or conflicting locks/exclusions')
    if any(r.get('price') is None or r['price']<=0 or not np.isfinite(r['xp']) for r in rows):
        raise ValueError('Explicit price and finite forecast required')
    xp=np.array([r['xp'] for r in rows]); cost=np.array([r['price'] for r in rows])
    # x=squad, y=XI, c=captain. Bench weight is an explicit objective approximation.
    objective=-np.concatenate([bench_weight*xp,(1-bench_weight)*xp,xp])
    constraints=[]; lo=[]; hi=[]
    def add(terms, lower, upper): constraints.append(terms);lo.append(lower);hi.append(upper)
    add({i:cost[i] for i in range(n)},0,round(budget*10))
    add({n+i:1 for i in range(n)},11,11)
    add({2*n+i:1 for i in range(n)},1,1)
    for pos,count in COUNTS.items():
        indices=[i for i,r in enumerate(rows) if r['position']==pos]
        add({i:1 for i in indices},count,count)
        add({n+i:1 for i in indices},MINIMUM[pos],MAXIMUM[pos])
    for club in sorted({r['team_id'] for r in rows}): add({i:1 for i,r in enumerate(rows) if r['team_id']==club},0,3)
    for i in range(n):
        add({n+i:1,i:-1},-np.inf,0);add({2*n+i:1,n+i:-1},-np.inf,0)
    lower=np.zeros(3*n);upper=np.ones(3*n)
    for i,r in enumerate(rows):
        if r['player_id'] in locked: lower[i]=1
        if r['player_id'] in excluded or not r.get('can_select',True): upper[i]=0
    if np.any(lower>upper): raise ValueError('Locked player cannot be selected')
    matrix=lil_matrix((len(constraints),3*n))
    for k,terms in enumerate(constraints):
        for i,value in terms.items(): matrix[k,i]=value
    result=milp(objective,integrality=np.ones(3*n),bounds=Bounds(lower,upper),
                constraints=LinearConstraint(matrix.tocsr(),lo,hi),options={'time_limit':time_limit,'mip_rel_gap':.0001})
    if result.x is None: raise ValueError('No legal squad found; relax locks, exclusions or budget')
    squad=[r['player_id'] for i,r in enumerate(rows) if result.x[i]>.5]
    xi=[r['player_id'] for i,r in enumerate(rows) if result.x[n+i]>.5]
    captain=next(r['player_id'] for i,r in enumerate(rows) if result.x[2*n+i]>.5)
    by_id={r['player_id']:r for r in rows}
    bench=sorted(set(squad)-set(xi),key=lambda i:(by_id[i]['position']!=1,-by_id[i]['xp'],i))
    vice=max((i for i in xi if i!=captain),key=lambda i:(by_id[i]['xp'],-i))
    team=dict(squad=squad,starters=xi,bench=bench,captain=captain,vice_captain=vice,
              cost=sum(by_id[i]['price'] for i in squad)/10,
              objective=float(-result.fun),bench_weight=bench_weight,solver_optimal=bool(result.success),
              mip_gap=float(result.mip_gap),expected_xi_captain=sum(by_id[i]['xp'] for i in xi)+by_id[captain]['xp'])
    validate_squad(team,rows,budget=budget,locked=locked,excluded=excluded)
    return team


def evaluate_squad(team, rows, points, participated):
    """Autosubs on scenario participation (including supplied card-only appearances).

    Missing players remain formation placeholders; not all XIs can be filled.
    """
    idx={r['player_id']:i for i,r in enumerate(rows)}
    positions={r['player_id']:r['position'] for r in rows}
    xi=team['starters']; bench=team['bench']
    points=np.asarray(points); active=np.asarray(participated,dtype=bool)
    if points.shape!=active.shape or points.shape[1]!=len(rows): raise ValueError('Scenario shape mismatch')
    xi_idx=[idx[i] for i in xi]
    total=(points[:,xi_idx]*active[:,xi_idx]).sum(axis=1).astype(float)
    contribution=np.zeros(len(points))
    relevant=xi+bench
    patterns,inverse=np.unique(active[:,[idx[i] for i in relevant]],axis=0,return_inverse=True)
    formation=Counter(positions[i] for i in xi)
    for k,pattern in enumerate(patterns):
        plays=dict(zip(relevant,pattern));selected=[]
        missing=[i for i in xi if not plays[i] and positions[i]!=1]
        goalkeeper=next(i for i in xi if positions[i]==1)
        if not plays[goalkeeper] and plays[bench[0]]: selected.append(bench[0])
        out=[]
        for substitute in bench[1:]:
            if not plays[substitute]: continue
            candidate=out+[substitute]
            possible=False
            for removed in combinations(missing,len(candidate)):
                counts=formation.copy()
                counts.subtract(positions[i] for i in removed);counts.update(positions[i] for i in candidate)
                if all(MINIMUM[p]<=counts[p]<=MAXIMUM[p] for p in COUNTS): possible=True;break
            if possible: out=candidate
        selected+=out
        mask=inverse==k
        if selected: contribution[mask]=points[np.ix_(mask,[idx[i] for i in selected])].sum(axis=1)
    cap,vice=idx[team['captain']],idx[team['vice_captain']]
    extra=np.where(active[:,cap],points[:,cap],np.where(active[:,vice],points[:,vice],0))
    return dict(points=total+contribution+extra,bench_points=contribution,captain_bonus=extra)
