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
25. **Potentially unclaimed cache files** — cache files in the project's blendcache folder that **no simulation in any scene of this `.blend`** owns (often left by a renamed or deleted object). Flagged as a WARNING to **review before deleting** — if another `.blend` shares the folder, they may belong to it. Failsafe never deletes anything.
26. **Settings-baseline drift** *(opt-in)* — warns if a simulation's settings changed since you clicked **Save Baseline**. The baseline is an external sidecar file; **nothing is ever written into your `.blend`.** It can only tell you settings changed since the baseline was saved, not since the bake — so save it right after baking.

Every report also shows **total cache disk usage** per simulation.

## What makes it different

Failsafe covers **both** physics-setup checks **and** real file-level cache
verification in one scan — and it verifies the actual cache files on disk instead
of trusting Blender's "baked" flag, which stays on after the files are deleted.
Its strongest, clearest edge is that **frame-by-frame, required-range cache-file
verification combined with physics-setup checks in one read-only tool** — and that
when Blender genuinely can't confirm something, it says **Couldn't verify** instead
of a false "all good." It runs in the GUI **and headless** — one command with a
build-readable exit code, plus a `--batch` mode for a whole folder, each file in
its own Blender subprocess with a timeout so one corrupt or hanging `.blend` can't
crash the run. (Per-file subprocess batch isolation is useful but **not unique** —
at least one other cache tool offers a comparable folder/batch mode; see
`strategy/FEATURE_MATRIX.md` for the honest comparison.)

## How it works

1. Open your scene (and **save it** before checking caches — caches live next to
   the saved `.blend`).
2. Open the **Failsafe** panel in the 3D viewport sidebar (press `N`).
3. Click **Scan Scene**.
4. Read the results — plain English, colour-coded, each with a **Select Object**
   button. Treat **Couldn't verify** as "not verified," not as a pass.
5. Optional: **Export Text Report** or **Export JSON Report** — each writes the
   report to a **Blender Text datablock** inside the current file (named
   `failsafe_report...` / `failsafe_report.json`) and copies it to your clipboard.
   You can read or save it from Blender's **Text Editor** (e.g. *Text → Save As*).
   Creating that Text datablock changes the **in-memory** project (so Blender may
   mark the file unsaved), but it does **not** write to disk on its own and never
   alters your scene data. There is **no** external file-save dialog for reports.
6. Optional: **Save Baseline** — a one-click snapshot of your current sim settings,
   written to an **external** sidecar file (`<blend>.failsafe-baseline.json`) next
   to your `.blend` so check #26 can later tell you if they drifted. This is the
   only time Failsafe writes a file to disk, and it never touches your `.blend`.

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
  5.0.1 and 5.2.3** (292/292 each) — on **macOS and Windows x64** (Windows via
  GitHub Actions `windows-2025`; see `certification/WINDOWS_CERTIFICATION.md`).
- No internet, no account, no extra downloads. Fully offline, no telemetry.
- **Scanning is read-only** — a scan never changes your scene and never writes any
  file. The only changes are ones **you** click: an **Export** adds a Text datablock
  to the current project in memory (nothing written to disk until *you* save),
  **Save Baseline** writes an external sidecar file next to your `.blend`. Neither
  edits your scene data, and neither saves your `.blend` for you.

## Two ways to run it (artist vs. pipeline)

Failsafe ships one add-on with two independent surfaces. You only need the first.

**For artists — the panel (GUI).** Everything above: open the sidebar, click
**Scan Scene**, read colour-coded results, jump to problem objects, and optionally
Export a report or Save a settings baseline. No command line, no setup.

