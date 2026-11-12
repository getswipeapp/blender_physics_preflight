import bpy, sys, os, tempfile
REPO = "/Users/ralph/Downloads/blender_physics_preflight"
sys.path.insert(0, REPO)
sys.path.insert(0, os.path.join(REPO, "tests"))
addon = "bl_ext.user_default.failsafe"

# Build the broken scene FIRST — fixtures may reset to factory settings (which
# disables user add-ons), so enable + configure AFTER building.
import fixtures
outdir = tempfile.mkdtemp(prefix="failsafe_bg_broken_")
fixtures.build_20_fail(outdir)   # real baked cache with a missing interior frame

bpy.ops.preferences.addon_enable(module=addon)
prefs = bpy.context.preferences.addons[addon].preferences
prefs.check_before_render = True
prefs.include_warnings = True
hooked = [getattr(h, "__name__", "") for h in bpy.app.handlers.render_init
          if getattr(h, "__name__", "") == "failsafe_render_init"]
print("HANDLER_HOOKED=%s" % hooked)

scn = bpy.context.scene
if scn.camera is None:
    cam_data = bpy.data.cameras.new("BGCam")
    cam = bpy.data.objects.new("BGCam", cam_data)
    scn.collection.objects.link(cam)
    cam.location = (0, -6, 2)
    scn.camera = cam
scn.render.resolution_x = 32
scn.render.resolution_y = 32
scn.render.resolution_percentage = 25
bpy.ops.render.render(write_still=False)
print("BG_BROKEN_DONE")
