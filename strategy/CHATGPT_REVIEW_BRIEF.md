# Independent Product Review Brief — "Physics Preflight" (Blender add-on)

You are being asked for an **independent** strategic review. The owner (Keith)
also has an analysis from another assistant and wants your *own* conclusions to
compare — so please **do your own research and reasoning**; don't assume the
other analysis is right. Where you can, look up real competing products and
prices yourself.

## What the product is

**Physics Preflight** is a commercial Blender add-on (to be sold on Superhive /
Blender Market). It is a **read-only "pre-flight" checker for physics and
simulation setups** — it scans a scene and reports problems that would ruin a
render (especially on a render farm), but it never changes anything.

**Its core differentiator:** Blender's "baked" flags stay `True` even after the
cache files are deleted from disk. Physics Preflight **verifies the actual cache
files on disk, frame by frame**, so it catches a sim that Blender *thinks* is
baked but isn't. Guiding rule: **never report a false PASS** — when something
can't be proven, it reports UNKNOWN, not PASS.

## Current feature set (23 checks, two groups)

**Physics Setup (16):** unapplied scale/rotation on physics objects; suspicious
rigid-body mass for object size; objects overlapping at start frame; collision
shape mismatch (convex hull on concave); high-poly/non-manifold colliders; Rigid
Body World disabled/misconfigured; cloth/soft-body collision not configured;
negative scale / scaled parents; real-world size sanity; origin far from
geometry; collision margin too large; animated passive collider not marked
'Animated'; broken rigid-body constraints; collision modifier above deforming
modifiers; cloth pin group empty/missing; fluid flow/effector outside domain or
domain with no flow.

**Simulation Caches (7):** is the sim baked; cache files actually present on disk
(not just the flag); baked range covers render range; frame gaps / sampling;
two sims sharing one cache location; non-portable cache paths; FPS/time-scale
changed after baking. Cache coverage spans cloth, soft body, particles, rigid
body, fluid (Mantaflow: data/mesh/noise/particles/guiding/config), and
geometry-nodes bakes.

## Current UI

A panel in Blender's 3D-viewport side (N) panel: a **Scan Scene** button, an
**Export Text Report** button, a show/hide-passed toggle, a summary tally of
fail/warning/unknown counts, and two collapsible groups of findings. Recent
additions: **colored severity icons** (red fail / amber warning / blue unknown /
green pass), **word-wrapped** finding text, **collapsible** findings, and the
**summary tally icons are clickable filters** (click to show only that severity).
Each finding can jump to the affected object ("Select 'X'"). It is otherwise
fairly plain — no status "badge", no in-app help/docs, no custom branding yet.

## Engineering status (context, not the question)

Logic is complete and certified: a 128-test headless suite passes on Blender
4.2.9 / 4.5.9 / 5.0.1 / 5.2.3; a real GUI acceptance test passed (install, scan,
deleted-cache catch, export); a scan is proven to change nothing on disk or in
the scene. Windows is untested (marked UNKNOWN). So the review should focus on
**product/market**, not code quality.

## What we want from you (independent)

1. **Competitive landscape.** Who actually competes (Superhive, Gumroad,
   elsewhere)? What do they offer, and at what price? Please name real products.
   Is "23 checks" competitive, thin, or beside the point for this niche?
2. **Positioning.** Is a physics/sim-cache-only tool better off staying deep and
   narrow, or broadening into general scene validation (where several competitors
   already are)? What is the sharpest positioning?
3. **Feature gaps.** What would make this materially more valuable or more
   sellable? Rank your ideas by value-to-effort. (One idea on the table: auto-run
   the checks right before render / on save, so the user doesn't have to remember
   to scan.)
4. **UI critique.** Compared to the norms of this add-on category, what should the
   UI add or change? Is "fairly plain" a problem? What are the 3–5 highest-impact
   UI improvements?
5. **Pricing.** What should it sell for at launch, and is there a higher tier
   (e.g. a studio/pipeline/headless version) worth creating later?
6. **Fixes philosophy.** Competitors offer one-click fixes. We are deliberately
   read-only (it's part of the trust story). Keep strictly read-only, add
   *guided* fixes (jump to the right panel, no auto-change), or add real fixes?

Please give concrete, opinionated answers with your reasoning, and flag anywhere
you're uncertain or where real data would change your advice.
