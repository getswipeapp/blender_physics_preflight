# Failsafe — Fresh-Install Usability Test (clean config, real customer instructions)

> **DRAFT — internal evidence, not published.** This is a scripted fresh-install
> and first-scan walkthrough on a **clean Blender configuration**, following the
> actual customer `launch/INSTALL_GUIDE.md` steps with the exact downloadable zip.
> It is **not** a substitute for a genuine first-time-user (naive human) session —
> that gate is recorded separately as **NOT TESTED** (see the status note at the
> bottom and `LAUNCH_PACKAGE.md`). This test answers a narrower, checkable
> question: *does the thing a customer downloads install cleanly into a Blender
> that has never seen it, and does the first scan work and read correctly?*

## How it was run (so it's reproducible)

- **Binary:** Blender **5.2.3 LTS** (`/Applications/Blender.app`).
- **Clean configuration:** a throwaway `BLENDER_USER_RESOURCES` directory plus
  `--factory-startup`, so there was **no pre-existing Failsafe install and no prior
  config** — a genuine first-time machine state. (Confirmed: the add-on was absent
  before install; it installed into the fresh config dir, not the already-set-up
  session.)
- **Package under test:** `dist/failsafe-933ea17.zip` — the exact zip a customer
  downloads (105 KB).
- **Steps:** the literal `INSTALL_GUIDE.md` flow — Install from Disk → tick to
  enable → open the Failsafe panel → Save file → Scan → read results.
- **Scene:** the reproducible demo fixture
  `/Users/Shared/failsafe_demo/failsafe ui test.blend` (one Cloth sim, baked to
  disk, cache frame 247 removed — see `certification/demo_fixture/REPRODUCIBILITY.md`).

The driver script exercised the **real registered operators** (`failsafe.scan`,
`failsafe.export_report`) and the installed engine — not a mock. Running from
background Blender means no human was clicking; the on-screen layout/legibility is
covered separately by the live-GUI gallery (`launch/gallery/`) and the heuristic
`BEGINNER_UX_REVIEW.md`.

## Results — 17 / 17 checks genuine PASS

| # | Step (from the guide) | Result |
|---|---|---|
| 1 | Clean config — add-on **not** already present | ✅ absent before install |
| 2 | **Install from Disk** the `.zip` | ✅ installed to repo `user_default` |
| 3 | **Tick the checkbox** to enable | ✅ `bl_ext.user_default.failsafe` enabled |
| 4 | `Scan Scene` operator registered | ✅ |
| 5 | `Select Affected Object` operator registered | ✅ |
| 6 | `Export Text Report` operator registered | ✅ |
| 7 | **Failsafe tab** / N-panel registered | ✅ panel `FAILSAFE_PT_panel`, category **"Failsafe"** |
| 8 | Default scene scan — "nothing to scan" is not an error | ✅ runs, 0 rows on the factory cube (in scope: nothing to flag) |
| 9 | Open a **saved** `.blend` (guide: save first) | ✅ loaded the demo |
| 10 | Fixture baked state survived reopen | ✅ `is_baked=True`, `use_disk_cache=True` |
| 11 | Fixture cache 249/250, frame **247** missing | ✅ 249 `.bphys`, 247 absent |
| 12 | **Scan** the saved scene | ✅ 13 result rows populated |
| 13 | Tally matches the documented gallery | ✅ **3 fail · 1 warning · 1 couldn't verify · 8 pass · 13 N/A** |
| 14 | Results split into two groups | ✅ **Physics Setup** + **Simulation Caches** |
| 15 | Status vocabulary present | ✅ FAIL / WARNING / UNKNOWN(="Couldn't verify") / PASS in rows |
| 16 | FAIL messages name the missing frame | ✅ all 3 FAILs name frame **247** |
| 17 | **Export Text Report** → Blender Text datablock | ✅ created `failsafe_report.txt`, neutral-path header |

### The three FAIL messages (verbatim from this fresh install)

- "Cloth is marked baked, but its cache on disk is incomplete."
- "Cloth is missing 1 of 250 required cache frame(s) on disk: **247**. The render
  will freeze or re-simulate there."
- "Cloth is missing 1 cached frame(s) across its 1–250 range: **247**. Each gap is
  a freeze/pop in the render."

### Exported report header (neutral path, no private info)

```
Failsafe report
Blender 5.2.3 LTS
File: /Users/Shared/failsafe_demo/failsafe ui test.blend
====================================================================
Summary: 3 Fail  1 Warning  1 Couldn't verify  8 Pass  13 N/A
("Couldn't verify" = not enough evidence to confirm — NOT a confirmed problem.
 Each one says why and what to do.)
```

## What this proves — and what it does not

**Proves:** the customer download installs cleanly on a never-configured Blender,
enables, registers its tab and operators, and the first scan produces the exact
documented, reproducible findings with plain-English, frame-naming messages and a
privacy-clean report. No code was modified; the scan is read-only.

**Does not prove:** that a real beginner, unaided, finds the panel, understands the
results, and acts on them. That is a human-judgment gate, recorded as **NOT TESTED**
(not failed) — recommended post-launch, not a release blocker, per the owner's
decision.

## Owner's 2-minute check (the one manual step Keith does)

1. Open **your newest Blender**, go to **Edit → Preferences → Add-ons**, use the
   **▾ → Install from Disk…**, and pick `dist/failsafe-933ea17.zip`. Tick it on.
2. Open any scene (or the demo), hover the 3D viewport, press **`N`**, click the
   **Failsafe** tab.
3. Click **Scan Scene**.
4. **The only question:** do the results make sense to you *without anyone
   explaining them?* If yes, this gate is satisfied for launch purposes.

---

**Status of the independent beginner gate:** **NOT TESTED** (recommended, not
required). This fresh-install usability test + the owner spot-check above stand in
its place for launch; a genuine naive-user session remains a good post-release
follow-up. Nothing here is published, merged, or priced.
