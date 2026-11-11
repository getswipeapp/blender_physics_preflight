# SPDX-License-Identifier: GPL-3.0-or-later
"""The N-panel UI: a one-click scan with two grouped, collapsible result lists.

Severity is shown with custom COLOURED icons (red fail / amber warning / blue
unknown / green pass) so problems stand out, and every finding's explanation is
word-wrapped so the full text is readable without widening the panel. Each
finding can be collapsed to keep a long list tidy (expanded by default).
"""
import os
import textwrap

import bpy
import bpy.utils.previews
from bpy.types import Panel

from .engine import (CHECKS, Status, GROUP_SETUP, GROUP_CACHE, display_name)
from .help_text import HELP

# Fallback monochrome icons if the coloured previews fail to load.
_STATUS_ICON = {
    Status.PASS: "CHECKMARK",
    Status.WARNING: "ERROR",
    Status.FAIL: "CANCEL",
    Status.UNKNOWN: "QUESTION",
    Status.NA: "DOT",
}

_ICON_FILE = {
    Status.FAIL: "fail.png",
    Status.WARNING: "warn.png",
    Status.UNKNOWN: "unknown.png",
    Status.PASS: "pass.png",
    Status.NA: "na.png",
}

_preview_coll = None

# Per-check "take me there" jump: which Properties-editor tab fixes this check,
# and the button label. Only drawn for per-object findings; scene-wide findings
# (e.g. a shared cache location) rely on their written Tip instead.
_PHYS = ("PHYSICS", "Open Physics settings")
_OBJ = ("OBJECT", "Open Object settings")
_FIX_TARGET = {
    1: _OBJ, 8: _OBJ, 9: _OBJ,                     # transforms / size
    2: _PHYS, 4: _PHYS, 5: _PHYS, 6: _PHYS, 7: _PHYS, 10: _PHYS, 11: _PHYS,
    12: _PHYS, 13: _PHYS, 14: _PHYS, 15: _PHYS, 16: _PHYS,   # rigid/cloth/fluid
    17: _PHYS, 18: _PHYS, 19: _PHYS, 20: _PHYS, 21: _PHYS, 22: _PHYS, 23: _PHYS,
}


def _get_prefs(context):
    """The add-on preferences, or None if unavailable."""
    try:
        return context.preferences.addons[__package__].preferences
    except Exception:
        return None


def _icon_value(status):
    """icon_id for the coloured severity icon, or 0 if previews unavailable."""
    if _preview_coll is None:
        return 0
    fn = _ICON_FILE.get(status)
    try:
        return _preview_coll[fn].icon_id if fn else 0
    except Exception:
        return 0


def _status_label(row, text, status):
    """A label with the coloured severity icon (falls back to a built-in icon)."""
    iv = _icon_value(status)
    if iv:
        row.label(text=text, icon_value=iv)
    else:
        row.label(text=text, icon=_STATUS_ICON.get(status, "DOT"))


def _wrap_chars(context):
    """Estimate how many characters fit on one line of the panel."""
    region = context.region
    width = region.width if region else 300
    try:
        uifac = context.preferences.system.ui_scale
    except Exception:
        uifac = 1.0
    # Panel padding + the indent + an icon eats some width; be conservative so
    # text wraps a touch early rather than truncating.
    usable = max(width - 62, 70)
    return max(int(usable / (7.3 * uifac)), 14)


def _wrap_label(col, context, text, status=None, indent=1.6):
    """Draw `text` word-wrapped across as many label rows as needed. The first
    row carries the coloured severity icon (when `status` is given); the rest
    align under it."""
    maxc = _wrap_chars(context)
    lines = textwrap.wrap(text, maxc) or [text]
    for i, ln in enumerate(lines):
        r = col.row(align=True)
        if indent:
            r.separator(factor=indent)
        if i == 0 and status is not None:
            _status_label(r, ln, status)
        elif status is not None:
            r.label(text=ln, icon="BLANK1")   # keep text aligned under the icon
        else:
            r.label(text=ln)


def _worst_for_check(items, check_id):
    sevs = {Status.FAIL: 4, Status.WARNING: 3, Status.UNKNOWN: 2,
            Status.NA: 1, Status.PASS: 0}
    best = None
    for it in items:
        if it.check_id == check_id:
            if best is None or sevs[it.status] > sevs[best]:
                best = it.status
    return best


