# Failsafe — Store Gallery (real, reproducible captures · DRAFT)

> **DRAFT — not published.** Genuine screenshots of the real add-on on a real,
> **reproducible** scene. No mockups, no fabricated UI, no fabricated results, no
> edited findings (a selling rule from the launch brief). Cropping only.

## Provenance (so the gallery is defensible)

- **Captured from:** the actual installed extension `bl_ext.user_default.failsafe`
  running in **Blender 5.2.3 LTS** on macOS.
- **Scene:** a disposable demo at a neutral path —
  `/Users/Shared/failsafe_demo/failsafe ui test.blend` — a single Cube with a
  **Cloth** sim. The path contains **no username or private information**.
- **The failure is real AND reproducible.** The cloth was baked to disk (all 250
  frames), the project saved with the bake intact, and then **one** cache frame
  (247) was deleted from the `blendcache_` folder on disk. The file was **not**
  re-saved after that deletion. On a fresh open from disk, Blender still reports
  the cloth as baked (`is_baked = True`, `use_disk_cache = True`), 249 of 250
  cache files are present, and frame **247** is genuinely missing.
- **Verified by reopening three times.** Each fresh open + scan through the real
  GUI operator reports, in Blender's own words:
  **"3 fail, 1 warning, 1 couldn't verify"** (8 pass, 13 N/A). The three FAIL
  messages name frame **247**.
- Every number and message shown in these images came out of that scan. Nothing
  was edited into the UI. The baseline comparison shown in
  `gallery_03_baseline.png` is real: **Save Settings Baseline** wrote an external
  sidecar (`…failsafe-baseline.json`) next to the `.blend` — it did **not** modify
  the `.blend` (read-only guarantee holds).

## The images (all 2:1, 1990 × 995 px, ≥ 1200 px wide)

The featured image is also exported as **JPG, ~0.2 MB** (well under Superhive's
5 MB featured-image limit).

| File | Feature it shows | The real result it proves |
|---|---|---|
| **featured.jpg / featured.png** | **Catches a missing cache frame — the headline moment.** | FAIL #17/#18/#20: "Cloth is **missing 1 of 250 required cache frame(s) on disk: 247**." Blender still calls it "baked." |
| **gallery_01_overview.png** | **The one-click interface + summary.** Scan Scene, Export Text Report, Save Settings Baseline, Check before render, and the live count pills (**3 / 1 / 1**). | A real scan summary: 3 fail, 1 warning, 1 couldn't-verify, shown as live counts. |
| **gallery_02_problems.png** | **Every problem explained in plain English, with a next step.** A WARNING and a FAIL, each with a "Why", a one-click **Open Physics settings (Cube)**, and a "Tip". | WARNING #7 (no collider) + FAIL "Cloth is marked baked, but its cache on disk is incomplete." |
| **gallery_03_baseline.png** | **Honest comparison + honest uncertainty.** A real baseline comparison PASS and a blue "couldn't verify". | #26 "tracked settings unchanged since the baseline was saved — **not proof the bake itself is good**"; #23 blue "Bake timing couldn't be confirmed" (Blender doesn't record bake-time FPS). |
| **gallery_04_report.png** | **Exports a shareable report** showing a **neutral file path**. | Report header: `File: /Users/Shared/failsafe_demo/failsafe ui test.blend` + `Summary: 3 Fail  1 Warning  1 Couldn't verify  8 Pass  13 N/A` and the honest "Couldn't verify = NOT a confirmed problem" note. |

**These five are the complete gallery** (Superhive minimum is five). Featured +
four = five, each showing a different genuine feature.

## QA (done)

- Every image is **genuinely captured** from the live Blender interface (native
  2442 × 2056 window screenshots, cropped — never upscaled, never edited).
- **2:1** and **≥ 1200 px wide** — confirmed 1990 × 995.
- **No usernames, private paths, notifications, or unrelated personal info.** The
  report's file path is the neutral `/Users/Shared/…`.
- Featured is **JPG and < 5 MB**; the rest are PNG (both allowed).

## Still open (owner gates — not screenshots)

- Genuine first-time-user (beginner) acceptance test.
- Price decision (UNDECIDED).
- Publication approval + merge. Nothing here is published or merged.
