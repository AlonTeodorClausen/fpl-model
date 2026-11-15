"""Minutes model v2: start, cameo given no start, and minutes given role.

Pre-registered in notes/minutes_v2.md. The constants below are fixed; changing
any of them makes a new candidate that must restart prospective evaluation.
Only minutes change; every other component is baseline v1.
"""
from collections import defaultdict

import numpy as np

from fpl_model.history_coverage import history_window
from fpl_model.label_contracts import utc

VERSION = 'component_minutes_v2'
HALF_LIFE_MATCHES = 5.0
PRIOR_MATCHES = 2.0
FULL_MATCH_MINUTES = 89
EARLY_EXIT_SD = 12.0
RETURN_START_FACTOR = 0.7
RETURN_MIN_MISSED = 2
FALLBACK_PRIOR = dict(full_match=0.6, early_exit_minutes=70.0)


def _known(rows):
    return all(r.get('starts') in (0, 1) and isinstance(r.get('minutes'), (int, float))
               and 0 <= r['minutes'] <= 90 for r in rows)


def _sorted(rows):
    return sorted(rows, key=lambda r: (utc(r['kickoff_time']), r['fixture_id']))


def position_priors(players, histories, past, config):
    """Pooled, unweighted rates per position from complete earlier histories."""
    by_player = defaultdict(list)
    for r in histories:
        by_player[r['player_id']].append(r)
    pooled = {pos: [] for pos in (1, 2, 3, 4)}
    for p in players:
        own = by_player.get(p['id'], [])
        if own and _known(own) and history_window(own, past, p['team'])['usable']:
            pooled[p['element_type']].extend(own)
    result = {}
    for pos, rows in pooled.items():
        starts = [r for r in rows if r['starts']]
        benched = [r for r in rows if not r['starts']]
        subs = [r for r in benched if r['minutes'] > 0]
        full = [r for r in starts if r['minutes'] >= FULL_MATCH_MINUTES]
        early = [r['minutes'] for r in starts if r['minutes'] < FULL_MATCH_MINUTES]
        result[pos] = dict(
            position=pos, rows=len(rows),
            start=len(starts)/len(rows) if rows else config.prior_start,
            sub_given_no_start=(len(subs)/len(benched) if benched else
                                config.prior_sub/max(1-config.prior_start, 1e-12)),
            full_match=len(full)/len(starts) if starts else FALLBACK_PRIOR['full_match'],
            early_exit_minutes=float(np.mean(early)) if early else FALLBACK_PRIOR['early_exit_minutes'],
            sub_minutes=float(np.mean([r['minutes'] for r in subs])) if subs else config.sub_minutes)
    return result


def returning_from_absence(rows, player):
    """Trailing missed matches count as absence only if FPL now says fully fit."""
    missed = 0
    for r in reversed(rows):
        if r['minutes'] > 0:
            break
        missed += 1
    chance = player.get('chance_of_playing_next_round')
    fit = player.get('status') == 'a' and chance in (None, 100)
    return missed if missed >= RETURN_MIN_MISSED and fit else 0


def apply_minutes_v2(par, history, prior, player, *, live):
    e = par['explanation']
    rows = _sorted(history)
    if len(rows) < 2 or par['history_coverage'] != 'complete_observed_window' or not _known(rows):
        e['role'] = dict(method=VERSION, status='fallback',
                         reason='requires_two_complete_final_rows_with_known_starts')
        return
    missed = returning_from_absence(rows, player) if live else 0
    used = rows[:len(rows)-missed]
    w = 2.0**(-np.arange(len(used)-1, -1, -1)/HALF_LIFE_MATCHES)
    start = np.array([bool(r['starts']) for r in used], dtype=bool)
    mins = np.array([r['minutes'] for r in used], dtype=float)
    sub = ~start & (mins > 0)
    full = start & (mins >= FULL_MATCH_MINUTES)
    early = start & ~full
    k = PRIOR_MATCHES

    def smooth(hits, weights, centre):
        return float((hits+k*centre)/(weights+k))

    p_start = smooth((w*start).sum(), w.sum(), prior['start'])
    p_sub_ns = smooth((w*sub).sum(), (w*~start).sum(), prior['sub_given_no_start'])
    p_full = smooth((w*full).sum(), (w*start).sum(), prior['full_match'])
    early_minutes = smooth((w*mins*early).sum(), (w*early).sum(), prior['early_exit_minutes'])
    sub_minutes = smooth((w*mins*sub).sum(), (w*sub).sum(), prior['sub_minutes'])
    p_sub = (1-p_start)*p_sub_ns
    if missed:
        moved = p_start*(1-RETURN_START_FACTOR)
        p_start -= moved
        p_sub += moved
    early_minutes = float(np.clip(early_minutes, 1, FULL_MATCH_MINUTES-1))
    sub_minutes = float(np.clip(sub_minutes, 1, 59))
    factor = e['injury_factor']
    par.update(p_start=p_start*factor, p_sub=p_sub*factor,
               start_minutes=p_full*90+(1-p_full)*early_minutes, sub_minutes=sub_minutes,
               full_match_prob=p_full, early_exit_minutes=early_minutes)
    e.update(pre_injury_start=p_start, pre_injury_sub=p_sub)
    e['role'] = dict(method=VERSION, status='estimated', position_prior=prior,
                     half_life_matches=HALF_LIFE_MATCHES, prior_matches=k,
                     fixture_ids=[r['fixture_id'] for r in used], weights=w.tolist(),
                     returning_after_missed_matches=missed,
                     p_start_given_available=p_start, p_sub_given_available=p_sub,
                     p_sub_given_no_start=p_sub_ns, full_match_prob=p_full,
                     early_exit_minutes=early_minutes, sub_minutes=sub_minutes)


def draw_start_minutes(par, rng, draws):
    early = np.clip(np.rint(rng.normal(par['early_exit_minutes'], EARLY_EXIT_SD, draws)),
                    1, FULL_MATCH_MINUTES-1)
    return np.where(rng.random(draws) < par['full_match_prob'], 90, early)
