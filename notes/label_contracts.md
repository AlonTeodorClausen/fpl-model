# Step 2B — identity, time and player-fixture label contracts

Status: sample validation for review, **not full ingestion or canonicalisation**. Season: `2026-2027`. No production adapters, multi-source runner, datasets, features, forecasting, optimisation or backtesting were changed.

All observations below are as captured on September 13–14, 2026. Resuming the audit on September 21 did not refresh them; “current GW” refers to the captured source state.

## Evidence and reproducibility

The Step 1 / Step 2A baseline remains:

`data/raw/2026-09-13_154638516264Z_fe2dc3c782d146b2b6a22bdaafb905c5`

The separate, immutable Step 2B sample is:

`data/raw/2026-09-14_144125953137Z_8c9e6040dee04f6dbdd83e7ae747929d`

All 20 responses were HTTP 200, stored byte-for-byte before validation, with request/retrieval/availability timestamps, URL, content type, size and SHA-256. Official responses were `application/json`; pinned GitHub CSV responses were `text/plain; charset=utf-8`. Retrieval spans `2026-09-14T14:41:26.089100+00:00` through `2026-09-14T14:41:27.799515+00:00`. Every sample file records `available_at = retrieved_at`; none has a verified `source_published_at`. The two snapshots' manifests and all raw hashes are verified by the offline audit. Raw snapshots remain gitignored.

Machine-readable results: `artifacts/audits/step2b_8c9e6040dee04f6dbdd83e7ae747929d/coverage.json`. This includes exact raw paths and manifest entries, field-by-field types/missingness, sample identities, candidate fixture associations, label states, every comparison and all 53 earlier minute differences. Companion tables are `discrepancies.csv`, `missing_player_fixtures.csv` and `fixture_crosswalk_candidates.csv`. The last is a diagnostic candidate table, not an approved mapping.

The experiment script `scripts/capture_label_sample.py` fixes 12 element IDs and six Core CSV paths; it also captures fresh official bootstrap/fixtures so that histories have contemporary identity and completion context. It does not enumerate all players or extend any production adapter. One writer owns this separate capture; the experiment alone finalizes it. Requests use connect/read timeout `(10, 30)` seconds, no redirects, and no credentials. Required FPL probe errors stop immediately, consistently with SnapshotWriter's retained-required-failure policy. Optional Core transport/5xx errors allow at most three attempts with 1s/2s waits; 429 stops rather than disregarding a server wait requirement. Attempt bodies/failures remain immutable. These are experiment policies, not changes to approved adapter behaviour.

Reproduce the **offline analysis**, without new requests:

```bash
.venv/bin/python scripts/audit_label_sample.py \
  data/raw/2026-09-13_154638516264Z_fe2dc3c782d146b2b6a22bdaafb905c5 \
  data/raw/2026-09-14_144125953137Z_8c9e6040dee04f6dbdd83e7ae747929d \
  --output /tmp/step2b-new-audit-directory
.venv/bin/python -m pytest -q
```

Use a new output directory; the audit refuses overwriting its reports or writing inside raw storage. A repeat live capture creates a different observation version and is not needed to reproduce this report.

## A. Explicit contracts

### Identity

- Canonical PL player key: `(season, official FPL element ID)`. Bootstrap `elements[].id` and element-summary `history[].element` name that identity. FPL `code` is retained as corroborating metadata, not substituted for `element`.
- Canonical PL team key: `(season, official FPL team ID)`. FPL `team.code` is a distinct identifier namespace. Never treat code 3 as team ID 3.
- Canonical fixture reference: `(season, official FPL fixture ID)`. A GW is not a fixture ID. Preserve both fixture and observed GW assignment.
- Step 2A's exact Core identity evidence is rechecked: all 657 `player_id`/`player_code`/names/team codes and all 20 team `id`/`code`/names match the baseline. Sample official player codes still agree in the new context. Unknown/ambiguous IDs fail closed; no fuzzy matching or name-derived player identities.
- Core `playermatchstats.player_id` references these verified players. All IDs in the sampled Core files belong to the 657-player baseline. Its match `home_team`/`away_team` are **FPL team codes**, often encoded as decimal strings (`3.0`), not FPL team IDs. Lossless integral parsing plus the verified code→ID table is necessary. Pinned cleaner documentation explicitly confirms this namespace.
- All 680 PL player-match rows across the two sampled GWs have a current baseline player team code belonging to the indicated match. This is a consistency check, not proof of historical membership after transfers. In official history, own-team context is derived from the linked fixture and `was_home`; current bootstrap team alone cannot establish an earlier team.
- Secondary-source aliases require a reviewable table with source namespace/ID or literal name, season or validity interval, official team ID, evidence, and review status. Unknown or conflicting aliases stay unresolved. No secondary alias table or guessed mapping is introduced here.

### Time

| Field | Meaning / policy |
|---|---|
| `event_time` | Time of the underlying event, e.g. fixture kickoff. May be null for an unscheduled fixture. Does not establish knowledge availability. |
| `source_published_at` | Publication time only when the source's semantics and evidence establish publication of this exact version. Unknown for these payloads. |
| `retrieved_at` | UTC, timezone-aware completion time when this response body was obtained. |
| `available_at` | Earliest permitted use of this captured version. Here it is retrieval time; a derived validation decision cannot predate any raw context it uses. |
| `forecast_origin_at` | Explicit UTC forecast cutoff, normally the relevant FPL deadline from the appropriate historical observation. Inputs require `available_at < forecast_origin_at`. Equality does not satisfy “before deadline.” |

`ObservationTime` enforces aware timestamps, normalises offsets to UTC, requires publication evidence when supplied, and forbids backdating this captured version before retrieval. It does not implement an archive-based availability exception. Earlier independently documented versions would require a separately reviewed policy. No historical eligibility is inferred from Git commit time, file path/GW, API `lastUpdated`, `modified`, match date, or a present-day request for an old season.

