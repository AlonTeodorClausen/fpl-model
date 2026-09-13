from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data"
RAW = DATA / "raw"
PROCESSED = DATA / "processed"
MODELS = ROOT / "models"

FPL_BOOTSTRAP = "https://fantasy.premierleague.com/api/bootstrap-static/"
FPL_FIXTURES = "https://fantasy.premierleague.com/api/fixtures/"

FPL_CORE_RAW = (
    "https://raw.githubusercontent.com/olbauday/"
    "FPL-Core-Insights/main/data/2026-2027"
)
FOOTBALL_DATA_UK_FIXTURES = (
    "https://www.football-data.co.uk/matches/resources/fixtures.csv"
)
FOOTBALL_DATA_ORG = "https://api.football-data.org/v4"
CLUBELO = "http://api.clubelo.com"
