# .bphys point-cache format — verified notes (deep-integrity basis)

Evidence gathered 2026-11-16 by baking real sims and reading the bytes on four
official Blender builds (4.2.9, 4.5.9, 5.0.1, 5.2.3). This is the basis for the
header-level integrity check; it records what we can honestly validate and what
we deliberately do **not** claim.

## Disk point-cache frame file (`<HEX(name)>_<frame:06d>_<index:02d>.bphys`)

Fixed 20-byte header, identical across all four versions:

| Offset | Size | Field       | Notes |
|-------:|-----:|-------------|-------|
| 0      | 8    | magic       | ASCII `BPHYSICS` on every version |
| 8      | 4    | type word   | LE uint32. **Low 16 bits** = sim type: soft=0, particle=1, cloth=2. **High 16 bits** are a version/compression flag: `0x0000` on 4.2/4.5, `0x0001` on 5.0/5.2 — so never key on the whole word, mask the low 16 bits. |
| 12     | 4    | totpoint    | LE uint32. Verified equal to the owning object's point count (cloth/soft = vertex count; particle = `settings.count`). |
| 16     | 4    | data_types  | LE uint32 bitmask of which per-point fields are stored. |

Measured (cloth grid, 81 verts): `magic=BPHYSICS`, typeword `0x0000_0002` (4.2/4.5)
/ `0x0001_0002` (5.0/5.2), totpoint `81`, data_types `22`. Soft body (42 verts):
type `0`, totpoint `42`. Particles (count 40): type `1`, totpoint `40`.

## What we validate now (basic structural verification)

`cache_inspect._bphys_header_valid()` + `_scan_point_cache_files()` perform a
**basic structural** check — not complete format validation. A present,
non-empty, readable `.bphys` frame is treated as **structurally invalid** (→
`frames_badheader` → `V_CORRUPT` → #17/#18 FAIL) when any of these hold:
- **Bad magic** — first 8 bytes ≠ `BPHYSICS` (garbage or a foreign file at the path).
- **Short header** — magic present but file < 20 bytes.
- **Zero header fields** — `totpoint == 0` or `data_types == 0`. This catches the
  fabricated `BPHYSICS` + 12 zero bytes file raised in review B1.
- **No payload** — exactly the 20-byte header with nothing after it.
- **Wrong sim-type** (review M1) — the type word (low 16 bits) does not match the
  type of the simulation that **owns** this cache. We compare only against the
  owner's known type (Cloth=2, Soft Body=0, Particles=1, Dynamic Paint=5,
  verified on real bakes across all four versions), never a guessed universal
  set. An owner kind we have not mapped skips the type check rather than being
  rejected. Scope note (review M1 follow-up): this is validated for the sim kinds
  and Blender versions we have baked and byte-inspected and for our fixtures — it
  is not a guarantee about every future Blender variant or every unusual-but-valid
  cache; it is the tested compatibility scope, not a universal proof.

**Hair Dynamics is intentionally exempt from the type check.** A hair-dynamics
cache is *mixed*: frame 0 is a particle frame (type 1, `totpoint` = strand count)
while the simulated frames are a cloth solve (type 2, `totpoint` = strand ×
points-per-strand) — verified on all four versions. There is no single correct
type, so enforcing one would reject a valid cache (the regression that the
`HS hair dynamics baked (pass)` fixture catches). Hair still gets the
magic/field/payload checks.

Known limits of this basic check (review M1): it does not bound the payload size
(it accepts any non-empty payload, down to a single byte, because the body is
compressed and version-variable) and does not decode the body. On the four-version
matrix every real baked cloth/soft/particle/hair/DP frame passes; this is
validated against our fixtures and real bakes, not proven false-positive-free in
general.

## What we DO NOT claim — verified structure ≠ verified payload (review B1)

This validates **file structure**, not the numerical correctness of the baked
data. Ground truth, probed on 5.2.3 by baking real cloth, recording the deformed
mesh at a frame, then mutating that frame's cache file and re-reading:

