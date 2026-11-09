# Response to the Independent Code Review (2026-11-09)

Status after fixes: **test suite 77/77 on Blender 5.2.3** — now including
**real-bake integration tests** (soft-body, particle, and fluid liquid+mesh
bakes with frames deleted) plus read-only side-effect checks. Items that need
other Blender versions to *certify* are called out as pre-launch to-dos (only
5.2.3 is installed here). See the v2 section at the bottom for the second-round
(R01–R04) responses.

## Section 1 — Cache false-PASS (highest priority)

| ID | Finding | Resolution |
|----|---------|------------|
| **F01** | Missing first/last frames pass #17–#20 | **Fixed (root cause).** Completeness is now decided in one place, `cache_inspect.cache_status()`, which compares disk files against the *entire* required range. #17/#18/#20 all read that verdict, so a missing head/mid/tail frame FAILs all of them. New regression tests: `build_F01_missing_tail/head/multi_tail` + 14 verdict unit tests. |
| **F02** | Fluid matcher too loose; mesh/noise not verified | **Improved.** Stricter filename regex (frame + real cache extension). Required sub-caches (`mesh/`, `noise/`) are derived from `use_mesh`/`use_noise` and a missing one marks the bake INCOMPLETE. *Caveat:* full fluid certification needs a real fluid bake on each version — pre-launch to-do. |
| **F03** | Packed GN bake misread as disk (`INHERIT`) | **Fixed.** `_resolve_gn_target()` follows `INHERIT` to the modifier setting; anything not resolving to `DISK` is UNKNOWN. Per-bake custom path, frame range and still-frame mode now honoured. *Caveat:* no headless GN-disk integration fixture (needs a GN sim) — logic verified, runtime pending. |
| **F04** | Fluid Replay passes #18/#19/#20 | **Fixed.** Replay is a distinct verdict state; #18 WARNs ("not a real bake"), #19/#20 stay silent. Verdict unit test added. |
| **F05** | External cache misclassified as memory | **Fixed.** A cache is disk-backed when `use_disk_cache` **or** `use_external`; only a non-external, non-disk cache is treated as memory. |
| **F06** | Sampled cache called "every frame" | **Fixed.** `frame_step > 1` marks the entry `sampled`; #20 WARNs that frames are interpolated instead of claiming "every frame". |
| **F07** | Unreadable file counted as present/fine | **Fixed.** Read errors are tracked separately; an unreadable required frame yields UNKNOWN (not a silent pass). |

## Section 2 — Physics-setup

| ID | Finding | Resolution |
|----|---------|------------|
| **c03** | Tests current frame; silent PASS on BVH fail | **Fixed.** Off-start-frame → UNKNOWN with guidance; a failed BVH build → UNKNOWN, never a clean PASS. New fixture `build_03_offstart_unknown`. |
| **c01** | Advertises rotation, only checks scale | **Fixed.** Now also flags unapplied rotation on cloth/soft-body/collision objects (where rest shape matters). New fixture `build_01_rotation_fail`. |
| **c16** | Treats effector as a flow source | **Fixed.** FLOW and EFFECTOR are separated; a domain with only effectors warns "no flow source". New fixture `build_16_effector_only_fail`. |
| **c05** | Only >2-face edges counted | **Kept, by design** (prevents false positives on flat floors/sheets). Documented as a limitation; type-aware watertightness is a candidate for v1.1. |
| **c07** | Any collider yields PASS | **Partially addressed.** `col.use` is already honoured; the cloth collision-collection nuance is a known edge case (documented). |
| **F13** | 4.4 slotted-action first-slot only | **Hardened; needs 4.4 runtime.** Slot-aware path retained; cannot certify without Blender 4.4/4.5 installed. |
| **F14** | Large-scene stalls | **Largely already bounded** — `is_concave` returns UNKNOWN above 4,000 faces; overlap is AABB-gated. Noted. |
| **F15** | Absolute-inside path called portable; symlinks | **Fixed.** Absolute paths are never "portable"; containment now uses `realpath` (symlink-safe). |
| **F16** | PASS language when unverified | **Fixed.** #21/#22 only emit PASS when at least one cache path was actually resolved/checked. |