The pinned exporter interprets kickoff strings with `utc=True` when inferring missing gameweeks; its CSV still has naive timestamps. This supports the diagnostic UTC interpretation, but does not establish the original database timezone, timestamp stability, or historical availability. Never silently accept arbitrary naive event timestamps in the general contract.

Capture is not atomic across endpoints. Availability of a validated player-fixture label is at least the maximum of history, fixtures and bootstrap availability used for that decision. Here histories arrived after both context files. A later response can still reflect a different upstream refresh cycle; version disagreements remain evidence, not values to average.

### Label completeness

Labels have key `(season, element, fixture)`, observation version, provenance links and explicit state:

| State | Rule |
|---|---|
| `unusable` | Missing player-fixture row; invalid/missing identity, opponent, kickoff or GW relationship; invalid minutes/points; not-started or unscheduled fixture; duplicate/ambiguous key (rejected by the audit). |
| `provisional` | Structurally valid row for a started fixture, but official fixture `finished`, event `finished` and event `data_checked` are not all true. |
| `final` | Valid identity/context and minutes/points, started fixture, official fixture `finished=true`, event `finished=true`, event `data_checked=true`. This means final **under the observed contract version**, not immune to later official corrections. |

`label_state` checks the core minutes/points label. Optional fields need their own presence/type/definition checks; a final minutes/points label does not manufacture absent xG or defensive statistics. Exact sampled schema/missingness is reported separately. `finished_provisional=true`, Core `finished=true`, a populated row, `modified=false`, or an available score is insufficient by itself.

An explicit zero-minute, zero-start row is an observed non-appearance label; an absent row is unknown. Negative FPL points remain legitimate. No roster expansion or missing-to-zero filling occurs. This conservative policy can delay otherwise settled individual-match labels until the whole GW is checked.

For a DGW, retain two distinct fixture rows for the same player/GW, each with its own identity and completion state. A future GW total may be assembled only after its expected fixture set and finality are established; no such aggregation is implemented. A postponed fixture with null kickoff/GW cannot yield a final played label; preserve earlier scheduling observations, then assess the rescheduled fixture's current observed event separately. Do not rewrite old GW membership or infer a zero for a postponed/blank fixture. Neither a DGW nor postponement occurs in this small real sample; these cases are covered by synthetic contract tests.

## B. Official FPL player-fixture sample

Twelve endpoints `/api/element-summary/{element_id}/` were fetched: IDs **1, 2, 4, 5, 12, 26, 109, 115, 124, 126, 426, 439**. This is a purposive validation sample, not a random or league-representative estimate.

| Team | Players (ID; position) | Observed representation |
|---|---|---|
| Arsenal | Raya 1 GK; Arrizabalaga 2 GK; Gabriel 4 DEF; J.Timber 5 DEF; Saka 12 MID; Havertz 26 FWD | Regular starters, unused goalkeeper, Timber three DNP rows then a 45-minute substitute appearance. |
| Brighton | Verbruggen 109 GK; De Cuyper 115 DEF; Groß 124 MID; O'Riley 126 MID | Starters and O'Riley three DNP rows then six minutes; four of the earlier 53 discrepancies. |
| Man Utd | B.Fernandes 426 MID; Šeško 439 FWD | Starter from the previously live match; substitute with 23/10/20/23 minutes and zero starts. |

Exact history paths are `raw/fpl_api/attempt_01/element_summary/{id}.json`; context paths are `raw/fpl_api/attempt_01/bootstrap_static.json` and `raw/fpl_api/attempt_01/fixtures.json`, relative to the sample snapshot. Appendix tables give individual retrieval timestamps.

Each response has top-level `fixtures`, `history`, `history_past`. Only `history` is audited as player-fixture labels: **four rows per player, 48 rows total, unique (element, fixture), GW1–4**, covering 12 distinct official fixtures. `fixtures` is future schedule context; `history_past` contains season aggregates, not match labels. Neither is merged into `history`.

The 41 history fields are fully enumerated with observed types in Appendix B; **no absent, null or empty values** occur in those 48 rows. This is sample evidence, not a promise for unplayed/future rows or future schema revisions.

| Group | Fields actually present | Interpretation |
|---|---|---|
| Identity/context | `element`, `fixture`, `round`, `opponent_team`, `was_home`, `kickoff_time`, `team_h_score`, `team_a_score` | Element/fixture/GW/opponent integers; home bool; UTC kickoff string; integer scores. Own team requires the fixture reference. |
| Participation | `minutes`, `starts` | Integer fixture values. Explicit DNPs and substitute starts=0 are present. |
| FPL scoring | `total_points`, `goals_scored`, `assists`, `clean_sheets`, `goals_conceded`, `own_goals`, `penalties_saved`, `penalties_missed`, `yellow_cards`, `red_cards`, `saves`, `bonus`, `bps` | Fixture-level scoring/label candidates; no cumulative differencing needed. |
| Defensive | `clearances_blocks_interceptions`, `recoveries`, `tackles`, `defensive_contribution` | Integer fixture values; do not replace them with similarly named Core metrics without definitions. |
| Expected statistics | `expected_goals`, `expected_assists`, `expected_goal_involvements`, `expected_goals_conceded` | Decimal **strings**, fixture-level, unlike bootstrap's cumulative season aggregates. |
| Other | `influence`, `creativity`, `threat`, `ict_index`, `value`, `selected`, `transfers_balance`, `transfers_in`, `transfers_out`, `modified` | Preserve as observed context. Price/ownership/transfer timing and `modified` semantics are not independently verified; no historical pre-deadline use. |

The 36 GW1–3 rows satisfy the conservative finality contract. All 12 GW4 rows remain provisional: GW4 is current, unfinished and unchecked, official fixture `finished=false` even for matches with `finished_provisional=true`. No live label or benchmark is treated as final merely because minutes now show 90.

**Conclusion:** official history is a promising primary source of FPL player-fixture labels, including starts and defensive contributions, with fixture identity and observed DNPs. The sample does not establish completeness for all 657 players, DGWs, transfers, postponed fixtures, score revisions or previous seasons.

