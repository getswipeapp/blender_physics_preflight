# SPDX-License-Identifier: GPL-3.0-or-later
"""Headless test harness for Physics Preflight.

Run:  blender -b --factory-startup -P tests/run_tests.py
Exits non-zero if any case fails. Each case builds a scene that should make one
specific check report a known status, then asserts it.
"""
import os
import sys
import tempfile
import traceback

import bpy

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
for p in (ROOT, HERE):
    if p not in sys.path:
        sys.path.insert(0, p)

import physics_preflight  # noqa: E402,F401
from physics_preflight import engine  # noqa: E402
from physics_preflight.engine import Status  # noqa: E402

import fixtures  # noqa: E402

SEV = {Status.FAIL: 4, Status.WARNING: 3, Status.UNKNOWN: 2,
       Status.NA: 1, Status.PASS: 0}


def worst_for_check(results, check_id):
    best = None
    for r in results:
        if r.check_id == check_id:
            if best is None or SEV[r.status] > SEV[best]:
                best = r.status
    return best


def statuses_for_check(results, check_id):
    return sorted({r.status for r in results if r.check_id == check_id})


# (label, check_id, builder, needs_outdir, expected_statuses)
CASES = [
    ("01 unapplied scale (warn)", 1, fixtures.build_01_fail, False, {Status.WARNING}),
    ("01 scale applied (pass)", 1, fixtures.build_01_pass, False, {Status.PASS}),
    ("02 absurd mass (warn)", 2, fixtures.build_02_fail, False, {Status.WARNING}),
    ("02 sane mass (pass)", 2, fixtures.build_02_pass, False, {Status.PASS}),
    ("03 overlap (warn)", 3, fixtures.build_03_fail, False, {Status.WARNING}),
    ("03 containment (warn)", 3, fixtures.build_03_containment_fail, False, {Status.WARNING}),
    ("03 separated (pass)", 3, fixtures.build_03_pass, False, {Status.PASS}),
    ("04 convex hull on torus (warn)", 4, fixtures.build_04_fail, False, {Status.WARNING}),
    ("04 convex hull on box (pass)", 4, fixtures.build_04_pass, False, {Status.PASS}),
    ("05 bad topology collider (warn)", 5, fixtures.build_05_fail, False, {Status.WARNING}),
    ("05 plane floor collider (pass)", 5, fixtures.build_05_pass, False, {Status.PASS}),
    ("06 rbw disabled (fail)", 6, fixtures.build_06_fail, False, {Status.FAIL}),
    ("06 rbw ok (pass)", 6, fixtures.build_06_pass, False, {Status.PASS}),
    ("07 cloth collision off (warn)", 7, fixtures.build_07_fail, False, {Status.WARNING}),
    ("07 cloth collision ok (pass)", 7, fixtures.build_07_pass, False, {Status.PASS}),
    ("08 negative scale (fail)", 8, fixtures.build_08_fail, False, {Status.FAIL}),
    ("08 normal scale (pass)", 8, fixtures.build_08_pass, False, {Status.PASS}),
    ("09 tiny object (warn)", 9, fixtures.build_09_fail, False, {Status.WARNING}),
    ("09 normal size (pass)", 9, fixtures.build_09_pass, False, {Status.PASS}),
    ("10 origin offset (warn)", 10, fixtures.build_10_fail, False, {Status.WARNING}),
    ("10 origin centred (pass)", 10, fixtures.build_10_pass, False, {Status.PASS}),
    ("11 big margin (warn)", 11, fixtures.build_11_fail, False, {Status.WARNING}),
    ("11 small margin (pass)", 11, fixtures.build_11_pass, False, {Status.PASS}),
    ("12 animated passive (fail)", 12, fixtures.build_12_fail, False, {Status.FAIL}),
    ("12 animated marked (pass)", 12, fixtures.build_12_pass, False, {Status.PASS}),
    ("13 broken constraint (fail)", 13, fixtures.build_13_fail, False, {Status.FAIL}),
    ("13 valid constraint (pass)", 13, fixtures.build_13_pass, False, {Status.PASS}),
    ("14 collision stack order (warn)", 14, fixtures.build_14_fail, False, {Status.WARNING}),
    ("14 collision at bottom (pass)", 14, fixtures.build_14_pass, False, {Status.PASS}),
    ("15 missing pin group (fail)", 15, fixtures.build_15_fail, False, {Status.FAIL}),
    ("15 valid pin group (pass)", 15, fixtures.build_15_pass, False, {Status.PASS}),
    ("16 domain no flow (warn)", 16, fixtures.build_16_fail, False, {Status.WARNING}),
    ("16 flow in domain (pass)", 16, fixtures.build_16_pass, False, {Status.PASS}),
    ("17 not baked (warn)", 17, fixtures.build_17_fail, False, {Status.WARNING}),
    ("18 baked files present (pass)", 18, fixtures.build_18_pass, True, {Status.PASS}),
    ("18 FALSE-PASS TRAP: baked flag, no files (fail)", 18, fixtures.build_18_fail, True, {Status.FAIL}),
    ("19 bake range short (warn)", 19, fixtures.build_19_fail, True, {Status.WARNING}),
    ("20 missing interior frame (fail)", 20, fixtures.build_20_fail, True, {Status.FAIL}),
    ("21 shared cache dir (warn)", 21, fixtures.build_21_fail, True, {Status.WARNING}),
    ("22 absolute cache path (warn)", 22, fixtures.build_22_fail, True, {Status.WARNING}),
    ("23 fps changed after bake (unknown)", 23, fixtures.build_23_fail, True, {Status.UNKNOWN, Status.WARNING}),
]


def main():
    passed = 0
    failed = 0
    fails = []
    tmp = tempfile.mkdtemp(prefix="physpf_tests_")
    for i, (label, cid, builder, needs_outdir, expected) in enumerate(CASES):
        try:
            if needs_outdir:
                outdir = os.path.join(tmp, "case_%02d" % i)
                os.makedirs(outdir, exist_ok=True)
                builder(outdir)
            else:
                builder()
            results = engine.run_all(bpy.context)
            got = worst_for_check(results, cid)
            all_st = statuses_for_check(results, cid)
            ok = got in expected
            if ok:
                passed += 1
                print("  PASS  %s  -> %s" % (label, got))
            else:
                failed += 1
                msg = ("  FAIL  %s  -> got worst=%s (statuses=%s), expected %s"
                       % (label, got, all_st, sorted(expected)))
                print(msg)
                fails.append(msg)
        except Exception:
            failed += 1
            tb = traceback.format_exc()
            msg = "  ERROR %s\n%s" % (label, tb)
            print(msg)
            fails.append(msg)

    print("\n%s" % ("=" * 60))
    print("Blender %s  |  %d passed, %d failed, %d total"
          % (bpy.app.version_string, passed, failed, len(CASES)))
    if fails:
        print("\nFAILURES:")
        for m in fails:
            print(m)
    # exit code for CI
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
