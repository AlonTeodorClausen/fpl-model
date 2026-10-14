"""Local user-owned squad; money is integer tenths of a million, never buy-price profit guesses."""
from collections import Counter
from decimal import Decimal, InvalidOperation
import json
import os
from pathlib import Path
import tempfile

from fpl_model.optimizer.squad import COUNTS


def money(value):
    """Convert an explicitly entered £m amount without silently rounding."""
    try:
        if isinstance(value, bool) or value is None:
            raise ValueError()
        amount = Decimal(str(value)) * 10
        if not amount.is_finite() or amount < 0 or amount != amount.to_integral_value():
            raise ValueError()
        return int(amount)
    except (ValueError, InvalidOperation):
        raise ValueError('Beløb skal være positive eller nul, i trin på £0,1m.') from None


def _integer(value, low, high, label):
    if type(value) is not int or not low <= value <= high:
        raise ValueError(f'{label}: forventede et heltal mellem {low} og {high}.')


def _shape(profile):
    if profile.get('schema_version') != 1 or not isinstance(profile.get('season'), str):
        raise ValueError('Ukendt holdformat/sæson.')
    from fpl_model.chips import normalize_chip_inventory
    normalize_chip_inventory(profile)
    entries = profile.get('players', [])
    if len(entries) != 15:
        raise ValueError('Indtast præcis 15 spillere.')
    for row in entries:
        _integer(row.get('player_id'), 1, 1000000, 'Spiller-ID')
        _integer(row.get('selling_price'), 1, 10000, 'Salgsværdi')
    if len({r['player_id'] for r in entries}) != 15:
        raise ValueError('Den samme spiller er valgt flere gange.')
    _integer(profile.get('bank'), 0, 100000, 'Bank')
    _integer(profile.get('free_transfers'), 0, 5, 'Gratis transfers')
    _integer(profile.get('transfers_made'), 0, 20, 'Transfers allerede foretaget')
    state=profile.get('pre_transfer_state')
    if state is not None:
        if not isinstance(state,dict):raise ValueError('Ugyldig tilstand før transfers.')
        from fpl_model.label_contracts import utc
        _integer(state.get('event'),1,38,'GW før transfers')
        _integer(state.get('existing_hits'),0,80,'Eksisterende hits')
        if state['existing_hits']%4:raise ValueError('Hits skal være delelige med fire.')
        if not state.get('confirmed_at'):raise ValueError('Bekræft tilstanden før transfers.')
        utc(state['confirmed_at'])
        _shape(dict(schema_version=1,season=profile['season'],players=state.get('players',[]),
                    bank=state.get('bank'),free_transfers=state.get('free_transfers'),transfers_made=0))



def validate_profile(profile, players, *, season):
    _shape(profile)
    if profile['season'] != season:
        raise ValueError('Holdets sæson matcher ikke datagrundlaget.')
    pool = {p['id']: p for p in players}
    ids = [r['player_id'] for r in profile['players']]
    if not set(ids) <= pool.keys():
        raise ValueError('Holdet indeholder ukendte officielle spiller-ID’er; opdatér/ret datagrundlaget.')
    if Counter(pool[i]['element_type'] for i in ids) != COUNTS:
        raise ValueError('Holdet skal have 2 målmænd, 5 forsvarere, 5 midtbaner og 3 angribere.')
    if max(Counter(pool[i]['team'] for i in ids).values()) > 3:
        raise ValueError('Mere end tre spillere fra én klub. Denne version kræver et lovligt udgangshold.')
    for row in profile['players']:
        current = pool[row['player_id']].get('now_cost')
        if current is None or row['selling_price'] > current:
            raise ValueError('Salgsværdi overstiger købspris i snapshot; kontrollér priser og datagrundlag.')
    if profile.get('pre_transfer_state'):
        state=profile['pre_transfer_state']
        validate_profile(dict(schema_version=1,season=season,players=state['players'],bank=state['bank'],
                              free_transfers=state['free_transfers'],transfers_made=0),players,season=season)
    # An already owned, unselectable player can be held, but cannot be newly bought.


def transfer_schedule(free_transfers, count, events, *, allow_hits=False, transfers_made=0):
    _integer(free_transfers, 0, 5, 'Gratis transfers')
    _integer(count, 0, 15, 'Nye transfers')
    _integer(transfers_made, 0, 20, 'Transfers allerede foretaget')
    if transfers_made + count > 20:
        raise ValueError('Grænsen på 20 transfers i samme GW overskrides.')
    if not allow_hits and count > free_transfers:
        raise ValueError('Forslaget kræver pointfradrag, som ikke er tilladt.')
    out = []
    for index, event in enumerate(events):
        moves = count if index == 0 else 0
        used = min(moves, free_transfers)
        remaining = free_transfers - used
        out.append(dict(event=event, available=free_transfers, used=used, remaining=remaining,
                        next_gw=min(5, remaining + 1), hits=4 * max(0, moves - used)))
        free_transfers = min(5, remaining + 1)
    return out


def save_profile(profile, path):
    """Atomic local edit; never touches snapshots or an external FPL account."""
    _shape(profile)
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(profile, ensure_ascii=False, indent=2, allow_nan=False) + '\n'
    name = None
    try:
        with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=path.parent, delete=False) as f:
            name = f.name
            f.write(payload)
            f.flush()
            os.fsync(f.fileno())
        os.replace(name, path)
    finally:
        if name is not None and Path(name).exists():
            Path(name).unlink()


def load_profile(path):
    profile = json.loads(Path(path).read_text())
    _shape(profile)
    return profile
