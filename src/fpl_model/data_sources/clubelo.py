from datetime import date, timedelta
from io import StringIO
from pathlib import Path
import pandas as pd
import requests

from fpl_model.config import CLUBELO

def _snapshot(day: date) -> pd.DataFrame:
    r = requests.get(f"{CLUBELO}/{day.isoformat()}", timeout=30)
    r.raise_for_status()
    return pd.read_csv(StringIO(r.text))

def fetch_clubelo(out_dir: Path, fallback_days: int = 21) -> None:
    # ClubElo daily snapshots can omit clubs during off-season rating gaps.
    today = date.today()
    current = _snapshot(today)
    fallback = _snapshot(today - timedelta(days=fallback_days))

    if "Club" in current.columns and "Club" in fallback.columns:
        missing = fallback.loc[~fallback["Club"].isin(current["Club"])]
        current = pd.concat([current, missing], ignore_index=True)

    out_dir.mkdir(parents=True, exist_ok=True)
    current.to_parquet(out_dir / "clubelo.parquet", index=False)
