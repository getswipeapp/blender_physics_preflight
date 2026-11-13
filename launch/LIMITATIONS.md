# Failsafe — Honest Limitations

> **DRAFT — pending independent review. Not published.**

This is the truthful "what it can and can't do" list. The product's reputation
rests on **not giving a false "all good."** When Failsafe can't be sure,
it reports **UNKNOWN** — it is designed never to report a confident PASS it can't
back up. (That's the design goal and how the checks are written; no software is
provably perfect, which is exactly why UNKNOWN exists.)

Put a short version in the store listing; keep this full version in the repo.

## What it is

A **read-only diagnostic**. A scan inspects your scene and reports problems. It
does **not** change anything, fix anything, bake anything, or touch the internet.
The only things it ever writes are ones **you** click, and **neither touches your
`.blend`**:

- **Export Report** — a text block inside the `.blend` (plus a clipboard copy), or
  a `.json` file you choose.
- **Save Baseline** — a one-click snapshot of the current simulation settings,
  written to an **external sidecar file** (`<blend>.failsafe-baseline.json`) next
  to your `.blend`, so check #26 can later tell you if the settings drifted. This
  is the only feature that writes a file to your computer, and only on your click.

The same checks also run **headless** (`failsafe/cli.py`) for render farms and
pipelines — exit codes `0/1/2/3`, `--json`, and a `--batch <folder>` mode. The
headless path is read-only too: it only opens and reads each `.blend`. In batch
mode each file runs in its **own Blender subprocess with a per-file timeout**
(`--timeout`), so a corrupt or hanging file is isolated to itself — recorded as an
error while every other file still scans. (`--in-process` opts out for speed when
isolation isn't needed.) The baseline's **Save Baseline** never overwrites an
existing baseline without asking first, and never writes automatically.

## What "the file is there" does and doesn't prove

Failsafe verifies that the expected cache files **exist on disk and are
non-empty, across the whole required frame range**. That catches the big real-
world failures: deleted caches, partial bakes, missing first/last frames, 0-byte
corrupt frames. It does **not** parse the inside of every cache file, so a file
that exists and has size is treated as present — it can't by itself guarantee the
simulation data is perfect or that the render will look identical. For the
failure modes that actually bite people (missing/partial/empty caches), file-
level verification is the right and sufficient check.

## Things it deliberately cannot confirm (reported as UNKNOWN / N/A)

- **Geometry-nodes bakes packed inside the .blend** (4.3+). A packed bake gives
  Python no files to verify → **UNKNOWN**.
- **In-memory caches** (e.g. the Rigid Body World cache, stored in the .blend).
  No files to check → the disk check is **NOT APPLICABLE**, not a failure.
- **Unsaved files.** Caches live next to the saved `.blend`; with no saved file
  there's no cache folder yet → cache checks report **UNKNOWN**. _Save, then scan._
- **Fluid "Replay" mode.** Not a true bake — Blender re-creates frames on reopen.
  Flagged as **WARNING**, never PASS.
- **Bake-time FPS / time-scale (check #23).** Blender doesn't record the FPS used
  when a cache was baked, so the tool **cannot detect** whether you changed it
  afterward. #23 is an honest reminder to re-bake if you did — not a detector.
- **Settings baseline (check #26).** This compares your current sim settings to a
  baseline **you** chose to save. It can only tell you settings changed **since the
  baseline was saved — not since the bake.** It compares a **curated set of key
  settings**, not every property, so a PASS says "the tracked settings are
  unchanged," never "nothing changed." The baseline covers **every scene** in the
  file, and each simulation is matched to its own scene, so one scene's settings are
  never compared against another's. With no baseline saved (or a missing, corrupt,
  foreign, or ambiguous one), it reports **Couldn't verify**, not a pass. Save the
  baseline right after baking for it to mean the most. A "settings unchanged" result
  is **not** proof the bake itself is good — only that the tracked settings didn't
  move.
- **Cloud-folder caches (check #24)** are flagged as a *risk*, by matching common
  sync-folder names (Dropbox, OneDrive, Google Drive, iCloud, etc.). It warns you
  the cache could be locked or only partly downloaded at render time; it can't see
  a given file's live sync state, so this is a heads-up, not a guarantee of trouble.
- **Orphaned cache files (check #25)** are reported as *safe to remove* only for the
  current `.blend`'s own cache folder. If another `.blend` shares that folder, files
  this scene doesn't own may belong to it — Failsafe never deletes anything, so the
  call to remove them stays yours.

## Checks that are judgement calls (WARNING, not FAIL)

Some checks flag things that *can* be intentional, so they warn rather than fail:
mass vs size (#2), collision-shape choice (#4), real-world size (#9), origin
offset (#10), collision margin (#11). Failsafe points them out; you decide.

Two checks were corrected after the code review and now behave honestly:
- **#1** also checks unapplied **rotation** (on cloth/soft-body/collision objects).
- **#3** evaluates the **start frame**; if you're elsewhere on the timeline it
  reports **UNKNOWN** and asks you to move to the start frame, rather than guessing.

## Platform / version coverage

- **Minimum Blender: 4.2 LTS.**
- The automated test suite passes **291/291 on Blender 4.2.9, 4.5.9, 5.0.1 and
  5.2.3** (headless), including real heavy-sim bakes (cloth, soft body, particle,
  fluid), damaged-cache cases, the cloud/orphan/baseline checks, the headless CLI,
  and adversarial batch cases (garbage files, partial-failure folders). See
  `certification/RUNTIME_CERTIFICATION.md`.
- **Still untested (not advertised as working):** Windows, a live geometry-nodes
  *disk* bake, and the CLI `-f`/`-a` render-handler paths. The live GUI smoke-test
  has not yet re-exercised the new **Save Baseline** / **Export JSON** buttons in a
  real window (the logic behind them is covered by the headless suite). The listing
  names only the versions actually tested.
- Cache folder names and relative paths differ slightly between Windows and macOS;
  a Windows pass is also on the pre-launch list.

## What it is NOT

- Not a render-readiness checker (missing textures, cameras, output paths) —
  deliberately out of scope; cheaper tools cover that.
- Not an auto-fixer (safe one-click fixes are a possible future update, not a v1
  promise, and not promised in the listing).
- Not a simulation baker. It checks your bakes; it doesn't create them.
