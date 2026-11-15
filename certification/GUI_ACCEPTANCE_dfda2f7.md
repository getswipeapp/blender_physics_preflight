# Failsafe — Live GUI Acceptance (build `dfda2f7`)

> **Real, live acceptance.** Driven against a running **Blender 5.2.3 LTS** (macOS)
> with the extension installed from `dist/failsafe-dfda2f7.zip`
> (`bl_ext.user_default.failsafe`, 26 checks registered), on the reproducible demo
> `/Users/Shared/failsafe_demo/failsafe ui test.blend`. Date: 2026-11-15.
> Captures: `launch/gallery/refresh_dfda2f7/`.

This round exists to verify the two owner-reported UI defects and the rebuilt
check #23 in the **real** interface, not just headless.

| # | Acceptance item | Result | Evidence |
|---|---|---|---|
| 1 | Installed build is the new one (not a cached old copy) | ✅ PASS | On-disk + in-memory confirmed: `BASELINE_SCHEMA = 4`, `_finite_positive` present, `FINGERPRINT_COMPAT_SCHEMAS = (3, 4)`, `_header_title` present, #23 `name_unknown = "Timing baseline couldn't be read"`. |
| 2 | **Title left-alignment (wide-width defect)** | ✅ PASS | Result titles (e.g. "Cloth/soft body has no collider", "Simulation isn't properly baked") render **flush-left**, aligned with the arrow and body text — no centering/right-drift. `01_overview.png`, `02_problems.png`. |
| 3 | **Title wrapping (narrow-width defect)** | ✅ PASS | The long #23 title "Frame rate changed since the timing baseline" **wraps onto two left-aligned lines** with no "…" truncation. `03_timing_warning.png`. |
| 4 | **#23 — no baseline / old baseline** | ✅ PASS | With the pre-existing schema-3 sidecar, #23 is **N/A** ("predates timing tracking"), not a false PASS and not the old permanent "?". Tally pill shows **❓ 0**. |
| 5 | **#23 — frame rate unchanged** | ✅ PASS | After **Save Settings Baseline** (schema-4, records 24 FPS), #23 = **PASS** "Frame rate unchanged since the baseline was saved (24 FPS)…" with the honest "not proof the cache was baked at that rate" caveat. |
| 6 | **#23 — frame rate changed** | ✅ PASS | Scene FPS 24→30 after baking → #23 = **WARNING** "Frame rate changed since the baseline: saved 24 FPS, scene is now 30 FPS…", with a re-bake Tip. `03_timing_warning.png`. |
| 7 | **#26 settings baseline** | ✅ PASS | After Save Baseline, #26 = PASS "Tracked settings unchanged since baseline". |
| 8 | **Save Baseline is read-only to the .blend** | ✅ PASS | Operator reported "Your .blend was not modified"; `bpy.data.is_dirty` stayed **False** across install, scan, save-baseline, FPS change, and export. Only the external `…failsafe-baseline.json` sidecar was written. |
| 9 | Expand/collapse of result rows | ✅ PASS | Per-row collapse (`failsafe.toggle_detail`) works; collapsed rows show a one-line summary, expand restores detail + action button. |
| 10 | Severity filter + Export report | ✅ PASS | The ❌/⚠️/❓ tally pills filter the list; **Export Text Report** wrote `failsafe_report.txt` with a neutral path and `Summary: 3 Fail  1 Warning  0 Couldn't verify  9 Pass  13 N/A`. `04_report.png`. |

**Reproducible saved-state tally (build `dfda2f7`):** 3 FAIL · 1 WARNING ·
**0 Couldn't verify** · 9 PASS · 13 N/A. The three FAILs name the genuinely-missing
cache frame **247**.

## Not covered here (unchanged owner gates)

- Genuine first-time-user (beginner) acceptance — still **NOT TESTED**.
- Price decision (UNDECIDED) and publication approval/merge — owner's call.