## Section 3 — Read-only / data-loss

| ID | Finding | Resolution |
|----|---------|------------|
| **F17** | Export overwrites a same-named text block | **Fixed.** Only a text block we created (identified by our header) is reused; otherwise Blender uniquifies the name. Message now says the report is stored *inside the .blend*. |
| **F18** | Selection lost if select fails | **Fixed.** Previous selection/active object are restored on failure. |

## Section 4 — Tests

| ID | Finding | Resolution |
|----|---------|------------|
| **F19** | Shallow assertions | **Improved.** Regression cases assert several checks at once **and forbid a wrong PASS** on a broken scene. |
| **F20** | Cache coverage cloth-heavy | **Improved** via 14 verdict unit tests covering fluid-replay, external, sampled, unreadable, corrupt, packed-GN, memory, missing sub-cache. End-to-end fluid/GN/soft-body/particle fixtures (heavy sims) remain a pre-launch to-do. |
| **F21** | Version runs incomplete | **Open (environment).** Only Blender 5.2.3 is installed here. 4.2/4.5/5.0 runs are a pre-launch step on Keith's machine. |

## Section 5 — Marketplace

| ID | Finding | Resolution |
|----|---------|------------|
| **F22** | Empty permissions table | **Fixed.** `files` and `clipboard` declared (≤64 chars each); `network` left undeclared. Validates and builds clean. |
| **F23** | Built artifact / license | **Noted.** Extension validates and builds; SPDX `GPL-3.0-or-later` in the manifest is the required notice. |
| **F24** | Over-broad "verified against disk" claim | **Fixed.** Report footer now distinguishes disk-verified caches from UNKNOWN/N-A cases (memory, packed GN, unsaved). |

## Still requires real Blender runtime to certify (pre-launch, Keith's machine)
- Headless test runs on Blender **4.2, 4.5, 5.0** (4.4 for F13).
- Heavy-sim end-to-end fixtures: a real fluid bake (incl. deleted mesh/noise),
  a Geometry Nodes disk bake, soft-body and particle caches.
- GUI acceptance test on the newest version.

---

# Re-review v2 responses (commit 0178405 → this commit)

The second review confirmed F01's core fix and found more promote-partial-
evidence-to-PASS paths. All are addressed below; the test suite grew from 61 to
**77** on Blender 5.2.3, now with real bakes rather than only constructed objects.

