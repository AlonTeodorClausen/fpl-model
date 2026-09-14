# Step 2A — source contracts and coverage audit

Audit date: 2026-09-14. This document describes **one observed snapshot**, not guaranteed provider coverage, a canonical dataset, or a historical training set.

Snapshot root (all raw paths below are relative to this exact directory):

```text
/Users/alonclausen/Desktop/fpl_free_model_starter-2/data/raw/2026-09-13_154638516264Z_fe2dc3c782d146b2b6a22bdaafb905c5
```

Run ID: `fe2dc3c782d146b2b6a22bdaafb905c5`. Created `2026-09-13T15:46:38.516264+00:00`; completed `2026-09-13T15:46:54.253373+00:00`. The manifest's canonical `status=complete` means published and integrity-verifiable; `run_metadata.overall=partial` records unavailable optional ClubElo. All 13 raw response entries, the manifest digest and COMPLETE marker verified. No replacement data was fetched and no raw content was modified.

The [coverage report](../artifacts/audits/step2a_fe2dc3c782d146b2b6a22bdaafb905c5/coverage.json) contains exact per-column types/missingness, nested JSON profiles, duplicate-key tests, identifier comparisons, source manifests and pinned upstream metadata. It is an ignored audit artifact, not a normalized dataset. The [audit script](../scripts/audit_snapshot.py) is offline and reproducible; CSV strings are not converted or filled. Empty strings, absent JSON keys, JSON nulls and empty arrays/objects are counted separately. Zero is never treated as missing.

## 1. Raw inventory and time provenance

The six FPL API/Core files **do not have a recorded `available_at` or content type in this manifest**. For this audit only, their conservative effective availability is `retrieved_at`. The raw manifest remains unchanged, and the JSON report distinguishes `recorded_available_at=null` from `effective_available_at`. Other adapters explicitly recorded availability equal to retrieval. A manifest's absent field is not proof of an earlier timestamp.

| Exact raw file | Retrieved at (UTC) | Recorded available_at | HTTP / content type | Bytes |
| --- | --- | --- | --- | ---: |
| `raw/fpl_api/bootstrap_static.json` | `2026-09-13T15:46:38.663888+00:00` | Absent; audit uses retrieval | 200 / (not recorded) | 1750370 |
| `raw/fpl_api/fixtures.json` | `2026-09-13T15:46:38.697835+00:00` | Absent; audit uses retrieval | 200 / (not recorded) | 206133 |
| `raw/fpl_core/907f666f2dc6796d417e49287fd31f88263f1d67/data/2026-2027/players.csv` | `2026-09-13T15:46:38.911384+00:00` | Absent; audit uses retrieval | 200 / (not recorded) | 31245 |
| `raw/fpl_core/907f666f2dc6796d417e49287fd31f88263f1d67/data/2026-2027/teams.csv` | `2026-09-13T15:46:39.400751+00:00` | Absent; audit uses retrieval | 200 / (not recorded) | 926 |
| `raw/fpl_core/907f666f2dc6796d417e49287fd31f88263f1d67/data/2026-2027/playerstats.csv` | `2026-09-13T15:46:39.708386+00:00` | Absent; audit uses retrieval | 200 / (not recorded) | 755496 |
| `raw/fpl_core/907f666f2dc6796d417e49287fd31f88263f1d67/data/2026-2027/gameweek_summaries.csv` | `2026-09-13T15:46:39.934147+00:00` | Absent; audit uses retrieval | 200 / (not recorded) | 10508 |
| `raw/football_data_uk/attempt_01/fixtures.csv` | `2026-09-13T15:46:40.038639+00:00` | `2026-09-13T15:46:40.038639+00:00` | 302 / text/html | 0 |
| `raw/football_data_uk/attempt_02/fixtures.csv` | `2026-09-13T15:46:49.348401+00:00` | `2026-09-13T15:46:49.348401+00:00` | 200 / text/csv | 53814 |
| `raw/football_data_org/PL/attempt_01/matches.json` | `2026-09-13T15:46:49.832166+00:00` | `2026-09-13T15:46:49.832166+00:00` | 200 / application/json;charset=UTF-8 | 366606 |
| `raw/football_data_org/CL/attempt_01/matches.json` | `2026-09-13T15:46:50.004081+00:00` | `2026-09-13T15:46:50.004081+00:00` | 200 / application/json;charset=UTF-8 | 138688 |
| `raw/clubelo/2026-09-13/attempt_01/ratings.csv` | `2026-09-13T15:46:50.517056+00:00` | `2026-09-13T15:46:50.517056+00:00` | 502 / (absent/empty) | 0 |
| `raw/clubelo/2026-09-13/attempt_02/ratings.csv` | `2026-09-13T15:46:51.801263+00:00` | `2026-09-13T15:46:51.801263+00:00` | 502 / (absent/empty) | 0 |
| `raw/clubelo/2026-09-13/attempt_03/ratings.csv` | `2026-09-13T15:46:54.233096+00:00` | `2026-09-13T15:46:54.233096+00:00` | 502 / (absent/empty) | 0 |

The Core pin is `907f666f2dc6796d417e49287fd31f88263f1d67`, not the older SHA mentioned in the Step 1C smoke-test notes. Its Git committer timestamp is `2026-09-13T12:49:01Z`. Commit time fixes revision identity but does not prove when each row became publicly available. No source supplies audited historical publication provenance in this snapshot.

The runner's `season=2026-2027` parameter selected Core's directory. It was not a query filter on the other APIs. Both football-data.org responses themselves report filter `season: "2026"`.

## 2. Official FPL API

### Bootstrap: players, teams and events

`raw/fpl_api/bootstrap_static.json` has top-level keys `chips`, `events`, `game_settings`, `game_config`, `phases`, `teams`, `total_players`, `element_stats`, `element_types`, `elements`.

Other bootstrap contents are context only: 8 chip records, 11 phases, 26 statistic definitions, 35 `game_settings` keys and 4 `game_config` keys. `total_players=10,745,022` counts game entries, not footballers. Scoring/settings contents have not been promoted to a verified season scoring engine in this audit.

| Entity | Count | Grain / identifiers |
| --- | ---: | --- |
| Players / `elements` | 657 | One current FPL player; unique integer `id` 1–657, `code`, `opta_code`; `team` references team `id`, `team_code` references team `code`; `element_type` references position type. |
| Teams | 20 | One current team; integer `id`, `code`, `pulse_id`; names and short names. The ID/code distinction matters. |
| Events | 38 | One GW; unique integer `id` 1–38, timezone-bearing `deadline_time`. |
| Position types | 4 | `element_types.id`; labels and selection rules, not player performance. |

The player table has **109 observed fields**; full inventory and types are in Appendix A. Examples of actual storage types: IDs, cost and counting statistics are integers; status/news are strings; expected totals and `form`/`selected_by_percent` are numeric-looking JSON strings; expected per-90 fields are JSON floats; selection flags are booleans; `price_change_projections` and `scout_risks` are arrays. This audit does not coerce them into one schema.

Player availability fields actually present include `status`, `news`, `news_added`, `chance_of_playing_this_round`, `chance_of_playing_next_round`, `removed`, `can_select`, `can_transact`, plus `scout_risks`/`scout_news_link`. Status counts are `a=469`, `d=16`, `i=65`, `s=3`, `u=104`. These are observed source codes; a complete status-transition contract is not yet validated. News is blank for 469 players; `news_added` is null for 400, while 257 timestamps range from `2026-07-23T12:01:23.272929Z` to `2026-09-13T15:00:09.305127Z`. A timestamp on a news item does not backdate the availability of the full current player record. Playing chances are null for 408 players (this round) and 400 (next round); null is not 100% or 0%.

Expected fields actually present:

```text
expected_goals, expected_assists, expected_goal_involvements,
expected_goals_conceded, expected_goals_per_90, expected_assists_per_90,
expected_goal_involvements_per_90, expected_goals_conceded_per_90,
ep_this, ep_next
```

The first four are season-to-date performance aggregates; the per-90 fields are rates. `ep_this`/`ep_next` are provider prediction-like values, not ground-truth labels and not forecasts produced by this project. Their exact semantics/calibration remain unverified. `minutes`, `starts`, `total_points`, goals, assists, cards, saves, bonus/BPS, tackles, recoveries and `clearances_blocks_interceptions` are also season aggregates. `event_points` is the current GW aggregate, which may be provisional. None is a complete fixture-level player label table.

Other missingness: `squad_number` is null for all 657; set-piece descriptive text is blank for all 657; order fields are mostly null. `birth_date`, `region`, `team_join_date` each lack 16 values. Team `strength`, `form`, `team_division` are null for all 20. Every team has zero in `played`, `points`, win/draw/loss and the four attack/defence-strength fields. These zeros look like unavailable/unmaintained context, not credible measured zero strength or standings; preserve them and keep their semantics unverified.

### Deadlines and fixture-level information

`raw/fpl_api/fixtures.json` contains **380 fixtures**, 17 fields, unique integer `id` 1–380, plus separate integer `code` and `pulse_id`. Team links use `team_h`/`team_a`; `event` is the GW. Every GW 1–38 has ten fixtures in this version. Kickoffs range from `2026-08-21T19:00:00Z` to `2027-05-30T15:00:00Z`; no kickoff or event is null in this snapshot. This does not guarantee future fixture versions remain complete or fixed.

All 380 fixture `code` values are distinct (2645195–2645574), but **every fixture `pulse_id` is 0**, so it is not a usable match key here. All player `team` references resolve to FPL teams and agree with their `team_code`; all fixture home/away team references resolve, and every sparse stats `element` reference resolves to the current player universe. These are current-snapshot checks, not proof of cross-season ID stability.

Only 30 fixtures have `finished=true`. There are 39 started fixtures, 38 with `finished_provisional=true`, and 341 without scores or stats. GW4 has eight provisionally finished fixtures, one in progress and one future fixture; **GW4 is not a finalized label set**. The distinction explains why football-data.org already calls 38 PL matches FINISHED while FPL has only 30 fully finished fixtures.

`stats` contains sparse fixture/player records using `element` as FPL player ID, numeric `value`, and `a`/`h` sides. Eleven identifiers occur in each of 39 populated fixture stats arrays:

```text
goals_scored, assists, own_goals, penalties_saved, penalties_missed,
yellow_cards, red_cards, saves, bonus, bps, defensive_contribution
```

These arrays reference 404 distinct players. They are genuinely fixture-linked observations, but **not a complete player-match table**: absent records do not prove DNP or zero, and no per-player minutes, starts, xG or xA fields occur here. Fixture-level `minutes` is match progress, not player minutes. Scores and sparse stats are post-match/provisional label candidates; IDs, known schedules and deadlines are context that could support later pre-deadline inputs after their own retrieval cutoff.

GW1–4 deadlines precede this snapshot's retrieval, so this version cannot supply leakage-safe inputs for those origins. GW4 deadline was `2026-09-12T12:30:00Z`; GW5 is next at `2026-09-18T17:30:00Z`. All 38 observed deadlines are listed in Appendix B. Future deadlines/schedules are only the versions known at retrieval.

## 3. FPL Core Insights: downloaded master files

All paths start with `raw/fpl_core/907f666f2dc6796d417e49287fd31f88263f1d67/data/2026-2027/`. Exact file/timestamp inventory is above; no other Core datasets were ingested.

| File | Rows / columns | Observed grain and identifiers |
| --- | --- | --- |
| `players.csv` | 657 / 7 | Current player metadata. Unique `player_id` and `player_code`; `team_code`, first/second/web names, full-word `position`. Official FPL IDs are present. No match key. |
| `teams.csv` | 20 / 14 | Current team metadata; `id`, `code`, `name`, `short_name`, strength fields, `pulse_id`, `elo`, `fotmob_name`. |
| `playerstats.csv` | 2,581 / 87 | Unique `(id, gw)`, 657 distinct official player IDs. Repeated **cumulative player/GW observations**, not matches. No fixture ID, match ID, opponent, kickoff or row observation timestamp. |
| `gameweek_summaries.csv` | 38 / 30 | One row per GW `id`; deadlines, state flags, competition-wide FPL summaries. No player-match grain. |

CSV values are strings. Numeric-looking fields, booleans and timestamps are described as lexical types in Appendix A; empty cells stay empty. All seven player metadata columns are populated. Core positions are full words rather than FPL `element_type` integers. Current identity compatibility does not establish historical team/position membership at each old GW.

### Cumulative statistics and completeness

