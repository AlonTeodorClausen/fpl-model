# Step 2C — bounded official-FPL player-fixture label ingestion

This stage captures an explicit player sample and normalizes official FPL history only. It does not expand the multi-source runner, ingest the player universe, join Core, select forecasting inputs, build features or train models. The existing Step 2B identity/time/finality contracts remain in use and unchanged.

## Interface and raw capture

`fetch_player_histories(writer, element_ids, session=None, clock=...)` accepts **1–20 distinct positive integer IDs**. The list is mandatory, validated before network access and requested in sorted order. No IDs are discovered or expanded from bootstrap. The bound is a deliberate Step 2C scope guard, not an API limit.

Each GET uses the official `https://fantasy.premierleague.com/api/element-summary/{id}/` endpoint. It stores exact `response.content` bytes before parsing at:

`raw/fpl_api/element_summary/{id}.json`

HTTP transfer/content decoding is performed by requests, as in the existing official adapter; JSON is never reserialized into raw storage. Metadata includes source `fpl_api`, required=true, URL, `request_context.element_id`, request start, retrieval, availability, HTTP status, content type, byte count and SHA-256. `available_at = retrieved_at` for each history response. Transport failures have explicit manifest records; HTTP/error/invalid-payload bodies remain captured. Headers, credentials and arbitrary exception text are never persisted or printed by this workflow.

The policy matches the existing official adapter: connect/read timeout **10/30 seconds**, no redirects, **one attempt / zero automatic retries**. A required failure needs a new snapshot run; a failed response is never replaced by an empty history. The adapter never finalizes or marks the overall writer complete.

The sample workflow creates exactly one writer, calls the existing bootstrap/fixture adapter, calls the new history adapter, then finalizes. A capture failure marks the run failed and leaves raw data in staging. There is no change to the existing multi-source runner or other adapters.

The existing bootstrap/fixture adapter does not record an explicit availability field. Normalization conservatively uses its recorded retrieval time, with `availability_basis = retrieval_fallback` retained in row provenance. No old manifest is changed.

## CLI and reproducibility

An explicit capture command, used once for this sample:

```bash
.venv/bin/python scripts/player_fixture_labels.py capture \
  --season 2026-2027 --elements 1 2 5 12 26 439 \
  --raw-root data/raw --output-root artifacts/audits
```

Offline reproduction from the captured snapshot:

```bash
.venv/bin/python scripts/player_fixture_labels.py normalize \
  --snapshot data/raw/2026-09-21_154052706958Z_ef2f249d293f4fa888176ed0c109ffce \
  --season 2026-2027 --elements 1 2 5 12 26 439 \
  --output-root /tmp/fpl-step2c-reproduction
```

Normalization verifies the snapshot's completion marker and hashes. It requires one unambiguous successful history capture for every explicitly requested player and bootstrap/fixture context from the **same snapshot**. A missing capture is an error; a genuine `history: []` is a successfully observed empty history with zero labels. The caller supplies the season, which must match run metadata if recorded. For older snapshots without season metadata, that season is an explicit caller assertion, not inferred from current time.

Each report is written exclusively to `<output-root>/step2c_<source-run-id>/`. Existing directories cannot be overwritten, even when using a different player selection. To reproduce or revise a normalization policy, use a new output root and retain the earlier report. Output inside raw snapshot storage is rejected.

Files:

- `labels.jsonl`: accepted, final or provisional observations.
- `quarantine.jsonl`: unusable rows with reasons and the complete original history object.
- `quality.json`: requested-player coverage, label states, missing/null fields, zero-minute counts, provenance and validation results.
- `COMPLETE.json`: SHA-256 of each preceding output, written last. Consumers must require it and check the digests; an interrupted report directory without the marker is incomplete.

For identical snapshot bytes, selected IDs, season and normalizer version, outputs are deterministic. There is no normalization-time timestamp or random output ID. Raw retrieval versions remain independent from processing time. `schema_version=1` identifies this initial format; future contract changes need an explicit version change and new output location.

