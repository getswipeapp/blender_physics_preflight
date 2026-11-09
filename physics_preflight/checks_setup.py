# SPDX-License-Identifier: GPL-3.0-or-later
"""Physics-setup checks (1-16).

Each function takes (ctx, mk) where ctx is a Blender context-like object with
``scene`` and ``evaluated_depsgraph_get()``, and mk builds a Result bound to the
check. Checks are read-only.

Judgement-heavy checks (mass, size, origin, margin, intersections) report
WARNING, never FAIL, to avoid false alarms. Structural mistakes that will
certainly misbehave (missing constraint object, object not in the Rigid Body
World, animated collider not marked Animated) report FAIL.
"""
from mathutils import Vector

from .engine import check, Status, GROUP_SETUP
from . import util


def _dg(ctx):
    return ctx.evaluated_depsgraph_get()


# --------------------------------------------------------------------- 1 ----
@check(1, "Unapplied scale / rotation on physics objects", GROUP_SETUP)
def c01_unapplied_transform(ctx, mk):
    out = []
    objs = util.physics_objects(ctx.scene)
    for o in objs:
        sx, sy, sz = o.scale
        non_unit = any(abs(s - 1.0) > 1e-4 for s in (sx, sy, sz))
        non_uniform = (abs(sx - sy) > 1e-4 or abs(sy - sz) > 1e-4)
        if non_uniform:
            out.append(mk(Status.WARNING,
                          "Non-uniform scale (%.3g, %.3g, %.3g). Collision "
                          "shapes and cloth behave wrongly until scale is "
                          "applied." % (sx, sy, sz),
                          object_name=o.name,
                          hint="Object > Apply > Scale (Ctrl+A)."))
        elif non_unit:
            out.append(mk(Status.WARNING,
                          "Scale is not 1.0 (%.3g, %.3g, %.3g). Apply scale so "
                          "the simulation uses the real size." % (sx, sy, sz),
                          object_name=o.name,
                          hint="Object > Apply > Scale (Ctrl+A)."))
        # Rotation matters where the sim uses the mesh rest shape or the object
        # is a mesh collider (cloth / soft body / collision).
        if util.rotation_matters(o) and util.has_unapplied_rotation(o):
            out.append(mk(Status.WARNING,
                          "Unapplied object rotation on a cloth/soft-body/"
                          "collision object. The rest shape and collider can be "
                          "offset from what you see.",
                          object_name=o.name,
                          hint="Object > Apply > Rotation (Ctrl+A)."))
    if not out:
        if objs:
            return [mk(Status.PASS,
                       "Physics objects have scale applied (and rotation where "
                       "it matters).")]
        return []
    return out


# --------------------------------------------------------------------- 2 ----
@check(2, "Suspicious rigid-body mass for the object size", GROUP_SETUP)
def c02_mass_sanity(ctx, mk):
    out = []
    any_active = False
    for o in util.active_rigid_bodies(ctx.scene):
        any_active = True
        rb = o.rigid_body
        d = o.dimensions
        vol = d.x * d.y * d.z
        if vol <= 1e-9:
            continue
        density = rb.mass / vol  # kg per m^3 (in scene units)
        if density < 2.0:
            out.append(mk(Status.WARNING,
                          "Very low density (%.3g kg/m^3) for its size. A "
                          "%.2gm object weighing %.3gkg will feel like a "
                          "balloon." % (density, max(d), rb.mass),
                          object_name=o.name,
                          hint="Check the Mass value in Physics Properties."))
        elif density > 25000.0:
            out.append(mk(Status.WARNING,
                          "Very high density (%.3g kg/m^3) for its size — "
                          "heavier than any solid metal. It may punch through "
                          "other objects." % density,
                          object_name=o.name,
                          hint="Check the Mass value in Physics Properties."))
    if not out and any_active:
        return [mk(Status.PASS, "Rigid-body masses look reasonable for their size.")]
    return out


