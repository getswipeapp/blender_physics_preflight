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

## What we validate now (file structure)

`cache_inspect._bphys_header_valid()` + `_scan_point_cache_files()`. A present,
non-empty, readable `.bphys` frame is treated as **structurally invalid** (→
`frames_badheader` → `V_CORRUPT` → #17/#18 FAIL) when any of these hold:
- **Bad magic** — first 8 bytes ≠ `BPHYSICS` (garbage or a foreign file at the path).
- **Short header** — magic present but file < 20 bytes.
- **Zero header fields** — `totpoint == 0` or `data_types == 0`. This catches the
  fabricated `BPHYSICS` + 12 zero bytes file raised in review B1.
- **No payload** — exactly the 20-byte header with nothing after it.

On the four-version matrix (4.2.9/4.5.9/5.0.1/5.2.3) every real baked
cloth/soft/particle/hair/DP frame passes this (no regressions; see the suite's
`integrity_header_tests` and the `HS bphys …` / `bphys … no cache PASS` cases).
We do not claim this is provably false-positive-free in general — it is validated
against our fixtures and the real bakes, no more than that.

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

## Next deep-integrity increment (planned, not yet built)

- **Baselined per-frame hashes** — the right way to catch a corrupted/truncated
  **body** that still has a valid header. When the user clicks Save Baseline,
  record a hash of each cache frame file; a later scan flags any frame whose
  bytes changed. This detects all three body-level mutations above with no false
  positives (a hash matches or it doesn't) and no format reverse-engineering.
  This is the honest path to "content integrity"; the current increment is
  structure validation only.
- **Stale-topology check** — compare header `totpoint` against the current
  object's point count; a mismatch means the cache was baked for a different
  mesh. Higher value, higher false-positive risk (modifier-stack order, particle
  counts), so it needs its own increment with explicit false-positive fixtures.
- Fluid (`.vdb`/`.uni`) and GN blob integrity: separate formats, separate study.
