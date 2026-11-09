# SPDX-License-Identifier: GPL-3.0-or-later
"""Scene builders for the headless test harness.

Each builder leaves the scene in a state that should make ONE check produce a
known status. Builders that need real cache files take an output directory and
save/bake inside it.
"""
import os
import shutil
import bpy
import bmesh
from mathutils import Vector


def reset():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    return bpy.context.scene


def _add_cube(name, location=(0, 0, 0), size=2.0):
    bpy.ops.mesh.primitive_cube_add(size=size, location=location)
    o = bpy.context.active_object
    o.name = name
    return o


def add_rigid_body(obj, body_type="ACTIVE"):
    with bpy.context.temp_override(active_object=obj, object=obj,
                                   selected_objects=[obj]):
        bpy.ops.rigidbody.object_add()
    obj.rigid_body.type = body_type
    return obj.rigid_body


def _ensure_rbw_collection_has(obj):
    """Make sure obj is inside the Rigid Body World collection."""
    rbw = bpy.context.scene.rigidbody_world
    if rbw and rbw.collection and obj.name not in rbw.collection.objects:
        rbw.collection.objects.link(obj)


# ----------------------------------------------------------- setup builders --

def build_01_fail():
    reset()
    o = _add_cube("Box")
    o.scale = (2.0, 1.0, 1.0)
    add_rigid_body(o)


def build_01_pass():
    reset()
    o = _add_cube("Box")
    add_rigid_body(o)


def build_01_rotation_fail():
    # A cloth object with unapplied rotation — rotation matters for cloth.
    reset()
    bpy.ops.mesh.primitive_plane_add(size=2, location=(0, 0, 3))
    o = bpy.context.active_object
    o.name = "Cloth"
    o.rotation_euler = (0.7, 0.0, 0.0)
    o.modifiers.new("Cloth", "CLOTH")


def build_03_offstart_unknown():
    # Two separated bodies, but the timeline is NOT on the start frame, so the
    # start-frame overlap state can't be confirmed -> UNKNOWN (not a false PASS).
    reset()
    sc = bpy.context.scene
    sc.frame_start, sc.frame_end = 1, 50
    sc.frame_current = 25
    a = _add_cube("A", location=(0, 0, 0), size=2.0)
    b = _add_cube("B", location=(5, 0, 0), size=2.0)
    add_rigid_body(a)
    add_rigid_body(b)


def build_16_effector_only_fail():
    # A domain whose only fluid object is an EFFECTOR (not a flow source).
    reset()
    dom = _add_cube("Domain", size=4.0)
    m = dom.modifiers.new("Fluid", "FLUID")
    m.fluid_type = "DOMAIN"
    m.domain_settings.domain_type = "LIQUID"
    bpy.ops.mesh.primitive_uv_sphere_add(radius=0.3, location=(0, 0, 0))
    eff = bpy.context.active_object
    eff.name = "Effector"
    f = eff.modifiers.new("Fluid", "FLUID")
    f.fluid_type = "EFFECTOR"


def build_02_fail():
    reset()
    o = _add_cube("Pebble", size=0.1)
    rb = add_rigid_body(o)
    rb.mass = 5000.0  # a 10cm pebble weighing 5 tonnes


def build_02_pass():
    reset()
    o = _add_cube("Crate", size=1.0)
    rb = add_rigid_body(o)
    rb.mass = 50.0


def build_03_fail():
    reset()
    a = _add_cube("A", location=(0, 0, 0), size=2.0)
    b = _add_cube("B", location=(0.5, 0, 0), size=2.0)  # overlapping
    add_rigid_body(a)
    add_rigid_body(b)


def build_03_containment_fail():
    reset()
    big = _add_cube("Big", size=4.0)
    bpy.ops.mesh.primitive_uv_sphere_add(radius=0.3, location=(0, 0, 0))
    small = bpy.context.active_object
    small.name = "Inner"
    add_rigid_body(big)
    add_rigid_body(small)


def build_03_pass():
    reset()
    a = _add_cube("A", location=(0, 0, 0), size=2.0)
    b = _add_cube("B", location=(5, 0, 0), size=2.0)
    add_rigid_body(a)
    add_rigid_body(b)


def build_04_fail():
    reset()
    bpy.ops.mesh.primitive_torus_add(location=(0, 0, 0))
    o = bpy.context.active_object
    o.name = "Torus"
    rb = add_rigid_body(o, "PASSIVE")
    rb.collision_shape = "CONVEX_HULL"


