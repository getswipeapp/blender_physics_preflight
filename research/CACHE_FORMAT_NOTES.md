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

## What we validate now (zero false positives)

`cache_inspect._bphys_header_valid()` + `_scan_point_cache_files()`:
- **Magic signature**: a present, non-empty, readable `.bphys` whose first 8
  bytes aren't `BPHYSICS` is **not** cache data (garbage, or a foreign file
  written to the cache path). → frame marked corrupt (`frames_badheader`).
- **Header length**: magic present but file < 20 bytes = truncated header. →
  corrupt.
- These feed the existing `V_CORRUPT` verdict, so checks #17 and #18 FAIL with a
  precise message naming the cause (0-byte vs invalid header). A genuine baked
  frame always passes, confirmed by the real cloth/soft/particle/hair/DP bakes
  on all four versions (349/349, no regressions, no false corrupt).

This goes **beyond** the previous check (presence + 0-byte + first-byte-readable):
a file can be non-empty and readable yet not be valid cache data. No competitor
validates frame structure.

## What we deliberately do NOT claim (the honest boundary)

- **No "expected byte size" / full-body check.** Point-cache bodies are
  **compressed** (variable size per frame) on 5.0+ — on 5.2 the `compression`
  toggle is even removed from the API. So "size == points × stride" would
  misfire. We validate only the fixed header, never the compressed body.
- **No decode of every frame's payload.** Would require tracking Blender's
  internal compression scheme across versions; fragile, deferred.

## Next deep-integrity increment (planned, not yet built)

- **Stale-topology check**: compare header `totpoint` against the current
  object's point count; a mismatch means the cache was baked for a different
  mesh (a real, common failure). Higher value, but higher false-positive risk
  (modifier-stack order, particle alive-counts), so it needs its own increment
  with explicit false-positive fixtures before shipping — per the owner's
  "benchmark false positives" directive.
- Fluid (`.vdb`/`.uni`) and GN blob integrity: separate formats, separate study.
