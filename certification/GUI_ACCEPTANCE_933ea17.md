# Failsafe — Live GUI Acceptance Test (commit `933ea17`)

> **DRAFT evidence — pending owner sign-off.** Performed in the real Blender
> window via the Blender MCP connection, driving the add-on's own operators (the
> exact code the panel buttons call). Date: 2026-11-13.

**Environment**
- Blender **5.2.3 LTS**, macOS (the owner's machine).
- Disposable test file: `failsafe ui test.blend` (a Cube with a **Cloth** sim whose
  disk cache is intentionally missing frame 247). The owner's real projects were
  not touched.
- Build under test: **`933ea17`** installed from `dist/failsafe-933ea17.zip` via
  `extensions.package_install_files`. Confirmed it is this exact build: the new
  modules `baseline.py` / `cli.py` / `batch.py` are present, both new operators
  register, and #26's heading is the `933ea17` string "Tracked settings unchanged
  since baseline".

**How this was driven (stated plainly):** each step calls the add-on's real
operator (`bpy.ops.failsafe.*`) in the live GUI build — the same code path the
panel buttons invoke. The Save-Baseline overwrite **confirmation dialog** is a
modal popup that can't be mouse-clicked reliably over MCP, so its two outcomes
(Cancel = preserve, Overwrite = replace) were exercised through the operator's
`EXEC_DEFAULT` paths rather than a literal click; the dialog itself (invoke +
draw + `overwrite` property) is present and shown in the panel. Everything else is
the real operator running in the real window.

## Results — 9/9 PASS

| # | Test | Result | Evidence |
|---|------|--------|----------|
| 1 | Install exact reviewed build `933ea17` | ✅ PASS | install `FINISHED`; `baseline`/`cli`/`batch` present; #26 heading = "Tracked settings unchanged since baseline" |
| 2 | Failsafe loads & shows all **26 checks** | ✅ PASS | `engine.CHECKS` ids 1–26; `label(UNKNOWN)` = "Couldn't verify"; panel renders (screenshot) |
| 3 | Save Baseline writes external JSON; `.blend` unchanged | ✅ PASS | sidecar `failsafe ui test.failsafe-baseline.json` created (schema **3**, identity `Scene::Cube::Cloth::Cloth`); `.blend` SHA-256 **identical** before/after (`f437af09…4b79`); operator reports "Your .blend was not modified" |
| 4 | Scan: baseline comparison works | ✅ PASS | #26 → **PASS** "The tracked settings of all 1 simulation are unchanged since the baseline was saved…" |
| 5 | Change a tracked setting → detected | ✅ PASS | cloth `mass` 0.3 → 0.55 → #26 → **WARNING** "Scene — Cube — Cloth — Cloth: settings changed since the baseline (**mass**)" |
| 6 | Overwrite: cancel preserves, confirm replaces | ✅ PASS | no-overwrite → **CANCELLED**, baseline SHA unchanged ("nothing was written"); `overwrite=True` → **FINISHED**, baseline SHA changed; operator has invoke + draw dialog + `overwrite` property |
| 7 | Export JSON: valid, findings, machine `UNKNOWN` | ✅ PASS | Text `failsafe_report.json` + clipboard; valid JSON; `summary.UNKNOWN` present; **"Couldn't verify" absent** from JSON; 26 checks; missing-frame detail "…on disk: 247" preserved. Full export: `results/gui_export_933ea17.json` |
| 8 | "Couldn't verify" shows reason + next action | ✅ PASS | "Bake timing couldn't be confirmed" → reason ("Blender doesn't store the FPS used at bake time…") + action ("When in doubt, delete the cache and re-bake.") |
| 9 | Ordinary scan writes no files / no scene change | ✅ PASS | scan added **0** files to the project folder; `.blend` SHA unchanged; selection / active object / frame / datablock counts identical before & after |

**Defects found:** none.

**Evidence files**
- `results/gui_acceptance_933ea17_panel.png` — the Failsafe panel in the live
  window (checks, a "Couldn't verify" item with its Why + Tip, Open-Physics jump).
- `results/gui_export_933ea17.json` — the actual JSON written by **Export JSON**
  in the GUI (tool=failsafe, overall=FAIL, `UNKNOWN`=1, 26 checks).

**Cleanup:** the cloth mass was restored to 0.3, the baseline re-matched to the
restored scene, and the test report Text datablock was removed. The on-disk
`.blend` was never saved by this test (it is byte-for-byte as the owner left it).

## Remaining commercial-release gates (not code)
- First-time-user (beginner) acceptance test.
- Windows testing, or ship with the documented Windows limitation.
- Owner approval to publish.
