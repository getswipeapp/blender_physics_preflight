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
    ("01 unapplied rotation on cloth (warn)", 1, fixtures.build_01_rotation_fail, False, {Status.WARNING}),
    ("01 scale applied (pass)", 1, fixtures.build_01_pass, False, {Status.PASS}),
    ("02 absurd mass (warn)", 2, fixtures.build_02_fail, False, {Status.WARNING}),
    ("02 sane mass (pass)", 2, fixtures.build_02_pass, False, {Status.PASS}),
    ("03 overlap (warn)", 3, fixtures.build_03_fail, False, {Status.WARNING}),
    ("03 containment (warn)", 3, fixtures.build_03_containment_fail, False, {Status.WARNING}),
    ("03 separated (pass)", 3, fixtures.build_03_pass, False, {Status.PASS}),
    ("03 off start frame (unknown)", 3, fixtures.build_03_offstart_unknown, False, {Status.UNKNOWN}),
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
    ("16 effector only, no flow (warn)", 16, fixtures.build_16_effector_only_fail, False, {Status.WARNING}),
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


# Cache regression: build one scene, assert SEVERAL checks at once, and forbid a
# PASS on any check whose cache is actually broken. This is the guard against
# F01 (missing head/tail frame slipping past all four cache checks) and F19
# (shallow assertions hiding a wrong PASS).
# (label, builder, {cid: expected_worst_set}, forbid_pass_cids)
CACHE_REGRESSION = [
    ("F01 missing LAST frame -> #17/#18/#20 FAIL", fixtures.build_F01_missing_tail,
     {17: {Status.FAIL}, 18: {Status.FAIL}, 20: {Status.FAIL}}, (17, 18, 20)),
    ("F01 missing FIRST frame -> #17/#18/#20 FAIL", fixtures.build_F01_missing_head,
     {17: {Status.FAIL}, 18: {Status.FAIL}, 20: {Status.FAIL}}, (17, 18, 20)),
    ("F01 missing LAST 3 frames -> #18/#20 FAIL", fixtures.build_F01_missing_multi_tail,
     {18: {Status.FAIL}, 20: {Status.FAIL}}, (17, 18, 20)),
]


def verdict_unit_tests():
    """Fast, deterministic logic tests for cache_inspect.cache_status(), built
    from constructed CacheEntry objects (no Blender bake needed). These
    reproduce the reviewer's isolated scenarios: F01 head/tail, F04 replay,
    F05 external vs memory, F06 sampled, F07 unreadable."""
    from physics_preflight import cache_inspect as ci

    def entry(present, expected=(1, 2, 3, 4, 5), baked=True, empty=(),
              unreadable=(), replay=False, memory=False, determinable=True,
              applicable=True, components=(), sampled=False, step=1):
        e = ci.CacheEntry("Obj", "Cloth", "point")
        e.baked_flag = baked
        e.baked_determinable = determinable
        e.file_check_applicable = applicable
        e.cache_dir = "/tmp/physpf_unit"
        e.frames_expected = list(expected)
        e.frames_present = set(present)
        e.frames_empty = set(empty)
        e.frames_unreadable = set(unreadable)
        e.replay = replay
        e.memory = memory
        e.sampled = sampled
        e.frame_step = step
        e.components_missing = list(components)
        return e

    cases = [
        ("F01 missing tail", entry(present=[1, 2, 3, 4]), ci.V_INCOMPLETE),
        ("F01 missing head", entry(present=[2, 3, 4, 5]), ci.V_INCOMPLETE),
        ("complete", entry(present=[1, 2, 3, 4, 5]), ci.V_COMPLETE),
        ("empty but baked", entry(present=[], baked=True), ci.V_EMPTY),
        ("no files, not baked", entry(present=[], baked=False), ci.V_NOT_BAKED),
        ("F07 corrupt 0-byte", entry(present=[1, 2, 3, 4, 5], empty=[3]), ci.V_CORRUPT),
        ("F07 unreadable", entry(present=[1, 2, 3, 4, 5], unreadable=[3]), ci.V_UNREADABLE),
        ("F04 replay", entry(present=[1], replay=True), ci.V_REPLAY),
        ("F05 memory (no files)", entry(present=[], memory=True), ci.V_MEMORY),
        ("packed GN", entry(present=[], determinable=False), ci.V_UNVERIFIABLE),
        ("unsaved", entry(present=[], applicable=False), ci.V_UNVERIFIABLE),
        ("F06 sampled complete", entry(present=[1, 3, 5], expected=[1, 3, 5],
                                       sampled=True, step=2), ci.V_COMPLETE),
        ("F06 sampled missing tail", entry(present=[1, 3], expected=[1, 3, 5],
                                           sampled=True, step=2), ci.V_INCOMPLETE),
        ("F02 fluid missing mesh sub-cache",
         entry(present=[1, 2, 3, 4, 5], components=["mesh"]), ci.V_INCOMPLETE),
    ]
    out = []
    for label, e, expect in cases:
        got = ci.cache_status(e).state
        out.append((label, got == expect, got, expect))
    return out


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

    # ---- cache regression (multi-check, forbids a wrong PASS) --------------
    for j, (label, builder, expectations, forbid_pass) in enumerate(CACHE_REGRESSION):
        try:
            outdir = os.path.join(tmp, "regr_%02d" % j)
            os.makedirs(outdir, exist_ok=True)
            builder(outdir)
            results = engine.run_all(bpy.context)
            problems = []
            for cid, expected in expectations.items():
                got = worst_for_check(results, cid)
                if got not in expected:
                    problems.append("#%d worst=%s want %s (all=%s)"
                                    % (cid, got, sorted(expected),
                                       statuses_for_check(results, cid)))
            for cid in forbid_pass:
                if Status.PASS in statuses_for_check(results, cid):
                    problems.append("#%d wrongly returned PASS" % cid)
            if problems:
                failed += 1
                msg = "  FAIL  %s  -> %s" % (label, "; ".join(problems))
                print(msg)
                fails.append(msg)
            else:
                passed += 1
                print("  PASS  %s" % label)
        except Exception:
            failed += 1
            msg = "  ERROR %s\n%s" % (label, traceback.format_exc())
            print(msg)
            fails.append(msg)

    # ---- verdict unit tests (fast, no bake) --------------------------------
    for label, ok, got, expect in verdict_unit_tests():
        if ok:
            passed += 1
            print("  PASS  verdict: %s  -> %s" % (label, got))
        else:
            failed += 1
            msg = "  FAIL  verdict: %s  -> got %s, want %s" % (label, got, expect)
            print(msg)
            fails.append(msg)

    total = len(CASES) + len(CACHE_REGRESSION) + len(verdict_unit_tests())
    print("\n%s" % ("=" * 60))
    print("Blender %s  |  %d passed, %d failed, %d total"
          % (bpy.app.version_string, passed, failed, total))
    if fails:
        print("\nFAILURES:")
        for m in fails:
            print(m)
    # exit code for CI
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
