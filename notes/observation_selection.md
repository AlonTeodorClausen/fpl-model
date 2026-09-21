# Step 2D — observation selection and completeness auditing

This stage is official-FPL-only and offline. It reads the two immutable Step 2C sample reports and their verified raw snapshots, preserves every version, and produces diagnostic artifacts. It does not fetch new data, expand the six-player sample, join Core, compute features, train models or implement an optimizer.

## Two distinct questions and APIs

**As-of information selection:** what captured version was available at the requested cutoff?

```python
select_as_of(
    observations, season="2026-2027", player_id=1, fixture_id=36,
    cutoff_at="2026-09-14T15:00:00Z",
    allowed_states={"provisional", "final"},
)
```

The rule is **`available_at <= cutoff_at`**, including exact equality. The cutoff and observation timestamps must carry a timezone; comparisons normalize offsets to UTC. Selection is season/player/fixture scoped. Future records are discarded using their availability before inspecting their state, values, provenance or conflicts. Adding a later observation—including conflicting later versions—cannot change an earlier as-of result.

Only accepted official `provisional` and `final` states can be allowed; the set must be nonempty. The latest eligible allowed observation wins, subject to conflict rules below. A `final`-only query may return an older final while a newer provisional exists: this is an explicit state filter, not a claim the older version is the latest source observation.

This inclusive rule supersedes the earlier Step 2B/2C proposal of strict `<` **for the new Step 2D selector**. The legacy `ObservationTime.eligible_at` helper is unchanged and is not called by this selector. Callers needing Step 2D semantics must use this API rather than interchange the two policies.

**Outcome selection:** what is the latest captured final official outcome for the pair?

```python
select_outcome(
    observations, season="2026-2027", player_id=1, fixture_id=36,
    outcome_cutoff_at=None,
)
```

Only `final` observations qualify. There is deliberately no `forecast_origin_at` argument. A final outcome may be retrieved after a pre-match forecast origin: it is the target, not the historical input. An optional `outcome_cutoff_at` freezes a target-vintage evaluation, using an inclusive bound; it must not be confused with a feature/forecast cutoff. Without it, selection considers all supplied captured versions, not an implicit wall-clock “now.”

Results have different purposes: `as_of_information` versus **`outcome_only`**. `Selection.for_information()` accepts only a selected as-of result, revalidates its provenance/time bound, and returns a detached copy. It rejects outcome-only results even when their observation happens to precede some later date. Selection wrappers are not valid raw observation inputs. This is an explicit interface guard, not a security boundary against callers deliberately rebuilding dictionaries; future input consumers must use the information API and accessor. No feature consumer is implemented here.

## Input and output contracts

Selectors consume the accepted normalized Step 2C observation format, not arbitrary unvalidated source rows. The audit loader verifies each report's COMPLETE marker and file hashes, verifies the raw snapshot and manifest hash, then reproduces its normalization to confirm identities, values and completion states. No report or source file is rewritten.

At the reusable selector boundary, validation checks official source, season, positive canonical player/fixture/team IDs, version identity, correspondence to `official_history`, timezone awareness, and raw provenance hashes/paths. `retrieved_at` and every context availability must be no later than the row's `available_at`. Invalid eligible data are rejected rather than backdated or coerced. A timestamp whose timezone is missing cannot be ordered and is rejected; it is not guessed to be UTC.

The version key is `(season, source_snapshot_id, player_id, fixture_id)` encoded by `observation_id`. Output contains status, purpose, selected observation or null, normalized cutoff, eligible version references, explicit duplicates, equivalent ties and conflict issues. Returned selected rows are copies; neither selection nor transition auditing mutates input observations.

| Selection status | Meaning |
|---|---|
| `selected` | One eligible allowed version chosen under the public policy. |
| `no_eligible_observation` | No captured matching observation is available at the as-of cutoff. Does not mean the player did not play, or that the official API never had a row. |
| `no_allowed_state` | Available observations exist, but none has an allowed as-of state. |
| `no_final_observation` | No final outcome qualifies. The completeness audit separately distinguishes provisional, absent, unresolved and quarantined contexts. |
| `conflict` | Eligible versions contain conflicting same-version records or differing equal-availability values. No value is selected. |

Quarantined/unusable rows are never selectable accepted labels. They remain in the separate quarantine input and completeness output; malformed quarantine records whose fixture cannot be identified remain unassigned rather than being given a guessed pair.

## Deterministic duplicate, tie and conflict policy

Conflict checks run on all time-eligible accepted observations for the pair **before filtering allowed states**. A state filter cannot hide a contradiction in the same observation version. Any such eligible conflict blocks the pair, even if a later unambiguous version also exists; manual review is required rather than silently choosing a convenient version.

