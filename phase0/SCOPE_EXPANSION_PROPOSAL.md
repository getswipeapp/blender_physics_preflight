# Physics Preflight — Scope Expansion Proposal (draft for Keith)

Date: 2026-11-09 · Status: PROPOSAL, nothing built.

## Goal
Keith: "If Triage has 5 of the 8, why can't we widen the gap so we're still the better option?"
Triage is a broad 98-check generalist ($9.99). Physics Preflight should be **the physics & simulation specialist**: deeper checks in that one area than any generalist, plus cache verification nobody else does properly.

We do **not** claim Triage lacks any check below unless its full list confirms it. Until then, Triage coverage = UNKNOWN.

## Proposed v1 check list (original 11 + 12 new = 23)

Legend for "API": ✅ property confirmed present on Blender 4.2.23 and 5.2.3 (`evidence/probe_scripts/extra_api.py`) · 🧪 behaviour already runtime-tested in Phase 0.
Every check still needs pass/fail fixtures on every supported version before it may be advertised.

### Physics Setup (8 original + 8 new)
| # | Check | Why beginners hit it | API |
|---|---|---|---|
| 1 | Unapplied scale/rotation on physics objects | Wrong collision size, odd spin | 🧪 |
| 2 | Suspicious rigid-body mass (vs size/density) | Heavy pebbles, feather bricks | 🧪 |
| 3 | Initial intersections **incl. one object fully inside another** | Objects explode on frame 1 | 🧪 (containment test required) |
| 4 | Collision shape mismatch (e.g. Convex Hull on a bowl) | Things float/fall through | 🧪 |
| 5 | High-poly or non-manifold colliders | Slow or unstable sims | 🧪 |
| 6 | Rigid Body World disabled / low substeps / wrong collection | "Nothing moves" | 🧪 |
| 7 | Cloth/soft-body collision config (no colliders, collision off) | Cloth falls through floor | 🧪 |
| 8 | Negative scale & scaled parents | Inverted normals, wrong sizes | 🧪 |
| **9** | **Real-world size sanity**: objects tiny/huge for the scene unit scale | Bullet is unstable at mm or km scale | ✅ |
| **10** | **Origin far from geometry** on active rigid bodies | Wobbly, off-centre spin | ✅ |
| **11** | **Collision margin too large for object size** | Visible gaps, hovering objects | ✅ |
| **12** | **Animated passive object not marked "Animated"** | Animated collider is ignored | ✅ |
| **13** | **Broken rigid-body constraints**: missing object 1/2, disabled | Chains/hinges fall apart | ✅ |
| **14** | **Collision modifier stack order** (collider deformed after Collision) | Cloth collides with the wrong shape | ✅ |
| **15** | **Cloth pin group set but empty / missing** | Flag/curtain falls to the floor | ✅ |
| **16** | **Fluid: flow/effector objects outside the domain, or domain with no flow** | Empty fluid sim | ✅ |

### Simulation Caches (3 original + 4 new)
| # | Check | Why it matters | API |
|---|---|---|---|
| 17 | Is the simulation baked? (with UNKNOWN where Blender can't tell) | Renders differ from viewport | 🧪 |
| 18 | **Every expected cache file present and nonempty, without trusting Blender's "baked" flag** | Blender says "baked" after files are deleted (all 4 versions) | 🧪 |
| 19 | Baked range covers the render range | Sim freezes mid-shot | 🧪 |
| **20** | **Frame gaps**: check every frame, not a sample | A single missing frame = a pop in the render | 🧪 (file pattern known) |
| **21** | **Two simulations writing to the same cache name/folder** | One sim silently overwrites the other | ✅ |
| **22** | **Non-portable caches**: absolute paths, outside the project folder, external/library caches | Breaks on another machine or render farm | ✅ |
| **23** | **FPS or time-scale changed after baking** | Sim plays at the wrong speed | ✅ (needs a recorded baseline; may become UNKNOWN-only) |

### Optional third group: Render Readiness (Keith to decide)
Missing textures, absolute paths, no camera, invalid output folder, collections excluded from render.
These are cheap to build and make the "replaces 3 add-ons" claim true. The trade-off is scope and test time.

## Positioning
- Headline idea: **"23 physics & simulation checks in one click — replaces Triage + Cache Guardian for about half the price."** (Only once every claim is test-confirmed; competitor names in ads need Keith's OK and Superhive policy check.)
- Differentiators that are runtime-proven today: file-level cache verification (#18, #20) and containment-aware intersection check (#3).

## Cost of widening
- Each new check needs a passing and a failing fixture on every supported version: 12 new checks × 2 fixtures × 4 versions ≈ 96 extra automated test runs. That's cheap headless, but the GUI test load grows.
- More checks means more false-positive risk. Each needs a clear threshold and plain-English wording, with WARNING (not FAIL) where judgement is involved (#2, #9, #10, #11).

## Decisions for Keith
1. Approve the 23-check list (or trim/add).
2. Include the Render Readiness group in v1, or save it for v1.1?
3. Price (stack it replaces ≈ $24–27).
4. Name: keep "Physics Preflight" (MotionLab reportedly uses it as a feature name) or rename.
5. Fluid fixtures: allow download.blender.org here, or run on Keith's Mac.
