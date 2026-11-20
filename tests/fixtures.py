# SPDX-License-Identifier: GPL-3.0-or-later
"""Scene builders for the headless test harness.

Each builder leaves the scene in a state that should make ONE check produce a
known status. Builders that need real cache files take an output directory and
save/bake inside it.
"""
import os
import shutil
import struct
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


# ---- heavy-sim integration fixtures (real bakes) ---------------------------

def _delete_point_frame(cachedir, which="last"):
    """Delete the first/last .bphys frame file in a blendcache dir, whatever the
    prefix. Returns the frame deleted, or None."""
    if not os.path.isdir(cachedir):
        return None
    files = [f for f in os.listdir(cachedir) if f.endswith(".bphys")]
    if not files:
        return None

    def frame_of(f):
        try:
            return int(f.rsplit("_", 2)[1])
        except Exception:
            return -1
    files.sort(key=frame_of)
    target = files[0] if which == "first" else files[-1]
    os.remove(os.path.join(cachedir, target))
    return frame_of(target)


def _make_softbody_blend(outdir, frame_end=8):
    reset()
    sc = bpy.context.scene
    sc.frame_start, sc.frame_end = 1, frame_end
    bpy.ops.mesh.primitive_ico_sphere_add(location=(0, 0, 3))
    o = bpy.context.active_object
    o.name = "Soft"
    m = o.modifiers.new("Softbody", "SOFT_BODY")
    pc = m.point_cache
    pc.frame_start, pc.frame_end = 1, frame_end
    blend = os.path.join(outdir, "soft.blend")
    bpy.ops.wm.save_as_mainfile(filepath=blend)
    pc.use_disk_cache = True
    _bake_point_cache(pc, o)
    bpy.ops.wm.save_mainfile()
    return blend


def build_softbody_pass(outdir):
    _make_softbody_blend(outdir)


def build_softbody_missing_tail(outdir):
    blend = _make_softbody_blend(outdir)
    _delete_point_frame(os.path.join(outdir, "blendcache_soft"), "last")
    bpy.ops.wm.open_mainfile(filepath=blend)


