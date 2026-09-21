"""Read-only Step 2B diagnostics. Candidate associations are NOT canonical joins.

Only compares the two explicitly captured gameweeks and the requested players.
Core naive kickoff values are tested against official UTC wall-clock values; the
result retains that interpretation as a review condition, not a timezone repair.
"""
import argparse
import csv
import hashlib
import importlib.util
import json
import sys
from collections import Counter, defaultdict
from datetime import datetime
from decimal import Decimal, InvalidOperation
from io import StringIO
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from fpl_model.io import verify_snapshot
from fpl_model.label_contracts import integer_id, label_state, utc

_spec = importlib.util.spec_from_file_location('step2a_profile', Path(__file__).with_name('audit_snapshot.py'))
_profile = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_profile)


def csv_rows(body):
    reader = csv.reader(StringIO(body.decode('utf-8-sig'), newline=''), strict=True)
    columns = next(reader)
    if not columns or len(columns) != len(set(columns)):
        raise ValueError('Missing or duplicate CSV columns')
    rows = []
    for row in reader:
        if not row:
            continue
        if len(row) != len(columns):
            raise ValueError('Non-rectangular CSV')
        rows.append(dict(zip(columns, row)))
    return rows, columns


def unique(rows, field):
    result = {}
    for row in rows:
        key = row[field]
        if key in result:
            raise ValueError('Ambiguous identity: ' + field)
        result[key] = row
    return result


def fixture_candidates(fixtures, matches, code_to_id):
    """Fail closed on collisions; UTC interpretation of naive Core time is explicit."""
    left, right = defaultdict(list), defaultdict(list)
    invalid = []
    fixture_ids = Counter(f['id'] for f in fixtures)
    match_ids = Counter(m['match_id'] for m in matches)
    for f in fixtures:
        if f.get('kickoff_time') is not None:
            key = (f['team_h'], f['team_a'], utc(f['kickoff_time']).replace(tzinfo=None))
            left[key].append(f)
    for m in matches:
        if m.get('tournament') != 'prem':
            continue
        try:
            dt = datetime.fromisoformat(m['kickoff_time'])
            if dt.tzinfo is not None:
                dt = utc(dt).replace(tzinfo=None)
            key = (code_to_id[integer_id(m['home_team'])], code_to_id[integer_id(m['away_team'])], dt)
            right[key].append(m)
        except (KeyError, ValueError):
            invalid.append(m['match_id'])
    candidates, collisions, unmatched = [], [], []
    for key, rows in sorted(right.items()):
        fs = left.get(key, [])
        if len(rows) != 1 or len(fs) > 1 or any(match_ids[r['match_id']] != 1 for r in rows) or any(fixture_ids[f['id']] != 1 for f in fs):
            collisions.append([r['match_id'] for r in rows])
        elif not fs:
            unmatched.append(rows[0]['match_id'])
        else:
            candidates.append({'fixture_id': fs[0]['id'], 'match_id': rows[0]['match_id'],
                               'home_fpl_team_id': key[0], 'away_fpl_team_id': key[1],
                               'official_kickoff_utc': utc(fs[0]['kickoff_time']).isoformat(),
                               'core_kickoff_literal': rows[0]['kickoff_time'],
                               'status': 'candidate_requires_core_utc_interpretation'})
    return {'candidates': candidates, 'collisions': collisions, 'unmatched': unmatched, 'invalid': invalid,
            'rule': 'verified team codes + ordered home/away + exact kickoff; naive Core time tested as UTC',
            'canonicalisation_approved': False}


def compare_value(a, b):
    if a in (None, '') or b in (None, ''):
        return 'missing in one source'
    try:
        equal = Decimal(str(a)) == Decimal(str(b))
    except (InvalidOperation, TypeError, ValueError):
        equal = a == b
    return 'identical' if equal else 'unexplained'


