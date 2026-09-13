from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data"
RAW = DATA / "raw"
PROCESSED = DATA / "processed"
MODELS = ROOT / "models"

FPL_BOOTSTRAP = "https://fantasy.premierleague.com/api/bootstrap-static/"
FPL_FIXTURES = "https://fantasy.premierleague.com/api/fixtures/"

# Adapter appends an explicit commit SHA, season and filename; never floating main.
FPL_CORE_RAW = "https://raw.githubusercontent.com/olbauday/FPL-Core-Insights"
FOOTBALL_DATA_UK_FIXTURES = "https://www.football-data.co.uk/fixtures.csv"
FOOTBALL_DATA_ORG = "https://api.football-data.org/v4"
CLUBELO = "http://api.clubelo.com"