# --------------------------------------------------------------------- 3 ----
@check(3, "Objects overlapping at the start frame", GROUP_SETUP)
def c03_initial_intersections(ctx, mk):
    dg = _dg(ctx)
    scene = ctx.scene
    bodies = util.active_rigid_bodies(scene)
    others = util.all_rigid_bodies(scene)
    if not bodies:
        return []
    out = []
    bvh_cache = {}
    uncertain = False  # a BVH failed to build, or we're not on the start frame

    # The sim starts at the first frame; geometry is evaluated at the CURRENT
    # frame. If they differ we can still report overlaps we see, but we must not
    # claim a clean PASS for the start state we didn't actually look at.
    at_start = (scene.frame_current == scene.frame_start)
    if not at_start:
        uncertain = True
    where = ("the start frame" if at_start
             else "the current frame (%d)" % scene.frame_current)

    def bvh(o):
        if o.name not in bvh_cache:
            bvh_cache[o.name] = util.bvh_from_object(o, dg)
        return bvh_cache[o.name]

    reported = set()
    for a in bodies:
        for b in others:
            if a is b:
                continue
            key = tuple(sorted((a.name, b.name)))
            if key in reported:
                continue
            if not util.bbox_overlap(a, b):
                continue
            ba, bb = bvh(a), bvh(b)
            if ba is None or bb is None:
                uncertain = True  # couldn't build geometry -> don't claim clean
                continue
            overlaps = ba.overlap(bb)
            if overlaps:
                reported.add(key)
                out.append(mk(Status.WARNING,
                              "Overlaps '%s' at %s. Interpenetrating rigid bodies "
                              "can explode apart on the first frame."
                              % (b.name, where),
                              object_name=a.name,
                              hint="Move them apart or add a small gap before "
                                   "frame 1."))
                continue
            # containment: BVH surface overlap misses one body fully inside
            # another, so test a point of A against B (Phase 0 catch).
            ca = util.world_bbox_center(a)
            cb = util.world_bbox_center(b)
            if util.point_inside_bvh(bb, ca) or util.point_inside_bvh(ba, cb):
                reported.add(key)
                out.append(mk(Status.WARNING,
                              "'%s' is fully inside '%s' at %s; they will burst "
                              "apart." % (a.name, b.name, where),
                              object_name=a.name,
                              hint="Separate the objects before the first frame."))
    if out:
        return out
    if uncertain:
        if not at_start:
            return [mk(Status.UNKNOWN,
                       "Overlaps are only checked at the frame you're on (%d), "
                       "not the start frame (%d). Go to the start frame and "
                       "re-scan to be sure."
                       % (scene.frame_current, scene.frame_start),
                       hint="Set the timeline to the first frame, then Scan "
                            "again.")]
        return [mk(Status.UNKNOWN,
                   "Some rigid bodies have no evaluable mesh, so start-frame "
                   "overlaps couldn't be fully checked.")]
    return [mk(Status.PASS, "No rigid bodies overlap at the start frame.")]


# --------------------------------------------------------------------- 4 ----
@check(4, "Collision shape mismatch (Convex Hull on a concave object)", GROUP_SETUP)
def c04_shape_mismatch(ctx, mk):
    dg = _dg(ctx)
    out = []
    any_checked = False
    for o in util.all_rigid_bodies(ctx.scene):
        rb = o.rigid_body
        if o.type != "MESH":
            continue
        if rb.collision_shape != "CONVEX_HULL":
            continue
        any_checked = True
        concave = util.is_concave(o, dg)
        if concave is None:
            out.append(mk(Status.UNKNOWN,
                          "Uses Convex Hull, but the mesh is too dense to test "
                          "for concavity here.",
                          object_name=o.name,
                          hint="For bowls/cups/rooms use Mesh shape (passive)."))
        elif concave:
            sev = Status.WARNING
            out.append(mk(sev,
                          "Concave object using a Convex Hull shape. Things will "
                          "float above its opening instead of falling in.",
                          object_name=o.name,
                          hint="Passive colliders: use Mesh shape. Active bodies "
                               "can't use Mesh — split the shape into convex parts."))
    if not out and any_checked:
        return [mk(Status.PASS, "Convex Hull shapes are used only on convex objects.")]
    return out


