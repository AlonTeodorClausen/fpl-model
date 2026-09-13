import os
from pathlib import Path
import requests
from dotenv import load_dotenv

from fpl_model.config import FOOTBALL_DATA_ORG

load_dotenv()

def fetch_competition_matches(code: str, out_dir: Path) -> None:
    token = os.getenv("FOOTBALL_DATA_ORG_TOKEN")
    if not token:
        print("FOOTBALL_DATA_ORG_TOKEN not set; skipping football-data.org")
        return

    r = requests.get(
        f"{FOOTBALL_DATA_ORG}/competitions/{code}/matches",
        headers={"X-Auth-Token": token},
        timeout=30,
    )
    r.raise_for_status()
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / f"{code}_matches.json").write_text(r.text, encoding="utf-8")
