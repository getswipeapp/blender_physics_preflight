# Physics Preflight

A read-only Blender add-on (extension) that catches physics and
simulation-cache problems **before you render** — in one click.

> **Why it exists:** Blender itself will tell you a simulation is "baked" when
> the cache files have been deleted. For Cloth, Soft Body and Fluid, the
> `is_baked` / `has_cache_baked_*` flags stay `True` after the files are gone
> (verified on Blender 4.2.23 / 4.5.15 / 5.0.1 / 5.2.3). Physics Preflight does
> **not** trust those flags — it checks the actual files on disk, frame by
> frame, and says **UNKNOWN** wherever Blender genuinely cannot prove the
> answer. No false "all good".

- **Read-only.** It never edits your scene, writes cache files, or auto-fixes.
- **Offline.** No network access, no telemetry, no licensing server.
- **Plain English.** Every finding tells a beginner what is wrong, why it
  matters, and how to fix it, with a one-click "Select affected object".

## Install

1. Download `physics_preflight-<version>.zip` (or build it yourself, below).
2. Blender → **Edit → Preferences → Get Extensions / Add-ons → Install from
   Disk…** → pick the zip.
3. Open the **Physics Preflight** tab in the 3D Viewport sidebar (press `N`).
4. Press **Scan Scene**.

Requires **Blender 4.2 LTS or newer** (4.2, 4.5, 5.0, 5.2 are the supported
targets).

## The 23 checks

### Physics Setup
| # | Check |
|---|---|
| 1 | Unapplied scale / rotation on physics objects |
| 2 | Suspicious rigid-body mass for the object size |
| 3 | Objects overlapping at the start frame — **including one object fully inside another** |
| 4 | Collision-shape mismatch (Convex Hull on a concave object) |
| 5 | High-poly or non-manifold colliders |
| 6 | Rigid Body World disabled / wrong collection / low substeps |
| 7 | Cloth / soft-body collision not configured |
| 8 | Negative scale or scaled parents on physics objects |
| 9 | Real-world size sanity for the scene scale |
| 10 | Origin far from geometry on active rigid bodies |
| 11 | Collision margin too large for the object size |
| 12 | Animated passive collider not marked "Animated" |
| 13 | Broken rigid-body constraints (missing object, disabled) |
| 14 | Collision modifier above deforming modifiers in the stack |
| 15 | Cloth pin group empty or missing |
| 16 | Fluid flow/effector outside the domain, or a domain with no flow |

### Simulation Caches
| # | Check |
|---|---|
| 17 | Is the simulation baked? (UNKNOWN where Blender can't tell) |
| 18 | **Every expected cache file present and non-empty** — not just the "baked" flag |
| 19 | Baked range covers the render range |
| 20 | **Frame gaps**: every frame cached, not a sample |
| 21 | Two simulations writing to the same cache location |
| 22 | Non-portable caches (absolute paths, outside the project) |
| 23 | FPS / time-scale changed after baking |

Covered cache systems: Cloth, Soft Body, Rigid Body World, Particles, Fluid
(Mantaflow), and Geometry Nodes simulation zones with **disk** bakes.

## Statuses

`PASS` · `WARNING` · `FAIL` · `UNKNOWN` · `NOT APPLICABLE`.

Judgement calls (mass, size, origin, margin, intersections) are **WARNING**, not
FAIL, to avoid false alarms. Structural mistakes that will certainly misbehave
(object not in the Rigid Body World, a constraint with no object, an animated
collider not marked "Animated") are **FAIL**.

## Known limits (honest, by design)

- **Geometry Nodes *packed* bakes (4.3+)** leave no Python-visible trace, so
  "baked?" and "range" report **UNKNOWN** for them — never a false PASS.
- **Rigid Body World** caches live inside the `.blend` (memory only), so the
  on-disk file check is **NOT APPLICABLE** for them.
- **Fluid "Replay"** is a playback cache, not a bake. It is reported as a
  **WARNING**, never PASS.
- **FPS at bake time is not recorded by Blender**, so check #23 is UNKNOWN by
  nature (it flags a non-default time scale, and reminds you to re-bake).
- Dynamic Paint and hair dynamics are out of scope for v1.
- Memory (non-disk) point caches can't be verified file-by-file — reported as
  NOT APPLICABLE with a note.

## Development

Source layout:

```
physics_preflight/        the extension (this folder is what gets zipped)
  blender_manifest.toml
  __init__.py             register / unregister
  engine.py               Result model, check registry, scan driver
  util.py                 read-only scene / geometry helpers
  cache_inspect.py        file-level cache verification (the differentiator)
  checks_setup.py         checks 1–16
  checks_cache.py         checks 17–23
  operators.py / ui.py / report.py
tests/
  fixtures.py             pass/fail scene builders
  run_tests.py            headless assertion harness
  run_all_versions.sh     run the harness on every installed Blender
```

### Run the tests

Against one Blender:

```bash
blender -b --factory-startup -P tests/run_tests.py
```

Against several installed versions (edit the paths at the top of the script):

```bash
tests/run_all_versions.sh
```

The harness builds a passing and a failing fixture for each check, runs the real
checks headless, and asserts the expected status — including the headline
"Blender says baked, but the files are gone" trap (#18) and the missing-interior
-frame trap (#20).

### Build the install zip

```bash
blender --command extension build --source-dir ./physics_preflight --output-dir ./dist
```

## License

GPL-3.0-or-later (required for Blender Python add-ons). See [LICENSE](LICENSE).
