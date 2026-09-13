import pandas as pd

def add_rolling_player_features(df: pd.DataFrame) -> pd.DataFrame:
    # Expected input: one row per player-match, sorted by kickoff.
    # IMPORTANT: always shift(1) before rolling to avoid look-ahead bias.
    df = df.sort_values(["player_id", "kickoff_time"]).copy()

    for col in ["minutes_played", "xg", "xa", "defensive_contributions"]:
        if col not in df.columns:
            continue
        g = df.groupby("player_id")[col]
        for window in (3, 5, 10):
            df[f"{col}_roll{window}"] = g.transform(
                lambda s: s.shift(1).rolling(window, min_periods=1).mean()
            )
    return df
