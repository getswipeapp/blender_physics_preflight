# Physics Preflight — Beginner GUI Acceptance Test (for Keith)

This is the one part of certification a person has to do by hand, because it
checks the add-on works through Blender's real window — buttons, panels, the
report — not just the automated tests Claude already ran.

**Time needed:** about 15 minutes.
**You need:** Blender 5.2 (the version you already have) and the file
`physics_preflight_c977ac2.zip` from your Downloads folder.

Work top to bottom. After each step there's a **✅ What you should see** line.
If what you see doesn't match, stop and tell Claude exactly which step and what
happened — that's a finding, not a failure on your part.

---

## Part A — Install and turn it on

1. Open Blender 5.2.
2. Top menu: **Edit → Preferences**.
3. On the left, click **Get Extensions** (or **Add-ons**).
4. Top-right corner of that window, click the **▼ (dropdown arrow)** → **Install from Disk…**
5. Pick `physics_preflight_c977ac2.zip` from Downloads, click **Install from Disk**.
6. In the search box type `physics`. The add-on **Physics Preflight** should appear.
7. Make sure the **checkbox next to its name is ticked** (enabled).

   ✅ *What you should see:* "Physics Preflight" listed with a tick. No red error
   text anywhere.

8. Close Preferences.

---

## Part B — Find the panel

1. In the main 3D view, press **N** (or click the small **<** arrow on the right edge)
   to open the side panel.
2. Look down the vertical tabs on the right for a tab labelled **Physics Preflight**.
   Click it.

   ✅ *What you should see:* a panel with a **Scan** button (and an Export option).

---

## Part C — The real test: catch a deleted cache ("no false pass")

This is the whole point of the product — proving it notices when cache files are
gone, even though Blender still *thinks* the sim is baked. Do this one carefully.

1. **Save the file first:** **File → Save As…**, save it somewhere easy like the
   Desktop as `preflight_test.blend`. (The add-on needs a saved file to find cache
   files — that's expected and correct.)
2. Add a quick cloth sim:
   - **Add → Mesh → Grid.** With it selected, go to the **Physics Properties** tab
     (the blue bouncing-ball icon in the right-hand properties panel).
   - Click **Cloth**.
   - Scroll down to **Cache**, tick **Disk Cache** (this makes it write files you
     can see), then click **Bake**. Wait for the bar to finish.
3. Open the Physics Preflight panel (Part B) and click **Scan**.

   ✅ *What you should see:* the cloth cache checks report **green / PASS** —
   it's baked and the files are there.

4. Now delete the cache files behind Blender's back:
   - In Finder, open the folder where you saved `preflight_test.blend`.
   - There's a folder next to it called **`blendcache_preflight_test`**. Open it,
     select all the files inside, and **move them to the Trash**. (Leave the
     `.blend` itself alone.)
5. Back in Blender — **do not re-bake, do not touch anything** — click **Scan** again.

   ✅ *What you should see (THE KEY RESULT):* the cache checks now turn
   **red/FAIL** (or say the cache is missing/incomplete). Blender's own Physics
   panel will still show the sim as "baked" — but Physics Preflight should
   **not** be fooled. If it still shows green here, that is the single most
   important bug to report.

---

## Part D — Report export and "it didn't touch my scene"

1. In the panel, use **Export** (report to a text block / clipboard).

   ✅ *What you should see:* a readable report listing the checks. Open Blender's
   **Text Editor** (change an area's editor type, or a new window) and confirm a
   new text block with the report exists.

2. Confirm the scan didn't change your scene: your selected object, the current
   frame, and the objects in the scene should all be exactly as before.

   ✅ *What you should see:* nothing moved, nothing got added or deleted, the
   frame number is unchanged.

---

## Part E — Quick "does it even open" smoke (optional but nice)

If you have 2 more minutes: with the cloth scene above, also try a **Fluid** domain
or a **Rigid Body** and hit **Scan** — just confirm the panel shows results and
Blender doesn't throw an error popup. We're not checking correctness here, just
that nothing crashes.

---

## How to report back

For each part, just tell Claude **"A ok, B ok, C ok…"** or describe anything that
looked wrong (a red error, a crash, or — most important — Part C still showing
green after you trashed the cache files). A screenshot is perfect if something
looks off. That's it — Claude turns your notes into the GUI row of the evidence
matrix.