class FAILSAFE_PT_panel(Panel):
    bl_label = "Failsafe"
    bl_idname = "FAILSAFE_PT_panel"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Failsafe"

    def draw(self, context):
        layout = self.layout
        wm = context.window_manager

        col = layout.column(align=True)
        col.scale_y = 1.3
        col.operator("failsafe.scan", icon="VIEWZOOM")

        row = layout.row(align=True)
        row.operator("failsafe.export_report", icon="TEXT")
        row.prop(wm, "failsafe_show_passed", text="", icon="HIDE_OFF", toggle=True)
        row.prop(wm, "failsafe_explain", text="", icon="QUESTION", toggle=True)

        # Opt-in: check automatically at the start of each render.
        prefs = _get_prefs(context)
        if prefs is not None:
            layout.prop(prefs, "check_before_render", icon="RENDER_STILL")
            banner = getattr(wm, "failsafe_render_banner", "")
            if banner:
                bad = getattr(wm, "failsafe_render_had_problem", False)
                if bad:
                    icon = "ERROR"
                elif "unverified" in banner:
                    icon = "QUESTION"      # unknowns -> not a clean tick
                else:
                    icon = "CHECKMARK"
                layout.box().label(text=banner, icon=icon)

        if not wm.failsafe_has_run:
            box = layout.box()
            box.label(text="Press Scan Scene to check this scene.", icon="INFO")
            box.label(text="Read-only. Nothing is changed.")
            return

        items = wm.failsafe_results

        # summary line (coloured counts)
        c = {Status.FAIL: 0, Status.WARNING: 0, Status.UNKNOWN: 0}
        for m in CHECKS:
            w = _worst_for_check(items, m.id)
            if w in c:
                c[w] += 1
        active_filter = wm.failsafe_filter
        s = layout.row(align=True)
        s.scale_y = 1.2
        self._filter_button(s, c[Status.FAIL], Status.FAIL, active_filter)
        self._filter_button(s, c[Status.WARNING], Status.WARNING, active_filter)
        self._filter_button(s, c[Status.UNKNOWN], Status.UNKNOWN, active_filter)
        if active_filter:
            fr = layout.row()
            fr.label(text="Showing %s only — click its icon again to clear."
                     % active_filter.lower(), icon="FILTER")

        collapsed = set(wm.failsafe_collapsed.split()) if wm.failsafe_collapsed else set()
        show_passed = wm.failsafe_show_passed
        explain = wm.failsafe_explain
        for group in (GROUP_SETUP, GROUP_CACHE):
            self._draw_group(context, layout, items, group, show_passed,
                             collapsed, active_filter, explain)

    def _filter_button(self, row, count, status, active_filter):
        """A clickable severity tally that filters the list to that severity."""
        iv = _icon_value(status)
        if iv:
            op = row.operator("failsafe.set_filter", text="%d" % count,
                              icon_value=iv, depress=(active_filter == status))
        else:
            op = row.operator("failsafe.set_filter", text="%d" % count,
                              icon=_STATUS_ICON.get(status, "DOT"),
                              depress=(active_filter == status))
        op.sev = status

    def _draw_group(self, context, layout, items, group, show_passed, collapsed,
                    active_filter="", explain=False):
        box = layout.box()
        box.label(text=group,
                  icon="PHYSICS" if group == GROUP_SETUP else "FILE_CACHE")
        drew_any = False
        for m in [m for m in CHECKS if m.group == group]:
            worst = _worst_for_check(items, m.id)
            if worst is None:
                worst = Status.NA
            if not show_passed and worst in (Status.PASS, Status.NA):
                continue
            # Severity filter from the clickable tally (empty = show all).
            if active_filter and worst != active_filter:
                continue
            drew_any = True
            is_collapsed = str(m.id) in collapsed

            # Clickable header: coloured severity icon + expand/collapse arrow.
            # The headline matches the icon colour: the green "pass" wording when
            # the check passes, and a short problem wording the moment it is a
            # warning or fail — so a collapsed row never reads as reassurance
            # while its dot is amber or red.
            head = box.row(align=True)
            head.scale_y = 1.15
            _status_label(head, "", worst)
            op = head.operator(
                "failsafe.toggle_detail",
                text=display_name(m, worst),
                icon="TRIA_RIGHT" if is_collapsed else "TRIA_DOWN",
                emboss=False)
            op.key = str(m.id)
            if is_collapsed:
                continue

            # Optional "why it matters" line (Explain mode), once per check.
            if explain:
                htext = HELP.get(m.id, "")
                if htext:
                    hb = box.column(align=True)
                    _wrap_label(hb, context, "Why: " + htext, status=None,
                                indent=1.6)

            # Expanded detail: wrapped message(s), select button, wrapped hint.
            for it in items:
                if it.check_id != m.id:
                    continue
                if not show_passed and it.status in (Status.PASS, Status.NA):
                    continue
                sub = box.column(align=True)
                _wrap_label(sub, context, it.message, status=it.status)
                if it.object_name:
                    orow = sub.row(align=True)
                    orow.separator(factor=1.6)
                    target = _FIX_TARGET.get(it.check_id)
                    if target and it.status not in (Status.PASS, Status.NA):
                        # One button that both selects the object and jumps to the
                        # tab where the fix lives.
                        o = orow.operator(
                            "failsafe.show_physics",
                            text="%s  (%s)" % (target[1], it.object_name),
                            icon="PHYSICS" if target[0] == "PHYSICS"
                            else "OBJECT_DATA")
                        o.object_name = it.object_name
                        o.target = target[0]
                    else:
                        o = orow.operator("failsafe.select_object",
                                          text="Select '%s'" % it.object_name,
                                          icon="RESTRICT_SELECT_OFF")
                        o.object_name = it.object_name
                if it.hint:
                    _wrap_label(sub, context, "Tip: " + it.hint, status=None,
                                indent=1.6)
        if not drew_any:
            if active_filter:
                box.label(text="No %s items in this group." % active_filter.lower(),
                          icon="BLANK1")
            else:
                box.label(
                    text="No problems reported (toggle the eye for details).",
                    icon="INFO")


classes = (FAILSAFE_PT_panel,)


def _load_icons():
    global _preview_coll
    try:
        pcoll = bpy.utils.previews.new()
        icon_dir = os.path.join(os.path.dirname(__file__), "icons")
        for fn in set(_ICON_FILE.values()):
            path = os.path.join(icon_dir, fn)
            if os.path.isfile(path):
                pcoll.load(fn, path, "IMAGE")
        _preview_coll = pcoll
    except Exception:
        _preview_coll = None


def _unload_icons():
    global _preview_coll
    if _preview_coll is not None:
        try:
            bpy.utils.previews.remove(_preview_coll)
        except Exception:
            pass
        _preview_coll = None


def register():
    _load_icons()
    for c in classes:
        bpy.utils.register_class(c)


def unregister():
    for c in reversed(classes):
        bpy.utils.unregister_class(c)
    _unload_icons()
