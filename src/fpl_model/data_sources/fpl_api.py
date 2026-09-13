import json
from pathlib import Path
import requests

from fpl_model.config import FPL_BOOTSTRAP, FPL_FIXTURES

def _get_json(url: str) -> dict | list:
    r = requests.get(url, timeout=30)
    r.raise_for_status()
    return r.json()

def fetch_fpl_snapshot(out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    payloads = {
        "bootstrap_static.json": _get_json(FPL_BOOTSTRAP),
        "fixtures.json": _get_json(FPL_FIXTURES),
    }
    for name, payload in payloads.items():
        (out_dir / name).write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