1. Identical repeated copies of a version may be deduplicated for selection, but are explicitly listed in `duplicate_versions` with copy counts. They are not silently discarded.
2. Different content or provenance for the same version is a `same_version_conflict`, regardless of purported ordering.
3. Different semantic values or states at the same availability instant are an `equal_availability_conflict`. No hash, run ID or input ordering resolves a disagreement in value.
4. Equal-time versions with equivalent semantic content may be ranked by the maximum tuple: **availability, retrieval time, source snapshot ID, sorted `(raw relative path, SHA-256)` provenance pairs, observation ID**. All tied candidates are recorded in `tie_versions`. This is a deterministic administrative choice, not evidence that one equivalent source was more correct.
5. Different values at genuinely different availability times are auditable official revisions, not conflicts merely because they changed. For final targets, the latest eligible final is selected and all eligible final references remain visible.

UTC instants, not timestamp string ordering or dataframe row ordering, determine chronology. Same-time equivalent transitions have only the administrative provenance order; they do not establish causal chronology. The real sample has no such ties or conflicts.

## Completeness and expected fixture context

Completeness accepts an explicit requested player/fixture universe with expectation evidence or an unresolved reason. It reports two independent dimensions:

| Dimension | Values |
|---|---|
| Label/coverage classification | `final`, `provisional`, `missing_observation`, `quarantined`, `unresolved_expectation`, `not_applicable`, `conflicting_observations` |
| Appearance | `explicit_zero`, `positive_minutes`, `unknown` |

A final zero-minute row is **final + explicit_zero**. A provisional zero-minute row is **provisional + explicit_zero** and remains in diagnostic evidence, but the outcome selection remains `no_final_observation`. Absence is never converted to zero minutes or DNP. Counts and each affected player/fixture ID are included in the artifact. Categories absent from a counts dictionary have zero cases in its explicitly enumerated universe; this does not assert zero missingness outside the universe.

`missing_observation` requires an independently justified expected pair with no eligible accepted/quarantined record. Otherwise absence is `unresolved_expectation`. Caller-supplied expectations/not-applicable claims require explicit evidence; the official context helper automatically creates neither historical membership intervals nor `not_applicable` claims. Its observed expectation availability is checked against historical audit cutoffs. Missing-row, quarantine and explicit expectation tests use synthetic contracts and are not claimed as observed live omissions.

A quarantine record at least as recent as the selected accepted version makes the completeness classification `quarantined`; older accepted provenance can remain visible for diagnosis. Older quarantine records remain listed even after a newer accepted version. The standalone selectors operate on accepted records; callers must also inspect the completeness gate rather than assuming that any selectable historical final clears a newer quarantine.

### What establishes an expected pair

The helper validates official players, teams and fixtures and accepts a known official history row as evidence **only for its exact player-fixture pair**. Fixture-side team identity must be compatible. An explicit official DNP row also establishes that observed pair; it does not prove a played appearance.

Current bootstrap team membership, or an appearance for a club at another date, does not establish historical registration for every fixture played by that club. There is no fuzzy matching, all-clubs expansion, inferred transfer date or assignment to both clubs' entire seasons. If official context is unavailable by a historical cutoff, expectation is unresolved. Future history cannot establish past expectation.

This conservative helper cannot certify full roster/appearance completeness from the sample alone. Many requested pairs remain unresolved even when most would intuitively be non-applicable; that is intentional. Verified dated registration/eligibility evidence would be needed to classify them safely.

## Transition audit

Each successive unambiguous pair of observation versions records:

- season, player ID and fixture ID;
- earlier/later snapshot IDs and availability timestamps;
- earlier/later label states;
- changed original fields, including separate presence flags so absent and null differ;
- classification: `official_revision`, `state_transition` or `unchanged`.

Historical team context is included alongside original FPL fields. Source/processing metadata changes alone are not statistic revisions. Both old and new values remain referenced. Legitimate changes at different times do not become error flags. Conflicted version groups are reported as issues rather than assigned a guessed transition.

## Real sample audit and reproduction

Inputs, unchanged:

- `artifacts/audits/step2c_8c9e6040dee04f6dbdd83e7ae747929d/` — September 14 observation.
- `artifacts/audits/step2c_ef2f249d293f4fa888176ed0c109ffce/` — September 21 observation.

Six players: **1, 2, 5, 12, 26, 439**. No network requests were made.

```bash
.venv/bin/python scripts/audit_observations.py \
  --reports \
    artifacts/audits/step2c_8c9e6040dee04f6dbdd83e7ae747929d \
    artifacts/audits/step2c_ef2f249d293f4fa888176ed0c109ffce \
  --cutoff-at 2026-09-14T15:00:00Z \
  --events 1 2 3 4 5 \
  --output-root /tmp/fpl-step2d-reproduction
```

