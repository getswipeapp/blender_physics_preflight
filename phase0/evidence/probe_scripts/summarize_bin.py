import json, sys, os
O = sys.argv[1]
def L(c):
    try: return json.load(open(f"{O}/report_{c}.json"))[c]
    except Exception as e: return {"EXCEPTION": repr(e)}
out = {}
for c in ["cloth_disk", "softbody_disk"]:
    r = L(c); a = r.get("after_files_deleted_and_reload", {})
    out[c] = f"files deleted={r.get('cache_dir_deleted')} -> is_baked={a.get('is_baked')} info='{a.get('info')}'"
for c in ["cloth_memory", "softbody_memory"]:
    r = L(c); out[c] = f"is_baked={r.get('after_bake',{}).get('is_baked')} info='{r.get('after_bake',{}).get('info')}'"
r = L("rigid"); out["rigid"] = f"baked={r.get('after_bake',{}).get('is_baked')} reload is_outdated={r.get('after_reload',{}).get('is_outdated')}"
r = L("particles"); out["particles"] = f"baked={r.get('after_bake',{}).get('is_baked')} files={len(r.get('files',[]))}+"
fb = L("fluid_bake"); fd = L("fluid_after_delete")
out["fluid_ALL"] = f"bake files={fb.get('file_count')} baked_flag={fb.get('after_bake',{}).get('has_cache_baked_data')} | after delete+reopen: files={len(fd.get('files_after_reopen',[]))} baked_flag={fd.get('reloaded',{}).get('has_cache_baked_data')}"
g = L("geometry_nodes"); out["gn_disk"] = f"bake={g.get('bake_result')} files={g.get('n_files')} target={g.get('modifier_bake_target')}"
gp = open(f"{O}/gn_packed.txt").read()
out["gn_packed"] = ("no bake_target (4.2)" if not gp.strip() else ("NO python-visible change" if '"diff": {}' in gp else gp[:200]))
ea = open(f"{O}/extra_api.txt").read(); out["extra_api_missing"] = ea[ea.find('"missing"'):][:60] if ea else "n/a"
out["setup_probe"] = "ok" if "SETUPJSON" in open(f"{O}/setup_probe.txt").read() else "FAIL"
for k, v in out.items(): print(f"  {k:16} {v}")
