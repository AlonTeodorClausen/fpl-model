"""Exactly three frequency-prior variants on an anchored development evaluation.

No network, tuning, default promotion, or changes to the historical row universe.
"""
from dataclasses import asdict, replace
from datetime import datetime, timezone
import hashlib
from importlib.metadata import version
import json
from pathlib import Path
from uuid import uuid4
import numpy as np

from fpl_model.backtest.walk_forward import evaluate_sample, _metrics
from fpl_model.models.baseline import BaselineConfig, model_version

EXPERIMENT_VERSION='frequency_prior_three_variants_v1'
STRENGTHS=(1.0,0.25,0.10)
METRICS=('minutes_bias','minutes_mae','minutes_rmse','dnp_brier','dnp_predicted',
         'dnp_observed','point_mae','point_rmse','point_crps')


def digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,allow_nan=False).encode()).hexdigest()


def row_contract(rows):
    fields=('event','player_id','position','fixture_ids','forecast_origin_at','actual','actual_minutes',
            'actual_dnp','reference','reference_minutes','reference_dnp','prior_rows')
    return [{key:r[key] for key in fields} for r in sorted(rows,key=lambda r:(r['event'],r['player_id']))]


def grouped_metrics(evaluation, *, seed, label, reference=False):
    rows=evaluation['rows']
    diagnostic={(r['event'],r['player_id']):r for r in evaluation['minute_diagnostics']['rows']}
    enriched=[{**r,**{k:diagnostic[r['event'],r['player_id']][k]
                     for k in ('regular','start_group','minute_group')}} for r in rows]
    groups=[('scope','all',enriched),('scope','regular',[r for r in enriched if r['regular']])]
    for dimension,key in [('position','position'),('gameweek','event'),('start_history','start_group'),
                          ('minute_history','minute_group')]:
        groups += [(dimension,str(g),[r for r in enriched if r[key]==g]) for g in sorted({r[key] for r in enriched})]
    groups += [('regular_position',str(p),[r for r in enriched if r['regular'] and r['position']==p])
               for p in sorted({r['position'] for r in enriched if r['regular']})]
    groups += [('position_start_history',f'{p}/{g}',[r for r in enriched if r['position']==p and r['start_group']==g])
               for p,g in sorted({(r['position'],r['start_group']) for r in enriched})]
    out=[]
    for dimension,group,subset in groups:
        m=_metrics(subset)
        if not subset:
            values={key:None for key in METRICS}
        else:
            points=m['reference' if reference else 'model']
            minutes=m['minutes']['reference'] if reference else m['minutes']
            values=dict(minutes_bias=float(np.mean([r['reference_minutes' if reference else 'predicted_minutes']-r['actual_minutes'] for r in subset])),
                minutes_mae=minutes['mae'],minutes_rmse=minutes['rmse'],
                dnp_brier=m['dnp']['reference_brier' if reference else 'brier'],
                dnp_predicted=float(np.mean([r['reference_dnp' if reference else 'p_no_play'] for r in subset])),
                dnp_observed=m['dnp']['observed_rate'],point_mae=points['mae'],point_rmse=points['rmse'],
                # A point forecast has a degenerate distribution: its CRPS = MAE.
                point_crps=points['mae'] if reference else points['crps'])
        out.append(dict(seed=seed,model_version=label,dimension=dimension,group=group,n=len(subset),
                        players=len({r['player_id'] for r in subset}),**values))
    return out


def seed_sensitivity(metrics):
    """Paired seed deltas; Monte Carlo spread is NOT statistical uncertainty."""
    lookup={(r['seed'],r['model_version'],r['dimension'],r['group']):r for r in metrics}
    out=[]
    for left,right in [('component_frequency_025_v1','component_baseline_v1'),
                       ('component_frequency_010_v1','component_baseline_v1'),
                       ('component_frequency_010_v1','component_frequency_025_v1')]:
        for dimension,group in sorted({(r['dimension'],r['group']) for r in metrics}):
            pairs=[(r,lookup[s,left,dimension,group]) for (s,m,d,g),r in lookup.items()
                   if m==right and d==dimension and g==group]
            row=dict(candidate=left,comparator=right,dimension=dimension,group=group,seeds=len(pairs),n=pairs[0][0]['n'])
            for key in METRICS:
                delta=[b[key]-a[key] for a,b in pairs if a[key] is not None and b[key] is not None]
                for suffix,fn in [('mean',np.mean),('min',np.min),('max',np.max)]:
                    row[f'{key}_delta_{suffix}']=float(fn(delta)) if delta else None
            out.append(row)
    return out


