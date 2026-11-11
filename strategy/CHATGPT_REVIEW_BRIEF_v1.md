# Failsafe — Independent Review Brief (UI + v1 features round)

*For an independent reviewer (ChatGPT). You do not have the repo; everything you
need to review is inline below. Please be adversarial — the whole point of these
rounds is to catch what we can't see ourselves. Prior rounds found real bugs
(e.g. a competitor we'd missed, staleness-flag false PASSes), so dig in.*

---

## 0. What Failsafe is (context)

A **read-only** Blender 4.2+ extension (sold on Superhive) that checks physics /
simulation setup **and** simulation-cache integrity *before you render*. 23
checks in two groups: **Physics Setup** (1–16) and **Simulation Caches** (17–23).

**Cardinal rules (unchanged, non-negotiable):**
1. **Never report a false PASS.** Where Blender can't prove a thing, report
   **UNKNOWN**, never PASS. Five statuses: PASS / WARNING / FAIL / UNKNOWN / N-A.
2. **Read-only.** No scene edits, no file writes, no network.
3. **The differentiator:** for disk-backed caches we verify the *actual files on
   disk, every required frame*, instead of trusting Blender's "baked" flag
   (which stays True after the files are deleted). Our main competitor, **Cache
   Guardian ($14)**, only *samples* start/end/interior frames — a missing middle
   frame can pass their check and freeze a render. We name the exact missing
   frame.

Prior review rounds (R11–R18) are closed and verified against real Blender
(131 headless tests). This round adds a UI correctness fix and the v1 features.
**140 headless tests now pass on Blender 5.2.3** (also previously green on
4.2 / 4.5 / 5.0).

---

## 1. Change A — status-aware check titles (UI correctness fix)

**The bug we fixed.** Each check had one positive headline ("Simulation is
baked"). A *collapsed* result row showed that positive headline next to a
coloured severity dot. So a **warning/fail** could read as reassurance — an amber
dot beside "Simulation is baked" looks like "all good" until you expand it. The
owner caught this and called it correctly: "if the windows weren't expanded you
would read that completely wrong."

**The fix.** Each check now has two headlines: the green **positive** one (shown
on PASS) and a short **problem** one (shown on WARNING / FAIL). UNKNOWN keeps the
positive text, on the theory that the blue "?" icon already reframes it as
"can't confirm", never "all good".

Selector (the whole mechanism):

```python
class Status:
    PASS = "PASS"; WARNING = "WARNING"; FAIL = "FAIL"
    UNKNOWN = "UNKNOWN"; NA = "NOT APPLICABLE"

def display_name(meta, status):
    """The headline to show for a check given its (worst) status."""
    if status in (Status.WARNING, Status.FAIL) and getattr(meta, "name_bad", None):
        return meta.name_bad
    return meta.name
```

The per-check status is the **worst** of its findings (FAIL>WARNING>UNKNOWN>NA>PASS),
and the panel header + the text report both use `display_name(meta, worst)`.

The 23 title pairs (positive shown on PASS / problem shown on WARNING+FAIL):

| # | positive (PASS) | problem (WARNING / FAIL) |
|---|---|---|
| 1 | Scale and rotation are applied | Scale or rotation not applied |
| 2 | Rigid body mass fits the object | Rigid body mass looks wrong |
| 3 | Objects don't overlap at the start | Objects overlap at the start |
| 4 | Collision shape fits the object | Collision shape doesn't fit |
| 5 | Colliders are clean, not too heavy | Collider is heavy or messy |
| 6 | Rigid Body World is enabled | Rigid Body World isn't set up right |
| 7 | Cloth/soft body has a collider | Cloth/soft body has no collider |
| 8 | No negative or inherited scale | Negative or inherited scale |
| 9 | Object sizes look realistic | Object size looks off |
| 10 | Object origin sits on its shape | Object origin is off-center |
| 11 | Collision margin fits the object | Collision margin is too big |
| 12 | Moving colliders marked 'Animated' | Moving collider not marked 'Animated' |
| 13 | Rigid body constraints are intact | Rigid body constraint is broken |
| 14 | Collision modifier order is correct | Collision modifier is out of order |
| 15 | Cloth pin group is valid | Cloth pin group is broken |
| 16 | Fluid flow is inside the domain | Fluid flow is outside the domain |
| 17 | Simulation is baked | Simulation isn't properly baked |
| 18 | Cache files are really on disk | Cache files are missing from disk |
| 19 | Baked frames cover the render | Bake doesn't cover the render |
| 20 | Every frame is cached (no gaps) | Some frames are missing from the cache |
| 21 | Each sim has its own cache folder | Two sims share a cache folder |
| 22 | Cache is saved inside the project | Cache is saved outside the project |
| 23 | Frame rate/speed unchanged since bake | Frame rate/speed may have changed since bake |

Note on #17: its FAIL sub-case is "marked baked, but the cache on disk is
incomplete/empty". We deliberately chose "Simulation **isn't properly** baked"
(not "is not baked") so the header doesn't contradict a detail line that says
"marked baked".

**Questions for you:**
- Does the positive-title-on-UNKNOWN choice actually read as "can't confirm", or
  is there still a misread risk (e.g. blue "?" + "Cache files are really on disk"
  read as a statement)? Is there a better rule?
- Are any of the 23 *problem* titles inaccurate or ambiguous for any state the
  check can emit? (#6 can fire for disabled world, missing collection, object
  not in world, **or** low substeps; #20's warning case is "sampled, not every
  frame" — does "Some frames are missing from the cache" over/understate that?
  #23's warning is only the RBW time-scale case.)

---

## 2. Change B — opt-in "check before render" (new; the table-stakes feature)

Cache Guardian ships an opt-in pre-render warning; we didn't. Now we do. It must
be **non-blocking and read-only** — it must never change the scene, write files,
or stop a render, and a bug in it must not break a render.

Design: a `render_init` handler (fires **once** at the start of a render job, not
per frame) runs one scan; on problems it prints a clear console warning (so it
also lands in render-farm logs) and leaves a one-line banner in the panel. The
scan logic is split into a pure `run_render_check()` with no preference reads and
no side effects, so it's unit-testable. Full module:

```python
import bpy
from bpy.app.handlers import persistent
from . import engine

ADDON_ID = __package__  # "bl_ext.user_default.failsafe" when installed

def get_prefs():
    try:
        return bpy.context.preferences.addons[ADDON_ID].preferences
    except Exception:
        return None

class _HandlerCtx:
    __slots__ = ("scene", "_dg")
    def __init__(self, scene, depsgraph):
        self.scene = scene
        self._dg = depsgraph
    def evaluated_depsgraph_get(self):
        return self._dg

def run_render_check(scene, depsgraph=None, include_warnings=True):
    """Pure + read-only: reads no prefs, writes nothing, changes nothing."""
    if depsgraph is None:
        try:
            depsgraph = bpy.context.evaluated_depsgraph_get()
        except Exception:
            depsgraph = None
    ctx = _HandlerCtx(scene, depsgraph)
    results = engine.run_all(ctx)
    counts = engine.summary_counts(results)
    f = counts[engine.Status.FAIL]; w = counts[engine.Status.WARNING]
    u = counts[engine.Status.UNKNOWN]
    problem = (f > 0) or (include_warnings and w > 0)
    banner = ("Last render check: %d fail, %d warning, %d unknown" % (f, w, u)
              if problem else "Last render check: no problems (%d unknown)" % u)
    return {"fail": f, "warning": w, "unknown": u, "problem": problem,
            "banner": banner, "fail_lines": _fail_lines(results)}

@persistent
def failsafe_render_init(scene, depsgraph=None):
    """Fires once at render start (opt-in). Never blocks the render."""
    try:
        prefs = get_prefs()
        if prefs is None or not getattr(prefs, "check_before_render", False):
            return
        include_warn = bool(getattr(prefs, "include_warnings", True))
        info = run_render_check(scene, depsgraph, include_warnings=include_warn)
        try:
            wm = bpy.context.window_manager
            wm.failsafe_render_banner = info["banner"]
            wm.failsafe_render_had_problem = bool(info["problem"])
        except Exception:
            pass
        if not info["problem"]:
            return
        sep = "=" * 64
        lines = [sep, "FAILSAFE — problems found right before render:",
                 "  %d FAIL, %d WARNING, %d UNKNOWN"
                 % (info["fail"], info["warning"], info["unknown"])]
        if info["fail_lines"]:
            lines.append("FAIL:"); lines.extend(info["fail_lines"])
        lines.append("(Read-only check; the render was NOT stopped.)")
        lines.append(sep)
        print("\n".join(lines))
    except Exception as e:   # never let a check bug break a render
        try: print("Failsafe render check skipped (internal error): %r" % e)
        except Exception: pass
```

The handler is appended to `bpy.app.handlers.render_init` on register and removed
on unregister (dedup-guarded by `__name__`). The add-on preference
`check_before_render` defaults **off**; a sub-toggle `include_warnings` (default
on) decides whether warnings count as a problem or only hard fails.

**Verified live** in the owner's Blender: a real `bpy.ops.render.render()` fired
the handler once, printed the warning naming the exact missing frame (247), set
the banner, and the render completed — `rendered_ok: true`, not stopped.

**Questions for you:**
- Is `render_init` the right hook vs `render_pre` (per-frame) or `render_write`?
  We chose `render_init` to run once. Does `render_init` reliably fire for F12
  still renders, animation renders, **and** `blender -b -f`/`-a` command-line
  renders and the render farm paths that matter? If some path skips
  `render_init`, we silently don't warn there.
- Any risk calling `engine.run_all()` (which builds BVH trees / reads evaluated
  geometry and enumerates cache files on disk) from inside `render_init`? Could
  `bpy.context.evaluated_depsgraph_get()` be unsafe/empty at that moment, and if
  so is "degrade to UNKNOWN on the geometry checks" acceptable? Threading?
- Is a **console print + panel banner** enough value, given the render still
  proceeds? Would a non-blocking popup/report be better, or is console the right
  call for farm compatibility? We deliberately do **not** offer a "cancel render"
  option (read-only philosophy) — do you agree, or is an opt-in hard-stop worth
  having?
- We write two `WindowManager` props from the handler (`failsafe_render_banner`,
  `failsafe_render_had_problem`). Is writing WM props from a render handler safe,
  or should that be deferred?

---

## 3. Change C — guided fix: "Open Physics settings" button

Each actionable, per-object finding now shows one button that (a) selects +
activates the object and (b) switches the Properties editor to the tab where the
fix lives — **PHYSICS** for rigid/cloth/fluid/cache checks, **OBJECT** for
transform/size checks (1, 8, 9). It only changes UI state + selection; no scene
data. Scene-wide findings (e.g. shared cache location) have no button and rely on
their written Tip. Core of the operator:

```python
class FAILSAFE_OT_show_physics(Operator):
    bl_idname = "failsafe.show_physics"
    bl_options = {"REGISTER", "UNDO"}
    object_name: StringProperty()
    target: StringProperty(default="PHYSICS")   # PHYSICS / OBJECT / ...
    def execute(self, context):
        # select+activate object (restore-on-failure, same as the Select button)
        # then:
        switched = False
        for area in context.screen.areas:
            if area.type == "PROPERTIES":
                try:
                    area.spaces.active.context = self.target
                    switched = True
                except Exception:
                    pass
                area.tag_redraw()
        if not switched:
            self.report({"INFO"},
                        "Open a Properties editor to see the %s settings." % self.target.title())
        return {"FINISHED"}
```

**Questions for you:**
- It switches **every** Properties editor in the current screen to the target
  tab. Surprising if the user has two Properties editors pinned to different
  tabs? Should it switch only one (and which)?
- Selection change carries UNDO. Is "selects an object + changes which Properties
  tab is shown" still fairly called **read-only** in our marketing, or should we
  soften that claim to "makes no changes to your scene *data*"?
- `space.context = "PHYSICS"` raises if the object has no physics context
  available? (We wrap it.) Any Blender-version gotchas with the context enum
  strings (PHYSICS/OBJECT/DATA/SCENE)?

---

## 4. Change D — opt-in "Explain" mode (why-it-matters per check)

A "?" toggle (default **off**) reveals one plain-English rationale line under
each expanded finding — distinct from the finding's *message* (what's wrong now)
and *Tip* (how to fix). Off by default so the normal problem view stays clean.
The 23 lines (please sanity-check the **physics accuracy** of these — a wrong
explanation would undermine trust):

1. Physics uses an object's real size and pose. Unapplied scale or rotation makes collisions and cloth behave as if the object were a different size or angle than it looks.
2. Mass decides how heavy a rigid body feels. A value far off for its size makes it drift like a balloon or smash through things.
3. Rigid bodies that already overlap on the first frame get shoved apart violently as the sim starts.
4. A Convex Hull collision shape fills in any hollow, so cups, bowls and rooms act solid. Hollow shapes need a Mesh shape instead.
5. Collision surfaces that are very dense or have internal/overlapping faces make a simulation slow and jittery.
6. Rigid bodies only move if a Rigid Body World exists, is enabled, and actually contains them.
7. Cloth and soft bodies only land on objects that have a Collision modifier. Without one, they fall straight through.
8. Negative or parent-inherited scale flips an object's normals and distorts its collision size, so physics behaves backwards.
9. Blender's solver is tuned around 1-metre objects. Very tiny or very huge objects simulate unstably.
10. A rigid body spins around its origin. An origin far from the shape makes it tumble off-centre.
11. The collision margin is an invisible buffer around a body. Too large, and objects float with a visible gap.
12. A passive collider that is animated must be marked 'Animated', or its collision shape stays frozen at the start frame.
13. A rigid-body constraint (a hinge or chain link) needs two valid bodies, or it silently holds nothing together.
14. Collision must sit below any deforming modifiers, or cloth collides with the object's undeformed shape.
15. A cloth pin group holds part of the cloth in place. If it's empty or missing, the whole cloth drops.
16. A fluid domain only fills if a Flow or Inflow source sits inside it.
17. An unbaked simulation is re-computed at render time and can differ from what you see in the viewport — or freeze a render farm.
18. Blender keeps reporting 'baked' even after the cache files are gone. The render needs the actual files on disk, so Failsafe checks them.
19. If the bake stops before the last rendered frame, the simulation freezes for the rest of the shot.
20. A single missing cache frame is a freeze or pop at that exact moment in the render.
21. Two simulations pointed at the same cache folder overwrite each other's frames.
22. A cache saved outside the project folder won't be found on another machine or a render farm.
23. Blender doesn't re-time an existing bake. Changing FPS or time scale after baking makes it play back at the wrong speed.

**Questions for you:**
- Any of these 23 explanations **technically wrong or misleading** to a Blender
  user? (We care most about #4 convex hull / mesh shape, #11 collision margin,
  #14 modifier order, #19 vs #20 wording, #23 time-remap behaviour.)

---

## 5. The product philosophy driving this (so your advice fits)

The owner's stance, held since day one and overriding "stay narrow + premium"
advice: **more capability for a lower price wins.** ("Add-on C does X+Y+Z for
$12 beats A does X for $14 — I'm buying C all day.") So the plan is: broadest sim
coverage + full-frame verification + honest UNKNOWN + these v1 features, priced
to undercut Cache Guardian ($14), likely **$9–12**. Please critique *within* that
philosophy, not against it — but do flag if any feature actively hurts trust,
clarity, or the read-only promise.

---

## 6. What we're explicitly asking you

1. **Correctness / honesty:** does anything here risk a misread or a false sense
   of safety? (The title system especially — that was the whole point.)
2. **The render handler:** hook choice, reliability across render paths, safety
   of running a full scan + WM writes mid-render, and whether console-only is
   enough.
3. **The guided-fix & read-only claim:** is "read-only" still honest with a
   button that selects objects and flips Properties tabs?
4. **Explain content accuracy** (the 23 lines).
5. **Launch readiness:** with v1 done (status-aware titles, per-frame evidence,
   guided fix, opt-in pre-render, Explain, honest summary), what's the single
   most important thing still missing before a paid launch — and is there
   anything here you'd *cut* as scope creep?
6. **Anything we didn't ask about but should have.**

Everything above is implemented, deployed, and covered by 140 passing headless
tests on Blender 5.2.3. Be blunt.
