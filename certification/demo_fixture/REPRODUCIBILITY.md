# Failsafe — Reproducible Demo Fixture (internal test evidence)

> **DRAFT — internal evidence, not published.** This records the disposable demo
> scene used for the store gallery and proves the headline failure is
> **reproducible after closing and reopening Blender** — not a one-off in-session
> artifact.

## What's in `failsafe_reproducible_demo.tar.gz`

- `failsafe ui test.blend` — the demo scene (Blender 5.2.3 LTS). One Cube with a
  **Cloth** sim, baked to disk, saved **with the bake intact**.
- `blendcache_failsafe ui test/` — the disk cache: **249** `.bphys` files for the
  1–250 range, with frame **247 deliberately removed** (245, 246, 248, 249 are
  present; 247 is not).
- `failsafe ui test.failsafe-baseline.json` — the external settings baseline
  sidecar written by **Save Settings Baseline**. Writing it did **not** modify the
  `.blend` (the read-only guarantee holds).

SHA-256 (recorded 2026-11-14):

| File | SHA-256 |
|---|---|
| `failsafe ui test.blend` | `7b24f1a264db3b2929e04155aaa5a9742411e9f93855cebffb329689db31fcaf` |
| `failsafe ui test.failsafe-baseline.json` | `9fc1ffc06ce3c4af6f905ad047c06dab9be7a054bb8360871709ef66b3c28295` |
| `failsafe_reproducible_demo.tar.gz` | `a69537aa5eb464bb52d51df9abb047826292980b872b9cce7cd6c208df6299d1` |

## How it was staged (the honest, documented procedure)

Worked only in `/Users/Shared/failsafe_demo/` (a neutral path — no username). The
original project at `~/Downloads` and the earlier screenshots were preserved,
untouched.

1. Saved the neutral-path `.blend` **before** baking.
2. Enabled Cloth **Disk Cache** and baked all **250** frames → saved the project
   **with the bake state intact**.
3. Reopened from disk and confirmed the baked state survived
   (`is_baked = True`, `use_disk_cache = True`, 250 files).
4. With the project **not** re-saved afterward, removed **only** cache frame 247
   from the `blendcache_` folder.

Frame 247 was removed **without** re-saving the `.blend` — re-saving at that point
could have let Blender re-evaluate and invalidate the demonstration. The `.blend`
on disk is therefore the version saved in step 2 (mtime confirms no later save).

## Reproduction proof (fresh open from disk → scan)

Opened the saved `.blend` fresh from disk and ran the real GUI scan operator
(`bpy.ops.failsafe.scan`). Repeated the close+reopen+scan cycle **three times** —
identical every time:

```
is_baked = True   use_disk_cache = True
cache files on disk = 249 / 250   (frame 247 missing)
baseline sidecar present = True

Failsafe: 3 fail, 1 warning, 1 couldn't verify
(tally: 3 FAIL, 1 WARNING, 1 UNKNOWN, 8 PASS, 13 N/A)
```

The three FAIL messages, verbatim from the scan:

- "Cloth is marked baked, but its cache on disk is incomplete."
- "Cloth is missing 1 of 250 required cache frame(s) on disk: **247**. The render
  will freeze or re-simulate there."
- "Cloth is missing 1 cached frame(s) across its 1–250 range: **247**. Each gap is
  a freeze/pop in the render."

The one "couldn't verify" is #23 (Blender doesn't record bake-time FPS); the
baseline check (#26) is a PASS ("unchanged since the baseline was saved — not
proof the bake itself is good") because the sidecar is present.

## Restoring the fixture

```
tar -xzf failsafe_reproducible_demo.tar.gz -C /some/neutral/dir
```

Open the extracted `.blend`, open the N-panel → **Failsafe** tab, click **Scan
Scene**. The scan reproduces the result above. The store gallery images in
`launch/gallery/` were cropped from native-resolution screenshots of exactly this
state.