def build_04_pass():
    reset()
    o = _add_cube("Box")
    rb = add_rigid_body(o)
    rb.collision_shape = "CONVEX_HULL"


def build_05_fail():
    reset()
    # build a mesh with an edge shared by three faces (bad topology)
    me = bpy.data.meshes.new("Bad")
    bm = bmesh.new()
    v0 = bm.verts.new((0, 0, 0))
    v1 = bm.verts.new((0, 1, 0))
    v2 = bm.verts.new((1, 0, 0))
    v3 = bm.verts.new((-1, 0, 0))
    v4 = bm.verts.new((0, 0, 1))
    bm.faces.new((v0, v1, v2))
    bm.faces.new((v0, v1, v3))
    bm.faces.new((v0, v1, v4))
    bm.to_mesh(me)
    bm.free()
    o = bpy.data.objects.new("BadCollider", me)
    bpy.context.scene.collection.objects.link(o)
    o.modifiers.new("Collision", "COLLISION")


def build_05_pass():
    reset()
    bpy.ops.mesh.primitive_plane_add(size=10)
    o = bpy.context.active_object
    o.name = "Floor"
    o.modifiers.new("Collision", "COLLISION")  # a plane floor is fine


def build_06_fail():
    reset()
    o = _add_cube("Box")
    add_rigid_body(o)
    bpy.context.scene.rigidbody_world.enabled = False


def build_06_pass():
    reset()
    o = _add_cube("Box")
    add_rigid_body(o)
    _ensure_rbw_collection_has(o)
    bpy.context.scene.rigidbody_world.substeps_per_frame = 10
    bpy.context.scene.rigidbody_world.solver_iterations = 10


def build_07_fail():
    reset()
    bpy.ops.mesh.primitive_plane_add(size=2, location=(0, 0, 3))
    o = bpy.context.active_object
    o.name = "Cloth"
    m = o.modifiers.new("Cloth", "CLOTH")
    m.collision_settings.use_collision = False


def build_07_pass():
    reset()
    bpy.ops.mesh.primitive_plane_add(size=2, location=(0, 0, 3))
    cloth = bpy.context.active_object
    cloth.name = "Cloth"
    cloth.modifiers.new("Cloth", "CLOTH")
    bpy.ops.mesh.primitive_plane_add(size=10)
    floor = bpy.context.active_object
    floor.modifiers.new("Collision", "COLLISION")


def build_08_fail():
    reset()
    o = _add_cube("Box")
    o.scale = (-1.0, 1.0, 1.0)  # determinant < 0
    add_rigid_body(o)


def build_08_pass():
    reset()
    o = _add_cube("Box")
    add_rigid_body(o)


def build_09_fail():
    reset()
    o = _add_cube("Speck", size=0.0005)  # 0.5 mm
    add_rigid_body(o)


def build_09_pass():
    reset()
    o = _add_cube("Box", size=1.0)
    add_rigid_body(o)


def build_10_fail():
    reset()
    o = _add_cube("Box", size=1.0)
    # move geometry away from the origin, in edit mode
    me = o.data
    for v in me.vertices:
        v.co += Vector((10.0, 0.0, 0.0))
    add_rigid_body(o)


def build_10_pass():
    reset()
    o = _add_cube("Box")
    add_rigid_body(o)


def build_11_fail():
    reset()
    o = _add_cube("Box", size=0.2)
    rb = add_rigid_body(o)
    rb.use_margin = True
    rb.collision_margin = 0.2


def build_11_pass():
    reset()
    o = _add_cube("Box", size=2.0)
    rb = add_rigid_body(o)
    rb.collision_margin = 0.04


def build_12_fail():
    reset()
    o = _add_cube("Mover")
    rb = add_rigid_body(o, "PASSIVE")
    rb.kinematic = False
    o.location = (0, 0, 0)
    o.keyframe_insert("location", frame=1)
    o.location = (5, 0, 0)
    o.keyframe_insert("location", frame=20)


def build_12_pass():
    reset()
    o = _add_cube("Mover")
    rb = add_rigid_body(o, "PASSIVE")
    rb.kinematic = True
    o.location = (0, 0, 0)
    o.keyframe_insert("location", frame=1)
    o.location = (5, 0, 0)
    o.keyframe_insert("location", frame=20)