| GW | Rows | Current player IDs absent from that GW | Maximum minutes | Maximum starts | Rows with minutes > 90 |
| --- | ---: | --- | ---: | ---: | ---: |
| 1 | 616 | 617–657 (41) | 90 | 1 | 0 |
| 2 | 652 | 653–657 (5) | 180 | 2 | 206 |
| 3 | 656 | 657 (1) | 270 | 3 | 244 |
| 4 | 657 | None | 360 | 4 | 262 |

Those missing IDs are measured against the **current** universe. They are not proven missing eligible historical players; introduction dates are not captured here. Do not fill earlier rows with zeros. The increasing maxima, repeated IDs and source documentation support cumulative rather than match-level interpretation.

`minutes`, `starts`, `expected_goals`, `expected_assists`, `defensive_contribution`, `clearances_blocks_interceptions`, `tackles`, `recoveries` are present and populated in all 2,581 rows. These are aggregate fields, not European/cup minutes or discrete defensive actions for each match. No separate clearances/blocks/interceptions breakdown is downloaded. Even GW deltas would not resolve double fixtures, revisions or missing historical rows.

Latest GW4 versus the independently retrieved FPL bootstrap differs for **53 players in minutes, 44 in starts, 48 in total points, 22 in xG, 28 in xA, 18 in tackles, 31 in combined clearances/blocks/interceptions, and 34 in recoveries**. Example official player ID 109, Verbruggen: Core minutes `270` / total points `9`; FPL minutes `360` / total points `17`. This is evidence of non-atomic, differing source versions during an active GW, not a license to merge their values. The pinned commit predates the FPL response by roughly three hours; causality for every difference has not been established.

All 657 latest Core prices multiplied by ten equal the corresponding FPL `now_cost`; Core uses price values such as `5.5` versus FPL integer `55`. A future schema must make this unit distinction explicit.

Core missingness: `news_added`, `set_piece_threat` and all three set-piece text columns are empty in **all 2,581 rows**. `news` is empty in 1,916; playing chance next/this round is empty in 1,678/1,794. All 20 `teams.elo`, `fotmob_name`, and `strength` entries are blank. Core supplies no usable Elo fallback in this snapshot.

### Summary timestamp warning

All 38 `gameweek_summaries.snapshot_time` values are **`2026-07-23T15:00:09.957449+00:00`**, despite GW1–3 finished flags and GW1–4 outcome/selection summaries. All 38 deadlines agree with FPL after parsing their UTC offsets. Outcome columns are blank for 34 future GWs; `release_time` is blank for all 38. `chip_plays`, `overrides`, `top_element_info` are serialized structures in CSV strings; some use Python-style quotes/`None`, so do not assume valid JSON or evaluate them as code.

The July timestamp cannot certify that these later outcome values existed in July. Treat it as unverified/stale metadata. The file's actual audit availability remains September retrieval. Likewise `gw` labels do not prove pre-deadline capture.

### Upstream structure inspected, not ingested

