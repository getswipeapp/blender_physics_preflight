import sys as _s
ARGV = _s.argv[_s.argv.index("--")+1:] if "--" in _s.argv else _s.argv[1:]
import bpy, sys, os, json
OUT = ARGV[0]; os.makedirs(OUT, exist_ok=True)
bpy.ops.wm.read_factory_settings(use_empty=True)
sc = bpy.context.scene; sc.frame_start, sc.frame_end = 1, 10
bpy.ops.mesh.primitive_cube_add(); ob = bpy.context.active_object
ng = bpy.data.node_groups.new("Sim", "GeometryNodeTree")
ng.interface.new_socket("Geometry", in_out="INPUT", socket_type="NodeSocketGeometry")
ng.interface.new_socket("Geometry", in_out="OUTPUT", socket_type="NodeSocketGeometry")
gi = ng.nodes.new("NodeGroupInput"); go = ng.nodes.new("NodeGroupOutput")
si = ng.nodes.new("GeometryNodeSimulationInput"); so = ng.nodes.new("GeometryNodeSimulationOutput")
si.pair_with_output(so); ng.links.new(gi.outputs[0], si.inputs[0]); ng.links.new(si.outputs[1], so.inputs[1]); ng.links.new(so.outputs[0], go.inputs[0])
mod = ob.modifiers.new("GN", "NODES"); mod.node_group = ng
mod.bake_target = "PACKED"
bpy.ops.wm.save_as_mainfile(filepath=os.path.join(OUT, "gn_packed_unbaked.blend"))
def snap():
    b = mod.bakes[0]
    d = {p.identifier: str(getattr(b, p.identifier)) for p in b.bl_rna.properties if p.identifier != "rna_type"}
    d["_dir"] = [x for x in dir(b) if not x.startswith("_")]
    return d
pre = snap()
with bpy.context.temp_override(scene=sc, active_object=ob, object=ob, selected_objects=[ob]):
    res = list(bpy.ops.object.simulation_nodes_cache_bake(selected=False))
post = snap()
bpy.ops.wm.save_as_mainfile(filepath=os.path.join(OUT, "gn_packed_baked.blend"))
sz = {f: os.path.getsize(os.path.join(OUT, f)) for f in os.listdir(OUT) if f.endswith(".blend")}
diff = {k: (pre[k], post[k]) for k in pre if pre[k] != post[k]}
print("GNJSON", json.dumps({"v": bpy.app.version_string, "bake": res, "diff": diff, "sizes": sz, "dir": post["_dir"], "files_on_disk": [r for r, _, f in os.walk(OUT) if f and r != OUT]}))
