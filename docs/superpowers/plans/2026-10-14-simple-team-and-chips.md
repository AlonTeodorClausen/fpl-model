# Simple Team View and Manual Chips Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give the user one standard forecast and correct, manually scheduled support for all four chips in the existing 1–4-GW team workflow.

**Architecture:** Keep player forecasts unchanged. Introduce shared chip rules and permanent-versus-active squad state in the existing sequence optimizer, then apply the same chip semantics in lineup selection and held-out evaluation. Move experimental controls off the main page while preserving existing reports and local profiles.

**Tech Stack:** Existing Python, NumPy, SciPy MILP, Streamlit and pytest; no new dependencies.

**Spec:** `docs/superpowers/specs/2026-10-14-simple-team-and-chips-design.md` (approved by user).

## Global Constraints

- Standardprognose uses `component_baseline_v1`, unchanged configuration, all experiments off.
- First delivery retains 1–4 consecutive GWs. Automatic chip placement and planning through GW19 remain later work.
- No new downloads, model components, parameter changes, snapshot changes or ignore-rule changes.
- Preserve existing local teams, raw data, reports and unrelated working-tree changes.
- Unknown chip status is not available. No guessing pre-transfer ownership, money, FT or existing hits.
- Fixed future prices; actual selling values; one chip per GW; explicit 2026/27 rules.
- Forecasts shared across proposals; planning scenarios remain separate from evaluation scenarios.
- Existing no-chip calls retain their behavior. Old reports remain readable without migration writes.
- Never stage whole directories: much of this project's approved earlier work is still untracked. Task checkpoints must contain only deliberately reviewed work; do not sweep that work into chip commits.

## Review Focus

- A Free Hit retaining an owned player must not charge a buy/sell spread for that retained player (Task 3).
- An already active chip is binding: a no-chip result is hypothetical, not an available recommendation (Tasks 1, 4, 5).
- Reopening a report or changing a chip must not reuse a stale lineup or silently relabel an old model (Tasks 2, 4, 5).
- Two first-half chips cannot be scheduled in the same GW, and FH19/FH20 is illegal across the reset (Task 1).
- A publicly imported team does not establish complete chip history or pre-transfer state; missing information must remain visible (Tasks 1, 5).

## Files and responsibilities

- New `src/fpl_model/chips.py`: validated chip inventory/schedule and pure state/accounting rules.
- Existing `my_team.py`: optional local profile extensions, backwards-compatible validation and persistence.
- Existing `optimizer/squad.py`, `optimizer/lineup.py`: chip-aware scoring and exact fixed-squad lineup search.
- Existing `optimizer/transfer_sequences.py`: chip-aware MILP, independent state replay and terminal state.
- Existing `sequence_planner.py`: paired chip/no-chip alternatives, reports and sensitivity.
- New `ui/chips.py`: inventory, pre-transfer confirmation and manual GW schedule controls.
- New `ui/forecast_controls.py`: extracted experimental controls; standard configuration helper.
- Existing `ui/my_team.py`, `ui/experiments.py`: main/analysis presentation and orchestration.
- Existing tests extended plus new `tests/test_chips.py`, `tests/test_chip_sequences.py`, `tests/test_chip_app.py`.
- New `notes/chips.md`, small README update: actual behavior, limitations and local usage.

## Task 1: Chip contract and safe local profiles

**Interfaces:** Add `normalize_chip_inventory(profile: dict) -> dict`, `validate_chip_plan(plan: dict[int, str], profile: dict, events: list[int], *, deadlines: dict[int, str], origin_at: str) -> dict[int, str]`, `chip_transfer_account(free: int, count: int, chip: str | None) -> dict` and `resolve_chip_origin(profile: dict, first_chip: str | None) -> dict` in `chips.py`.

