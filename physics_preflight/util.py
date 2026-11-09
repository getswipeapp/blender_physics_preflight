# SPDX-License-Identifier: GPL-3.0-or-later
"""Read-only scene / geometry helpers shared by the checks.

Every function here is pure and side-effect free: it may read evaluated
geometry, but it never changes the scene, selection, or active object, and it
always frees temporary meshes it creates.
"""
import bpy
import bmesh
from mathutils import Vector
from mathutils.bvhtree import BVHTree

PHYSICS_MODIFIER_TYPES = {"CLOTH", "SOFT_BODY", "FLUID", "DYNAMIC_PAINT"}
DEFORM_MODIFIER_TYPES = {
    "ARMATURE", "CAST", "CURVE", "DISPLACE", "HOOK", "LAPLACIANDEFORM",
    "LATTICE", "MESH_DEFORM", "SHRINKWRAP", "SIMPLE_DEFORM", "SMOOTH",
    "CORRECTIVE_SMOOTH", "LAPLACIANSMOOTH", "SURFACE_DEFORM", "WARP",
    "WAVE", "SUBSURF", "MULTIRES",
}


def unit_scale(scene):
    s = getattr(scene.unit_settings, "scale_length", 1.0) or 1.0
    return s


def physics_modifier_types(obj):
    return {m.type for m in obj.modifiers if m.type in PHYSICS_MODIFIER_TYPES}


def has_collision_modifier(obj):
    return any(m.type == "COLLISION" for m in obj.modifiers)


def is_physics_object(obj):
    """True if the object takes part in a physics/simulation system at all."""
    if getattr(obj, "rigid_body", None) is not None:
        return True
    if getattr(obj, "rigid_body_constraint", None) is not None:
        return True
    if obj.type == "MESH" and obj.particle_systems:
        return True
    if physics_modifier_types(obj):
        return True
    if has_collision_modifier(obj):
        return True
    return False


def physics_objects(scene):
    return [o for o in scene.objects if is_physics_object(o)]


def active_rigid_bodies(scene):
    out = []
    for o in scene.objects:
        rb = getattr(o, "rigid_body", None)
        if rb is not None and rb.type == "ACTIVE":
            out.append(o)
    return out


def all_rigid_bodies(scene):
    return [o for o in scene.objects
            if getattr(o, "rigid_body", None) is not None]


def collider_objects(scene):
    """Objects acting as Collision colliders (cloth/soft-body/particle floors)."""
    out = []
    for o in scene.objects:
        if has_collision_modifier(o):
            col = getattr(o, "collision", None)
            if col is None or col.use:
                out.append(o)
    return out


# --------------------------------------------------------------- geometry ---

def world_bbox_corners(obj):
    mw = obj.matrix_world
    return [mw @ Vector(c) for c in obj.bound_box]


def world_bbox_center(obj):
    cs = world_bbox_corners(obj)
    return sum(cs, Vector((0.0, 0.0, 0.0))) / 8.0


def world_dimensions(obj):
    """Axis-aligned world-space size (already includes object scale)."""
    return Vector(obj.dimensions)


def max_dim(obj):
    d = obj.dimensions
    return max(d.x, d.y, d.z)


def min_positive_dim(obj):
    d = [v for v in obj.dimensions if v > 1e-9]
    return min(d) if d else 0.0


class EvalMesh:
    """Context manager yielding the evaluated mesh, cleaned up on exit."""

    def __init__(self, obj, depsgraph):
        self.obj = obj
        self.dg = depsgraph
        self.ev = None
        self.me = None

    def __enter__(self):
        self.ev = self.obj.evaluated_get(self.dg)
        self.me = self.ev.to_mesh()
        return self.me

    def __exit__(self, *exc):
        if self.ev is not None:
            try:
                self.ev.to_mesh_clear()
            except Exception:
                pass
        return False


def eval_face_count(obj, depsgraph):
    with EvalMesh(obj, depsgraph) as me:
        return len(me.polygons)


def non_manifold_edge_count(obj, depsgraph, cap=200000):
    """Count *bad* non-manifold edges on the evaluated mesh: edges shared by
    more than two faces (T-junctions / internal faces). Open boundary edges
    (a plane floor, a flat sheet of cloth) are intentional and NOT counted.
    Returns int or None (None = mesh too large, UNKNOWN)."""
    with EvalMesh(obj, depsgraph) as me:
        if len(me.edges) > cap:
            return None
        bm = bmesh.new()
        try:
            bm.from_mesh(me)
            return sum(1 for e in bm.edges if len(e.link_faces) > 2)
        finally:
            bm.free()