## C. Pinned Core match/player-match sample

Every Core request uses the original commit **`907f666f2dc6796d417e49287fd31f88263f1d67`**, verified against the first snapshot manifest. URL prefix is `https://raw.githubusercontent.com/olbauday/FPL-Core-Insights/<sha>/`; directory spaces are URL-encoded. No `main` or newer revision was used.

Exact raw prefix: `raw/fpl_core/attempt_01/<sha>/`. The six requested suffixes and counts are:

| Upstream path under `data/2026-2027/` | Rows | Columns | Granularity / coverage |
|---|---:|---:|---|
| `By Gameweek/GW3/matches.csv` | 10 | 116 | One match; 10 PL, Sept 4–6; all Core finished. |
| `By Gameweek/GW3/playermatchstats.csv` | 400 | 64 | Unique player/match pairs; 40 per PL match, 400 distinct players. |
| `By Gameweek/GW4/matches.csv` | 20 | 116 | 10 PL + 5 Champions League + 5 EFL Cup; Sept 8–14; 17 Core finished, three not finished. |
| `By Gameweek/GW4/playermatchstats.csv` | 518 | 64 | 280 PL + 106 CL + 132 EFL Cup player/match rows; 17 matches, 381 distinct players. |
| `By Tournament/Champions League/GW4/matches.csv` | 5 | 116 | Five CL matches, Sept 8–10, all Core finished. |
| `By Tournament/Champions League/GW4/playermatchstats.csv` | 106 | 64 | Five CL matches, 20–22 recorded player rows per match. |

All **106 CL player rows are identical repeats** of rows already in the GW4 export. The CL match rows likewise reference the five GW4 CL match IDs; do not concatenate tournament and GW exports as independent data. `gameweek` groups European/cup matches into FPL-calendar windows; it is not necessarily their actual competition round. Upstream code can infer missing gameweeks from kickoff/deadlines and derives `tournament` from match slugs.

`matches.match_id` is a string slug (not an FPL fixture ID). `fotmob_id` is a separate numeric-looking ID; `match_url` is another provider reference. `kickoff_time` is an ISO-like string **without timezone**; match scores, `finished`, processing flags, home/away statistics and `tournament` are present. There is no official FPL fixture-ID column. Match slug dates can disagree with kickoff dates (e.g. Napoli–Arsenal slug ends September 8, kickoff September 9); do not parse event time from identifiers.

Non-PL opponents often have blank team references: GW4 has four missing home and four missing away codes; CL has three missing home and two missing away codes. This is FPL-club-oriented coverage, not a verified full European team/player universe. All sampled player IDs map to the FPL universe; absence of opponent players/IDs prevents claims of complete match rosters.

`playermatchstats` is genuinely player-match-level: unique `(player_id, match_id)`, including players with observed `minutes_played=0`. It has no direct team, kickoff, competition or FPL round field; those require the linked match. It has no explicit `starts`, FPL total points, bonus/BPS, cards or clean-sheet field. `start_min`/`finish_min` are **not a safe starts proxy**: pinned upstream documentation warns that those timelines remain unreliable.

| Player field | GW3 blanks / 400 | GW4 blanks / 518 | CL GW4 blanks / 106 |
|---|---:|---:|---:|
| `minutes_played` | 0 | 0 | 0 |
| `goals`, `assists` (each) | 113 | 141 | 32 |
| `xg`, `total_shots`, `shots_on_target` (each) | 254 | 316 | 60 |
| `xa` | 196 | 224 | 45 |
| `chances_created` | 112 | 140 | 31 |
| `interceptions`, `recoveries`, `clearances`, `tackles_won` (each) | 93 | 115 | 27 |
| `blocks` | 113 | 141 | 32 |
| `start_min`, `finish_min` (each) | 93 | 115 | 27 |
| `tackles`, `defensive_contributions` (each) | 400 | 518 | 106 |

CSV values remain strings; numeric lexical forms mix integer and decimal strings, booleans use text, missing cells are empty strings. Full 64/116-column lists, lexical types and missingness are in Appendix C / coverage.json. Do not impute blank xG/goals/assists as zero. `tackles_won` cannot substitute for FPL `tackles`; empty Core `defensive_contributions` does not establish zero actions. Team Elo and multiple tracking fields are also entirely blank in the match sample.

Pinned exporter/cleaner evidence was inspected separately and preserved byte-for-byte under the audit's `evidence/` directory with URLs, pin, retrieval times and hashes in `index.json`. The exporter runs a sanitizer before writing player-match CSVs: it removes known phantom rows, fills some null non-appearance minutes with zero and adjusts some timelines. Those are **upstream transformations**, not changes performed by this project. Its comments still warn about unresolved timelines. Thus “exact raw bytes” means the exact published CSV, not an untouched provider database or independently verified participation record. [Pinned exporter](https://github.com/olbauday/FPL-Core-Insights/blob/907f666f2dc6796d417e49287fd31f88263f1d67/scripts/export_data.py); [pinned cleaner](https://github.com/olbauday/FPL-Core-Insights/blob/907f666f2dc6796d417e49287fd31f88263f1d67/scripts/clean_playermatchstats.py).

## D. Cross-source sample comparison

Comparison window: GW3–4 only, 24 official sample player-fixtures. GW1–2 Core CSVs were deliberately not downloaded. **17 pairs** have both an exact verified player ID and a unique candidate fixture association: 11 in final GW3 and six in provisional GW4. Numeric comparison uses exact decimal equality, no rounding tolerance, conversion of blanks to zero, averaging or replacement.

| Field | Identical | Missing in Core | Unexplained difference |
|---|---:|---:|---:|
| Minutes | 15 | 0 | 2 |
| Starts | 0 | 17 | 0 |
| Goals | 11 | 6 | 0 |
| Assists | 11 | 6 | 0 |
| xG | 8 | 8 | 1 |
| xA | 12 | 5 | 0 |
| Saves / goals conceded (each) | 3 | 14 | 0 |
| Recoveries | 14 | 3 | 0 |
| Tackles / defensive contribution / clean sheets / total points (each) | 0 | 17 | 0 |

