# Physics Preflight — Reconciled Gameplan

*2026-11-10. Merges two independent reviews (Claude + ChatGPT) with
directly-verified competitor data. This supersedes the competitive picture in
`COMPETITIVE_ANALYSIS.md` (whose "no competitor" claim was wrong).*

---

## 1. The verified competitive landscape

All rows below were read from the live product pages (not guessed). Prices are
the sellers' listed prices.

| Product | Price | Checks sim CACHE FILES on disk? | Every frame or sampled? | Auto pre-render? | Read-only? |
|---------|------:|---------------------------------|-------------------------|------------------|------------|
| **Cache Guardian** (Salman Naseem) | **$14** | **Yes** ("checks disk, not just the flag") | **Sampled** — "start, end, and interior frames... instead of exhaustively reading every frame" | **Yes**, opt-in non-blocking warning | Default yes; one-click **Re-bake** fix |
| **SceneCheck** (Salman Naseem) | $3 | Baked-*state* only (not files on disk) | n/a | On **save**, not render | Checker + Fix buttons |
| **MotionLab** (Tesselune) | $9 | No (reports "cache/frame-coverage" but doesn't read disk); **Windows-only**, 4.5+ | n/a | No (manual) | Preflight part: yes |
| **Preflight** (Skava) | $9.99 | No (only "never baked"); **renders a test frame** | n/a | No (manual) | **No** — changes settings while probing |
| **Triage / CG General** | $9.99 | No — 98 *general* scene checks | n/a | No | Yes (read-only) |
| **Blend Inspector** | $4.99 | No — mesh/scene health + audits | n/a | No | Has fixes |

**The one that matters: Cache Guardian ($14).** It is our true head-to-head
competitor — same problem, same "check the disk not the flag" pitch, plus a
pre-render warning and a re-bake button we don't have yet.

## 2. Our real, verified edge (this is the whole pitch)

Reading Cache Guardian's own page hands us a sharp, *provable* differentiator:

1. **We verify EVERY frame; Cache Guardian samples.** Their page literally says
   they spot-check start/end/interior frames "instead of exhaustively reading
   every frame." A missing middle frame between their sample points can pass
   their check and **freeze a render** — the exact case our full-frame
   enumeration (and the F01 work) was built to catch. This is demonstrable in a
   15-second video.
2. **Honest UNKNOWN, never a false PASS.** A trust story none of them lead with.
3. **Broadest sim coverage.** Cloth, soft body, particles, rigid body, fluid
   (data/mesh/noise/particles/**guiding**/**config**), and geometry-nodes bakes.
4. **Cross-platform + multi-version certified** (4.2/4.5/5.0/5.2 headless + a GUI
   test). MotionLab is Windows-only; others' ranges vary.

**Where Cache Guardian is currently ahead of us** (the gaps to close): opt-in
**auto pre-render warning**, and a one-click **re-bake** affordance.

## 3. Where both reviews agree (high confidence)

- **Stay narrow and deep** — don't become a general scene checker (Triage,
  Preflight, Blend Inspector already own that). Own "simulation cache + physics
  setup, verified exhaustively."
- **Guided fixes, not automatic fixes** — keep the read-only trust story; add
  "take me to the right panel" buttons. (Cache Guardian's one-click re-bake shows
  the market wants *some* fix affordance — guided/opt-in is the safe version.)
- **Per-finding evidence is a priority** — show "expected 250, found 249, frame
  187 missing." It makes our full-frame edge visible and is exactly what beats a
  sampled competitor.
- **Opt-in auto pre-render: yes.** (See below on timing.)
- **No auto-scan-on-save.**
- **Price in the low-teens, one-time; no monthly seller sub until sales justify.**
- **The demo is the#1 marketing asset:** bake cloth → delete one middle frame →
  show Blender still says "baked" → show us naming the exact missing frame.

## 4. Where verification changed the plan

- **Auto pre-render moves UP, toward v1.** Both reviews first called it "v1.1,"
  but Cache Guardian ships it today, so it's **table-stakes** to compete
  head-to-head — not a nice-to-have. Recommend including an opt-in, non-blocking
  version **in v1** if it's not too costly; v1.1 at the latest.
- **Pricing has a real anchor now.** $14 (Cache Guardian) above, $9.99 generalists
  below. $12 undercuts the direct competitor slightly while signalling
  specialist. If we ship auto-pre-render + per-frame evidence (parity + better
  verification), **$14 is also defensible.**
- **Naming flag.** MotionLab has a *feature* called "Physics Preflight." Our
  *product* is named that. Low urgency, but a conscious call: keep it, or
  differentiate (e.g. a subtitle like "Physics Preflight — Cache Verify").

## 5. The build plan (reconciled, prioritized)

**v1 (launch) — make the edge visible and match the table-stakes:**
1. **Per-finding evidence** in the panel + report: "expected N, found M, missing
   frame X." (We partly do this in #20 — surface it on every cache finding.)
2. **Guided fixes**: each finding gets a "take me there" button to the exact
   Physics panel (extends today's "Select object"). No auto-changes.
3. **In-app "why it matters / how to fix"** per check (you hit this yourself).
4. **Opt-in auto pre-render warning** (Blender's `render_pre` handler;
   non-blocking, no repairs, no disk writes, no network). Include in v1 if
   feasible — it's how Cache Guardian competes.
5. **Top-of-panel result summary** that never shows UNKNOWN as success.
6. **Store assets**: the demo video above, 5 gallery images (2:1, ≥1200px),
   install/usage text.

**v1.1 (fast follow):**
7. Scan freshness/timestamp indicator ("scanned at HH:MM; scene may have changed").
8. Mute/ignore list.
9. A couple of adjacent "will it render" checks (sim-used textures missing, output
   path sanity) — only if they don't dilute the focus.

**Future "Pipeline" edition (separate, higher-priced — only after real buyers):**
10. Headless/CLI + JSON + exit codes for render-farm/CI gating. ChatGPT suggests
    $49–79; build only after v1 shows demand.

## 6. Decisions for Keith (business calls)

| Decision | Claude + ChatGPT lean | Your call |
|----------|----------------------|-----------|
| Product scope | Narrow + deep (sim cache + physics setup) | ? |
| Fixes | Guided only (stay read-only) | ? |
| Auto pre-render | Yes, opt-in — aim for v1 (table-stakes vs Cache Guardian) | ? |
| Launch price | **$12** (or $14 if we reach feature parity) | ? |
| Product name | Minor overlap with a MotionLab feature; probably keep | ? |
| Windows | Still untested — test, or launch Mac/Linux + honest | ? |
| Studio/headless edition | Later, only after v1 demand | ? |

## 7. Honest caveats (both reviews stress these)

- **Demand is unproven.** Listing prices ≠ sales. Treat launch as a 30-day
  experiment; track visits, conversion, refunds, support time.
- **Windows is untested** — don't claim it.
- Competitor feature claims are *their marketing*; we verified the pages exist and
  quoted them, but did not run their add-ons.

## Sources (verified competitor pages)
- Cache Guardian — https://superhivemarket.com/products/cache-guardian-simulation-cache-checker--pre-render-validator
- SceneCheck — https://superhivemarket.com/products/scenecheck-one-click-scene-validator-for-error-free-renders-and-deliveries
- MotionLab — https://superhivemarket.com/products/motionlab
- Preflight — https://superhivemarket.com/products/preflight--find-out-what-will-go-wrong-before-the-render-starts
- Triage / CG General — https://superhivemarket.com/products/triage
- Blend Inspector — https://superhivemarket.com/products/blend-inspector