def is_concave(obj, depsgraph, face_cap=4000):
    """Convexity test on the evaluated mesh (local space).

    Returns True (concave), False (convex) or None (UNKNOWN: too many faces,
    or no geometry). A solid is convex iff every vertex lies on the inner side
    of every face plane.
    """
    with EvalMesh(obj, depsgraph) as me:
        nverts = len(me.vertices)
        if nverts == 0 or len(me.polygons) == 0:
            return None
        if len(me.polygons) > face_cap:
            return None
        # tolerance relative to object size
        dmax = max(obj.dimensions) or 1.0
        tol = 1e-3 * dmax
        verts = [v.co.copy() for v in me.vertices]
        for p in me.polygons:
            n = p.normal
            if n.length_squared < 1e-12:
                continue
            c = p.center
            for v in verts:
                if (v - c).dot(n) > tol:
                    return True
        return False


def bvh_from_object(obj, depsgraph):
    """World-space BVHTree of the evaluated mesh, or None if no geometry."""
    with EvalMesh(obj, depsgraph) as me:
        if len(me.polygons) == 0:
            return None
        mw = obj.matrix_world
        verts = [mw @ v.co for v in me.vertices]
        polys = [tuple(p.vertices) for p in me.polygons]
        try:
            return BVHTree.FromPolygons(verts, polys)
        except Exception:
            return None


def bbox_overlap(a, b):
    """Cheap AABB overlap test between two objects' world bounding boxes."""
    ca = world_bbox_corners(a)
    cb = world_bbox_corners(b)
    amin = Vector((min(c.x for c in ca), min(c.y for c in ca), min(c.z for c in ca)))
    amax = Vector((max(c.x for c in ca), max(c.y for c in ca), max(c.z for c in ca)))
    bmin = Vector((min(c.x for c in cb), min(c.y for c in cb), min(c.z for c in cb)))
    bmax = Vector((max(c.x for c in cb), max(c.y for c in cb), max(c.z for c in cb)))
    return (amin.x <= bmax.x and amax.x >= bmin.x and
            amin.y <= bmax.y and amax.y >= bmin.y and
            amin.z <= bmax.z and amax.z >= bmin.z)


def point_inside_bvh(bvh, point):
    """Ray-parity point-in-solid test. Casts along +X and counts crossings.

    Returns True/False. Robust enough for the containment case BVH.overlap
    misses (one body fully inside another), which is the Phase 0 catch for
    check #3.
    """
    direction = Vector((1.0, 0.0, 0.0))
    eps = 1e-6
    origin = point.copy()
    crossings = 0
    for _ in range(128):
        hit = bvh.ray_cast(origin, direction)
        loc = hit[0]
        if loc is None:
            break
        crossings += 1
        origin = loc + direction * eps
    return (crossings % 2) == 1


_TRANSFORM_PATHS = ("location", "rotation_euler", "rotation_quaternion",
                    "rotation_axis_angle", "scale")


def _iter_action_fcurves(ad):
    """Yield an action's F-Curves across Blender versions.

    Blender 4.2 and earlier expose ``action.fcurves``. Blender 4.4+ moved to
    slotted actions where the F-Curves live in layer > strip > channelbag.
    """
    act = ad.action
    if act is None:
        return
    legacy = getattr(act, "fcurves", None)
    if legacy is not None:
        for fc in legacy:
            yield fc
        return
    slot = getattr(ad, "action_slot", None)
    for layer in getattr(act, "layers", []):
        for strip in getattr(layer, "strips", []):
            cb = None
            if slot is not None:
                try:
                    cb = strip.channelbag(slot)
                except Exception:
                    cb = None
            bags = [cb] if cb is not None else list(getattr(strip, "channelbags", []))
            for bag in bags:
                if bag is None:
                    continue
                for fc in getattr(bag, "fcurves", []):
                    yield fc


def has_transform_animation(obj):
    """True if the object's own action/drivers animate location/rotation/scale."""
    ad = obj.animation_data
    if ad is None:
        return False
    if ad.action is not None:
        for fc in _iter_action_fcurves(ad):
            if getattr(fc, "data_path", "") in _TRANSFORM_PATHS:
                return True
    for fc in getattr(ad, "drivers", []):
        if getattr(fc, "data_path", "") in _TRANSFORM_PATHS:
            return True
    return False


def is_moved_externally(obj):
    """Animated by its own action/drivers, by an animated parent, or by a
    non-static constraint (Follow Path, Child Of, etc.)."""
    if has_transform_animation(obj):
        return True
    p = obj.parent
    seen = 0
    while p is not None and seen < 32:
        if has_transform_animation(p):
            return True
        p = p.parent
        seen += 1
    if obj.constraints:
        for c in obj.constraints:
            if not c.mute and c.influence > 0.0:
                return True
    return False


def vertex_group_count(obj, group_name):
    """Number of vertices with nonzero weight in a vertex group.

    Returns (exists, count). count is None if it cannot be determined.
    """
    vg = obj.vertex_groups.get(group_name)
    if vg is None:
        return (False, None)
    if obj.type != "MESH" or obj.data is None:
        return (True, None)
    idx = vg.index
    count = 0
    for v in obj.data.vertices:
        for g in v.groups:
            if g.group == idx and g.weight > 0.0:
                count += 1
                break
    return (True, count)