CLI exits: **0** for a completed report without quarantine; **2** for a completed report with quarantine; **1** for capture/verification/normalization/output failure. A successful raw capture is distinct from label quality.

## Normalized schema

Within a single observation version, one accepted row has key `(season, player_id, fixture_id)`. Across versions the key is `(season, source_snapshot_id, player_id, fixture_id)`. `observation_id` encodes that versioned key. GW is not part of identity and never collapses DGW fixtures.

All mapped official values retain their decoded JSON value and type. FPL point totals are copied, never recomputed. The entire original history object is also retained in `official_history`, including unmapped price/ownership/transfer fields and future unknown fields. Exact lexical JSON bytes remain in the referenced raw file; JSONL is the processed representation.

| Column(s) | Type / source / contract |
|---|---|
| `schema_version`, `season`, `source` | Version integer; explicit `YYYY-YYYY`; fixed `fpl_api`. |
| `player_id` | Official positive integer `history.element`, equal to requested endpoint ID and present in bootstrap. |
| `fixture_id` | Official positive integer `history.fixture`, present uniquely in fixtures. |
| `event` | Integer `history.round`, consistent with fixture event and event record. |
| `team_id` | Official fixture `team_h` when `was_home=true`, otherwise `team_a`; both fixture team IDs must exist in bootstrap teams. |
| `opponent_team_id` | Official `history.opponent_team`, checked against the opposite fixture side. |
| `was_home` | Original boolean. No truthy string coercion. |
| `kickoff_time`, `event_time` | Original timezone-bearing kickoff string; same instant as fixture kickoff. Event time does not imply publication/availability. |
| `minutes`, `starts` | Official integer values. Minutes required by the label contract; starts optional when absent, otherwise subject to Step 2B checks. |
| `goals_scored`, `assists`, `clean_sheets`, `goals_conceded`, `own_goals`, `penalties_saved`, `penalties_missed`, `yellow_cards`, `red_cards`, `saves`, `bonus`, `bps` | Official integers when present. Missing optional values stay null, never zero. |
| `total_points` | Required official integer. Negative points are allowed. No point recalculation. |
| `influence`, `creativity`, `threat`, `ict_index` | Original finite, nonnegative decimal strings when present. |
| `expected_goals`, `expected_assists`, `expected_goal_involvements`, `expected_goals_conceded` | Original finite, nonnegative decimal strings when present; no float conversion or rounding. |
| `clearances_blocks_interceptions`, `recoveries`, `tackles`, `defensive_contribution` | Observed official integer defensive statistics when present. No Core substitutes. |
| `label_state`, `label_state_reason` | `final` or `provisional` in accepted labels; unusable rows go to quarantine. |
| `source_snapshot_id`, `observation_id`, `source_history_index` | Immutable raw run ID, versioned row key, zero-based position in that response's history array. |
| `retrieved_at` | This player's history retrieval time, copied from its manifest record. |
| `history_available_at` | That raw history's availability, equal to retrieval for this capture. |
| `available_at` | Maximum availability of history, bootstrap and fixture context used to validate the row. Never earlier than any dependency. |
| `source_published_at` | Null; no verified publication timestamp is supplied by these endpoints. |
| `provenance` | Three input file manifest entries with paths, SHA-256, timing and effective availability/basis. Context timestamps are independently retained. |
| `missing_fields`, `null_fields` | Separate lists for absent optional statistic keys and explicitly null values. Both normalize to null, with this distinction preserved. |
| `official_history` | Unmodified decoded original row; the raw file remains the authoritative byte representation. |

Integer statistics reject booleans, strings and nonintegral values. Negative counts are invalid; `total_points` and `bps` may be negative. The decimal-string type is the schema actually observed in Step 2B/2C: a future type change is quarantined for review rather than silently coerced. Missing optional statistics do not manufacture usable values. Invalid required values, including minutes/points, make the whole row unusable.

