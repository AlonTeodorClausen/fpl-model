"""Read verified official snapshots and reuse existing player-label normalization."""
import json
import hashlib
from pathlib import Path
from fpl_model.io import verify_snapshot
from fpl_model.label_contracts import utc
from fpl_model.player_fixture_labels import normalize_snapshot


def snapshot_paths(raw_root):
    found=[]
    for path in Path(raw_root).glob('*'):
        if not (path/'COMPLETE').is_file(): continue
        m=verify_snapshot(path)
        if all(any(f['source']=='fpl_api' and f['relative_path'].endswith('/'+name) and f['outcome']=='success'
                   for f in m['files']) for name in ('bootstrap_static.json','fixtures.json')):
            found.append(path)
    return sorted(found,reverse=True)


def load_data(path, *, season='2026-2027'):
    root=Path(path).resolve();manifest=verify_snapshot(root)
    entries=[e for e in manifest['files'] if e['source']=='fpl_api' and e['outcome']=='success']
    def read(name):
        matches=[e for e in entries if e['relative_path'].endswith('/'+name)]
        if len(matches)!=1: raise ValueError('Ambiguous or missing official source: '+name)
        return json.loads((root/matches[0]['relative_path']).read_bytes())
    bootstrap=read('bootstrap_static.json');fixtures=read('fixtures.json')
    # Audit the entire captured pool, including unattempted and failed players.
    # Never infer successful capture from HTTP 200 alone: validation failures are
    # excluded by the normalizer, and old snapshots are not fallback responses.
    ids=sorted(p['id'] for p in bootstrap['elements'])
    normalized=normalize_snapshot(root,season=season,element_ids=ids,allow_missing=True)
    rules=bootstrap['game_settings']
    if any(rules[k]!=v for k,v in dict(squad_squadsize=15,squad_squadplay=11,squad_team_limit=3).items()):
        raise ValueError('Unsupported squad rules in snapshot')
    if {p['id']:p['squad_select'] for p in bootstrap['element_types']}!={1:2,2:5,3:5,4:3}:
        raise ValueError('Unsupported position rules')
    return dict(players=bootstrap['elements'],teams=bootstrap['teams'],events=bootstrap['events'],fixtures=fixtures,
                histories=normalized['labels'] if normalized else [],quarantine=normalized['quarantine'] if normalized else [],
                as_of_at=max(utc(e.get('available_at',e['retrieved_at'])) for e in entries).isoformat(),
                snapshot_id=manifest['run_id'],snapshot_path=str(root),season=season,rules=rules,
                manifest_sha256=hashlib.sha256((root/'manifest.json').read_bytes()).hexdigest(),
                coverage=normalized['quality'],
                scoring=bootstrap.get('game_config',{}).get('scoring',{}))
