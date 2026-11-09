# Response to the Independent Code Review (2026-11-09)

Status after fixes: **all confirmed defects addressed; test suite 61/61 on
Blender 5.2.3**, including new regression tests that reproduce the reviewer's
scenarios. Items that need real multi-version / heavy-sim runtime to *certify*
are called out as pre-launch to-dos (only Blender 5.2.3 is installed here).

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