“Missing in Core” includes absent columns and empty cells, separately visible as null versus empty string in JSON. CSV blank cells alone cannot convey that distinction; use coverage.json. Numerical agreement is not proof of identical statistic definitions. Goals/assists agree where both values exist; the sample cannot establish equivalence of FPL assist rules and Core's provider definitions.

Observed non-equal values:

| Player | FPL fixture / Core match | Field | FPL | Core | Classification |
|---|---|---|---:|---:|---|
| De Cuyper 115 | 23 / `26-27-prem-brighton-hove-albion-vs-leeds-united` | minutes | 76 | 77.0 | Unexplained; possible minute accounting/rounding, not verified. |
| Havertz 26 | 29 / `26-27-prem-arsenal-vs-chelsea` | minutes | 77 | 78.0 | Unexplained; possible minute accounting/rounding, not verified. |
| Saka 12 | 29 / `26-27-prem-arsenal-vs-chelsea` | xG | 0.23 | 0.22 | Unexplained; provider/version/rounding cause not established. |

All three are in **completed, checked GW3**. They cannot simply be dismissed as current-GW provisional totals. No observed numeric difference is promoted to “definition difference” without evidence.

Seven official sample player-fixtures lack a Core player row:

- J.Timber, GW3 fixture 29: official explicit DNP row; absent Core row. Classification: missing in one source. A missing Core row cannot itself prove DNP.
- Brighton IDs 109/115/124/126, GW4 fixture 38, and Man Utd 426/439, fixture 39: Core match rows exist but remain `finished=False` at the pin; their player rows are absent. Classification: missing in one source, with source-version/provisional timing evidence.

Seven GW4 PL match completion flags disagree (`Core finished=True`, official `finished=False`); the separate `finality_differences` table classifies these as **provisional/finality issues**, not contradictory outcomes. Core processing flags are not a completion guarantee: GW3 has player-stats processing flags false despite all 400 rows existing. A parser must not infer official label finality from those flags.

The discrepancy categories supported by the report are identical, missing in one source, provisional/finality issue and unexplained. “Definition difference” remains a possible future classification when confirmed; none of the observed numeric mismatches has enough evidence for that assignment.

### The original 53-player aggregate minutes discrepancy

Recomputed on the **original** Step 1 snapshot, not replaced with today's bootstrap. For all 53 players, Core GW3 and GW4 cumulative minutes are unchanged. All discrepancies are confined to:

| Team | Players | Old FPL minus pinned Core | Evidence |
|---|---:|---|---|
| Brighton | 16 | 6–90 minutes | Coventry–Brighton, fixture 38, had finished provisionally by FPL retrieval but is unfinished in pinned Core. |
| Coventry City | 15 | 6–90 minutes | Same fixture. |
| Man City | 11 | Exactly +13 each | Manchester derby, fixture 39, was in progress during original FPL retrieval; absent from pinned Core player stats. |
| Man Utd | 11 | Exactly +13 each | Same fixture. |

The original official fixtures response reports 90 match-progress minutes for fixture 38 and **11** for fixture 39, while bootstrap's 22 derby participants have +13. These differing progress observations are consistent with non-atomic endpoint/cache refreshes; do not assert the feeds captured one exact game clock.

For sampled Brighton players Verbruggen, De Cuyper, Groß and O'Riley, new official history GW1–3 sums equal Core's earlier cumulative minutes (270, 243, 270, 0). Their official GW4 minutes (90, 90, 90, 6) exactly explain the original aggregate deltas. B.Fernandes also has prior-history sum 270, agreeing with Core; the original FPL total was 283 mid-match, while the newly retrieved GW4 history records 90. This supports an in-progress version explanation for his original +13.

**Assessment:** timing/version coverage strongly explains the 53-player pattern, and four full-match deltas are directly verified with sampled histories. All 53 have team-level timing evidence; the other 48 were not individually validated through element-summary, so a complete per-player reconciliation is not claimed. No broader request was made to force that conclusion. The two completed-GW minute differences above are a separate provider-level issue; they do not explain a 53-player cluster concentrated in two later matches. Core cumulative playerstats and Core player-match minutes must not be assumed internally interchangeable either.

## E. Fixture crosswalk viability

The audit tests `(verified home FPL team ID, verified away FPL team ID, exact kickoff UTC)` against Core team codes converted via the verified code table, interpreting Core's naive values as UTC **only for this diagnostic**. It never compares or fuzzily normalises team names/slugs. The pinned exporter's `pd.to_datetime(kickoff, utc=True)` and all 20 exact observed kickoff equalities support this interpretation; neither is a universal historical timezone warranty.

Result: **20/20 PL match candidates**, 10 GW3 and 10 GW4, each unique against the full fresh official 380-fixture list; **zero collisions, invalid keys or unmatched PL rows**. Sample player identity and inferred fixture sides agree for the 17 paired rows. Non-PL matches are excluded from the PL crosswalk; blank European/cup opponent IDs remain unresolved.

This is sufficiently promising for a later **reviewed, season/source-scoped deterministic rule**, with explicit timezone policy, unique team-code mappings and collision checks. It is not approved for unrestricted canonicalisation yet. Rescheduled kickoff versions, null dates, transfers, repeated team pairings and wrong/changed IDs must fail closed or remain unresolved. The candidate rule never accepts multiple candidates and does not fall back to names or nearest kickoff. Official fixture IDs must not be derived from Core match slugs.

## F. Historical usability and next step

Official fixture-level history is the preferred candidate for FPL targets; Core adds candidate European/cup participation and richer event statistics, with missingness and definition risks. Current schedules, identity/status context and finalized prior-match observations can inform forecasts **after their captured availability**. GW4 label rows are provisional; these raw files are observation versions, not final training rows.

