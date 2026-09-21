# Step 2E — bounded forecast-origin replay and readiness

This is an offline reference audit of players **1, 2, 5, 12, 26, 439** using the
existing September 14 and September 21 Step 2C reports and their immutable raw
captures. No new requests, features, scoring, Core joins, models or full-player
ingestion are performed. Previous snapshots and reports are not modified.

## Forecast origin

An origin is `(season, official event ID, official deadline UTC)`. The deadline
comes from `bootstrap-static`'s `events[id].deadline_time`; it is never calculated
from kickoff, match history or the current date. All timestamps must be aware;
output timestamps are normalized to UTC. The origin records the original file,
snapshot ID, manifest/file SHA-256, retrieval/availability, and precise field.

The earliest captured official deadline anchors an event's audit origin. This
keeps an existing origin stable when a later snapshot is added. Equal-time
disagreement about that initial deadline produces a conflicted, unresolved
origin. A missing deadline produces an unresolved origin, never an invented
cutoff. A changed deadline in the selected **pre-origin** bootstrap requires
review and blocks readiness; the tool does not silently move the cutoff.
Supporting deliberate replacement origins for revised deadlines is deferred.

An official deadline first observed **after** its own timestamp is useful to
define a retrospective question, but does not prove we knew that deadline then.
Its `deadline_evidence` is tagged `origin_definition_only`, with
`observed_by_origin=false`. It stays outside the information accessor. A separate
eligible bootstrap must establish the same deadline before readiness is possible.

## Minimal required information

For each origin/player the contract requires:

1. An eligible official bootstrap response, with a unique player, a known team
   ID, and the matching official deadline.
2. An eligible official fixture response containing an unambiguous event schedule
   for that **captured current team**. This is conditional schedule context, not
   proof of player participation, eligibility, or historical registration.
3. An eligible `element-summary/{player_id}` history response. Every observed
   history fixture must have a usable normalized observation selected through
   the Step 2D as-of selector; unresolved normalization, conflicts or quarantine
   block readiness. An older normalized row cannot stand in for a newer raw
   response whose normalization context was unavailable at the cutoff.

All required source versions and normalized observations must satisfy the
inclusive condition `available_at <= forecast_origin_at`. No minimum number of
historical appearances, required scoring statistic, model feature, or freshness
threshold is invented. `ready` means this factual reference contract is met,
not that a predictive model or complete historical roster is available.

A captured empty history is `empty_observed_history` and can meet this contract.
A missing history response cannot. Missing history rows never become inferred
DNPs. Provisional observed rows may be information, including explicit zero
minutes, while remaining ineligible as final targets. A player's appearance
establishes no expectation for other fixtures played by that team.

Multiple scheduled event fixtures are preserved. An empty event schedule is
`unresolved_empty_event_schedule` and blocks ready: this bounded implementation
does not guess whether the cause is a legitimate blank GW or incomplete context.
No historical membership intervals or transfer dates are inferred. The selected
team is explicitly `team_id_at_capture`, not a claim about the team at kickoff.

## Selection, conflict and readiness rules

`src/fpl_model/replay_readiness.py` operates on verified official source versions.
The CLI validates raw snapshot checksums and Step 2C report checksums, then
reproduces normalization and compares it to each supplied report. Raw context
selection applies the inclusive cutoff **before** checking eligible payloads or
conflicts. Player-fixture observations use `select_as_of(...).for_information()`
from Step 2D, with provisional and final states allowed.

Raw source ordering is descending availability, retrieval, snapshot ID, relative
path and SHA-256. Equivalent equal-time versions are explicitly listed and may
use that provenance tie-break. Divergent same-version metadata/payloads or
different values at an eligible equal timestamp are conflicts, even if a newer
version exists. Player-fixture tie/conflict rules remain Step 2D's existing
rules. Input and report ordering never selects a winner.

Each raw requirement records `available`, `missing` or `conflicted`, its reason,
selected reference and equivalent timestamp versions. Unresolved identity,
deadline, schedule and normalization checks have explicit record-level reasons.

| Readiness | Meaning |
|---|---|
| `ready` | Every required reference is pre-origin and all factual checks pass. |
| `partial` | Pre-origin source references exist, but identity/schedule/normalization or quarantine leaves a check unresolved. |
| `not_replayable` | A required reference lacks pre-origin provenance, or no official origin can be established. |
| `conflicted` | Eligible input source/observation or initial deadline versions conflict; no winner is guessed. |

Conflict takes precedence over other failure states; all reasons remain visible.
No eligible source version is explicitly `lacking_pre_origin_provenance`, whether
no capture exists at all or the first capture is later. This avoids a future
capture changing a historical classification from partial to not-replayable.
Earliest observed capture times are reported separately as audit diagnostics.
`provenance_class` distinguishes `pre_origin_captured`,
`lacking_pre_origin_provenance`, and `unresolved_origin`; possessing pre-origin
references alone does not bypass the other checks.

## Information and outcomes are separate

Every manifest record has separate `inputs` and `targets` sections.
`information_for(record)` requires readiness and rechecks the time boundary. It
returns a copy of **only** the input section, never targets, target diagnostics,
retrospective deadline evidence, or later capture coverage. This is a consumer
API contract over verified manifests, not a security boundary against callers
fabricating or rewriting dictionaries. It creates no forecasting features.

