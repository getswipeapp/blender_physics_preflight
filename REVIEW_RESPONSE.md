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

Plus the review's medium/accuracy notes: heuristic titles softened, guided-fix
made pin-aware and honest, every Explain line hedged, and the panel's
"read-only" claim scoped to the scan. All covered below.

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

**Fix:** the suite (now **158 tests**, up from 128) was re-run green on all four
supported builds:

| Blender build | Result | Tests |
|---------------|--------|-------|
| 4.2.9 LTS | ✅ PASS (rc=0) | 158 / 0 |
| 4.5.9 LTS | ✅ PASS (rc=0) | 158 / 0 |
| 5.0.1 | ✅ PASS (rc=0) | 158 / 0 |
| 5.2.3 LTS | ✅ PASS (rc=0) | 158 / 0 |

New coverage: title truthfulness (UNKNOWN/N-A never borrow a positive statement),
render-banner honesty (UNKNOWN-only is never "no problems"), and the render-check
read-only + warn-toggle behaviour.

**Files:** `certification/RUNTIME_CERTIFICATION.md` §0,
`certification/results/run_v1_{4.2,4.5,5.0,5.2}.log`.
**Commit:** `e0fef15`.

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
