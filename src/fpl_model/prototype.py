"""Application service; UI/CLI orchestration without changing model or solver APIs."""
from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
from importlib.metadata import version
import json
from pathlib import Path
import platform
from uuid import uuid4
import numpy as np
from fpl_model.simulation import simulate
from fpl_model.optimizer.squad import optimize_squad, evaluate_squad
from fpl_model.backtest.walk_forward import evaluate_sample, MODEL_VERSION


def run_prototype(data, event, config, *, draws=3000, seed=None, budget=100,
                  locked=(), excluded=(), bench_weight=.1):
    seed = int(np.random.SeedSequence().generate_state(1)[0]) if seed is None else int(seed)
    forecasts = simulate(data,event,config,draws=draws,seed=seed)
    table = forecasts.summary()
    team = optimize_squad(table,budget=budget,locked=locked,excluded=excluded,bench_weight=bench_weight)
    # Independent scenarios evaluate the fixed selected team, reducing MC selection optimism.
    independent = simulate(data,event,config,draws=draws,seed=seed+1)
    totals = evaluate_squad(team,table,independent.points,independent.minutes>0)
    values = totals['points']
    report = dict(snapshot_id=data['snapshot_id'],as_of_at=data['as_of_at'],
        manifest_sha256=data.get('manifest_sha256'),coverage=data.get('coverage'),
        model_version=MODEL_VERSION,created_at=datetime.now(timezone.utc).isoformat(),
        code_sha256={name:hashlib.sha256((Path(__file__).parent/name).read_bytes()).hexdigest()
            for name in ('diagnostics.py','models/baseline.py','simulation.py','scoring.py','history_coverage.py','backtest/walk_forward.py','optimizer/squad.py')},
        runtime_versions={'python':platform.python_version(),**{p:version(p) for p in ('numpy','scipy','pandas')}},
        snapshot_path=data.get('snapshot_path'),event=event,config=asdict(config),draws=draws,
        seed=seed,team_evaluation_seed=seed+1,budget=budget,locked=sorted(locked),excluded=sorted(excluded),
        player_explanations=forecasts.explanations,players=table,team=team,team_distribution=dict(mean=float(values.mean()),
            p10=float(np.quantile(values,.1)),p50=float(np.quantile(values,.5)),p90=float(np.quantile(values,.9)),
            bench_mean=float(totals['bench_points'].mean()),captain_bonus_mean=float(totals['captain_bonus'].mean())),
        evaluation=evaluate_sample(data,config,draws=min(draws,2000),seed=seed),
        model_status='preliminary_uncalibrated',
        limitations=['Independent minutes; no coherent real-team XI or GK exclusion.',
            'Shared opponent goal times for clean sheets/concessions. Independent player goals/assists need not sum to team goals.',
            'Bonus is a marginal 0–3 approximation, not a full BPS ranking; rare events are independent.',
            'Autosub evaluation follows participation/formation rules; bench objective is only weighted expected points.',
            'Current price budget is for a new squad; no selling values, transfers, hits or chips.'])
    return report, forecasts, totals


def save_run(report, output=None):
    """Persist exactly the displayed run, exclusively; no recapture/recomputation."""
    from fpl_model.config import ROOT, RAW
    import pandas as pd
    out=Path(output) if output is not None else ROOT/'artifacts/prototype'/(
        datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')+'_'+uuid4().hex[:8])
    protected=[RAW.resolve()]
    if report.get('snapshot_path'): protected.append(Path(report['snapshot_path']).resolve().parent)
    if any(out.resolve().is_relative_to(p) for p in protected):
        raise ValueError('Outputs cannot be written into raw storage')
    out.mkdir(parents=True,exist_ok=False)
    (out/'report.json').write_text(json.dumps(report,indent=2,ensure_ascii=False,allow_nan=False)+'\n')
    pd.DataFrame(report['players']).to_csv(out/'players.csv',index=False)
    pd.DataFrame(report['evaluation']['rows']).to_csv(out/'evaluation_rows.csv',index=False)
    return out
