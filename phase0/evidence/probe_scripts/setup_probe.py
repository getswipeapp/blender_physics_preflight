"""Feasibility probe for the 8 physics-setup checks (read-only APIs)."""
import json, sys
import sys as _s
ARGV = _s.argv[_s.argv.index("--")+1:] if "--" in _s.argv else _s.argv[1:]
import bpy, bmesh
from mathutils.bvhtree import BVHTree

bpy.ops.wm.read_factory_settings(use_empty=True)
sc = bpy.context.scene
R = {"version": bpy.app.version_string}

# fixtures: two overlapping cubes (one scaled, one negative), a parent with scale
bpy.ops.mesh.primitive_cube_add(location=(0, 0, 0)); a = bpy.context.active_object; a.name = "A"
bpy.ops.mesh.primitive_cube_add(location=(0.5, 0, 0)); b = bpy.context.active_object; b.name = "B"
b.scale = (-1, 2, 1); b.rotation_euler = (0.3, 0, 0)
bpy.ops.object.empty_add(); p = bpy.context.active_object; p.name = "P"; p.scale = (3, 3, 3)
a.parent = p
bpy.ops.mesh.primitive_plane_add(location=(5, 0, 0)); pl = bpy.context.active_object; pl.name = "Open"
bpy.ops.mesh.primitive_uv_sphere_add(segments=256, ring_count=128, location=(10, 0, 0)); hp = bpy.context.active_object
for o in (a, b, pl, hp):
    with bpy.context.temp_override(active_object=o, object=o, selected_objects=[o]):
        bpy.ops.rigidbody.object_add()
b.rigid_body.mass = 5000.0
b.rigid_body.collision_shape = "CONVEX_HULL"
pl.rigid_body.collision_shape = "MESH"
hp.rigid_body.collision_shape = "MESH"
bpy.ops.mesh.primitive_plane_add(location=(0, 5, 2)); cl = bpy.context.active_object
cl.modifiers.new("Cloth", "CLOTH")
bpy.context.view_layer.update()

dg = bpy.context.evaluated_depsgraph_get()
out = {}
for o in (a, b, pl, hp):
    m = o.matrix_world
    ev = o.evaluated_get(dg)
    me = ev.to_mesh()
    bm = bmesh.new(); bm.from_mesh(me)
    nm_edges = sum(1 for e in bm.edges if not e.is_manifold)
    out[o.name] = {
        "scale": tuple(round(s, 3) for s in o.scale),
        "rotation": tuple(round(r, 3) for r in o.rotation_euler),
        "world_det": round(m.determinant(), 3),
        "parent_scale": tuple(o.parent.scale) if o.parent else None,
        "mass": o.rigid_body.mass, "shape": o.rigid_body.collision_shape,
        "rb_type": o.rigid_body.type,
        "faces": len(me.polygons), "non_manifold_edges": nm_edges,
        "dims": tuple(round(x, 3) for x in o.dimensions),
    }
    bm.free(); ev.to_mesh_clear()


def bvh(o):
    ev = o.evaluated_get(dg)
    me = ev.to_mesh()
    verts = [o.matrix_world @ v.co for v in me.vertices]
    polys = [tuple(pp.vertices) for pp in me.polygons]
    t = BVHTree.FromPolygons(verts, polys)
    ev.to_mesh_clear()
    return t


R["objects"] = out
R["overlap_A_B_pairs"] = len(bvh(a).overlap(bvh(b)))
R["overlap_A_Open_pairs"] = len(bvh(a).overlap(bvh(pl)))
rbw = sc.rigidbody_world
R["rbw"] = {"enabled": rbw.enabled, "substeps": rbw.substeps_per_frame,
            "iterations": rbw.solver_iterations, "collection": rbw.collection.name if rbw.collection else None,
            "cache_range": (rbw.point_cache.frame_start, rbw.point_cache.frame_end),
            "scene_range": (sc.frame_start, sc.frame_end)}
cs = cl.modifiers["Cloth"].collision_settings
R["cloth"] = {"use_collision": cs.use_collision, "self": cs.use_self_collision,
              "collection": cs.collection.name if cs.collection else None,
              "distance_min": cs.distance_min, "quality": cs.collision_quality,
              "colliders_in_scene": [o.name for o in sc.objects if o.collision and o.collision.use]
              if hasattr(bpy.types.Object, "collision") else "n/a"}
print("SETUPJSON " + json.dumps(R))
