"""Cache pruning keeps every cache a review may need and never deletes."""
import importlib.util
import json
import os
from pathlib import Path


def script():
    path = Path(__file__).resolve().parents[1]/'scripts/prune_forecast_caches.py'
    spec = importlib.util.spec_from_file_location('prune_forecast_caches', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def key(i):
    return f'{i:064x}'


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value))


def test_keeps_newest_reviewed_and_last_pre_deadline_and_moves_rest(tmp_path):
    art = tmp_path/'artifacts'
    for i in range(1, 7):
        cache = art/'transfer_forecasts'/key(i)
        write(cache/'bundle.json', {})
        os.utime(cache, (i, i))
    deadline = {'11': '2026-11-21T11:00:00Z'}
    write(art/'transfers/a/report.json', dict(created_at='2026-11-15T10:00:00+00:00',
          forecast=dict(cache_key=key(1), deadlines=deadline)))
    write(art/'transfers/b/report.json', dict(created_at='2026-11-20T10:00:00+00:00',
          forecast=dict(cache_key=key(2), deadlines=deadline)))
    write(art/'transfers/late/report.json', dict(created_at='2026-11-22T10:00:00+00:00',
          forecast=dict(cache_key=key(3), deadlines=deadline)))
    write(art/'forecast_reviews/r/report.json', dict(forecast_metadata=dict(cache_key=key(4))))
    m = script()
    caches, keep, move = m.plan(art, newest=1)
    assert set(keep) == {key(2), key(4), key(6)}
    assert {p.name for p in move} == {key(1), key(3), key(5)}
    assert m.main(['--artifacts', str(art), '--keep-newest', '1']) == 0
    assert not (art/'transfer_forecasts/_to_delete').exists()
    assert m.main(['--artifacts', str(art), '--keep-newest', '1', '--apply']) == 0
    moved = {p.name for p in (art/'transfer_forecasts/_to_delete').iterdir()}
    assert moved == {key(1), key(3), key(5)}
    assert (art/'transfer_forecasts'/key(2)/'bundle.json').exists()
