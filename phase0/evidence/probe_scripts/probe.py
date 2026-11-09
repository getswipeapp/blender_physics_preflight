"""Phase-0 feasibility probe: what can Blender's Python API tell us about
simulation caches?  Runs against the `bpy` module (real Blender build).
Usage: python probe.py <outdir>
"""
import json, os, sys, glob, shutil, traceback
import faulthandler; faulthandler.enable()
import sys as _s
ARGV = _s.argv[_s.argv.index("--")+1:] if "--" in _s.argv else _s.argv[1:]
import bpy

OUT = os.path.abspath(ARGV[0])
ONLY = ARGV[1] if len(ARGV) > 1 else None
os.makedirs(OUT, exist_ok=True)
R = {"blender_version": bpy.app.version_string}


def rna_props(cls):
    try:
        return sorted(p.identifier for p in cls.bl_rna.properties if p.identifier != "rna_type")
    except Exception as e:
        return "ERR %r" % e


T = bpy.types
R["rna"] = {
    n: rna_props(getattr(T, n)) for n in
    ["PointCache", "RigidBodyWorld", "FluidDomainSettings", "NodesModifierBake",
     "NodesModifier", "ClothCollisionSettings", "CollisionSettings", "RigidBodyObject",
     "ParticleSystem"] if hasattr(T, n)
}


def reset():
    bpy.ops.wm.read_factory_settings(use_empty=True)


def ptc(pc):
    d = {}
    for k in ["is_baked", "is_baking", "is_outdated", "is_frame_skip", "use_disk_cache",
              "use_external", "use_library_path", "frame_start", "frame_end", "name",
              "filepath", "index", "info", "compression"]:
        if hasattr(pc, k):
            v = getattr(pc, k)
            d[k] = v if isinstance(v, (int, float, str, bool)) else str(v)
    return d


def ls(d):
    out = []
    for root, _, files in os.walk(d):
        for f in files:
            p = os.path.join(root, f)
            out.append((os.path.relpath(p, d), os.path.getsize(p)))
    return sorted(out)


def step(name, fn):
    if ONLY and name != ONLY:
        return
    try:
        R[name] = fn()
    except Exception:
        R[name] = {"EXCEPTION": traceback.format_exc()[-1500:]}


def ctx_override(obj=None):
    win = bpy.context.window_manager.windows[0] if bpy.context.window_manager.windows else None
    d = {"scene": bpy.context.scene}
    if obj is not None:
        d["active_object"] = obj
        d["object"] = obj
    return d


def bake_point_cache(pc, obj=None):
    """Try several ways of baking a single point cache headlessly."""
    with bpy.context.temp_override(point_cache=pc, **ctx_override(obj)):
        return list(bpy.ops.ptcache.bake(bake=True))


# ---------------------------------------------------------------- cloth -----
def cloth_case(use_disk, kind="CLOTH"):
    reset()
    sc = bpy.context.scene
    sc.frame_start, sc.frame_end = 1, 20
    bpy.ops.mesh.primitive_plane_add(size=2, location=(0, 0, 2))
    ob = bpy.context.active_object
    ob.modifiers.new("Cloth", kind)
    pc = ob.modifiers["Cloth"].point_cache
    pc.frame_start, pc.frame_end = 1, 10   # deliberately shorter than render range
    blend = os.path.join(OUT, "%s_disk%d.blend" % (kind.lower(), use_disk))
    bpy.ops.wm.save_as_mainfile(filepath=blend)
    pc.use_disk_cache = use_disk
    oname = ob.name
    before = ptc(pc)
    res = bake_point_cache(pc, ob)
    after = ptc(pc)
    bpy.ops.wm.save_mainfile()
    files = ls(OUT)
    # reload from disk and see what persists
    bpy.ops.wm.open_mainfile(filepath=blend)
    pc2 = bpy.data.objects[oname].modifiers["Cloth"].point_cache
    reloaded = ptc(pc2)
    # now delete disk files and reload
    cachedir = os.path.join(OUT, "blendcache_%s_disk%d" % (kind.lower(), use_disk))
    deleted = os.path.isdir(cachedir)
    if deleted:
        shutil.rmtree(cachedir)
    bpy.ops.wm.open_mainfile(filepath=blend)
    pc3 = bpy.data.objects[oname].modifiers["Cloth"].point_cache
    after_delete = ptc(pc3)
    return {"bake_result": res, "before": before, "after_bake": after, "files": files,
            "after_reload": reloaded, "cache_dir_deleted": deleted,
            "after_files_deleted_and_reload": after_delete}


