"""Immediate transfers into one fixed squad, with separate lineups for 1–4 GWs."""
import math
import numpy as np
from scipy.optimize import Bounds, LinearConstraint, milp
from scipy.sparse import lil_matrix

from fpl_model.my_team import transfer_schedule, validate_profile
from fpl_model.optimizer.squad import COUNTS, MINIMUM, MAXIMUM, validate_squad


class NoTransferSolution(ValueError):
    """Infeasibility or timeout without an incumbent, distinct from malformed inputs."""


def optimize_transfers(rows_by_event, profile, *, count, locked=(), excluded=(),
                       allow_hits=False, bench_weight=.1, time_limit=30):
    events = sorted(rows_by_event)
    if not 1 <= len(events) <= 4 or events != list(range(events[0], events[0]+len(events))):
        raise ValueError('Vælg 1–4 sammenhængende gameweeks.')
    if not math.isfinite(bench_weight) or not 0 <= bench_weight <= 1:
        raise ValueError('Ugyldig bænkvægt.')
    schedule = transfer_schedule(profile['free_transfers'], count, events, allow_hits=allow_hits,
                                 transfers_made=profile['transfers_made'])
    tables = {e: sorted(rows_by_event[e], key=lambda r: r['player_id']) for e in events}
    rows = tables[events[0]]
    ids = [r['player_id'] for r in rows]
    if len(set(ids)) != len(ids) or len(ids) < 15:
        raise ValueError('Ugyldig spillerpulje.')
    identity = lambda r: tuple(r.get(k) for k in ('player_id','price','position','team_id','can_select'))
    for table in tables.values():
        if [identity(r) for r in table] != [identity(r) for r in rows]:
            raise ValueError('Spillere, priser og identiteter skal være faste gennem horisonten.')
        if any(not math.isfinite(r['xp']) or type(r['price']) is not int or r['price'] <= 0 for r in table):
            raise ValueError('Manglende/ugyldige priser eller prognoser.')
    validate_profile(profile, [dict(id=r['player_id'], team=r['team_id'], element_type=r['position'],
                                   now_cost=r['price']) for r in rows], season=profile['season'])
    sales = {r['player_id']: r['selling_price'] for r in profile['players']}
    owned = set(sales)
    if not set(locked) <= owned or not set(excluded) <= set(ids) or set(locked) & set(excluded):
        raise ValueError('Behold kan kun vælges blandt egne spillere; kontrollér modstridende/ukendte valg.')
    n = len(rows)
    size = n * (1 + 2*len(events))
    objective = np.zeros(size)
    constraints, lows, highs = [], [], []

    def add(terms, low, high):
        constraints.append(terms); lows.append(low); highs.append(high)

    # Retaining an owned player consumes its sale opportunity, not its market price.
    costs = [sales.get(r['player_id'], r['price']) for r in rows]
    budget = profile['bank'] + sum(sales.values())
    add(dict(enumerate(costs)), 0, budget)
    add({i: 1 for i,r in enumerate(rows) if r['player_id'] in owned}, 15-count, 15-count)
    for pos, number in COUNTS.items():
        add({i: 1 for i,r in enumerate(rows) if r['position']==pos}, number, number)
    for club in sorted({r['team_id'] for r in rows}):
        add({i: 1 for i,r in enumerate(rows) if r['team_id']==club}, 0, 3)
    for g,event in enumerate(events):
        y, c = n*(1+2*g), n*(2+2*g)
        xp = np.array([r['xp'] for r in tables[event]])
        objective[:n] -= bench_weight*xp
        objective[y:y+n] = -(1-bench_weight)*xp
        objective[c:c+n] = -xp
        add({y+i: 1 for i in range(n)}, 11, 11)
        add({c+i: 1 for i in range(n)}, 1, 1)
        for pos in COUNTS:
            add({y+i: 1 for i,r in enumerate(rows) if r['position']==pos}, MINIMUM[pos], MAXIMUM[pos])
        for i in range(n):
            add({y+i: 1, i: -1}, -np.inf, 0)
            add({c+i: 1, y+i: -1}, -np.inf, 0)
    lower, upper = np.zeros(size), np.ones(size)
    for i,r in enumerate(rows):
        pid = r['player_id']
        if pid in locked:
            lower[i] = 1
        if pid in excluded or (pid not in owned and not r.get('can_select', True)):
            upper[i] = 0
    matrix = lil_matrix((len(constraints), size))
    for k,terms in enumerate(constraints):
        for i,value in terms.items():
            matrix[k,i] = value
    result = milp(objective, integrality=np.ones(size), bounds=Bounds(lower, upper),
                  constraints=LinearConstraint(matrix.tocsr(), lows, highs),
                  options={'time_limit': time_limit, 'mip_rel_gap': .0001})
    if result.x is None:
        reason = 'Ingen lovlig pakke' if result.status==2 else 'Solveren fandt ingen løsning inden tidsgrænsen'
        raise NoTransferSolution(f'{reason} med {count} transfers.')
    squad = [r['player_id'] for i,r in enumerate(rows) if result.x[i]>.5]
    incoming, outgoing = sorted(set(squad)-owned), sorted(owned-set(squad))
    pool = {r['player_id']: r for r in rows}
    bank = profile['bank'] + sum(sales[i] for i in outgoing) - sum(pool[i]['price'] for i in incoming)
    if len(incoming)!=count or len(outgoing)!=count or bank<0:
        raise RuntimeError('Solverresultatet overholder ikke transferregnskabet.')
    lineups = {}
    for g,event in enumerate(events):
        y, c = n*(1+2*g), n*(2+2*g)
        table = tables[event]; lookup = {r['player_id']: r for r in table}
        xi = [r['player_id'] for i,r in enumerate(rows) if result.x[y+i]>.5]
        captain = next(r['player_id'] for i,r in enumerate(rows) if result.x[c+i]>.5)
        bench = sorted(set(squad)-set(xi), key=lambda i: (lookup[i]['position']!=1,-lookup[i]['xp'],i))
        vice = max((i for i in xi if i!=captain), key=lambda i: (lookup[i]['xp'],-i))
        xi_points = sum(lookup[i]['xp'] for i in xi) + lookup[captain]['xp']
        lineup = dict(squad=squad, starters=xi, bench=bench, captain=captain, vice_captain=vice,
                      expected_xi_captain=xi_points, bench_weight=bench_weight,
                      objective=xi_points+bench_weight*sum(lookup[i]['xp'] for i in bench))
        validation_rows = [dict(r,price=sales.get(r['player_id'],r['price']),
                                can_select=r['player_id'] in owned or r.get('can_select',True)) for r in table]
        validate_squad(lineup, validation_rows, budget=budget/10, locked=locked, excluded=excluded)
        lineups[event] = lineup
    hits = schedule[0]['hits']
    return dict(count=count, squad=squad, **{'in': incoming, 'out': outgoing},
                bank_after=bank, hits=hits, transfer_schedule=schedule, lineups=lineups,
                objective=sum(t['objective'] for t in lineups.values())-hits,
                solver=dict(status='optimal' if result.success else 'feasible_time_limit',
                            gap=float(result.mip_gap), optimal=bool(result.success)))
