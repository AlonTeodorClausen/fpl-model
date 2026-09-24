"""Application service; UI/CLI orchestration without changing model or solver APIs."""
from dataclasses import asdict
import numpy as np
from fpl_model.simulation import simulate
from fpl_model.optimizer.squad import optimize_squad, evaluate_squad
from fpl_model.backtest.walk_forward import evaluate_sample


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
        snapshot_path=data.get('snapshot_path'),event=event,config=asdict(config),draws=draws,
        seed=seed,team_evaluation_seed=seed+1,budget=budget,locked=sorted(locked),excluded=sorted(excluded),
        players=table,team=team,team_distribution=dict(mean=float(values.mean()),
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
