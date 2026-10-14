"""Plan/evaluate transfer sequences against holding, with optional sensitivity."""
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import numpy as np
from fpl_model.chips import REBUILDS, LABELS, validate_chip_plan, normalize_chip_inventory
from fpl_model.my_team import validate_profile
from fpl_model.optimizer.transfer_sequences import optimize_sequence
from fpl_model.optimizer.transfers import NoTransferSolution
from fpl_model.optimizer.squad import evaluate_squad
from fpl_model.optimizer.lineup import refine_plan

VERSION='transfer_sequences_chips_v3'


def _evaluate(plan,bundle):
    values=[];summaries=[]
    for event,step in zip(bundle['events'],plan['steps']):
        if step['event']!=event:raise ValueError('Planens GWs matcher ikke prognosen.')
        lineup=plan['lineups'].get(event) or plan['lineups'].get(str(event))
        scenario=bundle['scenarios'][event]
        evaluation=evaluate_squad(lineup,bundle['rows'][event],scenario['points'],scenario['played'],chip=step.get('chip'))
        v=evaluation['points']-step['hits'];values.append(v)
        previous=plan.get('candidate_lineups',{}).get(event) or plan.get('candidate_lineups',{}).get(str(event))
        previous_mean=float(evaluate_squad(previous,bundle['rows'][event],scenario['points'],scenario['played'],chip=step.get('chip'))['points'].mean())-step['hits'] if previous else None
        summaries.append(dict(event=event,mean=float(v.mean()),p10=float(np.quantile(v,.1)),
                              p90=float(np.quantile(v,.9)),bench_mean=float(evaluation['bench_points'].mean()),
                              chip=step.get('chip'),bench_contribution_kind=evaluation['bench_contribution_kind'],hits=step['hits'],objective=lineup['objective']-step['hits'],
                              previous_lineup_mean=previous_mean,
                              lineup_gain=float(v.mean())-previous_mean if previous_mean is not None else None))
    return values,summaries


def compare_sequences(bundle,profile,*,max_per_gw=2,max_total=4,locked=(),excluded=(),
                      allow_hits=False,bench_weight=.1,time_limit=30,progress=None,chip_plan=None):
    if 'planning_scenarios' not in bundle:raise ValueError('Mangler separate scenarier til planlægning; genberegn prognosecache.')
    lineup_cache={}
    validate_profile(profile,bundle['players'],season=bundle['season'])
    ids={p['id'] for p in bundle['players']};owned={r['player_id'] for r in profile['players']}
    if not set(locked)<=owned or not set(excluded)<=ids or set(locked)&set(excluded):
        raise ValueError('Ukendte eller modstridende behold/udeluk-valg.')
    if type(max_per_gw) is not int or not 0<=max_per_gw<=15 or type(max_total) is not int or not 0<=max_total<=60:
        raise ValueError('Ugyldige transfergrænser.')
    chip_context=dict(deadlines=bundle['metadata']['deadlines'],origin_at=bundle['metadata']['forecast_origin_at'])
    chip_plan=validate_chip_plan(chip_plan or {},profile,bundle['events'],**chip_context)
    config=dict(max_per_gw=max_per_gw,max_total=max_total,locked=sorted(locked),excluded=sorted(excluded),
                allow_hits=allow_hits,bench_weight=bench_weight,time_limit=time_limit)
    packages=[];failures=[];hold_values=None
    counts=list(range(min(max_per_gw,max_total)+1))
    jobs=[('hold',0)]+[('ordinary',c) for c in counts]
    first=bundle['events'][0];first_chip=chip_plan.get(first)
    if chip_plan:jobs += [('chip',c) for c in ([None] if first_chip in REBUILDS else counts)]
    active=normalize_chip_inventory(profile).get('active_chip')
    binding=bool(active and active['event'] in bundle['events'])
    existing_hits=profile.get('pre_transfer_state',{}).get('existing_hits',0) if profile['transfers_made'] else 0
    if existing_hits and profile['pre_transfer_state'].get('event')!=first:
        raise ValueError('Bekræft eksisterende hits for den aktuelle GW.')
    for family,count in jobs:
        label=('Behold holdet hele horisonten' if family=='hold' else
               ('Fri omlægning' if count is None else f'{count} nu → bedste fortsættelse'))
        if family=='chip':label+=' · '+', '.join(f'{LABELS[c]} GW{e}' for e,c in sorted(chip_plan.items()))
        if progress:progress(label+' …')
        settings=dict(max_per_gw=0,max_total=0,bench_weight=bench_weight,time_limit=time_limit) if family=='hold' else config
        try:
            plan=optimize_sequence(bundle['rows'],profile,first_count=count,
                chip_plan=chip_plan if family=='chip' else {},chip_context=chip_context,**settings)
        except NoTransferSolution as exc:
            if family=='hold':raise
            failures.append(dict(first_count=count,comparison_family=family,reason=str(exc)));continue
        plan['plan_id']='hold' if family=='hold' else ('chip_rebuild' if count is None else ('chip_' if family=='chip' else '')+f'first_{count}')
        plan.update(label=label,comparison_family=family,hypothetical=binding and family!='chip')
        first_step=plan['steps'][0];first_step['new_hits']=first_step['hits']
        applied_existing=0 if family=='chip' and first_chip in REBUILDS else existing_hits
        first_step['existing_hits']=applied_existing;first_step['hits']+=applied_existing;plan['hits']+=applied_existing
        refine_plan(plan,bundle,lineup_cache)
        values,summaries=_evaluate(plan,bundle)
        if family=='hold':hold_values=values
        for i,row in enumerate(summaries):row['gain']=float((values[i]-hold_values[i]).mean())
        plan.update(per_gw=summaries,total_points=sum(r['mean'] for r in summaries),
                    total_gain=sum(r['gain'] for r in summaries),next_gw_gain=summaries[0]['gain'])
        packages.append(plan)
    rank=lambda p:(p['objective'],-sum(s['count'] for s in p['steps']),-(p['first_count'] or 0))
    ordinary=max((p for p in packages if p['comparison_family']!='chip'),key=rank)
    for p in packages:
        p['gain_vs_best_no_chip']=p['total_points']-ordinary['total_points']
    candidates=[p for p in packages if not p['hypothetical']]
    best=max(candidates,key=rank) if candidates else None
    config['chip_plan']=chip_plan
    root=Path(__file__).parent
    code={p:hashlib.sha256((root/p).read_bytes()).hexdigest() for p in
          ['sequence_planner.py','optimizer/transfer_sequences.py','optimizer/squad.py','optimizer/lineup.py','my_team.py','chips.py']}
    return dict(version=VERSION,scope='transfer_sequences',created_at=datetime.now(timezone.utc).isoformat(),
                profile=deepcopy(profile),forecast=deepcopy(bundle['metadata']),config=config,planner_code_sha256=code,
                players_by_event=bundle['rows'],odds_coverage=bundle['coverage'],packages=packages,
                unavailable_packages=failures,recommendation=dict(plan_id=best['plan_id'] if best else None,
                    criterion='optimizer_objective',not_simulated_points_optimum=True),
                limitations=[
                    'Fremtidige transfers og opstillinger planlægges med samme information som i dag; genplanlæg efter nye nyheder.',
                    'Ingen værdi sat på ukendt fremtidig information eller resterende transfers efter horisonten. Chips placeres manuelt; ingen automatisk GW19-strategi.',
                    'Faste fremtidige priser. Oprindelig salgsværdi gælder kun indtil første salg; genkøb sker til købspris.',
                    'Kandidattrupper findes med vægtet bænk. XI, bænkerækkefølge og anfører/vice vælges udtømmende inkl. autosubs i planlægningsscenarier; evaluering er separat.',
                    'Solverens gap gælder kun kandidatsøgningen. Ingen garanti for globalt optimale transfertrupper inklusive autosubs.',
                    'Skadesantagelser pr. GW er scenarier, ikke kalibrerede medicinske sandsynligheder. Uden override videreføres nuværende faktor.',
                    'Uafhængige GWs; ingen simuleret skade-/raskmeldingsproces. Odds-fallback og blanke/dobbelte GWs følger kampplanen.'])


