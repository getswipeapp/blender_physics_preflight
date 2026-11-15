# Failsafe — Store Gallery (real, reproducible captures · build `dfda2f7`)

> **DRAFT — not published.** Genuine screenshots of the real add-on on a real,
> **reproducible** scene. No mockups, no fabricated UI, no fabricated results, no
> edited findings (a selling rule from the launch brief). **Cropping and
> downscale only — no pixel, text, count or finding was altered.**

> **Build:** all six images were captured live from the verified build `dfda2f7`
> (extension `bl_ext.user_default.failsafe`, installed from
> `dist/failsafe-dfda2f7.zip`) in **Blender 5.2.3 LTS** on macOS. They replace the
> prior-build images (which showed check **#23** as a blue "couldn't verify" and a
> tally of 3 / 1 / 1). On this build #23 is a real **frame-rate timing baseline**
> check (unchanged → PASS, changed → WARNING), so the saved demo now scans
> **3 fail · 1 warning · 0 couldn't verify · 9 pass · 13 N/A**.

> **Composition pass (2026-11-15):** **Featured, Problems and FPS Warning** were
> re-shot with the Failsafe sidebar enlarged (UI scale raised, 3D viewport
> maximized) so the findings fill a much larger share of the frame and read at
> storefront-thumbnail size — the findings now occupy roughly 40–45 % of each
> image (vs ~17 % before). Still genuine captures of the real add-on on the same
> reproducible scene; crop + downscale only, no pixel/text/count/finding altered.
> **Overview, Report and Breadth are unchanged** (accepted on the prior pass). The
> un-cropped retina sources for the three re-shot images are kept in
> `refresh_dfda2f7_wide/`.

## Provenance (so the gallery is defensible)

- **Captured from:** the actual installed extension `bl_ext.user_default.failsafe`
  running in **Blender 5.2.3 LTS** on macOS, build `dfda2f7`.
- **Scene:** a disposable demo at a neutral path —
  `/Users/Shared/failsafe_demo/failsafe ui test.blend` — a single Cube with a
  **Cloth** sim. The path contains **no username or private information**.
- **The failure is real AND reproducible.** The cloth was baked to disk (all 250
  frames), the project saved with the bake intact, and then **one** cache frame
  (247) was deleted from the `blendcache_` folder on disk. The file was **not**
  re-saved after that deletion. On a fresh open from disk, Blender still reports
  the cloth as baked (`is_baked = True`, `use_disk_cache = True`), 249 of 250
  cache files are present, and frame **247** is genuinely missing.
- **Verified by reopening and scanning.** On build `dfda2f7`, a fresh open + scan
  through the real GUI operator reports, in Blender's own words:
  **"3 fail, 1 warning, 0 couldn't verify"** (9 pass, 13 N/A). The three FAIL
  messages name frame **247**.
- Every number and message shown in these images came out of that scan. Nothing
  was edited into the UI. **Save Settings Baseline** wrote an external sidecar
  (`…failsafe-baseline.json`) next to the `.blend` — it did **not** modify the
  `.blend` (`bpy.data.is_dirty` stayed False; read-only guarantee holds).

## The images (all 2:1, 1400 × 700 px, ≥ 1200 px wide)

The featured image is also exported as **JPG, ~0.13 MB** (well under Superhive's
5 MB featured-image limit).