# --------------------------------------------------------------------- 5 ----
@check(5, "High-poly or non-manifold colliders", GROUP_SETUP)
def c05_collider_geometry(ctx, mk):
    dg = _dg(ctx)
    scene = ctx.scene
    out = []
    targets = set()
    for o in util.all_rigid_bodies(scene):
        if o.type == "MESH" and o.rigid_body.collision_shape == "MESH":
            targets.add(o.name)
    for o in util.collider_objects(scene):
        if o.type == "MESH":
            targets.add(o.name)
    for name in sorted(targets):
        o = scene.objects.get(name)
        if o is None:
            continue
        faces = util.eval_face_count(o, dg)
        if faces > 100000:
            out.append(mk(Status.WARNING,
                          "Collider has %d faces. High-poly colliders make sims "
                          "slow and unstable." % faces,
                          object_name=o.name,
                          hint="Use a low-poly proxy collider."))
        nm = util.non_manifold_edge_count(o, dg)
        if nm is None:
            out.append(mk(Status.UNKNOWN,
                          "Collider is too dense to test for non-manifold edges.",
                          object_name=o.name))
        elif nm > 0:
            out.append(mk(Status.WARNING,
                          "Collider has %d edge(s) shared by more than two faces "
                          "(internal/overlapping geometry). Collisions can be "
                          "unstable." % nm,
                          object_name=o.name,
                          hint="Clean up: Select > All by Trait > Non Manifold, "
                               "and Mesh > Clean Up in Edit Mode."))
    if not out and targets:
        return [mk(Status.PASS, "Colliders are manifold and reasonably light.")]
    return out


# --------------------------------------------------------------------- 6 ----
@check(6, "Rigid Body World disabled / misconfigured", GROUP_SETUP)
def c06_rigidbody_world(ctx, mk):
    scene = ctx.scene
    bodies = util.all_rigid_bodies(scene)
    if not bodies:
        return []
    out = []
    rbw = scene.rigidbody_world
    if rbw is None:
        return [mk(Status.FAIL,
                   "Objects have Rigid Body physics but there is no Rigid Body "
                   "World. Nothing will move.",
                   hint="Scene Properties > Rigid Body World > Add.")]
    if not rbw.enabled:
        out.append(mk(Status.FAIL,
                      "Rigid Body World is disabled. No rigid body will move.",
                      hint="Enable it in Scene Properties > Rigid Body World."))
    coll = rbw.collection
    if coll is None:
        out.append(mk(Status.FAIL,
                      "Rigid Body World has no collection, so no object is "
                      "simulated.",
                      hint="Assign a collection in Rigid Body World settings."))
    else:
        members = set(coll.all_objects.keys()) if hasattr(coll, "all_objects") else set(coll.objects.keys())
        for o in bodies:
            if o.name not in members:
                out.append(mk(Status.FAIL,
                              "Has a rigid body but is not in the Rigid Body "
                              "World collection, so it is ignored.",
                              object_name=o.name,
                              hint="Object > Rigid Body > Add, or add it to the "
                                   "Rigid Body World collection."))
    if rbw.substeps_per_frame < 10:
        out.append(mk(Status.WARNING,
                      "Rigid Body World substeps are low (%d). Fast or stacked "
                      "objects may jitter or pass through each other."
                      % rbw.substeps_per_frame,
                      hint="Raise Substeps Per Frame (default 10) in Rigid Body "
                           "World settings."))
    if rbw.solver_iterations < 10:
        out.append(mk(Status.WARNING,
                      "Solver iterations are low (%d); constraints may be loose."
                      % rbw.solver_iterations,
                      hint="Raise Solver Iterations (default 10)."))
    if not out:
        return [mk(Status.PASS, "Rigid Body World is enabled and all bodies are in it.")]
    return out


# --------------------------------------------------------------------- 7 ----
@check(7, "Cloth / soft-body collision not configured", GROUP_SETUP)
def c07_cloth_collision(ctx, mk):
    scene = ctx.scene
    out = []
    colliders = util.collider_objects(scene)
    any_cloth = False
    for o in scene.objects:
        for m in o.modifiers:
            if m.type == "CLOTH":
                any_cloth = True
                cs = m.collision_settings
                if not cs.use_collision:
                    out.append(mk(Status.WARNING,
                                  "Cloth object has Object Collision turned off; "
                                  "it will fall through everything.",
                                  object_name=o.name,
                                  hint="Enable Collisions > Object Collisions in "
                                       "the Cloth settings."))
                elif not colliders:
                    out.append(mk(Status.WARNING,
                                  "Cloth collision is on, but no object in the "
                                  "scene has a Collision modifier to collide with.",
                                  object_name=o.name,
                                  hint="Add a Collision modifier to the floor / "
                                       "collider object."))
            elif m.type == "SOFT_BODY":
                any_cloth = True
                st = getattr(m, "settings", None)
                if st is not None and hasattr(st, "use_edge_collision"):
                    if not (st.use_edge_collision or getattr(st, "use_face_collision", False)):
                        # self-collision off is fine; only flag if no colliders
                        if not colliders:
                            out.append(mk(Status.WARNING,
                                          "Soft body has no Collision colliders in "
                                          "the scene; it may fall through the floor.",
                                          object_name=o.name,
                                          hint="Add a Collision modifier to the "
                                               "collider object."))
    if not out and any_cloth:
        return [mk(Status.PASS, "Cloth / soft-body collision is set up.")]
    return out