Historical outcomes retrieved later can be used as evaluation targets after finality/version checks, with the target-observation time kept separate from the historical forecast origin. They do not make contemporaneous inputs available retroactively. Even when a completed fixture's result precedes a later historical deadline, these present-day files do not prove which version/statistics were available then.

Neither snapshot establishes leakage-safe pre-deadline inputs for already elapsed GW1–4. Commit pinning provides reproducibility of bytes, not proof of prior public availability. Current player metadata, prices, ownership, cumulative totals, cup stats, revised xG and final scores may reveal information unavailable at historical origins. `modified`, processing flags and inferred GW folders are not publication timestamps. Raw captures of current historical-looking files are not historical snapshot backfills.

**Recommendation for Step 2C, subject to review:** implement a bounded official-label ingestion and validation stage first, retaining source versions, fixture identity and conservative completion states. Before broad expansion, validate another completed-fixture sample including DGW/postponement/transfer cases where available; review Core's UTC interpretation and the two minute discrepancies. Keep Core supplementary and source-specific until definitions/coverage are resolved. Plan prospective pre-deadline capture separately from later final-label capture. Do not yet join all sources into a canonical dataset or manufacture historical availability.

## Validation

Offline tests cover aware times and strict cutoff, publication evidence/backdating rejection, exact integral identifiers, DNP versus absence, finality flags, inconsistent identities/context, postponed/DGW fixtures, bounded pinned capture, raw byte/hash preservation, failure bodies, caller finalization, retry limits, secret-safe failures, malformed CSV, duplicate/colliding fixture keys, no name fallback, deterministic/read-only analysis and protected report output.

Full offline command `.venv/bin/python -m pytest -q`: **426 passed, 5 deselected in 2.53s**. The five live tests were excluded; no network was used. Two independent real-snapshot audit runs produced identical bytes for all four generated report files. Snapshot integrity and pinned source-evidence hashes were reverified; the resumed audit fetched no replacement data.

## Appendix A — exact sample raw paths and observation times

All paths below are relative to the Step 2B sample snapshot. Every row has HTTP 200 and `available_at = retrieved_at`. Full SHA-256, byte size, request start, URL and pin are retained in coverage.json and the immutable manifest.

| Exact raw path | Retrieved / available at (UTC) | Bytes |
|---|---|---:|
| `raw/fpl_api/attempt_01/bootstrap_static.json` | `2026-09-14T14:41:26.089100+00:00` | 1753431 |
| `raw/fpl_api/attempt_01/fixtures.json` | `2026-09-14T14:41:26.116501+00:00` | 206822 |
| `raw/fpl_api/attempt_01/element_summary/1.json` | `2026-09-14T14:41:26.124867+00:00` | 14703 |
| `raw/fpl_api/attempt_01/element_summary/2.json` | `2026-09-14T14:41:26.149105+00:00` | 16375 |
| `raw/fpl_api/attempt_01/element_summary/4.json` | `2026-09-14T14:41:26.160359+00:00` | 15315 |
| `raw/fpl_api/attempt_01/element_summary/5.json` | `2026-09-14T14:41:26.167338+00:00` | 13472 |
| `raw/fpl_api/attempt_01/element_summary/12.json` | `2026-09-14T14:41:26.174610+00:00` | 16514 |
| `raw/fpl_api/attempt_01/element_summary/26.json` | `2026-09-14T14:41:26.181871+00:00` | 15310 |
| `raw/fpl_api/attempt_01/element_summary/109.json` | `2026-09-14T14:41:26.188613+00:00` | 13519 |
| `raw/fpl_api/attempt_01/element_summary/115.json` | `2026-09-14T14:41:26.194986+00:00` | 12346 |
| `raw/fpl_api/attempt_01/element_summary/124.json` | `2026-09-14T14:41:26.201535+00:00` | 17078 |
| `raw/fpl_api/attempt_01/element_summary/126.json` | `2026-09-14T14:41:26.210427+00:00` | 12884 |
| `raw/fpl_api/attempt_01/element_summary/426.json` | `2026-09-14T14:41:26.217707+00:00` | 15994 |
| `raw/fpl_api/attempt_01/element_summary/439.json` | `2026-09-14T14:41:26.224263+00:00` | 12362 |
| `raw/fpl_core/attempt_01/907f666f2dc6796d417e49287fd31f88263f1d67/data/2026-2027/By Gameweek/GW3/matches.csv` | `2026-09-14T14:41:26.570231+00:00` | 8115 |
| `raw/fpl_core/attempt_01/907f666f2dc6796d417e49287fd31f88263f1d67/data/2026-2027/By Gameweek/GW3/playermatchstats.csv` | `2026-09-14T14:41:26.880607+00:00` | 84113 |
| `raw/fpl_core/attempt_01/907f666f2dc6796d417e49287fd31f88263f1d67/data/2026-2027/By Gameweek/GW4/matches.csv` | `2026-09-14T14:41:27.130229+00:00` | 13179 |
| `raw/fpl_core/attempt_01/907f666f2dc6796d417e49287fd31f88263f1d67/data/2026-2027/By Gameweek/GW4/playermatchstats.csv` | `2026-09-14T14:41:27.374091+00:00` | 109983 |
| `raw/fpl_core/attempt_01/907f666f2dc6796d417e49287fd31f88263f1d67/data/2026-2027/By Tournament/Champions League/GW4/matches.csv` | `2026-09-14T14:41:27.599850+00:00` | 5270 |
| `raw/fpl_core/attempt_01/907f666f2dc6796d417e49287fd31f88263f1d67/data/2026-2027/By Tournament/Champions League/GW4/playermatchstats.csv` | `2026-09-14T14:41:27.799515+00:00` | 25453 |

## Appendix B — complete official history schema

48 rows; observed Python JSON types and missingness. Integer-looking decimal strings are retained as strings. No schema claim is made for unsampled responses.

