from fpl_model.config import RAW
from fpl_model.io import snapshot_dir
from fpl_model.data_sources.fpl_api import fetch_fpl_snapshot
from fpl_model.data_sources.fpl_core import fetch_fpl_core_master
from fpl_model.data_sources.football_data_uk import fetch_upcoming_odds
from fpl_model.data_sources.football_data_org import fetch_competition_matches
from fpl_model.data_sources.clubelo import fetch_clubelo

def main():
    out = snapshot_dir(RAW)

    fetch_fpl_snapshot(out / "fpl_api")
    fetch_fpl_core_master(out / "fpl_core")
    fetch_upcoming_odds(out / "football_data_uk")

    # Optional independent schedules. Free token required.
    fetch_competition_matches("PL", out / "football_data_org")
    fetch_competition_matches("CL", out / "football_data_org")

    # Optional because FPL Core already includes Elo.
    try:
        fetch_clubelo(out / "clubelo")
    except Exception as exc:
        print(f"ClubElo skipped: {exc}")

    print(f"Snapshot written to: {out}")

if __name__ == "__main__":
    main()
