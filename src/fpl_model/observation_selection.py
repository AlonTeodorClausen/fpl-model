"""Separate information-state and outcome selection over verified FPL observations.

No forecast features are computed. Future records are filtered by availability
before payload, state, provenance conflict or tie inspection. Outcomes are tagged
outcome_only and cannot pass the information-result accessor.
"""
import copy
import json
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field

from fpl_model.label_contracts import utc
from fpl_model.player_fixture_labels import STAT_FIELDS


@dataclass(frozen=True)
class Selection:
    purpose: str
    status: str
    observation: dict | None = None
    cutoff_at: str | None = None
    eligible_versions: list = field(default_factory=list)
    duplicate_versions: list = field(default_factory=list)
    tie_versions: list = field(default_factory=list)
    issues: list = field(default_factory=list)

    def for_information(self):
        """Explicit gate for future information consumers; never accepts outcomes."""
        if self.purpose != 'as_of_information' or self.status != 'selected':
            raise ValueError('Only a selected as-of observation is information-eligible')
        _validate(self.observation)
        if utc(self.observation['available_at']) > utc(self.cutoff_at):
            raise ValueError('Observation is after information cutoff')
        return copy.deepcopy(self.observation)


def _positive(value):
    if type(value) is not int or value <= 0:
        raise ValueError('Expected positive canonical FPL ID')


def _query(season, player_id, fixture_id):
    if not isinstance(season, str) or not re.fullmatch(r'\d{4}-\d{4}', season) or int(season[5:]) != int(season[:4])+1:
        raise ValueError('Explicit season is required')
    _positive(player_id)
    _positive(fixture_id)


def _json(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False)


def _validate(r):
    _query(r['season'], r['player_id'], r['fixture_id'])
    if r['source'] != 'fpl_api' or r['label_state'] not in {'final', 'provisional'}:
        raise ValueError('Selectors require accepted official FPL observations')
    for k in ('team_id','opponent_team_id'):
        _positive(r[k])
    if r['team_id'] == r['opponent_team_id']:
        raise ValueError('Conflicting team identity')
    if not isinstance(r.get('source_snapshot_id'), str) or not r['source_snapshot_id']:
        raise ValueError('Missing observation version')
    expected = f"{r['season']}:{r['source_snapshot_id']}:{r['player_id']}:{r['fixture_id']}"
    if r.get('observation_id') != expected:
        raise ValueError('Conflicting observation identity')
    available = utc(r['available_at'])
    if utc(r['retrieved_at']) > available:
        raise ValueError('Availability cannot precede retrieval')
    if not r.get('provenance'):
        raise ValueError('Source provenance required')
    for p in r['provenance']:
        if p['source'] != 'fpl_api' or not p['relative_path'].startswith('raw/fpl_api/') or not re.fullmatch(r'[0-9a-f]{64}', p['sha256']):
            raise ValueError('Invalid official provenance')
        if utc(p['retrieved_at']) > available or utc(p.get('effective_available_at', p.get('available_at', p['retrieved_at']))) > available:
            raise ValueError('Context unavailable at observation availability')
    h = r['official_history']
    for output, raw in (('player_id','element'),('fixture_id','fixture'),('event','round'),
                        ('opponent_team_id','opponent_team'),('was_home','was_home'),('kickoff_time','kickoff_time')):
        if type(r[output]) is not type(h[raw]) or r[output] != h[raw]:
            raise ValueError('Normalized identity differs from official history')
    if type(r['was_home']) is not bool or type(r['minutes']) is not int or type(r['total_points']) is not int:
        raise ValueError('Invalid official label values')
    utc(r['kickoff_time'])
    for k in STAT_FIELDS:
        if r.get(k) != h.get(k):
            raise ValueError('Normalized statistic differs from official history')


def _ref(r):
    return {'snapshot':r['source_snapshot_id'], 'observation_id':r['observation_id'],
            'available_at':utc(r['available_at']).isoformat(), 'retrieved_at':utc(r['retrieved_at']).isoformat(),
            'raw_files':sorted((p['relative_path'],p['sha256']) for p in r['provenance'])}


def _rank(r):
    # Tie order is arbitrary but public and stable; it never decides conflicting values.
    return (utc(r['available_at']), utc(r['retrieved_at']), r['source_snapshot_id'],
            tuple(sorted((p['relative_path'],p['sha256']) for p in r['provenance'])), r['observation_id'])


def _semantic(r):
    ignored = {'provenance','source_snapshot_id','observation_id','source_history_index',
               'retrieved_at','available_at','history_available_at','source_published_at'}
    return _json({k:v for k,v in r.items() if k not in ignored})


