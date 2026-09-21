"""Offline Step 2D audit of verified Step 2C reports; no fetching or model inputs."""
import argparse
import hashlib
import json
import sys
from collections import Counter
from pathlib import Path

if __package__ in {None,''}:
    sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from fpl_model.io import verify_snapshot
from fpl_model.label_contracts import utc
from fpl_model.player_fixture_labels import normalize_snapshot
from fpl_model.observation_selection import (select_as_of,select_outcome,completeness_audit,
                                           fixture_universe,transition_audit)


def _bytes(data):
    return (json.dumps(data,indent=2,sort_keys=True,ensure_ascii=False,allow_nan=False)+'\n').encode()


def load_report(path):
    path=Path(path).resolve()
    marker=json.loads((path/'COMPLETE.json').read_text())
    names={'labels.jsonl','quarantine.jsonl','quality.json'}
    if marker.get('schema_version')!=1 or set(marker['files'])!=names:
        raise ValueError('Unknown Step 2C report contract')
    for name,sha in marker['files'].items():
        p=path/name
        if p.is_symlink() or hashlib.sha256(p.read_bytes()).hexdigest()!=sha:
            raise ValueError('Corrupt Step 2C report')
    quality=json.loads((path/'quality.json').read_text())
    labels=[json.loads(line) for line in (path/'labels.jsonl').read_text().splitlines()]
    quarantine=[json.loads(line) for line in (path/'quarantine.jsonl').read_text().splitlines()]
    snapshot=Path(quality['snapshot_path'])
    manifest=verify_snapshot(snapshot)
    if hashlib.sha256((snapshot/'manifest.json').read_bytes()).hexdigest()!=quality['manifest_sha256']:
        raise ValueError('Source snapshot mismatch')
    reproduced=normalize_snapshot(snapshot,season=quality['season'],element_ids=quality['requested_element_ids'])
    if reproduced!={'labels':labels,'quarantine':quarantine,'quality':quality}:
        raise ValueError('Report differs from official normalized source')
    def raw(suffix):
        entries=[e for e in manifest['files'] if e['source']=='fpl_api' and e['relative_path'].endswith('/'+suffix) and e['outcome']=='success']
        if len(entries)!=1:raise ValueError('Ambiguous source context')
        e=entries[0]
        return json.loads((snapshot/e['relative_path']).read_bytes()),utc(e.get('available_at',e['retrieved_at']))
    bootstrap,bt=raw('bootstrap_static.json');fixtures,ft=raw('fixtures.json')
    return dict(path=str(path),quality=quality,labels=labels,quarantine=quarantine,
                bootstrap=bootstrap,fixtures=fixtures,context_available_at=max(bt,ft),
                report_sha256=hashlib.sha256((path/'COMPLETE.json').read_bytes()).hexdigest())


def _example(selection,pid,fid):
    row=selection.observation
    return {'player_id':pid,'fixture_id':fid,'purpose':selection.purpose,'status':selection.status,
            'cutoff_at':selection.cutoff_at,'snapshot':row['source_snapshot_id'] if row else None,
            'label_state':row['label_state'] if row else None,'minutes':row['minutes'] if row else None,
            'total_points':row['total_points'] if row else None,'available_at':row['available_at'] if row else None,
            'eligible_versions':selection.eligible_versions,'tie_versions':selection.tie_versions,
            'duplicate_versions':selection.duplicate_versions,'issues':selection.issues}


