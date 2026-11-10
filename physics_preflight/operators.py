# SPDX-License-Identifier: GPL-3.0-or-later
"""Operators: run a scan, jump to an affected object, export the report."""
import bpy
from bpy.props import StringProperty, CollectionProperty, BoolProperty, IntProperty
from bpy.types import Operator, PropertyGroup

from . import engine
from . import report as report_mod


class PHYSPF_ResultItem(PropertyGroup):
    check_id: IntProperty()
    check_name: StringProperty()
    group: StringProperty()
    status: StringProperty()
    message: StringProperty()
    object_name: StringProperty()
    hint: StringProperty()


def _store_results(wm, results):
    coll = wm.physpf_results
    coll.clear()
    for r in results:
        it = coll.add()
        it.check_id = r.check_id
        it.check_name = r.check_name
        it.group = r.group
        it.status = r.status
        it.message = r.message
        it.object_name = r.object_name or ""
        it.hint = r.hint or ""
    wm.physpf_has_run = True


class PHYSPF_OT_scan(Operator):
    bl_idname = "physpf.scan"
    bl_label = "Scan Scene"
    bl_description = ("Run all Physics Preflight checks on the current scene "
                      "(read-only)")
    bl_options = {"REGISTER"}

    def execute(self, context):
        results = engine.run_all(context)
        _store_results(context.window_manager, results)
        counts = engine.summary_counts(results)
        self.report(
            {"INFO"},
            "Physics Preflight: %d fail, %d warning, %d unknown"
            % (counts[engine.Status.FAIL], counts[engine.Status.WARNING],
               counts[engine.Status.UNKNOWN]))
        return {"FINISHED"}


class PHYSPF_OT_select_object(Operator):
    bl_idname = "physpf.select_object"
    bl_label = "Select Affected Object"
    bl_description = "Select this object and make it active in the viewport"
    bl_options = {"REGISTER", "UNDO"}

    object_name: StringProperty()

    def execute(self, context):
        obj = context.scene.objects.get(self.object_name)
        if obj is None:
            self.report({"WARNING"}, "Object '%s' not found" % self.object_name)
            return {"CANCELLED"}
        # Remember the current selection so a failure doesn't leave the user
        # with everything deselected.
        prev_selected = list(context.selected_objects)
        prev_active = context.view_layer.objects.active
        try:
            for o in prev_selected:
                o.select_set(False)
            obj.select_set(True)
            context.view_layer.objects.active = obj
        except Exception:
            # restore what we changed
            try:
                for o in context.selected_objects:
                    o.select_set(False)
                for o in prev_selected:
                    o.select_set(True)
                context.view_layer.objects.active = prev_active
            except Exception:
                pass
            self.report({"WARNING"}, "Could not select '%s'" % self.object_name)
            return {"CANCELLED"}
        return {"FINISHED"}


class PHYSPF_OT_export_report(Operator):
    bl_idname = "physpf.export_report"
    bl_label = "Export Text Report"
    bl_description = ("Write the report to a Text datablock inside this .blend "
                      "and copy it to the clipboard")
    bl_options = {"REGISTER"}

    def execute(self, context):
        results = engine.run_all(context)
        _store_results(context.window_manager, results)
        text = report_mod.build_text_report(results)
        # Always create a fresh, uniquely-named text block. Blender appends
        # .001/.002 if the base name is taken, so we never overwrite anything the
        # user has — including an earlier report they may have edited.
        txt = bpy.data.texts.new("physics_preflight_report.txt")
        txt.write(text)
        try:
            context.window_manager.clipboard = text
        except Exception:
            pass
        self.report({"INFO"},
                    "Report written to new Text '%s' (inside the .blend) and "
                    "copied to the clipboard" % txt.name)
        return {"FINISHED"}


class PHYSPF_OT_toggle_detail(Operator):
    bl_idname = "physpf.toggle_detail"
    bl_label = "Toggle Finding Detail"
    bl_description = "Show or hide the full explanation for this check"
    bl_options = {"INTERNAL"}

    key: StringProperty()

    def execute(self, context):
        wm = context.window_manager
        collapsed = set(wm.physpf_collapsed.split()) if wm.physpf_collapsed else set()
        if self.key in collapsed:
            collapsed.discard(self.key)
        else:
            collapsed.add(self.key)
        wm.physpf_collapsed = " ".join(sorted(collapsed))
        return {"FINISHED"}


classes = (
    PHYSPF_ResultItem,
    PHYSPF_OT_scan,
    PHYSPF_OT_select_object,
    PHYSPF_OT_export_report,
    PHYSPF_OT_toggle_detail,
)


def register():
    for c in classes:
        bpy.utils.register_class(c)
    bpy.types.WindowManager.physpf_results = CollectionProperty(type=PHYSPF_ResultItem)
    bpy.types.WindowManager.physpf_has_run = BoolProperty(default=False)
    bpy.types.WindowManager.physpf_show_passed = BoolProperty(
        name="Show Passed", default=False,
        description="Also show checks that passed or do not apply")
    # space-separated list of check ids whose detail is collapsed. Empty by
    # default, so every finding starts EXPANDED (nothing hidden from the user).
    bpy.types.WindowManager.physpf_collapsed = StringProperty(default="")


def unregister():
    del bpy.types.WindowManager.physpf_collapsed
    del bpy.types.WindowManager.physpf_show_passed
    del bpy.types.WindowManager.physpf_has_run
    del bpy.types.WindowManager.physpf_results
    for c in reversed(classes):
        bpy.utils.unregister_class(c)