## Identity validation, quarantine and transfers

No secondary-source names, aliases or Core identifiers participate. Global duplicate/missing IDs in context tables are rejected as ambiguous. Duplicate player-fixture history rows are all quarantined rather than choosing the first/last. Wrong endpoint/player identity, unknown fixture/team IDs, inconsistent opponent/home/away, inconsistent kickoff/event, invalid statistics and not-started/unscheduled fixture contexts are unusable.

A player's current bootstrap team is **not** assigned to historical appearances. A transferred player's earlier rows retain the side implied by each official fixture/history pair. A current-team difference is reported in quality metadata, not automatically treated as an error or proof of transfer. The history endpoint plus fixture sides are the evidence; this stage does not claim independent historical registration or lineup verification.

Quarantine retains the requested player ID, original row, array index, snapshot/time provenance, `label_state=unusable` and explicit reason codes. It does not guess a valid fixture/player key for malformed rows. No unusable rows enter `labels.jsonl`.

## Completion and missingness

The Step 2B `label_state` contract is reused:

- **Final:** valid minutes/points and identity/context, started and finished official fixture, associated event finished and `data_checked=true`.
- **Provisional:** a valid row for a started fixture whose fixture/GW has not met all completion requirements.
- **Unusable:** missing/invalid required data or inconsistent context; quarantine or fail ambiguous global input.

`finished_provisional=true` is insufficient. Finality describes this observed version and can later be revised; it is not an immutable promise about source values. Nullable optional fields require field-specific downstream eligibility even when the points/minutes label is final.

An explicit zero-minute row remains an observed zero-minute row. Missing history creates no label. Empty history is recorded as `empty_observed_history`. The normalizer does not fabricate a player×fixture roster, so it cannot certify completeness of unseen rows or identify every missing appearance from this input alone.

DGWs stay separate fixture rows in the same event. Postponed/unscheduled fixtures without history create no zero-minute rows; stale history/context combinations are quarantined. If date or GW changes consistently in a later observation, the same fixture retains its ID and each version retains its own observed date/GW. Older rows are never updated.

## Observation versions and historical use

The two sample report directories contain independent observations. They can later be unioned by their versioned keys, preserving every value and state. A future selection policy could filter `available_at < forecast_origin_at` and choose the latest observation per season/player/fixture, with an explicit state policy. **That selector, feature generation and forecasting are not implemented here.**

No historical availability is inferred from kickoff, GW, `modified`, Git commit time, the present retrieval time, or finality. A history row for August fetched in September is a September observation version. Later finalized outcomes may be evaluation labels; those labels do not prove pre-deadline input availability. Separate prospective input capture and target-observation timing remain necessary for later backtesting.

## Live/sample validation summary

New raw snapshot:

`data/raw/2026-09-21_154052706958Z_ef2f249d293f4fa888176ed0c109ffce`

Retrieval window: **2026-09-21T15:40:52.861445+00:00 – 2026-09-21T15:40:52.933007+00:00**. Eight HTTP 200 responses: bootstrap, fixtures, and six element-summary responses, all `application/json`. No all-player history enumeration occurred.

| ID | Player | Team | Position | Observed GW1–5 minutes |
|---|---|---|---|---|
| 1 | Raya | Arsenal | GK | 90, 90, 90, 90, 90 |
| 2 | Arrizabalaga | Arsenal | GK | 0, 0, 0, 0, 0 |
| 5 | J.Timber | Arsenal | DEF | 0, 0, 0, 45, 59 |
| 12 | Saka | Arsenal | MID | 67, 90, 89, 90, 80 |
| 26 | Havertz | Arsenal | FWD | 90, 90, 77, 90, 90 |
| 439 | Šeško | Man Utd | FWD | 23, 10, 20, 23, 0 |

Current output:

`artifacts/audits/step2c_ef2f249d293f4fa888176ed0c109ffce/`