| Field | Observed types (count) | Absent / null / empty |
|---|---|---|
| `assists` | int: 48 | 0 / 0 / 0 |
| `bonus` | int: 48 | 0 / 0 / 0 |
| `bps` | int: 48 | 0 / 0 / 0 |
| `clean_sheets` | int: 48 | 0 / 0 / 0 |
| `clearances_blocks_interceptions` | int: 48 | 0 / 0 / 0 |
| `creativity` | str: 48 | 0 / 0 / 0 |
| `defensive_contribution` | int: 48 | 0 / 0 / 0 |
| `element` | int: 48 | 0 / 0 / 0 |
| `expected_assists` | str: 48 | 0 / 0 / 0 |
| `expected_goal_involvements` | str: 48 | 0 / 0 / 0 |
| `expected_goals` | str: 48 | 0 / 0 / 0 |
| `expected_goals_conceded` | str: 48 | 0 / 0 / 0 |
| `fixture` | int: 48 | 0 / 0 / 0 |
| `goals_conceded` | int: 48 | 0 / 0 / 0 |
| `goals_scored` | int: 48 | 0 / 0 / 0 |
| `ict_index` | str: 48 | 0 / 0 / 0 |
| `influence` | str: 48 | 0 / 0 / 0 |
| `kickoff_time` | str: 48 | 0 / 0 / 0 |
| `minutes` | int: 48 | 0 / 0 / 0 |
| `modified` | bool: 48 | 0 / 0 / 0 |
| `opponent_team` | int: 48 | 0 / 0 / 0 |
| `own_goals` | int: 48 | 0 / 0 / 0 |
| `penalties_missed` | int: 48 | 0 / 0 / 0 |
| `penalties_saved` | int: 48 | 0 / 0 / 0 |
| `recoveries` | int: 48 | 0 / 0 / 0 |
| `red_cards` | int: 48 | 0 / 0 / 0 |
| `round` | int: 48 | 0 / 0 / 0 |
| `saves` | int: 48 | 0 / 0 / 0 |
| `selected` | int: 48 | 0 / 0 / 0 |
| `starts` | int: 48 | 0 / 0 / 0 |
| `tackles` | int: 48 | 0 / 0 / 0 |
| `team_a_score` | int: 48 | 0 / 0 / 0 |
| `team_h_score` | int: 48 | 0 / 0 / 0 |
| `threat` | str: 48 | 0 / 0 / 0 |
| `total_points` | int: 48 | 0 / 0 / 0 |
| `transfers_balance` | int: 48 | 0 / 0 / 0 |
| `transfers_in` | int: 48 | 0 / 0 / 0 |
| `transfers_out` | int: 48 | 0 / 0 / 0 |
| `value` | int: 48 | 0 / 0 / 0 |
| `was_home` | bool: 48 | 0 / 0 / 0 |
| `yellow_cards` | int: 48 | 0 / 0 / 0 |

## Appendix C — complete Core schemas and missingness

All cells are CSV strings. Lexical forms below are the union of forms observed across the three exports, not inferred canonical types. Missing counts are empty cells in GW3 / GW4 / CL-GW4 respectively. The CL file repeats GW4 data, so its counts must not be added to the GW4 totals. Per-export lexical counts, absent columns and literal-null tokens are in coverage.json.

### Match schema (116 columns; 10 / 20 / 5 rows)

