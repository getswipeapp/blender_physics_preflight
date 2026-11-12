# Failsafe — Superhive Store Listing (DRAFT v2)

> **Status:** Draft for Keith to review and edit. Nothing here is published.
> Revised after (a) ChatGPT's launch-doc review and (b) the code fixes from the
> independent code review — feature descriptions below now match the **fixed**
> build (see `REVIEW_RESPONSE.md`).
> **Price:** _TBD_ — see "Pricing" at the bottom.
> **Before publishing:** add real screenshots/video and get Keith's approval.
> (Multi-version headless tests are **done** — 162/162 on 4.2.9 / 4.5.9 / 5.0.1 /
> 5.2.3; see `certification/RUNTIME_CERTIFICATION.md`.) See `launch/LIMITATIONS.md`
> and `launch/DEMO_SHOTLIST.md`.

---

## Headline

**Failsafe — Check Physics Setup + Simulation Caches in One Click**

## Hook

A Blender scene can still *look* baked after its cache files are gone. Failsafe
checks the **actual cache files on disk**, frame by frame, alongside
common physics-setup mistakes — so you catch the broken sim *before* you render,
not hours into a frame farm.

## Short description

Failsafe is a one-click, offline, read-only health check for your
physics and simulations. It runs **23 checks** across rigid bodies, cloth, soft
body, fluid, and geometry-nodes bakes, and reports each as PASS / WARNING / FAIL
/ UNKNOWN / NOT APPLICABLE, grouped into **Physics Setup** and **Simulation
Caches** — with a button to jump straight to each problem object.

It's deliberately cautious: when Blender genuinely can't confirm something (an
in-memory cache, a packed geometry-nodes bake, an unsaved file), it says
**UNKNOWN** rather than a misleading "all good."

## Who it's for

- **Beginners** who don't yet know the dozen quiet ways a sim breaks.
- **Freelancers and small studios** who can't afford a render that dies at frame
  200 because a cache was never fully baked.
- Anyone handing a `.blend` to a render farm, a client, or a teammate who needs
  to trust the sims are actually there.

## The problem it solves

Physics in Blender fails silently. A cache looks baked but the files were
deleted. A rigid body weighs five tonnes because of an unapplied scale. A cloth
sim has no collision object. A fluid used "Replay," which isn't a real bake. You
find out when the render looks wrong — or after you've wasted hours.

## What it checks (all 23)

