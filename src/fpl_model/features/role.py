import pandas as pd

def add_role_shift_features(df: pd.DataFrame) -> pd.DataFrame:
    # Candidate edge:
    # use average-position coordinates, touches in box, shot share, xG share,
    # set-piece share and starts to detect tactical role changes.
    #
    # Examples:
    # - avg_x / avg_y rolling change
    # - touches_box_per90 change
    # - team_xg_share change
    # - set_piece_share change
    # - structural-break flag after sustained role change
    return df