The [pinned README](https://github.com/olbauday/FPL-Core-Insights/blob/907f666f2dc6796d417e49287fd31f88263f1d67/README.md) and a non-truncated pinned Git tree were inspected on the audit date. Saved metadata/documentation, hashes and retrieval times are under the audit artifact's `evidence/`; they are separate from the original snapshot. README descriptions below remain **unverified schema claims**, not coverage findings from downloaded match data.

Relevant existing paths include:

```text
data/2026-2027/team_history.csv
data/2026-2027/By Gameweek/GW4/matches.csv
data/2026-2027/By Gameweek/GW4/fixtures.csv
data/2026-2027/By Gameweek/GW4/playermatchstats.csv
data/2026-2027/By Gameweek/GW4/player_gameweek_stats.csv
data/2026-2027/By Tournament/Champions League/GW4/matches.csv
data/2026-2027/By Tournament/Champions League/GW4/playermatchstats.csv
data/2026-2027/By Tournament/EFL Cup/GW4/playermatchstats.csv
```

The README describes `playermatchstats` with `player_id`, `match_id`, `minutes_played`, `xg`, `xa` and defensive metrics. It warns that `start_min`/`finish_min` can misrepresent unused players; minutes should not be derived from those bounds. Its `player_gameweek_stats` description uses differences of cumulative totals, so that export is not automatically player-match data. End-of-GW snapshot wording and claims about deadline fields require separate evidence before historical use. [Pinned documentation](https://github.com/olbauday/FPL-Core-Insights/blob/907f666f2dc6796d417e49287fd31f88263f1d67/README.md).

Observed metadata (not inferred row counts): GW4 `matches.csv` is 13,179 bytes; `playermatchstats.csv` 109,983; CL GW4 equivalents 5,270 and 25,453. `matches.csv` and `fixtures.csv` have **identical blob SHAs** within each of those folders. `player_gameweek_stats.csv` and `playerstats.csv` also respectively have the same blobs in main GW4 and CL GW4. Thus directory labels alone cannot prove tournament-specific player totals. Avoid double counting equivalent exports.

The pinned season has main `By Gameweek` GW1–38 directories and tournament folders for Premier League, Champions League, Europa League, Conference League, EFL Cup, Friendlies, Community Shield and Uefa Super Cup. **No FA Cup folder is present in this pinned season tree.** Future-GW folder existence does not establish populated or finalized data. No new match CSVs were downloaded to determine their rows, missingness or official fixture ID compatibility. Full relevant tree entries are in `coverage.json.upstream_evidence.season_tree`.

## 4. Football-Data.co.uk

The first stored response is an empty HTTP 302 redirect; the second is the 53,814-byte CSV from `https://football-data.co.uk/fixtures.csv`. The successful file has **190 rows, 94 columns**, and a unique observed `(Div, Date, HomeTeam, AwayTeam)` tuple. There is no stable team or match ID and no odds observation/publication timestamp in the CSV.

Date coverage is **2026-09-11 through 2026-09-14**, so the feed includes already-played and in-progress fixtures at September 13 retrieval; its filename is not a strict future-only contract. Dates are observed `DD/MM/YYYY` strings, times `HH:MM` strings. PL wall-clock times are one hour ahead of corresponding FPL UTC kickoffs in visible examples; the CSV timezone is not established by this audit and no conversion or mapping is applied.

| League code | Competition label | Rows |
| --- | --- | ---: |
| `B1` | Belgium top division | 9 |
| `D1` | Germany top division | 9 |
| `D2` | Germany second division | 9 |
| `E0` | Premier League | 10 |
| `E1` | England Championship | 12 |
| `E2` | England League One | 11 |
| `E3` | England League Two | 12 |
| `EC` | England National League | 12 |
| `F1` | France top division | 9 |
| `F2` | France second division | 9 |
| `G1` | Greece top division | 7 |
| `I1` | Italy top division | 10 |
| `I2` | Italy second division | 10 |
| `N1` | Netherlands top division | 9 |
| `P1` | Portugal top division | 9 |
| `SC1` | Scotland Championship | 4 |
| `SC2` | Scotland League One | 4 |
| `SC3` | Scotland League Two | 5 |
| `SP1` | Spain top division | 10 |
| `SP2` | Spain second division | 11 |
| `T1` | Turkey top division | 9 |

E0 has **10 rows and 20 unique club names**, September 12–14. These cover the snapshot's PL roster subject to unresolved name aliases; literal matching only resolves 15 names. All non-closing PL odds cells and referee fields are populated. Across all leagues, missingness includes Referee 120/190; Betfair Exchange AH home/away each 32/190; Exchange totals each 5/190; Exchange 1X2 each 2/190; Bet365 AH home/away each 1/190. No cells were filled.

Observed pre-closing families: 1X2 H/D/A for `B365`, `BFD`, `BV`, `BW`, `PP`, `SKB`, `Max`, `Avg`, `BFE`; over/under 2.5 for `B365`, `Max`, `Avg`, `BFE`; Asian handicap line `AHh` and home/away AH prices for the same four. The provider key identifies Bet365, Betfred, BetVictor, Bet&Win, Paddy Power, market max/average and Betfair Exchange. Its Skybet example uses `SK`, whereas this response uses `SKB`; confirm that spelling before introducing a bookmaker-specific schema. [Provider notes](https://football-data.co.uk/notes.txt).

The provider defines `C` after a bookmaker/Max/Avg prefix as closing odds, e.g. `B365CH`; `AHCh` is the companion closing handicap field. **All 44 closing columns are empty in all 190 rows**, including all PL rows. Their presence is schema evidence, not observed closing odds. The provider's general Friday/Tuesday collection schedule is not a row-specific publication timestamp. Neither pre-closing labels nor eventual historical closing values establish availability before an FPL deadline. Use this version only at its retrieval time; it arrived after the GW4 deadline. [Provider notes](https://football-data.co.uk/notes.txt).

Exact observed PL names and fixture rows appear in Appendix C and in the machine report. No historical odds ingestion, league-filtered replacement raw file, or guessed identity mapping was created.

## 5. football-data.org: PL and CL separately

Both captured token-authenticated responses succeeded; this confirms these two endpoints for this account at this retrieval, not all free-plan capabilities. Top-level keys are exactly `competition`, `filters`, `matches`, `resultSet`. Both have 15 match fields:

```text
area, competition, season, id, utcDate, status, matchday, stage, group,
lastUpdated, homeTeam, awayTeam, score, odds, referees
```

IDs/matchday are JSON integers, kickoff/update times strings with `Z`, status/stage strings, most context and score fields objects, referees arrays. Nested types/missingness are in Appendix A and `coverage.json`. Match `id` is a football-data.org ID, not an FPL fixture ID. Teams have `id`, `name`, `shortName`, `tla`, `crest`; 20 PL and 36 CL team IDs are present with stable repeated metadata in these responses.

| Property | PL | CL |
| --- | --- | --- |
| Rows / distinct match IDs | 380 / 380 | 144 / 144 |
| Match ID range | 560542–560921 | 575280–575423 |
| Competition | `PL`, ID 2021, `LEAGUE` | `CL`, ID 2001, `CUP` |
| Kickoff range UTC | 2026-08-21 19:00 – 2027-05-30 15:00 | 2026-09-08 16:45 – 2027-01-27 20:00 |
| Matchdays / stage | 1–38, 10 each; REGULAR_SEASON | 1–8, 18 each; LEAGUE_STAGE |
| Status | FINISHED 38; IN_PLAY 1; TIMED 341 | FINISHED 18; TIMED 126 |
| Null `group` | 380 | 144 |
| Null fullTime home/away each | 341 | 126 |
| Null halfTime home/away each | 342 | 126 |
| Empty referee arrays | 341 | 126 |

PL `lastUpdated` spans `2026-09-12T10:20:32Z`–`2026-09-13T15:46:29Z`; every CL `lastUpdated` is `2026-09-12T20:20:16Z`. Neither is treated as publication time. Both have result winner/duration and full/half-time score fields; populated scores in an IN_PLAY match remain provisional. `odds` contains only a package-activation message, not usable odds.

**Neither response contains players, lineups, benches, substitutions, appearances or player minutes**, including inside home/away team objects. Referee names are not player records; match status and result duration do not establish participation. No player workload can be inferred. CL coverage is the league stage only: no qualifying or knockout matches are present here, and no FA/EFL/Europa/Conference schedules were queried from this provider.

IDs, schedules and competition fields are context/candidate later inputs after retrieval. Results are post-match team-label candidates gated on completion; player-label eligibility is absent. Unknown extra field meanings remain unverified. The literal team ID/name inventories are in Appendix C.

## 6. Identity compatibility — diagnostics, not mappings

All comparisons below use literal equality or exact numeric identifier representations. No case folding, accent stripping, suffix removal, fuzzy matching or guessed ID crosswalk was applied. Unmatched names are not automatically missing clubs.

| Comparison | Exact result | Missing / conflict / ambiguity |
| --- | --- | --- |
| FPL team `code` ↔ Core `code` | 20/20 unique | No missing codes; `id`, `name`, `short_name` also agree for all 20. |
| FPL player `id` ↔ Core `player_id` | 657/657 unique | No missing/extra IDs; player code, team code and all compared names agree. |
| FPL player `code` ↔ Core `player_code` | 657/657 unique | Official IDs agree on every code; no duplicates/conflicts. |
| FPL player ↔ latest Core `playerstats.id` | 657/657 unique | Names agree; performance versions differ as reported above. Earlier GWs have smaller universes. |
| FPL fixture ↔ Core match | Not auditable | No Core match dataset or fixture-match crosswalk in the snapshot. Same-looking IDs must not be assumed equivalent. |
| FPL team name ↔ E0 team name | 15/20 unique | Five unmatched strings on each side; no duplicate observed club names. |
| FPL team name ↔ org PL full `name` | 0/20 | Full provider names differ for all teams. |
| FPL team name ↔ org PL `shortName` | 15/20 unique | Five unmatched strings on each side. |
| FPL `short_name` ↔ org PL `tla` | 19/20 unique | FPL `NFO` vs provider `NOT` remains unmatched. TLA is not an authoritative cross-provider ID. |

E0 unmatched FPL names: `Coventry City`, `Hull City`, `Ipswich Town`, `Man Utd`, `Spurs`. Unmatched provider strings: `Coventry`, `Hull`, `Ipswich`, `Man United`, `Tottenham`. These are alias-review candidates as sets; this audit does not pair or approve them.

football-data.org PL unmatched short-name FPL strings: `Brighton`, `Leeds`, `Man Utd`, `Nott'm Forest`, `Spurs`. Provider strings: `Brighton Hove`, `Leeds United`, `Man United`, `Nottingham`, `Tottenham`. Full/short names are linked only within each provider's own team ID in Appendix C.

CL has four exact short-name intersections with FPL (`Arsenal`, `Aston Villa`, `Liverpool`, `Man City`) and five shared literal three-letter codes. Its own `FCB` code is ambiguous between two different team IDs (Barcelona and Bayern). Therefore a general TLA join would be unsafe. Non-PL CL teams are expected extra entities, not errors. The remaining FPL teams are outside the literal intersection; this does not prove they are absent from European football overall.

## 7. What is missing and what Step 2B should do

**Missing from this snapshot:** complete official player-fixture labels (minutes, starts, xG/xA and full FPL scoring components including DNP/unknown distinction); a Core match/player-match table; a verified FPL fixture↔Core match bridge; approved secondary-source team aliases; historical player eligibility/team membership; prior-deadline versions of the current inputs; usable Elo; row-specific odds publication evidence; cup/European player participation; and finalized GW4 labels.

The snapshot was captured after GW1–4 deadlines, with GW4 live. Thus **zero historical GW1–4 feature origins are certified by this snapshot alone**. GW5 onward may use eligible observed context after retrieval and before their forecast origins, but current news, prices, eligibility and schedules can become stale. A pinned Git revision, `lastUpdated`, fixture date, Core `gw` or the stale July `snapshot_time` cannot repair missing historical availability. An input built from multiple sources must inherit the latest dependency availability, not the run start or earliest file time.

Recommendation for **Step 2B, for approval before implementation**: define and test strict observation-time/label-completion and identity schemas, then scope official per-fixture player-label ingestion and a small pinned Core `matches`/`playermatchstats` sample. Verify match identifiers, units, player identity, tournament coverage and minutes semantics before any canonical join. Resolve aliases through explicit evidence and reviewed tables; reject unresolved/ambiguous entities. Keep cumulative GW snapshots separate from actual player-match observations. Retain optional-source gaps instead of filling them, and continue obtaining prospective before-deadline snapshots for later backtesting.

No canonical datasets, modelling features, predictions, optimizer or Step 2B implementation were created.

## 8. Reproduction and verification

The audit script makes no network calls. Use a new output path because it refuses to overwrite reports:

```sh
.venv/bin/python scripts/audit_snapshot.py \
  data/raw/2026-09-13_154638516264Z_fe2dc3c782d146b2b6a22bdaafb905c5 \
  --evidence artifacts/audits/step2a_fe2dc3c782d146b2b6a22bdaafb905c5/evidence \
  --output /tmp/step2a-coverage-replay.json
.venv/bin/python -m pytest -q
```

Audit tests cover missing/null/empty/zero distinctions, nested shapes, lexical CSV types, duplicate identities, exact-name mismatch refusal, date parsing, deterministic replay, raw immutability, corrupt-snapshot rejection, and output overwrite/path guards. The full offline suite passed **384 tests, 5 live tests deselected**. Original snapshot bytes were rechecked against their pre-audit SHA-256 inventory.

## Appendix A. Complete observed field/type/missingness inventory
Each section points to one dataset within a raw file listed above. CSV types are lexical hints only; storage remains `str`. JSON uses actual Python JSON-decoder type names (`NoneType` = JSON null). Nested populations count present objects or flattened list items, not necessarily root entities. Types/counts include empty and null observations. Missing columns below are `absent / null / blank string`; empty arrays/objects are reported separately. All fields not assigned a verified semantic role in the source discussion remain unverified; per-field conservative roles are also in `coverage.json`.

### core_gameweek_summaries — 38 rows; 30 top-level columns
Raw file: `raw/fpl_core/907f666f2dc6796d417e49287fd31f88263f1d67/data/2026-2027/gameweek_summaries.csv`.

| Field/path | Population | Observed types:count | Absent / null / blank | Empty list / object |
| --- | ---: | --- | --- | --- |
| `average_entry_score` | 38 | integer_text:38 | 0 / 0 / 0 | 0 / 0 |
| `can_enter` | 38 | boolean_text:38 | 0 / 0 / 0 | 0 / 0 |
| `can_manage` | 38 | boolean_text:38 | 0 / 0 / 0 | 0 / 0 |
| `chip_plays` | 38 | text:38 | 0 / 0 / 0 | 0 / 0 |
| `cup_leagues_created` | 38 | boolean_text:38 | 0 / 0 / 0 | 0 / 0 |
| `data_checked` | 38 | boolean_text:38 | 0 / 0 / 0 | 0 / 0 |
| `deadline_time` | 38 | timestamp_text:38 | 0 / 0 / 0 | 0 / 0 |
| `deadline_time_epoch` | 38 | integer_text:38 | 0 / 0 / 0 | 0 / 0 |
| `deadline_time_game_offset` | 38 | integer_text:38 | 0 / 0 / 0 | 0 / 0 |
| `finished` | 38 | boolean_text:38 | 0 / 0 / 0 | 0 / 0 |
| `h2h_ko_matches_created` | 38 | boolean_text:38 | 0 / 0 / 0 | 0 / 0 |
| `highest_score` | 38 | decimal_text:4, empty:34 | 0 / 0 / 34 | 0 / 0 |
| `highest_scoring_entry` | 38 | decimal_text:4, empty:34 | 0 / 0 / 34 | 0 / 0 |
| `id` | 38 | integer_text:38 | 0 / 0 / 0 | 0 / 0 |
| `is_current` | 38 | boolean_text:38 | 0 / 0 / 0 | 0 / 0 |
| `is_next` | 38 | boolean_text:38 | 0 / 0 / 0 | 0 / 0 |
| `is_previous` | 38 | boolean_text:38 | 0 / 0 / 0 | 0 / 0 |
| `most_captained` | 38 | decimal_text:4, empty:34 | 0 / 0 / 34 | 0 / 0 |
| `most_selected` | 38 | decimal_text:4, empty:34 | 0 / 0 / 34 | 0 / 0 |
| `most_transferred_in` | 38 | decimal_text:4, empty:34 | 0 / 0 / 34 | 0 / 0 |
| `most_vice_captained` | 38 | decimal_text:4, empty:34 | 0 / 0 / 34 | 0 / 0 |
| `name` | 38 | text:38 | 0 / 0 / 0 | 0 / 0 |
| `overrides` | 38 | text:38 | 0 / 0 / 0 | 0 / 0 |
| `ranked_count` | 38 | integer_text:38 | 0 / 0 / 0 | 0 / 0 |
| `release_time` | 38 | empty:38 | 0 / 0 / 38 | 0 / 0 |
| `released` | 38 | boolean_text:38 | 0 / 0 / 0 | 0 / 0 |
| `snapshot_time` | 38 | timestamp_text:38 | 0 / 0 / 0 | 0 / 0 |
| `top_element` | 38 | decimal_text:4, empty:34 | 0 / 0 / 34 | 0 / 0 |
| `top_element_info` | 38 | empty:34, text:4 | 0 / 0 / 34 | 0 / 0 |
| `transfers_made` | 38 | integer_text:38 | 0 / 0 / 0 | 0 / 0 |

### core_players — 657 rows; 7 top-level columns
Raw file: `raw/fpl_core/907f666f2dc6796d417e49287fd31f88263f1d67/data/2026-2027/players.csv`.

| Field/path | Population | Observed types:count | Absent / null / blank | Empty list / object |
| --- | ---: | --- | --- | --- |
| `first_name` | 657 | text:657 | 0 / 0 / 0 | 0 / 0 |
| `player_code` | 657 | integer_text:657 | 0 / 0 / 0 | 0 / 0 |
| `player_id` | 657 | integer_text:657 | 0 / 0 / 0 | 0 / 0 |
| `position` | 657 | text:657 | 0 / 0 / 0 | 0 / 0 |
| `second_name` | 657 | text:657 | 0 / 0 / 0 | 0 / 0 |
| `team_code` | 657 | integer_text:657 | 0 / 0 / 0 | 0 / 0 |
| `web_name` | 657 | text:657 | 0 / 0 / 0 | 0 / 0 |

### core_playerstats — 2581 rows; 87 top-level columns
Raw file: `raw/fpl_core/907f666f2dc6796d417e49287fd31f88263f1d67/data/2026-2027/playerstats.csv`.

| Field/path | Population | Observed types:count | Absent / null / blank | Empty list / object |
| --- | ---: | --- | --- | --- |
| `assists` | 2581 | integer_text:2581 | 0 / 0 / 0 | 0 / 0 |
| `bonus` | 2581 | integer_text:2581 | 0 / 0 / 0 | 0 / 0 |
| `bps` | 2581 | integer_text:2581 | 0 / 0 / 0 | 0 / 0 |
| `chance_of_playing_next_round` | 2581 | decimal_text:903, empty:1678 | 0 / 0 / 1678 | 0 / 0 |
| `chance_of_playing_this_round` | 2581 | decimal_text:787, empty:1794 | 0 / 0 / 1794 | 0 / 0 |
| `clean_sheets` | 2581 | integer_text:2581 | 0 / 0 / 0 | 0 / 0 |
| `clean_sheets_per_90` | 2581 | decimal_text:2581 | 0 / 0 / 0 | 0 / 0 |
| `clearances_blocks_interceptions` | 2581 | integer_text:2581 | 0 / 0 / 0 | 0 / 0 |
| `corners_and_indirect_freekicks_order` | 2581 | decimal_text:322, empty:2259 | 0 / 0 / 2259 | 0 / 0 |
| `corners_and_indirect_freekicks_text` | 2581 | empty:2581 | 0 / 0 / 2581 | 0 / 0 |
| `cost_change_event` | 2581 | integer_text:2581 | 0 / 0 / 0 | 0 / 0 |
| `cost_change_event_fall` | 2581 | integer_text:2581 | 0 / 0 / 0 | 0 / 0 |
| `cost_change_start` | 2581 | integer_text:2581 | 0 / 0 / 0 | 0 / 0 |
| `cost_change_start_fall` | 2581 | integer_text:2581 | 0 / 0 / 0 | 0 / 0 |
| `creativity` | 2581 | decimal_text:2581 | 0 / 0 / 0 | 0 / 0 |
| `creativity_rank` | 2581 | integer_text:2581 | 0 / 0 / 0 | 0 / 0 |
| `creativity_rank_type` | 2581 | integer_text:2581 | 0 / 0 / 0 | 0 / 0 |
| `defensive_contribution` | 2581 | integer_text:2581 | 0 / 0 / 0 | 0 / 0 |
| `defensive_contribution_per_90` | 2581 | decimal_text:2581 | 0 / 0 / 0 | 0 / 0 |
| `direct_freekicks_order` | 2581 | decimal_text:230, empty:2351 | 0 / 0 / 2351 | 0 / 0 |
| `direct_freekicks_text` | 2581 | empty:2581 | 0 / 0 / 2581 | 0 / 0 |
| `dreamteam_count` | 2581 | integer_text:2581 | 0 / 0 / 0 | 0 / 0 |
| `ep_next` | 2581 | decimal_text:2581 | 0 / 0 / 0 | 0 / 0 |
| `ep_this` | 2581 | decimal_text:2581 | 0 / 0 / 0 | 0 / 0 |
| `event_points` | 2581 | integer_text:2581 | 0 / 0 / 0 | 0 / 0 |
| `expected_assists` | 2581 | decimal_text:2581 | 0 / 0 / 0 | 0 / 0 |
| `expected_assists_per_90` | 2581 | decimal_text:2581 | 0 / 0 / 0 | 0 / 0 |
| `expected_goal_involvements` | 2581 | decimal_text:2581 | 0 / 0 / 0 | 0 / 0 |
| `expected_goal_involvements_per_90` | 2581 | decimal_text:2581 | 0 / 0 / 0 | 0 / 0 |
| `expected_goals` | 2581 | decimal_text:2581 | 0 / 0 / 0 | 0 / 0 |
| `expected_goals_conceded` | 2581 | decimal_text:2581 | 0 / 0 / 0 | 0 / 0 |
| `expected_goals_conceded_per_90` | 2581 | decimal_text:2581 | 0 / 0 / 0 | 0 / 0 |
| `expected_goals_per_90` | 2581 | decimal_text:2581 | 0 / 0 / 0 | 0 / 0 |
| `first_name` | 2581 | text:2581 | 0 / 0 / 0 | 0 / 0 |
| `form` | 2581 | decimal_text:2581 | 0 / 0 / 0 | 0 / 0 |
| `form_rank` | 2581 | integer_text:2581 | 0 / 0 / 0 | 0 / 0 |
| `form_rank_type` | 2581 | integer_text:2581 | 0 / 0 / 0 | 0 / 0 |
| `goals_conceded` | 2581 | integer_text:2581 | 0 / 0 / 0 | 0 / 0 |
| `goals_conceded_per_90` | 2581 | decimal_text:2581 | 0 / 0 / 0 | 0 / 0 |
| `goals_scored` | 2581 | integer_text:2581 | 0 / 0 / 0 | 0 / 0 |
| `gw` | 2581 | integer_text:2581 | 0 / 0 / 0 | 0 / 0 |
| `ict_index` | 2581 | decimal_text:2581 | 0 / 0 / 0 | 0 / 0 |
| `ict_index_rank` | 2581 | integer_text:2581 | 0 / 0 / 0 | 0 / 0 |
| `ict_index_rank_type` | 2581 | integer_text:2581 | 0 / 0 / 0 | 0 / 0 |
| `id` | 2581 | integer_text:2581 | 0 / 0 / 0 | 0 / 0 |
| `influence` | 2581 | decimal_text:2581 | 0 / 0 / 0 | 0 / 0 |
| `influence_rank` | 2581 | integer_text:2581 | 0 / 0 / 0 | 0 / 0 |
| `influence_rank_type` | 2581 | integer_text:2581 | 0 / 0 / 0 | 0 / 0 |
| `minutes` | 2581 | integer_text:2581 | 0 / 0 / 0 | 0 / 0 |
| `news` | 2581 | empty:1916, text:665 | 0 / 0 / 1916 | 0 / 0 |
| `news_added` | 2581 | empty:2581 | 0 / 0 / 2581 | 0 / 0 |
| `now_cost` | 2581 | decimal_text:2581 | 0 / 0 / 0 | 0 / 0 |
| `now_cost_rank` | 2581 | integer_text:2581 | 0 / 0 / 0 | 0 / 0 |
| `now_cost_rank_type` | 2581 | integer_text:2581 | 0 / 0 / 0 | 0 / 0 |
| `own_goals` | 2581 | integer_text:2581 | 0 / 0 / 0 | 0 / 0 |
| `penalties_missed` | 2581 | integer_text:2581 | 0 / 0 / 0 | 0 / 0 |
| `penalties_order` | 2581 | decimal_text:252, empty:2329 | 0 / 0 / 2329 | 0 / 0 |
| `penalties_saved` | 2581 | integer_text:2581 | 0 / 0 / 0 | 0 / 0 |
| `penalties_text` | 2581 | empty:2581 | 0 / 0 / 2581 | 0 / 0 |
| `points_per_game` | 2581 | decimal_text:2581 | 0 / 0 / 0 | 0 / 0 |
| `points_per_game_rank` | 2581 | integer_text:2581 | 0 / 0 / 0 | 0 / 0 |
| `points_per_game_rank_type` | 2581 | integer_text:2581 | 0 / 0 / 0 | 0 / 0 |
| `recoveries` | 2581 | integer_text:2581 | 0 / 0 / 0 | 0 / 0 |
| `red_cards` | 2581 | integer_text:2581 | 0 / 0 / 0 | 0 / 0 |
| `saves` | 2581 | integer_text:2581 | 0 / 0 / 0 | 0 / 0 |
| `saves_per_90` | 2581 | decimal_text:2581 | 0 / 0 / 0 | 0 / 0 |
| `second_name` | 2581 | text:2581 | 0 / 0 / 0 | 0 / 0 |
| `selected_by_percent` | 2581 | decimal_text:2581 | 0 / 0 / 0 | 0 / 0 |
| `selected_rank` | 2581 | integer_text:2581 | 0 / 0 / 0 | 0 / 0 |
| `selected_rank_type` | 2581 | integer_text:2581 | 0 / 0 / 0 | 0 / 0 |
| `set_piece_threat` | 2581 | empty:2581 | 0 / 0 / 2581 | 0 / 0 |
| `starts` | 2581 | integer_text:2581 | 0 / 0 / 0 | 0 / 0 |
| `starts_per_90` | 2581 | decimal_text:2581 | 0 / 0 / 0 | 0 / 0 |
| `status` | 2581 | text:2581 | 0 / 0 / 0 | 0 / 0 |
| `tackles` | 2581 | integer_text:2581 | 0 / 0 / 0 | 0 / 0 |
| `threat` | 2581 | decimal_text:2581 | 0 / 0 / 0 | 0 / 0 |
| `threat_rank` | 2581 | integer_text:2581 | 0 / 0 / 0 | 0 / 0 |
| `threat_rank_type` | 2581 | integer_text:2581 | 0 / 0 / 0 | 0 / 0 |
| `total_points` | 2581 | integer_text:2581 | 0 / 0 / 0 | 0 / 0 |
| `transfers_in` | 2581 | integer_text:2581 | 0 / 0 / 0 | 0 / 0 |
| `transfers_in_event` | 2581 | integer_text:2581 | 0 / 0 / 0 | 0 / 0 |
| `transfers_out` | 2581 | integer_text:2581 | 0 / 0 / 0 | 0 / 0 |
| `transfers_out_event` | 2581 | integer_text:2581 | 0 / 0 / 0 | 0 / 0 |
| `value_form` | 2581 | decimal_text:2581 | 0 / 0 / 0 | 0 / 0 |
| `value_season` | 2581 | decimal_text:2581 | 0 / 0 / 0 | 0 / 0 |
| `web_name` | 2581 | text:2581 | 0 / 0 / 0 | 0 / 0 |
| `yellow_cards` | 2581 | integer_text:2581 | 0 / 0 / 0 | 0 / 0 |

### core_teams — 20 rows; 14 top-level columns
Raw file: `raw/fpl_core/907f666f2dc6796d417e49287fd31f88263f1d67/data/2026-2027/teams.csv`.

| Field/path | Population | Observed types:count | Absent / null / blank | Empty list / object |
| --- | ---: | --- | --- | --- |
| `code` | 20 | integer_text:20 | 0 / 0 / 0 | 0 / 0 |
| `elo` | 20 | empty:20 | 0 / 0 / 20 | 0 / 0 |
| `fotmob_name` | 20 | empty:20 | 0 / 0 / 20 | 0 / 0 |
| `id` | 20 | integer_text:20 | 0 / 0 / 0 | 0 / 0 |
| `name` | 20 | text:20 | 0 / 0 / 0 | 0 / 0 |
| `pulse_id` | 20 | integer_text:20 | 0 / 0 / 0 | 0 / 0 |
| `short_name` | 20 | text:20 | 0 / 0 / 0 | 0 / 0 |
| `strength` | 20 | empty:20 | 0 / 0 / 20 | 0 / 0 |
| `strength_attack_away` | 20 | integer_text:20 | 0 / 0 / 0 | 0 / 0 |
| `strength_attack_home` | 20 | integer_text:20 | 0 / 0 / 0 | 0 / 0 |
| `strength_defence_away` | 20 | integer_text:20 | 0 / 0 / 0 | 0 / 0 |
| `strength_defence_home` | 20 | integer_text:20 | 0 / 0 / 0 | 0 / 0 |
| `strength_overall_away` | 20 | integer_text:20 | 0 / 0 / 0 | 0 / 0 |
| `strength_overall_home` | 20 | integer_text:20 | 0 / 0 / 0 | 0 / 0 |

### fpl_element_types — 4 rows; 13 top-level columns
Raw file: `raw/fpl_api/bootstrap_static.json`.

| Field/path | Population | Observed types:count | Absent / null / blank | Empty list / object |
| --- | ---: | --- | --- | --- |
| `element_count` | 4 | int:4 | 0 / 0 / 0 | 0 / 0 |
| `id` | 4 | int:4 | 0 / 0 / 0 | 0 / 0 |
| `plural_name` | 4 | str:4 | 0 / 0 / 0 | 0 / 0 |
| `plural_name_short` | 4 | str:4 | 0 / 0 / 0 | 0 / 0 |
| `singular_name` | 4 | str:4 | 0 / 0 / 0 | 0 / 0 |
| `singular_name_short` | 4 | str:4 | 0 / 0 / 0 | 0 / 0 |
| `squad_max_play` | 4 | int:4 | 0 / 0 / 0 | 0 / 0 |
| `squad_max_select` | 4 | NoneType:4 | 0 / 4 / 0 | 0 / 0 |
| `squad_min_play` | 4 | int:4 | 0 / 0 / 0 | 0 / 0 |
| `squad_min_select` | 4 | NoneType:4 | 0 / 4 / 0 | 0 / 0 |
| `squad_select` | 4 | int:4 | 0 / 0 / 0 | 0 / 0 |
| `sub_positions_locked` | 4 | list:4 | 0 / 0 / 0 | 3 / 0 |
| `ui_shirt_specific` | 4 | bool:4 | 0 / 0 / 0 | 0 / 0 |

### fpl_elements — 657 rows; 109 top-level columns
Raw file: `raw/fpl_api/bootstrap_static.json`.

| Field/path | Population | Observed types:count | Absent / null / blank | Empty list / object |
| --- | ---: | --- | --- | --- |
| `assists` | 657 | int:657 | 0 / 0 / 0 | 0 / 0 |
| `birth_date` | 657 | NoneType:16, str:641 | 0 / 16 / 0 | 0 / 0 |
| `bonus` | 657 | int:657 | 0 / 0 / 0 | 0 / 0 |
| `bps` | 657 | int:657 | 0 / 0 / 0 | 0 / 0 |
| `can_select` | 657 | bool:657 | 0 / 0 / 0 | 0 / 0 |
| `can_transact` | 657 | bool:657 | 0 / 0 / 0 | 0 / 0 |
| `chance_of_playing_next_round` | 657 | NoneType:400, int:257 | 0 / 400 / 0 | 0 / 0 |
| `chance_of_playing_this_round` | 657 | NoneType:408, int:249 | 0 / 408 / 0 | 0 / 0 |
| `clean_sheets` | 657 | int:657 | 0 / 0 / 0 | 0 / 0 |
| `clean_sheets_per_90` | 657 | float:404, int:253 | 0 / 0 / 0 | 0 / 0 |
| `clearances_blocks_interceptions` | 657 | int:657 | 0 / 0 / 0 | 0 / 0 |
| `code` | 657 | int:657 | 0 / 0 / 0 | 0 / 0 |
| `corners_and_indirect_freekicks_order` | 657 | NoneType:576, int:81 | 0 / 576 / 0 | 0 / 0 |
| `corners_and_indirect_freekicks_text` | 657 | str:657 | 0 / 0 / 657 | 0 / 0 |
| `cost_change_event` | 657 | int:657 | 0 / 0 / 0 | 0 / 0 |
| `cost_change_event_fall` | 657 | int:657 | 0 / 0 / 0 | 0 / 0 |
| `cost_change_start` | 657 | int:657 | 0 / 0 / 0 | 0 / 0 |
| `cost_change_start_fall` | 657 | int:657 | 0 / 0 / 0 | 0 / 0 |
| `creativity` | 657 | str:657 | 0 / 0 / 0 | 0 / 0 |
| `creativity_rank` | 657 | int:657 | 0 / 0 / 0 | 0 / 0 |
| `creativity_rank_type` | 657 | int:657 | 0 / 0 / 0 | 0 / 0 |
| `defensive_contribution` | 657 | int:657 | 0 / 0 / 0 | 0 / 0 |
| `defensive_contribution_per_90` | 657 | float:404, int:253 | 0 / 0 / 0 | 0 / 0 |
| `direct_freekicks_order` | 657 | NoneType:598, int:59 | 0 / 598 / 0 | 0 / 0 |
| `direct_freekicks_text` | 657 | str:657 | 0 / 0 / 657 | 0 / 0 |
| `dreamteam_count` | 657 | int:657 | 0 / 0 / 0 | 0 / 0 |
| `element_type` | 657 | int:657 | 0 / 0 / 0 | 0 / 0 |
| `ep_next` | 657 | str:657 | 0 / 0 / 0 | 0 / 0 |
| `ep_this` | 657 | str:657 | 0 / 0 / 0 | 0 / 0 |
| `event_points` | 657 | int:657 | 0 / 0 / 0 | 0 / 0 |
| `expected_assists` | 657 | str:657 | 0 / 0 / 0 | 0 / 0 |
| `expected_assists_per_90` | 657 | float:404, int:253 | 0 / 0 / 0 | 0 / 0 |
| `expected_goal_involvements` | 657 | str:657 | 0 / 0 / 0 | 0 / 0 |
| `expected_goal_involvements_per_90` | 657 | float:404, int:253 | 0 / 0 / 0 | 0 / 0 |
| `expected_goals` | 657 | str:657 | 0 / 0 / 0 | 0 / 0 |
| `expected_goals_conceded` | 657 | str:657 | 0 / 0 / 0 | 0 / 0 |
| `expected_goals_conceded_per_90` | 657 | float:404, int:253 | 0 / 0 / 0 | 0 / 0 |
| `expected_goals_per_90` | 657 | float:404, int:253 | 0 / 0 / 0 | 0 / 0 |
| `first_name` | 657 | str:657 | 0 / 0 / 0 | 0 / 0 |
| `form` | 657 | str:657 | 0 / 0 / 0 | 0 / 0 |
| `form_rank` | 657 | int:657 | 0 / 0 / 0 | 0 / 0 |
| `form_rank_type` | 657 | int:657 | 0 / 0 / 0 | 0 / 0 |
| `goals_conceded` | 657 | int:657 | 0 / 0 / 0 | 0 / 0 |
| `goals_conceded_per_90` | 657 | float:404, int:253 | 0 / 0 / 0 | 0 / 0 |
| `goals_scored` | 657 | int:657 | 0 / 0 / 0 | 0 / 0 |
| `has_temporary_code` | 657 | bool:657 | 0 / 0 / 0 | 0 / 0 |
| `ict_index` | 657 | str:657 | 0 / 0 / 0 | 0 / 0 |
| `ict_index_rank` | 657 | int:657 | 0 / 0 / 0 | 0 / 0 |
| `ict_index_rank_type` | 657 | int:657 | 0 / 0 / 0 | 0 / 0 |
| `id` | 657 | int:657 | 0 / 0 / 0 | 0 / 0 |
| `in_dreamteam` | 657 | bool:657 | 0 / 0 / 0 | 0 / 0 |
| `influence` | 657 | str:657 | 0 / 0 / 0 | 0 / 0 |
| `influence_rank` | 657 | int:657 | 0 / 0 / 0 | 0 / 0 |
| `influence_rank_type` | 657 | int:657 | 0 / 0 / 0 | 0 / 0 |
| `known_name` | 657 | str:657 | 0 / 0 / 583 | 0 / 0 |
| `minutes` | 657 | int:657 | 0 / 0 / 0 | 0 / 0 |
| `news` | 657 | str:657 | 0 / 0 / 469 | 0 / 0 |
| `news_added` | 657 | NoneType:400, str:257 | 0 / 400 / 0 | 0 / 0 |
| `now_cost` | 657 | int:657 | 0 / 0 / 0 | 0 / 0 |
| `now_cost_rank` | 657 | int:657 | 0 / 0 / 0 | 0 / 0 |
| `now_cost_rank_type` | 657 | int:657 | 0 / 0 / 0 | 0 / 0 |
| `opta_code` | 657 | str:657 | 0 / 0 / 0 | 0 / 0 |
| `own_goals` | 657 | int:657 | 0 / 0 / 0 | 0 / 0 |
| `penalties_missed` | 657 | int:657 | 0 / 0 / 0 | 0 / 0 |
| `penalties_order` | 657 | NoneType:596, int:61 | 0 / 596 / 0 | 0 / 0 |
| `penalties_saved` | 657 | int:657 | 0 / 0 / 0 | 0 / 0 |
| `penalties_text` | 657 | str:657 | 0 / 0 / 657 | 0 / 0 |
| `photo` | 657 | str:657 | 0 / 0 / 0 | 0 / 0 |
| `points_per_game` | 657 | str:657 | 0 / 0 / 0 | 0 / 0 |
| `points_per_game_rank` | 657 | int:657 | 0 / 0 / 0 | 0 / 0 |
| `points_per_game_rank_type` | 657 | int:657 | 0 / 0 / 0 | 0 / 0 |
| `price_change_calibrating` | 657 | bool:657 | 0 / 0 / 0 | 0 / 0 |
| `price_change_hourly_rate` | 657 | int:657 | 0 / 0 / 0 | 0 / 0 |
| `price_change_locked_until` | 657 | NoneType:621, str:36 | 0 / 621 / 0 | 0 / 0 |
| `price_change_percent` | 657 | str:657 | 0 / 0 / 0 | 0 / 0 |
| `price_change_projections` | 657 | list:657 | 0 / 0 / 0 | 0 / 0 |
| `price_change_projections[].likelihood` | 1971 | int:1971 | 0 / 0 / 0 | 0 / 0 |
| `price_change_projections[].offset` | 1971 | int:1971 | 0 / 0 / 0 | 0 / 0 |
| `price_change_projections[].projected_percent` | 1971 | str:1971 | 0 / 0 / 0 | 0 / 0 |
| `recoveries` | 657 | int:657 | 0 / 0 / 0 | 0 / 0 |
| `red_cards` | 657 | int:657 | 0 / 0 / 0 | 0 / 0 |
| `region` | 657 | NoneType:16, int:641 | 0 / 16 / 0 | 0 / 0 |
| `removed` | 657 | bool:657 | 0 / 0 / 0 | 0 / 0 |
| `saves` | 657 | int:657 | 0 / 0 / 0 | 0 / 0 |
| `saves_per_90` | 657 | float:404, int:253 | 0 / 0 / 0 | 0 / 0 |
| `scout_news_link` | 657 | str:657 | 0 / 0 / 601 | 0 / 0 |
| `scout_risks` | 657 | list:657 | 0 / 0 / 0 | 650 / 0 |
| `scout_risks[].gameweek` | 14 | int:14 | 0 / 0 / 0 | 0 / 0 |
| `scout_risks[].notes` | 14 | str:14 | 0 / 0 / 0 | 0 / 0 |
| `scout_risks[].property` | 14 | str:14 | 0 / 0 / 0 | 0 / 0 |
| `scout_risks[].url` | 14 | NoneType:14 | 0 / 14 / 0 | 0 / 0 |
| `second_name` | 657 | str:657 | 0 / 0 / 0 | 0 / 0 |
| `selected_by_percent` | 657 | str:657 | 0 / 0 / 0 | 0 / 0 |
| `selected_rank` | 657 | int:657 | 0 / 0 / 0 | 0 / 0 |
| `selected_rank_type` | 657 | int:657 | 0 / 0 / 0 | 0 / 0 |
| `special` | 657 | bool:657 | 0 / 0 / 0 | 0 / 0 |
| `squad_number` | 657 | NoneType:657 | 0 / 657 / 0 | 0 / 0 |
| `starts` | 657 | int:657 | 0 / 0 / 0 | 0 / 0 |
| `starts_per_90` | 657 | float:404, int:253 | 0 / 0 / 0 | 0 / 0 |
| `status` | 657 | str:657 | 0 / 0 / 0 | 0 / 0 |
| `tackles` | 657 | int:657 | 0 / 0 / 0 | 0 / 0 |
| `team` | 657 | int:657 | 0 / 0 / 0 | 0 / 0 |
| `team_code` | 657 | int:657 | 0 / 0 / 0 | 0 / 0 |
| `team_join_date` | 657 | NoneType:16, str:641 | 0 / 16 / 0 | 0 / 0 |
| `threat` | 657 | str:657 | 0 / 0 / 0 | 0 / 0 |
| `threat_rank` | 657 | int:657 | 0 / 0 / 0 | 0 / 0 |
| `threat_rank_type` | 657 | int:657 | 0 / 0 / 0 | 0 / 0 |
| `total_points` | 657 | int:657 | 0 / 0 / 0 | 0 / 0 |
| `transfers_in` | 657 | int:657 | 0 / 0 / 0 | 0 / 0 |
| `transfers_in_event` | 657 | int:657 | 0 / 0 / 0 | 0 / 0 |
| `transfers_out` | 657 | int:657 | 0 / 0 / 0 | 0 / 0 |
| `transfers_out_event` | 657 | int:657 | 0 / 0 / 0 | 0 / 0 |
| `value_form` | 657 | str:657 | 0 / 0 / 0 | 0 / 0 |
| `value_season` | 657 | str:657 | 0 / 0 / 0 | 0 / 0 |
| `web_name` | 657 | str:657 | 0 / 0 / 0 | 0 / 0 |
| `yellow_cards` | 657 | int:657 | 0 / 0 / 0 | 0 / 0 |

### fpl_events — 38 rows; 29 top-level columns
Raw file: `raw/fpl_api/bootstrap_static.json`.

| Field/path | Population | Observed types:count | Absent / null / blank | Empty list / object |
| --- | ---: | --- | --- | --- |
| `average_entry_score` | 38 | int:38 | 0 / 0 / 0 | 0 / 0 |
| `can_enter` | 38 | bool:38 | 0 / 0 / 0 | 0 / 0 |
| `can_manage` | 38 | bool:38 | 0 / 0 / 0 | 0 / 0 |
| `chip_plays` | 38 | list:38 | 0 / 0 / 0 | 34 / 0 |
| `chip_plays[].chip_name` | 14 | str:14 | 0 / 0 / 0 | 0 / 0 |
| `chip_plays[].num_played` | 14 | int:14 | 0 / 0 / 0 | 0 / 0 |
| `cup_leagues_created` | 38 | bool:38 | 0 / 0 / 0 | 0 / 0 |
| `data_checked` | 38 | bool:38 | 0 / 0 / 0 | 0 / 0 |
| `deadline_time` | 38 | str:38 | 0 / 0 / 0 | 0 / 0 |
| `deadline_time_epoch` | 38 | int:38 | 0 / 0 / 0 | 0 / 0 |
| `deadline_time_game_offset` | 38 | int:38 | 0 / 0 / 0 | 0 / 0 |
| `finished` | 38 | bool:38 | 0 / 0 / 0 | 0 / 0 |
| `h2h_ko_matches_created` | 38 | bool:38 | 0 / 0 / 0 | 0 / 0 |
| `highest_score` | 38 | NoneType:34, int:4 | 0 / 34 / 0 | 0 / 0 |
| `highest_scoring_entry` | 38 | NoneType:34, int:4 | 0 / 34 / 0 | 0 / 0 |
| `id` | 38 | int:38 | 0 / 0 / 0 | 0 / 0 |
| `is_current` | 38 | bool:38 | 0 / 0 / 0 | 0 / 0 |
| `is_next` | 38 | bool:38 | 0 / 0 / 0 | 0 / 0 |
| `is_previous` | 38 | bool:38 | 0 / 0 / 0 | 0 / 0 |
| `most_captained` | 38 | NoneType:34, int:4 | 0 / 34 / 0 | 0 / 0 |
| `most_selected` | 38 | NoneType:34, int:4 | 0 / 34 / 0 | 0 / 0 |
| `most_transferred_in` | 38 | NoneType:34, int:4 | 0 / 34 / 0 | 0 / 0 |
| `most_vice_captained` | 38 | NoneType:34, int:4 | 0 / 34 / 0 | 0 / 0 |
| `name` | 38 | str:38 | 0 / 0 / 0 | 0 / 0 |
| `overrides` | 38 | dict:38 | 0 / 0 / 0 | 0 / 0 |
| `overrides.element_types` | 38 | list:38 | 0 / 0 / 0 | 38 / 0 |
| `overrides.pick_multiplier` | 38 | NoneType:38 | 0 / 38 / 0 | 0 / 0 |
| `overrides.rules` | 38 | dict:38 | 0 / 0 / 0 | 0 / 38 |
| `overrides.scoring` | 38 | dict:38 | 0 / 0 / 0 | 0 / 38 |
| `ranked_count` | 38 | int:38 | 0 / 0 / 0 | 0 / 0 |
| `release_time` | 38 | NoneType:38 | 0 / 38 / 0 | 0 / 0 |
| `released` | 38 | bool:38 | 0 / 0 / 0 | 0 / 0 |
| `top_element` | 38 | NoneType:34, int:4 | 0 / 34 / 0 | 0 / 0 |
| `top_element_info` | 38 | NoneType:34, dict:4 | 0 / 34 / 0 | 0 / 0 |
| `top_element_info.id` | 4 | int:4 | 0 / 0 / 0 | 0 / 0 |
| `top_element_info.points` | 4 | int:4 | 0 / 0 / 0 | 0 / 0 |
| `transfers_made` | 38 | int:38 | 0 / 0 / 0 | 0 / 0 |

### fpl_fixtures — 380 rows; 17 top-level columns
Raw file: `raw/fpl_api/fixtures.json`.

| Field/path | Population | Observed types:count | Absent / null / blank | Empty list / object |
| --- | ---: | --- | --- | --- |
| `code` | 380 | int:380 | 0 / 0 / 0 | 0 / 0 |
| `event` | 380 | int:380 | 0 / 0 / 0 | 0 / 0 |
| `finished` | 380 | bool:380 | 0 / 0 / 0 | 0 / 0 |
| `finished_provisional` | 380 | bool:380 | 0 / 0 / 0 | 0 / 0 |
| `id` | 380 | int:380 | 0 / 0 / 0 | 0 / 0 |
| `kickoff_time` | 380 | str:380 | 0 / 0 / 0 | 0 / 0 |
| `minutes` | 380 | int:380 | 0 / 0 / 0 | 0 / 0 |
| `provisional_start_time` | 380 | bool:380 | 0 / 0 / 0 | 0 / 0 |
| `pulse_id` | 380 | int:380 | 0 / 0 / 0 | 0 / 0 |
| `started` | 380 | bool:380 | 0 / 0 / 0 | 0 / 0 |
| `stats` | 380 | list:380 | 0 / 0 / 0 | 341 / 0 |
| `stats[].a` | 429 | list:429 | 0 / 0 / 0 | 193 / 0 |
| `stats[].a[].element` | 1358 | int:1358 | 0 / 0 / 0 | 0 / 0 |
| `stats[].a[].value` | 1358 | int:1358 | 0 / 0 / 0 | 0 / 0 |
| `stats[].h` | 429 | list:429 | 0 / 0 / 0 | 199 / 0 |
| `stats[].h[].element` | 1352 | int:1352 | 0 / 0 / 0 | 0 / 0 |
| `stats[].h[].value` | 1352 | int:1352 | 0 / 0 / 0 | 0 / 0 |
| `stats[].identifier` | 429 | str:429 | 0 / 0 / 0 | 0 / 0 |
| `team_a` | 380 | int:380 | 0 / 0 / 0 | 0 / 0 |
| `team_a_difficulty` | 380 | int:380 | 0 / 0 / 0 | 0 / 0 |
| `team_a_score` | 380 | NoneType:341, int:39 | 0 / 341 / 0 | 0 / 0 |
| `team_h` | 380 | int:380 | 0 / 0 / 0 | 0 / 0 |
| `team_h_difficulty` | 380 | int:380 | 0 / 0 / 0 | 0 / 0 |
| `team_h_score` | 380 | NoneType:341, int:39 | 0 / 341 / 0 | 0 / 0 |

### fpl_teams — 20 rows; 22 top-level columns
Raw file: `raw/fpl_api/bootstrap_static.json`.

| Field/path | Population | Observed types:count | Absent / null / blank | Empty list / object |
| --- | ---: | --- | --- | --- |
| `code` | 20 | int:20 | 0 / 0 / 0 | 0 / 0 |
| `draw` | 20 | int:20 | 0 / 0 / 0 | 0 / 0 |
| `form` | 20 | NoneType:20 | 0 / 20 / 0 | 0 / 0 |
| `id` | 20 | int:20 | 0 / 0 / 0 | 0 / 0 |
| `link_url` | 20 | str:20 | 0 / 0 / 20 | 0 / 0 |
| `loss` | 20 | int:20 | 0 / 0 / 0 | 0 / 0 |
| `name` | 20 | str:20 | 0 / 0 / 0 | 0 / 0 |
| `played` | 20 | int:20 | 0 / 0 / 0 | 0 / 0 |
| `points` | 20 | int:20 | 0 / 0 / 0 | 0 / 0 |
| `position` | 20 | int:20 | 0 / 0 / 0 | 0 / 0 |
| `pulse_id` | 20 | int:20 | 0 / 0 / 0 | 0 / 0 |
| `short_name` | 20 | str:20 | 0 / 0 / 0 | 0 / 0 |
| `strength` | 20 | NoneType:20 | 0 / 20 / 0 | 0 / 0 |
| `strength_attack_away` | 20 | int:20 | 0 / 0 / 0 | 0 / 0 |
| `strength_attack_home` | 20 | int:20 | 0 / 0 / 0 | 0 / 0 |
| `strength_defence_away` | 20 | int:20 | 0 / 0 / 0 | 0 / 0 |
| `strength_defence_home` | 20 | int:20 | 0 / 0 / 0 | 0 / 0 |
| `strength_overall_away` | 20 | int:20 | 0 / 0 / 0 | 0 / 0 |
| `strength_overall_home` | 20 | int:20 | 0 / 0 / 0 | 0 / 0 |
| `team_division` | 20 | NoneType:20 | 0 / 20 / 0 | 0 / 0 |
| `unavailable` | 20 | bool:20 | 0 / 0 / 0 | 0 / 0 |
| `win` | 20 | int:20 | 0 / 0 / 0 | 0 / 0 |

### odds — 190 rows; 94 top-level columns
Raw file: `raw/football_data_uk/attempt_02/fixtures.csv`.

| Field/path | Population | Observed types:count | Absent / null / blank | Empty list / object |
| --- | ---: | --- | --- | --- |
| `AHCh` | 190 | empty:190 | 0 / 0 / 190 | 0 / 0 |
| `AHh` | 190 | decimal_text:130, integer_text:60 | 0 / 0 / 0 | 0 / 0 |
| `Avg<2.5` | 190 | decimal_text:187, integer_text:3 | 0 / 0 / 0 | 0 / 0 |
| `Avg>2.5` | 190 | decimal_text:187, integer_text:3 | 0 / 0 / 0 | 0 / 0 |
| `AvgA` | 190 | decimal_text:188, integer_text:2 | 0 / 0 / 0 | 0 / 0 |
| `AvgAHA` | 190 | decimal_text:185, integer_text:5 | 0 / 0 / 0 | 0 / 0 |
| `AvgAHH` | 190 | decimal_text:188, integer_text:2 | 0 / 0 / 0 | 0 / 0 |
| `AvgC<2.5` | 190 | empty:190 | 0 / 0 / 190 | 0 / 0 |
| `AvgC>2.5` | 190 | empty:190 | 0 / 0 / 190 | 0 / 0 |
| `AvgCA` | 190 | empty:190 | 0 / 0 / 190 | 0 / 0 |
| `AvgCAHA` | 190 | empty:190 | 0 / 0 / 190 | 0 / 0 |
| `AvgCAHH` | 190 | empty:190 | 0 / 0 / 190 | 0 / 0 |
| `AvgCD` | 190 | empty:190 | 0 / 0 / 190 | 0 / 0 |
| `AvgCH` | 190 | empty:190 | 0 / 0 / 190 | 0 / 0 |
| `AvgD` | 190 | decimal_text:189, integer_text:1 | 0 / 0 / 0 | 0 / 0 |
| `AvgH` | 190 | decimal_text:187, integer_text:3 | 0 / 0 / 0 | 0 / 0 |
| `AwayTeam` | 190 | text:190 | 0 / 0 / 0 | 0 / 0 |
| `B365<2.5` | 190 | decimal_text:173, integer_text:17 | 0 / 0 / 0 | 0 / 0 |
| `B365>2.5` | 190 | decimal_text:187, integer_text:3 | 0 / 0 / 0 | 0 / 0 |
| `B365A` | 190 | decimal_text:162, integer_text:28 | 0 / 0 / 0 | 0 / 0 |
| `B365AHA` | 190 | decimal_text:178, empty:1, integer_text:11 | 0 / 0 / 1 | 0 / 0 |
| `B365AHH` | 190 | decimal_text:169, empty:1, integer_text:20 | 0 / 0 / 1 | 0 / 0 |
| `B365C<2.5` | 190 | empty:190 | 0 / 0 / 190 | 0 / 0 |
| `B365C>2.5` | 190 | empty:190 | 0 / 0 / 190 | 0 / 0 |
| `B365CA` | 190 | empty:190 | 0 / 0 / 190 | 0 / 0 |
| `B365CAHA` | 190 | empty:190 | 0 / 0 / 190 | 0 / 0 |
| `B365CAHH` | 190 | empty:190 | 0 / 0 / 190 | 0 / 0 |
| `B365CD` | 190 | empty:190 | 0 / 0 / 190 | 0 / 0 |
| `B365CH` | 190 | empty:190 | 0 / 0 / 190 | 0 / 0 |
| `B365D` | 190 | decimal_text:161, integer_text:29 | 0 / 0 / 0 | 0 / 0 |
| `B365H` | 190 | decimal_text:177, integer_text:13 | 0 / 0 / 0 | 0 / 0 |
| `BFDA` | 190 | decimal_text:151, integer_text:39 | 0 / 0 / 0 | 0 / 0 |
| `BFDCA` | 190 | empty:190 | 0 / 0 / 190 | 0 / 0 |
| `BFDCD` | 190 | empty:190 | 0 / 0 / 190 | 0 / 0 |
| `BFDCH` | 190 | empty:190 | 0 / 0 / 190 | 0 / 0 |
| `BFDD` | 190 | decimal_text:153, integer_text:37 | 0 / 0 / 0 | 0 / 0 |
| `BFDH` | 190 | decimal_text:165, integer_text:25 | 0 / 0 / 0 | 0 / 0 |
| `BFE<2.5` | 190 | decimal_text:176, empty:5, integer_text:9 | 0 / 0 / 5 | 0 / 0 |
| `BFE>2.5` | 190 | decimal_text:181, empty:5, integer_text:4 | 0 / 0 / 5 | 0 / 0 |
| `BFEA` | 190 | decimal_text:170, empty:2, integer_text:18 | 0 / 0 / 2 | 0 / 0 |
| `BFEAHA` | 190 | decimal_text:153, empty:32, integer_text:5 | 0 / 0 / 32 | 0 / 0 |
| `BFEAHH` | 190 | decimal_text:151, empty:32, integer_text:7 | 0 / 0 / 32 | 0 / 0 |
| `BFEC<2.5` | 190 | empty:190 | 0 / 0 / 190 | 0 / 0 |
| `BFEC>2.5` | 190 | empty:190 | 0 / 0 / 190 | 0 / 0 |
| `BFECA` | 190 | empty:190 | 0 / 0 / 190 | 0 / 0 |
| `BFECAHA` | 190 | empty:190 | 0 / 0 / 190 | 0 / 0 |
| `BFECAHH` | 190 | empty:190 | 0 / 0 / 190 | 0 / 0 |
| `BFECD` | 190 | empty:190 | 0 / 0 / 190 | 0 / 0 |
| `BFECH` | 190 | empty:190 | 0 / 0 / 190 | 0 / 0 |
| `BFED` | 190 | decimal_text:172, empty:2, integer_text:16 | 0 / 0 / 2 | 0 / 0 |
| `BFEH` | 190 | decimal_text:180, empty:2, integer_text:8 | 0 / 0 / 2 | 0 / 0 |
| `BVA` | 190 | decimal_text:174, integer_text:16 | 0 / 0 / 0 | 0 / 0 |
| `BVCA` | 190 | empty:190 | 0 / 0 / 190 | 0 / 0 |
| `BVCD` | 190 | empty:190 | 0 / 0 / 190 | 0 / 0 |
| `BVCH` | 190 | empty:190 | 0 / 0 / 190 | 0 / 0 |
| `BVD` | 190 | decimal_text:168, integer_text:22 | 0 / 0 / 0 | 0 / 0 |
| `BVH` | 190 | decimal_text:172, integer_text:18 | 0 / 0 / 0 | 0 / 0 |
| `BWA` | 190 | decimal_text:168, integer_text:22 | 0 / 0 / 0 | 0 / 0 |
| `BWCA` | 190 | empty:190 | 0 / 0 / 190 | 0 / 0 |
| `BWCD` | 190 | empty:190 | 0 / 0 / 190 | 0 / 0 |
| `BWCH` | 190 | empty:190 | 0 / 0 / 190 | 0 / 0 |
| `BWD` | 190 | decimal_text:173, integer_text:17 | 0 / 0 / 0 | 0 / 0 |
| `BWH` | 190 | decimal_text:177, integer_text:13 | 0 / 0 / 0 | 0 / 0 |
| `Date` | 190 | text:190 | 0 / 0 / 0 | 0 / 0 |
| `Div` | 190 | text:190 | 0 / 0 / 0 | 0 / 0 |
| `HomeTeam` | 190 | text:190 | 0 / 0 / 0 | 0 / 0 |
| `Max<2.5` | 190 | decimal_text:173, integer_text:17 | 0 / 0 / 0 | 0 / 0 |
| `Max>2.5` | 190 | decimal_text:184, integer_text:6 | 0 / 0 / 0 | 0 / 0 |
| `MaxA` | 190 | decimal_text:170, integer_text:20 | 0 / 0 / 0 | 0 / 0 |
| `MaxAHA` | 190 | decimal_text:177, integer_text:13 | 0 / 0 / 0 | 0 / 0 |
| `MaxAHH` | 190 | decimal_text:167, integer_text:23 | 0 / 0 / 0 | 0 / 0 |
| `MaxC<2.5` | 190 | empty:190 | 0 / 0 / 190 | 0 / 0 |
| `MaxC>2.5` | 190 | empty:190 | 0 / 0 / 190 | 0 / 0 |
| `MaxCA` | 190 | empty:190 | 0 / 0 / 190 | 0 / 0 |
| `MaxCAHA` | 190 | empty:190 | 0 / 0 / 190 | 0 / 0 |
| `MaxCAHH` | 190 | empty:190 | 0 / 0 / 190 | 0 / 0 |
| `MaxCD` | 190 | empty:190 | 0 / 0 / 190 | 0 / 0 |
| `MaxCH` | 190 | empty:190 | 0 / 0 / 190 | 0 / 0 |
| `MaxD` | 190 | decimal_text:159, integer_text:31 | 0 / 0 / 0 | 0 / 0 |
| `MaxH` | 190 | decimal_text:178, integer_text:12 | 0 / 0 / 0 | 0 / 0 |
| `PPA` | 190 | decimal_text:156, integer_text:34 | 0 / 0 / 0 | 0 / 0 |
| `PPCA` | 190 | empty:190 | 0 / 0 / 190 | 0 / 0 |
| `PPCD` | 190 | empty:190 | 0 / 0 / 190 | 0 / 0 |
| `PPCH` | 190 | empty:190 | 0 / 0 / 190 | 0 / 0 |
| `PPD` | 190 | decimal_text:157, integer_text:33 | 0 / 0 / 0 | 0 / 0 |
| `PPH` | 190 | decimal_text:169, integer_text:21 | 0 / 0 / 0 | 0 / 0 |
| `Referee` | 190 | empty:120, text:70 | 0 / 0 / 120 | 0 / 0 |
| `SKBA` | 190 | decimal_text:166, integer_text:24 | 0 / 0 / 0 | 0 / 0 |
| `SKBCA` | 190 | empty:190 | 0 / 0 / 190 | 0 / 0 |
| `SKBCD` | 190 | empty:190 | 0 / 0 / 190 | 0 / 0 |
| `SKBCH` | 190 | empty:190 | 0 / 0 / 190 | 0 / 0 |
| `SKBD` | 190 | decimal_text:164, integer_text:26 | 0 / 0 / 0 | 0 / 0 |
| `SKBH` | 190 | decimal_text:175, integer_text:15 | 0 / 0 / 0 | 0 / 0 |
| `Time` | 190 | text:190 | 0 / 0 / 0 | 0 / 0 |

### org_CL — 144 rows; 15 top-level columns
Raw file: `raw/football_data_org/CL/attempt_01/matches.json`.

| Field/path | Population | Observed types:count | Absent / null / blank | Empty list / object |
| --- | ---: | --- | --- | --- |
| `area` | 144 | dict:144 | 0 / 0 / 0 | 0 / 0 |
| `area.code` | 144 | str:144 | 0 / 0 / 0 | 0 / 0 |
| `area.flag` | 144 | str:144 | 0 / 0 / 0 | 0 / 0 |
| `area.id` | 144 | int:144 | 0 / 0 / 0 | 0 / 0 |
| `area.name` | 144 | str:144 | 0 / 0 / 0 | 0 / 0 |
| `awayTeam` | 144 | dict:144 | 0 / 0 / 0 | 0 / 0 |
| `awayTeam.crest` | 144 | str:144 | 0 / 0 / 0 | 0 / 0 |
| `awayTeam.id` | 144 | int:144 | 0 / 0 / 0 | 0 / 0 |
| `awayTeam.name` | 144 | str:144 | 0 / 0 / 0 | 0 / 0 |
| `awayTeam.shortName` | 144 | str:144 | 0 / 0 / 0 | 0 / 0 |
| `awayTeam.tla` | 144 | str:144 | 0 / 0 / 0 | 0 / 0 |
| `competition` | 144 | dict:144 | 0 / 0 / 0 | 0 / 0 |
| `competition.code` | 144 | str:144 | 0 / 0 / 0 | 0 / 0 |
| `competition.emblem` | 144 | str:144 | 0 / 0 / 0 | 0 / 0 |
| `competition.id` | 144 | int:144 | 0 / 0 / 0 | 0 / 0 |
| `competition.name` | 144 | str:144 | 0 / 0 / 0 | 0 / 0 |
| `competition.type` | 144 | str:144 | 0 / 0 / 0 | 0 / 0 |
| `group` | 144 | NoneType:144 | 0 / 144 / 0 | 0 / 0 |
| `homeTeam` | 144 | dict:144 | 0 / 0 / 0 | 0 / 0 |
| `homeTeam.crest` | 144 | str:144 | 0 / 0 / 0 | 0 / 0 |
| `homeTeam.id` | 144 | int:144 | 0 / 0 / 0 | 0 / 0 |
| `homeTeam.name` | 144 | str:144 | 0 / 0 / 0 | 0 / 0 |
| `homeTeam.shortName` | 144 | str:144 | 0 / 0 / 0 | 0 / 0 |
| `homeTeam.tla` | 144 | str:144 | 0 / 0 / 0 | 0 / 0 |
| `id` | 144 | int:144 | 0 / 0 / 0 | 0 / 0 |
| `lastUpdated` | 144 | str:144 | 0 / 0 / 0 | 0 / 0 |
| `matchday` | 144 | int:144 | 0 / 0 / 0 | 0 / 0 |
| `odds` | 144 | dict:144 | 0 / 0 / 0 | 0 / 0 |
| `odds.msg` | 144 | str:144 | 0 / 0 / 0 | 0 / 0 |
| `referees` | 144 | list:144 | 0 / 0 / 0 | 126 / 0 |
| `referees[].id` | 18 | int:18 | 0 / 0 / 0 | 0 / 0 |
| `referees[].name` | 18 | str:18 | 0 / 0 / 0 | 0 / 0 |
| `referees[].nationality` | 18 | str:18 | 0 / 0 / 0 | 0 / 0 |
| `referees[].type` | 18 | str:18 | 0 / 0 / 0 | 0 / 0 |
| `score` | 144 | dict:144 | 0 / 0 / 0 | 0 / 0 |
| `score.duration` | 144 | str:144 | 0 / 0 / 0 | 0 / 0 |
| `score.fullTime` | 144 | dict:144 | 0 / 0 / 0 | 0 / 0 |
| `score.fullTime.away` | 144 | NoneType:126, int:18 | 0 / 126 / 0 | 0 / 0 |
| `score.fullTime.home` | 144 | NoneType:126, int:18 | 0 / 126 / 0 | 0 / 0 |
| `score.halfTime` | 144 | dict:144 | 0 / 0 / 0 | 0 / 0 |
| `score.halfTime.away` | 144 | NoneType:126, int:18 | 0 / 126 / 0 | 0 / 0 |
| `score.halfTime.home` | 144 | NoneType:126, int:18 | 0 / 126 / 0 | 0 / 0 |
| `score.winner` | 144 | NoneType:126, str:18 | 0 / 126 / 0 | 0 / 0 |
| `season` | 144 | dict:144 | 0 / 0 / 0 | 0 / 0 |
| `season.currentMatchday` | 144 | int:144 | 0 / 0 / 0 | 0 / 0 |
| `season.endDate` | 144 | str:144 | 0 / 0 / 0 | 0 / 0 |
| `season.id` | 144 | int:144 | 0 / 0 / 0 | 0 / 0 |
| `season.startDate` | 144 | str:144 | 0 / 0 / 0 | 0 / 0 |
| `season.winner` | 144 | NoneType:144 | 0 / 144 / 0 | 0 / 0 |
| `stage` | 144 | str:144 | 0 / 0 / 0 | 0 / 0 |
| `status` | 144 | str:144 | 0 / 0 / 0 | 0 / 0 |
| `utcDate` | 144 | str:144 | 0 / 0 / 0 | 0 / 0 |

### org_CL_teams — 36 rows; 5 top-level columns
Raw file: `raw/football_data_org/CL/attempt_01/matches.json`.

| Field/path | Population | Observed types:count | Absent / null / blank | Empty list / object |
| --- | ---: | --- | --- | --- |
| `crest` | 36 | str:36 | 0 / 0 / 0 | 0 / 0 |
| `id` | 36 | int:36 | 0 / 0 / 0 | 0 / 0 |
| `name` | 36 | str:36 | 0 / 0 / 0 | 0 / 0 |
| `shortName` | 36 | str:36 | 0 / 0 / 0 | 0 / 0 |
| `tla` | 36 | str:36 | 0 / 0 / 0 | 0 / 0 |

### org_PL — 380 rows; 15 top-level columns
Raw file: `raw/football_data_org/PL/attempt_01/matches.json`.

| Field/path | Population | Observed types:count | Absent / null / blank | Empty list / object |
| --- | ---: | --- | --- | --- |
| `area` | 380 | dict:380 | 0 / 0 / 0 | 0 / 0 |
| `area.code` | 380 | str:380 | 0 / 0 / 0 | 0 / 0 |
| `area.flag` | 380 | str:380 | 0 / 0 / 0 | 0 / 0 |
| `area.id` | 380 | int:380 | 0 / 0 / 0 | 0 / 0 |
| `area.name` | 380 | str:380 | 0 / 0 / 0 | 0 / 0 |
| `awayTeam` | 380 | dict:380 | 0 / 0 / 0 | 0 / 0 |
| `awayTeam.crest` | 380 | str:380 | 0 / 0 / 0 | 0 / 0 |
| `awayTeam.id` | 380 | int:380 | 0 / 0 / 0 | 0 / 0 |
| `awayTeam.name` | 380 | str:380 | 0 / 0 / 0 | 0 / 0 |
| `awayTeam.shortName` | 380 | str:380 | 0 / 0 / 0 | 0 / 0 |
| `awayTeam.tla` | 380 | str:380 | 0 / 0 / 0 | 0 / 0 |
| `competition` | 380 | dict:380 | 0 / 0 / 0 | 0 / 0 |
| `competition.code` | 380 | str:380 | 0 / 0 / 0 | 0 / 0 |
| `competition.emblem` | 380 | str:380 | 0 / 0 / 0 | 0 / 0 |
| `competition.id` | 380 | int:380 | 0 / 0 / 0 | 0 / 0 |
| `competition.name` | 380 | str:380 | 0 / 0 / 0 | 0 / 0 |
| `competition.type` | 380 | str:380 | 0 / 0 / 0 | 0 / 0 |
| `group` | 380 | NoneType:380 | 0 / 380 / 0 | 0 / 0 |
| `homeTeam` | 380 | dict:380 | 0 / 0 / 0 | 0 / 0 |
| `homeTeam.crest` | 380 | str:380 | 0 / 0 / 0 | 0 / 0 |
| `homeTeam.id` | 380 | int:380 | 0 / 0 / 0 | 0 / 0 |
| `homeTeam.name` | 380 | str:380 | 0 / 0 / 0 | 0 / 0 |
| `homeTeam.shortName` | 380 | str:380 | 0 / 0 / 0 | 0 / 0 |
| `homeTeam.tla` | 380 | str:380 | 0 / 0 / 0 | 0 / 0 |
| `id` | 380 | int:380 | 0 / 0 / 0 | 0 / 0 |
| `lastUpdated` | 380 | str:380 | 0 / 0 / 0 | 0 / 0 |
| `matchday` | 380 | int:380 | 0 / 0 / 0 | 0 / 0 |
| `odds` | 380 | dict:380 | 0 / 0 / 0 | 0 / 0 |
| `odds.msg` | 380 | str:380 | 0 / 0 / 0 | 0 / 0 |
| `referees` | 380 | list:380 | 0 / 0 / 0 | 341 / 0 |
| `referees[].id` | 39 | int:39 | 0 / 0 / 0 | 0 / 0 |
| `referees[].name` | 39 | str:39 | 0 / 0 / 0 | 0 / 0 |
| `referees[].nationality` | 39 | str:39 | 0 / 0 / 0 | 0 / 0 |
| `referees[].type` | 39 | str:39 | 0 / 0 / 0 | 0 / 0 |
| `score` | 380 | dict:380 | 0 / 0 / 0 | 0 / 0 |
| `score.duration` | 380 | str:380 | 0 / 0 / 0 | 0 / 0 |
| `score.fullTime` | 380 | dict:380 | 0 / 0 / 0 | 0 / 0 |
| `score.fullTime.away` | 380 | NoneType:341, int:39 | 0 / 341 / 0 | 0 / 0 |
| `score.fullTime.home` | 380 | NoneType:341, int:39 | 0 / 341 / 0 | 0 / 0 |
| `score.halfTime` | 380 | dict:380 | 0 / 0 / 0 | 0 / 0 |
| `score.halfTime.away` | 380 | NoneType:342, int:38 | 0 / 342 / 0 | 0 / 0 |
| `score.halfTime.home` | 380 | NoneType:342, int:38 | 0 / 342 / 0 | 0 / 0 |
| `score.winner` | 380 | NoneType:341, str:39 | 0 / 341 / 0 | 0 / 0 |
| `season` | 380 | dict:380 | 0 / 0 / 0 | 0 / 0 |
| `season.currentMatchday` | 380 | int:380 | 0 / 0 / 0 | 0 / 0 |
| `season.endDate` | 380 | str:380 | 0 / 0 / 0 | 0 / 0 |
| `season.id` | 380 | int:380 | 0 / 0 / 0 | 0 / 0 |
| `season.startDate` | 380 | str:380 | 0 / 0 / 0 | 0 / 0 |
| `season.winner` | 380 | NoneType:380 | 0 / 380 / 0 | 0 / 0 |
| `stage` | 380 | str:380 | 0 / 0 / 0 | 0 / 0 |
| `status` | 380 | str:380 | 0 / 0 / 0 | 0 / 0 |
| `utcDate` | 380 | str:380 | 0 / 0 / 0 | 0 / 0 |

### org_PL_teams — 20 rows; 5 top-level columns
Raw file: `raw/football_data_org/PL/attempt_01/matches.json`.

| Field/path | Population | Observed types:count | Absent / null / blank | Empty list / object |
| --- | ---: | --- | --- | --- |
| `crest` | 20 | str:20 | 0 / 0 / 0 | 0 / 0 |
| `id` | 20 | int:20 | 0 / 0 / 0 | 0 / 0 |
| `name` | 20 | str:20 | 0 / 0 / 0 | 0 / 0 |
| `shortName` | 20 | str:20 | 0 / 0 / 0 | 0 / 0 |
| `tla` | 20 | str:20 | 0 / 0 / 0 | 0 / 0 |

## Appendix B. All observed FPL deadlines

| GW | Deadline UTC | Finished / data checked |
| ---: | --- | --- |
| 1 | `2026-08-21T17:30:00Z` | True / True |
| 2 | `2026-08-28T17:30:00Z` | True / True |
| 3 | `2026-09-04T17:30:00Z` | True / True |
| 4 | `2026-09-12T12:30:00Z` | False / False |
| 5 | `2026-09-18T17:30:00Z` | False / False |
| 6 | `2026-10-10T10:00:00Z` | False / False |
| 7 | `2026-10-17T10:00:00Z` | False / False |
| 8 | `2026-10-23T17:30:00Z` | False / False |
| 9 | `2026-10-31T11:00:00Z` | False / False |
| 10 | `2026-11-07T13:30:00Z` | False / False |
| 11 | `2026-11-21T13:30:00Z` | False / False |
| 12 | `2026-11-28T13:30:00Z` | False / False |
| 13 | `2026-12-02T18:30:00Z` | False / False |
| 14 | `2026-12-05T13:30:00Z` | False / False |
| 15 | `2026-12-12T13:30:00Z` | False / False |
| 16 | `2026-12-19T13:30:00Z` | False / False |
| 17 | `2026-12-26T11:00:00Z` | False / False |
| 18 | `2026-12-29T18:00:00Z` | False / False |
| 19 | `2027-01-01T18:30:00Z` | False / False |
| 20 | `2027-01-05T18:00:00Z` | False / False |
| 21 | `2027-01-16T13:30:00Z` | False / False |
| 22 | `2027-01-23T13:30:00Z` | False / False |
| 23 | `2027-01-30T13:30:00Z` | False / False |
| 24 | `2027-02-06T13:30:00Z` | False / False |
| 25 | `2027-02-10T18:30:00Z` | False / False |
| 26 | `2027-02-20T13:30:00Z` | False / False |
| 27 | `2027-02-27T13:30:00Z` | False / False |
| 28 | `2027-03-03T18:30:00Z` | False / False |
| 29 | `2027-03-13T13:30:00Z` | False / False |
| 30 | `2027-03-20T13:30:00Z` | False / False |
| 31 | `2027-04-10T12:30:00Z` | False / False |
| 32 | `2027-04-17T12:30:00Z` | False / False |
| 33 | `2027-04-24T12:30:00Z` | False / False |
| 34 | `2027-05-01T12:30:00Z` | False / False |
| 35 | `2027-05-08T12:30:00Z` | False / False |
| 36 | `2027-05-15T12:30:00Z` | False / False |
| 37 | `2027-05-23T12:30:00Z` | False / False |
| 38 | `2027-05-30T13:30:00Z` | False / False |

## Appendix C. Literal identity inventories

These are source-local inventories and exact intersections, not a cross-provider mapping.

### FPL teams (Core ID/code/name/short name exactly agree)

| FPL id | FPL code | Name | Short name |
| ---: | ---: | --- | --- |
| 1 | 3 | Arsenal | ARS |
| 2 | 7 | Aston Villa | AVL |
| 3 | 91 | Bournemouth | BOU |
| 4 | 94 | Brentford | BRE |
| 5 | 36 | Brighton | BHA |
| 6 | 8 | Chelsea | CHE |
| 7 | 9 | Coventry City | COV |
| 8 | 31 | Crystal Palace | CRY |
| 9 | 11 | Everton | EVE |
| 10 | 54 | Fulham | FUL |
| 11 | 88 | Hull City | HUL |
| 12 | 40 | Ipswich Town | IPS |
| 13 | 2 | Leeds | LEE |
| 14 | 14 | Liverpool | LIV |
| 15 | 43 | Man City | MCI |
| 16 | 1 | Man Utd | MUN |
| 17 | 4 | Newcastle | NEW |
| 18 | 17 | Nott'm Forest | NFO |
| 19 | 6 | Spurs | TOT |
| 20 | 56 | Sunderland | SUN |

### Football-Data.co.uk E0 fixtures

| Date as received | Time as received | HomeTeam | AwayTeam |
| --- | --- | --- | --- |
| 12/09/2026 | 15:00 | Aston Villa | Nott'm Forest |
| 12/09/2026 | 15:00 | Bournemouth | Brentford |
| 12/09/2026 | 15:00 | Chelsea | Hull |
| 12/09/2026 | 15:00 | Crystal Palace | Ipswich |
| 12/09/2026 | 15:00 | Liverpool | Fulham |
| 12/09/2026 | 17:30 | Tottenham | Everton |
| 12/09/2026 | 20:00 | Sunderland | Arsenal |
| 13/09/2026 | 14:00 | Coventry | Brighton |
| 13/09/2026 | 16:30 | Man United | Man City |
| 14/09/2026 | 20:00 | Leeds | Newcastle |

### football-data.org PL team entities

| Provider id | Full name | Short name | TLA |
| ---: | --- | --- | --- |
| 57 | Arsenal FC | Arsenal | ARS |
| 58 | Aston Villa FC | Aston Villa | AVL |
| 61 | Chelsea FC | Chelsea | CHE |
| 62 | Everton FC | Everton | EVE |
| 63 | Fulham FC | Fulham | FUL |
| 64 | Liverpool FC | Liverpool | LIV |
| 65 | Manchester City FC | Man City | MCI |
| 66 | Manchester United FC | Man United | MUN |
| 67 | Newcastle United FC | Newcastle | NEW |
| 71 | Sunderland AFC | Sunderland | SUN |
| 73 | Tottenham Hotspur FC | Tottenham | TOT |
| 322 | Hull City AFC | Hull City | HUL |
| 341 | Leeds United FC | Leeds United | LEE |
| 349 | Ipswich Town FC | Ipswich Town | IPS |
| 351 | Nottingham Forest FC | Nottingham | NOT |
| 354 | Crystal Palace FC | Crystal Palace | CRY |
| 397 | Brighton & Hove Albion FC | Brighton Hove | BHA |
| 402 | Brentford FC | Brentford | BRE |
| 1044 | AFC Bournemouth | Bournemouth | BOU |
| 1076 | Coventry City FC | Coventry City | COV |

### football-data.org CL team entities

| Provider id | Full name | Short name | TLA |
| ---: | --- | --- | --- |
| 4 | Borussia Dortmund | Dortmund | BVB |
| 5 | FC Bayern München | Bayern | FCB |
| 10 | VfB Stuttgart | Stuttgart | VFB |
| 57 | Arsenal FC | Arsenal | ARS |
| 58 | Aston Villa FC | Aston Villa | AVL |
| 64 | Liverpool FC | Liverpool | LIV |
| 65 | Manchester City FC | Man City | MCI |
| 66 | Manchester United FC | Man United | MUN |
| 78 | Club Atlético de Madrid | Atleti | ATL |
| 81 | FC Barcelona | Barça | FCB |
| 86 | Real Madrid CF | Real Madrid | RMA |
| 90 | Real Betis Balompié | Real Betis | BET |
| 94 | Villarreal CF | Villarreal | VIL |
| 100 | AS Roma | Roma | ROM |
| 108 | FC Internazionale Milano | Inter | INT |
| 113 | SSC Napoli | Napoli | NAP |
| 498 | Sporting Clube de Portugal | Sporting CP | SPO |
| 503 | FC Porto | Porto | FCP |
| 521 | Lille OSC | Lille | LIL |
| 524 | Paris Saint-Germain FC | PSG | PSG |
| 546 | Racing Club de Lens | RC Lens | RCL |
| 610 | Galatasaray SK | Galatasaray | GAL |
| 613 | Fenerbahçe SK | Fenerbahçe | FEN |
| 674 | PSV | PSV | PSV |
| 675 | Feyenoord Rotterdam | Feyenoord | FEY |
| 721 | RB Leipzig | RB Leipzig | RBL |
| 851 | Club Brugge KV | Club Brugge | BRU |
| 930 | SK Slavia Praha | Slavia Praha | SLP |
| 1887 | FK Shakhtar Donetsk | Shaktar | SHD |
| 1899 | PAE AEK | PAE AEK | AEK |
| 2016 | LASK Linz | LASK | LIN |
| 5720 | Viking FK | Viking | VIK |
| 5721 | FK Bodø/Glimt | Bodø/Glimt | FK |
| 7397 | Como 1907 | Como 1907 | COM |
| 7509 | ŠK Slovan Bratislava | Sl. Bratislava | SBA |
| 10233 | Sabah FK | Sabah FK | SAB |

### Exact name/code intersections

`fpl_team_odds_exact_name`: `Arsenal`, `Aston Villa`, `Bournemouth`, `Brentford`, `Brighton`, `Chelsea`, `Crystal Palace`, `Everton`, `Fulham`, `Leeds`, `Liverpool`, `Man City`, `Newcastle`, `Nott'm Forest`, `Sunderland`.

`fpl_team_org_PL_shortName`: `Arsenal`, `Aston Villa`, `Bournemouth`, `Brentford`, `Chelsea`, `Coventry City`, `Crystal Palace`, `Everton`, `Fulham`, `Hull City`, `Ipswich Town`, `Liverpool`, `Man City`, `Newcastle`, `Sunderland`.

`fpl_team_org_PL_tla`: `ARS`, `AVL`, `BHA`, `BOU`, `BRE`, `CHE`, `COV`, `CRY`, `EVE`, `FUL`, `HUL`, `IPS`, `LEE`, `LIV`, `MCI`, `MUN`, `NEW`, `SUN`, `TOT`.

`fpl_team_org_CL_shortName`: `Arsenal`, `Aston Villa`, `Liverpool`, `Man City`.

`fpl_team_org_CL_tla`: `ARS`, `AVL`, `LIV`, `MCI`, `MUN`.

