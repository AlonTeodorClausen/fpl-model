from pathlib import Path
import pandas as pd

from fpl_model.config import FOOTBALL_DATA_UK_FIXTURES

def fetch_upcoming_odds(out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    df = pd.read_csv(FOOTBALL_DATA_UK_FIXTURES)
    df.to_parquet(out_dir / "upcoming_odds.parquet", index=False)
