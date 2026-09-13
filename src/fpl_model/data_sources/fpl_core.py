from pathlib import Path
import pandas as pd

from fpl_model.config import FPL_CORE_RAW

MASTER_FILES = ["players.csv", "teams.csv", "playerstats.csv", "gameweek_summaries.csv"]

def fetch_fpl_core_master(out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    for filename in MASTER_FILES:
        url = f"{FPL_CORE_RAW}/{filename}"
        try:
            df = pd.read_csv(url)
        except Exception as exc:
            print(f"Skipping {filename}: {exc}")
            continue
        df.to_parquet(out_dir / filename.replace(".csv", ".parquet"), index=False)
