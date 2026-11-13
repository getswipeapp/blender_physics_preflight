# Failsafe — Superhive Store Listing (DRAFT v2)

> **Status:** Draft for Keith to review and edit. Nothing here is published.
> Revised after (a) ChatGPT's launch-doc review and (b) the code fixes from the
> independent code review — feature descriptions below now match the **fixed**
> build (see `REVIEW_RESPONSE.md`).
> **Price:** _TBD_ — see "Pricing" at the bottom.
> **Before publishing:** add real screenshots/video and get Keith's approval.
> (Multi-version headless tests are **done** — 292/292 on 4.2.9 / 4.5.9 / 5.0.1 /
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
physics and simulations. It runs **26 checks** across rigid bodies, cloth, soft
body, fluid, and geometry-nodes bakes, and reports each as Pass / Warning / Fail
/ **Couldn't verify** / Not applicable, grouped into **Physics Setup** and
**Simulation Caches** — with a button to jump straight to each problem object. It
also runs **headless** for render farms and pipelines (one command, a clean exit
code, and a `--batch` mode for a whole folder of `.blend` files).

It's deliberately cautious: when Blender genuinely can't confirm something (an
in-memory cache, a packed geometry-nodes bake, an unsaved file), it says
**Couldn't verify** rather than a misleading "all good."

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

## What it checks (all 26)

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

**Simulation Caches (10 checks)**
17. Is the simulation baked? *(answered from disk, not just the flag)*
18. **Cache files actually present on disk across the whole range — not just the "baked" flag** _(the headline check)_
19. Baked range covers the render range
20. Frame gaps: every frame cached (first, middle **and** last), or flagged if sampled
21. Two simulations sharing one cache location
22. Non-portable cache paths (absolute, or outside the project folder)
23. FPS / time-scale reminder *(Blender doesn't record the FPS used at bake time, so this flags the risk and reminds you to re-bake if you changed it — it can't detect the change for you)*
24. **Cache in a cloud-synced folder** (Dropbox, OneDrive, Google Drive, iCloud…) that can be locked or only partly downloaded while a render reads it
25. **Orphaned cache files** left behind by renamed or deleted sims — wasted disk, safe to remove
26. **Settings-baseline drift** *(opt-in)* — warns if a simulation's settings changed since you clicked **Save Baseline**. The baseline is an external sidecar file; **nothing is ever written into your `.blend`.** It can only tell you settings changed since the baseline was saved, not since the bake — so save it right after baking.

Every report also shows **total cache disk usage** per simulation.

## What makes it different

Failsafe covers **both** physics-setup checks **and** real file-level cache
verification in one scan — and it verifies the actual cache files on disk instead
of trusting Blender's "baked" flag, which stays on after the files are deleted.
Most tools do one side or the other; Failsafe does both, and it says **Couldn't
verify** rather than a false "all good" when Blender genuinely can't confirm
something. It runs in the GUI **and headless** — one command with a build-readable
exit code, plus a `--batch` mode for a whole folder — so the same checks guard a
render farm or a pipeline, not just your desk. In batch mode each file is scanned
in its **own Blender subprocess with a timeout**, so one corrupt or hanging
`.blend` can't crash the whole run — it's logged and the batch carries on.

## How it works

1. Open your scene (and **save it** before checking caches — caches live next to
   the saved `.blend`).
2. Open the **Failsafe** panel in the 3D viewport sidebar (press `N`).
3. Click **Scan Scene**.
4. Read the results — plain English, colour-coded, each with a **Select Object**
   button. Treat **Couldn't verify** as "not verified," not as a pass.
5. Optional: **Export Report** (JSON or a text block inside the `.blend`), and
   **Save Baseline** — a one-click snapshot of your current sim settings to an
   external sidecar file so check #26 can later tell you if they drifted. Save
   Baseline is the *only* thing Failsafe ever writes, and it never touches your
   `.blend`.

## Honest limitations (shown openly in the listing)

- It's a **diagnostic, not an auto-fixer** — it finds problems; you fix them.
  (Safe, optional one-click fixes are a planned future update, not promised for v1.)
- It's built so that when it can't be sure, it says **Couldn't verify** rather
  than a false "all good." Finding the files on disk confirms they exist and
  aren't empty — it can't by itself prove the simulation data is perfect or will
  render identically.
- Some cases Blender can't report from Python — packed geometry-nodes bakes and
  in-memory caches — are marked "Couldn't verify" / Not applicable, never guessed.
  (These are Blender limitations, not problems with your scene.)
- Save your file before scanning caches; an unsaved file has no cache folder yet.

(Full list in `launch/LIMITATIONS.md`.)

## Requirements

- Blender **4.2 LTS or newer**. Automated headless tests pass on **4.2.9, 4.5.9,
  5.0.1 and 5.2.3** (292/292 each). Windows is not yet tested — see `LIMITATIONS.md`.
- No internet, no account, no extra downloads. Fully offline, no telemetry.
- Read-only: a scan never changes your scene or writes any file. The only writes
  are the ones you click — Export Report, and Save Baseline (an external sidecar
  file) — and neither modifies your `.blend`.

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
| **$9.99** | Matches the closest competitor head-on. | Easier to justify now: 26 checks + a headless CLI + batch mode is at or above what the $9–$14 rivals offer. |

> **On the "$9 baseline":** ChatGPT's doc review said to keep $9 as the baseline.
> Your own Phase 0 report (§0) **explicitly withdrew** the $9 figure — it was
> "introduced in AI-drafted roadmap text, not specified by Keith… It is
> withdrawn." So price is genuinely open; $9 is an option, not a required floor.

## Notes for Keith (not part of the public listing)

- **Competitor names** are kept out of the public text (your selling rule). The
  "what makes it different" section now describes Failsafe's own coverage rather
  than claiming no rival combines both (Phase 0 didn't check every add-on
  exhaustively). Say the word if you want a named comparison table.
- **Feature accuracy:** checks #1, #3, #16, #18–#20 and #23 are described above to
  match the **fixed** build, not the first draft. #23 is honestly a reminder, not
  a detector. #26 (baseline) tells you settings changed since the baseline was
  *saved*, not since the bake — described that way above, no overclaim.
- **Pre-launch gates (Superhive + your roadmap).** Done: multi-version headless
  tests (4.2/4.5/5.0/5.2, **292/292 each**, including the new cloud/orphan/baseline
  checks, the headless CLI, and adversarial batch cases); owner GUI smoke-test on
  5.2.3 (install, scan, deleted-cache catch, export). Still open: real screenshots
  + optional video; a **separate** beginner usability test (a first-time user
  tries it); optional Windows check; and your publishing approval. (The owner GUI
  test and the beginner test are two different things — the first is done, the
  second isn't. The GUI smoke-test has not yet re-exercised the new Save Baseline
  button or the JSON export button in the live window.)
- **Superhive listing requirements** (per ChatGPT citing Superhive's seller docs —
  confirm current specs on the site when you set up the listing): at least **5**
  gallery images at **2:1 ratio, ≥1200 px wide**; written install instructions and
  FAQs **on the product page** (not just a downloadable guide); a demo video is
  **optional**; don't use the Blender logo/brand as a decorative element; support
  response goal is **72 hours**.
