"""2026/27 FPL scoring of supplied events; no probabilities or optimization.

Counts use official FPL definitions. Goals conceded must already cover the
player's interval (and the remainder after dismissal). Bonus is supplied, not BPS.
Rules: https://www.premierleague.com/en/news/2174909
"""
import numpy as np


def score_components(position, *, minutes, goals=0, assists=0, goals_conceded=0,
                 saves=0, defensive_contribution=0, penalties_saved=0,
                 penalties_missed=0, yellow_cards=0, red_cards=0, own_goals=0, bonus=0):
    if position not in (1, 2, 3, 4):
        raise ValueError('Unknown FPL position')
    m = np.asarray(minutes)
    played = m > 0
    return dict(
        appearance=played.astype(int)+(m>=60),
        goals=goals*{1:10,2:6,3:5,4:4}[position], assists=3*assists,
        clean_sheets=((m>=60)&(np.asarray(goals_conceded)==0))*{1:4,2:4,3:1,4:0}[position],
        goals_conceded=-(np.asarray(goals_conceded)//2) if position in (1,2) else 0,
        saves=np.asarray(saves)//3 if position==1 else 0,
        defensive_contribution=2*(np.asarray(defensive_contribution)>=(10 if position==2 else 12)) if position!=1 else 0,
        penalties_saved=5*penalties_saved, penalties_missed=-2*penalties_missed,
        yellow_cards=-yellow_cards, red_cards=-3*red_cards, own_goals=-2*own_goals, bonus=bonus)


def score_points(position, **events):
    """Unchanged baseline-v1 weights; one scoring path for total and explanation."""
    return sum(score_components(position, **events).values())