def build_13_fail():
    reset()
    a = _add_cube("A")
    add_rigid_body(a)
    bpy.ops.object.empty_add(location=(0, 0, 0))
    e = bpy.context.active_object
    e.name = "Constraint"
    with bpy.context.temp_override(active_object=e, object=e, selected_objects=[e]):
        bpy.ops.rigidbody.constraint_add()
    e.rigid_body_constraint.object1 = a
    e.rigid_body_constraint.object2 = None  # broken


def build_13_pass():
    reset()
    a = _add_cube("A", location=(-1, 0, 0))
    b = _add_cube("B", location=(1, 0, 0))
    add_rigid_body(a)
    add_rigid_body(b)
    bpy.ops.object.empty_add(location=(0, 0, 0))
    e = bpy.context.active_object
    with bpy.context.temp_override(active_object=e, object=e, selected_objects=[e]):
        bpy.ops.rigidbody.constraint_add()
    e.rigid_body_constraint.object1 = a
    e.rigid_body_constraint.object2 = b


def build_14_fail():
    reset()
    bpy.ops.mesh.primitive_plane_add(size=10)
    o = bpy.context.active_object
    o.name = "Floor"
    o.modifiers.new("Collision", "COLLISION")
    o.modifiers.new("Subdivision", "SUBSURF")  # deform AFTER collision


def build_14_pass():
    reset()
    bpy.ops.mesh.primitive_plane_add(size=10)
    o = bpy.context.active_object
    o.name = "Floor"
    o.modifiers.new("Subdivision", "SUBSURF")
    o.modifiers.new("Collision", "COLLISION")  # collision at the bottom


def build_15_fail():
    reset()
    bpy.ops.mesh.primitive_plane_add(size=2, location=(0, 0, 3))
    o = bpy.context.active_object
    o.name = "Flag"
    # A pin group that exists but has no weighted vertices — a classic beginner
    # mistake (created the group, forgot to assign weights). Blender clears
    # vertex_group_mass if set to a name that doesn't exist, so the empty-group
    # case is the testable one.
    o.vertex_groups.new(name="Pin")
    m = o.modifiers.new("Cloth", "CLOTH")
    m.settings.vertex_group_mass = "Pin"


def build_15_pass():
    reset()
    bpy.ops.mesh.primitive_plane_add(size=2, location=(0, 0, 3))
    o = bpy.context.active_object
    o.name = "Flag"
    vg = o.vertex_groups.new(name="Pin")
    vg.add([0, 1], 1.0, "REPLACE")
    m = o.modifiers.new("Cloth", "CLOTH")
    m.settings.vertex_group_mass = "Pin"


def build_16_fail():
    reset()
    o = _add_cube("Domain", size=4.0)
    m = o.modifiers.new("Fluid", "FLUID")
    m.fluid_type = "DOMAIN"
    m.domain_settings.domain_type = "GAS"
    # no flow object


def build_16_pass():
    reset()
    dom = _add_cube("Domain", size=4.0)
    m = dom.modifiers.new("Fluid", "FLUID")
    m.fluid_type = "DOMAIN"
    m.domain_settings.domain_type = "GAS"
    bpy.ops.mesh.primitive_uv_sphere_add(radius=0.3, location=(0, 0, 0))
    fl = bpy.context.active_object
    fl.name = "Inflow"
    f = fl.modifiers.new("Fluid", "FLUID")
    f.fluid_type = "FLOW"
    f.flow_settings.flow_type = "SMOKE"


# ----------------------------------------------------------- cache builders --

def _bake_point_cache(pc, obj):
    with bpy.context.temp_override(point_cache=pc, scene=bpy.context.scene,
                                   active_object=obj, object=obj):
        bpy.ops.ptcache.bake(bake=True)


def _make_cloth_blend(outdir, frame_end_cache=10, scene_end=10):
    """Create, save and disk-bake a cloth sim. Returns the blend path."""
    reset()
    sc = bpy.context.scene
    sc.frame_start, sc.frame_end = 1, scene_end
    bpy.ops.mesh.primitive_plane_add(size=2, location=(0, 0, 3))
    o = bpy.context.active_object
    o.name = "Cloth"
    m = o.modifiers.new("Cloth", "CLOTH")
    pc = m.point_cache
    pc.frame_start, pc.frame_end = 1, frame_end_cache
    blend = os.path.join(outdir, "cloth.blend")
    bpy.ops.wm.save_as_mainfile(filepath=blend)
    pc.use_disk_cache = True
    _bake_point_cache(pc, o)
    bpy.ops.wm.save_mainfile()
    return blend


