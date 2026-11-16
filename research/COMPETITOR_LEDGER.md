# Failsafe — Master Competitor Ledger (Stage 1 competitive intelligence)

> Built 2026-11-15 from a line-by-line read of each product's live Superhive pages
> (About / Docs / FAQ). Prices and version claims are from the listings on that date
> and can change. Statuses: **VERIFIED BETTER** (Failsafe already beats it),
> **VERIFIED MATCH** (parity), **GAP** (they have it, Failsafe likely doesn't —
> verify in our code), **NOT VERIFIED**, **TECHNICAL LIMITATION**.
>
> Failsafe-side claims marked *(verify in code)* are from project memory, not yet
> re-confirmed against the current source — Stage 2 must confirm each before we rely on it.

## ⚠️ VERIFIED UPDATE (2026-11-15) — read BUILD_ROADMAP.md

A source-grounded code inventory ran after this ledger was first drafted. Many rows
below marked "GAP *(verify)*" turned out to be **already built**: exhaustive every-frame
check, path-portability (#22), cloud-sync detection (#24, broader than any rival),
shared-dir (#21), bake-covers-render (#19), orphan detection (#25), headless CLI with
honest exit codes, batch folder scanning, and JSON reports all EXIST today. The genuine
remaining gaps are only: hair/Dynamic-Paint cache coverage, deep content-integrity
parsing, HTML report, persistent finding-dismissal, and (by design) repairs. See
BUILD_ROADMAP.md for the verified state and phased plan.

## Price map

| Product | Price | What it really is |
|---|---|---|
| RabbidRender Inspector | **$2.99** | Broad one-click render-readiness verdict (31 checks, list not public) |
| SceneCheck | **$3** | 8-check delivery validator with one-click fixes |
| Triage | **$9.99** | Broad 98-check read-only scene auditor |
| Cache Commander | **$9.99** | Simulation-cache inventory / cleanup / delivery QC (headless) |
| Preflight | **$9.99** | Render preflight that renders a real probe frame to measure render time |
| Cache Guardian | **$14** | **The direct rival** — simulation-cache checker + pre-render validator |
| RenderForge | **$20** | Cycles render-gate validator (blocks render until pass) |
| **Failsafe (ours)** | TBD | Physics-setup + simulation-cache reliability, exhaustive, read-only |

## The single most important finding

**Cache Guardian — our closest competitor — only SAMPLES cache frames.** Its own
docs say so, verbatim: it checks "start, end, and several interior frames rather than
every file," and admits "a gap between sampled frames could theoretically still be
missing, which is why this is documented as a known limitation." 

**Failsafe checks every required frame.** *(verify in code)* This is our strongest,
most defensible advantage and the core of the storefront message: **we catch the
missing frame the $14 tool can miss.**

---

## Competitor-by-competitor capability ledger

### Cache Guardian — $14 — THE DIRECT RIVAL
Covers 6 sim types (Cloth, Fluid/Mantaflow, Rigid Body, Soft Body, Particles, Geometry
Nodes zones; **Dynamic Paint not mentioned**). Blender 4.2–5.x. Cycles/Eevee. GPL.

| Capability | Category | Failsafe status |
|---|---|---|
| Baked-status check (all 6 types) | diagnostic | VERIFIED MATCH *(verify)* |
| On-disk cache present & non-empty | diagnostic | VERIFIED MATCH |
| **Every-frame disk verification** | diagnostic | **VERIFIED BETTER** — theirs is SAMPLED, ours exhaustive *(verify)* |
| Staleness via settings fingerprint at bake (mass, stiffness, resolution, frame range…) | diagnostic | PARTIAL — we have #26 settings + #23 FPS; breadth across all sim types = **GAP** *(verify)* |
| Frame-range-vs-render-range coverage | diagnostic | GAP? — we check missing frames in range; "bake stops short of render range" may differ *(verify)* |
| Cache path portability (absolute paths won't survive a move) | diagnostic | **GAP** — easy, valuable add |
| Shared cache directory warning (one bake overwrites another) | diagnostic | **GAP** — easy, valuable add |
| Cloud-synced cache path warning (Dropbox/Drive/OneDrive/iCloud) | diagnostic | **GAP** — easy, valuable add |
| Geometry Nodes sim-zone bake detection (heuristic) | diagnostic | **GAP?** — confirm we cover GN zones *(verify)* |
| Re-bake button (explicit, per-item) | automation/repair | GAP — needs hybrid decision |
| Export Report (plain text, next to .blend) | output | VERIFIED MATCH |
| Check-before-render popup (non-blocking) | safety | VERIFIED MATCH |
| Headless: checks run in `--background` (popup is UI-only) | pipeline | VERIFIED MATCH *(verify)* |
| Honest staleness disclosure (documents heuristic) | safety | VERIFIED MATCH (our "Couldn't verify") |
| **No multi-file batch / conflict / rebake-queue (planned Pro)** | limitation | OPPORTUNITY — we can ship batch first |

### Cache Commander — $9.99 — cache inventory / cleanup / delivery QC
Cloth, soft body, rigid body, particles, smoke, sim-node bakes, Alembic. Blender 4.2+.

| Capability | Category | Failsafe status |
|---|---|---|
| Per-cache inventory with size + owner | diagnostic | GAP — size reporting is a cheap bonus |
| Stale detection (mutation-tested) + unclaimed-file detection | diagnostic | PARTIAL |
| **Delete / Move cache files (byte-verified, repoint)** | automation/repair | GAP — cleanup lane; hybrid-only if we want it |
| Alembic listing + safe relocation | automation/repair | GAP (lower priority) |
| **Multi-file: check every .blend in a folder (each in own background Blender)** | pipeline | **GAP** — high value for studios |
| **Headless CLI, exit codes 0/1/2/3 where "did not run" ≠ pass** | pipeline | **GAP** — matches our honesty rule; must-have |
| **Self-contained HTML report** (verdict-first, offline) | output | **GAP** — strong upgrade over our text report |
| Baseline save + "what changed since last run" diff | diagnostic | GAP — nice-to-have |
| Sign-off record stored in .blend | safety | GAP (optional) |
| "Whole Delivery" — runs every installed tool in one pass | pipeline | OPPORTUNITY (ecosystem play) |

### Triage — $9.99 — broad read-only scene auditor (98 checks)
Read-only, "diagnoses, doesn't fix." Severity grades Critical/High/Low/Info.
Domains: Performance 23, Render 19, Geometry 16, Materials 13, Lighting 8, Scene-org 5,
Animation/rigging 14.

| Capability | Category | Failsafe status |
|---|---|---|
| Physics checks: unbaked cloth/softbody/fluid/rigid/particles | diagnostic | VERIFIED MATCH (ours deeper) |
| Cloth sim with no collision objects | diagnostic | VERIFIED MATCH (our physics-setup group) |
| Physics object with unapplied scale; extreme force-field; high substeps | diagnostic | PARTIAL — some may be **GAP** *(verify)* |
| **Severity grading (Critical/High/Low/Info)** | output | PARTIAL — we have FAIL/WARN/UNKNOWN/PASS/NA |
| **Dismiss intentional findings, persisted per-scene** | GUI | **GAP** — good UX, worth copying |
| 98 broad checks (render/geo/materials/lighting/rigging) | diagnostic | OUT OF LANE — do NOT chase the count |
| No export format, no headless | limitation | Failsafe already beats (we export + headless) |

### SceneCheck — $3 — delivery validator with fixes
8 checks (About says 6 base + 2 Pro; FAQ says all 8 — listing contradicts itself).
Missing textures (UDIM-aware), unpacked, absolute paths, camera, output path, hidden
collections, addon dependency, **simulation cache check**.

| Capability | Category | Failsafe status |
|---|---|---|
| Sim-cache baked check (6 sim types) | diagnostic | VERIFIED MATCH (ours deeper + exhaustive) |
| One-click Fix / Fix All / pack / relativize paths | automation/repair | GAP — hybrid-only |
| Auto-run on save (non-blocking) | safety | GAP — easy add |
| Export .txt and .json | output | PARTIAL — we do text; **JSON = GAP** |
| Missing-texture / unpacked / path checks | diagnostic | OUT OF LANE (asset-delivery, not physics) |

### Preflight — $9.99 — render preflight + real render-time measurement
Cycles/Eevee. Read-only (temp probe restored). Flags unbaked sims (one check only).

| Capability | Category | Failsafe status |
|---|---|---|
| **Renders a real probe frame to MEASURE render time** | diagnostic | GAP — out of lane, possible optional feature |
| Settings fingerprint before/after + restore | safety | VERIFIED MATCH (our baseline) |
| Unbaked-sim flag | diagnostic | VERIFIED MATCH (ours far deeper) |
| Camera / output / overwrite / frame-range render checks | diagnostic | OUT OF LANE (render-readiness) |
| Report into a text block in the .blend | output | VERIFIED MATCH-ish |

### RabbidRender Inspector — $2.99 — broad readiness verdict
31 checks (individual list NOT public — 6 broad areas). Read-only, offline.
One area = "simulation bake and cache risks" (no detail). 3-state verdict + score.
Copy Report (text) + Save JSON.

| Capability | Category | Failsafe status |
|---|---|---|
| 3-state readiness verdict + deterministic score | output | PARTIAL — our pills are similar |
| JSON export | output | **GAP** |
| Broad render-readiness areas (camera, assets, color mgmt…) | diagnostic | OUT OF LANE |
| Simulation bake/cache risk (undetailed) | diagnostic | VERIFIED BETTER (ours is the whole product) |

### RenderForge — $20 — Cycles render-gate
Blocks final render until lighting/materials/noise/settings pass. No physics checks.
(Docs page confusingly describes a different AI product — listing is inconsistent.)

| Capability | Category | Failsafe status |
|---|---|---|
| Blocks render until validation passes | safety | OPTIONAL — we could add an opt-in gate |
| Lighting/material/noise/Cycles-settings checks | diagnostic | OUT OF LANE |
| No simulation/physics checks | — | Failsafe wins this lane outright |

---

## Where Failsafe already WINS (verified)
1. **Exhaustive every-required-frame disk check** vs Cache Guardian's admitted sampling. *(verify in code — this is our #1 claim, must be rock-solid)*
2. **Dedicated physics-SETUP checks (pre-bake)** — missing colliders etc. Cache tools don't do this; Triage only touches it shallowly.
3. **Frame-rate timing baseline (#23)** — no cache rival has it. (Not "unique" overall — a niche extension has a version — but unique among these rivals.)
4. **Explicit "Couldn't verify"/never-false-PASS** state. (Cache Commander shares the spirit: "a check that did not run is never reported as a pass" — so claim it as a strength, not an exclusive.)
5. **Cross-version certification** (4.2/4.5/5.0/5.2) vs rivals' self-contradictory version claims.

## Biggest GAPS to close (ranked by customer value)
1. **Geometry Nodes simulation support** — modern Blender, both cache rivals have it. *(verify current coverage)*
2. **Multi-file / whole-folder batch scanning** — studios need it; only Cache Commander has it.
3. **Headless CLI with honest exit codes** (did-not-run ≠ pass) — perfect fit for our honesty rule.
4. **JSON + HTML report formats** — pipeline-friendly; several rivals have JSON, Cache Commander has HTML.
5. **Cache path portability + cloud-sync + shared-dir warnings** — three cheap, high-value checks (copy Cache Guardian).
6. **Broader staleness/settings-drift fingerprinting** across all sim types.
7. **Persistent dismissal of intentional findings** (Triage) — UX.
8. **Cache content/integrity validation** — *nobody does this well* (all only check "present/non-empty"). Our chance to lead, not just match.
9. **Opt-in authorized repairs** (re-bake / add collider) — needs the read-only decision.

## Out of lane (do NOT chase without a scope decision)
General render preflight (camera/output/textures/render settings — Triage/Preflight/
RabbidRender/SceneCheck), render-time probe (Preflight), cache deletion/cleanup
(Cache Commander), render gating (RenderForge). A focused "render readiness" group is a
reasonable later add; a 98-check generalist is not the goal.

## Sources
All Superhive product pages (About/Docs/FAQ), read 2026-11-15:
cache-guardian-simulation-cache-checker--pre-render-validator ·
cache-commander--see-what-your-simulations-weigh-and-move-them · triage ·
scenecheck-one-click-scene-validator-for-error-free-renders-and-deliveries ·
preflight--find-out-what-will-go-wrong-before-the-render-starts ·
rabbidrender-inspector · renderforge