Chip names: `wildcard`, `free_hit`, `triple_captain`, `bench_boost`. Normalize integer GW keys after JSON loading. Optional `profile['chip_inventory']` has version 1, matching season, `entry_start_event`, `active_chip` (event/name or null), and `halves` with keys `first`/`second`; each chip stores status, used_event, source and confirmed_at. Missing fields normalize in memory to unknown; no load-time writes. Optional `profile['pre_transfer_state']` carries players with selling prices, bank, free_transfers, existing_hits, event and confirmed_at. Never recursively embed a profile.

- [ ] Add failing tests in `test_chips.py` and extend `test_my_team.py`: old profiles load unchanged, unknown chips block only chip selection, wrong season/repeated chip/expired deadline/first-GW WC or FH fail, used chip cannot be reused, active chip cannot be changed, FH19/FH20 fails including recorded previous use.
- [ ] Pin arithmetic with `assert chip_transfer_account(3, 8, 'wildcard') == dict(used=0, remaining=3, next_gw=3, hits=0)` and the same for FH; normal/TC/BB with free=1,count=2 yields used=1,remaining=0,next_gw=1,hits=4. Non-integer/negative counts fail.
- [ ] Run `.venv/bin/python -m pytest -q tests/test_chips.py tests/test_my_team.py` and confirm the new cases fail before implementation.
- [ ] Implement these interfaces and profile validation. Validate confirmed pre-transfer player IDs, values and season through existing identity checks. Require the confirmed pre-transfer state for first-GW WC/FH after prior moves, and reject contradictory active-chip data.
- [ ] Run the same tests; confirm pass and no mutation of input dictionaries or saved legacy files.
- [ ] Review the exact task diff and checkpoint only its reviewed changes; retain unrelated pre-existing work.

## Task 2: Scoring and lineup selection

**Interfaces:** Extend `evaluate_squad(team, rows, points, participated, *, chip=None)` and `optimize_lineup(squad, rows, points, played, *, chip=None)`. `refine_plan` obtains the chip from the matching step and adds it to cache keys; lineups retain a `chip` field. WC/FH use ordinary scoring.

- [ ] Extend `test_lineup_optimization.py` and scoring tests with TC playing/cameo/absent captain, absent vice and negative points. For a fixed lineup assert `tc['points'] == normal['points'] + normal['captain_bonus']` elementwise; TC captain_bonus reports both extra copies.
- [ ] Add BB cases: expected points equal all 15 participating players once plus ordinary captain bonus. Assert a reserve replacing a DNP is never counted twice. Unknown chips fail. Compare chip-aware lineup results to a small brute-force scoring oracle; verify no-chip arrays remain identical.
- [ ] Run `.venv/bin/python -m pytest -q tests/test_lineup_optimization.py tests/test_prototype.py` and observe new failures.
- [ ] Implement TC bonus multiplier and BB all-squad scoring. Keep existing autosub path byte-for-byte for chip=None where practical. BB still requires legal XI and captain/vice; enumerate legal choices with deterministic ID tie-breaking. Report `bench_points` plus `bench_contribution_kind='bench_boost'` or `'autosubs'`.
- [ ] Add a cache regression: refine the same squad/event first without and then with TC/BB; each must match an uncached call and preserve distinct objectives. Bump lineup version without touching forecast simulation code.
- [ ] Run targeted tests to passing and checkpoint reviewed task changes.

## Task 3: Permanent and temporary squad state in the MILP

**Interfaces:** Extend `optimize_sequence(..., chip_plan=None, chip_context=None)`; `first_count=None` means unrestricted first-GW WC/FH relocation, and is invalid for ordinary first weeks. For non-empty chip_plan, require chip_context with `deadlines` and `origin_at` and validate eligibility using Task 1 before solver entry. Returned steps retain legacy fields and add chip, active_squad, permanent_squad_after, permanent_bank_after, original_lots_after, ordinary_count and relocation_count. Return `terminal_state` even for a final-week FH.

