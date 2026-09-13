# Candidate edges to test, not assume

1. **All-competition workload / rotation**
   - actual minutes in PL + Europe + cups
   - rest days, starts in last 7/14 days
   - interaction with age, position and manager rotation history

2. **Tactical role-shift detection**
   - average-position coordinates
   - touches in box, shot share, xG/xA share
   - set-piece share
   - change-point / structural-break flag

3. **Opponent-adjusted defensive-contribution probability**
   - predict P(CBIT>=10) or P(CBIRT>=12)
   - include expected possession, opponent style and player role
   - nonlinear threshold makes this better than using last season's DefCon points

4. **Exact autosub value**
   - simulate P(0 minutes) for each starter
   - legal formation constraints
   - evaluate bench positions from actual substitution probability

5. **Price dynamics**
   - transfers in/out, ownership, price history
   - forecast likely price change and future team-value option value
   - keep separate from pure expected-points forecast

6. **Manager/tactical regime changes**
   - detect breaks in team attack/defence and player role
   - downweight observations from the old regime

7. **Referee effects**
   - weekly referee appointments
   - penalty/card tendencies
   - probably small; only retain if walk-forward tests improve

8. **Weather**
   - wind/rain/heat from Open-Meteo historical forecasts
   - likely small; test rather than assume

9. **Uncertainty-aware optimisation**
   - optimise scenarios/distributions, not only mean xP
   - particularly relevant for captaincy, risky minutes and bench coverage