step("cloth_memory", lambda: cloth_case(False))
step("cloth_disk", lambda: cloth_case(True))
step("softbody_disk", lambda: cloth_case(True, "SOFT_BODY"))
step("softbody_memory", lambda: cloth_case(False, "SOFT_BODY"))


# ------------------------------------------------------------ rigid body ---
def rigid_case():
    reset()
    sc = bpy.context.scene
    sc.frame_start, sc.frame_end = 1, 30
    bpy.ops.mesh.primitive_cube_add(location=(0, 0, 3))
    ob = bpy.context.active_object
    with bpy.context.temp_override(**ctx_override(ob), selected_objects=[ob]):
        bpy.ops.rigidbody.object_add()
    rbw = sc.rigidbody_world
    pc = rbw.point_cache
    pc.frame_end = 30
    blend = os.path.join(OUT, "rigid.blend")
    bpy.ops.wm.save_as_mainfile(filepath=blend)
    d = {"has_use_disk_cache_attr": hasattr(pc, "use_disk_cache"), "before": ptc(pc)}
    d["note"] = "setting rigid-body point_cache.use_disk_cache=True segfaulted Blender 4.2.23; not attempted"
    try:
        with bpy.context.temp_override(point_cache=pc, scene=sc):
            d["bake_result"] = list(bpy.ops.ptcache.bake(bake=True))
    except Exception as e:
        d["bake_err"] = repr(e)
    d["after_bake"] = ptc(pc)
    bpy.ops.wm.save_mainfile()
    d["files"] = ls(OUT)
    bpy.ops.wm.open_mainfile(filepath=blend)
    d["after_reload"] = ptc(bpy.context.scene.rigidbody_world.point_cache)
    d["world_props"] = {k: str(getattr(bpy.context.scene.rigidbody_world, k)) for k in
                        ["enabled", "substeps_per_frame", "solver_iterations", "time_scale",
                         "use_split_impulse", "collection"] if hasattr(bpy.context.scene.rigidbody_world, k)}
    return d


step("rigid", rigid_case)


# ----------------------------------------------------------------- fluid ---
FLUID_KEYS = None


def fluid_snap(ds):
    keys = sorted(k for k in dir(ds) if k.startswith(("has_cache", "cache_")))
    return {k: str(getattr(ds, k)) for k in keys}


def fluid_bake():
    reset()
    sc = bpy.context.scene
    sc.frame_start, sc.frame_end = 1, 6
    bpy.ops.mesh.primitive_cube_add(size=2)
    dom = bpy.context.active_object
    dom.name = "Domain"
    m = dom.modifiers.new("Fluid", "FLUID")
    m.fluid_type = "DOMAIN"
    ds = m.domain_settings
    ds.domain_type = "GAS"
    ds.resolution_max = 16
    ds.cache_frame_start, ds.cache_frame_end = 1, 4
    bpy.ops.mesh.primitive_uv_sphere_add(radius=0.3, location=(0, 0, -0.5))
    fl = bpy.context.active_object
    f = fl.modifiers.new("Fluid", "FLUID")
    f.fluid_type = "FLOW"
    f.flow_settings.flow_type = "SMOKE"
    f.flow_settings.flow_behavior = "INFLOW"
    blend = os.path.join(OUT, "fluid.blend")
    bpy.ops.wm.save_as_mainfile(filepath=blend)
    ds.cache_directory = "//fluid_cache"
    ds.cache_type = os.environ.get("FLUID_CACHE_TYPE", "REPLAY")
    bpy.ops.wm.save_mainfile()
    d = {"before": fluid_snap(ds), "cache_type_requested": ds.cache_type}
    with bpy.context.temp_override(**ctx_override(dom)):
        d["bake_result"] = list(bpy.ops.fluid.bake_all())
    d["after_bake"] = fluid_snap(ds)
    bpy.ops.wm.save_mainfile()
    d["file_count"] = len(ls(os.path.join(OUT, "fluid_cache")))
    d["files_sample"] = ls(os.path.join(OUT, "fluid_cache"))[:40]
    return d


