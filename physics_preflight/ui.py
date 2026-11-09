# SPDX-License-Identifier: GPL-3.0-or-later
"""The N-panel UI: a one-click scan with two grouped result lists."""
import bpy
from bpy.types import Panel

from .engine import (CHECKS, Status, GROUP_SETUP, GROUP_CACHE)

_STATUS_ICON = {
    Status.PASS: "CHECKMARK",
    Status.WARNING: "ERROR",
    Status.FAIL: "CANCEL",
    Status.UNKNOWN: "QUESTION",
    Status.NA: "DOT",
}


def _worst_for_check(items, check_id):
    sevs = {Status.FAIL: 4, Status.WARNING: 3, Status.UNKNOWN: 2,
            Status.NA: 1, Status.PASS: 0}
    best = None
    for it in items:
        if it.check_id == check_id:
            if best is None or sevs[it.status] > sevs[best]:
                best = it.status
    return best


class PHYSPF_PT_panel(Panel):
    bl_label = "Physics Preflight"
    bl_idname = "PHYSPF_PT_panel"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Physics Preflight"

    def draw(self, context):
        layout = self.layout
        wm = context.window_manager

        col = layout.column(align=True)
        col.scale_y = 1.3
        col.operator("physpf.scan", icon="VIEWZOOM")

        row = layout.row(align=True)
        row.operator("physpf.export_report", icon="TEXT")
        row.prop(wm, "physpf_show_passed", text="", icon="HIDE_OFF", toggle=True)

        if not wm.physpf_has_run:
            box = layout.box()
            box.label(text="Press Scan Scene to check this scene.", icon="INFO")
            box.label(text="Read-only. Nothing is changed.")
            return

        items = wm.physpf_results

        # summary line
        c = {Status.FAIL: 0, Status.WARNING: 0, Status.UNKNOWN: 0}
        for m in CHECKS:
            w = _worst_for_check(items, m.id)
            if w in c:
                c[w] += 1
        s = layout.row(align=True)
        s.label(text="%d" % c[Status.FAIL], icon="CANCEL")
        s.label(text="%d" % c[Status.WARNING], icon="ERROR")
        s.label(text="%d" % c[Status.UNKNOWN], icon="QUESTION")

        show_passed = wm.physpf_show_passed
        for group in (GROUP_SETUP, GROUP_CACHE):
            self._draw_group(layout, items, group, show_passed)

    def _draw_group(self, layout, items, group, show_passed):
        box = layout.box()
        box.label(text=group, icon="PHYSICS" if group == GROUP_SETUP else "FILE_CACHE")
        drew_any = False
        for m in [m for m in CHECKS if m.group == group]:
            worst = _worst_for_check(items, m.id)
            if worst is None:
                worst = Status.NA
            if not show_passed and worst in (Status.PASS, Status.NA):
                continue
            drew_any = True
            row = box.row()
            row.label(text="#%d %s" % (m.id, m.name),
                      icon=_STATUS_ICON.get(worst, "DOT"))
            # per-result detail
            for it in items:
                if it.check_id != m.id:
                    continue
                if not show_passed and it.status in (Status.PASS, Status.NA):
                    continue
                sub = box.column(align=True)
                line = sub.row()
                line.separator(factor=2.0)
                line.label(text=it.message, icon=_STATUS_ICON.get(it.status, "DOT"))
                if it.object_name:
                    op = sub.row()
                    op.separator(factor=2.0)
                    o = op.operator("physpf.select_object",
                                    text="Select '%s'" % it.object_name,
                                    icon="RESTRICT_SELECT_OFF")
                    o.object_name = it.object_name
                if it.hint:
                    h = sub.row()
                    h.separator(factor=2.0)
                    h.label(text=it.hint, icon="BLANK1")
        if not drew_any:
            box.label(text="No issues.", icon="CHECKMARK")


classes = (PHYSPF_PT_panel,)


def register():
    for c in classes:
        bpy.utils.register_class(c)


def unregister():
    for c in reversed(classes):
        bpy.utils.unregister_class(c)