def build_17_fail():
    reset()
    bpy.ops.mesh.primitive_plane_add(size=2, location=(0, 0, 3))
    o = bpy.context.active_object
    o.name = "Cloth"
    o.modifiers.new("Cloth", "CLOTH")  # not baked


def build_18_pass(outdir):
    _make_cloth_blend(outdir)


def build_18_fail(outdir):
    """The headline test: bake to disk, delete the files, reopen. Blender still
    says baked; #18 must FAIL."""
    blend = _make_cloth_blend(outdir)
    cachedir = os.path.join(outdir, "blendcache_cloth")
    shutil.rmtree(cachedir, ignore_errors=True)
    bpy.ops.wm.open_mainfile(filepath=blend)


def build_19_fail(outdir):
    _make_cloth_blend(outdir, frame_end_cache=5, scene_end=20)


def build_20_fail(outdir):
    blend = _make_cloth_blend(outdir, frame_end_cache=10, scene_end=10)
    # delete a single interior frame file
    cachedir = os.path.join(outdir, "blendcache_cloth")
    prefix = "".join("%02X" % b for b in "Cloth".encode())
    target = os.path.join(cachedir, "%s_%06d_%02d.bphys" % (prefix, 5, 0))
    if os.path.isfile(target):
        os.remove(target)
    bpy.ops.wm.open_mainfile(filepath=blend)


def _delete_cloth_frame(outdir, frame):
    cachedir = os.path.join(outdir, "blendcache_cloth")
    prefix = "".join("%02X" % b for b in "Cloth".encode())
    target = os.path.join(cachedir, "%s_%06d_%02d.bphys" % (prefix, frame, 0))
    existed = os.path.isfile(target)
    if existed:
        os.remove(target)
    return existed


def build_F01_missing_tail(outdir):
    """Regression for F01: delete the LAST baked frame, reopen. Blender still
    reports the sim as baked. #17, #18 and #20 must all FAIL (the old code let
    all four cache checks PASS because #20 only looked between the first and
    last file that still existed)."""
    blend = _make_cloth_blend(outdir, frame_end_cache=10, scene_end=10)
    assert _delete_cloth_frame(outdir, 10), "expected frame 10 cache file"
    bpy.ops.wm.open_mainfile(filepath=blend)


def build_F01_missing_head(outdir):
    """Regression for F01: delete the FIRST baked frame, reopen."""
    blend = _make_cloth_blend(outdir, frame_end_cache=10, scene_end=10)
    assert _delete_cloth_frame(outdir, 1), "expected frame 1 cache file"
    bpy.ops.wm.open_mainfile(filepath=blend)


def build_F01_missing_multi_tail(outdir):
    """Delete the last three baked frames, reopen."""
    blend = _make_cloth_blend(outdir, frame_end_cache=10, scene_end=10)
    for fr in (8, 9, 10):
        _delete_cloth_frame(outdir, fr)
    bpy.ops.wm.open_mainfile(filepath=blend)


def build_22_fail(outdir):
    reset()
    sc = bpy.context.scene
    sc.frame_start, sc.frame_end = 1, 4
    o = _add_cube("Domain", size=4.0)
    m = o.modifiers.new("Fluid", "FLUID")
    m.fluid_type = "DOMAIN"
    m.domain_settings.domain_type = "GAS"
    m.domain_settings.cache_directory = "/tmp/physpf_abs_cache_outside"
    blend = os.path.join(outdir, "fluid_abs.blend")
    bpy.ops.wm.save_as_mainfile(filepath=blend)


def build_21_fail(outdir):
    reset()
    a = _add_cube("DomainA", location=(-5, 0, 0), size=4.0)
    ma = a.modifiers.new("Fluid", "FLUID")
    ma.fluid_type = "DOMAIN"
    ma.domain_settings.cache_directory = "//shared_cache"
    b = _add_cube("DomainB", location=(5, 0, 0), size=4.0)
    mb = b.modifiers.new("Fluid", "FLUID")
    mb.fluid_type = "DOMAIN"
    mb.domain_settings.cache_directory = "//shared_cache"
    blend = os.path.join(outdir, "shared.blend")
    bpy.ops.wm.save_as_mainfile(filepath=blend)


def build_23_fail(outdir):
    blend = _make_cloth_blend(outdir)
    bpy.context.scene.rigidbody_world  # none; use cloth baked + change fps
    bpy.context.scene.render.fps = 60
