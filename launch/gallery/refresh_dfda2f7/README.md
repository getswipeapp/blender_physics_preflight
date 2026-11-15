# Gallery refresh — build `dfda2f7` (2026-11-15)

New-build captures of the real add-on, replacing the prior-build `gallery_0X.png`.
Captured live from the connected extension `bl_ext.user_default.failsafe`
(installed from `dist/failsafe-dfda2f7.zip`) in **Blender 5.2.3 LTS** on macOS,
on the reproducible demo `/Users/Shared/failsafe_demo/failsafe ui test.blend`.
Real screenshots, cropping only — no edits. These need a final uniform 2:1 crop
before launch.

| File | What it shows (all real scan output) |
|---|---|
| `01_overview.png` | The one-click panel: Scan Scene, Export Text Report, Save Settings Baseline, Check before render, and the live count pills **3 / 1 / 0** (no more permanent "?"). Titles are **left-aligned**. |
| `02_problems.png` | The three cache FAILs, each in plain English with a one-click **Open Physics settings (Cube)** and a Tip: "Simulation isn't properly baked", "Cache files are missing from disk" (frame 247), "Some frames are missing from the cache". Titles wrap cleanly, left-aligned. |
| `03_timing_warning.png` | **The new check #23 in action.** After a deliberate 24→30 FPS change *after baking*, #23 reports **WARNING "Frame rate changed since the timing baseline"** — proof it is now a real detector, not a dumb "?". The long title **wraps onto two lines and stays left-aligned** (the narrow-width title fix). |
| `04_report.png` | The exported text report with a **neutral file path** (`/Users/Shared/…`) and `Summary: 3 Fail  1 Warning  0 Couldn't verify  9 Pass  13 N/A`. |
| `05_breadth.png` | The full Physics-Setup checklist (breadth of the 26 checks), PASS/NA rows, left-aligned titles. |

## Provenance notes

- `03_timing_warning.png` is a **deliberately staged** frame-rate change (24→30
  after baking) to demonstrate check #23 catching it. The result shown is the real,
  unedited WARNING for that state — not a fabricated finding. The *saved* demo
  (frame rate 24, matching its baseline) scans #23 as a green **PASS**.
- Across every capture the `.blend` was **never modified** (`bpy.data.is_dirty`
  stayed False). Saving the baseline wrote only the external
  `…failsafe-baseline.json` sidecar.
