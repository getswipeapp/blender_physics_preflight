# SPDX-License-Identifier: GPL-3.0-or-later
"""Operators: run a scan, jump to an affected object, export the report, and the
one user-initiated write action — Save Baseline."""
import os

import bpy
from bpy.props import StringProperty, CollectionProperty, BoolProperty, IntProperty
from bpy.types import Operator, PropertyGroup

from . import engine
from . import report as report_mod
from . import baseline as baseline_mod


class FAILSAFE_ResultItem(PropertyGroup):
    check_id: IntProperty()
    check_name: StringProperty()
    group: StringProperty()
    status: StringProperty()
    message: StringProperty()
    object_name: StringProperty()
    hint: StringProperty()


def _store_results(wm, results):
    coll = wm.failsafe_results
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
    wm.failsafe_has_run = True


class FAILSAFE_OT_scan(Operator):
    bl_idname = "failsafe.scan"
    bl_label = "Scan Scene"
    bl_description = ("Run all Failsafe checks on the current scene "
                      "(read-only)")
    bl_options = {"REGISTER"}

    def execute(self, context):
        results = engine.run_all(context)
        _store_results(context.window_manager, results)
        counts = engine.summary_counts(results)
        self.report(
            {"INFO"},
            "Failsafe: %d fail, %d warning, %d couldn't verify"
            % (counts[engine.Status.FAIL], counts[engine.Status.WARNING],
               counts[engine.Status.UNKNOWN]))
        return {"FINISHED"}


class FAILSAFE_OT_select_object(Operator):
    bl_idname = "failsafe.select_object"
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


class FAILSAFE_OT_show_physics(Operator):
    bl_idname = "failsafe.show_physics"
    bl_label = "Open Physics Settings"
    bl_description = ("Select this object and switch the Properties editor to the "
                      "tab where you fix it (nothing in the scene is changed)")
    bl_options = {"REGISTER", "UNDO"}

    object_name: StringProperty()
    # Properties-editor context to switch to: PHYSICS, OBJECT, DATA, SCENE…
    target: StringProperty(default="PHYSICS")

    def execute(self, context):
        # 1) Select + activate the object, if one was given (same careful,
        #    restore-on-failure logic as the Select button).
        if self.object_name:
            obj = context.scene.objects.get(self.object_name)
            if obj is not None:
                prev_selected = list(context.selected_objects)
                prev_active = context.view_layer.objects.active
                try:
                    for o in prev_selected:
                        o.select_set(False)
                    obj.select_set(True)
                    context.view_layer.objects.active = obj
                except Exception:
                    try:
                        for o in context.selected_objects:
                            o.select_set(False)
                        for o in prev_selected:
                            o.select_set(True)
                        context.view_layer.objects.active = prev_active
                    except Exception:
                        pass

        # 2) Switch ONE unpinned Properties editor to the right tab. This only
        #    changes which tab is shown — no scene data is touched. Pinned
        #    editors are left alone so we don't disturb a customised workspace.
        switched = False
        try:
            for area in context.screen.areas:
                if area.type != "PROPERTIES":
                    continue
                space = area.spaces.active
                if getattr(space, "use_pin_id", False):
                    continue      # respect a pinned Properties editor
                try:
                    space.context = self.target
                    area.tag_redraw()
                    switched = True
                    break         # switch only one
                except Exception:
                    pass
        except Exception:
            pass
        if not switched:
            # Be honest about what actually happened rather than implying both
            # the select and the navigation succeeded.
            if self.object_name:
                self.report({"INFO"},
                            "Selected '%s' — open its %s settings manually."
                            % (self.object_name, self.target.title()))
            else:
                self.report({"INFO"},
                            "Open an unpinned Properties editor to see the %s "
                            "settings." % self.target.title())
        return {"FINISHED"}


class FAILSAFE_OT_export_report(Operator):
    bl_idname = "failsafe.export_report"
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
        txt = bpy.data.texts.new("failsafe_report.txt")
        txt.write(text)
        try:
            context.window_manager.clipboard = text
        except Exception:
            pass
        self.report({"INFO"},
                    "Report written to new Text '%s' (inside the .blend) and "
                    "copied to the clipboard" % txt.name)
        return {"FINISHED"}


class FAILSAFE_OT_export_json(Operator):
    bl_idname = "failsafe.export_json"
    bl_label = "Export JSON Report"
    bl_description = ("Write a machine-readable JSON report to a Text datablock "
                      "inside this .blend and copy it to the clipboard (for "
                      "pipelines and render-farm tooling)")
    bl_options = {"REGISTER"}

    def execute(self, context):
        results = engine.run_all(context)
        _store_results(context.window_manager, results)
        text = report_mod.build_json_report(results)
        txt = bpy.data.texts.new("failsafe_report.json")
        txt.write(text)
        try:
            context.window_manager.clipboard = text
        except Exception:
            pass
        self.report({"INFO"},
                    "JSON report written to new Text '%s' (inside the .blend) "
                    "and copied to the clipboard" % txt.name)
        return {"FINISHED"}


