# Physics Preflight — Phase 0 Report (Roadmap v3)

Date: 2026-11-09 · Scope: revised competitor kill gate + permitted technical feasibility probe · No implementation started.

## 0. Correction from Keith (2026-11-09): the $9 price was never his requirement

Keith's actual concept: **one app that combines the useful pieces of several apps, so a buyer doesn't have to buy A + B + C, at a lower price than those standalone apps together.**
The "$9 or less" kill condition was introduced in AI-drafted roadmap text, not specified by Keith. It is withdrawn. The gate is re-stated as:

> **KILL if a single existing product already combines the same pieces (physics setup + cache verification [+ render readiness if in scope]) at or below the price we would need to charge to undercut the standalone stack.**

**The standalone stack a buyer would need today** (prices verified via screenshots or search snippets):

| To get… | Buy | Price |
|---|---|---|
| Physics setup checks (partial: scale, non-manifold, substeps, cloth collision) + unbaked sims | Triage | $9.99 |
| Full cache checks (baked, files on disk, range coverage) | Cache Guardian | $14.00 |
| Render-readiness basics (missing textures, paths, camera, output) | SceneCheck or RabbidRender Inspector | $3.00 / $2.99 |
| **Stack total** | | **≈ $24 (setup + cache) to ≈ $27 (with render readiness)** |