def _versions(rows):
    """Exact duplicates are explicitly reported; conflicts are never tie-broken."""
    groups = defaultdict(list)
    for r in rows:
        _validate(r)
        groups[r['observation_id']].append(r)
    unique, duplicates, issues = [], [], []
    for key, copies in sorted(groups.items()):
        distinct = {_json(r) for r in copies}
        if len(distinct) > 1:
            issues.append({'kind':'same_version_conflict','observation_id':key})
        else:
            unique.append(copies[0])
            if len(copies) > 1:
                duplicates.append({'observation_id':key,'copies':len(copies)})
    bytime = defaultdict(list)
    for r in unique:
        bytime[utc(r['available_at'])].append(r)
    for time, simultaneous in sorted(bytime.items()):
        if len({_semantic(r) for r in simultaneous}) > 1:
            issues.append({'kind':'equal_availability_conflict','available_at':time.isoformat(),
                           'observation_ids':sorted(r['observation_id'] for r in simultaneous)})
    return sorted(unique, key=_rank), duplicates, issues


def _eligible(observations, season, player_id, fixture_id, cutoff):
    rows=[]
    for r in observations:
        if not isinstance(r,dict):
            raise ValueError('Expected normalized observation, not a selection wrapper')
        if (r.get('season'),r.get('player_id'),r.get('fixture_id')) != (season,player_id,fixture_id):
            continue
        available = utc(r['available_at'])
        if cutoff is not None and available > cutoff:
            continue  # Do not inspect future state, values, provenance or conflicts.
        rows.append(r)
    return rows


def _select(observations, *, season, player_id, fixture_id, cutoff, states, purpose):
    _query(season,player_id,fixture_id)
    rows = _eligible(observations,season,player_id,fixture_id,cutoff)
    unique, duplicates, issues = _versions(rows)
    info = dict(purpose=purpose,cutoff_at=cutoff.isoformat() if cutoff else None,
                duplicate_versions=duplicates,issues=issues)
    if issues:
        return Selection(status='conflict',**info)
    allowed = [r for r in unique if r['label_state'] in states]
    refs = [_ref(r) for r in allowed]
    if not allowed:
        status = ('no_final_observation' if purpose=='outcome_only' else
                  'no_allowed_state' if unique else 'no_eligible_observation')
        return Selection(status=status,eligible_versions=refs,**info)
    chosen = allowed[-1]
    ties = [_ref(r) for r in allowed if utc(r['available_at']) == utc(chosen['available_at'])]
    return Selection(status='selected',observation=copy.deepcopy(chosen),eligible_versions=refs,
                     tie_versions=ties if len(ties)>1 else [],**info)


def select_as_of(observations, *, season, player_id, fixture_id, cutoff_at,
                 allowed_states=('provisional','final')):
    cutoff = utc(cutoff_at)
    states = set(allowed_states)
    if not states or not states <= {'provisional','final'}:
        raise ValueError('Allowed states must be a nonempty subset of accepted label states')
    return _select(observations,season=season,player_id=player_id,fixture_id=fixture_id,
                   cutoff=cutoff,states=states,purpose='as_of_information')


def select_outcome(observations, *, season, player_id, fixture_id, outcome_cutoff_at=None):
    """Latest final; optional target-vintage cutoff is NOT a forecast-origin cutoff."""
    cutoff = None if outcome_cutoff_at is None else utc(outcome_cutoff_at)
    return _select(observations,season=season,player_id=player_id,fixture_id=fixture_id,
                   cutoff=cutoff,states={'final'},purpose='outcome_only')


def _quarantine_for(quarantine, season, pid, fid, cutoff):
    result=[]
    for q in quarantine:
        if q.get('season') != season:
            continue
        if cutoff is not None and utc(q['available_at']) > cutoff:
            continue
        h=q.get('official_history')
        if q.get('requested_player_id')==pid and isinstance(h,dict) and type(h.get('fixture')) is int and h['fixture']==fid:
            if q.get('source') != 'fpl_api' or utc(q['retrieved_at'])>utc(q['available_at']):
                raise ValueError('Invalid quarantine provenance')
            result.append({'snapshot':q['source_snapshot_id'],'available_at':q['available_at'],
                           'source_history_index':q['source_history_index'],'reasons':q['reasons']})
    return sorted(result,key=_json)