| Column | Observed lexical forms | Empty GW3 / GW4 / CL-GW4 |
|---|---|---|
| `away_accurate_crosses` | decimal_text | 0 / 3 / 0 |
| `away_accurate_crosses_pct` | decimal_text | 0 / 3 / 0 |
| `away_accurate_long_balls` | decimal_text | 0 / 3 / 0 |
| `away_accurate_long_balls_pct` | decimal_text | 0 / 3 / 0 |
| `away_accurate_passes` | decimal_text | 0 / 3 / 0 |
| `away_accurate_passes_pct` | decimal_text | 0 / 3 / 0 |
| `away_aerial_duels_won` | decimal_text | 0 / 3 / 0 |
| `away_aerial_duels_won_pct` | decimal_text | 0 / 3 / 0 |
| `away_big_chances` | decimal_text | 0 / 3 / 0 |
| `away_big_chances_missed` | decimal_text | 0 / 3 / 0 |
| `away_blocked_shots` | decimal_text | 0 / 3 / 0 |
| `away_blocks` | decimal_text | 0 / 3 / 0 |
| `away_clearances` | decimal_text | 0 / 3 / 0 |
| `away_corners` | decimal_text | 0 / 3 / 0 |
| `away_distance_covered` | all empty | 10 / 20 / 5 |
| `away_duels_won` | decimal_text | 0 / 3 / 0 |
| `away_expected_goals_xg` | decimal_text | 0 / 3 / 0 |
| `away_fouls_committed` | decimal_text | 0 / 3 / 0 |
| `away_ground_duels_won` | decimal_text | 0 / 3 / 0 |
| `away_ground_duels_won_pct` | decimal_text | 0 / 3 / 0 |
| `away_hit_woodwork` | decimal_text | 0 / 3 / 0 |
| `away_interceptions` | decimal_text | 0 / 3 / 0 |
| `away_keeper_saves` | decimal_text | 0 / 3 / 0 |
| `away_non_penalty_xg` | decimal_text | 0 / 3 / 0 |
| `away_number_of_sprints` | all empty | 10 / 20 / 5 |
| `away_offsides` | decimal_text | 0 / 3 / 0 |
| `away_opposition_half` | decimal_text | 0 / 3 / 0 |
| `away_own_half` | decimal_text | 0 / 3 / 0 |
| `away_passes` | decimal_text | 0 / 3 / 0 |
| `away_possession` | decimal_text | 0 / 3 / 0 |
| `away_red_cards` | decimal_text | 0 / 3 / 0 |
| `away_running_distance` | all empty | 10 / 20 / 5 |
| `away_score` | decimal_text | 0 / 3 / 0 |
| `away_shots_inside_box` | decimal_text | 0 / 3 / 0 |
| `away_shots_off_target` | decimal_text | 0 / 3 / 0 |
| `away_shots_on_target` | decimal_text | 0 / 3 / 0 |
| `away_shots_outside_box` | decimal_text | 0 / 3 / 0 |
| `away_sprinting_distance` | all empty | 10 / 20 / 5 |
| `away_successful_dribbles` | decimal_text | 0 / 3 / 0 |
| `away_successful_dribbles_pct` | decimal_text | 0 / 3 / 0 |
| `away_tackles_won` | decimal_text | 0 / 3 / 0 |
| `away_tackles_won_pct` | all empty | 10 / 20 / 5 |
| `away_team` | decimal_text | 0 / 4 / 2 |
| `away_team_elo` | all empty | 10 / 20 / 5 |
| `away_throws` | decimal_text | 0 / 3 / 0 |
| `away_top_speed` | all empty | 10 / 20 / 5 |
| `away_total_shots` | decimal_text | 0 / 3 / 0 |
| `away_touches_in_opposition_box` | decimal_text | 0 / 3 / 0 |
| `away_walking_distance` | all empty | 10 / 20 / 5 |
| `away_xg_on_target_xgot` | decimal_text | 0 / 3 / 0 |
| `away_xg_open_play` | decimal_text | 0 / 3 / 0 |
| `away_xg_set_play` | decimal_text | 0 / 3 / 0 |
| `away_yellow_cards` | decimal_text | 0 / 3 / 0 |
| `bzzoiro_processed` | boolean_text | 0 / 13 / 5 |
| `finished` | boolean_text | 0 / 0 / 0 |
| `fotmob_id` | decimal_text | 0 / 0 / 0 |
| `gameweek` | integer_text | 0 / 0 / 0 |
| `home_accurate_crosses` | decimal_text | 0 / 3 / 0 |
| `home_accurate_crosses_pct` | decimal_text | 0 / 3 / 0 |
| `home_accurate_long_balls` | decimal_text | 0 / 3 / 0 |
| `home_accurate_long_balls_pct` | decimal_text | 0 / 3 / 0 |
| `home_accurate_passes` | decimal_text | 0 / 3 / 0 |
| `home_accurate_passes_pct` | decimal_text | 0 / 3 / 0 |
| `home_aerial_duels_won` | decimal_text | 0 / 3 / 0 |
| `home_aerial_duels_won_pct` | decimal_text | 0 / 3 / 0 |
| `home_big_chances` | decimal_text | 0 / 3 / 0 |
| `home_big_chances_missed` | decimal_text | 0 / 3 / 0 |
| `home_blocked_shots` | decimal_text | 0 / 3 / 0 |
| `home_blocks` | decimal_text | 0 / 3 / 0 |
| `home_clearances` | decimal_text | 0 / 3 / 0 |
| `home_corners` | decimal_text | 0 / 3 / 0 |
| `home_distance_covered` | all empty | 10 / 20 / 5 |
| `home_duels_won` | decimal_text | 0 / 3 / 0 |
| `home_expected_goals_xg` | decimal_text | 0 / 3 / 0 |
| `home_fouls_committed` | decimal_text | 0 / 3 / 0 |
| `home_ground_duels_won` | decimal_text | 0 / 3 / 0 |
| `home_ground_duels_won_pct` | decimal_text | 0 / 3 / 0 |
| `home_hit_woodwork` | decimal_text | 0 / 3 / 0 |
| `home_interceptions` | decimal_text | 0 / 3 / 0 |
| `home_keeper_saves` | decimal_text | 0 / 3 / 0 |
| `home_non_penalty_xg` | decimal_text | 0 / 3 / 0 |
| `home_number_of_sprints` | all empty | 10 / 20 / 5 |
| `home_offsides` | decimal_text | 0 / 3 / 0 |
| `home_opposition_half` | decimal_text | 0 / 3 / 0 |
| `home_own_half` | decimal_text | 0 / 3 / 0 |
| `home_passes` | decimal_text | 0 / 3 / 0 |
| `home_possession` | decimal_text | 0 / 3 / 0 |
| `home_red_cards` | decimal_text | 0 / 3 / 0 |
| `home_running_distance` | all empty | 10 / 20 / 5 |
| `home_score` | decimal_text | 0 / 3 / 0 |
| `home_shots_inside_box` | decimal_text | 0 / 3 / 0 |
| `home_shots_off_target` | decimal_text | 0 / 3 / 0 |
| `home_shots_on_target` | decimal_text | 0 / 3 / 0 |
| `home_shots_outside_box` | decimal_text | 0 / 3 / 0 |
| `home_sprinting_distance` | all empty | 10 / 20 / 5 |
| `home_successful_dribbles` | decimal_text | 0 / 3 / 0 |
| `home_successful_dribbles_pct` | decimal_text | 0 / 3 / 0 |
| `home_tackles_won` | decimal_text | 0 / 3 / 0 |
| `home_tackles_won_pct` | all empty | 10 / 20 / 5 |
| `home_team` | decimal_text | 0 / 4 / 3 |
| `home_team_elo` | all empty | 10 / 20 / 5 |
| `home_throws` | decimal_text | 0 / 3 / 0 |
| `home_top_speed` | all empty | 10 / 20 / 5 |
| `home_total_shots` | decimal_text | 0 / 3 / 0 |
| `home_touches_in_opposition_box` | decimal_text | 0 / 3 / 0 |
| `home_walking_distance` | all empty | 10 / 20 / 5 |
| `home_xg_on_target_xgot` | decimal_text | 0 / 3 / 0 |
| `home_xg_open_play` | decimal_text | 0 / 3 / 0 |
| `home_xg_set_play` | decimal_text | 0 / 3 / 0 |
| `home_yellow_cards` | decimal_text | 0 / 3 / 0 |
| `kickoff_time` | timestamp_text | 0 / 0 / 0 |
| `match_id` | text | 0 / 0 / 0 |
| `match_url` | text | 0 / 0 / 0 |
| `player_stats_processed` | boolean_text | 0 / 0 / 0 |
| `stats_processed` | boolean_text | 0 / 0 / 0 |
| `tournament` | text | 0 / 0 / 0 |

