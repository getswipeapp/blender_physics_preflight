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
does **not** change your scene data, fix anything, bake anything, or touch the
internet. The only changes come from a button **you** click:

- **Export Text Report** / **Export JSON Report** — each builds the report and
  writes it into a Blender **Text datablock** inside the current project (named
  `failsafe_report…` / `failsafe_report.json`), then copies it to the clipboard.
  There is **no external file-save dialog**. Note the honest nuance: creating a Text
  datablock **does change the in-memory `.blend`** (Blender may mark the project
  unsaved), even though it does **not** save the `.blend` to disk on its own and
  never edits your scene/object data. To get a file, save the text yourself from
  Blender's **Text Editor** (*Text → Save As*). For automation, use the headless
  CLI below.
- **Save Baseline** — a one-click snapshot of the current simulation settings,
  written to an **external sidecar file** (`<blend>.failsafe-baseline.json`) next
  to your `.blend`, so check #26 can later tell you if the settings drifted. This
  is the only feature that writes a file to disk, only on your click, and it asks
  before overwriting an existing baseline. It never touches your `.blend`.

So: **scanning writes nothing**; an **Export** changes only the in-memory project
(a new Text datablock, nothing on disk until you save); **Save Baseline** is the one
action that writes a file to disk, and it's an external sidecar, never the `.blend`.

The same checks also run **headless** (`failsafe/cli.py`) for render farms and
pipelines. With `--json` it prints a machine-readable report to **standard output**
(where a calling script can capture or redirect it to a file — the CLI itself does
not write report files). Exit codes:

- `0` **clean** — no FAIL and nothing unverified. **Important:** WARNINGs alone
  still return `0` unless you pass `--strict`, which makes a WARNING blocking (`1`).
  So a `0` means "no failures," not "no warnings" — inspect the report or use
  `--strict` if warnings should gate your pipeline.
- `1` **blocking** — at least one FAIL (or, with `--strict`, a WARNING).
- `2` **unverified** — no FAIL, but something is "Couldn't verify."
- `3` **usage/open error** — bad arguments, or a file that couldn't be opened or
  scanned (including a batch file that crashed or timed out).

The headless path is read-only: it only opens and reads each `.blend`. In batch mode
each file runs in its **own Blender subprocess with a per-file timeout**
(`--timeout`), so a corrupt or hanging file is isolated to itself — recorded as an
error while every other file still scans (`--in-process` opts out for speed).

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
- **Potentially unclaimed cache files (check #25)** are cache files in the project's
  blendcache folder that **no simulation in any scene of this `.blend` owns**
  (ownership is checked across all scenes, not just the active one). They're flagged as a
  WARNING to **review before deleting** — never as categorically safe to delete. If
  another `.blend` shares that folder, files this scene doesn't own may belong to it.
  Failsafe never deletes anything; the call stays yours.

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
- The automated test suite passes **292/292 on Blender 4.2.9, 4.5.9, 5.0.1 and
  5.2.3** (headless), including real heavy-sim bakes (cloth, soft body, particle,
  fluid), damaged-cache cases, the cloud/orphan/baseline checks, the headless CLI,
  and adversarial batch cases (garbage files, partial-failure folders). See
  `certification/RUNTIME_CERTIFICATION.md`.
- **Windows: tested and passing.** The same 292/292 suite passes on **Blender
  4.2.9 / 4.5.9 / 5.0.1 / 5.2.3 Windows x64**, plus a Windows functional acceptance
  (install, baseline, JSON export, CLI exit codes) and a real multi-process batch,
  run on GitHub Actions `windows-2025`. See `certification/WINDOWS_CERTIFICATION.md`.
  (The Windows runs are **headless**; a Windows GUI session isn't claimed.)
- **Still untested (not advertised as working):** a live geometry-nodes *disk* bake,
  the CLI `-f`/`-a` render-handler paths, and a **Windows GUI** session (the macOS
  GUI acceptance covered Save Baseline / Export JSON in a real window).

## What it is NOT

- Not a render-readiness checker (missing textures, cameras, output paths) —
  deliberately out of scope; cheaper tools cover that.
- Not an auto-fixer (safe one-click fixes are a possible future update, not a v1
  promise, and not promised in the listing).
- Not a simulation baker. It checks your bakes; it doesn't create them.
- Not a render-blocker. The opt-in "check before render" (enabled in add-on
  preferences) runs the scan once at render start and prints a console warning, but
  it is **synchronous and non-cancelling** — it never stops or alters a render, and
  it's not a guarantee the render will succeed.
