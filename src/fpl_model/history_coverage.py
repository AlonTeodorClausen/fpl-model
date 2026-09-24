"""Conservative history denominator checks, never a transfer/DNP inference."""
from collections import Counter


def history_window(rows, fixtures, team_id):
    """Inputs are already restricted to the cutoff and completed fixtures.

    Require observed rows for every prior fixture of one consistently observed
    club. New signings/transfers may fail this conservative check: we do not
    invent historical registration dates to repair the denominator.
    """
    expected={f['id'] for f in fixtures if team_id in (f['team_h'],f['team_a'])}
    counts=Counter(r['fixture_id'] for r in rows)
    missing=sorted(expected-counts.keys())
    if not rows:
        state='no_observed_history'
    elif any(r.get('team_id')!=team_id for r in rows):
        state='unresolved_team_membership'
    elif any(n!=1 for n in counts.values()) or set(counts)!=expected:
        state='incomplete_history_denominator'
    else:
        state='complete_observed_window'
    return dict(usable=state=='complete_observed_window',state=state,
                expected_missing_fixture_ids=missing,observed_rows=len(rows),expected_rows=len(expected))