- [ ] Write `test_chip_sequences.py` using the small pools/profile helpers from existing transfer tests. Cover WC permanent changes, FH temporary changes and restoration, two chip weeks, FT preservation, ordinary limits excluding chip relocations, locks/exclusions and insufficient bank. No-chip output must match existing tests.
- [ ] Add the spread regression: an owned player costs 80 but sells for 70. Keeping that player in an FH must not consume an extra 10; selling them finances only 70. Selling and later rebuying permanently uses market cost and loses the old acquisition lot.
- [ ] Add FH in the last selected GW, followed by a synthetic next-GW state check: `terminal_state` retains the pre-FH permanent IDs, bank, original lots and FT. Add `max_per_gw=0,max_total=0` with a selected WC/FH to prove ordinary limits do not block relocation. Check active exclusions after FH restoration.
- [ ] Run `.venv/bin/python -m pytest -q tests/test_chip_sequences.py tests/test_transfer_sequences.py` and confirm the new cases fail.
- [ ] Extend the existing MILP with permanent membership/lot/bank variables and active membership. Normal/WC weeks link active and permanent membership. FH weeks freeze permanent membership, acquisition lots and bank; optimize active membership separately. Use retention indicators when valuing temporary owned players so only actual changes incur the purchase/sale spread. FT edges use Task 1 rules; count only ordinary moves against ordinary limits.
- [ ] Use TC doubled captain coefficient and BB full-squad value in candidate objectives; leave other chip-week score terms ordinary. After solving, independently replay buy/sell/restore/cash/FT using Task 1 accounting; reject any discrepancy with solver state. Do not trust optimizer membership alone as cash validation.
- [ ] Run targeted tests including all legacy transfer tests and checkpoint reviewed changes. Preserve solver time-limit/gap reporting; do not claim globally optimal autosub-aware squads.

## Task 4: Paired plans and report contract

**Interfaces:** Extend `compare_sequences(..., chip_plan=None)` and preserve chip_plan in config for `compare_sensitivity`. Derive optimizer chip_context from bundle metadata `deadlines` and `forecast_origin_at`, never wall-clock time on replay. `packages` contains the hold reference, ordinary alternatives and chip alternatives; IDs are `hold`, existing `first_N`, and `chip_first_N` or `chip_rebuild`. Add `comparison_family`, `hypothetical`, `gain_vs_best_no_chip` and `terminal_state` to applicable results. Recommendation may never select a hypothetical plan.

- [ ] Extend `test_sequence_planner.py`: same bundle object/scenarios in every family, no forecast recomputation, selected chips actually applied, empty chip_plan preserves output semantics, FH/WC in first GW yields one rebuild candidate, unavailable candidates have explicit reasons.
- [ ] Test binding active chip: no-chip reference may be shown but `recommendation.plan_id` cannot refer to it. Pin existing-hit accounting: no-chip totals subtract confirmed already-incurred hits plus new hits; WC/FH cancels the confirmed first-GW historical hits. Report existing_hits/new_hits separately to avoid presenting sunk costs as new transfer costs.
- [ ] Run `.venv/bin/python -m pytest -q tests/test_sequence_planner.py tests/test_chip_sequences.py` and observe new failures.
- [ ] Route chip steps through scoring and lineup refinement. Preserve no-chip hold as reference, evaluate ordinary/chip families on paired held-out draws and recommend by planning objective. Label improvement over the best found no-chip plan as conditional on this horizon/search, not proven chip value. Carry inventory/pre-transfer provenance into reports and code hashes.
- [ ] Round-trip reports through JSON, test sensitivity with the same chip schedule and verify old reports without chip fields still render. Run targeted tests and checkpoint reviewed changes.

## Task 5: One standard forecast and manual chip controls

**Interfaces:** Add `standard_forecast_settings() -> dict` and `render_experimental_forecast_controls(data, events, labels, paths) -> dict` in `ui/forecast_controls.py`; returned keys match existing forecast_bundle keywords and source-loading settings. Add `render_chip_inventory(profile, data) -> dict` and `render_chip_schedule(profile, events, data, origin_at) -> dict[int,str]` in `ui/chips.py`.

