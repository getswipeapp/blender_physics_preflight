import sys as _s
ARGV = _s.argv[_s.argv.index("--")+1:] if "--" in _s.argv else _s.argv[1:]
import bpy, json
T=bpy.types
def has(cls,prop): return prop in {p.identifier for p in getattr(T,cls).bl_rna.properties}
q={"RigidBodyConstraint":["object1","object2","enabled","type"],
   "RigidBodyObject":["collision_margin","use_margin","kinematic","mesh_source","use_deform"],
   "CollisionSettings":["thickness_outer","use","damping","use_culling"],
   "ClothSettings":["vertex_group_mass","quality","mass","use_pressure","shrink_min"],
   "ClothCollisionSettings":["distance_min","self_distance_min","collision_quality","collection"],
   "SoftBodySettings":["use_goal","vertex_group_goal","mass","ball_size"],
   "FluidDomainSettings":["resolution_max","cache_type","cache_directory"],
   "FluidFlowSettings":["flow_type","flow_behavior","use_plane_init","subframes"],
   "RenderSettings":["fps","fps_base"],
   "UnitSettings":["scale_length","system"],
   "PointCache":["use_external","use_library_path","name","index","frame_step"]}
print("EXTRAJSON",json.dumps({"v":bpy.app.version_string,"missing":{c:[p for p in ps if not has(c,p)] for c,ps in q.items()}}))
