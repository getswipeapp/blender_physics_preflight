# Failsafe — Screenshots & Demo Shot-List

Superhive listings sell on **genuine screenshots** and (optionally) a short demo.
This is the shot-by-shot plan so you (Keith) can record them on your Mac. Every
shot must be the real add-on on a real scene — no mockups (a selling rule).

**Record only after the fixed build passes an independent re-review and the
multi-version tests** — the screenshots must show behaviour that's actually been
verified, or the listing over-promises.

**Gear:** newest Blender you have installed, the add-on installed, and a screen
recorder (macOS **Shift-Cmd-5**).

---

## Superhive gallery requirements (confirm current specs on the site)

Per ChatGPT's reading of Superhive's seller guidelines — double-check when you
upload, as specs change:

- **At least 5** gallery images.
- **2:1 aspect ratio**, **minimum 1200 px wide** (PNG or JPG).
- Written **install instructions and FAQs on the product page itself** — a
  downloadable guide alone isn't enough. (Reuse `INSTALL_GUIDE.md` + a short FAQ.)
- A demo **video is optional**, not required.
- **Don't** use the Blender logo or brand name as a decorative element in images.
- Plan to answer buyer support within Superhive's **72-hour** goal.

## A. Still screenshots (aim for 5–6, 2:1, ≥1200 px)

Use a simple, good-looking scene.

1. **The panel, fresh** — the sidebar open before scanning, showing "Scan Scene."
2. **A full result list** — after a scan on a scene with a mix of PASS / WARNING /
   FAIL, so all the colours show. The money shot.
3. **The headline FAIL (single missing frame)** — a close-up of #18/#20 failing
   because **one frame** is missing from an otherwise-baked cache. This proves the
   frame-by-frame verification far better than a wiped folder does. Show the
   message naming the missing frame.
4. **Select Object in action** — a FAIL result beside the actual problem object
   selected in the viewport.
5. **The two groups** — results showing the "Physics Setup" and "Simulation
   Caches" headings, communicating breadth (23 checks).
6. *(Optional)* **An honest UNKNOWN** — e.g. a packed geometry-nodes bake reported
   UNKNOWN, to show the product doesn't bluff.

## B. Demo video (optional, 60–90 s, no voiceover needed)

| Time | On screen |
|------|-----------|
| 0:00–0:08 | A scene that looks fine. Card: "Looks ready to render…" |
| 0:08–0:20 | Open the sidebar, click **Scan Scene**. |
| 0:20–0:42 | Results appear. Pause on the **FAIL** for the single missing cache frame (#18/#20). Card: "Blender said this was baked. One frame is gone." |
| 0:42–0:55 | Click **Select Object** → viewport jumps to the culprit. |
| 0:55–1:10 | Scroll the rest: a couple of WARNINGs and an honest UNKNOWN. |
| 1:10–1:25 | Card: "23 checks. Physics setup + real cache verification. One click." |
| 1:25–1:30 | End card: "Failsafe" + the price. |

## C. Staging the hero "broken cache" scene (the strong version)

The best demo shows a **single missing frame**, which the fixed build now catches
(the old code didn't). Stage it honestly:

1. Make a simple **cloth** sim (a plane falling on a cube).
2. **Bake** it (Physics Properties → Cache → **Bake**), then **save**.
3. In Finder, open the `blendcache_<yourfile>` folder next to the `.blend` and
   delete **one** frame file (e.g. the last `..._000010_00.bphys`) — not the whole
   folder.
4. Reopen the file. Blender still shows it as "baked" — but a frame is gone.
5. Scan. **#18 and #20 go FAIL**, naming the missing frame. That's your hero moment.

> Want it repeatable? I can script a tiny `.blend` generator that builds this exact
> single-frame-missing scene, so you record the same thing every time. That's
> test-fixture work and doesn't touch the reviewed add-on code.

## D. Before any of this goes public (reminder)

- Independent **re-review PASS** on the fixed build.
- Headless tests on Blender **4.2.9 / 4.5.9 / 5.0.1 / 5.2.3** — ✅ done (162/162 each).
- Record on the newest Blender so the UI matches what buyers see.
- Keith's final approval on screenshots, text, price, and publishing.
