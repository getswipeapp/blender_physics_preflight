# SPDX-License-Identifier: GPL-3.0-or-later
"""Windows functional acceptance (HEADLESS) for the INSTALLED Failsafe extension.

This is NOT a GUI acceptance test — it exercises the add-on's real operators and
code paths headlessly on Windows, to prove installation, registration, the
external baseline, JSON export, "Couldn't verify" wording, CLI exit codes (via a
real child process) and read-only safety all work with Windows paths.

Run WITHOUT --factory-startup so the installed extension is enabled:
  blender -b -P certification/ci/win_acceptance.py

Exits 0 if every check passes, 1 otherwise. Uses only disposable fixtures in a
temp dir.
"""
import hashlib
import json
import os
import subprocess
import sys
import tempfile

import bpy

MOD = "bl_ext.user_default.failsafe"
results = []  # (name, ok, detail)


def check(name, ok, detail=""):
    results.append((name, bool(ok), str(detail)[:120]))
    print(("PASS" if ok else "FAIL"), "-", name, "::", str(detail)[:120])


def sha(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for ch in iter(lambda: f.read(65536), b""):
            h.update(ch)
    return h.hexdigest()


def main():
    print("Windows functional acceptance — Blender", bpy.app.version_string)
    print("Platform:", sys.platform, "| binary:", bpy.app.binary_path)

    # --- install / registration ---------------------------------------------
    # Ensure the installed extension is ENABLED in THIS (background) process, so
    # its register() runs and the operators exist. `blender -b` does not reliably
    # auto-enable it unless the installing process saved userprefs; enabling here
    # makes the check deterministic (a real GUI install enables it the same way).
    import addon_utils
    try:
        addon_utils.enable(MOD, default_set=False, persistent=True)
    except Exception as e:
        print("addon_utils.enable note:", repr(e))

    import importlib
    try:
        pkg = importlib.import_module(MOD)
        eng = importlib.import_module(MOD + ".engine")
        bl = importlib.import_module(MOD + ".baseline")
        installed = True
    except Exception as e:
        check("extension imports (installed+enabled)", False, repr(e))
        _finish()
        return
    check("extension imports (installed+enabled)", installed, os.path.dirname(pkg.__file__))
    check("26 checks registered", len(eng.CHECKS) == 26, len(eng.CHECKS))
    check("Save Baseline operator registered", hasattr(bpy.types, "FAILSAFE_OT_save_baseline"))
    check("Export JSON operator registered", hasattr(bpy.types, "FAILSAFE_OT_export_json"))
    check('label(UNKNOWN) == "Couldn\'t verify"',
          eng.label(eng.Status.UNKNOWN) == "Couldn't verify",
          eng.label(eng.Status.UNKNOWN))

    # --- disposable cloth fixture, saved to a temp .blend -------------------
    # NB: never read_factory_settings here — it resets preferences and DISABLES
    # the installed extension. Just clear the current scene's objects instead.
    d = tempfile.mkdtemp(prefix="failsafe_win_")
    for o in list(bpy.data.objects):
        bpy.data.objects.remove(o, do_unlink=True)
    me = bpy.data.meshes.new("ClothM")
    ob = bpy.data.objects.new("Cloth", me)
    bpy.context.scene.collection.objects.link(ob)
    mod = ob.modifiers.new(name="Cloth", type="CLOTH")
    blend = os.path.join(d, "win fixture.blend")
    bpy.ops.wm.save_as_mainfile(filepath=blend)
    check("saved disposable .blend (Windows path)", os.path.isfile(blend), blend)

    # --- external baseline: create, .blend untouched, Windows path ----------
    bpath = bl.default_baseline_path()
    check("baseline path is next to the .blend (Windows)",
          bool(bpath) and bpath.endswith(".failsafe-baseline.json"), bpath)
    if os.path.isfile(bpath):
        os.remove(bpath)
    before = sha(blend)
    bpy.ops.failsafe.save_baseline('EXEC_DEFAULT', overwrite=False)
    after = sha(blend)
    check("Save Baseline created the external sidecar", os.path.isfile(bpath), bpath)
    check("Save Baseline left the .blend byte-identical", before == after)
    try:
        bdata = json.load(open(bpath))
        check("baseline JSON valid + schema recorded",
              bdata.get("kind") == "baseline" and "schema" in bdata, bdata.get("schema"))
    except Exception as e:
        check("baseline JSON valid + schema recorded", False, repr(e))

    # --- #26: PASS now, WARNING after a tracked setting changes -------------
    def worst26():
        res = eng.run_all(bpy.context)
        sev = {eng.Status.FAIL: 4, eng.Status.WARNING: 3, eng.Status.UNKNOWN: 2,
               eng.Status.NA: 1, eng.Status.PASS: 0}
        best = None
        for r in res:
            if r.check_id == 26 and (best is None or sev[r.status] > sev[best]):
                best = r.status
        return best
    check("#26 PASS right after Save Baseline", worst26() == eng.Status.PASS, worst26())
    mod.settings.mass = mod.settings.mass + 0.5
    check("#26 WARNING after a tracked setting change",
          worst26() == eng.Status.WARNING, worst26())

    # --- overwrite guard: no-overwrite preserves, overwrite replaces --------
    h0 = sha(bpath)
    r1 = bpy.ops.failsafe.save_baseline('EXEC_DEFAULT', overwrite=False)
    check("Save Baseline refuses silent overwrite (CANCELLED + preserved)",
          "CANCELLED" in r1 and sha(bpath) == h0, list(r1))
    r2 = bpy.ops.failsafe.save_baseline('EXEC_DEFAULT', overwrite=True)
    check("Save Baseline replaces on explicit overwrite",
          "FINISHED" in r2 and sha(bpath) != h0, list(r2))

    # --- Export JSON: valid, machine UNKNOWN kept, display word absent ------
    for t in list(bpy.data.texts):
        if t.name.startswith("failsafe_report"):
            bpy.data.texts.remove(t)
    bpy.ops.failsafe.export_json()
    txt = next((t for t in bpy.data.texts if t.name.startswith("failsafe_report")), None)
    blob = txt.as_string() if txt else ""
    try:
        jd = json.loads(blob)
        jok = True
    except Exception:
        jd, jok = {}, False
    check("Export JSON is valid JSON", jok)
    check("Export JSON keeps machine token UNKNOWN",
          "UNKNOWN" in (jd.get("summary") or {}))
    check("Export JSON never emits the display word 'Couldn't verify'",
          "Couldn't verify" not in blob)
    check("Export JSON has 26 checks", len(jd.get("checks", [])) == 26, len(jd.get("checks", [])))

    # --- "Couldn't verify" carries reason + next action --------------------
    os.remove(bpath)  # no baseline -> #26 UNKNOWN with reason+hint
    res = eng.run_all(bpy.context)
    u26 = [r for r in res if r.check_id == 26 and r.status == eng.Status.UNKNOWN]
    check("#26 'Couldn't verify' has reason + next action",
          bool(u26) and u26[0].message.strip() and (u26[0].hint or "").strip(),
          (u26[0].message[:40] if u26 else "no unknown"))

    # --- read-only: a scan writes no files, .blend unchanged ----------------
    before_files = set(os.listdir(d))
    hb = sha(blend)
    eng.run_all(bpy.context)
    check("ordinary scan writes no new files", set(os.listdir(d)) == before_files,
          sorted(set(os.listdir(d)) - before_files))
    check("ordinary scan leaves the .blend unchanged", sha(blend) == hb)

    # --- CLI exit codes via a REAL child process (Windows) ------------------
    binp = bpy.app.binary_path
    def cli_exit(args):
        expr = ("import bl_ext.user_default.failsafe.cli as c; c.main()")
        p = subprocess.run([binp, "-b", "--python-expr", expr, "--"] + args,
                           capture_output=True, text=True, timeout=180)
        return p.returncode
    check("CLI --help -> exit 3 (Windows)", cli_exit(["--help"]) == 3)
    check("CLI bad arg -> exit 3 (Windows)", cli_exit(["--nope"]) == 3)
    # empty factory scene -> clean -> exit 0
    check("CLI clean scan -> exit 0 (Windows)", cli_exit(["--text"]) == 0)

    _finish()


def _finish():
    nfail = sum(1 for _, ok, _ in results if not ok)
    print("\n" + "=" * 60)
    print("Windows functional acceptance: %d passed, %d failed, %d total"
          % (sum(1 for _, ok, _ in results if ok), nfail, len(results)))
    if nfail:
        print("FAILURES:")
        for n, ok, det in results:
            if not ok:
                print("  -", n, "::", det)
    sys.exit(1 if nfail else 0)


if __name__ == "__main__":
    main()