class FAILSAFE_OT_save_baseline(Operator):
    bl_idname = "failsafe.save_baseline"
    bl_label = "Save Settings Baseline"
    bl_description = ("Record the current simulation settings to an external "
                      ".failsafe-baseline.json file next to your .blend, so later "
                      "scans can tell you whether the settings changed. This is "
                      "the ONLY action that writes a file, and it writes only "
                      "that sidecar — it never changes your .blend. Click it "
                      "right after you bake.")
    bl_options = {"REGISTER"}

    overwrite: BoolProperty(
        name="Overwrite the existing baseline",
        description="Replace the baseline already saved for this file",
        default=False,
    )

    def invoke(self, context, event):
        # Never silently replace an existing baseline: if one is already there and
        # the user hasn't opted in, pop a dialog asking before overwriting.
        path = baseline_mod.default_baseline_path()
        if path and os.path.isfile(path) and not self.overwrite:
            return context.window_manager.invoke_props_dialog(self)
        return self.execute(context)

    def draw(self, context):
        col = self.layout.column()
        col.label(text="A settings baseline already exists for this file.",
                  icon="ERROR")
        col.label(text="Saving again will replace it.")
        col.prop(self, "overwrite")

    def execute(self, context):
        path = baseline_mod.default_baseline_path()
        if not path:
            self.report({"ERROR"},
                        "Save your .blend first — the baseline is written next "
                        "to it.")
            return {"CANCELLED"}
        existed = os.path.isfile(path)
        if existed and not self.overwrite:
            # Reached execute without confirming (e.g. OK'd the dialog without
            # ticking Overwrite): do not replace it silently.
            self.report({"WARNING"},
                        "A baseline already exists. Tick 'Overwrite' to replace "
                        "it — nothing was written.")
            return {"CANCELLED"}
        try:
            baseline_mod.save_baseline(context.scene, path,
                                       overwrite=self.overwrite)
        except Exception as exc:
            self.report({"ERROR"}, "Couldn't write the baseline: %s" % exc)
            return {"CANCELLED"}
        # Reset the opt-in so the next click starts safe again.
        self.overwrite = False
        self.report(
            {"INFO"},
            "Settings baseline %s next to your .blend as '%s'. Your .blend was "
            "not modified." % ("updated" if existed else "saved",
                               os.path.basename(path)))
        return {"FINISHED"}


class FAILSAFE_OT_toggle_detail(Operator):
    bl_idname = "failsafe.toggle_detail"
    bl_label = "Toggle Finding Detail"
    bl_description = "Show or hide the full explanation for this check"
    bl_options = {"INTERNAL"}

    key: StringProperty()

    def execute(self, context):
        wm = context.window_manager
        collapsed = set(wm.failsafe_collapsed.split()) if wm.failsafe_collapsed else set()
        if self.key in collapsed:
            collapsed.discard(self.key)
        else:
            collapsed.add(self.key)
        wm.failsafe_collapsed = " ".join(sorted(collapsed))
        return {"FINISHED"}


class FAILSAFE_OT_set_filter(Operator):
    bl_idname = "failsafe.set_filter"
    bl_label = "Filter By Severity"
    bl_description = ("Show only this severity. Click again to show everything. "
                      "Handy when a scan turns up a lot of findings")
    bl_options = {"INTERNAL"}

    sev: StringProperty()

    def execute(self, context):
        wm = context.window_manager
        # Clicking the active filter again clears it (back to showing all).
        wm.failsafe_filter = "" if wm.failsafe_filter == self.sev else self.sev
        return {"FINISHED"}


classes = (
    FAILSAFE_ResultItem,
    FAILSAFE_OT_scan,
    FAILSAFE_OT_select_object,
    FAILSAFE_OT_show_physics,
    FAILSAFE_OT_export_report,
    FAILSAFE_OT_export_json,
    FAILSAFE_OT_save_baseline,
    FAILSAFE_OT_toggle_detail,
    FAILSAFE_OT_set_filter,
)


def register():
    for c in classes:
        bpy.utils.register_class(c)
    bpy.types.WindowManager.failsafe_results = CollectionProperty(type=FAILSAFE_ResultItem)
    bpy.types.WindowManager.failsafe_has_run = BoolProperty(default=False)
    bpy.types.WindowManager.failsafe_show_passed = BoolProperty(
        name="Show Passed", default=False,
        description="Also show checks that passed or do not apply")
    bpy.types.WindowManager.failsafe_explain = BoolProperty(
        name="Explain", default=False,
        description=("Show a plain-English 'why it matters' line under each "
                     "finding (for anyone new to Blender's physics)"))
    # space-separated list of check ids whose detail is collapsed. Empty by
    # default, so every finding starts EXPANDED (nothing hidden from the user).
    bpy.types.WindowManager.failsafe_collapsed = StringProperty(default="")
    # active severity filter: "" (all), "FAIL", "WARNING" or "UNKNOWN".
    bpy.types.WindowManager.failsafe_filter = StringProperty(default="")


def unregister():
    del bpy.types.WindowManager.failsafe_explain
    del bpy.types.WindowManager.failsafe_filter
    del bpy.types.WindowManager.failsafe_collapsed
    del bpy.types.WindowManager.failsafe_show_passed
    del bpy.types.WindowManager.failsafe_has_run
    del bpy.types.WindowManager.failsafe_results
    for c in reversed(classes):
        bpy.utils.unregister_class(c)
