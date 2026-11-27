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
# R22 added two more (partial scan; internal check error) -> 30.
# R23 added two more (invocation proof; omitted-invocation repro) -> 32.
# R24 added two more (child-invoked-only-subset; child-suppressed-results) -> 34.
# R25 replaced the count-based suppress check with exact-findings checks
# (status-substitution; incomplete per-id evidence) -> 35.
# R26 added three verdict-consistency repros (overall / per-check status /
# summary distribution lies) -> 38.
# R27 added a customer-facing display-lie repro -> 39.
# R28 added metadata-fail-closed + missing-field + blender/file provenance
# repros -> 43.
# R29 added file-identity (not basename) + absent-provenance + cache false-zero
# (real failure honesty + unverified-zero rejection) repros -> 47.
# R30 added cache size-measurement honesty (false-zero rejection; verified-total-
# over-unmeasured rejection; honest-unknown acceptance; honest two-axis schema) +
# _same_file missing-path identity repros -> 52.
# R31 added cache partial-measurement honesty: measured/unmeasured fields must
# agree with the item null-byte counts (two contradiction rejections + one honest
# partial-unknown acceptance), plus a direct installed cache_inspect size-helper
# repro (one/all per-file stat failures -> None; 0-byte -> measured zero) -> 56.
EXPECTED_ACCEPT_CHECKS = 56