def fluid_inspect():
    bpy.ops.wm.open_mainfile(filepath=os.path.join(OUT, "fluid.blend"))
    ds = bpy.data.objects["Domain"].modifiers["Fluid"].domain_settings
    return {"reloaded": fluid_snap(ds), "files_now": ls(os.path.join(OUT, "fluid_cache")),
            "cache_dir_exists": os.path.isdir(os.path.join(OUT, "fluid_cache")),
            "abs_dir": bpy.path.abspath(ds.cache_directory)}


def fluid_delete_files():
    shutil.rmtree(os.path.join(OUT, "fluid_cache"), ignore_errors=True)
    r = fluid_inspect()
    r["files_after_reopen"] = ls(os.path.join(OUT, "fluid_cache"))
    return r


step("fluid_bake", fluid_bake)
step("fluid_inspect", fluid_inspect)
step("fluid_after_delete", fluid_delete_files)



# ------------------------------------------------------------- particles ---
def particle_case():
    reset()
    sc = bpy.context.scene
    sc.frame_start, sc.frame_end = 1, 20
    bpy.ops.mesh.primitive_plane_add()
    ob = bpy.context.active_object
    ob.modifiers.new("P", "PARTICLE_SYSTEM")
    ps = ob.particle_systems[0]
    pc = ps.point_cache
    blend = os.path.join(OUT, "particles.blend")
    bpy.ops.wm.save_as_mainfile(filepath=blend)
    pc.use_disk_cache = True
    d = {"before": ptc(pc)}
    d["bake_result"] = bake_point_cache(pc, ob)
    d["after_bake"] = ptc(pc)
    bpy.ops.wm.save_mainfile()
    d["files"] = [f for f in ls(OUT) if "particles" in f[0]][:5]
    return d


step("particles", particle_case)


# ------------------------------------------------- geometry nodes sim zone --
def gn_case():
    reset()
    sc = bpy.context.scene
    sc.frame_start, sc.frame_end = 1, 10
    bpy.ops.mesh.primitive_cube_add()
    ob = bpy.context.active_object
    ng = bpy.data.node_groups.new("Sim", "GeometryNodeTree")
    if hasattr(ng, "interface"):
        ng.interface.new_socket("Geometry", in_out="INPUT", socket_type="NodeSocketGeometry")
        ng.interface.new_socket("Geometry", in_out="OUTPUT", socket_type="NodeSocketGeometry")
    gi = ng.nodes.new("NodeGroupInput")
    go = ng.nodes.new("NodeGroupOutput")
    si = ng.nodes.new("GeometryNodeSimulationInput")
    so = ng.nodes.new("GeometryNodeSimulationOutput")
    si.pair_with_output(so)
    ng.links.new(gi.outputs[0], si.inputs[0])
    ng.links.new(si.outputs[1], so.inputs[1])
    ng.links.new(so.outputs[0], go.inputs[0])
    mod = ob.modifiers.new("GN", "NODES")
    mod.node_group = ng
    blend = os.path.join(OUT, "gn.blend")
    bpy.ops.wm.save_as_mainfile(filepath=blend)
    d = {"modifier_props": rna_props(T.NodesModifier)}
    bakes = list(getattr(mod, "bakes", []))
    d["n_bakes"] = len(bakes)

    def bk():
        out = []
        for b in mod.bakes:
            e = {}
            for p in b.bl_rna.properties:
                if p.identifier == "rna_type":
                    continue
                v = getattr(b, p.identifier)
                e[p.identifier] = v if isinstance(v, (int, float, str, bool)) else str(v)
            out.append(e)
        return out
    d["before"] = bk()
    for target in ["DISK"]:
        try:
            mod.bake_target = target
            d["bake_target_set"] = target
        except Exception as e:
            d["set_target_err"] = repr(e)
        mod.bake_directory = "//gn_bake"
        try:
            with bpy.context.temp_override(**ctx_override(ob)):
                d["bake_result"] = list(bpy.ops.object.simulation_nodes_cache_bake(selected=False))
        except Exception as e:
            d["bake_err"] = repr(e)
    d["after_bake"] = bk()
    d["modifier_bake_target"] = getattr(mod, "bake_target", "n/a")
    bpy.ops.wm.save_mainfile()
    d["files"] = ls(os.path.join(OUT, "gn_bake"))[:10]
    d["n_files"] = len(ls(os.path.join(OUT, "gn_bake")))
    return d


step("geometry_nodes", gn_case)

with open(os.path.join(OUT, "report_%s.json" % (ONLY or "all")), "w") as fh:
    json.dump(R, fh, indent=1, default=str)
print("WROTE", os.path.join(OUT, "report.json"))
