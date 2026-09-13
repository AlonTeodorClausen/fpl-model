# 2026/27 edge candidate:
# predict the DISTRIBUTION of defensive contributions, not its mean FPL points.
#
# DEF gets +2 if CBIT >= 10.
# MID/FWD gets +2 if CBIRT >= 12.
#
# A count model (Poisson/Negative Binomial) lets us calculate:
# P(count >= threshold) * 2.
#
# Add opponent possession/strength and tactical role because the threshold is nonlinear.