def _make_particle_blend(outdir, frame_end=8):
    reset()
    sc = bpy.context.scene
    sc.frame_start, sc.frame_end = 1, frame_end
    bpy.ops.mesh.primitive_plane_add(size=4)
    o = bpy.context.active_object
    o.name = "Emitter"
    with bpy.context.temp_override(active_object=o, object=o, selected_objects=[o]):
        bpy.ops.object.particle_system_add()
    psys = o.particle_systems[0]
    pset = psys.settings
    pset.count = 50
    pset.frame_start, pset.frame_end = 1, max(2, frame_end // 2)
    pset.lifetime = frame_end
    pc = psys.point_cache
    pc.frame_start, pc.frame_end = 1, frame_end
    blend = os.path.join(outdir, "parts.blend")
    bpy.ops.wm.save_as_mainfile(filepath=blend)
    pc.use_disk_cache = True
    with bpy.context.temp_override(point_cache=pc, scene=sc, active_object=o, object=o):
        bpy.ops.ptcache.bake(bake=True)
    bpy.ops.wm.save_mainfile()
    return blend


def build_particle_pass(outdir):
    _make_particle_blend(outdir)


def build_particle_missing_tail(outdir):
    blend = _make_particle_blend(outdir)
    _delete_point_frame(os.path.join(outdir, "blendcache_parts"), "last")
    bpy.ops.wm.open_mainfile(filepath=blend)


def _make_hair_blend(outdir, frame_end=6):
    """Create, save and disk-bake a hair-dynamics sim (the particle point cache
    written when ``use_hair_dynamics`` is on). Returns the blend path."""
    reset()
    sc = bpy.context.scene
    sc.frame_start, sc.frame_end = 1, frame_end
    bpy.ops.mesh.primitive_plane_add(size=4)
    o = bpy.context.active_object
    o.name = "HairObj"
    with bpy.context.temp_override(active_object=o, object=o, selected_objects=[o]):
        bpy.ops.object.particle_system_add()
    psys = o.particle_systems[0]
    psys.settings.type = 'HAIR'
    psys.settings.count = 20
    psys.use_hair_dynamics = True
    pc = psys.point_cache
    pc.frame_start, pc.frame_end = 1, frame_end
    blend = os.path.join(outdir, "hair.blend")
    bpy.ops.wm.save_as_mainfile(filepath=blend)
    pc.use_disk_cache = True
    with bpy.context.temp_override(point_cache=pc, scene=sc, active_object=o, object=o):
        bpy.ops.ptcache.bake(bake=True)
    bpy.ops.wm.save_mainfile()
    return blend


def build_hair_pass(outdir):
    _make_hair_blend(outdir)


def build_hair_missing_tail(outdir):
    blend = _make_hair_blend(outdir)
    _delete_point_frame(os.path.join(outdir, "blendcache_hair"), "last")
    bpy.ops.wm.open_mainfile(filepath=blend)


def _make_dpaint_blend(outdir, frame_end=6):
    """Create, save and disk-bake a Dynamic Paint *vertex* canvas surface (which
    uses a standard .bphys point cache). Returns the blend path."""
    reset()
    sc = bpy.context.scene
    sc.frame_start, sc.frame_end = 1, frame_end
    bpy.ops.mesh.primitive_grid_add(size=4)
    o = bpy.context.active_object
    o.name = "DPCanvas"
    m = o.modifiers.new("DP", type='DYNAMIC_PAINT')
    with bpy.context.temp_override(active_object=o, object=o, selected_objects=[o]):
        bpy.ops.dpaint.type_toggle(type='CANVAS')
    surf = m.canvas_settings.canvas_surfaces[0]
    surf.surface_format = 'VERTEX'
    pc = surf.point_cache
    pc.frame_start, pc.frame_end = 1, frame_end
    blend = os.path.join(outdir, "dpaint.blend")
    bpy.ops.wm.save_as_mainfile(filepath=blend)
    pc.use_disk_cache = True
    with bpy.context.temp_override(point_cache=pc, scene=sc, active_object=o, object=o):
        bpy.ops.ptcache.bake(bake=True)
    bpy.ops.wm.save_mainfile()
    return blend


def build_dpaint_pass(outdir):
    _make_dpaint_blend(outdir)


def build_dpaint_missing_tail(outdir):
    blend = _make_dpaint_blend(outdir)
    _delete_point_frame(os.path.join(outdir, "blendcache_dpaint"), "last")
    bpy.ops.wm.open_mainfile(filepath=blend)


def _corrupt_point_frame(cachedir, mode):
    """Overwrite a middle .bphys frame with content that is non-empty and
    readable but not valid point-cache data. Modes:
      'garbage'    bytes with no BPHYSICS magic.
      'truncated'  magic present, but fewer than the 20 header bytes.
      'zerofields' the exact 'BPHYSICS' + 12 zero bytes fabricated file (valid
                   magic, full 20-byte length, but totpoint=0 and data_types=0).
      'headeronly' the real frame's valid 20-byte header with the payload
                   stripped (valid magic + fields, but no per-point data).
    Returns the file touched."""
    files = sorted(f for f in os.listdir(cachedir) if f.endswith(".bphys"))
    target = os.path.join(cachedir, files[len(files) // 2])
    if mode == "garbage":
        with open(target, "wb") as fh:
            fh.write(b"this is not a point-cache file, but it is not empty\n")
    elif mode == "truncated":
        with open(target, "wb") as fh:
            fh.write(b"BPHYSICS\x02\x00\x00\x00")  # 12 bytes: partial header
    elif mode == "zerofields":
        with open(target, "wb") as fh:
            fh.write(b"BPHYSICS" + b"\x00" * 12)  # 20 bytes, totpoint/data_types=0
    elif mode == "wrongtype":
        # Keep a fully valid structure but overwrite the type word (offset 8)
        # with a DIFFERENT valid sim type (particle=1 on a cloth cache=2), so the
        # frame declares it belongs to another simulation.
        with open(target, "rb") as fh:
            data = bytearray(fh.read())
        struct.pack_into("<I", data, 8, 1)  # low16 = 1 (particle) != cloth (2)
        with open(target, "wb") as fh:
            fh.write(data)
    else:  # headeronly: keep the real 20-byte header, drop the payload
        with open(target, "rb") as fh:
            header = fh.read(20)
        with open(target, "wb") as fh:
            fh.write(header)
    return os.path.basename(target)


def build_bphys_badmagic(outdir):
    """Bake a cloth cache, then replace a frame with non-cache garbage. Blender
    still reports the sim as baked; #17/#18 must FAIL (corrupt), not pass."""
    blend = _make_cloth_blend(outdir, frame_end_cache=6, scene_end=6)
    _corrupt_point_frame(os.path.join(outdir, "blendcache_cloth"), "garbage")
    bpy.ops.wm.open_mainfile(filepath=blend)


def build_bphys_truncated_header(outdir):
    """Bake a cloth cache, then truncate a frame to a partial header."""
    blend = _make_cloth_blend(outdir, frame_end_cache=6, scene_end=6)
    _corrupt_point_frame(os.path.join(outdir, "blendcache_cloth"), "truncated")
    bpy.ops.wm.open_mainfile(filepath=blend)


def build_bphys_zerofields(outdir):
    """The B1 example: a frame of 'BPHYSICS' + 12 zero bytes — valid magic, full
    20-byte length, but zero point count and data-type mask. Must FAIL, never a
    clean PASS."""
    blend = _make_cloth_blend(outdir, frame_end_cache=6, scene_end=6)
    _corrupt_point_frame(os.path.join(outdir, "blendcache_cloth"), "zerofields")
    bpy.ops.wm.open_mainfile(filepath=blend)


def build_bphys_header_only(outdir):
    """A frame with the real, valid 20-byte header but no payload at all."""
    blend = _make_cloth_blend(outdir, frame_end_cache=6, scene_end=6)
    _corrupt_point_frame(os.path.join(outdir, "blendcache_cloth"), "headeronly")
    bpy.ops.wm.open_mainfile(filepath=blend)


def build_bphys_wrongtype(outdir):
    """A structurally-valid frame whose type word says particle (1) on a cloth
    cache (2) — not this simulation's cache file. Must FAIL (M1)."""
    blend = _make_cloth_blend(outdir, frame_end_cache=6, scene_end=6)
    _corrupt_point_frame(os.path.join(outdir, "blendcache_cloth"), "wrongtype")
    bpy.ops.wm.open_mainfile(filepath=blend)


def prefix_of(name):
    """The uppercase-hex cache filename prefix Blender uses for an object/cache
    name (matches cache_inspect._hex_name)."""
    return "".join("%02X" % b for b in name.encode())


def _make_two_sim_blend(outdir, frame_end=6):
    """Create, save and disk-bake TWO sims in one scene (a cloth plane and a soft-
    body cube) so the cache-hash tests can prove the baseline keys each sim
    independently. Both write into the single ``blendcache_twosim`` folder, told
    apart by their filename prefix. Returns the blend path."""
    reset()
    sc = bpy.context.scene
    sc.frame_start, sc.frame_end = 1, frame_end
    bpy.ops.mesh.primitive_plane_add(size=2, location=(0, 0, 3))
    o1 = bpy.context.active_object
    o1.name = "ClothP"
    m1 = o1.modifiers.new("Cloth", "CLOTH")
    pc1 = m1.point_cache
    pc1.frame_start, pc1.frame_end = 1, frame_end
    bpy.ops.mesh.primitive_cube_add(size=1, location=(3, 0, 3))
    o2 = bpy.context.active_object
    o2.name = "SoftC"
    m2 = o2.modifiers.new("Soft", "SOFT_BODY")
    pc2 = m2.point_cache
    pc2.frame_start, pc2.frame_end = 1, frame_end
    blend = os.path.join(outdir, "twosim.blend")
    bpy.ops.wm.save_as_mainfile(filepath=blend)
    pc1.use_disk_cache = True
    pc2.use_disk_cache = True
    _bake_point_cache(pc1, o1)
    _bake_point_cache(pc2, o2)
    bpy.ops.wm.save_mainfile()
    return blend


def _make_fluid_blend(outdir, frame_end=4, use_mesh=True):
    reset()
    sc = bpy.context.scene
    sc.frame_start, sc.frame_end = 1, frame_end
    bpy.ops.mesh.primitive_cube_add(size=4, location=(0, 0, 0))
    dom = bpy.context.active_object
    dom.name = "Domain"
    m = dom.modifiers.new("Fluid", "FLUID")
    m.fluid_type = "DOMAIN"
    ds = m.domain_settings
    ds.domain_type = "LIQUID"
    ds.resolution_max = 16
    ds.use_mesh = use_mesh
    ds.cache_type = "ALL"
    ds.cache_frame_start, ds.cache_frame_end = 1, frame_end
    ds.cache_directory = "//fluidcache"
    bpy.ops.mesh.primitive_uv_sphere_add(radius=0.7, location=(0, 0, 1.2))
    fl = bpy.context.active_object
    fl.name = "Inflow"
    f = fl.modifiers.new("Fluid", "FLUID")
    f.fluid_type = "FLOW"
    f.flow_settings.flow_type = "LIQUID"
    f.flow_settings.flow_behavior = "GEOMETRY"
    blend = os.path.join(outdir, "fluid.blend")
    bpy.ops.wm.save_as_mainfile(filepath=blend)
    with bpy.context.temp_override(scene=sc, active_object=dom, object=dom,
                                   selected_objects=[dom]):
        bpy.ops.fluid.bake_all()
    bpy.ops.wm.save_mainfile()
    return blend


def build_fluid_pass(outdir):
    blend = _make_fluid_blend(outdir)
    bpy.ops.wm.open_mainfile(filepath=blend)


def build_fluid_missing_data_frame(outdir):
    blend = _make_fluid_blend(outdir)
    data = os.path.join(outdir, "fluidcache", "data")
    files = sorted(f for f in os.listdir(data) if f.endswith(".vdb"))
    assert files, "expected baked fluid data files"
    os.remove(os.path.join(data, files[-1]))  # delete last data frame
    bpy.ops.wm.open_mainfile(filepath=blend)


def build_fluid_missing_mesh_frame(outdir):
    blend = _make_fluid_blend(outdir, use_mesh=True)
    mesh = os.path.join(outdir, "fluidcache", "mesh")
    files = sorted(f for f in os.listdir(mesh))
    assert files, "expected baked fluid mesh files"
    os.remove(os.path.join(mesh, files[-1]))  # delete a required mesh frame
    bpy.ops.wm.open_mainfile(filepath=blend)


def _make_gn_disk_blend(outdir, frame_end=6, packed=False, scene_sim_range=None,
                        custom_bake_dir=None):
    """Create a Geometry Nodes simulation-zone bake with a REAL moving simulation,
    stored on DISK, so the GN cache-hash tests run on a genuine bake that writes
    both ``meta/*.json`` AND ``blobs/*.blob`` (the heavy attribute data).

    The zone feeds its previous state through a Set Position offset, so each baked
    frame carries real, changing geometry — which is what makes Blender spill the
    attribute arrays to blob files (a trivial passthrough stored nothing and wrote
    no blobs). The grid is dense enough that the position array is always a blob.

    Returns ``(blend_path, disk_available, packed_made)``:
      * ``disk_available`` — a real disk bake was written (True on ALL four versions:
        GN sim bakes go to disk on 4.5/5.0/5.2 via ``bake_target='DISK'`` and on 4.2
        via ``bake_directory`` alone, since 4.2 has no ``bake_target`` and no packed
        storage).
      * ``packed_made`` — a PACKED bake was actually produced (only possible where
        ``bake_target`` exists, i.e. 4.3+). ``packed=True`` on 4.2 can't pack, so it
        falls back to a disk bake and ``packed_made`` is False (the caller skips the
        packed-only assertion there)."""
    reset()
    sc = bpy.context.scene
    sc.frame_start, sc.frame_end = 1, frame_end
    bpy.ops.mesh.primitive_grid_add(x_subdivisions=24, y_subdivisions=24, size=4)
    ob = bpy.context.active_object
    ob.name = "GNObj"
    mod = ob.modifiers.new("GeoNodes", "NODES")
    ng = bpy.data.node_groups.new("SimTree", "GeometryNodeTree")
    mod.node_group = ng
    ng.interface.new_socket("Geometry", in_out="INPUT",
                            socket_type="NodeSocketGeometry")
    ng.interface.new_socket("Geometry", in_out="OUTPUT",
                            socket_type="NodeSocketGeometry")
    n = ng.nodes
    gi = n.new("NodeGroupInput")
    go = n.new("NodeGroupOutput")
    si = n.new("GeometryNodeSimulationInput")
    so = n.new("GeometryNodeSimulationOutput")
    si.pair_with_output(so)

    def _geo_in(node):
        for i, s in enumerate(node.inputs):
            if s.type == "GEOMETRY":
                return i
        return 0

    def _geo_out(node):
        for i, s in enumerate(node.outputs):
            if s.type == "GEOMETRY":
                return i
        return 0

    setp = n.new("GeometryNodeSetPosition")
    off = n.new("ShaderNodeCombineXYZ")
    try:
        off.inputs[2].default_value = 0.05
    except Exception:
        pass
    L = ng.links.new
    L(gi.outputs[0], si.inputs[_geo_in(si)])          # initial geometry
    L(si.outputs[_geo_out(si)], setp.inputs[0])       # previous state -> Set Position
    L(off.outputs[0], setp.inputs[3])                 # Offset (+Z each step)
    L(setp.outputs[0], so.inputs[_geo_in(so)])        # store new state
    L(so.outputs[_geo_out(so)], go.inputs[0])

    # A scene-wide custom simulation range OVERRIDES the scene frame range for sim
    # zones (verified on real bakes) — used to prove #27 honours it (review B4a).
    if scene_sim_range is not None and hasattr(sc, "use_custom_simulation_range"):
        sc.use_custom_simulation_range = True
        sc.simulation_frame_start, sc.simulation_frame_end = scene_sim_range
    blend = os.path.join(outdir, "gn.blend")
    bpy.ops.wm.save_as_mainfile(filepath=blend)
    has_bt = hasattr(mod, "bake_target")
    packed_made = bool(packed and has_bt)
    if has_bt:
        mod.bake_target = "PACKED" if packed_made else "DISK"
    if not packed_made:
        mod.bake_directory = "//gnbake"   # disk location (honoured on 4.2 too)
    # A per-bake CUSTOM path stores files directly under it (no <bake_id> subfolder) —
    # used to prove the enumerator looks in the right place (review, round 3).
    if custom_bake_dir is not None and not packed_made:
        bk = (getattr(mod, "bakes", []) or [None])[0]
        if bk is not None and hasattr(bk, "use_custom_path"):
            bk.use_custom_path = True
            bk.directory = custom_bake_dir
    bpy.ops.wm.save_as_mainfile(filepath=blend)
    bpy.context.view_layer.objects.active = ob
    ob.select_set(True)
    with bpy.context.temp_override(scene=sc, active_object=ob, object=ob,
                                   selected_objects=[ob]):
        bpy.ops.object.simulation_nodes_cache_bake()
    bpy.ops.wm.save_mainfile()
    return blend, (not packed_made), packed_made


def gn_bake_dir(outdir, blend=None):
    """The `<bake_dir>/<bake_id>` folder of the first GN disk bake, or None."""
    for ob in bpy.data.objects:
        for mod in ob.modifiers:
            if mod.type != "NODES":
                continue
            for b in getattr(mod, "bakes", []) or []:
                bid = getattr(b, "bake_id", None)
                if bid is not None:
                    d = os.path.join(outdir, "gnbake", str(bid))
                    if os.path.isdir(d):
                        return d
    return None


def build_fluid_mislabeled_mesh(outdir):
    """Adversarial (R10): delete the last mesh frame, then drop a wrongly-named
    data file into mesh/. The component-specific matcher must ignore it, so the
    mesh sub-cache is still missing a frame -> #18 FAIL."""
    blend = _make_fluid_blend(outdir, use_mesh=True)
    mesh = os.path.join(outdir, "fluidcache", "mesh")
    data = os.path.join(outdir, "fluidcache", "data")
    mesh_files = sorted(os.listdir(mesh))
    os.remove(os.path.join(mesh, mesh_files[-1]))          # remove a real mesh frame
    data_files = sorted(f for f in os.listdir(data) if f.endswith(".vdb"))
    shutil.copy(os.path.join(data, data_files[-1]),
                os.path.join(mesh, data_files[-1]))         # misplace a data file
    bpy.ops.wm.open_mainfile(filepath=blend)


def build_fluid_missing_config(outdir):
    """R11: a real bake, then delete a config/ file. config is a required
    component, so its absence must FAIL #18 even though data/ is intact."""
    blend = _make_fluid_blend(outdir, use_mesh=True)
    cfg = os.path.join(outdir, "fluidcache", "config")
    files = sorted(os.listdir(cfg))
    assert files, "expected baked fluid config files"
    os.remove(os.path.join(cfg, files[-1]))  # delete a required config frame
    bpy.ops.wm.open_mainfile(filepath=blend)


def build_fluid_offset_unknown(outdir):
    """R12: a fully-baked fluid whose cache_frame_offset is non-zero. The baked
    range no longer maps straight onto the render range, so #19 must report
    UNKNOWN rather than a false 'range covers' PASS."""
    blend = _make_fluid_blend(outdir, use_mesh=True)
    bpy.ops.wm.open_mainfile(filepath=blend)
    for o in bpy.context.scene.objects:
        for md in o.modifiers:
            if md.type == "FLUID" and md.fluid_type == "DOMAIN":
                md.domain_settings.cache_frame_offset = 5
    bpy.ops.wm.save_mainfile()


def _make_fluid_guide_blend(outdir, frame_end=4):
    """A real gas domain with guiding enabled (effector guide source), baked.
    Produces guiding/fluid_guiding_NNNN.vdb alongside data/ and config/."""
    reset()
    sc = bpy.context.scene
    sc.frame_start, sc.frame_end = 1, frame_end
    # Create ALL geometry first, before touching any fluid/guide settings. On
    # Blender 4.2 headless, adding an object *after* guiding is enabled on the
    # domain triggers a ViewLayer.update() crash (a Blender ops/depsgraph quirk,
    # unrelated to the add-on). Building geometry up front avoids it.
    bpy.ops.mesh.primitive_cube_add(size=4, location=(0, 0, 0))
    dom = bpy.context.active_object
    dom.name = "Domain"
    bpy.ops.mesh.primitive_uv_sphere_add(radius=0.7, location=(0, 0, -1.2))
    fl = bpy.context.active_object
    fl.name = "Inflow"
    bpy.ops.mesh.primitive_uv_sphere_add(radius=0.7, location=(0, 0, 1.2))
    ef = bpy.context.active_object
    ef.name = "Guide"
    bpy.context.view_layer.update()

    # Now configure modifiers (no more object creation after this point).
    m = dom.modifiers.new("Fluid", "FLUID")
    m.fluid_type = "DOMAIN"
    ds = m.domain_settings
    ds.domain_type = "GAS"
    ds.resolution_max = 16
    ds.cache_type = "ALL"
    ds.cache_frame_start, ds.cache_frame_end = 1, frame_end
    ds.cache_directory = "//fluidcache"

    f = fl.modifiers.new("Fluid", "FLUID")
    f.fluid_type = "FLOW"
    f.flow_settings.flow_type = "SMOKE"
    f.flow_settings.flow_behavior = "INFLOW"

    efm = ef.modifiers.new("Fluid", "FLUID")
    efm.fluid_type = "EFFECTOR"
    try:
        efm.effector_settings.effector_type = "GUIDE"
    except Exception:
        pass

    # Enable guiding on the domain LAST, once every object already exists.
    ds.use_guide = True
    try:
        ds.guide_source = "EFFECTOR"
    except Exception:
        pass
    blend = os.path.join(outdir, "fluid_guide.blend")
    bpy.ops.wm.save_as_mainfile(filepath=blend)
    with bpy.context.temp_override(scene=sc, active_object=dom, object=dom,
                                   selected_objects=[dom]):
        bpy.ops.fluid.bake_all()
    bpy.ops.wm.save_mainfile()
    return blend


def build_fluid_missing_guiding(outdir):
    """R16: a real guiding bake, then delete a guiding/ frame. Guiding is a
    required component when use_guide is on, so its absence must FAIL #18 even
    though data/ and config/ are intact."""
    blend = _make_fluid_guide_blend(outdir)
    guiding = os.path.join(outdir, "fluidcache", "guiding")
    assert os.path.isdir(guiding), "expected a guiding/ sub-cache dir"
    files = sorted(os.listdir(guiding))
    assert files, "expected baked guiding files"
    os.remove(os.path.join(guiding, files[-1]))  # delete a required guiding frame
    bpy.ops.wm.open_mainfile(filepath=blend)


def build_22_fail(outdir):
    reset()
    sc = bpy.context.scene
    sc.frame_start, sc.frame_end = 1, 4
    o = _add_cube("Domain", size=4.0)
    m = o.modifiers.new("Fluid", "FLUID")
    m.fluid_type = "DOMAIN"
    m.domain_settings.domain_type = "GAS"
    m.domain_settings.cache_directory = "/tmp/failsafe_abs_cache_outside"
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


# ---- #23 frame-rate / timing baseline fixtures -----------------------------
# #23 compares the current scene frame rate (and Rigid Body World time scale)
# against a value captured with Save Baseline. These exercise every branch:
# unchanged (PASS), changed fps / fps_base / time scale (WARNING), no baseline
# (NA setup hint), corrupt / foreign baseline (UNKNOWN), an intentional
# non-default time scale that MATCHES the baseline (PASS, not a false warning),
# and multiple scenes.

def _save_timing_baseline():
    """Capture a Failsafe baseline (external sidecar) for the current file."""
    from failsafe import baseline as bl
    p = bl.default_baseline_path()
    bl.save_baseline(bpy.context.scene, p, overwrite=True)
    return p


def build_23_pass(outdir):
    """Bake at 24 fps, save a baseline, change nothing -> #23 PASS."""
    _make_cloth_blend(outdir)
    bpy.context.scene.render.fps = 24
    bpy.context.scene.render.fps_base = 1.0
    _save_timing_baseline()


def build_23_warn_fps(outdir):
    """Bake + baseline at 24 fps, then set the scene to 30 -> #23 WARNING."""
    _make_cloth_blend(outdir)
    sc = bpy.context.scene
    sc.render.fps, sc.render.fps_base = 24, 1.0
    _save_timing_baseline()
    sc.render.fps = 30


def build_23_warn_fpsbase(outdir):
    """Change only fps_base (24/1.0 -> 24/1.001) so effective fps differs -> WARN."""
    _make_cloth_blend(outdir)
    sc = bpy.context.scene
    sc.render.fps, sc.render.fps_base = 24, 1.0
    _save_timing_baseline()
    sc.render.fps_base = 1.001


def build_23_na_no_baseline(outdir):
    """Baked cloth, NO baseline saved -> #23 NA (unobtrusive setup hint)."""
    _make_cloth_blend(outdir)
    # deliberately no baseline


def build_23_unknown_foreign(outdir):
    """Baseline saved, then its recorded source file is a different name -> UNKNOWN."""
    import json
    from failsafe import baseline as bl
    _make_cloth_blend(outdir)
    p = _save_timing_baseline()
    with open(p) as fh:
        d = json.load(fh)
    d["file"] = "/elsewhere/some_other_project.blend"
    with open(p, "w") as fh:
        json.dump(d, fh)


def build_23_unknown_corrupt(outdir):
    """A baseline file that exists but is unreadable garbage -> UNKNOWN."""
    from failsafe import baseline as bl
    _make_cloth_blend(outdir)
    _save_timing_baseline()
    with open(bl.default_baseline_path(), "w") as fh:
        fh.write("{ this is not valid json")


def build_23_rbw_intentional_ok(outdir):
    """A deliberate non-default Rigid Body World time scale (0.5) that MATCHES
    the baseline must NOT warn (the old code warned on any value != 1.0) -> PASS."""
    _make_cloth_blend(outdir)
    sc = bpy.context.scene
    sc.render.fps, sc.render.fps_base = 24, 1.0
    with bpy.context.temp_override(scene=sc):
        bpy.ops.rigidbody.world_add()
    sc.rigidbody_world.time_scale = 0.5
    _save_timing_baseline()           # captures time_scale=0.5
    # leave it at 0.5 -> unchanged -> PASS


def build_23_rbw_changed(outdir):
    """Rigid Body World time scale changed since the baseline -> WARNING."""
    _make_cloth_blend(outdir)
    sc = bpy.context.scene
    sc.render.fps, sc.render.fps_base = 24, 1.0
    with bpy.context.temp_override(scene=sc):
        bpy.ops.rigidbody.world_add()
    sc.rigidbody_world.time_scale = 1.0
    _save_timing_baseline()
    sc.rigidbody_world.time_scale = 0.5   # changed -> WARNING


def build_23_multiscene(outdir):
    """Two scenes captured in one baseline; change fps only in the active (sim)
    scene -> WARNING, proving per-scene timing is independent."""
    _make_cloth_blend(outdir)
    sc = bpy.context.scene
    sc.name = "SimScene"
    sc.render.fps, sc.render.fps_base = 24, 1.0
    # OtherScene's saved fps is set to the value the active scene will CHANGE to
    # (30), so if #23 ever compared against the wrong scene's record it would
    # wrongly PASS. Correct per-scene anchoring must still WARNING here.
    other = bpy.data.scenes.new("OtherScene")
    other.render.fps = 30
    _save_timing_baseline()           # captures both scenes (SimScene=24, Other=30)
    sc.render.fps = 30                # change active only -> WARNING on scan


def build_23_unknown_unreadable_fps(outdir):
    """B1 regression: a schema-4 baseline whose scene_timing fps was hand-edited
    to null. #23 must be UNKNOWN (it could not compare), NEVER a green PASS."""
    import json
    _make_cloth_blend(outdir)
    sc = bpy.context.scene
    sc.render.fps, sc.render.fps_base = 24, 1.0
    p = _save_timing_baseline()
    with open(p) as fh:
        d = json.load(fh)
    d["scene_timing"][sc.name]["fps"] = None
    with open(p, "w") as fh:
        json.dump(d, fh)


def build_23_unknown_bad_timescale(outdir):
    """M2 regression: fps matches, but the baseline's rbw_time_scale is garbage.
    #23 must report UNKNOWN, never a PASS that claims the time scale 'matches'."""
    import json
    _make_cloth_blend(outdir)
    sc = bpy.context.scene
    sc.render.fps, sc.render.fps_base = 24, 1.0
    with bpy.context.temp_override(scene=sc):
        bpy.ops.rigidbody.world_add()
    sc.rigidbody_world.time_scale = 1.0
    p = _save_timing_baseline()
    with open(p) as fh:
        d = json.load(fh)
    d["scene_timing"][sc.name]["rbw_time_scale"] = "not-a-number"
    with open(p, "w") as fh:
        json.dump(d, fh)


def build_schema3_baseline(outdir):
    """M1 regression: a baseline saved under the PREVIOUS schema (3), i.e. before
    timing tracking (no scene_timing section). After the 3->4 bump it must stay
    comparable for #26 (settings unchanged -> PASS) and read as NA for #23
    (frame-rate tracking simply not set up) — never voided to a false result."""
    import json
    _make_cloth_blend(outdir)
    p = _save_timing_baseline()
    with open(p) as fh:
        d = json.load(fh)
    d["schema"] = 3
    d.pop("scene_timing", None)       # schema-3 baselines carried no timing
    with open(p, "w") as fh:
        json.dump(d, fh)


# ---- B2 regression: non-finite / incomplete timing values must be UNKNOWN -----
_DELETE_KEY = object()


def _save_then_corrupt_timing(outdir, with_rbw=False, **changes):
    """Save a schema-4 baseline for a baked cloth at 24 fps, then overwrite one or
    more scene_timing values with junk (or delete a key with _DELETE_KEY). Python's
    json writes NaN/Infinity literally and parses them back, so these simulate a
    hand-edited or half-written sidecar."""
    import json
    _make_cloth_blend(outdir)
    sc = bpy.context.scene
    sc.render.fps, sc.render.fps_base = 24, 1.0
    if with_rbw:
        with bpy.context.temp_override(scene=sc):
            bpy.ops.rigidbody.world_add()
        sc.rigidbody_world.time_scale = 1.0
    p = _save_timing_baseline()
    with open(p) as fh:
        d = json.load(fh)
    rec = d["scene_timing"][sc.name]
    for k, v in changes.items():
        if v is _DELETE_KEY:
            rec.pop(k, None)
        else:
            rec[k] = v
    with open(p, "w") as fh:
        json.dump(d, fh)


def build_23_nan_fps(outdir):
    """fps = NaN: NaN comparisons are all False, so an unguarded check would fall
    through to a green PASS. Must be UNKNOWN."""
    _save_then_corrupt_timing(outdir, fps=float("nan"))


def build_23_inf_fps(outdir):
    """fps = Infinity -> UNKNOWN (not a WARNING formatting 'inf FPS')."""
    _save_then_corrupt_timing(outdir, fps=float("inf"))


def build_23_nan_fpsbase(outdir):
    """fps_base = NaN -> UNKNOWN."""
    _save_then_corrupt_timing(outdir, fps_base=float("nan"))


def build_23_zero_fps(outdir):
    """fps = 0 (non-positive) -> UNKNOWN."""
    _save_then_corrupt_timing(outdir, fps=0)


def build_23_missing_fpsbase(outdir):
    """A saved record missing fps_base is incomplete -> UNKNOWN, not a 1.0 default
    that could mask a changed base."""
    _save_then_corrupt_timing(outdir, fps_base=_DELETE_KEY)


def build_23_nan_timescale(outdir):
    """fps matches, but rbw_time_scale = NaN -> UNKNOWN, never a PASS that claims
    the time scale 'also matches'."""
    _save_then_corrupt_timing(outdir, with_rbw=True, rbw_time_scale=float("nan"))