Still **not covered by any paid product**: mass sanity (#2), initial intersections including containment (#3), collision-shape mismatch (#4), and true file-level cache verification that does not trust Blender's "baked" flag (§3b).

**Re-evaluated gate: NOT TRIGGERED.** No single product combines setup and full cache checks. Triage is closest on setup and Cache Guardian on caches. Together they cost ≈ $24.
**Price room:** anything clearly below ≈ $24 meets the "cheaper than buying A + B + C" test. A price is Keith's decision (§5).

## 1. Verdict

**Kill gate (re-stated in §0): NOT TRIGGERED → PROCEED, pending Keith's review of Triage (§1c). The $9 condition below is superseded by §0 and kept only for the record.**

No single product meets all three kill conditions (≥5 of 8 setup checks AND all 3 cache checks AND ≤ $9 AND well-reviewed). The nearest products miss in different ways:

| Candidate | ≥5/8 setup checks? | All 3 cache checks? | ≤ $9? | Well-reviewed? | Kills? |
|---|---|---|---|---|---|
| Cache Guardian (Superhive/Skillshare) | **No** (0/8) | Yes (but samples frames for #10) | **No** ($14 ✔) | No sales/rating shown ✔ | No |
| ELTIGA/blender-qc-audit (GitHub) | Partly: 3 YES + 5 PARTIAL | **No** (partial on all 3) | Yes (free, MIT) | **No** (0 stars, 2 weeks old, headless script, no UI) | No |
| SceneCheck (Superhive) | **No** (0/8) ✔ | **No**: #9 only (Pro); #10/#11 not described ✔ | Yes ($3; Pro appears to be a preferences toggle) | No sales/rating shown ✔ | No |
| RabbidRender Inspector (Superhive) | **No** (no physics-setup area in its 31 checks) ✔ | Partial/UNKNOWN ("simulation bake and cache risks") | Yes ($2.99) | No sales/rating shown ✔ | No |

**Evidence limitation (important):** Superhive, Gumroad, Skillshare, blendermarket.com and extensions.blender.org are **blocked by this cloud session's network policy**. Pages could not be opened directly. Superhive/Gumroad data comes from search-engine snippets of those pages, and ratings, sales counts and dates are mostly **UNKNOWN**. GitHub data is first-hand: the source of 3 tools was read. Before launch, Keith should open the 4 listings above in a browser to confirm their ratings and sales. This would only matter if Scenecheck's "Pro" tier turned out to include physics-setup checks, which nothing found suggests.

## 1b. Owner browser verification (Keith, 2026-11-09 10:46–10:47, screenshots in `evidence/owner_screenshots_2026-11-09/`)

| Product | Verified on page | Effect on gate |
|---|---|---|
| Cache Guardian | **$14**, Salman Naseem, published **3 months ago**, Blender **3.2–5.2**, extension-compatible. **No Sales or Rating rows shown** in the Details panel (FinalCheck's panel shows both, so these appear to be absent or below the display threshold). | Still fails on price (> $9) and has no setup checks. |
| SceneCheck | **$3**, Salman Naseem, published **4 months ago**, listing says Blender **3.2–5.2** but its text says "4.2 LTS or newer, tested through 5.x". **No Sales or Rating rows.** About page (pasted text): **6 included checks**: missing textures, unpacked data, absolute paths, camera, output path, render-excluded collections. **2 "Pro" checks**, "enabled in preferences" (no separate Pro price is shown, so Pro may be **included in the $3**): addon dependencies, and **Simulation Cache Checks**: "scans every Cloth, Soft Body, Fluid, Dynamic Paint, Particle, and Rigid Body World simulation **for a baked cache**". It offers Fix / Fix All for paths and packing. | Fails: **0/8 setup checks**. Cache: #9 **Y** (Pro). #10 **N/U**: it describes only "has a baked cache", with no mention of verifying files on disk or nonempty files. If it relies on Blender's flags, it would hit the false-PASS trap in §3b. #11 **N/U**: no frame-range coverage mentioned. |
| FinalCheck | **$1**, Omine, **80+ sales, 5★ (3 ratings)**, published **over 4 years ago**, Blender **2.9–4.5**. Checks: missing files, render region, view-layer/collection/object visibility. | Fails: 0/8 setup checks, no cache checks. |
| RenderToolbox (Gumroad) | **$0+** (pay what you want), **5★ (3 ratings)**. Buttons: Scene Diagnostics, Save Scene, Extract Assets, Animation/Material/DataBlock/Visibility/Lighting/Mesh Reports, Pack Resources, **Bake Action** (animation bake, not a sim cache check), Make Local. | Fails: no physics-setup or sim-cache checks visible. |
| ELTIGA/blender-qc-audit | **0 stars, 0 watching, 0 forks, 2 commits, last commit 2 weeks ago**, MIT. Described as a "Headless QC audit skill for AI agents". | Fails "well-reviewed"; partial on cache checks; no UI. |

| RabbidRender Inspector | **$2.99**, GPL, v1.0.0, published **about 2 months ago**, Blender **4.5–5.2** (tested on Windows only), extension-compatible. **No Sales or Rating rows shown.** "31 focused checks" in six areas: camera/frame range/engine/output; render borders/compositor; missing or non-portable images/libraries/**caches**; render-state differences; **"Simulation bake and cache risks"**; lighting/color management/inventory. Read-only, offline, no telemetry. | Fails: no physics-setup area listed (0/8 evident; the list says "areas such as", so strictly UNKNOWN, but every area is about render readiness). Cache coverage is plausibly #9 and partly #10, with #11 UNKNOWN. Not well-reviewed (no ratings). |

**RabbidRender takeaway:** this is the **closest low-price overlap on caches** ($2.99). It is not a kill, but it means the cache half of Physics Preflight is **not unique** at the low end. The listing must lead with what nobody else does: the **8 physics-setup checks** and **real file-level cache verification** (Blender's own flags can say "baked" when the files are gone, see §3b). Because RabbidRender describes its cache coverage only as "risks", its exact behavior should be treated as UNKNOWN, not as absent.

**Gate result after verification: still NOT TRIGGERED, and now with stronger evidence.** None of the four verified Superhive/Gumroad products under $9 contains a single physics-setup check. The only cache checker with visible traction data has none shown.

## 1c. Reconciliation with ChatGPT's Phase 0 draft (2026-11-09)

**New competitors from ChatGPT's sweep that mine missed:**

| Product | Status | Effect on gate |
|---|---|---|
| **Triage** (CG General, Superhive) | Confirmed by search snippet: **$9.99**, "98-check diagnostic tool", read-only, Blender 4.2–5.2. Snippet examples: "Physics object with unapplied scale", "Cloth simulation with no Collision objects". ChatGPT also cites negative scale, non-manifold geometry, high rigid-body substeps and unbaked simulations. Sales and ratings UNKNOWN. | **Closest competitor found.** Partial coverage of setup items 1, 5, 6, 7 and 8 (5 items, all partial or unproven) plus cache #9. It fails the gate only on **price ($9.99 > $9)** and on unconfirmed cache checks #10/#11. **This is the single biggest commercial risk:** a $9.99 tool with 98 checks against our $9 tool with 11. **A sale on Triage would satisfy the price condition**, so the gate depends on #10/#11 and reviews. |
| **MotionLab** (Superhive, $9) | Not reachable from my searches. Per ChatGPT: uses **"Physics Preflight" as an internal feature name** and documents rigid-body frame-range coverage (#11). | Not a kill. **Name collision**: recommend Keith decide whether to rename (e.g. "Sim Preflight", "Physics & Cache Check") before any listing work. |
| Physics Dropper ($4, 3,300+ sales, 43 ratings), KaBRICK ($7.50), OMI Physics Body glTF (free), NVIDIA SimReady (free) | Setup and export tools, not diagnostics. | Not kills. |

**Where the two reports differ (my runtime results take precedence over documentation-only claims):**

| Topic | ChatGPT draft | This report (runtime-tested, §3) |
|---|---|---|
| Runtime proof | "No real Blender tests run; runtime UNKNOWN" | Probes **were run** on Blender-built `bpy` 4.2.23 / 4.5.15 / 5.0.1 / 5.2.3. This is not the full GUI binary, so **certifying the official binaries and GUI is still outstanding**, and both reports agree on that. |
| Rigid Body disk cache | "Conditional disk verification" | **Not applicable.** The rigid-body cache is memory-only and stored in the .blend. Setting `use_disk_cache` on it **segfaulted 4.2.23**. |
| Trusting `is_baked` / `has_cache_baked_*` | Listed as the bake-state access | **Unsafe alone.** Both stay True after the disk cache is deleted (all 4 versions). File-level checks are mandatory. |
| Particles | "Investigate; not yet claimed" | Same `.bphys` disk pattern confirmed. Feasible. |
| GN zones | "Reliable verification UNKNOWN" | Disk bakes: feasible via `meta/*.json`. **Packed bakes: confirmed undetectable** (no RNA change), so UNKNOWN. |
| Fluid | Feasible | API feasible, but **fluid fixtures need official binaries** (Mantaflow broken in the `bpy` wheel). |
| GUI test on every version | v3 controls; not reduced | Agreed this is Keith's call. It **cannot be done in this cloud environment** (no display or GUI binary). |
| GPL | Buyers may redistribute | Agreed. A commercial limitation, not a blocker. |

**Updated gate statement:** NOT TRIGGERED, with a **narrower margin than §1 suggested**. Triage is one price cut or two confirmed cache checks away from being a serious threat. Phase 1 should not start until Keith has seen Triage's full check list.

## 1d. Triage full check list, fetched directly (2026-11-09, after the network change)
Source: `evidence/competitor_pages/triage_listing_fetched_2026-11-09.txt`. The listing says "This is the full list." It shows 98 checks in 7 categories.
Details: **$9.99**, published 3 months ago, Blender 4.2–5.2, GPL, seller "TheFridge". **No Sales or Rating rows.**

Every physics/simulation-related Triage check (all others are performance, render, geometry, materials, lighting, organisation or rigging):
- Unbaked Cloth / Soft Body / Fluid domain / Rigid Body world / high-count particle system → our cache #9 (baked?). Nothing about files on disk (#10) or frame-range coverage (#11).
- High Rigid Body sub-steps → part of our #6 (performance angle only)
- Unapplied object scale; Physics object with unapplied scale → our #1 (scale only, no rotation)
- Negative object scale → our #8 (no scaled-parent check listed)
- Non-manifold geometry (all meshes) → our #5 (generic; no high-poly collider check)
- Cloth simulation with no Collision objects → our #7 (one case)
- Extreme force field strength → not in our list

**Not in Triage at all:** mass sanity (#2), initial intersections/containment (#3), collision-shape mismatch (#4), rigid body world disabled/collection problems, cache files on disk (#10), frame-range coverage (#11), and all 12 proposed new checks.
**Result:** Triage covers 5 of our original 8 setup checks partially and 1 of 3 cache checks. Against the 23-check plan (SCOPE_EXPANSION_PROPOSAL.md) it overlaps on about 6, mostly partially. The planned gap holds.

**MotionLab (fetched directly 2026-11-09):** $9, published 3 months ago, Blender 4.5+, **Windows x64 only**. It is a motion-data recording/analysis tool (speed, acceleration, CSV/JSON export). "Physics Preflight" is the name of **one small feature inside it**: "reports potential cache or frame-coverage problems" for **Rigid Body simulations only**. It is not a competing product. The name overlaps only at feature level, so **Keith keeps the name "Physics Preflight"** (decision 2026-11-09).

## 2. Competitor matrix

Items: 1 scale/rotation · 2 mass · 3 intersections · 4 collision-shape mismatch · 5 high-poly/non-manifold colliders · 6 RBW/sim settings · 7 cloth/soft-body collision config · 8 negative scale/scaled parents · 9 baked? · 10 disk files present & nonempty · 11 bake range covers render range.
Y = yes · P = partial · N = no · U = unknown (not stated, so not assumed absent). ✔ = confirmed by Keith's screenshots 2026-11-09.

| Product | Store / price | Age / traction | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 9 | 10 | 11 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Cache Guardian (Salman Naseem) | Superhive $14 ✔; Skillshare | Published 3 months ago ✔; Blender 3.2–5.2 ✔; no sales/rating shown ✔ | N | N* | N | N | N | N | N | N | Y | P (samples start/end/some interior frames) | Y |
| SceneCheck (Salman Naseem) | Superhive $3 ✔ ("Pro" toggle in prefs; no separate Pro price shown) | Published 4 months ago ✔; 4.2+ per text ✔; no sales/rating shown ✔ | N | N | N | N | N | N | N | N | Y (Pro) ✔ | N/U ✔ | N/U ✔ |
| RabbidRender Inspector | Superhive $2.99 ✔, GPL, v1.0.0 | ~2 months old ✔; 4.5–5.2 (Windows-tested) ✔; no sales/rating shown ✔ | N/U | N/U | N/U | N/U | N/U | N/U | N/U | N/U | Likely Y ("simulation bake and cache risks") | P ("missing or non-portable … caches") | U |
| Cache Commander | Superhive $29, v1.2.1 | U | N | N | N | N | N | N | N | N | P | P | U |
| Oh My Bake | Superhive $5.50 | U | N | N | N | N | N | N | N | N | P (bake tool, "Bake Missing") | U | U |
| FinalCheck | Superhive $1 ✔ / Gumroad | 80+ sales, 5★ (3) ✔; >4 yrs old ✔; 2.9–4.5 ✔ | N | N | N | N | N | N | N | N | U | U | U |
| BlendBuddy ("Scene Doctor") | Superhive $9.99 | U | P (generic) | N | N | N | N | N | N | N | N | N | N |
| SceneHelm | Superhive, price U | v1.0–1.5 beta | P (generic) | N | N | N | P (generic non-manifold) | N | N | N | N | N | N |
| Unit & Scale Doctor / Transform Checker / Scale Alert | Superhive/Gumroad, prices U | U | P–Y (scale only) | N | N | N | N | N | N | P–Y | N | N | N |
| JiggleMaker | Superhive, price U | U | P (alerts: unapplied transforms) | N | N | N | N | N | N | N | P (cloth bake admin) | U | U |
| RenderToolbox | Gumroad $0+ ✔ | 5★ (3) ✔ | N | N | N | N | N | N | N | N | N | N | N |
| Render Ready (Core) | own site, from $19, online activation | "85+ checks" claim | U | U | U | U | U | U | U | U | U | U | U |
| **ELTIGA/blender-qc-audit** (source read) | GitHub, free MIT ✔ | 0★ / 0 forks / 2 commits ✔; created 2026-10-26 | P | Y | Y | P | P | Y | P | P | P | P (fluid dir non-empty only) | P (rigid body only) |
| swstl/clanker_blender render_preflight (source read) | GitHub, free, no licence | 1★, 2026-11-04 | N | N | N | N | N | N | N | N | Y | P (GN folder only) | N |
| GermanCGArtist bbr_preflight (source read) | GitHub, free MIT | 1★, Oct 2026 | N | N | N | N | N | N | N | N | Y | P | N |
| extensions.blender.org | free | — | No physics/cache diagnostic found (Quick Rigid is a settings panel) | | | | | | | | | | |

\*Cache Guardian fingerprints mass/stiffness only to detect stale bakes, not to judge mass.

**Positioning gap confirmed:** Nobody sells "physics setup + cache" in one beginner tool. The two halves exist separately: Cache Guardian covers caches for $14, and blender-qc-audit covers setup for free but has no UI and is aimed at AI agents. Checks 1 (rotation), 5 (high-poly colliders), 7 (cloth collision config) and 8 (scaled parents) are not covered by anyone.

**Competitive risk to note:** The seller Salman Naseem has both Cache Guardian ($14) and Scenecheck ($3). They are the most likely to add setup checks. Price pressure at the low end is real ($1–$3 validators exist).

## 3. Technical feasibility (real Blender, headless)

Run on **Blender 4.2.23 LTS, 4.5.15 LTS, 5.0.1 and 5.2.3 LTS**, using the official `bpy` module builds from PyPI on Linux x86-64. Scripts and raw JSON are in `evidence/`. Results were the same on all four versions unless noted.

### 3a. Physics setup checks (1–8): all feasible with read-only APIs
Confirmed on all 4 versions: object scale, rotation, `matrix_world.determinant()` (negative or mirrored scale), parent scale, `rigid_body.mass/collision_shape/type`, evaluated-mesh face count, bmesh non-manifold edge count, `BVHTree.overlap`, `RigidBodyWorld.enabled/substeps_per_frame/solver_iterations/collection`, and cloth `collision_settings`.
**Design catch:** a BVH surface-overlap test returned **0 overlaps for a body fully inside another**. Check 3 needs a separate containment test (point-inside), or it will give a false PASS.

### 3b. Cache checks: what Blender's API can and cannot establish

| System | #9 baked? | #10 disk files present & nonempty | #11 range covers render range |
|---|---|---|---|
| Cloth | `point_cache.is_baked` (see trap) | Feasible **only by our own file check**: `blendcache_<blend>/<HEX(name)>_<frame:06d>_<index:02d>.bphys` | Feasible: `point_cache.frame_start/end` vs scene |
| Soft body | same as cloth | same as cloth | same |
| Rigid Body World | `is_baked` (persists in .blend) | **NOT APPLICABLE**: memory-only cache stored in the .blend | Feasible |
| Fluid (Mantaflow) | `has_cache_baked_data/mesh/noise/particles` (see trap) | Feasible by scanning `cache_directory` subfolders (`config/`, `data/`, `mesh/` …) | Feasible: `cache_frame_start/end` |
| Particles | `point_cache.is_baked` | same `.bphys` pattern (confirmed) | Feasible |
| GN simulation zone, **disk** bake | **No API flag.** Infer from `<bake_directory>/<bake_id>/meta/*.json` | Feasible (meta + blobs files) | Feasible from meta filenames (frame numbers) |
| GN simulation zone, **packed** bake (4.3+) | **UNKNOWN: not determinable.** Baking packed changed **no** Python-visible property (only the .blend grew ~15 KB) | NOT APPLICABLE | **UNKNOWN** |

**Two false-PASS traps found (core selling point, since Blender itself misreports):**
1. **Cloth / soft body:** after baking to disk, **deleting the cache folder** and reopening the .blend, Blender still reports `is_baked=True` and `info="10 frames on disk."` (all 4 versions).
2. **Fluid:** `has_cache_baked_*` flags remain `True` after the cache folder is removed, and were `True` even when only a config file had been written.
→ The add-on must never treat Blender's flags as proof. It must check the filesystem and report UNKNOWN where it cannot.

Also note: rigid body `is_outdated` reads `True` after simply reopening a correctly baked file, so it **must not** be used as a "stale" signal.

### 3c. Blockers and risks found (documented, not hidden)
- ~~**Fluid fixtures cannot be produced with the PyPI `bpy` build.**~~ **RESOLVED in §3e with official binaries.** Mantaflow baking is broken there (`'LevelsetGrid' object has no attribute 'setConst'`, then `Manta::Error` abort/segfault on all 4 versions). Fluid test fixtures need **official Blender binaries**, and download.blender.org is blocked in this session. This is either a network change for this environment or a job for Keith's machine.
- **Graphical UI tests are impossible here** (the bpy module has no UI). This agrees with Claude's v3 note: run headless on all versions, run the GUI test on the newest version plus Keith's acceptance test.
- Setting `use_disk_cache=True` on the Rigid Body World cache **segfaults Blender 4.2.23**. This is irrelevant to a read-only tool, but test fixtures must never do it.
- Only Linux was tested. Windows and macOS path handling (hex filenames, `//` relative paths, library-linked caches via `use_library_path`, external caches via `use_external`) need test coverage.

### 3e. Re-run on OFFICIAL Blender binaries (2026-11-09, after the network change)
Official Linux x64 builds **4.2.23 LTS, 4.5.15 LTS, 5.0.1, 5.2.3 LTS** were downloaded from download.blender.org and **verified against Blender's published SHA-256** (`evidence/binary_probe_results/official_blender_downloads.sha256`). All probes ran in background mode (`blender -b`). **Every case exited cleanly on every version.** Results: `evidence/binary_probe_results/<version>/SUMMARY.txt`.

Same on all 4 versions:
- **Cloth & soft body:** after the disk cache is deleted and the file reopened, Blender still reports `is_baked=True`, "10 frames on disk". **False-PASS trap confirmed on the real app.**
- **Fluid ("All" bake mode):** bakes all frames as `config/config_NNNN.uni` + `data/fluid_data_NNNN.vdb`. After the files are deleted and the file reopened: **0 files, but `has_cache_baked_data=True`.** **Trap confirmed for fluid.** Per-frame file names mean checks #10, #19 and #20 are feasible.
- **Fluid ("Replay" mode, tested on 5.2.3):** "Bake All" wrote **only frame 1** yet reported baked, and **reopening the file re-creates frame 1**. Replay caches are playback caches, not bakes. The add-on must report them as WARNING ("Replay cache — frames are generated on playback; a render farm may re-simulate"), never as PASS.
- Rigid body: baked state persists in the .blend; `is_outdated` reads True after a normal reopen (do not use it as a stale signal).
- Particles: disk bake works (`.bphys`).
- Geometry Nodes disk bake works. **Packed bakes show no Python-visible change** (4.5, 5.0, 5.2); 4.2 has no packed bakes.
- Setup-check APIs and all APIs for the 12 proposed new checks: present on all 4 versions.

**Blocker from §3c resolved:** fluid fixtures can now be produced. The earlier failures were specific to the PyPI `bpy` build.
**Still outstanding:** the graphical UI test (no display here; Keith's Mac, newest version), and Windows/macOS path tests.

### 3d. Proposed supported matrix for v1 (pending binary + GUI tests)
- Blender **4.2 LTS, 4.5 LTS, 5.0, 5.2 LTS** (extension format requires 4.2+).
- Cache checks: Cloth, Soft Body, Rigid Body (#9, #11; #10 N/A), Particles, Fluid (Mantaflow), GN simulation zones with **disk** bakes. GN **packed** bakes report UNKNOWN for "baked" and "range".
- Dynamic Paint and hair dynamics are out of scope for v1 and should be listed in Limitations.

## 4. Marketplace / policy notes
- Superhive accepts GPL-compatible Blender add-ons. A pure-Python extension is GPL-bound, which is normal there (RabbidRender is GPL at $2.99).
- No network, telemetry or licensing server is needed, so there is no policy conflict.
- No blocker found. Not verified against Superhive's current seller terms (site blocked here).

## 5. Recommended next steps (all need Keith's go-ahead where noted)
1. ~~Keith: spot-check listings~~ DONE for Cache Guardian, SceneCheck, FinalCheck, RenderToolbox and ELTIGA (§1b). RabbidRender Inspector and the SceneCheck About page also DONE. No competitor checks remain open.
2. ~~Environment: allow download.blender.org~~ DONE (approved by Keith 2026-11-09); official binaries verified and probed (§3e).
3. Begin Phase 1 build with the matrix in §3d. Marketing angle: "Blender can say a sim is baked when the files are gone. Physics Preflight checks the actual files."
4. Price (Keith decides): the stack it replaces costs ≈ $24–27 (§0). Options: **$12–15** ("half the price of Triage + Cache Guardian"), or **$9.99** (matches Triage, harder to justify fewer checks). Lead the listing with "replaces 2–3 add-ons" and the real file check, not with price alone.

## 6. Evidence index
- `evidence/probe_scripts/`: probe.py (caches), setup_probe.py (setup APIs), gn_packed.py, run_all.sh, summarize.py
- `evidence/probe_results/<version>/`: raw JSON per case, SUMMARY.txt, setup_probe.txt, gn_packed.txt, fluid_bake_errors.txt
- `evidence/competitor_sources/`: GitHub source of the 3 free tools that were inspected
- `evidence/owner_screenshots_2026-11-09/`: Keith's 8 browser screenshots + RabbidRender and SceneCheck listing text
- `SHA256SUMS`: hashes of every file above