| ID | Finding | Resolution |
|----|---------|------------|
| **R01** | Fluid mesh/noise sub-cache checked for "any file", not every frame | **Fixed.** Each enabled sub-cache (mesh/noise) is scanned over the full required range; a frame counts only if data **and** every enabled sub-cache has it. Missing sub-cache frames → INCOMPLETE. Proven by a **real fluid bake** fixture that deletes one `fluid_mesh` frame → #18 FAIL. |
| **R02** | #19 still PASSed an incomplete bake (never called the verdict) | **Fixed.** #19 now consults `cache_status()`: it only PASSes when the configured range covers the render range **and** the cache is actually COMPLETE on disk (or a baked memory cache). The F01 regression now forbids a PASS on #19 too — that's the gap that let this slip. |
| **R03** | GN metadata could PASS without its `blobs/` data | **Fixed.** When `meta/` has frames, `blobs/` must exist and be non-empty, else the bake is INCOMPLETE ("blob data" missing). Unit-tested. |
| **R04** | `cache_status()` COMPLETE + #17 "is baked" even when the baked flag is off | **Fixed.** When files are complete but Blender's baked flag is off, #17 now returns a WARNING ("files present but flag off — may be stale"), not a definitive "baked" PASS. #18 still PASSes (the files genuinely exist) — that's #18's question. |
| Fluid matcher too permissive (`unrelated_0001.vdb`) | **Fixed.** Matcher now requires the real `fluid_<component>_NNNN.<ext>` prefix (verified against a real bake), so stray files aren't counted. |
| Scanners used `getsize` but never opened files | **Fixed.** `_file_state()` now opens each file for a byte; a non-zero-size but unreadable file is reported, not passed. |
| #21/#22 global PASS with unresolved paths | **Fixed.** Both return UNKNOWN when any relevant cache path couldn't be resolved, instead of a blanket PASS. |
| c16 counted OUTFLOW as a source | **Fixed.** OUTFLOW is separated from inflow/geometry sources; a domain with only an outflow (or effector) warns "no flow source". |
| Export overwrite via header match | **Fixed.** Export now always creates a fresh, uniquely-named text block (Blender appends .001/.002); it never overwrites anything. |
| UI "No issues" implied verified | **Fixed.** Now "No problems reported (toggle the eye for details)" with an info icon, not a checkmark. |
| **F13 correction** (reviewer noted it was not resolved) | **Reworked.** `_iter_action_fcurves()` now prefers the slotted representation (every layer/strip/channelbag) and only falls back to legacy `action.fcurves` when there are no layers or the slotted path yielded nothing — so it no longer short-circuits on the legacy first-slot view. Still needs a real 4.4/4.5 run to certify. |
| `run_all_versions.sh` passed with zero binaries | **Fixed.** Exits non-zero if no Blender binary was found (an empty matrix is a failure, not a pass). |

## New tests (77 total on 5.2.3)
- **Real-bake integration:** soft-body disk cache (+deleted last frame), particle
  cache (+deleted last frame), and a fluid liquid+mesh bake with a deleted data
  frame **and** a deleted mesh frame — all correctly FAIL.
- **#19** added to the F01 regression's forbidden-PASS set.
- **GN unit tests:** INHERIT→modifier target resolution, and metadata-without-
  blobs → INCOMPLETE.
- **Read-only checks:** Scan leaves selection, active object, current frame and
  the object set unchanged.

## Still requires other-version / GUI runtime (pre-launch, Keith's machine)
- Headless runs on Blender **4.2 / 4.5 / 5.0** (4.4/4.5 specifically for F13).
- A live **Geometry Nodes disk bake** integration test (scripting one headlessly
  is fragile; the INHERIT/blobs logic is unit-tested here).
- GUI acceptance test; Windows path coverage; a before/after filesystem snapshot
  around Scan on disposable projects.

---

# Re-review v3 note (commit bbbaa72 → this commit)

The v3 review was run against a **stale zip** (an earlier `physics_preflight_
review_current.zip`, before the v2 fixes were rebuilt into it), so its R01–R06
findings were already fixed in commit `bbbaa72` (fluid per-component scanning,
#19 using `cache_status()`, GN blobs, #17 stale-flag, the `fluid_` matcher,
#21/#22 UNKNOWN, file-read checks, OUTFLOW, slotted actions, UI wording,
run_all_versions). Two findings were genuinely still present and are fixed here:

| ID | Finding | Resolution |
|----|---------|------------|
| **R07** | GN custom *path* wrongly triggered custom *frame-range* handling (range came out 0–0) | **Fixed.** Range logic extracted to `_gn_bake_range()`; only a custom frame range or a still-frame bake changes the range. Unit-tested (custom path → scene range). |
| **#18 text** | "missing 0 of N frames" shown when only a sub-cache was incomplete | **Fixed.** When data frames are all present but a sub-cache (mesh/noise/particles) or GN blob data is missing, #18 says "cache is incomplete: &lt;what&gt;" and #20 stays silent. |
| Fluid particle sub-cache | not checked | **Added.** Liquid spray/foam/bubble/tracer particle caches are now verified per-frame like mesh/noise. |

Test suite: **81/81 on Blender 5.2.3.**