def run_experiment(data, anchor, *, seeds=None):
    """Seed #1 reproduces the supplied existing baseline evaluation exactly."""
    original=anchor['evaluation']
    if data['snapshot_id']!=anchor['snapshot_id'] or data.get('manifest_sha256')!=anchor.get('manifest_sha256'):
        raise ValueError('Anchor snapshot does not match the input snapshot')
    config=BaselineConfig(**original['config'])
    if config.frequency_prior_games!=1 or config.minutes_prior_games!=1 or original['model_version']!='component_baseline_v1':
        raise ValueError('Anchor must use baseline v1 with both prior strengths 1.0')
    primary=original['seed'];seeds=list(seeds) if seeds is not None else [primary,primary+1,primary+2]
    if not 1<=len(seeds)<=3 or len(set(seeds))!=len(seeds) or seeds[0]!=primary or any(type(s)!=int or s<0 for s in seeds):
        raise ValueError('Use 1–3 distinct nonnegative seeds, beginning with the anchor seed')
    expected=row_contract(original['rows'])
    if not expected: raise ValueError('No existing evaluation rows')
    variants=[];runs=[];metrics=[]
    for strength in STRENGTHS:
        c=replace(config,frequency_prior_games=strength,minutes_prior_games=1.0)
        label=model_version(c)
        variants.append(dict(model_version=label,**asdict(c)))
        for seed in seeds:
            result=evaluate_sample(data,c,draws=original['draws'],seed=seed)
            if row_contract(result['rows'])!=expected:
                raise ValueError('Evaluation rows/targets/reference changed; refusing a different comparison basis')
            if strength==1 and seed==primary and result['rows']!=original['rows']:
                raise ValueError('Baseline rows no longer reproduce the anchored predictions')
            runs.append(dict(model_version=label,seed=seed,evaluation=result))
            metrics+=grouped_metrics(result,seed=seed,label=label)
            if strength==1: metrics+=grouped_metrics(result,seed=seed,label='historical_mean_reference',reference=True)
    root=Path(__file__).parent
    return dict(experiment_version=EXPERIMENT_VERSION,data_role='development',default_model_changed=False,
        snapshot_id=data['snapshot_id'],snapshot_path=data.get('snapshot_path'),manifest_sha256=data.get('manifest_sha256'),
        anchor_sha256=digest(anchor),evaluation_rows_sha256=digest(expected),n=len(expected),
        gameweeks=sorted({r['event'] for r in expected}),seeds=seeds,draws=original['draws'],
        seed_strategy='base_seed + event; same strategy/count in all variants; NOT fully coupled random draws',
        variants=variants,runs=runs,metrics=metrics,seed_sensitivity=seed_sensitivity(metrics),
        seed_summary=summarize_seeds(metrics),
        group_definitions={k:original['minute_diagnostics'][k] for k in ('regular_rule','start_group_rule','minute_group_rule')}
            if 'minute_diagnostics' in original else {k:runs[0]['evaluation']['minute_diagnostics'][k]
                for k in ('regular_rule','start_group_rule','minute_group_rule')},
        code_sha256={name:hashlib.sha256((root/name).read_bytes()).hexdigest() for name in
            ('minutes_experiment.py','models/baseline.py','simulation.py','scoring.py','diagnostics.py','backtest/walk_forward.py','history_coverage.py')},
        runtime_versions={name:version(name) for name in ('numpy','scipy','pandas')},
        limitations=['GW3–5 were already used for diagnostics: development data, not independent test performance.',
            'Extra seeds quantify simulation noise only, not sampling uncertainty or statistically secure improvement.',
            'The reference is a point forecast; its reported CRPS is its degenerate-distribution CRPS (= MAE).',
            'Groups use only earlier matches; regular players can change groups across GWs.',
            *original['limitations']])


def save_experiment(report, output=None):
    from fpl_model.config import ROOT, RAW
    import pandas as pd
    out=Path(output) if output is not None else ROOT/'artifacts/minutes_experiments'/(
        datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')+'_'+uuid4().hex[:8])
    protected=[RAW.resolve()]
    if report.get('snapshot_path'): protected.append(Path(report['snapshot_path']).resolve().parent)
    if any(out.resolve().is_relative_to(p) for p in protected): raise ValueError('Output cannot be inside raw storage')
    out.mkdir(parents=True,exist_ok=False)
    (out/'comparison.json').write_text(json.dumps(report,indent=2,ensure_ascii=False,allow_nan=False)+'\n')
    pd.DataFrame(report['metrics']).to_csv(out/'metrics.csv',index=False)
    pd.DataFrame(report['seed_sensitivity']).to_csv(out/'seed_sensitivity.csv',index=False)
    pd.DataFrame(report.get('seed_summary',summarize_seeds(report['metrics']))).to_csv(out/'seed_summary.csv',index=False)
    return out


def comparison_paths(root):
    return sorted(Path(root).glob('*/comparison.json'),reverse=True)


def summarize_seeds(metrics):
    """Mean/min/max of metric estimates; observations are not replicated per seed."""
    from collections import defaultdict
    grouped=defaultdict(list)
    for row in metrics:
        grouped[row['model_version'],row['dimension'],row['group']].append(row)
    out=[]
    expected_seeds={r['seed'] for r in metrics}
    for (model,dimension,group),rows in sorted(grouped.items()):
        rows=sorted(rows,key=lambda r:r['seed'])
        seeds=[r['seed'] for r in rows]
        if len(set(seeds))!=len(seeds) or set(seeds)!=expected_seeds or len({(r['n'],r['players']) for r in rows})!=1:
            raise ValueError('Seed summaries require unique, matching seeds and observation counts')
        result=dict(model_version=model,dimension=dimension,group=group,n=rows[0]['n'],
                    players=rows[0]['players'],seed_count=len(rows))
        for key in METRICS:
            values=[r[key] for r in rows if r[key] is not None]
            if values and len(values)!=len(rows): raise ValueError('Metric missing in only some seeds')
            for suffix,fn in [('mean',np.mean),('min',np.min),('max',np.max)]:
                result[f'{key}_{suffix}']=float(fn(values)) if values else None
        out.append(result)
    return out


def summarize_saved(path):
    """Derive a new summary without changing saved predictions or their provenance."""
    path=Path(path)
    raw=path.read_bytes();report=json.loads(raw)
    report['seed_summary']=summarize_seeds(report['metrics'])
    report['derived_from_path']=str(path.resolve())
    report['derived_from_sha256']=hashlib.sha256(raw).hexdigest()
    report['summary_code_sha256']=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    report['summary_note']='Means and ranges across existing seeds: simulation variation, not match-sampling uncertainty.'
    return report