# --------------------------------------------------------------------- 8 ----
@check(8, "Negative scale or scaled parents on physics objects", GROUP_SETUP)
def c08_negative_scale(ctx, mk):
    out = []
    for o in util.physics_objects(ctx.scene):
        det = o.matrix_world.determinant()
        if det < 0:
            out.append(mk(Status.FAIL,
                          "Mirrored / negative scale (normals are inverted). "
                          "Collisions and cloth will behave backwards.",
                          object_name=o.name,
                          hint="Apply scale, or fix the negative axis and "
                               "recalculate normals."))
        elif any(s < 0 for s in o.scale):
            out.append(mk(Status.WARNING,
                          "Has a negative scale component. This often flips "
                          "normals and collision.",
                          object_name=o.name,
                          hint="Apply scale (Ctrl+A)."))
        p = o.parent
        if p is not None:
            ps = p.scale
            if any(abs(s - 1.0) > 1e-3 for s in ps):
                out.append(mk(Status.WARNING,
                              "Parent '%s' has scale (%.3g, %.3g, %.3g); the "
                              "physics object inherits it and its collision size "
                              "may be wrong." % (p.name, ps[0], ps[1], ps[2]),
                              object_name=o.name,
                              hint="Apply scale on the parent, or unparent for "
                                   "the simulation."))
    if not out and util.physics_objects(ctx.scene):
        return [mk(Status.PASS, "No negative scale or scaled parents on physics objects.")]
    return out


# --------------------------------------------------------------------- 9 ----
@check(9, "Real-world size sanity for the scene scale", GROUP_SETUP)
def c09_size_sanity(ctx, mk):
    scene = ctx.scene
    us = util.unit_scale(scene)
    out = []
    bodies = util.physics_objects(scene)
    for o in bodies:
        if o.type != "MESH":
            continue
        md = util.max_dim(o) * us  # real-world metres
        if md <= 1e-9:
            continue
        if md < 0.001:
            out.append(mk(Status.WARNING,
                          "Only %.3g mm across at this scene scale. The solver "
                          "is tuned around 1 m; tiny objects are unstable."
                          % (md * 1000.0),
                          object_name=o.name,
                          hint="Scale up, or raise substeps, or adjust the "
                               "scene's Unit Scale."))
        elif md > 1000.0:
            out.append(mk(Status.WARNING,
                          "About %.3g m across — very large. Large objects can "
                          "simulate sluggishly or jitter." % md,
                          object_name=o.name,
                          hint="Consider the scene's Unit Scale."))
    if not out and bodies:
        return [mk(Status.PASS, "Physics objects are a sensible real-world size.")]
    return out


# -------------------------------------------------------------------- 10 ----
@check(10, "Origin far from geometry on active rigid bodies", GROUP_SETUP)
def c10_origin_offset(ctx, mk):
    out = []
    bodies = util.active_rigid_bodies(ctx.scene)
    for o in bodies:
        origin = o.matrix_world.translation
        center = util.world_bbox_center(o)
        offset = (center - origin).length
        md = util.max_dim(o)
        if md <= 1e-9:
            continue
        if offset > 0.5 * md and offset > 1e-4:
            out.append(mk(Status.WARNING,
                          "Origin is %.2g units from the mesh centre (object is "
                          "%.2g across). It will spin and tumble off-centre."
                          % (offset, md),
                          object_name=o.name,
                          hint="Object > Set Origin > Origin to Center of Mass "
                               "(or to Geometry)."))
    if not out and bodies:
        return [mk(Status.PASS, "Rigid-body origins are near their geometry.")]
    return out


