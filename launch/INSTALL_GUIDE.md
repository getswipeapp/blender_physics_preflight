# Failsafe — Quick Start (for beginners)

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
| **PASS** | Checked, and it's fine. |
| **WARNING** | Worth a look — might be intentional, might be a mistake. |
| **FAIL** | A real problem that will likely hurt your render. |
| **UNKNOWN** | Blender can't confirm this — treat it as "not verified," not a pass. |
| **NOT APPLICABLE** | This check doesn't apply to your scene. |

- Click **Select Object** on any result to jump straight to the object it's about.
- Click **Export Report** to save the report **as a text block inside your
  `.blend`** and copy it to your clipboard. (It does **not** write a separate
  `.txt` file to your computer — open it in Blender's Text Editor, or paste it
  from the clipboard into any document.)

## Why "UNKNOWN" is a feature, not a bug

Other tools will cheerfully say "all good" when they actually can't tell. Failsafe
won't. If Blender genuinely can't confirm something — a packed
geometry-nodes bake, an in-memory cache, an unsaved file — it says **UNKNOWN** so
you know to check it yourself, instead of trusting a green light that was never real.

## Troubleshooting

- **No "Failsafe" tab?** Enable the add-on in **Preferences → Add-ons**
  (search its name; the checkbox should be ticked).
- **Cache checks all say UNKNOWN?** Save your `.blend` and scan again.
- **Overlap check says UNKNOWN?** Move the timeline to the first frame and
  re-scan — it checks overlaps at the start frame.
- **Nothing to scan?** The scene may have no physics — that's a clean bill of
  health, not an error.
