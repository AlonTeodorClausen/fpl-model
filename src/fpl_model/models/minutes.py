# Recommended design:
# 1) classifier: P(appearance > 0)
# 2) classifier: P(start | appearance)
# 3) regress minutes conditional on starting
# 4) regress minutes conditional on sub appearance
#
# Key features should include:
# recent starts/minutes, injury status, all-competition workload,
# days of rest, European/cup minutes and role stability.