def audit_reports(report_paths,*,cutoff_at,events):
    cutoff=utc(cutoff_at)
    if not events or any(type(e) is not int or e<=0 for e in events):
        raise ValueError('Explicit positive event IDs required')
    loaded=sorted([load_report(p) for p in report_paths],key=lambda d:d['quality']['source_snapshot_id'])
    if not loaded or len({d['quality']['source_snapshot_id'] for d in loaded})!=len(loaded):
        raise ValueError('Need distinct source snapshot reports')
    seasons={d['quality']['season'] for d in loaded}
    if len(seasons)!=1:raise ValueError('Cannot mix seasons')
    season=next(iter(seasons))
    ids=sorted({i for d in loaded for i in d['quality']['requested_element_ids']})
    if len(ids)>20:raise ValueError('Step 2D audit is bounded to 20 players')
    rows=[r for d in loaded for r in d['labels']]
    quarantine=[q for d in loaded for q in d['quarantine']]
    contexts=sorted(loaded,key=lambda d:(d['context_available_at'],d['quality']['source_snapshot_id']))
    if len({d['context_available_at'] for d in contexts})!=len(contexts):
        raise ValueError('Equal-time context versions require review')
    latest=contexts[-1]
    past=[d for d in contexts if d['context_available_at']<=cutoff]
    historical=past[-1] if past else latest
    fixtures=[f for f in latest['fixtures'] if f['event'] in events]
    pairs=[(p,f['id']) for p in ids for f in fixtures]
    def universe(context,at=None):
        b=context['bootstrap']
        return fixture_universe(season=season,players=b['elements'],teams=b['teams'],fixtures=context['fixtures'],
                pairs=pairs,observations=rows,context_available_at=context['context_available_at'],cutoff_at=at)
    info_completeness=completeness_audit(universe(historical,cutoff),rows,season=season,purpose='as_of',cutoff_at=cutoff,quarantine=quarantine)
    outcome_completeness=completeness_audit(universe(latest),rows,season=season,purpose='outcome',quarantine=quarantine)
    pair_counts=Counter((r['player_id'],r['fixture_id']) for r in rows)
    as_of=[];outcomes=[];deadline_examples=[]
    event_by_id={e['id']:e for e in latest['bootstrap']['events']}
    fixture_by_id={f['id']:f for f in latest['fixtures']}
    for pid,fid in sorted(pair_counts):
        a=select_as_of(rows,season=season,player_id=pid,fixture_id=fid,cutoff_at=cutoff)
        o=select_outcome(rows,season=season,player_id=pid,fixture_id=fid)
        as_of.append(_example(a,pid,fid));outcomes.append(_example(o,pid,fid))
        event=event_by_id.get(fixture_by_id[fid]['event'],{})
        if event.get('deadline_time'):
            # Retrospective demonstration only: latest schedule/deadline version
            # is not asserted to have been known at that historical origin.
            at_origin=select_as_of(rows,season=season,player_id=pid,fixture_id=fid,cutoff_at=event['deadline_time'])
            deadline_examples.append({'player_id':pid,'fixture_id':fid,'illustrative_forecast_origin_at':event['deadline_time'],
                'origin_basis':'latest observed event deadline; historical deadline version not verified',
                'as_of':_example(at_origin,pid,fid),'outcome':_example(o,pid,fid)})
    transitions=transition_audit(rows)
    source_refs=[{'report_path':d['path'],'source_snapshot_id':d['quality']['source_snapshot_id'],
                  'raw_snapshot_path':d['quality']['snapshot_path'],'report_sha256':d['report_sha256'],
                  'manifest_sha256':d['quality']['manifest_sha256']} for d in loaded]
    identity={'schema_version':1,'sources':source_refs,'cutoff_at':cutoff.isoformat(),'events':sorted(set(events))}
    audit_id='step2d_'+hashlib.sha256(_bytes(identity)).hexdigest()[:16]
    unassigned=[q for q in quarantine if not isinstance(q.get('official_history'),dict) or type(q['official_history'].get('fixture')) is not int]
    return {**identity,'audit_id':audit_id,'season':season,'player_ids':ids,
            'summary':{'unique_player_fixtures':len(pair_counts),'observations':len(rows),
                'requested_universe_pairs':len(pairs),'quarantined_source_rows':len(quarantine),
                'unassigned_quarantined_rows':len(unassigned),
                'observations_per_pair_distribution':dict(sorted(Counter(pair_counts.values()).items())),
                'state_transitions':dict(sorted(Counter(t['earlier_state']+' -> '+t['later_state'] for t in transitions['transitions']).items())),
                'pairs_with_changed_fields':sum(bool(t['changed_fields']) for t in transitions['transitions'])},
            'observations_per_pair':[dict(player_id=p,fixture_id=f,count=n) for (p,f),n in sorted(pair_counts.items())],
            'transitions':transitions,'as_of_completeness':info_completeness,'outcome_completeness':outcome_completeness,
            'unassigned_quarantine':unassigned,'as_of_examples':as_of,'outcome_examples':outcomes,
            'illustrative_origin_examples':deadline_examples,
            'limitations':['Requested universe uses latest captured GW fixture IDs and is an audit scope, not historical participation evidence.',
                'No membership intervals are inferred; unobserved pairs remain unresolved.',
                'As-of uses inclusive availability cutoff; outcomes are separately tagged outcome_only.',
                'No outcomes, later contexts or revisions are supplied as forecasting features.']}


def write_audit(report,output_root):
    root=Path(output_root).resolve()
    for source in report['sources']:
        if root.is_relative_to(Path(source['raw_snapshot_path']).resolve().parent) or root.is_relative_to(Path(source['report_path']).resolve()):
            raise ValueError('Audit output must be outside protected inputs')
    directory=root/report['audit_id'];directory.mkdir(parents=True,exist_ok=False)
    payloads={'quality.json':report,'transitions.json':report['transitions']}
    checksums={}
    for name,value in payloads.items():
        body=_bytes(value)
        with (directory/name).open('xb') as f:f.write(body)
        checksums[name]=hashlib.sha256(body).hexdigest()
    with (directory/'COMPLETE.json').open('xb') as f:f.write(_bytes({'schema_version':1,'files':checksums}))
    return directory


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--reports',type=Path,nargs='+',required=True)
    parser.add_argument('--cutoff-at',required=True)
    parser.add_argument('--events',type=int,nargs='+',required=True)
    parser.add_argument('--output-root',type=Path,required=True)
    args=parser.parse_args(argv)
    report=audit_reports(args.reports,cutoff_at=args.cutoff_at,events=args.events)
    directory=write_audit(report,args.output_root)
    print(f"audit: {directory}\nsummary: {json.dumps(report['summary'],sort_keys=True)}")
    return 0


if __name__=='__main__':
    raise SystemExit(main())
