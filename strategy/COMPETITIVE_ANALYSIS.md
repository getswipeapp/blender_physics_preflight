# Physics Preflight — Competitive Analysis & Roadmap

*Prepared by Claude, 2026-11-10. Market data from live web research (sources at
the end). This is Claude's independent take; a separate neutral brief
(`CHATGPT_REVIEW_BRIEF.md`) asks ChatGPT for its own, so the two can be compared.*

> **⚠️ CORRECTION (2026-11-10, after ChatGPT's review + verification).** My §1/§3
> claim that *no competitor checks physics/sim caches* was **wrong**. ChatGPT's
> independent review found several, and I verified the pages directly. The
> accurate, verified landscape and the reconciled plan are in **`GAMEPLAN.md`** —
> read that, not the table below, for the real competitive picture. The roadmap
> in §5 here still broadly holds (both reviews agree on it). Keeping this file as
> an honest record of the first pass.

---

## 1. TL;DR

- **Our moat is real and unusual:** across the Blender "preflight / validation /
  inspector" category, **no competitor verifies physics or simulation caches at
  all.** They validate meshes, materials, UVs, naming, and export-readiness.
  Nobody checks "is this sim actually baked on disk, frame by frame." Blender
  itself still has **no scene-wide cache overview** (an open feature request).
- **But Keith's instinct is also correct:** competitors win on **breadth**. A
  $4.99 tool ships ~8 scene-health checks *plus* texture/VRAM/file-size audits
  *and* one-click fixes. Next to them, a physics-only tool can *look* thin even
  though it's deeper where it counts.
- **Recommendation:** don't ship bare, and don't rewrite. **Go deeper in our
  lane** (make the physics/cache story undeniable and automatic) and **add just
  enough breadth** to not look narrow — then price for the value, not the
  check-count.

## 2. The market (who we're up against)

All of these are on Superhive (formerly Blender Market). None touches physics
caches — the overlap with us is only the handful of generic "scene health"
checks.

| Add-on | What it does | Physics/sim cache? | Price |
|--------|--------------|--------------------|-------|
| **Blend Inspector** | .blend diagnostic: 8 scene-health checks (unapplied transforms/rotation, negative scale, origin, unused material slots, high-poly, missing UVs, duplicate mesh data) + file-size/VRAM/texture audits; has one-click fixes; "[Select]" affected objects | ❌ none | **$4.99** |
| **Scene Ready** | Preflight QA for export targets (glTF/Unity/Unreal/USD); dry-run mode; READY / WARNINGS / BLOCKED status; naming, collections, geometry, cleanup | ❌ none | ~low (not listed) |
| **Store Ready** | Marketplace-delivery checks (default names, unpacked/missing textures) before upload | ❌ none | low |
| **PV Asset Validator** | Pre-export asset issues: mesh names, modifiers, material counts, scale, UV ranges | ❌ none | low |
| **Mesh Check** | Topology only (N-gons, open edges, coincident verts, non-applied scale) | ❌ none | low |
| **SmartScene ToolKit** | Bundle incl. "Scene Sanity Tools" (vague) | ❌ none | bundle |

**Read on the market:** validation tools sell, they cluster at **$5–$15**, they
compete on breadth + one-click fixes + polished UI, and **physics/sim integrity
is a blank space none of them fill.**

## 3. Where we already win

1. **Physics/sim cache integrity — uniquely.** Cloth, soft body, particles,
   rigid body, fluid (Mantaflow: data/mesh/noise/particles/guiding/config),
   geometry-nodes bakes. Nobody else does any of this.
2. **"Never a false PASS."** We verify the actual files on disk frame-by-frame
   instead of trusting Blender's "baked" flag (which stays true after the files
   are gone). This is a *trust* story no competitor tells — and you proved it
   live by deleting the cache and watching us catch it.
3. **Read-only & safe.** Changes nothing, writes nothing (certified).
4. **Certified broadly.** Headless pass on Blender 4.2 / 4.5 / 5.0 / 5.2 + a real
   GUI acceptance test. Most small add-ons can't show this.

## 4. Where we look thin (the honest gaps vs competitors)

- **Breadth of checks.** 23 is respectable, but they're concentrated in physics.
  Competitors spread across mesh/materials/textures/UV/naming/export.