**For technical directors / render farms — headless (optional).** The same checks
also run from the command line with **no GUI**, returning a build-readable **exit
code** (`0` = no blocking failures or unverified results — **warnings may still
remain unless you pass `--strict`**, which makes a warning blocking · `1` blocking
fail · `2` couldn't-verify · `3` usage/open error),
optional `--json`, and a `--batch <folder>` mode that scans a whole folder of
`.blend` files. In batch mode each file runs in its **own Blender subprocess with a
per-file timeout**, so one corrupt or hanging file is isolated and logged while the
rest keep scanning. This is a command-line capability you can wire into your own
scripts — **not** a bundled integration with any specific render-farm product.

Both surfaces share the exact same check engine, so a finding is identical whether a
person clicks Scan or a script runs the CLI. Artists can ignore the headless side
entirely.

## FAQ

**Will Failsafe guarantee my render succeeds?**
No. It's a pre-render diagnostic that catches common, specific physics and cache
problems. It can't promise a render will complete or look correct — plenty can go
wrong that's outside its scope (textures, lighting, memory, render settings). It
reduces one category of nasty surprises; it doesn't guarantee success.

**Does it check every possible cache problem?**
No. It verifies that the expected cache files **exist on disk and are non-empty
across the required frame range** — which catches the big ones (deleted caches,
partial bakes, missing first/last frames, 0-byte frames). It does **not** parse the
internal contents of each cache file, so it can't prove the simulation data itself
is perfect or will render identically. When Blender genuinely can't confirm
something, it says **Couldn't verify** rather than a false "all good."

**Does it change or fix my file?**
No. **Scanning is read-only** — it never edits your scene data. The only changes
happen when **you** click a button. **Export Text Report** / **Export JSON Report**
each add a Blender **Text datablock** to the current project (in memory) and copy it
to your clipboard — that marks the project unsaved but writes nothing to disk until
you save, and there's no external file dialog; you can save the text yourself from
Blender's Text Editor. **Save Baseline** writes an **external** sidecar file next to
your `.blend` (and asks before overwriting). Nothing Failsafe does edits your scene
or saves your `.blend` for you.

**How do I get a JSON file on disk?**
In the GUI, click **Export JSON Report** and save the resulting Text datablock from
Blender's Text Editor. For automation, run the **headless CLI with `--json`** — it
prints the JSON to **standard output**, where your calling script can capture or
redirect it to a file.

**Is it an auto-fixer?**
No. It's a diagnostic — it finds problems and points you at the object; you make the
fix. (Safe one-click fixes are a possible future update, not a v1 promise.)

**Does it need the internet or an account?**
No. Fully offline. No account, no telemetry, no downloads.

**Which Blender versions are supported?**
Blender **4.2 LTS or newer**. The automated test suite passes 292/292 on
**4.2.9 / 4.5.9 / 5.0.1 / 5.2.3**, on **macOS and Windows x64** (headless). A Windows
*GUI* session is not separately certified; the live-window acceptance was done on
macOS.

**What about check #26, the settings baseline?**
It's opt-in. After you click **Save Baseline**, later scans can warn you if a
curated set of key simulation settings **changed since you saved the baseline** — not
since the bake. A "settings unchanged" result means those tracked settings didn't
move, not that every property is identical or that the bake itself is good.

**Can it check automatically before I render?**
Yes — there's an **opt-in "check before render"** you enable in the add-on's
preferences. When it's on, Failsafe runs its scan once at the **start** of a render
and, if it finds problems, prints a clear warning to the system console (so it also
lands in render-farm logs) and updates a one-line banner in the panel. It runs
**synchronously** (on a heavy scene it can add a short delay before rendering
starts), it **never cancels or alters the render**, and it is **not** a guarantee the
render will succeed — just an early heads-up. It's off by default.

## Two workflows, one product

The GUI panel and the headless CLI are **two ways to use the same single add-on**,
not two separately sold editions. There is no "Pro" or "Pipeline" SKU — everything
described here (panel, Export, Save Baseline, headless CLI, batch) ships together in
one product.

## Licensing

**GPL-3.0-or-later.** (Superhive permits either GPL or MIT for code products;
Failsafe is licensed GPL-3.0-or-later — the standard choice for Blender add-ons that
link Blender's GPL Python API.) Source and license notices are distributed to
buyers, as normal for GPL add-ons there.

---

## Pricing — UNDECIDED (Keith decides)

**No price is set.** This is an open owner decision, deliberately left blank in
this draft. No savings figure, "replaces N add-ons" math, or buyer-demand estimate
is asserted here — those would be guesses, and the selling rule is no invented
claims.

For reference only (facts, not a recommendation): competitors' own list prices at
the time the feature matrix was compiled are recorded in
`strategy/FEATURE_MATRIX.md`. Any earlier "$9 baseline" or "$12 target" figures
from draft roadmap text are **withdrawn** — they were AI-drafted, not specified by
Keith. Set the price yourself when you're ready; the listing text does not depend
on it.

## Notes for Keith (not part of the public listing)

- **Competitor names** are kept out of the public text (your selling rule). The
  "what makes it different" section describes Failsafe's own coverage and explicitly
  notes the batch-isolation feature is **not unique** (Cache Commander offers a
  comparable per-file background-process folder mode). The internal
  `strategy/FEATURE_MATRIX.md` carries the honest, verification-labelled comparison.
- **Feature accuracy:** checks #1, #3, #16, #18–#20 and #23 are described above to
  match the **fixed** build, not the first draft. #23 is honestly a reminder, not
  a detector. #26 (baseline) tells you settings changed since the baseline was
  *saved*, not since the bake — described that way above, no overclaim.
- **Pre-launch gates (Superhive + your roadmap).** Done: multi-version headless
  tests (4.2/4.5/5.0/5.2, **292/292 each**, including the new cloud/orphan/baseline
  checks, the headless CLI, and adversarial batch cases) on **macOS and Windows x64**;
  the **macOS** live-GUI acceptance (install, scan, deleted-cache catch, **Save
  Baseline and Export JSON exercised in a real window** — see
  `certification/GUI_ACCEPTANCE_933ea17.md`); Windows certification
  (`certification/WINDOWS_CERTIFICATION.md`, headless). Still open: real screenshots +
  optional video; a **separate** beginner usability test (a genuine first-time user
  tries it); and your publishing approval. (The owner GUI test is done on macOS; the
  beginner usability test is a different thing and is not. A Windows *GUI* session is
  optional — Windows is certified headless.)
- **Superhive listing requirements** (per ChatGPT citing Superhive's seller docs —
  confirm current specs on the site when you set up the listing): at least **5**
  gallery images at **2:1 ratio, ≥1200 px wide**; written install instructions and
  FAQs **on the product page** (not just a downloadable guide); a demo video is
  **optional**; don't use the Blender logo/brand as a decorative element; support
  response goal is **72 hours**.