| Mutation of one frame file | Structure check | Blender's own read |
|---|---|---|
| bad magic / short header / zero fields / header-only | **rejects** (FAIL) | falls back to rest |
| **body zeroed, header intact, full size** | passes (looks valid) | **cannot load it — falls back to rest** |
| **body truncated, header intact** | passes (looks valid) | **cannot load it — falls back to rest** |

So a well-formed header with a corrupted or truncated **body** is NOT detected by
the structure check, yet Blender still can't use it. Two hard constraints make a
cheap payload check infeasible:
- Point-cache **bodies are compressed and variable-size** on 5.0+ (the
  `compression` toggle is gone from 5.2's API), so there is no "expected size" to
  compare against, and no stride to recompute.
- When a present frame fails to load, Blender writes **no error** to stderr and
  leaves `point_cache.is_baked == True` — it silently renders the rest shape. So
  there is no in-process signal, and no reference "truth" to compare an evaluated
  frame against. A reference-free payload oracle is not reliable.

Therefore `V_COMPLETE`/PASS means **"all frames present and structurally
well-formed"**, and the #18 PASS message says so explicitly — it is NOT a claim
that the payload bytes are numerically intact. We do not treat an un-decoded
payload as proven healthy.

## Baselined per-frame hashes — SHIPPED (2026-11-16, review M2)

Catches a corrupted/truncated **body** that still has a valid header — the gap
the structural check above can't close. Implemented in `cachehash.py` + check
**#27** ("Cache files unchanged since the baseline"), certified on all four
versions.

How it works:
  - Save Baseline *with cache hashes* streams a SHA-256 of every present point-
    cache frame file into the external sidecar (schema 5, optional `cache_hashes`
    section), keyed by the sim's stable `Scene::Owner::System::Sub` identity and
    the file's **project-relative** path + frame number. Reads only; the one write
    is the sidecar, never the .blend.
  - A later verification re-hashes and compares. It is run ON DEMAND (the "Verify
    Cache Hashes" button, or the CLI `--verify-hashes` flag), NOT on every quick
    scan, because it reads every cache byte — a quick scan must never freeze on
    gigabytes. The GUI runs it in a modal operator that streams one file per step
    with progress and Esc-cancel; the normal scan reports "#27 hasn't been run".

Honesty constraints, all enforced and tested:
    - A mismatch is **"cache file changed since the baseline,"** NOT automatically
      "corrupt." A deliberate re-bake legitimately rewrites the bytes — a
      *detected change*, which may be expected. The #27 message says so.
    - A match is **"bytes unchanged since the baseline,"** NEVER "content valid."
      Verified by a test that damages a frame, baselines the damaged bytes, then
      gets a clean "unchanged" — proving a match is not a validity oracle.
    - So hashing is **change detection**, only as trustworthy as the moment the
      baseline was taken. NOT "no false positives" (a re-bake is a true change
      that isn't a defect).
    - Missing / no-section / no-baseline / wrong-schema / foreign / unreadable /
      not-run can never PASS (each has a test forbidding PASS).
    - Edge cases covered by tests: genuine re-bake, multi-sim keying, project
      relocation (whole folder moved), a file changing mid-read (-> VOLATILE,
      skipped), and a cancelled capture (raises, writes nothing).
  Complementary to — not a substitute for — having Blender decode the frame
  (kept deliberately separate). Scope: **point caches** (.bphys) for now; fluid
  (`.vdb`/`.uni`) and GN blobs are the next hashing sub-increment (their file
  layouts differ and need their own study).

## Next deep-integrity increments (planned, not yet built)

- **Cache-hash coverage for fluid + Geometry Nodes** — extend the #27 manifest to
  the Mantaflow sub-caches and GN blobs (multi-file-per-frame layouts, separate
  from the one-file-per-frame `.bphys` scheme).
- **Stale-topology check** — compare header `totpoint` against the current
  object's point count; a mismatch means the cache was baked for a different
  mesh. Higher value, higher false-positive risk (modifier-stack order, particle
  counts), so it needs its own increment with explicit false-positive fixtures.
- Fluid (`.vdb`/`.uni`) and GN blob integrity: separate formats, separate study.