- **No "fix it" affordance.** Competitors offer one-click fixes; we're
  deliberately read-only. (Keep the safety, but we can add *guided* fixes — jump
  to the exact panel — without becoming an auto-changer.)
- **Manual-only.** You must remember to press Scan. Competitors are the same, but
  this is our chance to leapfrog them (see roadmap #1).
- **No pipeline/headless story.** Nothing for render farms or batch.
- **UI is functional but plain** (see §6).

## 5. Recommended roadmap (ranked by value-to-effort)

Built from Claude's earlier recommendations + the competitive gaps + Keith's own
ideas. Grouped into "v1 (ship-worthy)" and "v1.1 / v2 (sell-up)".

**Make v1 genuinely compelling:**
1. **Auto-run before render / on save (Keith's idea).** A toggle that runs the
   checks automatically when you hit Render or save, and warns if a sim cache is
   broken. Turns the product from "remember to scan" into a *safety net*. This is
   the single highest-value add and directly answers "humans are lazy."
2. **Guided fixes (stay read-only).** Each finding gets a "take me there" button
   to the exact panel/setting (we already do "Select object"). Lowers the skill
   needed to act — without silent auto-changes that would break our trust story.
3. **Built-in "why it matters / how to fix" per check.** You hit this yourself
   ("what does #23 mean?"). Short plain-English explanations make it valuable to
   beginners — a big slice of buyers.
4. **A little adjacent breadth** so we don't look narrow: a few high-value
   non-physics checks that still fit "will this render correctly" (e.g. missing/
   unpacked textures used by sims, output path sanity, a couple of the
   scene-health staples). Enough to broaden appeal without becoming a mesh tool.

**Sell-up / studio tier (v1.1 / v2):**
5. **Headless / CLI mode + JSON output.** Run preflight from a render-farm
   submission script, machine-readable results. Moves us from a $10 artist tool
   into *pipeline insurance* studios pay more for. Genuinely unique in the
   "artist-owned preflight" space.
6. **Render-manager hooks** (Flamenco / Deadline) building on #5.
7. **Mute / ignore list** ("I know about this one").
8. **More sim coverage** (Alembic / USD caches, hair, linked-library caches).
9. **Report export formats** (HTML / CSV / JSON for sharing).
10. **Profiles/presets** ("render farm" vs "solo artist" check sets).

## 6. UI assessment ("is no-frills normal?")

Short answer: our UI is **clean and functional but plainer than the category
leaders.** Competitors lean on status badges (READY/WARNINGS/BLOCKED), grouped
collapsible sections, "[Select]" jump buttons, and summary counts — several of
which we now have (colored severity icons, collapsible findings, clickable
severity filters, Select-object). So we're close to parity after the last two
updates. To fully match/raise the bar: a cleaner header with an overall
pass/warn status badge, per-check "learn more", and tidier spacing. This is worth
a focused UI pass, and worth asking ChatGPT to critique against competitor
screenshots.

## 7. Open business decisions (Keith's calls)

- **Scope for v1:** physics-deep only, or physics-deep + a little adjacent
  breadth? (Claude leans: add a *little* breadth + auto-run, then ship.)
- **Price:** the category sits $5–$15; our depth + certification could support the
  upper end, and a future studio/headless tier could be more.
- **Fixes philosophy:** keep strictly read-only, or add *guided* (not automatic)
  fixes? (Claude: guided only — protects the trust story.)
- **Windows:** test it, or launch Mac/Linux-only and honest.

## Sources
- [Scene Ready — Superhive](https://superhivemarket.com/products/scene-ready-cleanup-export-qa/docs)
- [Blend Inspector — Superhive](https://superhivemarket.com/products/blend-inspector)
- [Store Ready — Superhive](https://superhivemarket.com/products/store-ready)
- [PV Asset Validator — Superhive](https://superhivemarket.com/products/pv-asset-validator)
- [Mesh Check — Superhive](https://superhivemarket.com/products/mesh-check-)
- [SmartScene ToolKit — Superhive](https://superhivemarket.com/products/smartscene-toolkit)
- [Blender issue: scene-wide cache overview not implemented](https://projects.blender.org/blender/blender/issues/107290)
- [Baking Physics Simulations — Blender Manual](https://docs.blender.org/manual/en/latest/physics/baking.html)
- [Blender Cycles render-farm pre-flight checklist](https://irendering.net/blender-cycles-render-farm-pre-flight-checklist/)
