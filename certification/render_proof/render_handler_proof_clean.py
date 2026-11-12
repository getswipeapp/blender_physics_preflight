import bpy
addon = "bl_ext.user_default.failsafe"
try:
    bpy.ops.preferences.addon_enable(module=addon)
except Exception as e:
    print("enable note:", e)
prefs = bpy.context.preferences.addons[addon].preferences
prefs.check_before_render = True
prefs.include_warnings = True
# Confirm the handler is actually hooked in this background session.
hooked = [getattr(h, "__name__", "") for h in bpy.app.handlers.render_init
          if getattr(h, "__name__", "") == "failsafe_render_init"]
print("HANDLER_HOOKED=%s" % hooked)
scn = bpy.context.scene
scn.render.resolution_x = 32
scn.render.resolution_y = 32
scn.render.resolution_percentage = 25
# default scene has a camera; render a single still, no file written
bpy.ops.render.render(write_still=False)
print("BG_RENDER_DONE")
