# Physics Preflight — Runtime Certification Evidence

**Package under test:** `physics_preflight_c977ac2.zip`
**Source commit:** `c977ac2` (branch `phase1-physics-preflight-extension`)
**Package SHA-256:** `67c03635af34de73a65fc9d2e7f16d8beccf57b34ec9dfffd34909d58a6d210b`
**Host:** macOS (Darwin 25, Apple Silicon / arm64)
**Prepared by:** Claude Code (headless), autonomously, per the approved Option 1 plan.

> Ground rule honoured throughout: **no compatibility is claimed for anything not
> actually executed.** Versions/platforms not run are marked UNKNOWN, not PASS.

**Date:** 2026-11-10

### Bottom line
- **Headless certification: PASS on Blender 4.2.9, 4.5.9, 5.0.1, 5.2.3** — 128/128
  each, including real cloth/soft-body/particle/fluid bakes and damaged-cache
  adversarial cases.
- **Read-only / filesystem safety: PASS** on all four — a scan changes nothing.
- **Still open (not claimed as passing):** the GUI acceptance test on 5.2 (needs
  Keith — checklist ready), a live Geometry-Nodes *disk* bake, and **Windows**
  (no Windows host here — UNKNOWN, documented in §5).

---

## 1. Headless test matrix (automated)

Each cell is the result of `blender -b --factory-startup -P tests/run_tests.py`
run against an **official Blender build** (downloaded from download.blender.org,
de-quarantined, run from an isolated copy — the user's installed 5.2.3 was used
as-is). The suite covers: all 23 checks on crafted scenes, real heavy-sim bakes
(cloth, soft body, particles, fluid incl. mesh/noise/particles/guiding/config),
adversarial damaged caches, the single-source-of-truth verdict engine, the
reliability guards (R14–R18), and read-only / filesystem-safety assertions.

| Blender build | Channel | Result | Tests | Evidence log |
|---------------|---------|--------|-------|--------------|
| **Blender 4.2.9** | LTS | ✅ **PASS** | 128 passed / 0 failed | `results/run_4.2.log` |
| **Blender 4.5.9** | LTS | ✅ **PASS** | 128 passed / 0 failed | `results/run_4.5.log` |
| **Blender 5.0.1** | stable | ✅ **PASS** | 128 passed / 0 failed | `results/run_5.0.log` |
| **Blender 5.2.3** | LTS | ✅ **PASS** | 128 passed / 0 failed | `results/run_5.2.log` |

All four builds are **official download.blender.org arm64 releases**, run headless
(`-b --factory-startup`). 5.2.3 is the user's installed copy; 4.2.9 / 4.5.9 / 5.0.1
were downloaded, de-quarantined, and run from isolated copies. Declared support in
`blender_manifest.toml`: Blender 4.2+ (`blender_version_min = "4.2.0"`).

**One finding during certification (now fixed):** the guiding integration fixture
originally crashed on **4.2.9** only — adding the guide-effector object *after*
enabling guiding on the domain hit a Blender 4.2 headless `ViewLayer.update()`
bug (a Blender ops/depsgraph quirk, **not** an add-on defect). The fixture was
reordered to build all geometry before enabling guiding; 4.2.9 then passed
128/128 like the rest. The add-on's own code was unchanged by this fix.

## 2. Simulation coverage (within the headless suite)

| Simulation type | Baked-OK case | Damaged-cache case | Notes |
|-----------------|---------------|--------------------|-------|
| Cloth / Soft Body (point cache) | ✅ real bake | ✅ missing tail frame → FAIL | disk cache |
| Particles (point cache) | ✅ real bake | ✅ missing tail frame → FAIL | disk cache |
| Fluid (Mantaflow) | ✅ real bake | ✅ missing data / mesh / config / guiding frame → FAIL; mislabeled file ignored | data+mesh+noise+particles+guiding+config |
| Rigid Body World | ✅ flag + reliability | memory cache (in .blend) | no disk files by design; staleness guarded |
| Geometry Nodes (disk bake) | logic unit-tested | blobs-missing → FAIL; present → UNKNOWN | see §4 — live GN disk bake is a GUI item |

## 3. Read-only / filesystem safety (automated)

A scan must never modify the scene or write to disk. Asserted after a full
`run_all()` over a scene with a **real baked cache on disk**:

- Scene state unchanged: selection, active object, current frame, frame range,
  mode, and object/mesh/text datablock counts.
- Filesystem unchanged: the entire cache tree snapshotted (path → size, mtime);
  **no file added, removed, or modified** by a scan.

Result: ✅ **PASS on all four versions** — with a real 10-file soft-body cache on
disk, a full scan added/removed/changed zero files and left the scene (selection,
active object, frame, frame range, mode, datablock counts) byte-for-byte identical.

## 4. Items that genuinely require a human / another platform

These are **not** claimed as passing; they are the honest remaining gaps.

| Item | Status | Why it can't be headless-certified here |
|------|--------|------------------------------------------|
| GUI acceptance on 5.2 (install, panel, scan, deleted-cache "no false pass", export) | ⏳ pending Keith | Needs the real Blender window + a human; checklist prepared (`GUI_ACCEPTANCE_CHECKLIST.md`). |
| Live Geometry Nodes **disk** bake integration | ⏳ UNKNOWN | GN sim-zone disk bakes are too fragile to script headlessly; the add-on already reports UNKNOWN for them by design, and the logic is unit-tested. |
| `is_outdated` / stage-flag-off live triggers (R13/R14) | ⏳ UNKNOWN | Set by Blender's depsgraph during interactive editing; don't flip under `--factory-startup`. Verdict logic is unit-tested via the real check functions. |
| Windows cache-path handling | ⏳ UNKNOWN (see §5) | No Windows runtime available on this host. |

## 5. Windows compatibility (documented, not certified)

No Windows machine is available in this environment, so **Windows is not
certified**. Code-level notes for the reviewer: paths are handled with
`os.path`/`bpy.path.abspath` (separator-agnostic), cache filename matching is
case-insensitive, and portability checks use `realpath`/`commonpath`. These make
Windows support *plausible* but **unproven**. Recommended before claiming Windows
support: run `tests/run_tests.py` on Blender 4.2/5.2 on Windows and spot-check a
backslash cache path.

## 6. How to reproduce

```bash
# from the repo root
bash /Users/ralph/Downloads/blender_runtime_certification/run_matrix.sh
```

Per-version full logs are saved under `blender_runtime_certification/results/`.

---

*Summary line and remaining-limitations list are completed from the actual run
below once every version has executed.*
