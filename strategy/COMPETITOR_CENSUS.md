# Competitor Census — Blender render-preflight / sim-cache checkers

> **⚠️ Superseded for competitor facts (2026-11-13).** Prices/capabilities in this
> Phase-0 census are unverified and partly stale (e.g. Cache Commander is ~$29 with
> a background-process batch mode). Use `strategy/FEATURE_MATRIX.md` (verification-
> labelled) as the source of truth; re-check each live Superhive listing before any
> public use.

*2026-11-11. Systematic sweep of Superhive (category/tag pages + searches), read
off live listings. ~80–85% complete for the niche; the tier that matters most
(tools that verify sim caches **on disk**) is believed fully captured. Prices are
as listed (several were on sale); flagged items need re-verification.*

## The full field (sorted by relevance to us; closest first)

| Product | Price | Checks sim cache **files on disk**? | Read-only? | Auto pre-render? |
|---------|------:|-------------------------------------|------------|------------------|
| **Cache Guardian** — *Pre-Render Validator* | $14 | **Yes — but SAMPLED** (start/end/interior frames, "instead of exhaustively reading every frame") + fingerprint staleness | Default yes; 1-click Re-bake | **Yes**, opt-in non-blocking |
| **Cache Commander** — *size/cleanup + move* | ~$9.99 ⚠️ | **Yes** on disk; flags stale + orphan caches, shared-dir clashes; "check a folder" background mode | Scan read-only; then delete/move | No on-render; has a **pipeline command** (clean/blocking/could-not-check) |
| **MotionLab** — *motion analysis* | $39 ⚠️ | **Partial — Rigid Body only**; Windows-only | Read-only (preflight part) | Not stated |
| SceneCheck | $3 | Baked-*flag* only (Pro) | Fixes available | On **save**, not render |
| RabbidRender Inspector | $2.99 | Flag only ("cache risks") | **Read-only** | Pre-job, not F12 |
| Zap Doctor | $9 | Flag only ("unbaked sims") | Fixes (revertable) | No |
| Preflight (Skava) | $9.99 | Flag only | **No** — renders a test frame | Not stated |
| RenderForge | $20 | No (lighting/materials/Cycles) | Approval-gated | **Blocks** render until passed |
| FinalCheck | $1 / free | No (current-frame only) | Fixes | **Yes** on render |
| Triage / CG General | $7.49 | No — ~98 general checks | **Read-only** | No |
| Render Guard (NovaStrikes) | $19.99 Pro | No (crash prevention) | Optimizers destructive | **Yes** (Pro) |
| RenderSense | $4.99 | No (scene-cost analysis) | — | No |
| PBR Validator | $9.99 | No (materials) | Fixes | — |
| Scene Doctor | $15 | No (geometry/materials health score) | **Read-only** | No |
| Scene Ready | $5.25 | No (export readiness) | Dry-run + safe fixes | Export, not render |
| Store Ready | $9 | No (marketplace submission) | Modifies | No |
| SceneHelm | $24.90 | No ("missing files") | Modifies | Manual rerun |
| Sampleproof | $9.99 | No (sample-count advisor) | Writes report | No |
| Render Visibility Check | $5.90 | No (render-visibility) | Modifies | No |

## The part that answers "do we know the field?" — yes, for the tier that counts

**Only THREE products actually read simulation caches on disk.** Everyone else in
the "render preflight" crowd only reads Blender's in-scene *bake flag* — the exact
thing that lies after you delete the files. Our head-to-head tier:

1. **Cache Guardian ($14)** — the closest. Covers all 6 sim types, but **samples**
   frames (start/end/interior). Has fingerprint staleness + opt-in auto-pre-render
   + 1-click re-bake.
2. **Cache Commander (~$9.99)** — **new to us.** Verifies caches on disk and finds
   stale/orphan/shared caches, but it's positioned as a *size + cleanup + move*
   tool, not a render-readiness gate. Notably it already has a **folder/pipeline
   command** (the studio angle).
3. **MotionLab ($39)** — Rigid Body **only**, Windows-only, inside a motion-analysis
   product. Barely a competitor for our scope.

## Where Failsafe is differentiated from each (the wedge)

- **vs Cache Guardian:** we verify **every frame**; they sample. A missing middle
  frame can pass their check and freeze a render — our demo case exactly. We also
  report honest UNKNOWN and cover the fluid sub-caches (guiding/config) + GN bakes.
- **vs Cache Commander:** they clean/move caches by size; we're the **render-safety
  gate** with full-frame verification + physics *setup* checks too. Different job,
  and we're deeper on integrity. (They do have a pipeline command — relevant if we
  build headless later.)
- **vs MotionLab:** we cover **all** sim types, cross-platform, far cheaper.

## Pricing landscape for our tier
Cache Commander ~$9.99 · Cache Guardian $14 · MotionLab $39. With "does more for
less," Failsafe lands best at **$9–12** — undercut Cache Guardian, roughly match
Cache Commander, while doing more than both (full-frame + all sim types + setup
checks + honest UNKNOWN).

## Corrections to earlier notes
- **MotionLab** is listed **$39**, not $9 (one earlier pass said $9 — disputed, re-verify).
- **Blend Inspector** ($4.99) is **not on Superhive** — it's on a separate site; drop it from the Superhive competitor set.
- **Cache Commander** was missing from all earlier passes — it's a real second disk-cache competitor.

## Honest completeness caveat
~80–85% of the render-preflight niche captured; Superhive's search is JS-rendered
so some **newer/low-traffic listings may be missing**, and this micro-niche is
clearly growing fast (many 2025–2026 launches). The **sim-cache-on-disk tier is
confidently complete** (3 products). New entrants will keep appearing — treat this
as a current snapshot, not a permanent list.
