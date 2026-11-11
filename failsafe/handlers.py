# SPDX-License-Identifier: GPL-3.0-or-later
"""Opt-in 'check before render' — a read-only, non-cancelling render warning.

When the user turns it on in the add-on preferences, Failsafe runs its scan once
at the start of a render. If it finds problems it prints a clear warning to the
system console (so it also lands in render-farm logs) and leaves a one-line
banner in the panel. It NEVER changes the scene, writes files, touches the
network, or cancels the render — a bug in here must not break a render, so the
whole handler is wrapped in try/except.

"Non-cancelling", not "non-blocking": the scan runs synchronously at render
start, so on a very heavy scene it can add a short delay before rendering begins
— it just never stops or alters the render.

The scan logic lives in ``run_render_check()``, a pure function that reads
nothing from preferences and writes nothing back — so the test harness can drive
it directly. The handler on top is the only part that reads the preference and
updates the UI.
"""
import bpy
from bpy.app.handlers import persistent

from . import engine

# In an installed extension this is "bl_ext.user_default.<id>", which is exactly
# the key Blender files the add-on's preferences under.
ADDON_ID = __package__


def get_prefs():
    """The add-on preferences, or None if they aren't registered (e.g. tests)."""
    try:
        return bpy.context.preferences.addons[ADDON_ID].preferences
    except Exception:
        return None


class _HandlerCtx:
    """Minimal stand-in for a Blender context during a render handler."""

    __slots__ = ("scene", "_dg")

    def __init__(self, scene, depsgraph):
        self.scene = scene
        self._dg = depsgraph

    def evaluated_depsgraph_get(self):
        return self._dg


def _fail_lines(results):
    by_id = {m.id: m for m in engine.CHECKS}
    out = []
    for r in results:
        if r.status == engine.Status.FAIL:
            who = (" [%s]" % r.object_name) if r.object_name else ""
            meta = by_id.get(r.check_id)
            title = (engine.display_name(meta, engine.Status.FAIL)
                     if meta else r.check_name)
            out.append("  - %s%s: %s" % (title, who, r.message))
    return out


def render_banner(f, w, u, problem):
    """The panel banner for a render check. Honesty rule: a scene with only
    UNKNOWN results is NOT 'no problems' — those are the exact checks that
    couldn't be verified, which is what a buyer most wants to know before a
    render. Never present them as a clean result."""
    if problem:
        return "Last render check: %d fail, %d warning, %d unknown" % (f, w, u)
    if u > 0:
        return "Last render check: no confirmed problems, %d unverified" % u
    return "Last render check: all clear"


def run_render_check(scene, depsgraph=None, include_warnings=True):
    """Run every check against ``scene`` and summarise it for a pre-render warning.

    Read-only and side-effect-free: it reads no preferences and writes no
    properties (it does read the scene and build the same evaluated data a scan
    does). Returns a dict the handler (or a test) can act on.
    """
    if depsgraph is None:
        try:
            depsgraph = bpy.context.evaluated_depsgraph_get()
        except Exception:
            depsgraph = None
    ctx = _HandlerCtx(scene, depsgraph)
    results = engine.run_all(ctx)
    counts = engine.summary_counts(results)
    f = counts[engine.Status.FAIL]
    w = counts[engine.Status.WARNING]
    u = counts[engine.Status.UNKNOWN]
    problem = (f > 0) or (include_warnings and w > 0)
    banner = render_banner(f, w, u, problem)
    return {
        "fail": f, "warning": w, "unknown": u,
        "problem": problem, "banner": banner,
        "fail_lines": _fail_lines(results),
    }


@persistent
def failsafe_render_init(scene, depsgraph=None):
    """Fires once at the start of a render (opt-in). Never cancels the render."""
    wm = None
    try:
        prefs = get_prefs()
        if prefs is None or not getattr(prefs, "check_before_render", False):
            return
        # Mark the banner "running" BEFORE the scan, so if the scan raises the
        # panel can't keep showing an earlier success (V06: no stale banner).
        try:
            wm = bpy.context.window_manager
            wm.failsafe_render_banner = "Render check running…"
            wm.failsafe_render_had_problem = False
        except Exception:
            wm = None

        include_warn = bool(getattr(prefs, "include_warnings", True))
        info = run_render_check(scene, depsgraph, include_warnings=include_warn)

        # Leave the result banner in the panel (a UI property — not scene data).
        try:
            if wm is not None:
                wm.failsafe_render_banner = info["banner"]
                wm.failsafe_render_had_problem = bool(info["problem"])
        except Exception:
            pass

        # Always print a one-line summary so the UNKNOWN count is visible in the
        # terminal and farm logs, even when nothing is a confirmed problem.
        head = ("FAILSAFE render check: %d FAIL, %d WARNING, %d UNKNOWN"
                % (info["fail"], info["warning"], info["unknown"]))
        if not info["problem"]:
            tail = (" — no confirmed problems" if info["unknown"]
                    else " — all clear")
            print(head + tail)
            return

        # Confirmed problems: the prominent, detailed warning.
        sep = "=" * 64
        lines = [sep, head, "(problems found right before render)"]
        if info["fail_lines"]:
            lines.append("FAIL:")
            lines.extend(info["fail_lines"])
        lines.append("(Read-only check; the render was NOT stopped.)")
        lines.append(sep)
        print("\n".join(lines))
    except Exception as e:  # never let a check bug break a render
        # Replace any "running…"/stale banner so a crash can't look like success.
        try:
            if wm is not None:
                wm.failsafe_render_banner = ("Render check didn't finish — "
                                             "see console")
                wm.failsafe_render_had_problem = True
        except Exception:
            pass
        try:
            print("Failsafe render check skipped (internal error): %r" % e)
        except Exception:
            pass


class FAILSAFE_AddonPreferences(bpy.types.AddonPreferences):
    bl_idname = ADDON_ID

    check_before_render: bpy.props.BoolProperty(
        name="Check before render",
        description=("Run a read-only Failsafe scan at the start of each render "
                     "and warn in the console if there are problems. Never "
                     "changes the scene or stops the render"),
        default=False,
    )
    include_warnings: bpy.props.BoolProperty(
        name="Also warn on warnings",
        description="Warn before render for warnings too, not only hard fails",
        default=True,
    )

    def draw(self, context):
        layout = self.layout
        layout.prop(self, "check_before_render")
        row = layout.row()
        row.enabled = self.check_before_render
        row.prop(self, "include_warnings")


def _ensure_handler(add):
    handlers = bpy.app.handlers.render_init
    present = [h for h in handlers
               if getattr(h, "__name__", "") == "failsafe_render_init"]
    if add and not present:
        handlers.append(failsafe_render_init)
    elif not add:
        for h in present:
            handlers.remove(h)


def register():
    bpy.utils.register_class(FAILSAFE_AddonPreferences)
    bpy.types.WindowManager.failsafe_render_banner = bpy.props.StringProperty(
        default="")
    bpy.types.WindowManager.failsafe_render_had_problem = bpy.props.BoolProperty(
        default=False)
    _ensure_handler(True)


def unregister():
    _ensure_handler(False)
    try:
        del bpy.types.WindowManager.failsafe_render_had_problem
        del bpy.types.WindowManager.failsafe_render_banner
    except Exception:
        pass
    bpy.utils.unregister_class(FAILSAFE_AddonPreferences)
