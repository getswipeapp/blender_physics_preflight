import json, sys, os
V = sys.argv[1]; D = os.path.join(os.path.dirname(__file__), "..", "out", V)
def L(c):
    try: return json.load(open(f"{D}/report_{c}.json"))[c]
    except Exception as e: return {"EXCEPTION": repr(e)}
K = ["is_baked", "is_outdated", "use_disk_cache", "info"]
f = lambda d: {k: d.get(k) for k in K}
print("#", V)
for c in ["cloth_memory", "cloth_disk", "softbody_memory", "softbody_disk"]:
    r = L(c)
    if "EXCEPTION" in r: print(c, "EXC", str(r["EXCEPTION"])[-200:]); continue
    print(c, "| baked:", f(r["after_bake"]), "| files deleted+reload:", f(r["after_files_deleted_and_reload"]))
r = L("rigid"); print("rigid", f(r.get("after_bake", {})), "reload:", f(r.get("after_reload", {})))
r = L("particles"); print("particles", f(r.get("after_bake", {})))
for c in ["fluid_bake", "fluid_inspect", "fluid_after_delete"]:
    r = L(c); d = r.get("after_bake") or r.get("reloaded") or {}
    print(c, {k: d.get(k) for k in ["has_cache_baked_data", "has_cache_baked_any", "cache_type"]}, "files:", r.get("file_count", r.get("cache_dir_exists")), str(r.get("EXCEPTION", ""))[-150:])
r = L("geometry_nodes")
print("GN modprops:", [p for p in r.get("modifier_props", []) if "bake" in p])
print("GN bake keys:", list((r.get("after_bake") or [{}])[0].keys()), "target:", r.get("modifier_bake_target"), r.get("set_target_err"), "n_files:", r.get("n_files"), "bake:", r.get("bake_result"), str(r.get("bake_err", ""))[:200])
