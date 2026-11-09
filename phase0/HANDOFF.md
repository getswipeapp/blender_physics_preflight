# Physics Preflight — Handoff to the next Claude session

Written 2026-11-09 at the end of the cloud Phase 0 session. Give this file (and this folder) to the new chat.

## THE GOAL: this is a commercial product, built to be SOLD
Physics Preflight is an **AI Income Lab** product. The point of all this work is to **sell a paid Blender add-on on Superhive** (formerly Blender Market, superhivemarket.com) and make money from it. Every decision should serve that goal: a product beginners will actually pay for, a listing that sells it honestly, and a launch Keith approves.

**Owner:** Keith (GitHub: getswipeapp). Keith is not a developer. Explain things in plain English, make sensible technical decisions yourself, and only ask Keith about business decisions (price, publishing, money, accounts).

**Product concept (Keith's own words, summarized):** *one add-on that combines the useful pieces of several add-ons, so a buyer doesn't have to buy app A + B + C, at a better price than those standalone apps.*

**Value proposition:** "Physics setup + simulation cache checks in one click." It is a beginner-friendly, read-only diagnostic that finds physics-setup mistakes and broken/missing simulation caches **before** you render.

**Why people would buy it (positioning):**
- Today a buyer needs **Triage ($9.99) + Cache Guardian ($14) ≈ $24** to get partial coverage, and still misses many checks.
- Physics Preflight is **the physics & simulation specialist**: 23 checks vs about 6 physics checks in Triage.
- **Killer selling point (proven by tests):** Blender can say a simulation is "baked" when the cache files are gone. Physics Preflight checks the **actual files**. Competitors that trust Blender's flag give a false "all good".
- Draft listing headline: **"Physics Preflight — Check Physics Setup + Simulation Caches in One Click"**

**Price:** NOT decided. Keith decides later. Context: the stack it replaces costs about $24–27. The earlier "$9" was invented by an AI and is NOT a requirement.

## Road to sale (roadmap phases still ahead)
- **Phase 1 — Build:** pure Python, Blender extension format, no dependencies, offline, read-only, one-click scan, plain-English results, select the affected object, export a text report. Results grouped under "Physics Setup" and "Simulation Caches".
- **Phase 2 — Tests:** a passing and a failing test scene for every check, plus cache fixtures (baked/unbaked, valid disk cache, missing/empty cache, in-memory, incomplete and complete frame range, unsupported/unreadable). Headless tests on every supported Blender version. GUI test on the newest version. **No false PASS.**
- **Phase 3 — Delivery package:** installable extension .zip, source, test fixtures, **genuine screenshots**, a short demo video, beginner instructions, a limitations list, a SHA-256 manifest, and a review package for an independent Claude review.
- **Phase 4 — Commercial launch:** **Keith personally approves** seller registration, price, the listing text, publishing and payment setup. Never create accounts, spend money or publish anything without Keith's explicit OK.

**Definition of finished:** all checks built and tested on the supported versions → independent Claude review PASS on the exact package → Keith completes a beginner acceptance test → Keith approves publication → the listing goes live.

**Selling rules:**
- **Advertise only features confirmed by tests.** Never claim a check works on a version or sim type that wasn't tested. Where Blender can't tell, the product says UNKNOWN, and the listing says so too (limitations section).
- **Licence:** Superhive requires GPL-compatible add-ons. Buyers may legally redistribute GPL code. That is a commercial limitation, not a blocker; it's normal on Superhive. Write all code originally; do not copy competitors' code.
- Don't name competitors in the listing without Keith's OK.
- No network access, telemetry or paid AI calls inside the product.

**After launch (commercial proof):** track 30-day sales, refunds, marketplace fees and support requests, and decide stop/continue using the thresholds in Keith's Roadmap v2 (ask Keith for them; they are not in this repo). Ten sales is an experiment milestone, not proof of profitability.

**Planned v1.1 (after launch):** optional, user-clicked, undoable "Fix" buttons for safe cases (e.g. apply scale). That adds more value at the same price.

## Where things stand
- **Phase 0 is done.** Competitor research and the technical feasibility probe are both complete. See `PHASE0_REPORT.md`.
- **Competitive result:** no product combines physics-setup checks with real cache verification. The closest is **Triage** ($9.99, 98 generic checks, about 6 overlapping ours, mostly partially) plus **Cache Guardian** ($14, caches only). Together that stack costs about $24.
- **Keith's actual product concept** (supersedes the "$9" in Roadmap v3): one add-on that combines the useful pieces of several add-ons, cheaper than buying them separately. Gates are guidance, not the final word.
- **Scope decided:** build the **23 checks** in `SCOPE_EXPANSION_PROPOSAL.md` (16 physics setup + 7 cache). Leave out non-physics "render readiness" checks (missing textures, camera and so on); cheap tools already do those.
- **Name:** keep "Physics Preflight". MotionLab only uses it as the name of a small feature.
- **Price:** not decided yet. Keith will decide later.

## Technical facts the build MUST respect (proven on official Blender 4.2.23 / 4.5.15 / 5.0.1 / 5.2.3)
1. **Never trust Blender's "baked" flags alone.** For cloth, soft body and fluid, `is_baked` / `has_cache_baked_*` stay True after the cache files are deleted. Check the files on disk.
   - Point-cache files: `blendcache_<blendname>/<HEX(cache name or object name)>_<frame:06d>_<index:02d>.bphys`
   - Fluid "All" bake: `<cache_directory>/config/config_NNNN.uni`, `data/fluid_data_NNNN.vdb` (mesh/noise/particles subfolders when enabled)
   - GN disk bake: `<bake_directory>/<bake_id>/meta/NNNNN_*.json` + `blobs/`
2. **Fluid "Replay" mode is not a bake.** It reports baked after writing only frame 1, and reopening the file re-creates frames. Report a WARNING, never PASS.
3. **Rigid Body World cache is memory-only** (stored in the .blend). The disk check is NOT APPLICABLE. Never set `use_disk_cache` on it: that segfaulted Blender 4.2.
4. Rigid body `is_outdated` reads True after a normal reopen, so do not use it as a "stale" signal.
5. **Geometry Nodes packed bakes (4.3+) are invisible to Python.** "Baked" and "range" must report UNKNOWN for them.
6. **Intersection check needs a containment test.** BVH overlap returns 0 for an object fully inside another.
7. Statuses: PASS / WARNING / FAIL / UNKNOWN / NOT APPLICABLE. No false PASS. Read-only, offline, no telemetry, no auto-fixes.

## Next steps (Phase 1)
1. Build the extension (pure Python, Blender extension format with `blender_manifest.toml`, Blender 4.2+). One-click scan, two result groups (Physics Setup / Simulation Caches), plain-English messages, "select affected object", export a text report.
2. For every check, make a passing and a failing test .blend and run headless tests on 4.2, 4.5, 5.0 and 5.2 (`blender -b --factory-startup -P test.py`).
3. The GUI test on the newest version plus Keith's beginner acceptance test, on Keith's Mac.
4. Also test macOS and Windows file paths (cache folder names, `//` relative paths).

## Useful files
- `evidence/probe_scripts/`: working probe scripts. `probe.py` builds and bakes cloth/soft body/rigid/fluid/particle/GN test scenes. Run it with `blender -b --factory-startup -P probe.py -- <outdir> <case>`. Set `FLUID_CACHE_TYPE=ALL` for real fluid bakes.
- `evidence/binary_probe_results/`: raw results per Blender version.
- `evidence/competitor_pages/`, `evidence/owner_screenshots_2026-11-09/`, `evidence/competitor_sources/`: competitor evidence.
- `SHA256SUMS`: integrity manifest for every file.