The generated versioned audit is `artifacts/audits/step2d_10b18c9e11272c88/`, containing `quality.json`, `transitions.json` and a hash-bearing `COMPLETE.json` written last. Existing destinations and protected input locations cannot be overwritten. The audit ID derives deterministically from the versioned audit contract, source references/hashes, cutoff and requested events. Input report ordering does not change the output.

The requested completeness scope is **six players × 50 official GW1–5 fixtures = 300 candidate pairs**. Those 300 are a retrospective audit scope, not a claim that every player should have a label for every fixture. The fixture list and illustrative deadlines come from the latest captured official schedule and must not be reused as proof of historical schedule knowledge. Historical expectation evidence is separately filtered by cutoff.

There are **54 captured observations of 30 unique player-fixtures**: 24 pairs have two observations, and six pairs have one. All 30 observed pairs are kept in selection examples and transition inventory; the CLI event list bounds the completeness fixture universe rather than discarding captured history.

| Result | As-of September 14, 15:00 UTC | Latest final outcomes |
|---|---:|---:|
| Final pairs | 18 | 30 |
| Provisional pairs | 6 | 0 |
| Unresolved expectation | 276 | 270 |
| Justified expected-but-missing pairs | 0 | 0 |
| Quarantined / conflicting pairs | 0 / 0 | 0 / 0 |
| Explicit zero-minute observations | 7 | 9 |
| Positive-minute observations | 17 | 21 |

At the as-of cutoff, 24 of the 30 observed pair examples select a version; six return `no_eligible_observation`. The six later GW5 rows cannot enter the September 14 information state. The absence of known missing/quarantined cases in this sample does **not** establish complete coverage of the unobserved 270–276 candidate pairs.

There are **six provisional→final transitions**, all from the September 14 snapshot to September 21:

| Player ID | Fixture ID | Changed original fields |
|---:|---:|---|
| 1 | 36 | creativity, influence, ict_index |
| 2 | 36 | None; state changed only |
| 5 | 36 | creativity, influence, ict_index |
| 12 | 36 | creativity, influence, threat, ict_index |
| 26 | 36 | creativity, influence, threat, ict_index |
| 439 | 39 | creativity, influence, threat, ict_index |

Five pairs therefore contain legitimate official field revisions. The other 18 transitions are final→final with unchanged original values. There are no conflict issues or source quarantine rows. The machine-readable transition file contains each exact old/new value and timestamp.

For all **30 illustrative pre-match event-deadline queries**, the as-of selector returns no eligible player-fixture outcome, while the outcome selector can select a final label. Example: player 1, fixture 36, observed deadline `2026-09-12T12:30:00Z`; the final target was observed on September 21 and is valid for outcome use, not input use at that earlier origin. The deadline examples are explicitly retrospective because the true pre-deadline schedule version was not captured here.

## Leakage and regression coverage

Tests enforce inclusive equality and equivalent UTC offsets; timezone-aware cutoffs, retrieval and availability; exclusion of after-cutoff observations; invariance when future valid or conflicting snapshots are appended; target-only finals after forecast origin; rejection of outcome results by the information accessor; retention of earlier provisional versions; permitted state filters without hidden conflicts; latest-final revisions; same-version/equal-time conflicts independent of ordering; explicit equivalent ties/duplicates; source and context availability; separate zero/provisional/missing/quarantine states; no inferred transfer tenure; and future expectation evidence exclusion.

Artifact tests use synthetic captured snapshots, verify deterministic report bytes and reversed-input invariance, reject corruption/duplicate report inputs, and ensure earlier files remain unchanged. Real report reproduction verifies source hashes and normalized content before auditing; the full audit deliberately examines both source vintages for diagnostics and outcomes, while the reusable as-of selector never inspects future payload values.

Verification: `.venv/bin/python -m pytest -q` completed with **496 passed, 5 deselected in 2.38s** (20 Step 2D tests). The live tests were excluded. Reversing report/event input order preserved the audit; a fresh output directory reproduced all three artifact files byte-for-byte and their completion hashes verified. All 71 protected raw/Step 2A/2B/2C files retained their hashes. Generated Step 2D artifacts remain gitignored and untracked.

## Remaining limitations and recommendation for Step 2E

Historical membership, live DGW/rescheduling/transfer coverage, independently archived publication times and truly pre-deadline source versions are still incomplete. Equal-time conflicting values require review; no automatic reconciliation exists. Final labels remain versioned because official corrections can occur. Low-level selector callers must supply verified normalized observations; the audit loader supplies that verification boundary.

**Recommended Step 2E:** a bounded prospective replay/readiness manifest for these same six players. Record explicit forecast origins and references to source versions captured by each origin, keep final-outcome references in a separate target section, and gate readiness on missing/quarantined/unresolved cases. Validate the separation with one prospectively captured GW when authorized, without inventing historical snapshots. Establish input coverage before features, models, full-player expansion or Core enrichment. No Step 2E functionality is implemented here.