**Physics Setup (16 checks)**
1. Unapplied **scale or rotation** on physics objects
2. Suspicious rigid-body mass for the object's size
3. Objects overlapping at the start frame *(checks the start frame; asks you to move there if you're elsewhere on the timeline)*
4. Collision-shape mismatch (Convex Hull on a concave object)
5. High-poly or non-manifold colliders
6. Rigid Body World disabled or misconfigured
7. Cloth / soft-body collision not configured
8. Negative scale or scaled parents on physics objects
9. Real-world size sanity for the scene's scale
10. Origin far from the geometry on active rigid bodies
11. Collision margin too large for the object's size
12. Animated passive collider not marked "Animated"
13. Broken rigid-body constraints
14. Collision modifier sitting above deforming modifiers
15. Cloth pin group empty or missing
16. Fluid **flow source** or effector outside the domain, or a domain with no flow source

**Simulation Caches (7 checks)**
17. Is the simulation baked? *(answered from disk, not just the flag)*
18. **Cache files actually present on disk across the whole range — not just the "baked" flag** _(the headline check)_
19. Baked range covers the render range
20. Frame gaps: every frame cached (first, middle **and** last), or flagged if sampled
21. Two simulations sharing one cache location
22. Non-portable cache paths (absolute, or outside the project folder)
23. FPS / time-scale reminder *(Blender doesn't record the FPS used at bake time, so this flags the risk and reminds you to re-bake if you changed it — it can't detect the change for you)*

## What makes it different

In our Phase 0 competitor research, **no single add-on combined physics-setup
checks with real file-level cache verification** — you'd assemble two or three
separate tools to get partial coverage. Failsafe does both in one scan,
and it verifies the real cache files instead of trusting Blender's "baked" flag,
which stays on after the files are deleted.

## How it works

1. Open your scene (and **save it** before checking caches — caches live next to
   the saved `.blend`).
2. Open the **Failsafe** panel in the 3D viewport sidebar (press `N`).
3. Click **Scan Scene**.
4. Read the results — plain English, colour-coded, each with a **Select Object**
   button. Treat **UNKNOWN** as "not verified," not as a pass.
5. Optional: **Export Report** writes the report to a text block **inside the
   `.blend`** and copies it to your clipboard (it doesn't save a separate file on
   your computer).

## Honest limitations (shown openly in the listing)

- It's a **diagnostic, not an auto-fixer** — it finds problems; you fix them.
  (Safe, optional one-click fixes are a planned future update, not promised for v1.)
- It's built so that when it can't be sure, it says **UNKNOWN** rather than a
  false "all good." Finding the files on disk confirms they exist and aren't
  empty — it can't by itself prove the simulation data is perfect or will render
  identically.
- Some cases Blender can't report from Python — packed geometry-nodes bakes and
  in-memory caches — are marked UNKNOWN / NOT APPLICABLE, never guessed.
- Save your file before scanning caches; an unsaved file has no cache folder yet.

(Full list in `launch/LIMITATIONS.md`.)

## Requirements

- Blender **4.2 LTS or newer**. Automated headless tests pass on **4.2.9, 4.5.9,
  5.0.1 and 5.2.3** (162/162 each). Windows is not yet tested — see `LIMITATIONS.md`.
- No internet, no account, no extra downloads. Fully offline, no telemetry.
- Read-only: it never changes your scene and never writes files unless you click
  Export (which adds a text block inside the `.blend`).

## Licensing

GPL-3.0-or-later (standard and required for Blender add-ons on Superhive). Source
and license notices are distributed to buyers, as normal for GPL add-ons there.

---

## Pricing (Keith decides)

The stack a buyer would otherwise assemble costs **≈ $24–27** (Phase 0). Options:

| Price | Angle | Trade-off |
|------|-------|-----------|
| **$12** | "Half the price of the 2–3 add-ons it replaces." | Phase 0's lead pick; clean value story. |
| **$14–15** | Premium but still well under the stack. | Best margin if the file-check angle lands. |
| **$9.99** | Matches the closest competitor head-on. | Hardest to justify (fewer total checks, though deeper on physics). |

> **On the "$9 baseline":** ChatGPT's doc review said to keep $9 as the baseline.
> Your own Phase 0 report (§0) **explicitly withdrew** the $9 figure — it was
> "introduced in AI-drafted roadmap text, not specified by Keith… It is
> withdrawn." So price is genuinely open; $9 is an option, not a required floor.

## Notes for Keith (not part of the public listing)

- **Competitor names** are kept out of the public text (your selling rule). The
  "no single add-on combines both" line is backed by the Phase 0 research, not a
  guess. Say the word if you want a named comparison table.
- **Feature accuracy:** checks #1, #3, #16, #18–#20 and #23 are described above to
  match the **fixed** build, not the first draft. #23 is honestly a reminder, not
  a detector.
- **Pre-launch gates (Superhive + your roadmap):** multi-version headless tests
  (4.2/4.5/5.0/5.2) ✅ **done**; GUI acceptance ✅ **done** (owner, 5.2.3). Still
  open: real screenshots + optional video, your beginner acceptance test, Windows
  check (optional), and your publishing approval.
- **Superhive listing requirements** (per ChatGPT citing Superhive's seller docs —
  confirm current specs on the site when you set up the listing): at least **5**
  gallery images at **2:1 ratio, ≥1200 px wide**; written install instructions and
  FAQs **on the product page** (not just a downloadable guide); a demo video is
  **optional**; don't use the Blender logo/brand as a decorative element; support
  response goal is **72 hours**.
