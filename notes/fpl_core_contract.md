# FPL Core raw ingestion contract — Step 1C

Reviewed 2026-09-13 against commit
`349ffd62a458f0dfcac72901aabdfe55f16a8050`, for season `2026-2027`.
The live smoke test pins this exact revision. This is a reference for testing,
not an automatically updated production default.

## File selection

Only the four master files already named by the original adapter are ingested.
All paths below are relative to `data/<season>/` at the supplied commit.

| File | Requirement | Minimum columns checked | Reason |
| --- | --- | --- | --- |
| `players.csv` | Required | `player_id`, `player_code`, `team_code`, `position` | Core player metadata. |
| `teams.csv` | Required | `id`, `code`, `name` | Core team metadata. |
| `playerstats.csv` | Required | `id`, `gw`, `minutes`, `total_points` | Existing player-statistics export; granular interpretation remains separate work. |
| `gameweek_summaries.csv` | Optional | `id`, `deadline_time` | Supplemental event metadata; official FPL ingestion already supplies event/deadline data. |

These requirements are explicit constants in the adapter, not inferred from
whether a download happens to succeed. A missing optional summary never makes a
required file optional. All four files are attempted on a successful required path.

## Pinning and provenance

`fetch_fpl_core_master(writer, *, commit_sha, season="2026-2027")` requires a full
40-character hexadecimal SHA. Branch names, tags and abbreviated SHAs are rejected
before network access; uppercase hex is normalized to lowercase. The adapter never
resolves `main`, discovers a latest revision, or falls back to another path/season.

The caller chooses the SHA explicitly. Every source URL is constructed as:

```text
https://raw.githubusercontent.com/olbauday/FPL-Core-Insights/<sha>/data/<season>/<file>
```

The writer persists `source_commits.fpl_core` before the first request. The same
source cannot switch revisions later in that run, even across separate adapter
calls. Each raw file and no-body failure also records its `commit_sha` and
`request_url`; timestamps, required/optional flags and the remaining snapshot
metadata follow the existing contract. Other sources need not be Git-versioned.

Raw files are stored under:

```text
raw/fpl_core/<sha>/data/<season>/<file>
```

Request/retrieval timestamps reflect the actual local request. Neither the Git
commit date nor an upstream `snapshot_time` is substituted for retrieval time or
treated as proof of historical pre-deadline availability.

## Parsing and failure behavior

Response-body bytes from `requests.Response.content` are persisted before decoding
or CSV parsing. HTTP content/transfer decoding is handled by requests; there is no
CSV rewriting, dataframe conversion or Parquet output. A UTF-8 BOM is tolerated
only during parsing; the saved bytes retain it, along with CRLFs and quoting.

GitHub Raw serves the observed CSVs as `text/plain`. The adapter checks the CSV
body rather than requiring a `text/csv` media type. It rejects empty bodies,
missing/duplicate/empty headers, malformed quoting, inconsistent row widths and
invalid core identifiers. Extra columns, quoted multiline fields and empty
non-key statistics are preserved. Header-only tables are schema-valid; this does
not assert useful data coverage. Dataset validation is not implemented here.

Required HTTP, transport or contract failures raise a safe exception and prevent
finalization. HTTP error bodies and malformed CSVs remain in staging. An optional
failure may allow finalization, but remains visible in both the manifest and the
returned per-file report (`success`, `http_error`, `request_failed`, or
`contract_failed`). An HTTP 200 with invalid CSV retains its HTTP success entry
plus a separate failure record; HTTP success does not imply contract success.

No automatic retries or redirects occur. Response headers, exception text and
credentials are not recorded. The caller owns finalization, and a borrowed HTTP
session remains caller-owned. The old path-based multi-source runner has not been
migrated in this step.

## Observed structure and unresolved meaning

Inspection of the [pinned season directory](https://github.com/olbauday/FPL-Core-Insights/tree/349ffd62a458f0dfcac72901aabdfe55f16a8050/data/2026-2027)
confirmed all four selected files. It also contained `team_history.csv`,
`By Gameweek/`, and `By Tournament/`; those are not ingested in this step.

- The observed root `playerstats.csv` had 2,580 rows, 656 distinct `id` values,
  and `gw` values 1–4. Repeated player IDs are expected in this sample. The file
  must not be assumed to contain one current row per player or one row per match.
  Cumulative fields, GW labels and subsequent revisions need a separate audit.
- The inspected `By Gameweek/GW1/` directory contained `matches.csv`,
  `playermatchstats.csv`, and `player_gameweek_stats.csv`, alongside other files.
  These are distinct exports; the adapter does not substitute them for master
  files, deduplicate across directories, or traverse tournaments.
- Player metadata uses `player_id` and `team_code`, whereas statistics use `id`;
  teams contain both `id` and `code`. The sample's positions were full words
  (`Goalkeeper`, `Defender`, `Midfielder`, `Forward`). No canonical mappings or
  position conversion are inferred during ingestion.
- The upstream [README](https://github.com/olbauday/FPL-Core-Insights/blob/349ffd62a458f0dfcac72901aabdfe55f16a8050/README.md)
  describes season aggregates and end-of-GW folders, while also referring to
  deadline snapshot fields. These descriptions do not establish one uniform
  information cutoff. Immutable Git retrieval alone does not establish that the
  data was publicly available before a historical FPL deadline.

## Verification

Normal tests use synthetic stored CSV fixtures, mock sessions and the existing
network guard:

```sh
.venv/bin/python -m pytest -q
```

Exactly one Core live test is added and excluded by default. Run it explicitly:

```sh
.venv/bin/python -m pytest tests/test_fpl_core_live.py -m live -q
```

It fetches the four files at the reviewed SHA into pytest's temporary directory
and verifies the finalized snapshot. It additionally expects the optional file
to succeed because its presence was verified at this specific revision.
