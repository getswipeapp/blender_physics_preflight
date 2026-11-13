# Competitor Gap List — everything they do that we don't (yet)

> **⚠️ Superseded for competitor facts (2026-11-13).** This Phase-0 gap list cites
> unverified competitor data (e.g. "Render Ready $19/49/99", Cache Commander
> pricing) that the independent review did not confirm. Use `strategy/FEATURE_MATRIX.md`
> (verification-labelled) for competitor claims; treat the entries here as an
> internal build-idea backlog, not verified market fact.

Read from the live product pages 2026-11-12. This is the build list. Goal
(Keith's): **do everything the competitors do, and more, for less money.**

Our price target: **$12**. Competitors: SceneCheck $3, Cache Commander $9.99,
Cache Guardian $14, Render Ready $19 / $49 / $99.

What we ALREADY beat them on (keep, don't lose):
- **Every required frame verified on disk** (Cache Guardian only samples; the
  rest check first/last or just the flag). Nobody else does per-frame.
- **UNKNOWN status** — we never bluff a pass. No competitor has this.
- **Physics *setup* checks + cache checks in one tool** (16 setup + 7 cache).
  Cache Guardian/Commander are cache-only; SceneCheck/Render Ready don't do
  physics setup at all.

---

## TIER A — cache / sim gaps (our wheelhouse). BUILD. Makes us beat Guardian + Commander outright.

| # | Feature | Who has it | We have it? | Plan |
|---|---------|-----------|-------------|------|
| A1 | **Staleness: settings changed since bake** (fingerprint of mass/stiffness/res) | Cache Guardian, Cache Commander | Partial — we read Blender's `is_outdated` flag only (unreliable headless) | Add our own fingerprint compare |
| A2 | **Cloud-synced cache path warning** (Dropbox/GDrive/OneDrive/iCloud) | Cache Guardian | No | BUILD — new check #24 |
| A3 | **Orphan / unclaimed cache files** (files on disk no sim owns) | Cache Commander | No | BUILD — new check #25 |
| A4 | **Cache size / disk usage per sim + total** | Cache Commander | No | BUILD — add to report + check |
| A5 | **Alembic (.abc) cache verification** (MeshSequence/Transform cache) | Cache Commander | No | BUILD — new inspector + check #26 |
| A6 | **Headless CLI with exit codes** (0 clean / 1 blocking / 2 unverified) | Cache Commander | No (handler only, unproven) | BUILD — new `cli.py` |
| A7 | **JSON report output** | SceneCheck, Cache Commander (HTML) | No (text + clipboard only) | BUILD — add JSON |
| A8 | **Batch: scan a folder of .blend files headless** | Cache Commander | No | BUILD (pairs with A6) |
| A9 | **HTML report** | Cache Commander, Render Ready | No | Phase 2 (JSON first) |

## TIER B — general render-readiness gaps (SceneCheck / Render Ready territory). Cheap table-stakes → BUILD; the rest is a scope decision.

| # | Feature | Who has it | We have it? | Plan |
|---|---------|-----------|-------------|------|
| B1 | **Missing textures** (image file not on disk) | SceneCheck, Render Ready | No | BUILD (cheap, universal) |
| B2 | **No active camera / camera hidden from render** | SceneCheck, Render Ready | No | BUILD (cheap) |
| B3 | **Invalid output path** (folder missing / not writable) | SceneCheck | No | BUILD (cheap) |
| B4 | **Collection with meshes excluded from render** | SceneCheck | No | BUILD (cheap) |
| B5 | **Absolute paths on images/libs/sounds/clips** | SceneCheck | Partial (cache paths only) | Extend |
| B6 | **Unpacked external data warning** | SceneCheck | No | BUILD (cheap) |
| B7 | **Add-on dependency detection** (nodes from non-built-in add-ons) | SceneCheck (Pro), Render Ready | No | Phase 2 |
| B8 | **Material health** (broken links, empty slots, colorspace) | Render Ready | No | Phase 2 |
| B9 | **Output/format/resolution safety checks** | Render Ready | No | Phase 2 |
| B10 | **Workflow presets** (Animation / Still / Game / ArchViz / 3D Print / Farm) | Render Ready | No | Phase 2 |
| B11 | **VRAM / render-time / scene-bloat estimates** | Render Ready (Studio $99) | No | Later / maybe |

> **Scope decision for Keith (B7–B11):** building all of Tier B turns Failsafe
> from a *simulation* checker into a *general render-readiness* suite — i.e. a
> direct Render Ready ($19–99) / SceneCheck ($3) competitor. The cheap ones
> (B1–B6) are worth grabbing now so we're not *missing* basics. The deep ones
> (B7–B11) are a real second product's worth of work. I'll build B1–B6 and stop
> there unless you say "go all the way."

## TIER C — destructive cache tools. Conflict with our read-only promise.

| # | Feature | Who has it | Decision |
|---|---------|-----------|----------|
| C1 | **Delete caches** | Cache Commander | Skip — breaks read-only. We *detect* orphans (A3); user deletes. |
| C2 | **Move caches** (byte-verified relocate) | Cache Commander | Skip for v1 — breaks read-only. Possible opt-in later. |
| C3 | **Re-bake button** | Cache Guardian | Maybe — user-triggered, calls Blender's own bake op. Low priority. |

---

## Build order (this is what I'm doing)

1. A2 cloud path, A3 orphans, A4 size, A7 JSON — fast, read-only, pure parity/wins.
2. A5 Alembic, A1 fingerprint staleness — moderate.
3. A6 CLI + exit codes, A8 batch folder — the render-farm answer.
4. B1–B6 cheap render-readiness checks.
5. Re-test headless on all four Blender versions. Only then is any of it "done."
