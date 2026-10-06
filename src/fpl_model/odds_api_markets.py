"""William Hill market translation only; all fitting lives in defensive_odds.

Explicit aliases checked in the 2026-10-01 access audit against official UTC
kickoffs. Names alone never establish a fixture match. No fuzzy matching.
"""
import math
from fpl_model.label_contracts import utc

BOOKMAKER = 'williamhill'
ALIASES = {'Leeds United':'Leeds', 'Brighton and Hove Albion':'Brighton',
    'Manchester United':'Man Utd', 'Tottenham Hotspur':'Spurs',
    'Nottingham Forest':"Nott'm Forest", 'Manchester City':'Man City',
    'Newcastle United':'Newcastle'}


def extract_market(event, retrieved_at):
    """Return canonical five prices plus provenance, or a safe explicit rejection.

    last_update describes provider updates, not when this project possessed the
    prices. It must be aware and no later than retrieval; it never replaces it.
    """
    provenance = dict(event_id=event.get('id'), bookmaker=BOOKMAKER,
                      markets=['h2h','totals'], totals_point=2.5)
    def reject(reason):
        return dict(prices=None, market_provenance=provenance, failure=reason)
    books=event.get('bookmakers')
    if not isinstance(books,list):return reject('invalid_bookmakers')
    books=[b for b in books if isinstance(b,dict) and b.get('key')==BOOKMAKER]
    if len(books)!=1:return reject('missing_williamhill' if not books else 'duplicate_williamhill')
    book=books[0];provenance['bookmaker_last_update']=book.get('last_update')
    markets=book.get('markets')
    if not isinstance(markets,list):return reject('invalid_markets')
    selected={}
    for key in ('h2h','totals'):
        found=[m for m in markets if isinstance(m,dict) and m.get('key')==key]
        if len(found)!=1:return reject(('missing_' if not found else 'duplicate_')+key+'_market')
        selected[key]=found[0]
    provenance['market_last_updates']={k:m.get('last_update') for k,m in selected.items()}
    try:
        stamps=[provenance['bookmaker_last_update'],*provenance['market_last_updates'].values()]
        if any(utc(t)>utc(retrieved_at) for t in stamps):return reject('invalid_provider_update')
    except (ValueError,TypeError,AttributeError):return reject('invalid_provider_update')
    h=selected['h2h'].get('outcomes');t=selected['totals'].get('outcomes')
    if not isinstance(h,list) or any(not isinstance(o,dict) for o in h):return reject('invalid_h2h_market')
    if not isinstance(t,list) or any(not isinstance(o,dict) for o in t):return reject('invalid_totals_2_5')
    provenance['observed_totals_lines']=sorted({o['point'] for o in t
        if type(o.get('point')) in (int,float) and math.isfinite(o['point'])})
    t=[o for o in t if o.get('point')==2.5]
    if not t:return reject('missing_totals_2_5')
    names=[event.get('home_team'),'Draw',event.get('away_team')]
    if any(not isinstance(o.get('name'),str) for o in h):return reject('invalid_h2h_market')
    if any(not isinstance(o.get('name'),str) for o in t):return reject('invalid_totals_2_5')
    if len(set(names))!=3 or len(h)!=3 or set(o.get('name') for o in h)!=set(names):return reject('invalid_h2h_market')
    if len(t)!=2 or {o.get('name') for o in t}!={'Over','Under'}:return reject('invalid_totals_2_5')
    if any(type(o.get('price')) not in (int,float) or not math.isfinite(o['price']) or o['price']<=1 for o in h+t):
        return reject('invalid_decimal_price')
    hp={o['name']:o['price'] for o in h};tp={o['name']:o['price'] for o in t}
    prices=dict(home=hp[names[0]],draw=hp['Draw'],away=hp[names[2]],over25=tp['Over'],under25=tp['Under'])
    return dict(prices=prices,market_provenance=provenance,failure=None)