# R22-1: the saved cloth fixture structurally guarantees these registered checks
# EXECUTE (reach a non-N/A verdict), so a scan that ran fewer (e.g. engine.run_all
# returning a single Result) is rejected — a 27-entry report never proves these
# ran. Grounded in the real CLI-child scan on 5.2.3, which executes
# {1, 7, 8, 9, 17, 26}; this is the stable, structurally-forced subset:
#   #1  Scale and rotation are applied   -> runs for every object
#   #7  Cloth/soft body has a collider   -> runs because the fixture has a CLOTH
#                                           modifier (proves the physics path ran)
#   #8  No negative or inherited scale   -> runs for every object
#   #26 Tracked settings vs baseline     -> always runs (UNKNOWN without a baseline)
CLOTH_REQUIRED_IDS = frozenset({1, 7, 8, 26})


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
        ip = jp + ".inv"
        # Clear the report, exit-code AND invocation sidecars first, so a stale
        # file from a previous child can never stand in for this one's result (a
        # child that writes none must read back as rc=None / empty / no evidence,
        # not a cached value).
        for f in (jp, cp, ip):
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
        # R24-1: the child's OWN execution evidence (ids it invoked + findings it
        # returned per check), recorded inside the SAME process that wrote the
        # report. None when the child did not write it.
        inv = None
        if os.path.isfile(ip):
            try:
                inv = json.load(open(ip, encoding="utf-8"))
            except Exception:
                inv = None
        child_out = (p.stdout or "") + "\n" + (p.stderr or "")
        return p.returncode, declared, raw, child_out, inv

    # R24-1 / R25-1: instrument the ACTUAL CLI child being certified. Before it
    # runs the scan, wrap every registered check function with a recorder that
    # notes (a) the check was invoked and (b) the EXACT findings it returned
    # ([status, object, message, hint] rows); after the scan write that evidence
    # to a <report>.inv sidecar. valid_cli_scan then certifies the report AND this
    # same-process evidence together, requiring complete per-id evidence and an
    # EXACT per-id findings match — a second independent scan can never stand in,
    # and a dropped or status-swapped finding is caught even when the count is
    # unchanged. ``attack`` runs before the scan (cripple run_all); ``post`` runs
    # after it (tamper with the recorded evidence) so a regression can prove the
    # gate catches each.
    def instrumented_expr(attack="", post=""):
        return (
            "import sys, json\n"
            "import bpy as _bpy\n"
            "import bl_ext.user_default.failsafe.engine as e\n"
            "_inv = []\n_ret = {}\n"
            "def _wrap(mid, fn):\n"
            "    def rec(ctx, mk):\n"
            "        _inv.append(mid)\n"
            "        out = fn(ctx, mk)\n"
            "        _ret[mid] = [[r.status, r.object_name, r.message, r.hint] "
            "for r in (out or [])]\n"
            "        return out\n"
            "    return rec\n"
            "for _m in e.CHECKS:\n    _m.func = _wrap(_m.id, _m.func)\n"
            + attack +
            "import bl_ext.user_default.failsafe.cli as c\n"
            "jp = r'%s'\n"
            "code, out = c.run(['--json'])\n"
            # R27-1: record the registry's CANONICAL per-check metadata — the
            # customer-facing display for each check's derived status, plus its
            # name/group — straight from the engine, so the gate can reject a
            # report whose display/name/group was rewritten to mislead.
            "_SEV = e.SEVERITY\n"
            "_meta = {}\n"
            "for _m in e.CHECKS:\n"
            "    _rows = _ret.get(_m.id, [])\n"
            "    _st = max((_r[0] for _r in _rows), key=lambda s: _SEV.get(s, -1)) "
            "if _rows else e.Status.NA\n"
            "    _meta[_m.id] = {'display': e.display_name(_m, _st), "
            "'name': _m.name, 'group': _m.group}\n"
            # R28-2: record the child's ACTUAL provenance (the Blender version and
            # the .blend it really had open), so the gate can reject a report that
            # claims a different version or file.
            "_prov = {'blender': _bpy.app.version_string, "
            "'file': _bpy.data.filepath or None}\n"
            + post +
            "open(jp, 'w', encoding='utf-8').write(out)\n"
            "open(jp + '.inv', 'w', encoding='utf-8').write("
            "json.dumps({'invoked': _inv, 'findings': _ret, 'meta': _meta, "
            "'provenance': _prov, 'schema': 1}))\n"
            "open(jp + '.code', 'w').write(str(code))\n"
            "sys.exit(code)\n")

    # A child run_all that INVOKES only {1,7,8,26}: the report still lists 27
    # entries, but the child recorded only 4 invocations.
    REDUCED_ATTACK = (
        "def _atk(context, hash_verify=None):\n"
        "    ctx = e.ScanContext(context, hash_verify=hash_verify)\n"
        "    out = []\n"
        "    for meta in e.CHECKS:\n"
        "        if meta.id in (1, 7, 8, 26):\n"
        "            r = meta.func(ctx, e._mk(meta))\n"
        "            if r: out.extend(r)\n"
        "    return out\n"
        "e.run_all = _atk\n")
    # A child run_all that invokes ALL 27 but SWAPS every WARNING finding to PASS
    # after the functions returned: same check ids, same finding counts, altered
    # statuses. The recorder captured the real WARNINGs, so the report disagrees.
    SUBSTITUTE_ATTACK = (
        "_orig = e.run_all\n"
        "def _sub(context, hash_verify=None):\n"
        "    out = _orig(context, hash_verify=hash_verify)\n"
        "    for r in out:\n"
        "        if r.status == e.Status.WARNING:\n"
        "            r.status = e.Status.PASS\n"
        "    return out\n"
        "e.run_all = _sub\n")
    # A child that invoked all 27 but DROPS its recorded evidence for every id
    # outside {1,7,8,26} after the scan: incomplete per-id evidence.
    MISSING_POST = (
        "for _k in list(_ret):\n"
        "    if _k not in (1, 7, 8, 26):\n        _ret.pop(_k)\n")
    # R26-1 tampers: keep the real findings + evidence, but rewrite the report's
    # top-level verdicts. Each must be caught because the verdicts are DERIVED from
    # the recorded findings and must match.
    OVERALL_LIE = ("import json as _j\n_d = _j.loads(out)\n"
                   "_d['overall'] = 'PASS'\nout = _j.dumps(_d)\n")
    STATUS_LIE = ("import json as _j\n_d = _j.loads(out)\n"
                  "for _c in _d['checks']:\n"
                  "    if _c.get('status') == 'WARNING':\n        _c['status'] = 'PASS'\n"
                  "out = _j.dumps(_d)\n")
    SUMMARY_LIE = ("import json as _j\n_d = _j.loads(out)\n_s = _d['summary']\n"
                   "_s['PASS'] = _s.get('PASS', 0) + _s.get('WARNING', 0)\n"
                   "_s['WARNING'] = 0\nout = _j.dumps(_d)\n")

    registry_ids = [m.id for m in eng.CHECKS]
    EXP_BLENDER = bpy.app.version_string

    def _evidence(inv):
        ids = list((inv or {}).get("invoked", []))
        finds = {int(k): v for k, v in (inv or {}).get("findings", {}).items()}
        meta = {int(k): v for k, v in (inv or {}).get("meta", {}).items()}
        prov = (inv or {}).get("provenance")
        return ids, finds, meta, prov

    # Certify in FULL certification mode: invocation, exact findings, verdict
    # consistency, registry metadata (require_meta -> fail CLOSED on missing
    # metadata), and provenance (the report's blender/file must match what the
    # child really ran and the intended fixture). R22..R28.
    def _certify(rc, decl, raw, out, inv, required_ids=None):
        ids_, finds_, meta_, prov_ = _evidence(inv)
        return gate_check.valid_cli_scan(
            rc, raw, ids_, finds_, registry_ids, child_stderr=out,
            declared_code=decl, allowed_codes=(0, 1, 2), required_ids=required_ids,
            report_meta=meta_, require_meta=True, provenance=prov_,
            expected_blender=EXP_BLENDER, expected_file=blend,
            require_provenance=True, require_cache_verified=True)

    rc_ok, decl_ok, raw_ok, out_ok, inv_ok = cli_json_child(instrumented_expr(),
                                                            open_blend=blend)
    v_ok = _certify(rc_ok, decl_ok, raw_ok, out_ok, inv_ok,
                    required_ids=CLOTH_REQUIRED_IDS)
    check("CLI child proof: invoked all 27 + exact findings + verdicts + display + "
          "provenance (R22..R28)",
          v_ok.ok, "rc=%s invoked=%s executed=%s missing_ev=%s mismatch=%s; %s"
          % (rc_ok, v_ok.info.get("invoked"), v_ok.info.get("executed"),
             v_ok.info.get("evidence_missing"), v_ok.info.get("findings_mismatch"),
             "; ".join(v_ok.reasons) or "ok"))

    # R24-1 repro: invoked only {1,7,8,26} -> rejected on its own evidence.
    rc_rd, decl_rd, raw_rd, out_rd, inv_rd = cli_json_child(
        instrumented_expr(REDUCED_ATTACK), open_blend=blend)
    v_rd = _certify(rc_rd, decl_rd, raw_rd, out_rd, inv_rd,
                    required_ids=CLOTH_REQUIRED_IDS)
    check("CLI child that INVOKED only {1,7,8,26} is REJECTED on its own evidence (R24-1)",
          not v_rd.ok, "invoked=%s -> %s"
          % (sorted(set(_evidence(inv_rd)[0])), "; ".join(v_rd.reasons)))

    # R25-1 repro B: WARNING finding swapped to PASS (same count) -> rejected.
    rc_su, decl_su, raw_su, out_su, inv_su = cli_json_child(
        instrumented_expr(SUBSTITUTE_ATTACK), open_blend=blend)
    v_su = _certify(rc_su, decl_su, raw_su, out_su, inv_su)
    check("CLI child that SWAPPED a WARNING finding to PASS (same count) is REJECTED (R25-1)",
          not v_su.ok, "mismatch=%s -> %s"
          % (v_su.info.get("findings_mismatch"), "; ".join(v_su.reasons)))

    # R25-1 repro A: findings evidence recorded for only {1,7,8,26} -> rejected.
    rc_mi, decl_mi, raw_mi, out_mi, inv_mi = cli_json_child(
        instrumented_expr(post=MISSING_POST), open_blend=blend)
    v_mi = _certify(rc_mi, decl_mi, raw_mi, out_mi, inv_mi)
    check("CLI child with incomplete per-check findings evidence is REJECTED (R25-1)",
          not v_mi.ok, "missing_ev=%s -> %s"
          % (v_mi.info.get("evidence_missing"), "; ".join(v_mi.reasons)))

    # Honest evidence, but one report field is tampered — each must be REJECTED.
    def _tamper(post, info_key, label):
        rc_, decl_, raw_, out_, inv_ = cli_json_child(
            instrumented_expr(post=post), open_blend=blend)
        v_ = _certify(rc_, decl_, raw_, out_, inv_)
        check(label, not v_.ok, "%s=%s -> %s"
              % (info_key, v_.info.get(info_key), "; ".join(v_.reasons)))

    _tamper(OVERALL_LIE, "overall_expected",
            "CLI child whose report lies overall=PASS (real WARNING) is REJECTED (R26-1)")
    _tamper(STATUS_LIE, "status_mismatch",
            "CLI child whose report flips a check status to PASS is REJECTED (R26-1)")
    _tamper(SUMMARY_LIE, "overall_expected",
            "CLI child whose report fakes the summary distribution is REJECTED (R26-1)")

    # R27-1 repro: the machine status/summary/overall stay honest, but a non-PASS
    # check's CUSTOMER-FACING display is rewritten to a reassuring message. The
    # gate derives each check's canonical display from the registry and rejects
    # the mismatch, so the wording shown to a customer can't contradict the result.
    DISPLAY_LIE = ("import json as _j\n_d = _j.loads(out)\n"
                   "for _c in _d['checks']:\n"
                   "    if _c.get('status') in ('UNKNOWN', 'WARNING', 'FAIL'):\n"
                   "        _c['display'] = 'Everything verified -- ready to render.'\n"
                   "        break\n"
                   "out = _j.dumps(_d)\n")
    _tamper(DISPLAY_LIE, "meta_mismatch",
            "CLI child whose report shows a reassuring display for a non-PASS "
            "check is REJECTED (R27-1)")

    # R28-1 repro: the child's canonical metadata is dropped from the evidence.
    # require_meta must fail CLOSED (not silently skip the display check).
    _tamper("_meta.clear()\n", "meta_mismatch",
            "CLI child that omits its canonical metadata is REJECTED, not skipped (R28-1)")
    # R28-1 repro: the report omits a per-check metadata field (here name).
    MISSING_FIELD = ("import json as _j\n_d = _j.loads(out)\n"
                     "for _c in _d['checks']:\n        _c.pop('name', None)\n"
                     "out = _j.dumps(_d)\n")
    _tamper(MISSING_FIELD, "meta_mismatch",
            "CLI child whose report omits a per-check metadata field is REJECTED (R28-1)")
    # R28-2 repros: the report claims a different Blender version / .blend file
    # than the child actually ran (provenance stays truthful in the sidecar).
    BLENDER_LIE = ("import json as _j\n_d = _j.loads(out)\n"
                   "_d['blender'] = '9.9.9'\nout = _j.dumps(_d)\n")
    _tamper(BLENDER_LIE, "overall_expected",
            "CLI child whose report claims a different Blender version is REJECTED (R28-2)")
    FILE_LIE = ("import json as _j\n_d = _j.loads(out)\n"
                "_d['file'] = '/evil/other.blend'\nout = _j.dumps(_d)\n")
    _tamper(FILE_LIE, "overall_expected",
            "CLI child whose report claims a different .blend file is REJECTED (R28-2)")

    # R29-1 repro: the child really opens a DIFFERENT file that shares the
    # fixture's basename. Provenance stays truthful (it records the decoy it
    # actually opened), so a basename-only check would ACCEPT it; matching the
    # scanned file to the intended fixture by IDENTITY REJECTS it.
    decoy_dir = tempfile.mkdtemp(prefix="failsafe_decoy_")
    decoy = os.path.join(decoy_dir, os.path.basename(blend))  # same name, other dir
    with open(blend, "rb") as _src, open(decoy, "wb") as _dst:
        _dst.write(_src.read())
    rc_dc, decl_dc, raw_dc, out_dc, inv_dc = cli_json_child(instrumented_expr(),
                                                            open_blend=decoy)
    v_dc = _certify(rc_dc, decl_dc, raw_dc, out_dc, inv_dc)
    check("CLI child that scanned a different file sharing the fixture's basename "
          "is REJECTED (identity, not basename) (R29-1)",
          not v_dc.ok, "scanned=%s expected=%s -> %s"
          % (_evidence(inv_dc)[3], os.path.basename(blend), "; ".join(v_dc.reasons)))

    # R29-1 repro: the child's recorded provenance is dropped. require_provenance
    # must fail CLOSED — an absent provenance cannot certify which file ran, so it
    # is a hard failure, never a silently skipped check.
    _tamper("_prov.clear()\n", "overall_expected",
            "CLI child that omits its provenance is REJECTED, not skipped (R29-1)")

    # R29-2 repro: a REAL cache-enumeration failure in the child. The report must
    # mark the cache UNKNOWN (enumerated:false, null total) instead of fabricating
    # a zero, so a could-not-enumerate is never mistaken for a verified empty.
    CACHE_FAIL_ATTACK = (
        "import bl_ext.user_default.failsafe.cache_inspect as _ci2\n"
        "def _cboom(*a, **k):\n"
        "    raise RuntimeError('cache enumeration failed (simulated)')\n"
        "_ci2.enumerate_caches = _cboom\n")
    rc_cf, decl_cf, raw_cf, out_cf, inv_cf = cli_json_child(
        instrumented_expr(attack=CACHE_FAIL_ATTACK), open_blend=blend)
    try:
        _cf_block = json.loads(raw_cf).get("cache_disk_usage", {})
    except ValueError:
        _cf_block = {}
    check("Report marks a FAILED cache enumeration as unknown, not a false zero "
          "(enumerated:false, null total) (R29-2)",
          _cf_block.get("enumerated") is False and _cf_block.get("total_bytes") is None,
          "cache_disk_usage=%s" % (_cf_block,))

    # R29-2 repro: a report presenting the legacy false-zero cache shape (0 bytes,
    # no enumeration attestation) must be REJECTED in certification mode — an
    # unverified zero cannot certify.
    CACHE_FALSEZERO_POST = ("import json as _j\n_d = _j.loads(out)\n"
                            "_d['cache_disk_usage'] = {'total_bytes': 0, 'items': []}\n"
                            "out = _j.dumps(_d)\n")
    _tamper(CACHE_FALSEZERO_POST, "overall_expected",
            "CLI child whose report claims an unverified zero cache is REJECTED (R29-2)")

    # R30-1 repro (the actual false-zero vector): a populated cache whose size went
    # unmeasured, but the report presents total_bytes:0 as if it were a verified
    # figure. An unknown size laundered into a confident zero must be REJECTED.
    CACHE_FALSEZERO_UNMEASURED_POST = (
        "import json as _j\n_d = _j.loads(out)\n"
        "_d['cache_disk_usage'] = {'enumerated': True, 'measured': False,\n"
        "    'total_bytes': 0, 'known_subtotal_bytes': 0, 'unmeasured': 1,\n"
        "    'items': [{'object': 'Cloth', 'system': 'Cloth', 'bytes': None}]}\n"
        "out = _j.dumps(_d)\n")
    _tamper(CACHE_FALSEZERO_UNMEASURED_POST, "overall_expected",
            "CLI child whose report presents total_bytes:0 for an unmeasured cache "
            "is REJECTED (R30-1 false zero)")

    # R30-1 repro: a report that declares a VERIFIED non-null total_bytes while
    # still admitting an unmeasured cache behind it — a confident number laid over
    # an unknown. The gate must REJECT (a verified total cannot hide unmeasured
    # caches, and the total must equal the measured sum).
    CACHE_HIDDEN_UNMEASURED_POST = (
        "import json as _j\n_d = _j.loads(out)\n"
        "_d['cache_disk_usage'] = {'enumerated': True, 'measured': True,\n"
        "    'total_bytes': 4096, 'known_subtotal_bytes': 0, 'unmeasured': 1,\n"
        "    'items': [{'object': 'Cloth', 'system': 'Cloth', 'bytes': None}]}\n"
        "out = _j.dumps(_d)\n")
    _tamper(CACHE_HIDDEN_UNMEASURED_POST, "overall_expected",
            "CLI child whose report declares a verified total over an unmeasured "
            "cache is REJECTED (R30-1)")

    # R30-1 positive: a report that HONESTLY reports an unmeasured cache as unknown
    # (total_bytes:null, measured:false) is ACCEPTED — the honest unknown is not a
    # false zero, and the correctness certification does not hinge on a knowable
    # informational cache size.
    CACHE_HONEST_UNKNOWN_POST = (
        "import json as _j\n_d = _j.loads(out)\n"
        "_d['cache_disk_usage'] = {'enumerated': True, 'measured': False,\n"
        "    'total_bytes': None, 'known_subtotal_bytes': 0, 'unmeasured': 1,\n"
        "    'items': [{'object': 'Cloth', 'system': 'Cloth', 'bytes': None}]}\n"
        "out = _j.dumps(_d)\n")
    rc_hu, decl_hu, raw_hu, out_hu, inv_hu = cli_json_child(
        instrumented_expr(post=CACHE_HONEST_UNKNOWN_POST), open_blend=blend)
    v_hu = _certify(rc_hu, decl_hu, raw_hu, out_hu, inv_hu)
    check("CLI child that HONESTLY reports an unmeasured cache as unknown (null "
          "total) is ACCEPTED (R30-1 honest unknown)",
          v_hu.ok, "ok=%s -> %s" % (v_hu.ok, "; ".join(v_hu.reasons) or "accepted"))

    # R30-1 positive: the child's REAL report carries the honest two-axis cache
    # schema (enumerated AND measured, with a labelled known subtotal) — proof the
    # production builder, not just the gate, distinguishes a measured figure from
    # an unmeasured one, and never emits a non-null total it did not measure.
    try:
        _ok_block = json.loads(raw_ok).get("cache_disk_usage", {})
    except ValueError:
        _ok_block = {}
    _tot = _ok_block.get("total_bytes")
    check("Real report states cache size on two honest axes (enumerated + measured, "
          "labelled subtotal) and never a non-null total it didn't measure (R30-1)",
          (_ok_block.get("enumerated") is True
           and _ok_block.get("measured") in (True, False)
           and "known_subtotal_bytes" in _ok_block
           and "unmeasured" in _ok_block
           and (_tot is None or _ok_block.get("measured") is True)),
          "cache_disk_usage keys=%s measured=%s total=%s"
          % (sorted(_ok_block.keys()), _ok_block.get("measured"), _tot))

    # R30-2 repro: gate_check._same_file must not treat two identical NONEXISTENT
    # paths as the same file (identity of a missing/deleted file can't be
    # established), while still proving identity for a real file and rejecting two
    # genuinely different paths (R29-1 preserved).
    _miss = os.path.join(decoy_dir, "gone", "fixture.blend")
    _same_missing = gate_check._same_file(_miss, _miss)
    _same_real = gate_check._same_file(blend, blend)
    _same_decoy = gate_check._same_file(blend, decoy)
    check("_same_file rejects identical missing paths, confirms a real file, and "
          "rejects a same-basename decoy (R30-2 / R29-1)",
          (_same_missing is False and _same_real is True and _same_decoy is False),
          "identical_missing=%s real=%s decoy=%s"
          % (_same_missing, _same_real, _same_decoy))

    # R31-2 repro: the measured/unmeasured SUMMARY fields must agree with the
    # actual items. measured:true asserted over a null-byte (unread) item is a
    # contradiction and must be REJECTED — the gate's companion to the R31-1 fix
    # that stops a partial size measurement from ever becoming a numeric item.
    CACHE_MEASURED_OVER_NULL_POST = (
        "import json as _j\n_d = _j.loads(out)\n"
        "_d['cache_disk_usage'] = {'enumerated': True, 'measured': True,\n"
        "    'total_bytes': None, 'known_subtotal_bytes': 0, 'unmeasured': 0,\n"
        "    'items': [{'object': 'Cloth', 'system': 'Cloth', 'bytes': None}]}\n"
        "out = _j.dumps(_d)\n")
    _tamper(CACHE_MEASURED_OVER_NULL_POST, "overall_expected",
            "CLI child claiming measured:true over a null-byte cache item is "
            "REJECTED (R31-2 contradiction)")

    # R31-2 repro: an unmeasured count that disagrees with the number of null-byte
    # items is a contradictory report and must be REJECTED.
    CACHE_UNMEASURED_COUNT_LIE_POST = (
        "import json as _j\n_d = _j.loads(out)\n"
        "_d['cache_disk_usage'] = {'enumerated': True, 'measured': False,\n"
        "    'total_bytes': None, 'known_subtotal_bytes': 100, 'unmeasured': 2,\n"
        "    'items': [{'object': 'A', 'system': 'Cloth', 'bytes': 100},\n"
        "              {'object': 'B', 'system': 'Cloth', 'bytes': None}]}\n"
        "out = _j.dumps(_d)\n")
    _tamper(CACHE_UNMEASURED_COUNT_LIE_POST, "overall_expected",
            "CLI child whose unmeasured count disagrees with its null-byte items "
            "is REJECTED (R31-2)")

    # R31-2 positive: an HONEST partial-unknown cache — one stage/frame measured,
    # another genuinely unmeasured, a null total, a labelled known subtotal, and
    # summary fields that match the items — is ACCEPTED. This is exactly what the
    # fixed cache_inspect emits when one measurement succeeds and another fails.
    CACHE_HONEST_PARTIAL_POST = (
        "import json as _j\n_d = _j.loads(out)\n"
        "_d['cache_disk_usage'] = {'enumerated': True, 'measured': False,\n"
        "    'total_bytes': None, 'known_subtotal_bytes': 100, 'unmeasured': 1,\n"
        "    'items': [{'object': 'A', 'system': 'Cloth', 'bytes': 100},\n"
        "              {'object': 'B', 'system': 'Cloth', 'bytes': None}]}\n"
        "out = _j.dumps(_d)\n")
    rc_hp, decl_hp, raw_hp, out_hp, inv_hp = cli_json_child(
        instrumented_expr(post=CACHE_HONEST_PARTIAL_POST), open_blend=blend)
    v_hp = _certify(rc_hp, decl_hp, raw_hp, out_hp, inv_hp)
    check("CLI child HONESTLY reporting a partial-unknown cache (one measured, one "
          "unmeasured, fields consistent) is ACCEPTED (R31-2)",
          v_hp.ok, "ok=%s -> %s" % (v_hp.ok, "; ".join(v_hp.reasons) or "accepted"))

    # R31-1 repro on the REAL INSTALLED build: the cache_inspect size helpers must
    # propagate a per-file measurement failure as unknown (None), never a silently
    # understated partial or a false verified zero, while a genuine 0-byte file
    # stays a MEASURED zero. Forced via a scandir/getsize wrapper over real files,
    # the exact "file present, size unreadable" condition (R31-1).
    import importlib as _il
    _ci = _il.import_module(MOD + ".cache_inspect")
    _sd = tempfile.mkdtemp(prefix="acc_r31_")
    for _n in ("a.vdb", "b.vdb"):
        with open(os.path.join(_sd, _n), "wb") as _fh:
            _fh.write(b"\0" * 100)
    _full = _ci._dir_size(_sd)
    _rs = os.scandir

    def _mk(fail):
        class _E:
            def __init__(s, de): s._de = de
            @property
            def name(s): return s._de.name
            def is_file(s, follow_symlinks=True):
                return s._de.is_file(follow_symlinks=follow_symlinks)
            def stat(s, follow_symlinks=True):
                if fail is None or s._de.name in fail:
                    raise OSError("forced stat failure")
                return s._de.stat(follow_symlinks=follow_symlinks)

        class _C:
            def __init__(s, p): s._it = _rs(p)
            def __enter__(s): return (_E(d) for d in s._it)
            def __exit__(s, *a): s._it.close()
        return lambda p: _C(p)
    try:
        _ci.os.scandir = _mk({"a.vdb"})
        _one = _ci._dir_size(_sd)
        _ci.os.scandir = _mk(None)
        _allf = _ci._dir_size(_sd)
    finally:
        _ci.os.scandir = _rs
    _zd = tempfile.mkdtemp(prefix="acc_r31z_")
    open(os.path.join(_zd, "empty.vdb"), "wb").close()
    _zero = _ci._dir_size(_zd)
    check("Installed cache_inspect propagates a failed size measurement as unknown "
          "(None), never a partial or false zero; 0-byte stays measured (R31-1)",
          (_full == 200 and _one is None and _allf is None and _zero == 0),
          "full=%r one_fail=%r all_fail=%r zero=%r"
          % (_full, _one, _allf, _zero))

    # Real child-failure repro (R20-1): a child that exits 0 but produces NO
    # report (the crash-exit-0 class) must be REJECTED by the very same gate.
    bad_expr = "import sys; jp = r'%s'; sys.exit(0)  # report intentionally unwritten"
    rc_bad, decl_bad, raw_bad, out_bad, _ = cli_json_child(bad_expr)
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
    rc_cr, decl_cr, raw_cr, out_cr, _ = cli_json_child(crash_expr, open_blend=blend)
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
    rc_em, decl_em, raw_em, out_em, _ = cli_json_child(empty_expr, open_blend=blend)
    v_em = gate_check.valid_cli_report(rc_em, raw_em, child_stderr=out_em,
                                       declared_code=decl_em,
                                       allowed_codes=(0, 1, 2))
    check("CLI zero-result scan (run_all->[]) is an all-N/A report, REJECTED (R21-2)",
          not v_em.ok, "rc=%s executed=%s -> %s"
          % (rc_em, v_em.info.get("executed"), "; ".join(v_em.reasons)))

    # R22-1 repro: a PARTIALLY executed scan. Force engine.run_all to return only
    # its FIRST Result, so the CLI emits a 27-entry report with exactly ONE
    # non-N/A check and 26 N/A. min_executed=1 alone would ACCEPT it; requiring the
    # fixture's structural check SET (CLOTH_REQUIRED_IDS) REJECTS it, because the
    # other required checks are still N/A. "27 listed" never proves 27 ran.
    partial_expr = ("import sys; "
                    "import bl_ext.user_default.failsafe.engine as e; "
                    "_orig = e.run_all; "
                    "e.run_all = (lambda *a, **k: _orig(*a, **k)[:1]); "
                    "import bl_ext.user_default.failsafe.cli as c; "
                    "jp = r'%s'; code, out = c.run(['--json']); "
                    "open(jp, 'w', encoding='utf-8').write(out); "
                    "open(jp + '.code', 'w').write(str(code)); "
                    "sys.exit(code)")
    rc_pt, decl_pt, raw_pt, out_pt, _ = cli_json_child(partial_expr, open_blend=blend)
    v_pt = gate_check.valid_cli_report(rc_pt, raw_pt, child_stderr=out_pt,
                                       declared_code=decl_pt,
                                       allowed_codes=(0, 1, 2),
                                       required_ids=CLOTH_REQUIRED_IDS)
    check("CLI partial scan (run_all[:1], 1-of-27 executed) is REJECTED (R22-1)",
          not v_pt.ok, "rc=%s executed=%s missing=%s -> %s"
          % (rc_pt, v_pt.info.get("executed"), v_pt.info.get("required_missing"),
             "; ".join(v_pt.reasons)))

    # R22 repro: a registered check RAISES. engine.run_all turns it into an
    # UNKNOWN "internal error" finding; overall is non-clean (exit 2, within
    # allowed_codes) and the report still has 27 checks with execution evidence —
    # so the earlier checks would pass it. The gate must REJECT it on the stable
    # internal-error marker, while leaving legitimate "Couldn't verify" UNKNOWNs
    # (which this fixture also has) accepted.
    ie_expr = ("import sys; "
               "import bl_ext.user_default.failsafe.engine as e; "
               "e.CHECKS[0].func = (lambda ctx, mk: (_ for _ in ()).throw("
               "RuntimeError('boom ' * 200))); "
               "import bl_ext.user_default.failsafe.cli as c; "
               "jp = r'%s'; code, out = c.run(['--json']); "
               "open(jp, 'w', encoding='utf-8').write(out); "
               "open(jp + '.code', 'w').write(str(code)); "
               "sys.exit(code)")
    rc_ie, decl_ie, raw_ie, out_ie, _ = cli_json_child(ie_expr, open_blend=blend)
    v_ie = gate_check.valid_cli_report(rc_ie, raw_ie, child_stderr=out_ie,
                                       declared_code=decl_ie,
                                       allowed_codes=(0, 1, 2))
    has_marker = gate_check.CHECK_INTERNAL_ERROR in raw_ie
    check("CLI scan where a check RAISED (internal error) is REJECTED (R22)",
          (not v_ie.ok) and has_marker, "rc=%s marker=%s -> %s"
          % (rc_ie, has_marker, "; ".join(v_ie.reasons)))

    # R23-1: prove the scan INVOKES every one of the registered check functions.
    # A report's N/A is ambiguous ("ran and nothing applicable" vs "never ran"),
    # so required_ids (non-N/A) and the 27 listed entries cannot prove the whole
    # registry executed — a scan returning results for only {1,7,8,26} and no
    # results for the other 23 still satisfies those checks. Independently wrap
    # every registered check function with a recorder, run a real scan, and
    # require EXACTLY the registered ids to have been invoked once each. A function
    # that legitimately returns N/A / no findings STILL fires its recorder, so
    # this counts invocation, not results, and distinguishes "ran and N/A" from
    # "skipped". Restore the originals in a finally so nothing leaks.
    expected_ids = [m.id for m in eng.CHECKS]
    invoked = []
    saved_funcs = [(m, m.func) for m in eng.CHECKS]

    def _recorder(target, mid, fn):
        def rec(ctx, mk):
            target.append(mid)
            return fn(ctx, mk)
        return rec
    scan_ok = True
    for m in eng.CHECKS:
        m.func = _recorder(invoked, m.id, m.func)
    try:
        res_inv = eng.run_all(bpy.context)
    except Exception as exc:
        scan_ok = False
        res_inv = []
        print("invocation-proof scan raised:", repr(exc))
    finally:
        for m, fn in saved_funcs:
            m.func = fn
    produced = {getattr(r, "check_id", None) for r in res_inv}
    na_but_invoked = sorted(set(i for i in invoked if i not in produced))
    v_inv = gate_check.valid_invocations(invoked, expected_ids)
    check("scan INVOKED every registered check exactly once, incl. N/A ones (R23-1)",
          scan_ok and v_inv.ok and len(expected_ids) == 27 and len(na_but_invoked) > 0,
          "invoked=%s unique=%s expected=%s na_but_invoked=%d; %s"
          % (v_inv.info.get("invoked"), v_inv.info.get("unique"),
             v_inv.info.get("expected"), len(na_but_invoked),
             "; ".join(v_inv.reasons) or "ok"))

    # R23-1 repro: a scan that SKIPS checks is caught by that proof. Temporarily
    # shrink the registry so run_all iterates only a subset, record invocations,
    # and assert valid_invocations REJECTS it for the missing ids (the skipped
    # functions never fired their recorder). Restore the full registry after.
    invoked_skip = []
    saved_funcs2 = [(m, m.func) for m in eng.CHECKS]
    for m in eng.CHECKS:
        m.func = _recorder(invoked_skip, m.id, m.func)
    saved_checks = list(eng.CHECKS)
    try:
        del eng.CHECKS[4:]  # a crippled scan that invokes only the first 4 checks
        try:
            eng.run_all(bpy.context)
        except Exception as exc:
            print("omitted-invocation repro scan raised:", repr(exc))
    finally:
        eng.CHECKS[:] = saved_checks
        for m, fn in saved_funcs2:
            m.func = fn
    v_skip = gate_check.valid_invocations(invoked_skip, expected_ids)
    check("a scan that SKIPS checks is caught by the invocation proof (R23-1)",
          not v_skip.ok, "invoked=%s -> %s"
          % (sorted(set(invoked_skip)), "; ".join(v_skip.reasons)))

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
