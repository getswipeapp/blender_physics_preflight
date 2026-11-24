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

# The shared certification verdict helpers live in tests/gate_check.py; reuse
# valid_cli_report so the Windows CLI acceptance uses the exact same fail-closed
# report check the suite regression-tests (R20-1).
REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if os.path.join(REPO, "tests") not in sys.path:
    sys.path.insert(0, os.path.join(REPO, "tests"))
import gate_check

MOD = "bl_ext.user_default.failsafe"
results = []  # (name, ok, detail)

# R19-2: the acceptance run declares its own fixed inventory, independent of what
# actually ran, exactly like the main suite (R18-1). The success path performs
# this many checks; a run that reaches the summary with a different count (e.g. a
# 0/0/0 or a short early-return run) emits ok=no and the gate rejects it, so the
# ", 0 failed," marker can no longer bless a shortened acceptance. Re-baseline by
# counting the check() calls on the success path if acceptance checks change.
# R21 added two CLI regressions (crash-after-write; zero-result scan) and reworked
# the clean-scan check, taking the success-path count from 26 to 28.
EXPECTED_ACCEPT_CHECKS = 28


def _safe(detail):
    """Redact crash-signature substrings from a diagnostic string before it is
    printed. A PASSING crash/exit-0 regression legitimately REPORTS that it found
    a traceback; echoing the raw signature verbatim would otherwise plant it in
    the acceptance log, where the gate's own log-level crash-signature scan would
    then (falsely) reject the whole run. Keeps the gate's safety net intact while
    letting the regression say what it caught."""
    s = str(detail)
    for sig in gate_check.CRASH_SIGNATURES:
        s = s.replace(sig, sig.split()[0] + "<redacted>")
    return s