Targets use Step 2D `select_outcome`, selecting official final observations
without a forecast-origin cutoff. Each carries `purpose=outcome_only`, observation
and snapshot IDs, availability, final state, appearance status and provenance;
candidate final revisions remain auditable. Equal-version conflicts are exposed.
A quarantine at least as recent as the selected final suppresses its usable
target reference while retaining a `historical_final_reference` for diagnosis.
Neither target conflicts, missing finals nor later quarantine affect inputs.

The target fixture inventory is separately the union of the pre-origin schedule
and fixtures in that player's observed official history for the audited event.
It is **not** copied into the input fixture inventory. A rescheduled fixture can
retain its target by fixture ID even if its eventual event changed; the target's
actual event is recorded. This is a reference audit, not a definition of a future
GW scoring target or a sum over those references. Historical non-replayable
origins can therefore show final outcomes without pretending to have known
fixture context in advance.

## Real six-player results

Inputs:

- `artifacts/audits/step2c_8c9e6040dee04f6dbdd83e7ae747929d/`
- `artifacts/audits/step2c_ef2f249d293f4fa888176ed0c109ffce/`

The audited scope is **GWs1–6 × six players = 36 records**.

| GW | Captured official deadline (UTC) | Result for all six players |
|---|---|---|
| 1 | 2026-08-21 17:30 | not_replayable |
| 2 | 2026-08-28 17:30 | not_replayable |
| 3 | 2026-09-04 17:30 | not_replayable |
| 4 | 2026-09-12 12:30 | not_replayable |
| 5 | 2026-09-18 17:30 | ready under the minimal contract |
| 6 | 2026-10-10 10:00 | prospective ready under the minimal contract |

The 24 GW1–4 records lack pre-origin provenance. Their input fixture and
observation lists are empty; historical API rows cannot repair that deficiency.
The first sample bootstrap was captured at
`2026-09-14T14:41:26.089100+00:00`, already after all four deadlines.

GW5 selects September 14 references and four earlier observed player-fixtures per
player, retaining GW4's provisional state. Its six final targets were retrieved
on September 21, after GW5's deadline, and remain exclusively outcome references.
GW6 selects September 21 references and five historical rows per player. No GW6
final target is available. GW6's deadline is still prospective relative to these
captures; readiness describes the captured schedule version, not proof that no
further official schedule or identity update will occur before October 10.

There are **12 ready records, 24 not-replayable records, 30 selected final target
references and six no-final-target cases**, with no source quarantine in these
captures. Real-data ordering and frozen-input behavior are also covered by
synthetic integration tests; no network is needed to run them.

Example for player 1, GW5: input history snapshot
`8c9e6040dee04f6dbdd83e7ae747929d` was available at
`2026-09-14T14:41:26.124867+00:00`; its four input observations have the same
effective availability. The GW5 fixture is 42. Its target observation
`2026-2027:ef2f249d293f4fa888176ed0c109ffce:1:42` was available at
`2026-09-21T15:40:52.900223+00:00`. The target is valid for evaluation but is not
in that origin's input observations.

## Artifacts and reproduction

Final audit: `artifacts/audits/step2e_fd1de6dc316e133d/`, containing
`manifest.json`, `quality.json`, `provenance_trace.json`, and `COMPLETE.json`.
An earlier development run remains untouched at `step2e_81cdd29aae7c4fed/`;
use the final audit above. Both are generated, gitignored artifacts.

The manifest contains one record per player/origin. Quality includes counts and
explicit non-ready IDs/reasons. The trace shows player 1 across all six origins,
with separate input/target provenance and earliest capture diagnostics. The audit
ID hashes deterministic report contents and source evidence. Files use exclusive
creation; the hash-bearing completion marker is written last. An existing output
directory or protected raw/report location cannot be overwritten.

```bash
.venv/bin/python scripts/audit_replay_readiness.py \
  --reports \
    artifacts/audits/step2c_8c9e6040dee04f6dbdd83e7ae747929d \
    artifacts/audits/step2c_ef2f249d293f4fa888176ed0c109ffce \
  --events 1 2 3 4 5 6 \
  --output-root /tmp/fpl-step2e-reproduction

.venv/bin/python -m pytest -q
```

Regression coverage includes post-deadline exclusion, future-snapshot invariance,
late final targets, target-only conflicts/quarantine, inclusive boundaries,
timezone validation, equivalent/conflicting ties, missing/empty histories,
provisional history, changed deadlines, unresolved team/blank context, multiple
fixtures, rescheduled target identity, source verification, deterministic
read-only artifact output, and synthetic prospective readiness.

## Remaining limits and Step 2F recommendation

These captures cannot support leakage-safe inputs for GWs1–4. No later download
can backfill those missing historical availability proofs. Historical final
targets are useful, but do not make a historical origin replayable. Coverage is
only six players; freshness, transfer/registration history, revised-deadline
origin policy and blank/postponed schedule interpretation remain unresolved.

For **Step 2F**, validate a bounded prospective capture-to-replay cycle for these
same six players: explicitly capture official context/history before a verified
deadline, freeze its input-reference manifest, then attach later official final
targets and assert that the frozen input section is unchanged. Include a
reviewable policy for deadline revisions and capture freshness, and record
unresolved schedule/membership cases without inferred DNPs. Keep it official-FPL
only; do not expand the player sample or introduce models/features yet.
This recommendation is not implemented by Step 2E.
