import pandas as pd

def add_workload_features(matches: pd.DataFrame) -> pd.DataFrame:
    # Intended for ALL competitions, not just Premier League.
    # Useful edge candidates:
    # - minutes_all_comps_7d / 14d
    # - starts_all_comps_14d
    # - days_since_last_match
    # - days_since_last_start
    # - European/cup match within +/- 3 days
    return matches
