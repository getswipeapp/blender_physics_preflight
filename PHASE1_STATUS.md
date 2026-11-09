# Phase 1 — Build status

Date: 2026-11-09 · Follows `phase0/` (research + feasibility, all green).

## What was built
The complete **Physics Preflight** extension (`physics_preflight/`), implementing
all **23 checks** from the Scope Expansion Proposal (16 physics setup + 7 cache),
plus a one-click scan panel, "select affected object", and a text-report export.

Honours every technical rule proven in Phase 0:
- Never trusts Blender's `is_baked` / `has_cache_baked_*` flags — checks the real
  files on disk (`cache_inspect.py`), frame by frame.
- Fluid "Replay" → WARNING, never PASS.
- Rigid Body World disk check → NOT APPLICABLE (memory-only cache).
- Geometry Nodes packed bakes → UNKNOWN (undetectable from Python).
- Containment test for intersections (BVH overlap misses one body inside another).
- Five statuses, no false PASS, read-only, offline, no telemetry.

## What was tested
Headless harness (`tests/run_tests.py`) with a passing **and** failing fixture
per check — **41 assertions, all passing on Blender 5.2.3 LTS** (the version
installed on this Mac), including:
- #18 the headline trap: bake to disk → PASS; delete the files, reopen → Blender
  still reports baked, our check **FAILs**.
- #20 a single missing interior frame → **FAIL**.
- #3 one rigid body fully inside another → **WARNING** via the containment test.
- Version-sensitive paths (Blender 5.x slotted actions) handled.

The extension also passes `blender --command extension validate` and builds a
clean install zip (`extension build`).

## Still outstanding (from Phase 0 Next Steps)
1. **Run the headless harness on 4.2 LTS, 4.5 LTS and 5.0** — only 5.2.3 is
   installed here. Use `tests/run_all_versions.sh` after installing the others.
   The code guards every version-specific API, but this must be confirmed.
2. **GUI acceptance test** on the newest version + Keith's beginner test (needs a
   display; can't be done headless).
3. **Windows / macOS path coverage** — cache folder names, `//` relative paths,
   external/library caches. The path logic is OS-agnostic (`os.path`), tested on
   macOS; confirm on Windows.
4. Price and store listing: Keith's call (see `phase0/PHASE0_REPORT.md` §5).