### Player-match schema (64 columns; 400 / 518 / 106 rows)

| Column | Observed lexical forms | Empty GW3 / GW4 / CL-GW4 |
|---|---|---|
| `accurate_crosses` | decimal_text | 277 / 345 / 75 |
| `accurate_crosses_percent` | decimal_text | 277 / 345 / 75 |
| `accurate_long_balls` | decimal_text | 211 / 264 / 62 |
| `accurate_long_balls_percent` | decimal_text | 211 / 264 / 62 |
| `accurate_passes` | decimal_text | 113 / 141 / 32 |
| `accurate_passes_percent` | decimal_text | 117 / 143 / 32 |
| `aerial_duels_won` | decimal_text | 107 / 130 / 32 |
| `aerial_duels_won_percent` | decimal_text | 187 / 244 / 52 |
| `assists` | decimal_text | 113 / 141 / 32 |
| `big_chances_missed` | all empty | 400 / 518 / 106 |
| `blocks` | decimal_text | 113 / 141 / 32 |
| `chances_created` | decimal_text | 112 / 140 / 31 |
| `clearances` | decimal_text | 93 / 115 / 27 |
| `corners` | all empty | 400 / 518 / 106 |
| `defensive_contributions` | all empty | 400 / 518 / 106 |
| `dispossessed` | decimal_text | 113 / 141 / 32 |
| `distance_covered` | decimal_text | 93 / 222 / 27 |
| `dribbled_past` | decimal_text | 113 / 141 / 32 |
| `duels_lost` | decimal_text | 146 / 177 / 38 |
| `duels_won` | decimal_text | 139 / 172 / 38 |
| `final_third_passes` | decimal_text | 158 / 184 / 42 |
| `finish_min` | integer_text | 93 / 115 / 27 |
| `fouls_committed` | decimal_text | 93 / 115 / 27 |
| `gk_accurate_long_balls` | decimal_text | 380 / 492 / 101 |
| `gk_accurate_passes` | decimal_text | 380 / 492 / 101 |
| `goals` | decimal_text | 113 / 141 / 32 |
| `goals_conceded` | decimal_text | 380 / 492 / 101 |
| `goals_prevented` | decimal_text | 381 / 494 / 103 |
| `ground_duels_won` | decimal_text | 132 / 159 / 33 |
| `ground_duels_won_percent` | decimal_text | 132 / 159 / 33 |
| `headed_clearances` | decimal_text | 278 / 369 / 88 |
| `high_claim` | decimal_text | 380 / 492 / 101 |
| `interceptions` | decimal_text | 93 / 115 / 27 |
| `match_id` | text | 0 / 0 / 0 |
| `minutes_played` | decimal_text | 0 / 0 / 0 |
| `number_of_sprints` | decimal_text | 122 / 243 / 32 |
| `offsides` | all empty | 400 / 518 / 106 |
| `penalties_missed` | integer_text | 0 / 0 / 0 |
| `penalties_scored` | decimal_text | 0 / 0 / 0 |
| `player_id` | integer_text | 0 / 0 / 0 |
| `recoveries` | decimal_text | 93 / 115 / 27 |
| `running_distance` | decimal_text | 93 / 222 / 27 |
| `saves` | decimal_text | 380 / 492 / 101 |
| `saves_inside_box` | decimal_text | 380 / 492 / 101 |
| `shots_on_target` | decimal_text | 254 / 316 / 60 |
| `sprinting_distance` | decimal_text | 108 / 235 / 28 |
| `start_min` | integer_text | 93 / 115 / 27 |
| `successful_dribbles` | all empty | 400 / 518 / 106 |
| `successful_dribbles_percent` | all empty | 400 / 518 / 106 |
| `sweeper_actions` | decimal_text | 380 / 492 / 101 |
| `tackles` | all empty | 400 / 518 / 106 |
| `tackles_won` | decimal_text | 93 / 115 / 27 |
| `tackles_won_percent` | all empty | 400 / 518 / 106 |
| `team_goals_conceded` | integer_text | 0 / 0 / 0 |
| `top_speed` | decimal_text | 93 / 222 / 27 |
| `total_shots` | decimal_text | 254 / 316 / 60 |
| `touches` | decimal_text | 93 / 115 / 27 |
| `touches_opposition_box` | decimal_text | 113 / 141 / 32 |
| `walking_distance` | decimal_text | 400 / 439 / 27 |
| `was_fouled` | decimal_text | 256 / 336 / 70 |
| `xa` | decimal_text | 196 / 224 / 45 |
| `xg` | decimal_text | 254 / 316 / 60 |
| `xgot` | decimal_text | 339 / 417 / 78 |
| `xgot_faced` | decimal_text | 381 / 494 / 103 |

## Appendix D — observed completion-flag differences

These are separate from numeric discrepancies. Core completion does not override the official-label finality contract.

| FPL fixture | Core match | Official finished | Core finished | Classification |
|---|---|---|---|---|
| 31 | `26-27-prem-aston-villa-vs-nottingham-forest` | False | True | provisional/finality issue |
| 32 | `26-27-prem-afc-bournemouth-vs-brentford` | False | True | provisional/finality issue |
| 33 | `26-27-prem-chelsea-vs-hull-city` | False | True | provisional/finality issue |
| 34 | `26-27-prem-crystal-palace-vs-ipswich-town` | False | True | provisional/finality issue |
| 35 | `26-27-prem-liverpool-vs-fulham` | False | True | provisional/finality issue |
| 37 | `26-27-prem-tottenham-hotspur-vs-everton` | False | True | provisional/finality issue |
| 36 | `26-27-prem-sunderland-vs-arsenal` | False | True | provisional/finality issue |