- [ ] Add AppTest cases in `test_chip_app.py`: main page has Standardprognose and no model-experiment widgets; analyses expose the existing six model choices and bonus/prior/assist controls; data age and old saved model names remain correct.
- [ ] Test legacy profile -> unknown chip inventory -> manual confirmation -> save -> reload. Assert no network call and no profile write before Gem hold. Confirm unavailable chips cannot be scheduled, manual pre-transfer editor validates 15 players/money/FT, and an imported team's active-chip field does not silently imply complete chip history.
- [ ] Test profile change/import/reset clears stale chip widgets and scheduled chip results. Unknown status still allows ordinary transfers. An already-active chip is visibly binding; missing restoration state blocks only unsafe calculations.
- [ ] Run `.venv/bin/python -m pytest -q tests/test_chip_app.py tests/test_my_team_app.py tests/test_team_import_app.py` and confirm new tests fail.
- [ ] Extract experimental controls without duplicating their model configuration logic. Let the analysis page offer a transfer-experiment view using `render(experimental=True)`; main `render()` uses standard settings and no experiment controls. Namespace session/widget keys so analysis state cannot silently affect the main standard forecast.
- [ ] Add inventory and per-GW chip controls, with 1–4 GW scope shown clearly and official GW19 expiry. Use sequential planner for chip plans; if Alle transfers nu is selected, explain that chip scheduling requires Transfers uge for uge rather than silently changing behavior. Main transfer cache signature includes chip state/schedule and pre-transfer confirmation; forecast cache does not.
- [ ] Show active and restored FH troupes, WC permanent changes, FT/hits, conditional chip gain, XI/bench/captain/vice, planning objective and separate simulated points. Old reports use defaults and retain original model labels. Run targeted AppTests and checkpoint reviewed changes.

## Task 6: End-to-end verification and delivery

**Files:** `notes/chips.md`, `README.md`; minimal corrections to the above files only if verification identifies concrete failures.

- [ ] Document four chip semantics, manual status confirmation, prior-transfer requirements, fixed-price assumption, baseline default and the 1–4-GW boundary. Explicitly state no automatic GW19 scheduling or chip activation on the FPL account.
- [ ] Run `.venv/bin/python -m pytest -q`; preserve stdout and report actual counts. Do not reuse the old 775-pass count as evidence for changed code.
- [ ] Use existing local data to run one saved no-chip comparison and a manual chip comparison with identical forecasts. Use a separate test profile/output directory under the existing ignored artifacts root; do not overwrite the user's team. Inspect paired report references, FT, restoration and scoring. Cover remaining chip branches with deterministic offline fixtures; no new downloads required.
- [ ] Open the running Streamlit app: verify Standardprognose, chip inventory/schedule, explanations and one saved comparison. Check save/reload and the analysis page. Label synthetic checks distinctly from real player forecasts.
- [ ] Inspect exact changed files and staged contents for unrelated prior work, credentials and generated outputs. Checkpoint only reviewed source/tests/docs. Do not change ignore rules or upload raw captures/results. Report completion, tests, known limitations and exact usage; do not begin automatic GW19 planning.

## Plan self-review

Spec coverage: model separation (Task 5), inventory/deadlines/season rules (1,5), scoring (2), permanent/temporary money and ownership (3), comparable reports/cache/provenance (4), backward compatibility and UI workflow (1,4,5), verification and scope boundary (6). All five Review Focus cases have named regression coverage. No new forecast model, deadline hardcoding, chip auto-activation or long-horizon optimization is included.

Recommended execution: implement directly in this session, sequentially, because scoring, state transitions, planner and UI share the same interfaces. Review the final integration after tests; use separate implementation agents only if the user chooses that approach.

## Execution result — 2026-10-14

Tasks 1–6 implemented and verified: 803 offline tests passed, 5 live tests deselected.
Real saved data used for a GW7–8 smoke comparison (3000 scenarios, seed 42), with
hypothetical chip inventory explicitly labeled. Browser checked and app restarted.
Local code checkpoints remain in ignored artifacts/chip_implementation; no source
commit/push because affected dependencies contain earlier uncommitted work. All
existing working-tree changes, user profiles and snapshots preserved.
