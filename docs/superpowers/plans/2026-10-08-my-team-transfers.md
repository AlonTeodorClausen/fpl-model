# My team and immediate transfers implementation plan

> Execution: inline using executing-plans and test-driven-development. The user approved the in-chat design and explicitly instructed implementation.

**Goal:** Save a real squad and compare holding against immediate transfer packages over 1–4 GWs.

**Architecture:** Reuse simulation/odds and autosub evaluation. One fixed squad per package with independently optimized lineups each GW. Cache forecasts separately from user constraints.

**Constraints:** No new models, downloads, chips or future transfer sequences. Monetary values are integer tenths. No hits by default. All scenarios share one information cutoff; future availability/prices remain fixed assumptions. Raw data and generated results stay ignored.

**Interfaces/files:** `my_team.py` validates/persists a profile; `optimizer/transfers.py` optimizes a fixed-horizon squad; `transfer_planner.py` caches scenarios and compares packages; `app.py` routes to `ui/my_team.py` and existing `ui/experiments.py`.

## Tasks
- [x] Profile tests first: money, IDs/positions/club limits, free transfers, save/edit/reload. Implement profile persistence and transfer accounting; run focused tests.
- [x] Optimizer tests first: actual selling values, bank, zero/one/multiple moves, horizon tradeoffs, locks/exclusions, hits, solver status. Implement joint MILP and reuse lineup/autosub contracts; run focused tests.
- [x] Service tests first: common pre-origin cutoff, deterministic cache invalidation, BGW/DGW, shared scenario evaluation, odds fallback and saved reports. Implement forecast bundle/cache and package comparison; run focused tests.
- [x] App tests first: default team page, manual editing/persistence, explicit actions, results/lineups, secondary legacy page. Implement UI and example-player preset (no invented user finances).
- [x] Run full offline suite; exercise real stored data and browser; document commands/limitations and review focused diff.

## Review focus
Owned unselectable players must not be forced out; future sources cannot enter an earlier cutoff; excluded owned players must leave proposals but not the hold comparator; transfer costs/hits occur once; stale inputs must not masquerade as a new capture.

## Progress and decisions
- Working in the existing checkout to preserve the active app and ignored local captures. No source/model formula changes planned.
- User approval applies to implementation; no additional design approval checkpoint.
- Official rules checked 2026-10-08: one FT/GW, cap five, four-point hits, 20 transfers/GW. https://www.premierleague.com/es/news/4661029
- Default proposal set: hold plus best feasible package for each exact transfer count. Equal horizon weights; existing bench weight 0.1. Not an exhaustive simulated-point optimum or valuation of waiting.

## Verification
- Full offline suite: 662 passed, 5 live tests deselected (2026-10-08).
- Reviewed transfer budget, source timing and season boundaries; fixed cross-season profile handling and disallowed skipping the next GW.
- Browser verification caught a keyed-widget reset issue missed by value-only AppTest assertions. Explicit state initialization now updates the browser; regression checks the frontend reset signal. Example players confirmed in the live browser; actual sale values/bank remain blank.
- Existing real snapshots exercised over GW6–9, 3,000 scenarios, seed 42, without downloads. William Hill coverage 10/10, 10/10, 0/10, 0/10; uncovered fixtures use marked baseline fallback.
- Integration run used explicitly hypothetical sale values and bank, not user finances. Its saved report rendered all package results and four per-GW lineups successfully. Raw snapshots and generated outputs remain ignored.