# -------------------------------------------------------------------- 11 ----
@check(11, "Collision margin too large for the object size", GROUP_SETUP)
def c11_collision_margin(ctx, mk):
    out = []
    bodies = util.all_rigid_bodies(ctx.scene)
    for o in bodies:
        rb = o.rigid_body
        margin = rb.collision_margin
        if not getattr(rb, "use_margin", False):
            # Margin still applies on some shapes, but when use_margin is off
            # Blender uses an embedded margin; only flag the explicit case.
            pass
        mind = util.min_positive_dim(o)
        if mind <= 1e-9:
            continue
        if margin > 0.25 * mind and margin > 1e-5:
            out.append(mk(Status.WARNING,
                          "Collision margin (%.3g) is large versus the object's "
                          "smallest size (%.3g). Objects will hover with a "
                          "visible gap." % (margin, mind),
                          object_name=o.name,
                          hint="Lower Collision Margin in Physics Properties "
                               "(default 0.04)."))
    if not out and bodies:
        return [mk(Status.PASS, "Collision margins are small relative to object size.")]
    return out


# -------------------------------------------------------------------- 12 ----
@check(12, "Animated passive collider not marked 'Animated'", GROUP_SETUP)
def c12_animated_passive(ctx, mk):
    out = []
    bodies = util.all_rigid_bodies(ctx.scene)
    for o in bodies:
        rb = o.rigid_body
        if rb.type != "PASSIVE":
            continue
        if util.is_moved_externally(o) and not rb.kinematic:
            out.append(mk(Status.FAIL,
                          "Passive collider is animated, but 'Animated' is off. "
                          "Its collision shape stays frozen at the start frame.",
                          object_name=o.name,
                          hint="Enable Physics Properties > Rigid Body > "
                               "Settings > Animated."))
    if not out and bodies:
        return [mk(Status.PASS, "Animated colliders are marked 'Animated'.")]
    return out


# -------------------------------------------------------------------- 13 ----
@check(13, "Broken rigid-body constraints", GROUP_SETUP)
def c13_constraints(ctx, mk):
    out = []
    any_con = False
    for o in ctx.scene.objects:
        rbc = getattr(o, "rigid_body_constraint", None)
        if rbc is None:
            continue
        any_con = True
        if rbc.object1 is None or rbc.object2 is None:
            out.append(mk(Status.FAIL,
                          "Constraint is missing object 1 and/or object 2; it "
                          "does nothing (chains/hinges fall apart).",
                          object_name=o.name,
                          hint="Set both objects in the Rigid Body Constraint."))
            continue
        for slot, other in (("object 1", rbc.object1), ("object 2", rbc.object2)):
            if getattr(other, "rigid_body", None) is None:
                out.append(mk(Status.FAIL,
                              "%s ('%s') has no rigid body, so the constraint "
                              "can't hold it." % (slot, other.name),
                              object_name=o.name,
                              hint="Add a rigid body to '%s'." % other.name))
        if not rbc.enabled:
            out.append(mk(Status.WARNING,
                          "Rigid-body constraint is disabled.",
                          object_name=o.name,
                          hint="Enable it in the Rigid Body Constraint panel."))
    if not out and any_con:
        return [mk(Status.PASS, "Rigid-body constraints reference valid objects.")]
    return out


# -------------------------------------------------------------------- 14 ----
@check(14, "Collision modifier is above deforming modifiers", GROUP_SETUP)
def c14_collision_stack_order(ctx, mk):
    out = []
    any_col = False
    for o in ctx.scene.objects:
        col_idx = None
        deform_after = []
        for i, m in enumerate(o.modifiers):
            if m.type == "COLLISION":
                col_idx = i
                any_col = True
            elif col_idx is not None and m.type in util.DEFORM_MODIFIER_TYPES:
                deform_after.append(m.name)
        if col_idx is not None and deform_after:
            out.append(mk(Status.WARNING,
                          "Collision modifier is above deforming modifier(s) "
                          "%s. Cloth will collide with the undeformed shape."
                          % ", ".join("'%s'" % n for n in deform_after),
                          object_name=o.name,
                          hint="Move the Collision modifier to the bottom of "
                               "the stack."))
    if not out and any_col:
        return [mk(Status.PASS, "Collision modifiers sit below any deformers.")]
    return out