def audit(baseline, sample):
    baseline, sample = Path(baseline), Path(sample)
    bm, sm = verify_snapshot(baseline), verify_snapshot(sample)
    sha = bm['source_commits']['fpl_core']
    if sm['source_commits']['fpl_core'] != sha:
        raise ValueError('Core commit differs from audited baseline')

    def one(root, manifest, suffix):
        entries = [f for f in manifest['files'] if f['relative_path'].endswith(suffix) and f['outcome'] == 'success']
        if len(entries) != 1:
            raise ValueError('Expected one successful file: ' + suffix)
        e = entries[0]
        return (root / e['relative_path']).read_bytes(), e

    def js(root, manifest, suffix):
        return json.loads(one(root, manifest, suffix)[0])

    old = js(baseline, bm, 'bootstrap_static.json')
    new = js(sample, sm, 'bootstrap_static.json')
    fixtures = js(sample, sm, 'fixtures.json')
    old_fixtures = js(baseline, bm, 'fixtures.json')
    teams = unique(old['teams'], 'id')
    players = unique(old['elements'], 'id')
    fresh_players = unique(new['elements'], 'id')
    core_players = csv_rows(one(baseline, bm, '/players.csv')[0])[0]
    core_teams = csv_rows(one(baseline, bm, '/teams.csv')[0])[0]
    core_p = unique(core_players, 'player_id')
    core_t = unique(core_teams, 'id')
    if {integer_id(x) for x in core_p} != set(players) or {integer_id(x) for x in core_t} != set(teams):
        raise ValueError('Baseline identity coverage changed')
    for p in core_players:
        f = players[integer_id(p['player_id'])]
        if integer_id(p['player_code']) != f['code'] or integer_id(p['team_code']) != f['team_code'] or any(p[k] != f[k] for k in ('first_name', 'second_name', 'web_name')):
            raise ValueError('Unverified Core player identity')
    for t in core_teams:
        f = teams[integer_id(t['id'])]
        if integer_id(t['code']) != f['code'] or t['name'] != f['name']:
            raise ValueError('Unverified Core team identity')
    code_to_id = {t['code']: t['id'] for t in teams.values()}
    if len(code_to_id) != len(teams):
        raise ValueError('Ambiguous team code')
    datasets, histories, history_meta = {}, [], {}
    core_matches, core_stats = [], []
    cl_stats = []
    for e in sm['files']:
        path = e['relative_path']
        if e['outcome'] != 'success':
            continue
        body = (sample / path).read_bytes()
        if '/element_summary/' in path:
            data = json.loads(body)
            rows = data['history']
            pid = integer_id(Path(path).stem)
            if not isinstance(rows, list) or any(r['element'] != pid for r in rows):
                raise ValueError('Wrong element history')
            if pid not in players or fresh_players[pid]['code'] != players[pid]['code']:
                raise ValueError('Sample player identity changed')
            histories.extend(rows)
            history_meta[pid] = e
            datasets[path] = {'manifest': e, 'top_level_keys': sorted(data), 'history': _profile.profile(rows),
                              'history_key': _profile.keys(rows, 'element', 'fixture')}
        elif path.endswith('.csv'):
            if e.get('commit_sha') != sha:
                raise ValueError('Unpinned Core file')
            rows, columns = csv_rows(body)
            is_match = path.endswith('/matches.csv')
            datasets[path] = {'manifest': e, 'profile': _profile.profile(rows, csv_values=True, columns=columns),
                              'identity_key': _profile.keys(rows, *(['match_id'] if is_match else ['player_id', 'match_id']))}
            if is_match:
                datasets[path]['competitions'] = dict(Counter(r['tournament'] for r in rows))
                datasets[path]['kickoff_range_literal'] = _profile.date_range([r['kickoff_time'] for r in rows])
                datasets[path]['finished'] = dict(Counter(r['finished'] for r in rows))
            else:
                datasets[path]['unknown_fpl_player_ids'] = sorted({integer_id(r['player_id']) for r in rows} - set(players))
                datasets[path]['distinct_players'] = len({r['player_id'] for r in rows})
                datasets[path]['rows_per_match'] = dict(Counter(r['match_id'] for r in rows))
            if '/By Gameweek/' in path:
                (core_matches if is_match else core_stats).extend(rows)
            elif not is_match:
                cl_stats.extend(rows)
    if _profile.keys(histories, 'element', 'fixture')['duplicate_groups']:
        raise ValueError('Duplicate player fixture labels')
    if _profile.keys(core_stats, 'player_id', 'match_id')['duplicate_groups']:
        raise ValueError('Duplicate Core player-match rows')
    unique(core_matches, 'match_id')
    crosswalk = fixture_candidates(fixtures, core_matches, code_to_id)
    candidates = {r['fixture_id']: r['match_id'] for r in crosswalk['candidates']}
    stats = {(integer_id(r['player_id']), r['match_id']): r for r in core_stats}
    matches = unique(core_matches, 'match_id')
    player_match_competitions = Counter()
    team_conflicts = []
    for row in core_stats:
        match = matches[row['match_id']]
        player_match_competitions[match['tournament']] += 1
        if match['tournament'] == 'prem':
            pid = integer_id(row['player_id'])
            if pid not in players or players[pid]['team_code'] not in (integer_id(match['home_team']), integer_id(match['away_team'])):
                team_conflicts.append({'element': pid, 'match_id': row['match_id']})
    event_by_id, fixture_by_id = unique(new['events'], 'id'), unique(fixtures, 'id')
    contexts = [one(sample, sm, suffix)[1] for suffix in ('bootstrap_static.json', 'fixtures.json')]
    labels = []
    for h in histories:
        f = fixture_by_id[h['fixture']]
        state, reason = label_state(h, f, event_by_id.get(f['event'], {}), element_id=h['element'])
        available = max(utc(m['available_at']) for m in [history_meta[h['element']], *contexts]).isoformat()
        labels.append({'element': h['element'], 'fixture': h['fixture'], 'round': h['round'],
                       'state': state.value, 'reason': reason, 'label_observed_available_at': available})
    fields = {'minutes': 'minutes_played', 'starts': 'starts', 'goals_scored': 'goals',
              'assists': 'assists', 'expected_goals': 'xg', 'expected_assists': 'xa',
              'saves': 'saves', 'goals_conceded': 'goals_conceded', 'recoveries': 'recoveries',
              'tackles': 'tackles', 'defensive_contribution': 'defensive_contributions',
              'clean_sheets': 'clean_sheets', 'total_points': 'total_points'}
    comparisons, paired, missing_pairs = [], [], []
    label_index = {(r['element'], r['fixture']): r for r in labels}
    for h in histories:
        if h['round'] not in (3, 4):
            continue
        pid, fid = h['element'], h['fixture']
        mid = candidates.get(fid)
        c = stats.get((pid, mid))
        context = {'element': pid, 'name': players[pid]['web_name'], 'fixture': fid, 'round': h['round'],
                   'candidate_core_match': mid, 'official_label_state': label_index[pid, fid]['state']}
        if context['official_label_state'] == 'unusable':
            missing_pairs.append({**context, 'classification': 'unexplained',
                                  'timing_evidence': 'Invalid official context; comparison withheld'})
            continue
        if c is None:
            missing_pairs.append({**context, 'classification': 'missing in one source',
                                  'timing_evidence': 'Core fixture not finished at pin' if mid and matches[mid]['finished'] == 'False' else 'no Core player row; absence does not establish DNP'})
            continue
        paired.append(context)
        for a, b in fields.items():
            classification = compare_value(h.get(a), c.get(b))
            comparisons.append({**context, 'fpl_field': a, 'core_field': b, 'fpl_value': h.get(a),
                                'core_value': c.get(b), 'classification': classification})
    cumulative = csv_rows(one(baseline, bm, '/playerstats.csv')[0])[0]
    gw3 = {integer_id(r['id']): r for r in cumulative if r['gw'] == '3'}
    gw4 = {integer_id(r['id']): r for r in cumulative if r['gw'] == '4'}
    minutes = []
    for pid, p in players.items():
        if pid not in gw4 or Decimal(gw4[pid]['minutes']) == p['minutes']:
            continue
        h = [r for r in histories if r['element'] == pid]
        f4 = [f for f in old_fixtures if f['event'] == 4 and p['team'] in (f['team_h'], f['team_a'])]
        minutes.append({'element': pid, 'name': p['web_name'], 'team': teams[p['team']]['name'],
                        'core_gw3': gw3.get(pid, {}).get('minutes'), 'core_gw4': gw4[pid]['minutes'],
                        'baseline_fpl_minutes': p['minutes'], 'delta': p['minutes'] - int(gw4[pid]['minutes']),
                        'baseline_fixtures': f4,
                        'sample_history_before_gw4': sum(r['minutes'] for r in h if r['round'] < 4) if h else None,
                        'sample_history_gw4': [r['minutes'] for r in h if r['round'] == 4] if h else None})
    stats_keys = {(r['player_id'], r['match_id']): r for r in core_stats}
    result = {'audit_id': 'step2b_' + sm['run_id'], 'core_commit_sha': sha,
              'inputs': [{'snapshot_id': m['run_id'], 'path': str(root.resolve()),
                          'manifest_sha256': hashlib.sha256((root / 'manifest.json').read_bytes()).hexdigest(),
                          'manifest': m} for root, m in ((baseline, bm), (sample, sm))],
              'datasets': datasets, 'official_history_profile': _profile.profile(histories),
              'sample': [{'element': pid, 'name': players[pid]['web_name'], 'team': teams[players[pid]['team']]['name'],
                          'position': players[pid]['element_type'], 'minutes': [h['minutes'] for h in histories if h['element'] == pid],
                          'starts': [h.get('starts') for h in histories if h['element'] == pid]} for pid in sorted(history_meta)],
              'identity': {'verified_core_players': len(core_players), 'verified_core_teams': len(core_teams),
                           'core_pl_player_current_team_conflicts': team_conflicts,
                           'player_match_competitions_excluding_duplicate_exports': dict(player_match_competitions),
                           'cl_player_rows_repeated_identically_in_gw4': sum(stats_keys.get((r['player_id'], r['match_id'])) == r for r in cl_stats)},
              'finality_differences': [{'fixture': fid, 'match_id': mid,
                                       'fpl_finished': fixture_by_id[fid]['finished'],
                                       'core_finished': matches[mid]['finished'],
                                       'classification': 'provisional/finality issue'}
                                      for fid, mid in candidates.items()
                                      if (matches[mid]['finished'] == 'True') != fixture_by_id[fid]['finished']],
              'labels': labels, 'label_states': dict(Counter(r['state'] for r in labels)),
              'fixture_crosswalk': crosswalk, 'paired_player_fixtures': paired, 'missing_player_fixtures': missing_pairs,
              'comparisons': comparisons,
              'comparison_counts': {field: dict(Counter(r['classification'] for r in comparisons if r['fpl_field'] == field)) for field in fields},
              'aggregate_minutes_discrepancies': minutes,
              'aggregate_minutes_team_counts': dict(Counter(r['team'] for r in minutes)),
              'limitations': ['Sample only; candidate crosswalk is not approved canonical mapping.',
                              'Core naive kickoff interpreted as UTC for diagnostic comparison only.',
                              'No historical input availability before actual retrieval is established.',
                              'No field imputation or reconciliation. Final labels can be revised.']}
    verify_snapshot(baseline)
    verify_snapshot(sample)
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('baseline', type=Path)
    parser.add_argument('sample', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(argv)
    if any(args.output.resolve().is_relative_to(p.resolve().parent) for p in (args.baseline, args.sample)):
        parser.error('Audit output must be outside raw snapshot storage')
    result = audit(args.baseline, args.sample)
    args.output.mkdir(parents=True, exist_ok=True)
    files = ['coverage.json', 'discrepancies.csv', 'fixture_crosswalk_candidates.csv', 'missing_player_fixtures.csv']
    if any((args.output / name).exists() for name in files):
        raise FileExistsError('Audit output already exists')
    with (args.output / 'coverage.json').open('x') as f:
        json.dump(result, f, indent=2, ensure_ascii=False)
        f.write('\n')
    for name, rows in [('discrepancies.csv', result['comparisons']),
                       ('fixture_crosswalk_candidates.csv', result['fixture_crosswalk']['candidates']),
                       ('missing_player_fixtures.csv', result['missing_player_fixtures'])]:
        with (args.output / name).open('x', newline='') as f:
            if rows:
                writer = csv.DictWriter(f, fieldnames=list(rows[0]))
                writer.writeheader()
                writer.writerows(rows)
    print(f"audit: {result['audit_id']}\nhistory rows: {result['official_history_profile']['row_count']}\npaired sample fixtures: {len(result['paired_player_fixtures'])}")


if __name__ == '__main__':
    main()