def completeness_audit(universe, observations, *, season, purpose, cutoff_at=None, quarantine=()):
    if purpose not in {'as_of','outcome'}:
        raise ValueError('Explicit audit purpose required')
    cutoff=utc(cutoff_at) if purpose=='as_of' or cutoff_at is not None else None
    observations=list(observations)
    pairs=[]
    seen=set()
    for expected in sorted(universe,key=lambda u:(u['player_id'],u['fixture_id'])):
        expected=copy.deepcopy(expected)
        pid,fid=expected['player_id'],expected['fixture_id']
        _query(season,pid,fid)
        if (pid,fid) in seen:
            raise ValueError('Duplicate requested pair')
        seen.add((pid,fid))
        if expected['expectation'] not in {'expected','unresolved','not_applicable'} or not expected.get('evidence'):
            raise ValueError('Expectation needs explicit evidence or unresolved reason')
        if cutoff is not None and expected.get('expectation_available_at') is not None and utc(expected['expectation_available_at'])>cutoff:
            expected.update(expectation='unresolved',evidence=['expectation_evidence_unavailable_at_cutoff'])
        selected=(select_as_of(observations,season=season,player_id=pid,fixture_id=fid,cutoff_at=cutoff)
                  if purpose=='as_of' else select_outcome(observations,season=season,player_id=pid,fixture_id=fid,outcome_cutoff_at=cutoff))
        qs=_quarantine_for(quarantine,season,pid,fid,cutoff)
        obs=selected.observation
        diagnostic=None
        if selected.status=='conflict':
            classification='conflicting_observations'
        elif qs and (obs is None or max(utc(q['available_at']) for q in qs)>=utc(obs['available_at'])):
            classification='quarantined'
        elif obs:
            classification=obs['label_state']
        elif purpose=='outcome' and _eligible(observations,season,pid,fid,cutoff):
            classification='provisional'
            diagnostic=_select(observations,season=season,player_id=pid,fixture_id=fid,
                               cutoff=cutoff,states={'provisional'},purpose='diagnostic_only').observation
        elif expected['expectation']=='unresolved':
            classification='unresolved_expectation'
        elif expected['expectation']=='not_applicable':
            classification='not_applicable'
        else:
            classification='missing_observation'
        visible=obs or diagnostic
        pairs.append({**expected,'classification':classification,
                      'appearance':('explicit_zero' if visible['minutes']==0 else 'positive_minutes') if visible and classification in {'final','provisional'} else 'unknown',
                      'selected_version':_ref(obs) if obs else None,
                      'diagnostic_version':_ref(diagnostic) if diagnostic else None,
                      'quarantine':qs,'selection_status':selected.status})
    return {'purpose':purpose,'cutoff_at':cutoff.isoformat() if cutoff else None,'pairs':pairs,
            'counts':dict(sorted(Counter(p['classification'] for p in pairs).items())),
            'appearance_counts':dict(sorted(Counter(p['appearance'] for p in pairs).items()))}


def fixture_universe(*, season,players,teams,fixtures,pairs,observations,context_available_at,cutoff_at=None):
    """Observed official history establishes only that pair; never infer tenure.

    No automatic not_applicable assignments: current team or a past appearance
    does not establish club registration for another fixture's date.
    """
    cutoff=None if cutoff_at is None else utc(cutoff_at)
    context=utc(context_available_at)
    requested=sorted(set(pairs))
    for pid,fid in requested:_query(season,pid,fid)
    if len(requested)!=len(pairs):
        raise ValueError('Duplicate requested universe pair')
    def index(rows):
        result={}
        for r in rows:
            _positive(r['id'])
            if r['id'] in result:raise ValueError('Ambiguous official identity')
            result[r['id']]=r
        return result
    if cutoff is not None and context>cutoff:
        return [dict(player_id=p,fixture_id=f,expectation='unresolved',evidence=['context_unavailable_at_cutoff']) for p,f in requested]
    ps,ts,fs=index(players),index(teams),index(fixtures)
    output=[]
    for pid,fid in requested:
        _positive(pid);_positive(fid)
        evidence=[]
        evidence_times=[]
        if pid in ps and fid in fs and all(fs[fid].get(k) in ts for k in ('team_h','team_a')):
            for r in observations:
                if r.get('season')!=season or r.get('player_id')!=pid or r.get('fixture_id')!=fid:continue
                if cutoff is not None and utc(r['available_at'])>cutoff:continue
                _validate(r)
                if r['team_id'] in (fs[fid]['team_h'],fs[fid]['team_a']):
                    evidence.append(r['observation_id'])
                    evidence_times.append(utc(r['available_at']))
        output.append(dict(player_id=pid,fixture_id=fid,expectation='expected' if evidence else 'unresolved',
                           evidence=sorted(set(evidence)) or ['historical_membership_or_fixture_context_not_established'],
                           expectation_available_at=max(context,min(evidence_times)).isoformat() if evidence_times else None))
    return output


def transition_audit(observations):
    groups=defaultdict(list)
    for r in observations:groups[(r['season'],r['player_id'],r['fixture_id'])].append(r)
    transitions,issues=[],[]
    for (season,pid,fid),rows in sorted(groups.items()):
        unique,duplicates,conflicts=_versions(rows)
        issues.extend({'season':season,'player_id':pid,'fixture_id':fid,**c} for c in conflicts)
        for d in duplicates:issues.append({'kind':'duplicate_reported','player_id':pid,'fixture_id':fid,**d})
        if conflicts:continue
        for a,b in zip(unique,unique[1:]):
            fields={}
            av={**a['official_history'],'team_id':a['team_id']}
            bv={**b['official_history'],'team_id':b['team_id']}
            for k in sorted(av.keys()|bv.keys()):
                if (k in av,av.get(k))!=(k in bv,bv.get(k)):
                    fields[k]={'earlier_present':k in av,'earlier':av.get(k),'later_present':k in bv,'later':bv.get(k)}
            transitions.append({'season':season,'player_id':pid,'fixture_id':fid,
                'earlier_snapshot':a['source_snapshot_id'],'later_snapshot':b['source_snapshot_id'],
                'earlier_state':a['label_state'],'later_state':b['label_state'],
                'earlier_available_at':a['available_at'],'later_available_at':b['available_at'],
                'changed_fields':fields,'classification':'official_revision' if fields else
                'state_transition' if a['label_state']!=b['label_state'] else 'unchanged'})
    return {'transitions':transitions,'issues':issues}