# -------------------------------------------------------------------- 15 ----
@check(15, "Cloth pin group empty or missing", GROUP_SETUP)
def c15_cloth_pin_group(ctx, mk):
    out = []
    any_pin = False
    for o in ctx.scene.objects:
        for m in o.modifiers:
            if m.type != "CLOTH":
                continue
            st = m.settings
            grp = getattr(st, "vertex_group_mass", "")
            if not grp:
                continue
            any_pin = True
            exists, count = util.vertex_group_count(o, grp)
            if not exists:
                out.append(mk(Status.FAIL,
                              "Cloth pin group '%s' is set but that vertex group "
                              "does not exist. The cloth will fall." % grp,
                              object_name=o.name,
                              hint="Pick an existing group, or clear the Pinning "
                                   "group in Cloth > Shape."))
            elif count == 0:
                out.append(mk(Status.FAIL,
                              "Cloth pin group '%s' exists but has no weighted "
                              "vertices, so nothing is pinned." % grp,
                              object_name=o.name,
                              hint="Assign vertices to the pin group, or clear it."))
            elif count is None:
                out.append(mk(Status.UNKNOWN,
                              "Cloth pin group '%s' could not be inspected." % grp,
                              object_name=o.name))
    if not out and any_pin:
        return [mk(Status.PASS, "Cloth pin groups contain pinned vertices.")]
    return out


# -------------------------------------------------------------------- 16 ----
@check(16, "Fluid flow/effector outside the domain, or domain with no flow", GROUP_SETUP)
def c16_fluid_layout(ctx, mk):
    scene = ctx.scene
    out = []
    domains = []
    flows = []        # genuine FLOW sources (inflow/outflow/geometry)
    effectors = []    # EFFECTOR objects (colliders/guides) — NOT a source
    for o in scene.objects:
        for m in o.modifiers:
            if m.type == "FLUID":
                ft = getattr(m, "fluid_type", "")
                if ft == "DOMAIN":
                    domains.append(o)
                elif ft == "FLOW":
                    flows.append(o)
                elif ft == "EFFECTOR":
                    effectors.append(o)
    if not domains:
        return []

    def world_aabb(obj):
        cs = util.world_bbox_corners(obj)
        mn = Vector((min(c.x for c in cs), min(c.y for c in cs), min(c.z for c in cs)))
        mx = Vector((max(c.x for c in cs), max(c.y for c in cs), max(c.z for c in cs)))
        return mn, mx

    def overlaps_domain(dmn, dmx, obj):
        fmn, fmx = world_aabb(obj)
        return (fmx.x >= dmn.x and fmn.x <= dmx.x and
                fmx.y >= dmn.y and fmn.y <= dmx.y and
                fmx.z >= dmn.z and fmn.z <= dmx.z)

    for dom in domains:
        dmn, dmx = world_aabb(dom)
        # A domain needs a genuine FLOW source. Effectors alone can't fill it.
        if not flows:
            if effectors:
                out.append(mk(Status.WARNING,
                              "Fluid domain has effector object(s) but no Flow "
                              "source, so nothing is emitted; the simulation will "
                              "be empty.",
                              object_name=dom.name,
                              hint="Add an Inflow/Flow object inside the domain."))
            else:
                out.append(mk(Status.WARNING,
                              "Fluid domain has no Flow objects; the simulation "
                              "will be empty.",
                              object_name=dom.name,
                              hint="Add an Inflow or Flow object inside the domain."))
            continue
        any_flow_inside = False
        for fo in flows:
            inside = overlaps_domain(dmn, dmx, fo)
            any_flow_inside = any_flow_inside or inside
            if not inside:
                out.append(mk(Status.WARNING,
                              "Flow object '%s' is fully outside the fluid domain "
                              "and won't contribute." % fo.name,
                              object_name=fo.name,
                              hint="Move it inside the domain box."))
        for eo in effectors:
            if not overlaps_domain(dmn, dmx, eo):
                out.append(mk(Status.WARNING,
                              "Effector object '%s' is fully outside the fluid "
                              "domain and has no effect." % eo.name,
                              object_name=eo.name,
                              hint="Move it inside the domain box."))
        if not any_flow_inside:
            out.append(mk(Status.WARNING,
                          "No Flow source overlaps this domain; the sim will be "
                          "empty.",
                          object_name=dom.name))
    if not out and domains:
        return [mk(Status.PASS, "Fluid flow objects sit inside their domain.")]
    return out