def compare_sensitivity(report,alternative_bundle,*,label,progress=None):
    """Revalue frozen plans AND reoptimize separately, never mix their claims."""
    a,b=report['forecast'],alternative_bundle['metadata']
    for key in ('snapshot_id','manifest_sha256','forecast_origin_at','config','draws','seed','deadlines','code_sha256','input_sources'):
        # JSON roundtrips may stringify the event keys in deadlines.
        if json.dumps(a.get(key),sort_keys=True)!=json.dumps(b.get(key),sort_keys=True):
            raise ValueError('Følsomhed kræver samme data, GWs, origin, konfiguration og seed.')
    base_version=lambda m:m.get('base_model_version',m['model_version'])
    if base_version(a)!=base_version(b) or json.dumps(report['odds_coverage'],sort_keys=True)!=json.dumps(alternative_bundle['coverage'],sort_keys=True):
        raise ValueError('Følsomhed kræver samme model og odds-input; kun tilgængelighed må ændres.')
    alternative=compare_sequences(alternative_bundle,report['profile'],**report['config'],progress=progress)
    fixed=[];hold=None
    for plan in report['packages']:
        values,rows=_evaluate(plan,alternative_bundle)
        if hold is None:hold=values
        gain=sum(float((v-h).mean()) for v,h in zip(values,hold))
        fixed.append(dict(plan_id=plan['plan_id'],label=plan['label'],base_points=plan['total_points'],
                          alternative_points=sum(r['mean'] for r in rows),gain_in_base=plan['total_gain'],
                          gain_in_alternative=gain,change_in_gain=gain-plan['total_gain']))
    first=lambda r: next((p['steps'][0] for p in r['packages'] if p['plan_id']==r['recommendation']['plan_id']),None)
    x,y=first(report),first(alternative)
    changed=None if x is None or y is None else (x['in'],x['out'])!=(y['in'],y['out'])
    return dict(label=label,base_cache_key=a['cache_key'],alternative=alternative,fixed_plans=fixed,
                changed_first_transfers=changed,
                interpretation='Hypotetisk følsomhed; ikke nye nyheder eller dokumenteret modelperformance.')
