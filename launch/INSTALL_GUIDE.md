# Failsafe — Quick Start (for beginners)

> **DRAFT — pending independent review. Not published.**

This takes about two minutes. No account, no internet, nothing to configure.

## 1. Install

1. In Blender, go to **Edit → Preferences → Add-ons**.
2. Click the **arrow icon (▾)** in the top-right of that window and choose
   **Install from Disk…**
3. Pick the **`failsafe.zip`** file you downloaded. (Install the zip —
   don't unzip it first.)
4. After installing, make sure its checkbox is **ticked** to enable it. Search
   "Failsafe" in the Add-ons list if you don't see it.

> On Blender 4.2+ this is an "extension," so you can also manage it under
> **Edit → Preferences → Get Extensions / Add-ons**.

## 2. Open the panel

1. Hover your mouse over the main **3D Viewport**.
2. Press **`N`** to open the right-hand sidebar (or drag the little arrow on the
   right edge).
3. Click the **Failsafe** tab.

## 3. Scan

1. **Save your file first** if you're checking simulation caches — caches live in
   a folder next to your saved `.blend`, so an unsaved file has nothing to check.
2. Click **Scan Scene**.
3. Read the results, split into **Physics Setup** and **Simulation Caches**.

## 4. Read the results

| Status | Means |
|--------|-------|
| **Pass** | Checked, and it's fine. |
| **Warning** | Worth a look — might be intentional, might be a mistake. |
| **Fail** | A real problem that will likely hurt your render. |
| **Couldn't verify** | Blender couldn't give enough to confirm this — treat it as "not verified," not a pass. Each one shows why and what to do. |
| **Not applicable** | This check doesn't apply to your scene. |

- Click **Select Object** on any result to jump straight to the object it's about.
- Click **Export Text Report** or **Export JSON Report** to put the report into a
  **Blender Text datablock** (named `failsafe_report…`) and copy it to your
  clipboard. There's no "save file" dialog — to keep it as a file, open Blender's
  **Text Editor**, pick that text, and use **Text → Save As**. (Creating the text
  marks the project unsaved, but nothing is written to disk until you save, and your
  scene isn't changed.) For automation, the **headless CLI `--json`** prints the
  JSON to standard output instead.
- Click **Save Baseline** to snapshot your current simulation settings to an
  external file next to your `.blend` — later scans can then warn you if those
  settings drift (check #26). It asks before overwriting, and never changes your
  scene or your `.blend`.

## Why "Couldn't verify" is a feature, not a bug

A green "all good" is only trustworthy if the tool actually checked. Failsafe is
built so it won't claim a pass it can't back up: if Blender genuinely can't confirm
something — a packed geometry-nodes bake, an in-memory cache, an unsaved file — it
says **Couldn't verify** (with the reason and a next step) so you know to check it
yourself, rather than showing a green light that was never real.

## Troubleshooting

- **No "Failsafe" tab?** Enable the add-on in **Preferences → Add-ons**
  (search its name; the checkbox should be ticked).
- **Cache checks all say "Couldn't verify"?** Save your `.blend` and scan again.
- **Overlap check says "Couldn't verify"?** Move the timeline to the first frame
  and re-scan — it checks overlaps at the start frame.
- **Nothing to scan?** The scene may have no physics or simulations for Failsafe to
  check — that means there was nothing in its scope to flag, not that the whole scene
  is render-ready. It's not an error.
