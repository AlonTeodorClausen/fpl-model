# Step 2F-A — prospective six-player input freeze

**Phase A is implemented and tested offline. The first real prospective freeze
has not been run. The full prospective cycle is not validated. Phase B is not
implemented.** This workflow captures only official FPL data for players
**1, 2, 5, 12, 26, 439**. There is no player-expansion option, Core join, feature
calculation, model, xP or optimizer.

## Run shortly before the official deadline

From the repository root, use this command for the first planned **GW6** run:

```bash
.venv/bin/python scripts/freeze_forecast_origin.py \
  --season 2026-2027 \
  --event 6 \
  --max-input-age 30m \
  --raw-root data/raw \
  --report-root artifacts/audits \
  --freeze-root artifacts/freezes \
  --prior-report artifacts/audits/step2c_8c9e6040dee04f6dbdd83e7ae747929d \
  --prior-report artifacts/audits/step2c_ef2f249d293f4fa888176ed0c109ffce
```

The existing captures identify GW6's deadline as **2026-10-10 10:00 UTC**. This is
an existing observation, not a newly verified live date. The command fetches and
uses GW6's fresh official `deadline_time` at execution; it never substitutes this
document's date. Reconfirm the official deadline when planning the run.

The selected **operational policy for this first validation** is a maximum input
age of **30 minutes at forecast origin**. Start approximately **15–20 minutes
before the verified deadline**, allowing time for eight sequential requests,
normalization, validation and a fresh rerun if needed. Do not wait until the last
seconds. This is an operational choice, not an empirical or universal freshness
threshold; the general contract requires an explicit positive `--max-input-age`
in seconds, minutes or hours (`1800s`, `30m`, `1h`). There is no hidden default.

Running this command days early captures data but rejects the freeze as stale
at the origin. Running it at or after GW6's deadline rejects it as late. It does
not switch an explicit GW6 request to GW7. A rejected attempt is not a valid
Phase-A freeze.

For other runs, `--event next` selects the unique earliest future deadline in the
fresh bootstrap relative to **capture start**. The event is then fixed for that
run: crossing its deadline during downloads never rolls to a later event. Starting
an entirely new `next` command after a missed deadline intentionally selects the
next future event; pin an event ID for repeated attempts at the same origin, as
in the command above. There is no hardcoded calendar date in core logic.

## Workflow and failure behavior

The CLI creates one `SnapshotWriter`, captures bootstrap-static and fixtures,
then exactly six element-summary histories through the existing adapters. All
eight responses are required for this workflow. Exact response bytes and source
provenance are preserved. Existing adapter HTTP policy is unchanged: connect/read
timeouts of 10/30 seconds, no automatic retries or redirects. A retry is a new
snapshot/run, never a mix of old and new responses. Read timeout is an inactivity
timeout, not a guarantee of total command duration; publication checks the deadline.

After successful snapshot finalization, the workflow normalizes and writes a new
Step 2C report, verifies that report against raw data, and evaluates Step 2E
readiness using **only the fresh snapshot**. Step 2D's inclusive as-of selector
is used by readiness. Older reports/freezes contribute deadline evidence only.
There is no fallback to their bootstrap, schedule, histories or selected rows.

A fresh HTTP/transport failure preserves downloaded bodies and a failed raw run
under `data/raw/.staging/`; no freeze is created. A successful capture that fails
readiness, freshness or prospective timing produces an explicit `rejected`
attempt with reasons. A malformed global context or integrity error stops the
workflow without a valid freeze. No exception text, headers or credentials are
printed. Retain the fresh capture/report even when the attempt fails.

Exit codes:

- **0:** a verified ready Phase-A freeze was published.
- **2:** a completed attempt was published as rejected; inspect its reasons.
- **1:** capture, contract, integrity, filesystem or publication failure; no
  previous capture was substituted. Raw/report evidence remains where written.

The summary prints the selected event, UTC deadline, freeze path, status/reasons,
freshness policy/pass result, deadline-revision flag and `phase_b: not_started`.
Observed revision timestamps are printed if a revision was detected.

## Freeze contract and immutability

Each attempt receives a new `artifacts/freezes/step2fa_<UUID>/` directory, even
when the input versions are identical. `freeze.json` contains:

- versioned contract, phase, season, event, official origin UTC, capture start,
  freeze creation UTC, fresh snapshot ID and the fixed six player IDs;
- per-player readiness and unresolved/conflicted reasons;
- input-only relevant fixture IDs, observation IDs, source snapshot IDs,
  availability/retrieval timestamps and raw path/checksum provenance;
- checksum-addressed references to the immutable raw snapshot and normalized
  report, plus a canonical SHA-256 of the complete input-reference section;
- selected official deadline evidence, prior observed deadline versions and
  revision status;
- configured freshness maximum, each selected reference's age at origin and
  pass/fail, and a separate Phase-B handoff with no attached final results.

`COMPLETE.json` is written last using exclusive file creation and fsync. It
records the unique freeze ID, status, publication UTC and freeze/input hashes.
Directories/files are never overwritten or resumed. Interrupted publication
without a completion marker is invalid. Timing is checked during preparation,
before output creation and immediately before writing the completion marker.
`freeze_created_at` and the sampled publication time must be **strictly before**
the origin. Raw/as-of availability remains inclusive (`<= origin`), but a new
prospective freeze cannot be created exactly at the deadline.

