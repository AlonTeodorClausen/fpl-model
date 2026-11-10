"""Selection and display data for one cached forecast, without new modelling."""

import numpy as np
from pathlib import Path
import re

from fpl_model.transfer_planner import load_cached_bundle


def bundle_for_report(report, session_bundle, cache_root):
    """Use the report's exact forecast, falling back to its saved summaries only."""
    metadata=report['forecast']
    key=metadata.get('cache_key')
    if key and re.fullmatch(r'[0-9a-f]{64}',key) is None:
        raise ValueError('Invalid saved forecast identity')
    def verify(bundle):
        original=bundle['metadata']
        if any(metadata.get(field)!=original.get(field) for field in
               ('cache_key','model_version','forecast_origin_at',
                'snapshot_id','manifest_sha256','seed','draws')):
            raise ValueError('Saved forecast cache identity mismatch')
        return bundle
    if key and session_bundle is not None and session_bundle.get('metadata',{}).get('cache_key')==key:
        return verify(session_bundle)
    if key and (Path(cache_root)/key/'bundle.json').is_file():
        return verify(load_cached_bundle(cache_root,key))
    return dict(metadata=metadata,
                rows={int(event):rows for event,rows in report['players_by_event'].items()},
                explanations={},planning_scenarios={})


def selected_owned_id(value, owned_ids):
    """Ignore arbitrary URL parameters and only open an owned FPL player ID."""
    if not isinstance(value, str) or not value.isascii() or not value.isdecimal():
        return None
    player_id = int(value)
    return player_id if player_id in owned_ids else None


def comparison_rows(bundle, event, selected_id, compare_ids):
    """Keep the clicked player first and compare only this bundle's GW rows."""
    if event not in bundle['rows']:
        raise ValueError('GW mangler i prognosen.')
    lookup = {row['player_id']: row for row in bundle['rows'][event]}
    ids = list(dict.fromkeys([selected_id, *compare_ids]))
    if any(player_id not in lookup for player_id in ids):
        raise ValueError('Ukendt spiller i prognosen.')
    return [lookup[player_id] for player_id in ids]


def point_distribution(bundle, event, player_id):
    """Raw player points from the same planning scenarios used for xP."""
    order = {player['id']: i for i, player in enumerate(sorted(bundle['players'], key=lambda p: p['id']))}
    if player_id not in order:
        raise ValueError('Ukendt spiller i prognosen.')
    values = bundle['planning_scenarios'][event]['points'][:, order[player_id]]
    points, counts = np.unique(values, return_counts=True)
    return [(int(point), float(count / len(values))) for point, count in zip(points, counts)]
