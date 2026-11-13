# Failsafe — Response to Independent v1 Product Review (V01–V07)

This document answers the independent review titled *"Failsafe — Independent v1
Product Review."* Each finding is restated (paraphrased), then followed by the
exact change made, the file(s) touched, the commit that carried it, and how it
is verified. Nothing here is a feature change beyond what the review asked for.

**Branch:** `phase1-physics-preflight-extension` → PR
[getswipeapp/blender_physics_preflight#1](https://github.com/getswipeapp/blender_physics_preflight/pull/1)
**Review verdict being answered:** Product direction **PASS**; paid launch
**CONDITIONAL** on four required items (V01/V02, V03, V04/V07, V06). All four are
addressed and re-certified below.

---

## Summary table

| ID | Severity (as raised) | Short form | Status |
|----|----------------------|-----------|--------|
| **V01** | Required | Collapsed UNKNOWN/N-A rows borrowed a positive title | ✅ Fixed |
| **V02** | Required | Check #23 title asserted "unchanged" — knowledge it can't have | ✅ Fixed |
| **V03** | Required | Render check treated "UNKNOWN only" as "no problems" | ✅ Fixed |
| **V04** | Required | Render handler not proven on the background/farm path | ✅ Proven |
| **V05** | Medium | "non-blocking" wording overclaimed the handler's behaviour | ✅ Fixed |
| **V06** | Required | A stale success banner could survive a scan that errored | ✅ Fixed |
| **V07** | Required | New features not re-certified across supported versions | ✅ Re-certified |
| **V08** | High (2nd review) | Turning off warning *alerts* could falsely report "all clear" | ✅ Fixed + 4 regressions |

Plus the review's medium/accuracy notes: heuristic titles softened, guided-fix
made pin-aware and honest, every Explain line hedged, and the panel's
"read-only" claim scoped to the scan. All covered below. The second review's
packaging items (LICENSE in the ZIP, manifest URL, Bash 3.2, buyer docs) are in
the final section.

---

## V01 — Collapsed rows must never read as reassurance *(Required)*

**As raised:** when a finding row is collapsed, only its title shows. UNKNOWN and
N-A rows were borrowing the check's positive/neutral name, so a row with an amber
or blue dot could read like an all-clear.

**Fix:** titles are now **per status**. `engine.display_name(meta, status)`
resolves a distinct title for FAIL / WARNING / UNKNOWN / N-A / PASS, falling back
only to a *more severe* label, never to the positive one:

- FAIL → `name_bad` → `name`
- WARNING → `name_warn` → `name_bad` → `name`
- UNKNOWN → `name_unknown` → `name`
- N-A → `name_na` → `name`
- PASS → `name`

Every check now carries an explicit `name_bad` and, where it can land on
UNKNOWN/WARNING/N-A, an explicit `name_unknown` / `name_warn` / `name_na`.

**Files:** `failsafe/engine.py` (CheckMeta + `display_name`), `failsafe/checks_setup.py`,
`failsafe/checks_cache.py`, `failsafe/ui.py` (headers use `display_name`),
`failsafe/report.py`.
**Commits:** `f8b58ee` (status-aware titles), `9b26e68` (truthful per-status titles).
**Verified:** `tests/run_tests.py` → `title_tests()` asserts UNKNOWN/N-A never
reproduce the positive statement; live GUI confirmed the collapsed-row wording.

## V02 — Check #23 can't claim the timing is "unchanged" *(Required)*

**As raised:** #23's title read like "Frame rate/speed unchanged since bake,"
asserting a fact the add-on cannot verify. (Note: #23 **always** returns UNKNOWN —
it never returns PASS — so the real defect was the UNKNOWN title, not a false PASS.)

**Fix:** #23 UNKNOWN now reads **"Bake timing couldn't be confirmed"**
(`name_unknown`), and its WARNING variant reads "Playback speed may have changed
since bake." No title asserts the timing is unchanged.

**Files:** `failsafe/checks_cache.py` (#23).
**Commit:** `9b26e68`.
**Verified:** `title_tests()` asserts #23 never emits an "unchanged"/positive
title and only ever surfaces as UNKNOWN/WARNING; confirmed live in the panel.

## V03 — "UNKNOWN only" is not "no problems" *(Required)*

**As raised:** the check-before-render banner collapsed an all-UNKNOWN result to a
clean "no problems," hiding unverified items from anyone reading a render log.

**Fix:** the banner is now built by `render_banner(f, w, u, problem)`:
- any FAIL/WARNING → names them;
- no problems but `u > 0` → **"no confirmed problems, N unverified"**;
- only truly clean → "all clear."

The console **always prints the full counts** (`N FAIL, N WARNING, N UNKNOWN`)
on every render, so a headless/farm log shows the UNKNOWN count even with no
window open. The panel banner uses a neutral QUESTION icon (not a green tick)
whenever the text contains "unverified."

**Files:** `failsafe/handlers.py` (`render_banner`, `failsafe_render_init`),
`failsafe/ui.py` (banner icon logic).
**Commit:** `9b26e68`.
**Verified:** `render_check_tests()` asserts an UNKNOWN-only result is never
labelled "no problems"; the headless proof below prints the UNKNOWN count.

## V04 — Prove the handler on the background / farm path *(Required)*

**As raised:** the render_init handler was only shown working interactively; its
behaviour under `blender -b` (the render-farm path) was unproven.

**Fix / proof:** captured a fresh headless run on **Blender 5.2.3 LTS**, launched
`blender -b -P …` **without** `--factory-startup` so the installed extension loads
and its handler registers. Evidence committed at
`certification/results/render_handler_proof_5.2.3.log`; the exact scripts are at
`certification/render_proof/`. Result:

- **Clean scene:** `HANDLER_HOOKED=['failsafe_render_init']`, then
  `FAILSAFE render check: 0 FAIL, 0 WARNING, 0 UNKNOWN — all clear`, render completed.
- **Broken-cache scene (missing interior frame):** handler fired,
  `FAILSAFE render check: 3 FAIL, 1 WARNING, 1 UNKNOWN`, and it **named the exact
  missing frame (5)** in the log. The render **completed** — the check is
  non-cancelling by design.

**Files:** `certification/render_proof/render_handler_proof_clean.py`,
`certification/render_proof/render_handler_proof_broken.py`,
`certification/results/render_handler_proof_5.2.3.log`.
**Verified:** the committed log is a direct capture, not a transcript.

## V05 — "non-blocking" overclaimed the handler *(Medium)*

**As raised:** describing the check as "non-blocking" implied it runs async/off the
render thread; it is synchronous and simply never cancels the render.

**Fix:** wording corrected throughout to **"non-cancelling, not non-blocking."**
The `handlers.py` module docstring and the certification benchmark note both say
the check is synchronous and non-cancelling, and the panel text no longer implies
otherwise.

**Files:** `failsafe/handlers.py` (docstring), `certification/RUNTIME_CERTIFICATION.md`.
**Commit:** `9b26e68`.

## V06 — No stale success banner after a failed scan *(Required)*

**As raised:** if a scan raised partway through, a previously-shown success banner
could remain, implying a clean result that never completed.

**Fix:** `failsafe_render_init` sets a **"Render check running…"** banner *before*
running, and on any exception sets a **"Render check didn't finish"** banner — it
never leaves a success message standing after a failure, and it never cancels the
render.

**Files:** `failsafe/handlers.py` (`failsafe_render_init`).
**Commit:** `9b26e68`.
**Verified:** `render_check_tests()` covers the running/failed banner states.

## V07 — Re-certify the new features across versions *(Required)*

**As raised:** prior certification predated the v1 features; new behaviour must be
re-run, not assumed from the old matrix.

**Fix:** the suite (now **162 tests**, up from 128) was re-run green on all four
supported builds:

| Blender build | Result | Tests |
|---------------|--------|-------|
| 4.2.9 LTS | ✅ PASS (rc=0) | 162 / 0 |
| 4.5.9 LTS | ✅ PASS (rc=0) | 162 / 0 |
| 5.0.1 | ✅ PASS (rc=0) | 162 / 0 |
| 5.2.3 LTS | ✅ PASS (rc=0) | 162 / 0 |

New coverage: title truthfulness (UNKNOWN/N-A never borrow a positive statement),
render-banner honesty (UNKNOWN-only is never "no problems"), the render-check
read-only + warn-toggle behaviour, and the V08 regressions below.

**Files:** `certification/RUNTIME_CERTIFICATION.md` §0,
`certification/results/run_v1_{4.2,4.5,5.0,5.2}.log`.
**Commit:** `e0fef15` (re-run at 162 with the V08 fix).

## V08 — Turning off warning *alerts* must not fake "all clear" *(High — 2nd review)*

**As raised:** the "Also warn on warnings" preference (`include_warnings`)
controlled both whether warnings *escalate* to a prominent alert **and** whether
the scan counted as clean. A scene with **2 warnings, 0 fail, 0 unknown** and the
preference off reported **"Last render check: all clear."** That is a false clean
— exactly the thing Failsafe promises never to do.

**Root cause:** `run_render_check` passed its escalation flag into the banner, and
the banner used it (not the raw counts) to decide "clean." The console tail had
the same flaw (`" — all clear"` on the non-escalated path), and the panel icon
could show a green tick next to a warning-bearing banner.

**Fix — separate the *alert threshold* from the *factual summary*:**
- `render_banner(f, w, u)` no longer takes the escalation flag. It is clean only
  when `f == 0 and w == 0 and u == 0`; any fail/warning shows the counts; an
  UNKNOWN-only result is "no confirmed problems, N unverified." This is
  independent of `include_warnings`.
- The console tail on the non-escalated path is now truthful: it never prints
  "all clear" when warnings or unknowns were found.
- The panel icon reserves the green CHECKMARK for a genuinely clean banner;
  anything with warnings/unknowns gets a neutral mark, never a tick.
- `include_warnings` now only governs escalation (the loud console block + red
  panel state), as intended.

**Files:** `failsafe/handlers.py` (`render_banner`, `run_render_check`,
`failsafe_render_init` console tail), `failsafe/ui.py` (banner icon).
**Verified:** `tests/run_tests.py` → `render_check_tests()` adds four V08
regressions — warning-only and warning+UNKNOWN with `include_warnings=False` must
show the counts and never read as "all clear," and the banner must be identical
whether alerts are on or off. Suite re-run **162/162 on all four versions**.

---

## Accuracy / medium notes from the review

- **Heuristic titles softened** so a guess doesn't read as a verdict: #2 ("mass may
  need review"), #16 fill check, #20 *sampled*-cache gets its own WARNING title
  ("Cache is sampled, not every frame") distinct from the FAIL title, #22 portability.
  *(Files: `checks_setup.py`, `checks_cache.py`; commits `9b26e68`, `aa7ec78`.)*
- **Guided-fix is pin-aware and honest:** `FAILSAFE_OT_show_physics` selects the
  object and switches **one unpinned** Properties editor to the right tab; if it
  can't, it says so plainly ("Selected 'X' — open its settings manually") instead
  of pretending. *(Files: `operators.py`, `ui.py`; commit `aa7ec78`.)*
- **Every Explain line hedged** for physics accuracy — "can"/"may" rather than
  asserting a single cause/outcome. *(File: `help_text.py`; commit `aa7ec78`.)*
- **"Read-only" claim scoped to the scan:** panel text now reads "Read-only scan —
  your scene, caches and files are never changed," so it doesn't imply the nav
  buttons (which change selection) are read-only. *(File: `ui.py`; commit `672d991`.)*

---

## Second-review packaging fixes

| Item | Finding | Fix |
|------|---------|-----|
| **LICENSE in the ZIP** | GPL `LICENSE` was at the repo root but not inside `failsafe/`, so it wasn't in the buyer ZIP | Copied `LICENSE` into `failsafe/LICENSE`; it now ships in the package (verified in the rebuilt ZIP). |
| **Manifest website 404** | `blender_manifest.toml` pointed to `…/blender_failsafe` (404) | Now points to the real repo `…/blender_physics_preflight`. |
| **Bash 3.2 portability** | `tests/run_all_versions.sh` used a Bash-4 associative array (`declare -A`), which fails on macOS's default Bash 3.2 | Rewritten with an indexed array + indirect expansion; `bash -n` + a live run verified on Bash 3.2.57. |
| **Buyer docs on old name** | README + `launch/*` still said "Physics Preflight," with an untested version note (`4.2.23 / 4.5.15`) | Reconciled to **Failsafe**; versions corrected to the certified `4.2.9 / 4.5.9 / 5.0.1 / 5.2.3`; "tests pending" notes updated to "done (162/162)." |

Note on the reviewer's Bash remark: the item was in `tests/run_all_versions.sh`
(the release gate), not `certification/run_matrix.sh`; both are now 3.2-safe.

## Documented limitations carried forward (not regressions)

These remain **UNKNOWN**, not claimed as passing:

- **Windows** — no Windows host available here; paths use `os.path` /
  `bpy.path.abspath`, case-insensitive cache matching, `realpath`/`commonpath`
  portability checks, so support is *plausible but unproven*. Run
  `tests/run_tests.py` on Windows before claiming it.
- **Geometry-Nodes *disk* bake — guided-fix destination.** Point/cloth/fluid
  caches route to the Physics tab correctly; a GN disk bake's fix lives on the
  **Modifier** tab, but the finding record doesn't yet carry sim type, so the jump
  isn't specialised. Deferred to v1.1; the check itself already reports GN disk
  bakes honestly (UNKNOWN/FAIL, never a false PASS).

## Remaining commercial gates (owner's call, not code)

1. Final package verification (ZIP + SHA-256 manifest — included in this handoff).
2. **Truthful listing claims** — the store copy must say Failsafe *diagnoses*
   identifiable setup/cache issues; it does not *guarantee* a render. Keep the
   precise "scans don't change your scene/caches/files" wording.
3. Owner approval to publish.

---

*Generated as part of the v1 review-response handoff. No feature changes were made
beyond the items above; nothing has been published.*

---

## Addendum — Expanded release for independent re-review (2026-11-12)

After the V01–V08 fixes above were certified, a **feature round** was added to
reach (and pass) competitor parity. This is new scope, not a review response, and
is listed here so the package under review is self-describing. **The V01–V08
certified baseline in §0 of `RUNTIME_CERTIFICATION.md` is preserved unchanged;** a
new section (−1) certifies the expanded build.

**What was added**
- **3 new checks:** #24 cloud-synced cache folder, #25 orphaned cache files,
  #26 opt-in settings-baseline drift.
- **Headless CLI** (`failsafe/cli.py`): exit codes `0/1/2/3`, `--json`/`--text`.
- **Crash/hang-isolated batch** (`failsafe/batch.py`): `--batch <folder>` runs
  **each file in its own Blender subprocess with a per-file timeout** (`--timeout`),
  so a corrupt or hanging `.blend` is isolated to itself and the batch continues
  with every good file's result preserved. `--in-process` keeps the fast path.
- **JSON export** button and **per-sim cache disk-usage** in reports.
- **"Couldn't verify"** as the user-facing word for `UNKNOWN` (display-only; the
  JSON/CLI machine token stays `UNKNOWN`, asserted by the suite).
- **Save Baseline** (`failsafe/baseline.py`): the **only** write action, and it
  writes only an **external** `<blend>.failsafe-baseline.json` — never the `.blend`.

**Hardening in response to the review direction (items 2–5)**
- **Save Baseline — no auto-write, no silent overwrite.** It only ever writes on an
  explicit click; `save_baseline` raises unless `overwrite=True`, and the operator
  shows a confirm dialog before replacing an existing baseline (tested).
- **#26 false-PASS audit.** Changed object identity, missing settings, corrupt
  JSON, an **unknown schema**, and a baseline saved for a **different file** all
  report "Couldn't verify", never PASS (tested, incl. pure-helper guards).
- **Batch isolation (item 4).** Each file runs in its own subprocess with a
  timeout; crash / hang / corrupt / launch-failure are each isolated and recorded
  as a per-file error while clean files keep their results (tested with a fake
  subprocess runner so the failure modes are deterministic).
- **"Couldn't verify" always actionable.** Every UNKNOWN carries a reason and a
  next action (asserted across #26's branches), while JSON/CLI keep `UNKNOWN`.

**Trust rules held**
- Scans remain 100% read-only (asserted on all four versions). The baseline
  sidecar is the single opt-in write and never touches the `.blend`.
- No status was turned into a false PASS. #26 with no/corrupt/mismatched/foreign
  baseline reports "Couldn't verify"; a "settings unchanged" result is stated as
  *not* proof the bake itself is good. Packed-GN / memory cases stay
  "Couldn't verify"/N-A and are labelled a **Blender limitation, not the user's
  fault**, with no implication that saving or re-baking fixes them.

### Independent review of `f148524` — blockers R19–R25 resolved

Each was reproduced with a regression test, then fixed, without weakening the
read-only rule:

- **R19** — isolated batch rejects a nonzero subprocess exit **even when the child
  printed JSON** (print-then-segfault → error, never clean).
- **R20** — empty / no-`.blend` folder returns **exit 3** ("no .blend files
  found"), isolated and `--in-process`; never clean.
- **R21** — baseline identity is now `Object::System::SubName`; two particle
  systems on one object no longer collide, and any residual collision forces #26
  to "Couldn't verify", never PASS.
- **R22** — orphan match uses the full `(prefix, index)` identity, and an
  unreadable blendcache folder → #25 "Couldn't verify" (not a false clean).
- **R23** — `display_name` never borrows the positive title for UNKNOWN (exception
  path too); #24/#25/#26 carry truthful `name_unknown` headlines.
- **R24** — orphan ownership is gathered across **all scenes** in the `.blend`.
- **R25** — isolated batch JSON preserves per-file **findings incl. exact
  missing-frame messages**, not just summary counts.

### Re-review of `1ac88ba` — baseline false-PASS risks R26–R27 closed

- **R26 — cross-scene baseline identity.** Baseline identities are now
  **scene-qualified** (`Scene::Owner::System::SubName`, and
  `Scene::Scene::Rigid Body World`), and the baseline captures **every scene** in
  the `.blend`. The Rigid Body World (which shared one identity across scenes) is
  now per-scene, so scanning scene B never PASSes against scene A's baseline — a
  scene not in the baseline reports "Couldn't verify". Schema bumped to 3.
- **R27 — incomplete fingerprint + float rounding.** The cloth fingerprint now
  also tracks `pin_stiffness`, `vertex_group_mass`, the per-vertex-group stiffness
  groups, sewing force and shrink range. Float precision tightened **5 → 10 dp** so
  a small real change isn't hidden. #26's PASS wording now states the **tracked**
  settings are unchanged (a curated subset) — it never claims "all settings",
  honouring "never claim all settings are unchanged when only a subset was
  compared".

**Evidence**
- Headless suite **292/292 on 4.2.9 / 4.5.9 / 5.0.1 / 5.2.3** (rc=0 each);
  logs `certification/results/run_v6_{4.2,4.5,5.0,5.2}.log`. Includes a regression
  test for every blocker R19–R27.
- **Real multi-process batch proof** (Blender 5.2.3):
  `certification/results/real_batch_proof_5.2.3.log` — actual child processes: a
  good file scanned clean, a corrupt file isolated as an error with the good one
  preserved, and a genuinely hanging child **killed at a 3 s timeout**. This is the
  real end-to-end test the review asked for, not a simulation.
- CLI proof `certification/results/cli_proof_5.2.3.log` (exit 0 clean / 3 usage;
  JSON keeps `UNKNOWN`; text shows "Couldn't verify").
- Package `dist/failsafe-933ea17.zip` (commit `933ea17`); SHA-256 in `certification/RELEASE_SHA256SUMS.txt`.
- Feature matrix: `strategy/FEATURE_MATRIX.md` (consumer vs pipeline; vs competitors).

**Still open (owner's call / not claimed):** live-GUI re-test of the new Save
Baseline (incl. overwrite dialog) / Export JSON buttons; the separate
first-time-user usability test; Windows; a live GN *disk* bake.
