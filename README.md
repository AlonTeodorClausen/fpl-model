# FPL Free Model – starter

Goal: separate the project into four layers:

1. **Data ingestion** – raw snapshots only.
2. **Features / forecasts** – expected minutes and component forecasts.
3. **Expected FPL points** – convert component distributions into xP.
4. **Optimisation / backtest** – squad, lineup, bench, captain, transfers, chips.

## Core free sources

- Official FPL API:
  - https://fantasy.premierleague.com/api/bootstrap-static/
  - https://fantasy.premierleague.com/api/fixtures/
- FPL Core Insights:
  - https://github.com/olbauday/FPL-Core-Insights
- Football-Data.co.uk upcoming fixtures + odds:
  - https://www.football-data.co.uk/matches/resources/fixtures.csv
- football-data.org:
  - free API key; Premier League + Champions League fixtures are in the free tier.
- ClubElo:
  - http://api.clubelo.com/YYYY-MM-DD
  - optional; cache locally and backfill if a club is absent from a daily off-season snapshot.

## Recommended first modelling milestone

Do not train one model directly on FPL points.

Build components:

- P(appearance)
- P(start)
- expected minutes conditional on start/sub
- player xG and xA rates
- team goals / clean-sheet probabilities
- defensive-contribution threshold probability
- goalkeeper saves
- cards
- bonus (later: match-level Monte Carlo)

Then combine those components with the official scoring rules.

## Data discipline

Every weekly run should create an immutable `data/raw/YYYY-MM-DD_HHMM/` snapshot.
That is essential for walk-forward backtesting without look-ahead bias.
