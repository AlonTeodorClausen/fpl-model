# Daily-use stabilization

> Execute the two independent tasks with scoped subagents, preserve existing work, then review and verify their combined result.

**Goal:** Use the latest usable local official inputs by default and report honest point-reference uncertainty.

**Architecture:** Keep Streamlit, immutable captures, existing history/context loading, readiness checks and stored forecast evaluation. No model changes or downloads. Normal team use follows usable local data; explicit historical selection remains available for investigation.

**Tech Stack:** Existing Python, Streamlit and pytest.

**Spec:** User approved acting on the project review, with subagents on different models. This implements the bounded stabilization part of recommendations 1–2. Background capture/resume and a model-comparison dashboard are deferred.

## Global constraints

- Preserve all pre-existing working-tree changes, profiles, snapshots and reports. Work in the current checkout because the running app depends on those changes.
- No network data capture, simulation/model changes, automatic tuning, dependency changes, commits or pushes in this task.
- No edits to raw files or old generated evaluations. Write corrected evaluations as new artifacts.
- Retain guest publication pinning and isolation. Local latest-data behavior must not leak into guest mode.
- Main handles README/notes and combined verification; agents edit only their owned files.

## Review focus

1. A retained older session selection must not silently govern the normal latest-data mode.
2. New context with a compatible earlier complete history should retain distinct provenance; partial/corrupt/missing data must stay visible and cannot bypass readiness.
3. Explicit historical selection must remain stable and visibly marked; saved forecasts retain their original dates.
4. Point-reference intervals and CRPS must be absent without a predictive distribution; model intervals stay unchanged.
5. Legacy generated reviews must not be reused as corrected reviews simply because input hashes match.

### Task 1: Honest point-reference metrics (Luna)

**Files:** `daily_forecast_review.py`, `prediction_evaluation.py`, `ui/forecast_review.py`, associated evaluation tests.

- [x] Add regression tests that reproduce copied model quantiles in the simple reference.
- [x] Set reference quantiles to unavailable and make interval metrics handle unavailable quantiles, retaining model intervals and point/minute/DNP errors.
- [x] Version the corrected daily evaluation; prevent automatic reuse of old daily results while keeping them unchanged on disk. Use a small shared version constant if appropriate.
- [x] Test old/current evaluation selection and mixed/missing intervals. Run focused tests.

### Task 2: Latest usable data as the ordinary workflow (Sol)

**Files:** `ui/my_team.py`, a small data-selection helper if needed, `quick_refresh.py`/`prototype_data.py` only as necessary, associated tests.

- [x] Reproduce stale-session selection and newest context/history combinations in offline tests.
- [x] Normal local mode chooses latest usable local input pair; expose historical selection inside an advanced expander with explicit historical label.
- [x] Changing available local data updates the normal selection on rerun without downloads. Preserve bank, squad, chip choices and original reports.
- [x] Preserve explicit refresh success selection, latest context/history timestamps, limited-readiness acknowledgement and guest active-publication behavior.
- [x] Display a clear explanation when a newer candidate is unusable; do not mislabel an older selection as freshly fetched.
- [x] Run focused tests, including normal/experimental modes, invalid/partial inputs and guest behavior.

### Integration and delivery (main)

- [x] Review agent changes and run full offline suite.
- [x] Generate one corrected after-round artifact from the existing GW8–11 report and existing outcomes; compare point metrics and unchanged originals.
- [x] Verify actual app rendering without downloads or new simulations.
- [x] Update concise existing documentation and report behavior, verification, limitations and next step.

**Execution ruling:** Existing user changes make a fresh base-branch worktree unsuitable. Scoped file ownership and before/after copies in ignored artifacts provide review isolation without discarding work or changing ignore rules.

## Completion — 10 November 2026

Implemented and reviewed with scoped Sol/Luna agents and an independent Astra review. Two review findings were fixed with regressions: unsaved editor state on automatic price changes, and a newer context masking an intervening partial history capture. A small CSS correction makes the advanced sidebar controls readable.

Verification: `.venv/bin/python -m pytest -q` — **935 passed, 5 deselected in 126.48s**. The 59-test input-selection suite and three independent review regressions also pass. Existing corrected v3 review renders without network calls; its 1,186 comparison rows retain the original point/minute/DNP metrics. Original report/profile hashes are unchanged. Browser checked on the running local app: latest-local mode, explicit historical controls, original capture times and stale-data warning all visible. No downloads or production simulations; no commit or push.