**30 accepted rows; 30 final; zero quarantined; nine explicit zero-minute rows.** All 27 configured statistics are present and non-null in this sample. Every normalized original field was independently checked against its raw response row; all agree. `quality.json` records counts, availability and field missingness; `COMPLETE.json` covers every output's hash.

Earlier source observation, normalized offline without changing Step 2B files:

`artifacts/audits/step2c_8c9e6040dee04f6dbdd83e7ae747929d/`

It references the original September 14 Step 2B snapshot and selects the same six players: **24 accepted rows, 18 final and six provisional**, zero quarantined. Both normalized versions remain separate. Across them, 24 player-fixture keys are shared, six new GW5 labels appear, and all six old GW4 provisional rows become final in the new observation. The earlier 18 final rows retain identical original history values.

Five shared GW4 rows also have revised provider statistics:

| Player / fixture | Changed official fields (old → new) |
|---|---|
| Raya / 36 | creativity 0.0 → 0.2; influence 0.0 → 37.8; ict_index 0.0 → 3.8 |
| J.Timber / 36 | creativity 0.0 → 1.9; influence 0.0 → 6.0; ict_index 0.0 → 0.8 |
| Saka / 36 | creativity 0.0 → 16.9; influence 0.0 → 45.4; threat 0.0 → 57.0; ict_index 0.0 → 11.9 |
| Havertz / 36 | creativity 0.0 → 12.4; influence 0.0 → 1.6; threat 0.0 → 32.0; ict_index 0.0 → 4.6 |
| Šeško / 39 | creativity 0.0 → 0.7; influence 0.0 → 1.2; threat 0.0 → 4.0; ict_index 0.0 → 0.6 |

Minutes and total points in all 24 shared rows were unchanged. These observed late updates support retaining source versions and treating provisional zero-valued statistics cautiously. They are not corrected in either version and are unrelated to unresolved Core minute/xG differences.

## Offline test coverage and remaining uncertainties

`tests/fixtures/player_fixture_labels/contract_cases.json` explicitly declares synthetic contract cases. These exercise normal and zero-minute appearances, absent rows, substitutes, DGWs, postponements, consistent/stale reschedules, transfers and provisional/finished/unchecked GWs. Live validation establishes ordinary appearances, observed DNP/substitute histories and a provisional→final transition. It does **not** establish live DGW, postponement, transfer or rescheduling behaviour; those remain contract fixtures.

Additional tests verify raw bytes/checksums, manifest metadata, caller finalization, failed body retention, bounded IDs/timeouts/attempts, no secret leakage, exact official values/types, canonical identity rejection, optional absent-vs-null fields, duplicate quarantine, later context raising availability, protected raw data, deterministic reports and retention of separate provisional/final observation versions. Default tests are offline and use no token.

Full command `.venv/bin/python -m pytest -q`: **476 passed, 5 deselected in 2.43s** (50 new Step 2C cases). The existing live tests were excluded. Both real sample reports reproduced byte-for-byte in fresh output directories; their raw snapshots and report checksums verified. All 53 protected pre-existing raw/Step 2A/Step 2B files retained their original hashes. The new raw snapshot and generated audit directories remain gitignored and untracked.

Coverage of all players/seasons, historical registrations and source corrections beyond this sample remains unverified. A final flag is a conservative observed-state criterion, not proof all optional statistics can never change. Same-snapshot endpoints can still reflect different upstream refresh cycles; context inconsistencies are quarantined. Core remains a later enrichment source and the one-minute/xG discrepancies are untouched.

## Recommendation for Step 2D

Implement a **bounded official-only observation selection and completeness audit**, using these versioned outputs: define and test strict `available_at < forecast_origin_at`, state eligibility, deterministic ties and quarantined/missing-row handling; report availability gaps without manufacturing zeros or historical snapshots. Retain the six-player bound initially and validate a real DGW/transfer/postponement example only when available and approved. This should establish trustworthy version selection before any full-player expansion, canonical multi-source joins, features or model training. No Step 2D logic is implemented now.