| File | Feature it shows | The real result it proves |
|---|---|---|
| **featured.jpg / featured.png** | **Catches a missing cache frame — the headline moment.** *(Re-shot, panel-dominant.)* The finding fills the right ~45 % of the frame, the Cube still in view. | FAIL: "Cloth is **missing 1 of 250 required cache frame(s) on disk: 247**. The render will freeze or re-simulate there." Blender still calls it "baked." |
| **gallery_01_overview.png** | **The one-click interface + summary.** Scan Scene, Export Text Report, Save Settings Baseline, Check before render, and the live count pills (**3 / 1 / 0** — no more permanent "?"). Titles are **left-aligned**. | A real scan summary shown as live counts: 3 fail, 1 warning, 0 couldn't-verify. |
| **gallery_02_problems.png** | **Every problem explained in plain English, with a next step.** *(Re-shot, panel-dominant.)* The **3 / 1 / 0** pills plus the collision WARNING with its full "Why" and a one-click **Open Physics settings (Cube)** + Tip; the cache FAILs follow below. | WARNING: "Cloth collision is on, but no object in the scene has a Collision modifier to collide with." + the 3 / 1 / 0 count pills (0 couldn't-verify). |
| **gallery_03_timing_warning.png** | **The new frame-rate timing check (#23) catching a change.** *(Re-shot, panel-dominant.)* A **WARNING** after the scene frame rate was changed 24→30 FPS *after baking*. The long title **wraps onto two left-aligned lines** (the narrow-width title fix). | WARNING: "Frame rate changed since the baseline: saved 24 FPS, scene is now 30 FPS…" with a re-bake Tip. |
| **gallery_04_report.png** | **Exports a shareable report** showing a **neutral file path**. | Report header: `File: /Users/Shared/failsafe_demo/failsafe ui test.blend` + `Summary: 3 Fail  1 Warning  0 Couldn't verify  9 Pass  13 N/A` and the honest "Couldn't verify = NOT a confirmed problem" note. |
| **gallery_05_breadth.png** | **Breadth of the 26 checks.** The Physics-Setup checklist with green PASS rows, grey N/A rows, and the one WARNING — left-aligned titles. | A real checklist: PASS/N/A/WARNING rows across the Physics Setup group. |

**Six images total** (featured + five), each showing a different genuine feature.
Superhive's minimum is five.

> **Note on `gallery_03_timing_warning.png`:** this is a **deliberately staged**
> frame-rate change (24→30 FPS after baking) to demonstrate check #23 catching it.
> The result shown is the real, unedited WARNING for that state — not a fabricated
> finding — so its count pill reads 3 / **2** / 0 (the extra warning is the timing
> one). The *saved* demo (frame rate 24, matching its baseline) scans #23 as a
> green **PASS**, which is the 3 / 1 / 0 state shown in every other image.

## Evidence / originals

The **un-cropped native captures** are retained as evidence:
- `refresh_dfda2f7/` — first-pass full-window/full-panel grabs (source for the
  accepted **Overview, Report, Breadth**).
- `refresh_dfda2f7_wide/` — the 3420×2009 retina sources for the re-shot
  **Featured, Problems, FPS Warning** (sidebar enlarged for readability).

The published images are a straight crop + downscale of those (Pillow, LANCZOS, no
other edit). The prior-build and prior-framing published images remain recoverable
from git history.

## QA (done)

- Every image is **genuinely captured** from the live Blender interface (build
  `dfda2f7`), **cropped and downscaled only** — never upscaled, never edited.
- **Uniform 2:1** at **1400 × 700** (≥ 1200 px wide) — confirmed.
- **No usernames, private paths, notifications, or unrelated personal info.** The
  report's file path is the neutral `/Users/Shared/…`.
- **Counts and findings match the live scan** — 3 / 1 / 0 on the saved state
  (Featured, Problems, Overview, Report, Breadth); 3 / 2 / 0 on the clearly-labeled
  staged timing shot (FPS Warning).
- **Findings are readable at thumbnail size** — on the three re-shot images the
  sidebar fills ~40–45 % of the frame (vs ~17 % before), with the 3D scene still
  visible; no warning, explanation or Tip is cropped off.
- Featured is **JPG and < 5 MB** (~0.13 MB); the rest are PNG (both allowed).

## Still open (owner gates — not screenshots)

- Genuine first-time-user (beginner) acceptance test — **NOT TESTED** (owner's call;
  may stay marked NOT TESTED rather than delay launch).
- Price decision (UNDECIDED).
- Publication approval + merge. Nothing here is published or merged.
