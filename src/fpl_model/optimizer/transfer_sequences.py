"""Deterministic open-loop transfer plans: one squad/bank/FT state per GW.

All forecasts are supplied at one origin. No hindsight or future prices. Manually scheduled chips use explicit state transitions.
The MILP jointly optimizes all weeks; it does not pick transfers inside scenarios.
"""
import math
import numpy as np
from scipy.optimize import Bounds, LinearConstraint, milp
from scipy.sparse import lil_matrix

from fpl_model.chips import REBUILDS, validate_chip_plan, resolve_chip_origin, chip_transfer_account
from fpl_model.my_team import validate_profile
from fpl_model.optimizer.squad import COUNTS, MINIMUM, MAXIMUM, validate_squad
from fpl_model.optimizer.transfers import NoTransferSolution


def optimize_sequence(rows_by_event, profile, *, first_count=0, max_per_gw=2,
                      max_total=4, locked=(), excluded=(), allow_hits=False,
                      bench_weight=.1, time_limit=30, chip_plan=None, chip_context=None):
    events=sorted(rows_by_event)
    if not 1<=len(events)<=4 or events!=list(range(events[0],events[0]+len(events))):
        raise ValueError('Vælg 1–4 sammenhængende GWs.')
    chip_plan=chip_plan or {}
    if chip_plan:
        if chip_context is None:raise ValueError('Chipplan kræver deadline og prognosetidspunkt.')
        chip_plan=validate_chip_plan(chip_plan,profile,events,**chip_context)
    first_chip=chip_plan.get(events[0]);rebuild=first_chip in REBUILDS
    lockable={r['player_id'] for r in profile['players']}
    profile=resolve_chip_origin(profile,first_chip)
    for v,maximum in ((max_per_gw,15),(max_total,60)):
        if type(v) is not int or not 0<=v<=maximum:raise ValueError('Ugyldig transfergrænse.')
    if first_count is None and not rebuild:raise ValueError('Fri omlægning kræver WC/FH.')
    if first_count is not None and (type(first_count) is not int or not 0<=first_count<=15):raise ValueError('Ugyldig transfergrænse.')
    if not rebuild and first_count>min(max_per_gw,max_total,20-profile['transfers_made']):
        raise NoTransferSolution('Transfergrænsen tillader ikke dette antal nu.')
    if not rebuild and not allow_hits and first_count>profile['free_transfers']:
        raise NoTransferSolution('Dette antal transfers nu kræver pointfradrag.')
    if not math.isfinite(time_limit) or time_limit<=0 or not math.isfinite(bench_weight) or not 0<=bench_weight<=1:
        raise ValueError('Ugyldig solver-/bænkindstilling.')
    tables={e:sorted(rows_by_event[e],key=lambda r:r['player_id']) for e in events}
    rows=tables[events[0]]; n=len(rows); ids=[r['player_id'] for r in rows]
    if n<15 or len(set(ids))!=n:raise ValueError('Ugyldig spillerpulje.')
    identity=lambda r:tuple(r.get(k) for k in ('player_id','price','position','team_id','can_select'))
    for table in tables.values():
        if [identity(r) for r in table]!=[identity(r) for r in rows]:
            raise ValueError('Identiteter og priser skal være faste gennem horisonten.')
        if any(not math.isfinite(r['xp']) or type(r['price']) is not int or r['price']<=0 for r in table):
            raise ValueError('Ugyldige prognoser/priser.')
    validate_profile(profile,[dict(id=r['player_id'],team=r['team_id'],element_type=r['position'],now_cost=r['price']) for r in rows],season=profile['season'])
    sales={p['player_id']:p['selling_price'] for p in profile['players']}; owned=set(sales)
    if not set(locked)<=lockable or not set(excluded)<=set(ids) or set(locked)&set(excluded):
        raise ValueError('Ukendte eller modstridende behold/udeluk-valg.')
    objective=[]; lower=[]; upper=[]
    def variables(count, high=1):
        out=np.arange(len(objective),len(objective)+count)
        objective.extend([0.]*count);lower.extend([0.]*count);upper.extend([high]*count)
        return out
    weeks=[]
    for g in events:
        weeks.append({key:variables(n) for key in ('x','buy','sell','original','active_original','permanent','xi','captain')})
    banks=variables(len(events),profile['bank']+sum(r['price'] for r in rows))
    permanent_banks=variables(len(events),profile['bank']+sum(r['price'] for r in rows))
    transitions=[]
    for t,event in enumerate(events):
        chip=chip_plan.get(event);limit=15 if chip in REBUILDS else max_per_gw
        edges=[(f,k,chip_transfer_account(f,k,chip)['next_gw']) for f in range(6) for k in range(limit+1)
               if (chip in REBUILDS or allow_hits or k<=f)
               and (t or (f==profile['free_transfers'] and (first_count is None or k==first_count)))]
        indices=variables(len(edges));transitions.append(list(zip(indices,edges)))
        for j,(f,k,_) in transitions[-1]:objective[j]=chip_transfer_account(f,k,chip)['hits']
    constraints=[];low=[];high=[]
    def add(terms,lo,hi=None):
        constraints.append(terms);low.append(lo);high.append(lo if hi is None else hi)
    add({int(i):1 for e,w in zip(events,weeks) if chip_plan.get(e) not in REBUILDS for i in w['buy']},0,max_total)
    for t,event in enumerate(events):
        w=weeks[t]; prev=weeks[t-1] if t else None; table=tables[event]
        chip=chip_plan.get(event);temporary=chip=='free_hit'
        if temporary:
            add({int(permanent_banks[t]):1,**({int(permanent_banks[t-1]):-1} if t else {})},0 if t else profile['bank'])
        else:add({int(permanent_banks[t]):1,int(banks[t]):-1},0)
        add({int(j):1 for j,_ in transitions[t]},1)
        add({**{int(i):1 for i in w['buy']},**{int(j):-k for j,(_,k,_) in transitions[t]}},0)
        if t:
            for f in range(6):
                add({**{int(j):1 for j,(a,_,_) in transitions[t] if a==f},
                     **{int(j):-1 for j,(_,_,b) in transitions[t-1] if b==f}},0)
        cash={int(banks[t]):1}
        if t:cash[int(permanent_banks[t-1])]=-1
        for i,r in enumerate(rows):
            pid=r['player_id']; initial=int(pid in owned)
            x,b,s,o,y,c=(int(w[k][i]) for k in ('x','buy','sell','active_original','xi','captain'))
            balance={x:1,b:-1,s:1}
            if t:balance[int(prev['permanent'][i])]=-1
            add(balance,0 if t else initial)
            add({b:1,s:1},0,1)  # no same-week buy/sell or phantom cash
            permanent=int(w['permanent'][i]);lot=int(w['original'][i])
            if temporary:
                add({permanent:1,**({int(prev['permanent'][i]):-1} if t else {})},0 if t else initial)
                add({lot:1,**({int(prev['original'][i]):-1} if t else {})},0 if t else initial)
            else:
                add({permanent:1,x:-1},0);add({lot:1,o:-1},0)
            # Original acquisition lot survives only until its first sale.
            survival={o:1,s:1}
            if t:
                op=int(prev['original'][i]);survival[op]=-1
                add({o:1,op:-1},-np.inf,0)
            else:upper[o]=initial
            add(survival,0 if t else initial,np.inf)
            add({o:1,x:-1},-np.inf,0)
            # Cash = previous bank + market sales - original-lot discount - buys.
            discount=r['price']-sales.get(pid,r['price'])
            cash[b]=r['price'];cash[s]=-r['price'];cash[o]=-discount
            if t:cash[int(prev['original'][i])]=discount
            weight=1 if chip=='bench_boost' else bench_weight
            objective[x]=-weight*table[i]['xp']
            objective[y]=-(1-weight)*table[i]['xp'];objective[c]=-(2 if chip=='triple_captain' else 1)*table[i]['xp']
            add({y:1,x:-1},-np.inf,0);add({c:1,y:-1},-np.inf,0)
            if pid in locked:lower[x]=1
            if pid in excluded:upper[x]=0
            if not r.get('can_select',True):upper[b]=0
        add(cash,0 if t else profile['bank']-sum(r['price']-sales[r['player_id']] for r in rows if r['player_id'] in owned))
        add({int(i):1 for i in w['xi']},11);add({int(i):1 for i in w['captain']},1)
        for pos,count in COUNTS.items():
            ix=[i for i,r in enumerate(rows) if r['position']==pos]
            add({int(w['x'][i]):1 for i in ix},count)
            add({int(w['xi'][i]):1 for i in ix},MINIMUM[pos],MAXIMUM[pos])
        for club in sorted({r['team_id'] for r in rows}):
            add({int(w['x'][i]):1 for i,r in enumerate(rows) if r['team_id']==club},0,3)
    matrix=lil_matrix((len(constraints),len(objective)))
    for k,terms in enumerate(constraints):
        for i,v in terms.items():matrix[k,i]=v
    result=milp(np.array(objective),integrality=np.ones(len(objective)),bounds=Bounds(lower,upper),
                constraints=LinearConstraint(matrix.tocsr(),low,high),
                options={'time_limit':time_limit,'mip_rel_gap':.0001})
    if result.x is None:
        raise NoTransferSolution('Ingen lovlig plan fundet' if result.status==2 else 'Ingen plan fundet inden solverens tidsgrænse.')
    pool={r['player_id']:r for r in rows}; current=set(owned); remaining_original=set(owned)
    bank=profile['bank'];free=profile['free_transfers'];steps=[];lineups={}
    for t,event in enumerate(events):
        w=weeks[t];lookup={r['player_id']:r for r in tables[event]}
        selected=lambda key:[ids[i] for i in range(n) if result.x[w[key][i]]>.5]
        squad=selected('x');incoming=sorted(set(squad)-current);outgoing=sorted(current-set(squad));k=len(incoming)
        proceeds=sum(sales[i] if i in remaining_original else pool[i]['price'] for i in outgoing)
        purchases=sum(pool[i]['price'] for i in incoming);bank+=proceeds-purchases
        chip=chip_plan.get(event);account=chip_transfer_account(free,k,chip)
        hits=account['hits'];used=account['used'];next_free=account['next_gw']
        if (k!=len(outgoing) or (chip not in REBUILDS and k>max_per_gw) or (not allow_hits and hits) or bank<0
            or (t==0 and first_count is not None and k!=first_count) or abs(result.x[banks[t]]-bank)>1e-4):
            raise RuntimeError('Solverplanens transferregnskab kunne ikke valideres.')
        xi=selected('xi');captain=selected('captain')[0]
        bench=sorted(set(squad)-set(xi),key=lambda i:(lookup[i]['position']!=1,-lookup[i]['xp'],i))
        vice=max((i for i in xi if i!=captain),key=lambda i:(lookup[i]['xp'],-i))
        xi_points=sum(lookup[i]['xp'] for i in xi)+(2 if chip=='triple_captain' else 1)*lookup[captain]['xp']
        lineup=dict(chip=chip,squad=squad,starters=xi,bench=bench,captain=captain,vice_captain=vice,
                    expected_xi_captain=xi_points,bench_weight=bench_weight,
                    objective=xi_points+(1 if chip=='bench_boost' else bench_weight)*sum(lookup[i]['xp'] for i in bench))
        # Cash is validated separately above; reuse the standard identity/lineup rules.
        validate_squad(lineup,[dict(r,can_select=r['player_id'] in current or r.get('can_select',True)) for r in tables[event]],
                       budget=sum(pool[i]['price'] for i in squad)/10,locked=locked,excluded=excluded)
        lineups[event]=lineup
        active_bank=bank
        if chip=='free_hit':bank+=purchases-proceeds
        else:remaining_original-=set(outgoing);current=set(squad)
        if abs(result.x[permanent_banks[t]]-bank)>1e-4 or set(selected('permanent'))!=current or set(selected('original'))!=remaining_original:
            raise RuntimeError('Permanent trup/bank kunne ikke valideres.')
        steps.append(dict(event=event,chip=chip,count=k,**{'in':incoming,'out':outgoing},squad=squad,
                          active_squad=squad,permanent_squad_after=sorted(current),permanent_bank_after=bank,
                          original_lots_after=sorted(remaining_original),ordinary_count=0 if chip in REBUILDS else k,
                          relocation_count=k if chip in REBUILDS else 0,
                          bank_after=active_bank,sale_proceeds=proceeds,purchase_cost=purchases,
                          available=free,**account))
        free=next_free
    if sum(s['ordinary_count'] for s in steps)>max_total:raise RuntimeError('Samlet transfergrænse overskredet.')
    terminal=dict(squad=sorted(current),bank=bank,free_transfers=free,
                  selling_prices={i:sales[i] if i in remaining_original else pool[i]['price'] for i in sorted(current)})
    return dict(first_count=first_count,terminal_state=terminal,steps=steps,lineups=lineups,hits=sum(s['hits'] for s in steps),
                objective=sum(l['objective'] for l in lineups.values())-sum(s['hits'] for s in steps),
                solver=dict(status='optimal' if result.success else 'feasible_time_limit',
                            gap=float(result.mip_gap),optimal=bool(result.success)))