def check(name, ok, detail=""):
    detail = _safe(detail)
    results.append((name, bool(ok), detail[:120]))
    print(("PASS" if ok else "FAIL"), "-", name, "::", detail[:120])


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
    check("27 checks registered", len(eng.CHECKS) == 27, len(eng.CHECKS))
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

    # --- B2: direct CAPTURE must NOT force an overwrite (review blocker) -----
    # A baseline exists now; a direct (EXEC_DEFAULT) cache-hash CAPTURE without the
    # overwrite opt-in must refuse and leave the sidecar byte-identical.
    hb2 = sha(bpath)
    rc = bpy.ops.failsafe.cache_hash('EXEC_DEFAULT', mode='CAPTURE',
                                     overwrite=False)
    check("B2: direct CAPTURE refuses silent overwrite (CANCELLED + preserved)",
          "CANCELLED" in rc and sha(bpath) == hb2, list(rc))

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
    check("Export JSON has 27 checks", len(jd.get("checks", [])) == 27, len(jd.get("checks", [])))

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

    # R20-1 / R21: a clean CLI scan must prove it ACTUALLY RAN, not merely that
    # the child exited 0. On this Blender a --python-expr child that raises still
    # exits 0, so the exit code cannot stand in for "the scan produced a report".
    # Run the scanner in a real child, open the real cloth fixture so checks
    # actually execute, capture its JSON report AND the child's real process
    # result, and require a complete, EXECUTED 27-check report via the shared
    # gate_check.valid_cli_report.
    def cli_json_child(body_expr, open_blend=None):
        jp = os.path.join(d, "cli_report.json")
        cp = jp + ".code"
        # Clear BOTH the report and the exit-code sidecar first, so a stale file
        # from a previous child can never stand in for this one's result (a child
        # that writes neither must read back as rc=None / empty, not a cached 0).
        for f in (jp, cp):
            try:
                os.remove(f)
            except OSError:
                pass
        cmd = [binp, "-b"]
        if open_blend:
            cmd.append(open_blend)  # Blender opens it before --python-expr runs
        cmd += ["--python-expr", body_expr % jp]
        # R21-1: capture subprocess.run's REAL result. The parent used to discard
        # it and trust only the child-written sidecar, so a child that wrote code=0
        # and then crashed (leaving a traceback on stderr, Blender still exiting 0)
        # was accepted. Return the real returncode and combined stdout+stderr too.
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
        raw = ""
        if os.path.isfile(jp):
            with open(jp, encoding="utf-8") as fh:
                raw = fh.read()
        declared = None
        if os.path.isfile(cp):
            try:
                declared = int(open(cp).read().strip())
            except ValueError:
                declared = None
        child_out = (p.stdout or "") + "\n" + (p.stderr or "")
        return p.returncode, declared, raw, child_out

    scan_expr = ("import sys; import bl_ext.user_default.failsafe.cli as c; "
                 "jp = r'%s'; code, out = c.run(['--json']); "
                 "open(jp, 'w', encoding='utf-8').write(out); "
                 "open(jp + '.code', 'w').write(str(code)); "
                 "sys.exit(code)")
    # Scan the REAL saved fixture (a cloth object), so checks genuinely execute
    # and the report carries non-N/A results. A defined scan verdict (clean /
    # blocking / unverified = 0/1/2) is accepted; the exit code is only a sanity
    # cross-check, the complete executed report is the proof (R21-2).
    rc_ok, decl_ok, raw_ok, out_ok = cli_json_child(scan_expr, open_blend=blend)
    v_ok = gate_check.valid_cli_report(rc_ok, raw_ok, child_stderr=out_ok,
                                       declared_code=decl_ok,
                                       allowed_codes=(0, 1, 2))
    check("CLI scan of the real fixture -> a complete, EXECUTED 27-check report (R21-2)",
          v_ok.ok, "rc=%s executed=%s findings=%s; %s"
          % (rc_ok, v_ok.info.get("executed"), v_ok.info.get("findings"),
             "; ".join(v_ok.reasons) or "ok"))

    # Real child-failure repro (R20-1): a child that exits 0 but produces NO
    # report (the crash-exit-0 class) must be REJECTED by the very same gate.
    bad_expr = "import sys; jp = r'%s'; sys.exit(0)  # report intentionally unwritten"
    rc_bad, decl_bad, raw_bad, out_bad = cli_json_child(bad_expr)
    v_bad = gate_check.valid_cli_report(rc_bad, raw_bad, child_stderr=out_bad,
                                        declared_code=decl_bad,
                                        allowed_codes=(0, 1, 2))
    check("CLI child that exits 0 with no report is REJECTED by the gate (R20-1)",
          not v_bad.ok, "rc=%s raw=%dB -> %s"
          % (rc_bad, len(raw_bad), "; ".join(v_bad.reasons)))

    # R21-1 repro: a child that writes a VALID executed report AND code=0, then
    # raises. Blender still exits 0 and the sidecar says 0, so the old
    # sidecar-only check would PASS it; the gate must REJECT it on the traceback
    # left in the child's (previously discarded) stderr and/or the real exit.
    crash_expr = ("import sys; import bl_ext.user_default.failsafe.cli as c; "
                  "jp = r'%s'; code, out = c.run(['--json']); "
                  "open(jp, 'w', encoding='utf-8').write(out); "
                  "open(jp + '.code', 'w').write('0'); "
                  "raise RuntimeError('boom AFTER writing a valid report + code=0')")
    rc_cr, decl_cr, raw_cr, out_cr = cli_json_child(crash_expr, open_blend=blend)
    v_cr = gate_check.valid_cli_report(rc_cr, raw_cr, child_stderr=out_cr,
                                       declared_code=decl_cr,
                                       allowed_codes=(0, 1, 2))
    check("CLI child that writes a valid report+code=0 then CRASHES is REJECTED (R21-1)",
          not v_cr.ok, "rc=%s declared=%s -> %s"
          % (rc_cr, decl_cr, "; ".join(v_cr.reasons)))

    # R21-2 repro: force engine.run_all() to return [] in the child. The CLI then
    # emits a 27-entry report that is ALL "NOT APPLICABLE" (the static registry)
    # and exits 0 — a zero-result scan. The gate must REJECT it for lack of
    # execution evidence, even though it has 27 checks and a non-empty summary.
    empty_expr = ("import sys; "
                  "import bl_ext.user_default.failsafe.engine as e; "
                  "e.run_all = (lambda *a, **k: []); "
                  "import bl_ext.user_default.failsafe.cli as c; "
                  "jp = r'%s'; code, out = c.run(['--json']); "
                  "open(jp, 'w', encoding='utf-8').write(out); "
                  "open(jp + '.code', 'w').write(str(code)); "
                  "sys.exit(code)")
    rc_em, decl_em, raw_em, out_em = cli_json_child(empty_expr, open_blend=blend)
    v_em = gate_check.valid_cli_report(rc_em, raw_em, child_stderr=out_em,
                                       declared_code=decl_em,
                                       allowed_codes=(0, 1, 2))
    check("CLI zero-result scan (run_all->[]) is an all-N/A report, REJECTED (R21-2)",
          not v_em.ok, "rc=%s executed=%s -> %s"
          % (rc_em, v_em.info.get("executed"), "; ".join(v_em.reasons)))

    _finish()


def _finish():
    npass = sum(1 for _, ok, _ in results if ok)
    nfail = sum(1 for _, ok, _ in results if not ok)
    total = len(results)
    print("\n" + "=" * 60)
    print("Windows functional acceptance: %d passed, %d failed, %d total"
          % (npass, nfail, total))
    if nfail:
        print("FAILURES:")
        for n, ok, det in results:
            if not ok:
                print("  -", n, "::", det)
    # R19-2: independent inventory + completion sentinel, gated by
    # tests/gate_check.py --sentinel ACCEPT_DONE. A short run (early return, or a
    # 0/0/0 run) has total != EXPECTED_ACCEPT_CHECKS -> ok=no -> gate rejects,
    # even though "0 failed" would otherwise satisfy a bare marker check.
    consistent = (npass + nfail == total) and total > 0
    inventory_ok = (total == EXPECTED_ACCEPT_CHECKS)
    ok_overall = (nfail == 0) and consistent and inventory_ok
    if not inventory_ok:
        print("ACCEPT INVENTORY MISMATCH (R19-2): ran %d != declared %d"
              % (total, EXPECTED_ACCEPT_CHECKS))
    ver_token = "%d.%d.%d" % tuple(bpy.app.version)
    print("ACCEPT_DONE version=%s passed=%d failed=%d total=%d expected=%d "
          "consistent=%s ok=%s"
          % (ver_token, npass, nfail, total, EXPECTED_ACCEPT_CHECKS,
             "yes" if consistent else "no", "yes" if ok_overall else "no"))
    sys.exit(0 if ok_overall else 1)


if __name__ == "__main__":
    main()
