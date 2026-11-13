# Failsafe

> **DRAFT — not yet published.** This build is pending independent review. Nothing
> here is final until that review passes and the owner approves.

A read-only Blender add-on (extension) that catches physics and
simulation-cache problems **before you render** — in one click.

> **Why it exists:** Blender itself will tell you a simulation is "baked" when
> the cache files have been deleted. For Cloth, Soft Body and Fluid, the
> `is_baked` / `has_cache_baked_*` flags stay `True` after the files are gone
> (verified on Blender 4.2.9 / 4.5.9 / 5.0.1 / 5.2.3). Failsafe does
> **not** trust those flags — it checks the actual files on disk, frame by
> frame, and says **Couldn't verify** wherever Blender genuinely cannot prove
> the answer. No false "all good".

- **Read-only scans.** A scan never edits your scene, writes cache files, or
  auto-fixes. The only opt-in writes are a button-click away: **Export** builds an
  in-memory Text datablock (nothing on disk until you save); **Save Baseline** writes
  an external sidecar — never the `.blend`.
- **Offline.** No network access, no telemetry, no licensing server.
- **Plain English.** Every finding tells a beginner what is wrong, why it
  matters, and how to fix it, with a one-click "Select affected object".
- **Optional "check before render".** An opt-in preference runs the scan once at
  render start and prints a console warning — **synchronous and non-cancelling**; it
  never stops or alters a render, and isn't a guarantee of render success.

## Install

1. Download `failsafe-<version>.zip` (or build it yourself, below).
2. Blender → **Edit → Preferences → Get Extensions / Add-ons → Install from
   Disk…** → pick the zip.
3. Open the **Failsafe** tab in the 3D Viewport sidebar (press `N`).
4. Press **Scan Scene**.

Requires **Blender 4.2 LTS or newer** (4.2, 4.5, 5.0, 5.2 are the supported
targets).

### Also runs headless (render farms / pipelines)

No window, no person — just an exit code a build system can read:

```bash
blender -b shot.blend \
  --python-expr "import bl_ext.user_default.failsafe.cli as c; c.main()" -- --json --strict
```

Exit codes: `0` clean · `1` blocking (a FAIL) · `2` unverified (a "Couldn't
verify") · `3` usage/internal. **`0` means no FAIL and nothing unverified — WARNINGs
alone still return `0` unless you pass `--strict`** (which makes a WARNING blocking).
`--batch <folder>` scans every `.blend` in a folder (worst result wins). Output is
`--text` (default) or `--json`, printed to **stdout** (redirect it to save a file).
Everything
headless is read-only too — it only reads each file and prints a report.

**Crash-isolated batch (render farms).** `--batch` runs **each file in its own
Blender subprocess with a per-file timeout** (`--timeout <secs>`, default 300), so
one corrupt or hanging `.blend` can't take the whole run down — it's recorded as
an error and the batch keeps going, preserving every good file's result. Use
`--in-process` for the faster single-process scan when you don't need isolation.

## The 26 checks

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
| 17 | Is the simulation baked? ("Couldn't verify" where Blender can't tell) |
| 18 | **Every expected cache file present and non-empty** — not just the "baked" flag |
| 19 | Baked range covers the render range |
| 20 | **Frame gaps**: every frame cached, not a sample |
| 21 | Two simulations writing to the same cache location |
| 22 | Non-portable caches (absolute paths, outside the project) |
| 23 | FPS / time-scale changed after baking |
| 24 | Cache sitting in a cloud-synced folder (Dropbox, OneDrive, Google Drive, iCloud…) — can be locked or only partly downloaded at render time |
| 25 | Potentially unclaimed cache files no simulation in this scene owns (often from renamed/deleted sims) — flagged to review before deleting, since a shared folder may hold another `.blend`'s data |
| 26 | Simulation settings changed since you saved a **baseline** (opt-in; compares against an external sidecar file, never written into your `.blend`) |

Covered cache systems: Cloth, Soft Body, Rigid Body World, Particles, Fluid
(Mantaflow), and Geometry Nodes simulation zones with **disk** bakes.

Reports also show **total cache disk usage** per simulation, so you can see at a
glance how much space a scene's bakes take.

## Statuses

`Pass` · `Warning` · `Fail` · `Couldn't verify` · `Not applicable`.

"Couldn't verify" means Failsafe didn't have enough evidence to confirm the
answer — **not** that something is wrong. Every one shows a plain reason and a
next step. (Internally, and in `--json` / CLI output, this status is still the
machine-readable token `UNKNOWN`, so automation keeps a stable contract; only the
word shown to people changed.)

Judgement calls (mass, size, origin, margin, intersections) are **WARNING**, not
FAIL, to avoid false alarms. Structural mistakes that will certainly misbehave
(object not in the Rigid Body World, a constraint with no object, an animated
collider not marked "Animated") are **FAIL**.

## Known limits (honest, by design)

- **Geometry Nodes *packed* bakes (4.3+)** leave no Python-visible trace, so
  "baked?" and "range" report **Couldn't verify** for them — never a false PASS.
  (This is a Blender limitation, not a problem with your scene.)
- **Rigid Body World** caches live inside the `.blend` (memory only), so the
  on-disk file check is **Not applicable** for them.
- **Fluid "Replay"** is a playback cache, not a bake. It is reported as a
  **Warning**, never PASS.
- **FPS at bake time is not recorded by Blender**, so check #23 is "Couldn't
  verify" by nature (it flags a non-default time scale, and reminds you to re-bake).
- The **baseline** check (#26) can only tell you settings changed since you saved
  the baseline — not since the bake itself. Save the baseline right after baking
  for it to mean the most; with no baseline saved it reports "Couldn't verify".
- Dynamic Paint and hair dynamics are out of scope for v1.
- Memory (non-disk) point caches can't be verified file-by-file — reported as
  Not applicable with a note.

## Development

Source layout:

```
failsafe/        the extension (this folder is what gets zipped)
  blender_manifest.toml
  __init__.py             register / unregister
  engine.py               Result model, check registry, scan driver
  util.py                 read-only scene / geometry helpers
  cache_inspect.py        file-level cache verification (the differentiator)
  baseline.py             opt-in external settings-baseline (the one write action)
  cli.py                  headless entry point (exit codes, --json, --batch)
  batch.py                crash/hang-isolated batch (one subprocess per file)
  checks_setup.py         checks 1–16
  checks_cache.py         checks 17–26
  operators.py / ui.py / report.py / handlers.py / help_text.py
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
blender --command extension build --source-dir ./failsafe --output-dir ./dist
```

## License

GPL-3.0-or-later. (Superhive permits GPL or MIT for code products; Failsafe uses
GPL-3.0-or-later, the standard choice for add-ons that link Blender's GPL Python
API.) See [LICENSE](LICENSE).