As with raw snapshots, immutability is an API and hash-verification contract,
not a WORM filesystem or trusted external timestamp service. A correctly set
host clock is required. Keep the original freeze, raw snapshot and normalized
report available for later verification. The default verifier checks their
hashes and prospective timing; it rejects incomplete, changed or rejected
attempts. The inspect-only `require_ready=False` option can read rejection
records; it does not make them valid prospective freezes.

Manifest content is deterministic for identical input versions, explicit clock
timestamps, policy and deadline evidence, regardless of input record ordering.
Real reruns have new capture IDs and times; even publishing identical manifest
content twice creates distinct directories/marker IDs. A frozen manifest never
updates itself when later observations arrive. It describes the selected early
information set, not a claim that no further news arrived before the deadline.

## Provenance correctness and freshness are separate

Step 2E readiness remains unchanged: genuine pre-origin identity/deadline,
fixture context and captured player-history information are required. Provisional
history is allowed information; a captured empty history is valid but is never
interpreted as DNP. Missing/unknown/conflicted input context cannot yield ready.
Historical team membership and participation are not invented from the schedule.

The freeze adds two checks to readiness:

1. Every selected source/observation must belong to this fresh snapshot and must
   have been retrieved after capture started and be available by freeze creation.
2. For every required source reference and selected normalized observation,
   `age_at_origin = forecast_origin_at - available_at` must be nonnegative and
   no greater than the explicit configured maximum. Raw-context ages are checked
   independently, so a newer history response cannot mask stale context.

A stale but genuinely pre-origin record retains `readiness=ready` in the
provenance assessment, while the operational freeze is `rejected` with
`stale_inputs`. Ages and original timestamps are retained, never backdated or
replaced. Age concerns observation retrieval, not the date of the historical
match represented by a freshly downloaded history row.

## Deadline revisions

The current capture supplies the selected official deadline. Prior **completed**
attempts in the same freeze root and explicitly supplied verified `--prior-report`
reports contribute versioned deadline evidence. Keep the same freeze root across
reruns; moving to a new root requires explicitly supplying earlier report evidence.
Comparison is scoped to these verified inputs, not arbitrary files elsewhere.
Failed/incomplete capture responses remain raw diagnostic evidence but cannot
silently become accepted source inputs or completed freezes.

Different observed deadlines are preserved with each source snapshot/path/hash,
retrieval and availability. A revision is reported; the **new freeze explicitly
uses the fresh observation** and identifies it in `deadline.selected`. Equal-time
disagreement is a conflict and rejects the freeze. A deadline revised into the
past also fails prospective timing. A changed future deadline must still pass
freshness at that new origin.

This intentionally creates a new prospective origin version rather than changing
the older Step 2E audit origin or an existing freeze. The earlier deadline and
freeze remain intact. The workflow cannot detect an official revision that has
never been captured; a later run can report it, but must not rewrite old evidence.

## Phase-B handoff, not Phase-B implementation

The handoff records the season and exact `(player_id, fixture_id)` schedule pairs,
the immutable input SHA-256, and `phase_b_status=not_started`. These pairs are
captured team schedule context, not proof that each player will participate.

Phase B can later verify the completion/manifest/input hashes and referenced raw
and normalized report checksums, fetch new official observations separately,
select final labels, and link them by these official IDs. It must preserve the
original input observation IDs/checksums exactly and report missing/unusable
results explicitly. A moved fixture, changed GW, deadline revision or transfer
requires review rather than a rewritten origin or guessed participation.

The Phase-A manifest contains no `targets`, outcome-selection results or future
result values. Input-only references are copied out of Step 2E's separate input
section; contaminated sections are rejected. Prior finalized match histories
available before origin remain legitimate inputs. Raw HTTP provenance's
`outcome: success` is transport metadata, not a final player outcome.

Read-only verification is available without implementing attachment:

```python
from fpl_model.forecast_freeze import verify_freeze
frozen = verify_freeze("artifacts/freezes/step2fa_<actual-run-id>")
assert frozen["status"] == "ready"
assert frozen["handoff"]["phase_b_status"] == "not_started"
```

For a plain Python invocation in this repository, set `PYTHONPATH=src`; the CLI
sets up its own import path. Use the actual returned directory, not the placeholder.

## Offline validation and outstanding real work

The offline tests use fake HTTP with the real adapters, writer, normalizer,
readiness selector and freeze publication/verification. They cover the exact
sample, before/at/after deadline, crossing the deadline during capture/publication,
freshness boundaries, stale-but-provenance-correct data, no fallback on fresh
failure, missing/quarantined/conflicted inputs, versioned revisions, deterministic
content, immutable reruns, target exclusion, and raw/report integrity checks.

Run `.venv/bin/python -m pytest -q` (live tests remain excluded).

Remaining real work: run the command in the selected operational window, retain
the resulting **ready** freeze, then undertake a separately approved Phase B
after final official outcomes become available. Network availability, correctly
set UTC clocks, unchanged access to the six canonical identities, sufficient
source coverage and a verified current deadline remain execution prerequisites.
No full-cycle validation is claimed here.
