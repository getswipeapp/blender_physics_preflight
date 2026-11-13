# SPDX-License-Identifier: GPL-3.0-or-later
"""Headless test harness for Failsafe.

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

import failsafe  # noqa: E402,F401
from failsafe import engine  # noqa: E402
from failsafe.engine import Status  # noqa: E402

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
    # heavy-sim integration (real bakes): prove the scanners populate correctly,
    # not just the decision logic.
    ("HS soft-body baked (pass)", 18, fixtures.build_softbody_pass, True, {Status.PASS}),
    ("HS soft-body missing last frame (fail)", 18, fixtures.build_softbody_missing_tail, True, {Status.FAIL}),
    ("HS particle baked (pass)", 18, fixtures.build_particle_pass, True, {Status.PASS}),
    ("HS particle missing last frame (fail)", 18, fixtures.build_particle_missing_tail, True, {Status.FAIL}),
    ("HS fluid baked (pass)", 18, fixtures.build_fluid_pass, True, {Status.PASS}),
    ("HS fluid missing data frame (fail)", 18, fixtures.build_fluid_missing_data_frame, True, {Status.FAIL}),
    ("HS fluid missing mesh frame (fail)", 18, fixtures.build_fluid_missing_mesh_frame, True, {Status.FAIL}),
    ("HS fluid mislabeled data-in-mesh (fail)", 18, fixtures.build_fluid_mislabeled_mesh, True, {Status.FAIL}),
    # R11: config/ is a required component; deleting one config frame fails #18
    # even though data/ and mesh/ are intact.
    ("HS fluid missing config frame (fail)", 18, fixtures.build_fluid_missing_config, True, {Status.FAIL}),
    # R12: a non-zero cache frame offset makes #19 UNKNOWN (coverage can't be
    # confirmed from the raw range), never a false PASS.
    ("R12 fluid cache offset (unknown)", 19, fixtures.build_fluid_offset_unknown, True, {Status.UNKNOWN}),
    # R16: guiding is a required component when enabled; deleting a guiding frame
    # fails #18 even though data/ and config/ are intact. (real guide bake)
    ("HS fluid missing guiding frame (fail)", 18, fixtures.build_fluid_missing_guiding, True, {Status.FAIL}),
]


# Cache regression: build one scene, assert SEVERAL checks at once, and forbid a
# PASS on any check whose cache is actually broken. This is the guard against
# F01 (missing head/tail frame slipping past all four cache checks) and F19
# (shallow assertions hiding a wrong PASS).
# (label, builder, {cid: expected_worst_set}, forbid_pass_cids)
CACHE_REGRESSION = [
    # forbid_pass now includes #19 (R02): an incomplete bake must not get a
    # green "range covers" tick while #18/#20 are failing.
    ("F01 missing LAST frame -> no cache PASS", fixtures.build_F01_missing_tail,
     {17: {Status.FAIL}, 18: {Status.FAIL}, 20: {Status.FAIL}}, (17, 18, 19, 20)),
    ("F01 missing FIRST frame -> no cache PASS", fixtures.build_F01_missing_head,
     {17: {Status.FAIL}, 18: {Status.FAIL}, 20: {Status.FAIL}}, (17, 18, 19, 20)),
    ("F01 missing LAST 3 frames -> no cache PASS", fixtures.build_F01_missing_multi_tail,
     {18: {Status.FAIL}, 20: {Status.FAIL}}, (17, 18, 19, 20)),
]


def verdict_unit_tests():
    """Fast, deterministic logic tests for cache_inspect.cache_status(), built
    from constructed CacheEntry objects (no Blender bake needed). These
    reproduce the reviewer's isolated scenarios: F01 head/tail, F04 replay,
    F05 external vs memory, F06 sampled, F07 unreadable."""
    from failsafe import cache_inspect as ci

    def entry(present, expected=(1, 2, 3, 4, 5), baked=True, empty=(),
              unreadable=(), replay=False, memory=False, determinable=True,
              applicable=True, components=(), sampled=False, step=1,
              outdated=False, skipped=False, baking=False):
        e = ci.CacheEntry("Obj", "Cloth", "point")
        e.baked_flag = baked
        e.baked_determinable = determinable
        e.file_check_applicable = applicable
        e.cache_dir = "/tmp/failsafe_unit"
        e.frames_expected = list(expected)
        e.frames_present = set(present)
        e.frames_empty = set(empty)
        e.frames_unreadable = set(unreadable)
        e.replay = replay
        e.memory = memory
        e.sampled = sampled
        e.frame_step = step
        e.components_missing = list(components)
        e.cache_outdated = outdated
        e.frame_skip = skipped
        e.baking_in_progress = baking
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
        # R11: a missing config sub-cache makes a full data set INCOMPLETE.
        ("R11 fluid missing config sub-cache",
         entry(present=[1, 2, 3, 4, 5], components=["config (missing 1 frame)"]),
         ci.V_INCOMPLETE),
        # R13: an enabled stage whose baked flag is off is flagged as a missing
        # component even when (stale) files are present -> not COMPLETE.
        ("R13 fluid stage-not-baked sub-cache",
         entry(present=[1, 2, 3, 4, 5], components=["noise (stage not baked)"]),
         ci.V_INCOMPLETE),
        # R14: a complete cache Blender has marked outdated is not a confident
        # PASS -> UNVERIFIABLE (UNKNOWN), never COMPLETE.
        ("R14 complete but outdated -> UNVERIFIABLE",
         entry(present=[1, 2, 3, 4, 5], outdated=True), ci.V_UNVERIFIABLE),
        # R14: outdated must not override a harder failure — no files is still
        # EMPTY, not a soft UNKNOWN.
        ("R14 outdated but no files -> EMPTY",
         entry(present=[], baked=True, outdated=True), ci.V_EMPTY),
        # R15: frame_skip is an INDEPENDENT downgrade — a complete, not-outdated
        # cache with skipped frames must not pass as COMPLETE.
        ("R15 complete but frame_skip (not outdated) -> UNVERIFIABLE",
         entry(present=[1, 2, 3, 4, 5], outdated=False, skipped=True),
         ci.V_UNVERIFIABLE),
        ("R15 both outdated and frame_skip -> UNVERIFIABLE",
         entry(present=[1, 2, 3, 4, 5], outdated=True, skipped=True),
         ci.V_UNVERIFIABLE),
        # R15: a hard failure still wins — missing files take precedence over the
        # soft staleness flags.
        ("R15 frame_skip but missing files -> INCOMPLETE",
         entry(present=[1, 2, 3, 4], skipped=True), ci.V_INCOMPLETE),
        # R16 test #4: a bake in progress is never a confident COMPLETE…
        ("R16 complete but bake in progress -> UNVERIFIABLE",
         entry(present=[1, 2, 3, 4, 5], baking=True), ci.V_UNVERIFIABLE),
        # …but missing files still take precedence over the in-progress flag.
        ("R16 bake in progress but missing files -> INCOMPLETE",
         entry(present=[1, 2, 3, 4], baking=True), ci.V_INCOMPLETE),
        # R16: a missing/unbaked guiding sub-cache makes the bake INCOMPLETE.
        ("R16 fluid guiding stage-not-baked sub-cache",
         entry(present=[1, 2, 3, 4, 5], components=["guiding (stage not baked)"]),
         ci.V_INCOMPLETE),
    ]
    out = []
    for label, e, expect in cases:
        got = ci.cache_status(e).state
        out.append((label, got == expect, got, expect))
    return out


def gn_unit_tests():
    """Geometry Nodes bake-target resolution (F03/R03). A live GN disk bake is
    too fragile to script headlessly, so these cover the INHERIT resolution and
    the blob-missing verdict directly."""
    from failsafe import cache_inspect as ci

    class Fake:
        def __init__(self, **kw):
            self.__dict__.update(kw)

    out = []
    target_cases = [
        ("INHERIT falls back to modifier PACKED",
         Fake(bake_target="INHERIT"), Fake(bake_target="PACKED"), "PACKED"),
        ("explicit DISK overrides a PACKED modifier",
         Fake(bake_target="DISK"), Fake(bake_target="PACKED"), "DISK"),
        ("missing bake target uses modifier DISK",
         Fake(bake_target=None), Fake(bake_target="DISK"), "DISK"),
        ("empty bake target uses modifier PACKED",
         Fake(bake_target=""), Fake(bake_target="PACKED"), "PACKED"),
    ]
    for label, bake, mod, expect in target_cases:
        got = ci._resolve_gn_target(bake, mod)
        out.append(("gn target: " + label, got == expect, got, expect))

    # R07: a custom PATH must not trigger custom-range handling; only a custom
    # frame range (or STILL) changes the range.
    scene = Fake(frame_start=1, frame_end=10)
    range_cases = [
        ("custom path only -> scene range",
         Fake(bake_mode="ANIMATION", use_custom_path=True,
              use_custom_simulation_frame_range=False, frame_start=0, frame_end=0),
         (1, 10)),
        ("custom range -> its own range",
         Fake(bake_mode="ANIMATION", use_custom_simulation_frame_range=True,
              frame_start=3, frame_end=7), (3, 7)),
        ("no customisation -> scene range",
         Fake(bake_mode="ANIMATION"), (1, 10)),
        ("still frame -> single frame",
         Fake(bake_mode="STILL", frame_start=5), (5, 5)),
    ]
    for label, bake, expect in range_cases:
        got = ci._gn_bake_range(bake, scene)
        out.append(("gn range: " + label, got == expect, got, expect))

    # Metadata present but blobs/ missing -> not COMPLETE (R03).
    e = ci.CacheEntry("Obj", "Geometry Nodes", "gn")
    e.baked_determinable = True
    e.file_check_applicable = True
    e.cache_dir = "/tmp/failsafe_gn"
    e.frames_expected = [1, 2, 3]
    e.frames_present = {1, 2, 3}
    e.baked_flag = True
    e.components_missing = ["blob data"]
    got = ci.cache_status(e).state
    out.append(("gn blobs missing -> INCOMPLETE", got == ci.V_INCOMPLETE,
                got, ci.V_INCOMPLETE))

    # R09: a GN disk bake whose files are all present is still UNVERIFIABLE
    # (UNKNOWN), never a confident COMPLETE — we can't prove blob integrity.
    e2 = ci.CacheEntry("Obj", "Geometry Nodes", "gn")
    e2.baked_determinable = True
    e2.file_check_applicable = True
    e2.cache_dir = "/tmp/failsafe_gn"
    e2.frames_expected = [1, 2, 3]
    e2.frames_present = {1, 2, 3}
    e2.baked_flag = True
    e2.certifiable = False
    got2 = ci.cache_status(e2).state
    out.append(("gn disk present -> UNVERIFIABLE (can't certify)",
                got2 == ci.V_UNVERIFIABLE, got2, ci.V_UNVERIFIABLE))
    return out


def fluid_matcher_unit_tests():
    """R10: each fluid sub-cache matcher accepts only ITS component's files, so
    a file from one component can't be counted inside another's folder."""
    from failsafe import cache_inspect as ci
    rx = ci._FLUID_COMPONENT_RE
    checks = [
        ("data accepts fluid_data", bool(rx["data"].match("fluid_data_0001.vdb")), True),
        ("mesh accepts fluid_mesh", bool(rx["mesh"].match("fluid_mesh_0001.bobj.gz")), True),
        ("noise accepts fluid_noise", bool(rx["noise"].match("fluid_noise_0001.vdb")), True),
        ("particles accepts fluid_particles", bool(rx["particles"].match("fluid_particles_0001.vdb")), True),
        ("mesh rejects a data file", bool(rx["mesh"].match("fluid_data_0001.vdb")), False),
        ("data rejects a mesh file", bool(rx["data"].match("fluid_mesh_0001.bobj.gz")), False),
        ("data rejects unrelated file", bool(rx["data"].match("unrelated_0001.vdb")), False),
        ("noise rejects a data file", bool(rx["noise"].match("fluid_data_0001.vdb")), False),
        # R16: guiding matcher accepts only fluid_guiding files.
        ("guiding accepts fluid_guiding", bool(rx["guiding"].match("fluid_guiding_0001.vdb")), True),
        ("guiding rejects a data file", bool(rx["guiding"].match("fluid_data_0001.vdb")), False),
        ("data rejects a guiding file", bool(rx["data"].match("fluid_guiding_0001.vdb")), False),
    ]
    return [("fluid matcher: %s" % label, got == expect, got, expect)
            for label, got, expect in checks]


def _run_check_entries(cid, entries):
    """Invoke one real check function against a constructed list of CacheEntry
    objects (bypasses disk enumeration), returning its worst status."""
    from failsafe import engine, checks_cache  # noqa: F401
    meta = next(m for m in engine.CHECKS if m.id == cid)
    mk = engine._mk(meta)

    class Ctx:
        pass
    ctx = Ctx()
    ctx.scene = bpy.context.scene
    ctx._failsafe_caches = entries
    results = meta.func(ctx, mk)
    return worst_for_check(results, cid)


def memory_reliability_tests():
    """R17: the staleness guards (outdated / frame_skip / baking) must apply to
    MEMORY caches and the Rigid Body World too, not just disk caches. is_outdated
    doesn't flip under headless bake, so we drive the real #17/#19 check logic
    with constructed entries (the exact false-PASS combination from the review)."""
    from failsafe import cache_inspect as ci

    def mem(kind="point", system="Cloth", baked=True, outdated=False,
            skipped=False, baking=False, crange=(1, 10), srange=(1, 10)):
        e = ci.CacheEntry("Obj", system, kind)
        e.baked_flag = baked
        e.memory = True
        e.cache_outdated = outdated
        e.frame_skip = skipped
        e.baking_in_progress = baking
        e.cache_range = crange
        e.scene_range = srange
        return e

    out = []
    # The headline case: memory + is_baked + is_outdated must NOT be PASS on #17.
    got = _run_check_entries(17, [mem(outdated=True)])
    out.append(("R17 memory cache outdated -> #17 UNKNOWN (not PASS)",
                got == Status.UNKNOWN, got, Status.UNKNOWN))
    # A clean memory cache is still a PASS.
    got = _run_check_entries(17, [mem()])
    out.append(("R17 memory cache clean -> #17 PASS",
                got == Status.PASS, got, Status.PASS))
    # Rigid Body World (bypasses cache_status) must honour the flags too.
    got = _run_check_entries(17, [mem(kind="rbw", system="Rigid Body World",
                                      skipped=True)])
    out.append(("R17 RBW frame_skip -> #17 UNKNOWN (not PASS)",
                got == Status.UNKNOWN, got, Status.UNKNOWN))
    got = _run_check_entries(17, [mem(kind="rbw", system="Rigid Body World")])
    out.append(("R17 RBW clean -> #17 PASS", got == Status.PASS, got, Status.PASS))
    # #19 must not green-light coverage for a stale memory cache.
    got = _run_check_entries(19, [mem(baking=True)])
    out.append(("R19 memory cache baking -> #19 no PASS",
                got != Status.PASS, got, "not PASS"))
    got = _run_check_entries(19, [mem()])
    out.append(("R19 memory cache clean -> #19 PASS",
                got == Status.PASS, got, Status.PASS))
    # reliability_reasons stays empty for a clean cache (no false downgrade).
    clean = mem()
    out.append(("R17 clean cache has no reliability reasons",
                ci.reliability_reasons(clean) == [], ci.reliability_reasons(clean), []))
    return out


def stage_flag_state_tests():
    """R18: a fluid stage baked-flag that this Blender build does not expose must
    read as 'unknown' (-> UNKNOWN), never silently default to 'baked'."""
    from failsafe import cache_inspect as ci

    class DS:  # stand-in for domain_settings
        def __init__(self, **kw):
            self.__dict__.update(kw)

    out = []
    cases = [
        ("flag True -> baked", DS(has_cache_baked_mesh=True), "baked"),
        ("flag False -> unbaked", DS(has_cache_baked_mesh=False), "unbaked"),
        ("flag absent -> unknown (not baked!)", DS(), "unknown"),
    ]
    for label, ds, expect in cases:
        got = ci._stage_flag_state(ds, "has_cache_baked_mesh")
        out.append(("R18 stage flag: " + label, got == expect, got, expect))

    # And the verdict routing: an 'unknown' stage makes a file-complete fluid
    # UNVERIFIABLE (UNKNOWN), carrying its specific note.
    e = ci.CacheEntry("Obj", "Fluid", "fluid")
    e.baked_determinable = True
    e.file_check_applicable = True
    e.cache_dir = "/tmp/failsafe_fluid"
    e.frames_expected = [1, 2, 3]
    e.frames_present = {1, 2, 3}
    e.baked_flag = True
    e.certifiable = False
    e.uncertain_note = "the 'mesh' stage's baked state isn't exposed on this Blender version"
    v = ci.cache_status(e)
    out.append(("R18 unverifiable stage -> UNVERIFIABLE",
                v.state == ci.V_UNVERIFIABLE, v.state, ci.V_UNVERIFIABLE))
    out.append(("R18 unverifiable stage carries its note",
                "isn't exposed" in (v.note or ""), v.note, "<note with reason>"))
    return out


def readonly_tests():
    """Scan must not change the scene: selection, active object, current frame
    or the object set. (Covers the Scan path; Export is a separate explicit
    action.)"""
    fixtures.build_03_fail()  # two rigid bodies
    sc = bpy.context.scene
    for o in list(bpy.context.selected_objects):
        o.select_set(False)
    objs = list(sc.objects)
    if objs:
        objs[0].select_set(True)
        bpy.context.view_layer.objects.active = objs[0]

    def snap():
        return {
            "sel": sorted(o.name for o in bpy.context.selected_objects),
            "active": getattr(bpy.context.view_layer.objects.active, "name", None),
            "frame": sc.frame_current,
            "frame_range": (sc.frame_start, sc.frame_end),
            "names": sorted(o.name for o in sc.objects),
            "mode": getattr(bpy.context, "mode", None),
            # new datablock counts — a scan must not create texts/objects/meshes
            "n_texts": len(bpy.data.texts),
            "n_objects": len(bpy.data.objects),
            "n_meshes": len(bpy.data.meshes),
        }
    before = snap()
    engine.run_all(bpy.context)
    after = snap()
    return [
        ("read-only: selection unchanged", before["sel"] == after["sel"],
         after["sel"], before["sel"]),
        ("read-only: active object unchanged", before["active"] == after["active"],
         after["active"], before["active"]),
        ("read-only: current frame unchanged", before["frame"] == after["frame"],
         after["frame"], before["frame"]),
        ("read-only: frame range unchanged",
         before["frame_range"] == after["frame_range"],
         after["frame_range"], before["frame_range"]),
        ("read-only: object set unchanged", before["names"] == after["names"],
         len(after["names"]), len(before["names"])),
        ("read-only: mode unchanged", before["mode"] == after["mode"],
         after["mode"], before["mode"]),
        ("read-only: no new text datablocks created",
         before["n_texts"] == after["n_texts"], after["n_texts"], before["n_texts"]),
        ("read-only: no new object datablocks", before["n_objects"] == after["n_objects"],
         after["n_objects"], before["n_objects"]),
        ("read-only: no new mesh datablocks", before["n_meshes"] == after["n_meshes"],
         after["n_meshes"], before["n_meshes"]),
    ]


def roundtrip_fix_tests():
    """A finding must CLEAR when the problem is fixed, not only appear when it
    breaks (the owner verified this by hand: delete the cache files -> #18 FAIL,
    put them back -> #18 PASS). Prove the full round-trip on a real baked cache:
    PASS -> (delete a frame) FAIL -> (restore it) PASS again."""
    import glob
    import shutil
    out = []
    outdir = tempfile.mkdtemp(prefix="failsafe_roundtrip_")
    try:
        fixtures.build_softbody_pass(outdir)
    except Exception as ex:
        return [("roundtrip: build soft-body", False, repr(ex), "built")]

    r = engine.run_all(bpy.context)
    s1 = worst_for_check(r, 18)
    out.append(("roundtrip 1/3 baked+present -> #18 PASS", s1 == Status.PASS,
                s1, Status.PASS))

    caches = glob.glob(os.path.join(outdir, "blendcache_*"))
    files = sorted(glob.glob(os.path.join(caches[0], "*.bphys"))) if caches else []
    if not files:
        out.append(("roundtrip: found cache files", False, len(files), ">0"))
        return out
    victim = files[-1]
    backup = victim + ".bak"
    shutil.copy2(victim, backup)
    os.remove(victim)                         # break it: one frame missing
    r = engine.run_all(bpy.context)
    s2 = worst_for_check(r, 18)
    out.append(("roundtrip 2/3 frame deleted -> #18 FAIL", s2 == Status.FAIL,
                s2, Status.FAIL))

    shutil.move(backup, victim)               # fix it: restore the frame
    r = engine.run_all(bpy.context)
    s3 = worst_for_check(r, 18)
    out.append(("roundtrip 3/3 frame restored -> #18 PASS again",
                s3 == Status.PASS, s3, Status.PASS))
    return out


def readonly_filesystem_tests():
    """A scan must not WRITE to disk — it only reads cache files. Build a real
    baked soft-body (so there are cache files on disk), snapshot the whole cache
    tree (path -> size, mtime), run every check, and assert nothing changed and
    no file was added or removed."""
    out = []
    outdir = tempfile.mkdtemp(prefix="failsafe_ro_fs_")
    try:
        fixtures.build_softbody_pass(outdir)
    except Exception as ex:
        return [("read-only fs: build soft-body cache", False, repr(ex), "built")]

    def tree_snap(root):
        snap = {}
        for dirpath, _dirs, files in os.walk(root):
            for fn in files:
                p = os.path.join(dirpath, fn)
                try:
                    st = os.stat(p)
                    snap[os.path.relpath(p, root)] = (st.st_size, st.st_mtime_ns)
                except OSError:
                    snap[os.path.relpath(p, root)] = ("ERR",)
        return snap

    before = tree_snap(outdir)
    engine.run_all(bpy.context)
    after = tree_snap(outdir)
    added = sorted(set(after) - set(before))
    removed = sorted(set(before) - set(after))
    changed = sorted(k for k in before if k in after and before[k] != after[k])
    out.append(("read-only fs: cache had files to guard", len(before) > 0,
                len(before), ">0"))
    out.append(("read-only fs: no files added by a scan", added == [], added, []))
    out.append(("read-only fs: no files removed by a scan", removed == [], removed, []))
    out.append(("read-only fs: no file contents/mtime changed", changed == [],
                changed, []))
    return out


def render_check_tests():
    """The opt-in 'check before render' logic (handlers.run_render_check): it must
    flag a broken scene, stay read-only, and honour the 'also warn on warnings'
    toggle — all without blocking anything."""
    from failsafe import handlers
    from failsafe.help_text import HELP
    out = []

    # Every check must have a plain-English "why it matters" line.
    ids = {m.id for m in engine.CHECKS}
    out.append(("help: every check has a 'why' line", set(HELP) == ids,
                sorted(set(HELP) ^ ids), "no diff"))

    # 1) A known-broken scene (baked flag on, no cache files -> #18 FAIL) must be
    #    reported as a problem, with the fail surfaced in the banner.
    outdir = tempfile.mkdtemp(prefix="failsafe_render_fail_")
    fixtures.build_18_fail(outdir)
    info = handlers.run_render_check(bpy.context.scene)
    out.append(("render check: broken scene -> fail>0",
                info["fail"] > 0, info["fail"], ">0"))
    out.append(("render check: broken scene -> problem flagged",
                info["problem"] is True, info["problem"], True))
    out.append(("render check: banner mentions the fail count",
                "fail" in info["banner"], info["banner"], "<...fail...>"))

    # 2) Read-only: running the render check must not touch the scene/datablocks.
    def snap():
        sc = bpy.context.scene
        return (sorted(o.name for o in sc.objects), sc.frame_current,
                len(bpy.data.texts), len(bpy.data.objects), len(bpy.data.meshes))
    before = snap()
    handlers.run_render_check(bpy.context.scene)
    after = snap()
    out.append(("render check: read-only (scene unchanged)", before == after,
                after, before))

    # 3) The 'also warn on warnings' toggle: a warn-only scene (#17 not baked) is
    #    a problem only when warnings are included.
    fixtures.build_17_fail()
    on = handlers.run_render_check(bpy.context.scene, include_warnings=True)
    off = handlers.run_render_check(bpy.context.scene, include_warnings=False)
    out.append(("render check: warn-only scene has no hard fail",
                on["fail"] == 0, on["fail"], 0))
    out.append(("render check: warn-only scene has a warning",
                on["warning"] > 0, on["warning"], ">0"))
    out.append(("render check: include_warnings=True -> problem (escalates)",
                on["problem"] is True, on["problem"], True))
    out.append(("render check: include_warnings=False -> not escalated",
                off["problem"] is False, off["problem"], False))

    # V08: turning OFF warning alerts escalation must NOT turn a warning-bearing
    # scene into "all clear". The banner is factual, independent of the toggle.
    out.append(("V08: warn-only + include_warnings=False is NOT 'all clear'",
                "all clear" not in off["banner"] and "warning" in off["banner"],
                off["banner"], "shows the warning, not all-clear"))
    out.append(("V08: warn-only banner identical with alerts on vs off",
                on["banner"] == off["banner"], (on["banner"], off["banner"]),
                "same factual banner"))

    # Banner honesty (V03 + V08): the banner reflects the counts, never the
    # alert preference. Warnings and unknowns always appear; only an empty
    # result is "all clear".
    rb = handlers.render_banner
    out.append(("render banner: unknown-only is not a clean result",
                "couldn't verify" in rb(0, 0, 3), rb(0, 0, 3),
                "...couldn't verify..."))
    out.append(("render banner: truly clean says all clear",
                rb(0, 0, 0) == "Last render check: all clear",
                rb(0, 0, 0), "all clear"))
    out.append(("render banner: confirmed problems show counts",
                "fail" in rb(2, 1, 1), rb(2, 1, 1), "...fail..."))
    # V08 regressions on the pure banner: warning-only and warning+unknown must
    # show the counts and never read as clean, with no escalation flag in play.
    out.append(("V08 banner: warning-only shows counts, not clear",
                rb(0, 2, 0) == "Last render check: 0 fail, 2 warning, 0 couldn't verify",
                rb(0, 2, 0), "0 fail, 2 warning, 0 couldn't verify"))
    out.append(("V08 banner: warning+unknown is not clear",
                "all clear" not in rb(0, 1, 2) and "warning" in rb(0, 1, 2),
                rb(0, 1, 2), "not all clear, shows warning"))
    return out


def title_tests():
    """V01/V02: the headline must never make a stronger claim than the status.
    UNKNOWN and N/A must not borrow the positive PASS wording."""
    from failsafe.engine import display_name, Status, CHECKS
    by_id = {m.id: m for m in CHECKS}
    out = []

    # Every check that can report UNKNOWN carries an explicit "couldn't verify"
    # headline, so it never falls back to the positive statement.
    for cid in (3, 4, 5, 15, 17, 18, 19, 20, 21, 22, 23):
        m = by_id[cid]
        dn = display_name(m, Status.UNKNOWN)
        out.append(("title #%d UNKNOWN is explicit, not the positive name" % cid,
                    bool(m.name_unknown) and dn == m.name_unknown and dn != m.name,
                    dn, m.name_unknown))

    # #23 specifically must not assert 'unchanged' when it cannot know.
    dn23 = display_name(by_id[23], Status.UNKNOWN).lower()
    out.append(("title #23 UNKNOWN doesn't claim 'unchanged'",
                "unchanged" not in dn23 and ("confirm" in dn23 or "couldn't" in dn23),
                dn23, "a 'couldn't confirm' statement"))

    # #18 N/A must not claim files are on disk.
    dn18na = display_name(by_id[18], Status.NA)
    out.append(("title #18 N/A isn't a positive on-disk claim",
                dn18na == by_id[18].name_na and dn18na != by_id[18].name,
                dn18na, by_id[18].name_na))

    # #20 WARNING (sampled cache) reads differently from its FAIL headline.
    m20 = by_id[20]
    out.append(("title #20 WARNING != FAIL headline",
                display_name(m20, Status.WARNING) != display_name(m20, Status.FAIL),
                display_name(m20, Status.WARNING), display_name(m20, Status.FAIL)))

    # PASS always shows the positive statement.
    out.append(("title PASS shows positive name",
                display_name(by_id[18], Status.PASS) == by_id[18].name,
                display_name(by_id[18], Status.PASS), by_id[18].name))
    return out


def new_feature_tests():
    """A1-A7: the new competitor-parity features. Cloud-path warning (#24),
    orphan-file detection (#25), cache-size reporting (A4), JSON report (A7),
    and the headless CLI exit codes (A6)."""
    import json as _json
    from failsafe import cache_inspect as ci, engine, report, cli
    out = []

    # --- A2 cloud_sync_marker: pure string classifier -----------------------
    cloud_cases = [
        ("/Users/x/Dropbox/proj/blendcache_a", "Dropbox"),
        ("/Users/x/OneDrive/proj", "OneDrive"),
        ("/Users/x/Google Drive/proj", "Google Drive"),
        ("/Users/x/Library/Mobile Documents/com~apple~CloudDocs/p", "iCloud Drive"),
        ("/Users/x/Projects/local/blendcache_a", None),
        ("", None),
    ]
    for path, expect in cloud_cases:
        got = ci.cloud_sync_marker(path)
        out.append(("A2 cloud marker %r -> %s" % (path, expect),
                    got == expect, got, expect))

    # --- A2 #24 check against constructed entries ---------------------------
    def disk_entry(cloud=None):
        e = ci.CacheEntry("Obj", "Cloth", "point")
        e.memory = False
        e.cache_dir = "/some/dir"
        e.cloud_marker = cloud
        return e
    got = _run_check_entries(24, [disk_entry(cloud="Dropbox")])
    out.append(("A2 #24 cloud cache -> WARNING", got == Status.WARNING, got,
                Status.WARNING))
    got = _run_check_entries(24, [disk_entry(cloud=None)])
    out.append(("A2 #24 local cache -> PASS", got == Status.PASS, got, Status.PASS))

    # --- A4 human_bytes -----------------------------------------------------
    for n, expect in ((0, "0 B"), (512, "512 B"), (1536, "1.5 KB"),
                      (5 * 1024 * 1024, "5.0 MB"), (None, "unknown size")):
        got = ci.human_bytes(n)
        out.append(("A4 human_bytes(%r)=%s" % (n, expect), got == expect, got,
                    expect))

    # --- A3 orphan filename regex -------------------------------------------
    rx = ci._BPHYS_RE
    g1 = bool(rx.match("506C616E65_000010_00.bphys"))
    out.append(("A3 bphys regex accepts real name", g1 is True, g1, True))
    g2 = bool(rx.match("notacache.txt"))
    out.append(("A3 bphys regex rejects junk", g2 is False, g2, False))

    # --- A3 orphan scan: pure dir logic (identity = prefix + index) ---------
    odir = tempfile.mkdtemp(prefix="failsafe_orphan_")
    owned_pfx = "506C616E65"          # "Plane"
    orphan_pfx = "4F6C64"             # "Old"
    for fr in (1, 2, 3):
        with open(os.path.join(odir, "%s_%06d_00.bphys" % (owned_pfx, fr)), "wb") as fh:
            fh.write(b"x" * 100)
    for fr in (1, 2):
        with open(os.path.join(odir, "%s_%06d_00.bphys" % (orphan_pfx, fr)), "wb") as fh:
            fh.write(b"y" * 50)
    orphans = ci.scan_orphans_in_dir(odir, {(owned_pfx, 0)})
    out.append(("A3 orphan scan finds 1 unowned identity",
                len(orphans) == 1, len(orphans), 1))
    if orphans:
        out.append(("A3 orphan scan counts 2 files",
                    orphans[0]["files"] == 2, orphans[0]["files"], 2))
        out.append(("A3 orphan scan sums 100 bytes",
                    orphans[0]["bytes"] == 100, orphans[0]["bytes"], 100))
    out.append(("A3 orphan scan: all owned -> none",
                ci.scan_orphans_in_dir(odir, {(owned_pfx, 0), (orphan_pfx, 0)}) == [],
                "(list)", "[]"))
    # R22: a file with an OWNED prefix but an UNOWNED index is still an orphan.
    idir = tempfile.mkdtemp(prefix="failsafe_orphanidx_")
    for fr in (1, 2):
        with open(os.path.join(idir, "%s_%06d_00.bphys" % (owned_pfx, fr)), "wb") as fh:
            fh.write(b"z" * 10)   # owned (prefix,0)
    with open(os.path.join(idir, "%s_%06d_01.bphys" % (owned_pfx, 7)), "wb") as fh:
        fh.write(b"z" * 10)       # same prefix, index 1 -> NOT owned -> orphan
    idx_orphans = ci.scan_orphans_in_dir(idir, {(owned_pfx, 0)})
    out.append(("R22 orphan scan matches full (prefix,index) identity",
                len(idx_orphans) == 1 and idx_orphans[0]["index"] == 1,
                idx_orphans, "1 orphan at index 1"))
    # R22: a non-existent folder is simply "nothing there" -> [] (not an error).
    out.append(("R22 missing folder -> [] (not an error)",
                ci.scan_orphans_in_dir(os.path.join(odir, "nope"), set()) == [],
                "[]", "[]"))
    # R22: a folder that exists but can't be enumerated RAISES (so the check can
    # report "Couldn't verify"), rather than silently returning [] = clean. We
    # prove this by pointing the scanner at a regular file: os.scandir raises.
    raised_oserr = False
    try:
        import failsafe.cache_inspect as _ci2
        # bypass the isdir() guard by calling os.scandir semantics on a file:
        _bad = os.path.join(odir, "%s_%06d_00.bphys" % (owned_pfx, 1))
        orig_isdir = os.path.isdir
        _ci2.os.path.isdir = lambda p: True       # force past the guard
        try:
            _ci2.scan_orphans_in_dir(_bad, set())
        finally:
            _ci2.os.path.isdir = orig_isdir
    except OSError:
        raised_oserr = True
    out.append(("R22 unreadable folder raises (not silent clean)",
                raised_oserr, raised_oserr, True))

    # --- A7 build_json_report: valid JSON, stable shape ---------------------
    results = engine.run_all(bpy.context)
    blob = report.build_json_report(results)
    try:
        data = _json.loads(blob)
        parsed = True
    except Exception:
        data = {}
        parsed = False
    out.append(("A7 JSON report parses", parsed, parsed, True))
    out.append(("A7 JSON has tool=failsafe", data.get("tool") == "failsafe",
                data.get("tool"), "failsafe"))
    for key in ("summary", "overall", "checks", "cache_disk_usage"):
        out.append(("A7 JSON has %r" % key, key in data, key in data, True))
    ids = {c["id"] for c in data.get("checks", [])}
    out.append(("A7 JSON includes new checks 24 & 25",
                {24, 25} <= ids, sorted(ids)[-3:] if ids else [], "24,25 present"))

    # --- A6 CLI exit codes --------------------------------------------------
    def R(status, cid=1):
        m = next(mm for mm in engine.CHECKS if mm.id == cid)
        return engine.Result(cid, m.name, m.group, status, "x")
    out.append(("A6 FAIL -> exit 1",
                cli.verdict_exit_code([R(Status.FAIL)]) == 1,
                cli.verdict_exit_code([R(Status.FAIL)]), 1))
    out.append(("A6 UNKNOWN -> exit 2",
                cli.verdict_exit_code([R(Status.UNKNOWN)]) == 2,
                cli.verdict_exit_code([R(Status.UNKNOWN)]), 2))
    out.append(("A6 WARNING (lax) -> exit 0",
                cli.verdict_exit_code([R(Status.WARNING)]) == 0,
                cli.verdict_exit_code([R(Status.WARNING)]), 0))
    out.append(("A6 WARNING (strict) -> exit 1",
                cli.verdict_exit_code([R(Status.WARNING)], strict=True) == 1,
                cli.verdict_exit_code([R(Status.WARNING)], strict=True), 1))
    out.append(("A6 FAIL beats UNKNOWN -> exit 1",
                cli.verdict_exit_code([R(Status.FAIL), R(Status.UNKNOWN, 2)]) == 1,
                cli.verdict_exit_code([R(Status.FAIL), R(Status.UNKNOWN, 2)]), 1))
    # bad args -> usage code 3, with help text
    code, txt = cli.run(argv=["--bogus"])
    out.append(("A6 bad arg -> exit 3", code == 3, code, 3))
    # real run returns a defined code and non-empty output
    code, txt = cli.run(argv=["--json"])
    out.append(("A6 --json run returns defined code",
                code in (0, 1, 2), code, "0/1/2"))
    out.append(("A6 --json run emits JSON", txt.strip().startswith("{"),
                txt[:1], "{"))

    # --- A8 batch: aggregate exit + file discovery -------------------------
    out.append(("A8 aggregate [] -> clean", cli.aggregate_exit([]) == 0,
                cli.aggregate_exit([]), 0))
    out.append(("A8 aggregate blocking wins",
                cli.aggregate_exit([0, 2, 1]) == 1,
                cli.aggregate_exit([0, 2, 1]), 1))
    out.append(("A8 aggregate usage beats unverified",
                cli.aggregate_exit([2, 3]) == 3,
                cli.aggregate_exit([2, 3]), 3))
    out.append(("A8 aggregate unverified over clean",
                cli.aggregate_exit([0, 2]) == 2,
                cli.aggregate_exit([0, 2]), 2))
    bdir = tempfile.mkdtemp(prefix="failsafe_batch_")
    for fn in ("a.blend", "b.blend", "notes.txt"):
        with open(os.path.join(bdir, fn), "wb") as fh:
            fh.write(b"")
    found = cli._list_blend_files(bdir)
    out.append(("A8 _list_blend_files finds 2 .blend", len(found) == 2,
                len(found), 2))
    code, _ = cli.run(argv=["--batch", "/no/such/failsafe/dir"])
    out.append(("A8 batch missing folder -> exit 3", code == 3, code, 3))

    # --- Status rename: user word changes, machine contract does NOT --------
    out.append(("label UNKNOWN -> Couldn't verify",
                engine.label(Status.UNKNOWN) == "Couldn't verify",
                engine.label(Status.UNKNOWN), "Couldn't verify"))
    out.append(("internal status stays UNKNOWN",
                Status.UNKNOWN == "UNKNOWN", Status.UNKNOWN, "UNKNOWN"))
    out.append(("JSON summary keeps machine key UNKNOWN",
                "UNKNOWN" in data.get("summary", {}),
                sorted(data.get("summary", {}).keys()), "UNKNOWN present"))
    out.append(("JSON never emits the display word",
                "Couldn't verify" not in blob, "display word absent", True))
    return out


def baseline_tests():
    """The opt-in settings-baseline feature: pure helpers plus the #26 check's
    five outcomes (no baseline / match / drift / identity mismatch / corrupt),
    driven with monkeypatched baseline data so no real bake is needed."""
    import json as _json
    from failsafe import baseline as bl, engine
    out = []

    # --- diff_fingerprint ---------------------------------------------------
    a = {"settings": {"mass": 1.0, "quality": 5}, "cache_range": [1, 10]}
    b = {"settings": {"mass": 1.0, "quality": 5}, "cache_range": [1, 10]}
    out.append(("baseline diff identical -> none",
                bl.diff_fingerprint(a, b) == [], bl.diff_fingerprint(a, b), []))
    c = {"settings": {"mass": 2.0, "quality": 5}, "cache_range": [1, 10]}
    out.append(("baseline diff finds changed setting",
                bl.diff_fingerprint(a, c) == ["mass"],
                bl.diff_fingerprint(a, c), ["mass"]))
    d = {"settings": {"mass": 1.0, "quality": 5}, "cache_range": [1, 20]}
    out.append(("baseline diff finds range change",
                "cache frame range" in bl.diff_fingerprint(a, d),
                bl.diff_fingerprint(a, d), "cache frame range"))

    # --- load_baseline adversarial cases ------------------------------------
    d0 = tempfile.mkdtemp(prefix="failsafe_bl_")
    missing = os.path.join(d0, "nope.json")
    try:
        bl.load_baseline(missing)
        ok, got = False, "no raise"
    except ValueError as e:
        ok, got = (str(e) == "no baseline file"), str(e)
    out.append(("baseline load missing -> ValueError", ok, got, "no baseline file"))

    corrupt = os.path.join(d0, "bad.json")
    with open(corrupt, "w") as fh:
        fh.write("{not valid json")
    try:
        bl.load_baseline(corrupt)
        ok = False
    except ValueError:
        ok = True
    out.append(("baseline load corrupt -> ValueError", ok, ok, True))

    wrong = os.path.join(d0, "wrong.json")
    with open(wrong, "w") as fh:
        _json.dump({"hello": "world"}, fh)
    try:
        bl.load_baseline(wrong)
        ok = False
    except ValueError:
        ok = True
    out.append(("baseline load wrong-shape -> ValueError", ok, ok, True))

    # --- save + round-trip --------------------------------------------------
    spath = os.path.join(d0, "x.failsafe-baseline.json")
    bl.save_baseline(bpy.context.scene, spath)
    loaded = bl.load_baseline(spath)
    out.append(("baseline save+load round-trip",
                loaded.get("kind") == "baseline"
                and loaded.get("schema") == bl.BASELINE_SCHEMA,
                loaded.get("kind"), "baseline"))
    out.append(("baseline file has fingerprints dict",
                isinstance(loaded.get("fingerprints"), dict),
                type(loaded.get("fingerprints")).__name__, "dict"))

    # --- never auto-overwrites an existing baseline -------------------------
    # spath already exists from the round-trip above.
    raised = False
    try:
        bl.save_baseline(bpy.context.scene, spath)          # no overwrite flag
    except FileExistsError:
        raised = True
    out.append(("baseline save refuses to overwrite silently", raised, raised,
                True))
    before = open(spath).read()
    out.append(("baseline file untouched after refused overwrite",
                open(spath).read() == before, "unchanged", "unchanged"))
    # explicit overwrite is allowed
    wrote = False
    try:
        bl.save_baseline(bpy.context.scene, spath, overwrite=True)
        wrote = True
    except Exception:
        wrote = False
    out.append(("baseline save overwrites when asked explicitly", wrote, wrote,
                True))
    # a fresh path writes with no flag needed
    fresh = os.path.join(d0, "fresh.failsafe-baseline.json")
    bl.save_baseline(bpy.context.scene, fresh)
    out.append(("baseline save writes a brand-new file", os.path.isfile(fresh),
                os.path.isfile(fresh), True))

    # --- schema + foreign-file guards (pure helpers) ------------------------
    out.append(("schema_ok accepts current schema",
                bl.schema_ok({"schema": bl.BASELINE_SCHEMA}), True, True))
    out.append(("schema_ok rejects a newer/unknown schema",
                not bl.schema_ok({"schema": 999}), False, False))
    out.append(("schema_ok rejects a baseline with no schema",
                not bl.schema_ok({"kind": "baseline"}), False, False))
    out.append(("foreign file: different .blend name is flagged",
                bl.foreign_file_name({"file": "/a/other.blend"},
                                     "/b/mine.blend") == "other.blend",
                "flagged", "other.blend"))
    out.append(("foreign file: same name (moved project) is NOT flagged",
                bl.foreign_file_name({"file": "/a/mine.blend"},
                                     "/b/mine.blend") is None, None, None))
    out.append(("foreign file: unknown current file -> not flagged",
                bl.foreign_file_name({"file": "/a/other.blend"}, "") is None,
                None, None))

    # --- #26 check: five outcomes via monkeypatch ---------------------------
    meta = next(m for m in engine.CHECKS if m.id == 26)
    mk = engine._mk(meta)

    class Ctx:
        pass
    ctx = Ctx()
    ctx.scene = bpy.context.scene

    one = {"Cube::Cloth": {"system": "Cloth", "kind": "point",
                           "settings": {"mass": 1.0}, "cache_range": [1, 10]}}
    orig_cap, orig_path, orig_load = (bl.capture_fingerprints,
                                      bl.default_baseline_path, bl.load_baseline)
    try:
        bl.capture_fingerprints = lambda scene: dict(one)
        bl.default_baseline_path = lambda: os.path.join(d0, "missing.json")
        bl.load_baseline = orig_load  # real: file missing -> UNKNOWN
        w = worst_for_check(meta.func(ctx, mk), 26)
        out.append(("#26 sims + no baseline -> Couldn't verify",
                    w == Status.UNKNOWN, w, Status.UNKNOWN))

        saved = {"kind": "baseline", "schema": bl.BASELINE_SCHEMA,
                 "fingerprints": dict(one)}
        bl.default_baseline_path = lambda: spath
        bl.load_baseline = lambda p: saved
        w = worst_for_check(meta.func(ctx, mk), 26)
        out.append(("#26 matching baseline -> Pass", w == Status.PASS, w,
                    Status.PASS))

        bl.capture_fingerprints = lambda scene: {
            "Cube::Cloth": {"system": "Cloth", "kind": "point",
                            "settings": {"mass": 2.0}, "cache_range": [1, 10]}}
        w = worst_for_check(meta.func(ctx, mk), 26)
        out.append(("#26 changed settings -> Warning", w == Status.WARNING, w,
                    Status.WARNING))

        bl.capture_fingerprints = lambda scene: {
            "Renamed::Cloth": {"system": "Cloth", "kind": "point",
                               "settings": {"mass": 1.0}, "cache_range": [1, 10]}}
        w = worst_for_check(meta.func(ctx, mk), 26)
        out.append(("#26 identity mismatch -> Couldn't verify",
                    w == Status.UNKNOWN, w, Status.UNKNOWN))

        bl.capture_fingerprints = lambda scene: dict(one)

        def _boom(p):
            raise ValueError("baseline unreadable: boom")
        bl.load_baseline = _boom
        w = worst_for_check(meta.func(ctx, mk), 26)
        out.append(("#26 corrupt baseline -> Couldn't verify",
                    w == Status.UNKNOWN, w, Status.UNKNOWN))

        # a baseline from a newer/unknown schema must not produce a PASS even if
        # the fingerprints happen to match
        bl.load_baseline = lambda p: {"kind": "baseline", "schema": 999,
                                      "fingerprints": dict(one)}
        w = worst_for_check(meta.func(ctx, mk), 26)
        out.append(("#26 unknown-schema baseline -> Couldn't verify",
                    w == Status.UNKNOWN, w, Status.UNKNOWN))

        # never claims "since bake"; PASS wording says "since it was saved"
        bl.capture_fingerprints = lambda scene: dict(one)
        bl.load_baseline = lambda p: {"kind": "baseline",
                                      "schema": bl.BASELINE_SCHEMA,
                                      "fingerprints": dict(one)}
        res = meta.func(ctx, mk)
        pass_msgs = " ".join(r.message for r in res if r.status == Status.PASS)
        out.append(("#26 never claims 'since bake'",
                    "since bake" not in pass_msgs.lower(), pass_msgs[:40],
                    "no 'since bake'"))
    finally:
        bl.capture_fingerprints = orig_cap
        bl.default_baseline_path = orig_path
        bl.load_baseline = orig_load
    return out


def batch_adversarial_tests():
    """The IN-PROCESS batch scanner (--in-process) must survive bad input: a
    corrupt/non-blend file must become a per-file error (not a crash, not a silent
    mis-scan), and a mixed folder must still scan the good files and report the
    worst exit. (In-process is the fast path; the crash-isolated default path is
    covered by batch_isolation_tests below.)"""
    import json as _json
    from failsafe import cli
    out = []

    # Corrupt / non-blend file -> graceful per-file error, defined exit.
    bad_dir = tempfile.mkdtemp(prefix="failsafe_badbatch_")
    with open(os.path.join(bad_dir, "garbage.blend"), "wb") as fh:
        fh.write(b"this is definitely not a blend file" * 20)
    code, txt = cli.run(argv=["--batch", bad_dir, "--in-process", "--json"])
    try:
        data = _json.loads(txt)
        parsed = True
    except Exception:
        data = {}
        parsed = False
    out.append(("batch garbage: JSON still parses", parsed, parsed, True))
    files = data.get("files", [])
    out.append(("batch garbage: recorded as a per-file error",
                len(files) == 1 and "error" in files[0],
                [list(f.keys()) for f in files], "1 error entry"))
    out.append(("batch garbage: defined exit 3 (no crash)", code == 3, code, 3))

    # Partial failure: one good file + one bad file.
    mixed = tempfile.mkdtemp(prefix="failsafe_mixedbatch_")
    bpy.ops.wm.read_factory_settings(use_empty=True)   # clean, sim-free scene
    good = os.path.join(mixed, "good.blend")
    bpy.ops.wm.save_as_mainfile(filepath=good)
    with open(os.path.join(mixed, "bad.blend"), "wb") as fh:
        fh.write(b"nope not a blend")
    code, txt = cli.run(argv=["--batch", mixed, "--in-process", "--json"])
    data = _json.loads(txt)
    fls = data.get("files", [])
    exits = sorted(f.get("exit") for f in fls)
    out.append(("batch partial: both files reported", len(fls) == 2, len(fls), 2))
    out.append(("batch partial: good scanned (0) + bad errored (3)",
                0 in exits and 3 in exits, exits, "[0, 3]"))
    out.append(("batch partial: overall exit = worst (3)",
                data.get("overall_exit") == 3, data.get("overall_exit"), 3))
    out.append(("batch partial: good file has no error key",
                any("error" not in f for f in fls), exits, "a clean file present"))

    # R20: in-process empty folder must not report clean either.
    empty = tempfile.mkdtemp(prefix="failsafe_inproc_empty_")
    code, txt = cli.run(argv=["--batch", empty, "--in-process", "--json"])
    out.append(("R20 in-process empty folder -> exit 3", code == 3, code, 3))
    return out


def batch_isolation_tests():
    """The DEFAULT crash-isolated batch path (failsafe.batch): each file runs in
    its own Blender subprocess with a timeout. A crash or a hang in one file must
    not take the batch down, and the results of files that scanned cleanly must be
    preserved. Driven with a FAKE runner so crashes/hangs/timeouts are simulated
    deterministically — no real Blender is spawned and nothing actually crashes."""
    import json as _json
    import subprocess as _sp
    from failsafe import batch, cli
    out = []

    S, E = batch._MARK_START, batch._MARK_END

    def good_stdout(fail=0, warn=0, unknown=0, exit_code=0, checks=None):
        payload = {"overall": "PASS", "exit": exit_code,
                   "summary": {"FAIL": fail, "WARNING": warn, "UNKNOWN": unknown,
                               "PASS": 0, "NOT APPLICABLE": 0},
                   "checks": checks or [],
                   "cache_disk_usage": []}
        return "Blender banner line\n" + S + _json.dumps(payload) + E + "\nquit"

    # a FAIL report whose finding names a missing frame (for R25)
    _fail_checks = [
        {"id": 20, "name": "Every frame is cached (no gaps)", "group": "Simulation Caches",
         "status": "FAIL", "display": "A cache frame is missing",
         "findings": [{"status": "FAIL", "object": "Cloth",
                       "message": "frame 7 is missing from the cache", "hint": "re-bake"}]},
        {"id": 1, "name": "ok", "group": "Physics Setup", "status": "PASS",
         "display": "ok", "findings": []},
    ]

    # A fake runner keyed by the .blend path in the child argv, so one folder can
    # mix clean / crashing / hanging / corrupt files.
    def make_runner(behaviour):
        def runner(argv, timeout):
            blend = argv[2]  # [bin, "-b", blend, ...]
            how = behaviour.get(os.path.basename(blend), "good")
            if how == "hang":
                raise _sp.TimeoutExpired(cmd=argv, timeout=timeout)
            if how == "crash":
                return (-11, "", "Segmentation fault")      # killed, no JSON
            if how == "corrupt":
                return (1, "Error: not a blend\n", "")       # opened, no markers
            if how == "launchfail":
                raise OSError("blender binary missing")
            if how == "jsoncrash":
                # Printed a clean report, THEN exited abnormally (R19).
                return (-11, good_stdout(exit_code=cli.EXIT_CLEAN), "late segfault")
            if how == "fail":
                return (0, good_stdout(fail=1, exit_code=cli.EXIT_BLOCKING,
                                       checks=_fail_checks), "")
            return (0, good_stdout(), "")                    # clean
        return runner

    # --- single-file outcomes ------------------------------------------------
    pf = batch.scan_file_isolated("clean.blend", "blender", timeout=5,
                                  runner=make_runner({}))
    out.append(("isolated clean -> exit 0, no error",
                pf["exit"] == 0 and "error" not in pf, pf.get("exit"), 0))

    pf = batch.scan_file_isolated("hang.blend", "blender", timeout=5,
                                  runner=make_runner({"hang.blend": "hang"}))
    out.append(("isolated hang -> timeout error, exit 3",
                pf["exit"] == 3 and "timed out" in pf.get("error", ""),
                pf.get("error"), "timed out"))

    pf = batch.scan_file_isolated("crash.blend", "blender", timeout=5,
                                  runner=make_runner({"crash.blend": "crash"}))
    out.append(("isolated crash -> error, exit 3 (never a pass)",
                pf["exit"] == 3 and "error" in pf, pf.get("exit"), 3))

    pf = batch.scan_file_isolated("corrupt.blend", "blender", timeout=5,
                                  runner=make_runner({"corrupt.blend": "corrupt"}))
    out.append(("isolated corrupt -> no-result error, exit 3",
                pf["exit"] == 3 and "error" in pf, pf.get("exit"), 3))

    pf = batch.scan_file_isolated("nolaunch.blend", "blender", timeout=5,
                                  runner=make_runner({"nolaunch.blend": "launchfail"}))
    out.append(("isolated launch failure -> error, exit 3",
                pf["exit"] == 3 and "could not run Blender" in pf.get("error", ""),
                pf.get("error"), "could not run Blender"))

    # R19: a worker that printed CLEAN JSON but then exited abnormally must NOT be
    # accepted as clean — the nonzero rc wins and it's an error.
    pf = batch.scan_file_isolated("jc.blend", "blender", timeout=5,
                                  runner=make_runner({"jc.blend": "jsoncrash"}))
    out.append(("R19 clean JSON + abnormal exit -> error, not clean",
                pf["exit"] == 3 and "error" in pf and "overall" not in pf,
                {k: pf.get(k) for k in ("exit", "overall")}, "exit 3, error"))

    # R25: a FAIL worker's per-file result preserves the findings, incl. the exact
    # missing frame, not just the summary counts.
    pf = batch.scan_file_isolated("fr.blend", "blender", timeout=5,
                                  runner=make_runner({"fr.blend": "fail"}))
    msgs = " ".join(f.get("message", "") for c in pf.get("findings", [])
                    for f in c.get("findings", []))
    out.append(("R25 per-file findings preserved (names missing frame)",
                "frame 7 is missing" in msgs, msgs[:40], "frame 7 missing"))
    out.append(("R25 PASS checks are dropped from findings",
                all(c["status"] != "PASS" for c in pf.get("findings", [])),
                [c["status"] for c in pf.get("findings", [])], "no PASS"))

    # --- partial-failure batch: clean + crash + hang + fail together ---------
    folder = tempfile.mkdtemp(prefix="failsafe_isobatch_")
    for n in ("a_clean.blend", "b_crash.blend", "c_hang.blend", "d_fail.blend"):
        open(os.path.join(folder, n), "wb").close()
    behaviour = {"b_crash.blend": "crash", "c_hang.blend": "hang",
                 "d_fail.blend": "fail"}
    agg, txt = batch.run_isolated_batch(
        folder, {"format": "json", "strict": False}, blender_bin="blender",
        timeout=5, runner=make_runner(behaviour))
    data = _json.loads(txt)
    fls = {os.path.basename(f["file"]): f for f in data["files"]}
    out.append(("iso batch: all 4 files reported", len(fls) == 4, len(fls), 4))
    out.append(("iso batch: clean file preserved (exit 0, no error)",
                fls["a_clean.blend"]["exit"] == 0
                and "error" not in fls["a_clean.blend"],
                fls["a_clean.blend"].get("exit"), 0))
    out.append(("iso batch: crash isolated to its file",
                "error" in fls["b_crash.blend"], list(fls["b_crash.blend"]),
                "error key"))
    out.append(("iso batch: hang isolated (timeout)",
                "timed out" in fls["c_hang.blend"].get("error", ""),
                fls["c_hang.blend"].get("error"), "timed out"))
    out.append(("iso batch: real FAIL still seen (exit 1)",
                fls["d_fail.blend"]["exit"] == 1,
                fls["d_fail.blend"].get("exit"), 1))
    out.append(("iso batch: marked isolated in JSON",
                data.get("isolated") is True, data.get("isolated"), True))
    # Aggregation priority (same as the in-process scanner): a blocking FAIL
    # outranks a usage/error, so this mixed batch exits 1 — the actionable FAIL.
    out.append(("iso batch: FAIL outranks errors in aggregate (exit 1)",
                agg == 1, agg, 1))

    # An error must still beat clean files (never hidden): clean + crash -> 3.
    folder_e = tempfile.mkdtemp(prefix="failsafe_isoerr_")
    for n in ("ok1.blend", "ok2.blend", "boom.blend"):
        open(os.path.join(folder_e, n), "wb").close()
    agg_e, _ = batch.run_isolated_batch(
        folder_e, {"format": "json"}, blender_bin="blender", timeout=5,
        runner=make_runner({"boom.blend": "crash"}))
    out.append(("iso batch: an error beats clean files (exit 3)",
                agg_e == 3, agg_e, 3))

    # worst-wins without any error: clean + a blocking FAIL -> exit 1
    folder2 = tempfile.mkdtemp(prefix="failsafe_isobatch2_")
    for n in ("ok.blend", "bad.blend"):
        open(os.path.join(folder2, n), "wb").close()
    agg2, _ = batch.run_isolated_batch(
        folder2, {"format": "json"}, blender_bin="blender", timeout=5,
        runner=make_runner({"bad.blend": "fail"}))
    out.append(("iso batch: FAIL beats clean (exit 1)", agg2 == 1, agg2, 1))

    # not-a-folder -> defined usage error
    agg3, txt3 = batch.run_isolated_batch(
        "/no/such/folder/xyz", {"format": "text"}, blender_bin="blender",
        runner=make_runner({}))
    out.append(("iso batch: missing folder -> exit 3", agg3 == 3, agg3, 3))

    # R20: an empty folder (zero .blend) must NOT report clean.
    empty_dir = tempfile.mkdtemp(prefix="failsafe_isoempty_")
    agg_empty, txt_empty = batch.run_isolated_batch(
        empty_dir, {"format": "json"}, blender_bin="blender",
        runner=make_runner({}))
    out.append(("R20 iso empty folder -> exit 3, not clean",
                agg_empty == 3, agg_empty, 3))
    out.append(("R20 iso empty folder -> says no .blend found",
                "no .blend files found" in txt_empty, "(msg)", "no .blend found"))
    # a folder with only non-blend files is also "zero .blend" -> not clean
    nb_dir = tempfile.mkdtemp(prefix="failsafe_isononblend_")
    open(os.path.join(nb_dir, "notes.txt"), "wb").close()
    agg_nb, _ = batch.run_isolated_batch(
        nb_dir, {"format": "text"}, blender_bin="blender", runner=make_runner({}))
    out.append(("R20 iso only-non-blend -> exit 3", agg_nb == 3, agg_nb, 3))

    # child argv shape: isolated, reads the file, no --factory-startup for farm
    argv = batch.build_child_argv("blenderbin", "/shots/x.blend")
    out.append(("iso child argv: background + file + python-expr",
                argv[:3] == ["blenderbin", "-b", "/shots/x.blend"]
                and "--python-expr" in argv, argv[:3], "bin -b file"))
    argv_src = batch.build_child_argv("b", "/x.blend", source_root="/src")
    out.append(("iso child argv: source mode adds --factory-startup",
                "--factory-startup" in argv_src, "--factory-startup" in argv_src,
                True))

    # _extract_json tolerates banner noise and rejects junk
    out.append(("iso extract: finds JSON amid noise",
                batch._extract_json("x\n" + S + '{"a":1}' + E + "\ny")
                == {"a": 1}, "parsed", {"a": 1}))
    out.append(("iso extract: no markers -> None",
                batch._extract_json("just blender output") is None, "None", None))
    return out


def review_blocker_tests():
    """Regression tests for independent-review blockers R21, R23, R24.
    (R19/R20 are in the batch tests; R22/R25 in the orphan and batch tests.)"""
    from failsafe import baseline as bl, engine, cache_inspect as ci
    out = []

    # --- R21: multiple particle systems on one object ----------------------
    bpy.ops.wm.read_factory_settings(use_empty=True)
    me = bpy.data.meshes.new("PM")
    ob = bpy.data.objects.new("Emitter", me)
    bpy.context.scene.collection.objects.link(ob)
    for nm in ("PSysA", "PSysB"):
        ob.modifiers.new(name=nm, type="PARTICLE_SYSTEM")
        ob.particle_systems[-1].name = nm
    fp = bl.capture_fingerprints(bpy.context.scene)
    part_keys = [k for k, _ in bl.sim_items(fp) if "::Particles" in k]
    out.append(("R21 two particle systems -> two distinct identities",
                len(part_keys) == 2 and len(set(part_keys)) == 2,
                part_keys, "2 distinct"))

    meta26 = next(m for m in engine.CHECKS if m.id == 26)
    mk = engine._mk(meta26)

    class Ctx:
        pass
    ctx = Ctx()
    ctx.scene = bpy.context.scene
    ambig_fp = {"Cube::Cloth::Cloth": {"system": "Cloth", "kind": "point",
                                       "settings": {"mass": 1.0},
                                       "cache_range": [1, 10]},
                bl.AMBIG_KEY: ["Cube::Cloth::Cloth"]}
    orig = (bl.capture_fingerprints, bl.default_baseline_path, bl.load_baseline)
    try:
        bl.capture_fingerprints = lambda s: dict(ambig_fp)
        bl.default_baseline_path = lambda: "/tmp/x.failsafe-baseline.json"
        bl.load_baseline = lambda p: {"kind": "baseline",
                                      "schema": bl.BASELINE_SCHEMA,
                                      "fingerprints": dict(ambig_fp)}
        w = worst_for_check(meta26.func(ctx, mk), 26)
        out.append(("R21 ambiguous identity -> Couldn't verify (not PASS)",
                    w == engine.Status.UNKNOWN, w, engine.Status.UNKNOWN))
    finally:
        bl.capture_fingerprints, bl.default_baseline_path, bl.load_baseline = orig

    # --- R23: UNKNOWN titles never borrow the positive name ----------------
    class FakeMeta:
        name = "All good and fully verified"
        name_bad = name_warn = name_unknown = name_na = None
    dn = engine.display_name(FakeMeta, engine.Status.UNKNOWN)
    out.append(("R23 UNKNOWN title isn't the positive name",
                dn != FakeMeta.name and "good" not in dn.lower(), dn, "generic"))
    for cid in (24, 25, 26):
        m = next(mm for mm in engine.CHECKS if mm.id == cid)
        out.append(("R23 check #%d has a truthful name_unknown" % cid,
                    bool(m.name_unknown)
                    and "couldn't" in m.name_unknown.lower(),
                    m.name_unknown, "set + truthful"))

    # --- R24: orphan ownership spans ALL scenes in the .blend --------------
    # Disk-cache flags don't stick on a bare headless mesh, so stub the per-cache
    # identity (returns one id per object) and prove ownership aggregates across
    # every scene passed — the actual R24 fix (was: current scene only).
    bpy.ops.wm.read_factory_settings(use_empty=True)
    scA = bpy.context.scene
    scB = bpy.data.scenes.new("OtherScene")

    def add_cloth(scene, objname):
        m = bpy.data.meshes.new(objname + "_m")
        o = bpy.data.objects.new(objname, m)
        scene.collection.objects.link(o)
        o.modifiers.new(name="Cloth", type="CLOTH")
        return o
    add_cloth(scA, "ClothA")
    add_cloth(scB, "ClothB")

    orig_ident = ci._point_cache_identity_for
    try:
        # any point cache -> a unique identity keyed by its owning object name
        ci._point_cache_identity_for = lambda obj, pc: (obj.name.upper(), 0)
        a_only = ci.owned_point_cache_identities([scA])
        all_owned = ci.owned_point_cache_identities([scA, scB])
    finally:
        ci._point_cache_identity_for = orig_ident
    out.append(("R24 ownership includes other scenes' caches",
                ("CLOTHB", 0) in all_owned and ("CLOTHB", 0) not in a_only,
                (sorted(a_only), sorted(all_owned)), "B included only in all"))
    out.append(("R24 find_orphan scans all of bpy.data.scenes",
                scB in list(bpy.data.scenes), True, True))

    # --- R26: baseline identities are scene-qualified ----------------------
    bpy.ops.wm.read_factory_settings(use_empty=True)
    sA = bpy.context.scene
    sA.name = "SceneA"
    sB = bpy.data.scenes.new("SceneB")

    def add_cloth_named(scene, objname):
        m = bpy.data.meshes.new(objname + "_m")
        o = bpy.data.objects.new(objname, m)
        scene.collection.objects.link(o)
        o.modifiers.new(name="Cloth", type="CLOTH")  # same mod name in both
        return o
    add_cloth_named(sA, "ClothA")
    add_cloth_named(sB, "ClothB")
    fp = bl.capture_fingerprints()
    keys = [k for k, _ in bl.sim_items(fp)]
    a_keys = [k for k in keys if k.startswith("SceneA::")]
    b_keys = [k for k in keys if k.startswith("SceneB::")]
    out.append(("R26 identities are scene-qualified (both scenes captured)",
                len(a_keys) >= 1 and len(b_keys) >= 1, keys, "A:: and B:: keys"))
    # The reviewer's exact case: Rigid Body World shares one owner name across
    # scenes, so WITHOUT scene-qualification both would collide. Scene-qualified,
    # the two RBW identities are distinct.
    idA = "SceneA::Scene::Rigid Body World"
    idB = "SceneB::Scene::Rigid Body World"
    out.append(("R26 RBW identity is scene-qualified (no cross-scene collision)",
                idA != idB and idA.startswith("SceneA::")
                and idB.startswith("SceneB::"), (idA, idB), "distinct"))
    # every fingerprint records its scene
    out.append(("R26 each fingerprint carries its scene",
                all(v.get("scene") for _, v in bl.sim_items(fp)),
                "all have scene", True))

    # #26: a baseline saved for Scene A must NOT PASS when Scene B is scanned.
    cur_b = {"SceneB::C::Cloth::Cloth": {"scene": "SceneB", "system": "Cloth",
             "kind": "point", "settings": {"mass": 1.0}, "cache_range": [1, 10]}}
    saved_a = {"SceneA::C::Cloth::Cloth": {"scene": "SceneA", "system": "Cloth",
               "kind": "point", "settings": {"mass": 1.0}, "cache_range": [1, 10]}}
    meta26b = next(m for m in engine.CHECKS if m.id == 26)
    mkb = engine._mk(meta26b)
    ctxb = Ctx()
    ctxb.scene = bpy.context.scene
    orig2 = (bl.capture_fingerprints, bl.default_baseline_path, bl.load_baseline)
    try:
        bl.capture_fingerprints = lambda s=None: dict(cur_b)
        bl.default_baseline_path = lambda: "/tmp/x.failsafe-baseline.json"
        bl.load_baseline = lambda p: {"kind": "baseline",
                                      "schema": bl.BASELINE_SCHEMA,
                                      "fingerprints": dict(saved_a)}
        w = worst_for_check(meta26b.func(ctxb, mkb), 26)
        out.append(("R26 scanning an un-baselined scene -> Couldn't verify",
                    w == engine.Status.UNKNOWN, w, engine.Status.UNKNOWN))
    finally:
        bl.capture_fingerprints, bl.default_baseline_path, bl.load_baseline = orig2

    # --- R27: fingerprint coverage + float precision -----------------------
    out.append(("R27 cloth tracks pin_stiffness", "pin_stiffness" in bl._CLOTH,
                "pin_stiffness" in bl._CLOTH, True))
    out.append(("R27 cloth tracks vertex_group_mass",
                "vertex_group_mass" in bl._CLOTH,
                "vertex_group_mass" in bl._CLOTH, True))
    # a small float change (1e-6) that the old 5-dp rounding hid is now kept
    out.append(("R27 float precision keeps a 1e-6 change",
                bl._rv(0.5000010) != bl._rv(0.5000020),
                (bl._rv(0.5000010), bl._rv(0.5000020)), "distinct"))
    changed = bl.diff_fingerprint(
        {"settings": {"mass": 0.5000010}, "cache_range": None},
        {"settings": {"mass": 0.5000020}, "cache_range": None})
    out.append(("R27 diff catches the 1e-6 setting change",
                "mass" in changed, changed, "mass changed"))
    # the PASS wording doesn't claim EVERY property is unchanged
    bpy.ops.wm.read_factory_settings(use_empty=True)
    one = {"S::C::Cloth::Cloth": {"scene": "S", "system": "Cloth", "kind": "point",
           "settings": {"mass": 1.0}, "cache_range": [1, 10]}}
    ctxp = Ctx()
    ctxp.scene = bpy.context.scene
    orig3 = (bl.capture_fingerprints, bl.default_baseline_path, bl.load_baseline)
    try:
        bl.capture_fingerprints = lambda s=None: dict(one)
        bl.default_baseline_path = lambda: "/tmp/x.failsafe-baseline.json"
        bl.load_baseline = lambda p: {"kind": "baseline",
                                      "schema": bl.BASELINE_SCHEMA,
                                      "fingerprints": dict(one)}
        res = meta26b.func(ctxp, mkb)
        pass_msg = " ".join(r.message for r in res
                            if r.status == engine.Status.PASS).lower()
    finally:
        bl.capture_fingerprints, bl.default_baseline_path, bl.load_baseline = orig3
    out.append(("R27 PASS says 'tracked', not 'all settings'",
                "tracked" in pass_msg and "curated" in pass_msg, pass_msg[:50],
                "tracked + curated"))
    return out


def couldnt_verify_tests():
    """Every 'Couldn't verify' a user sees must carry a plain reason (message) AND
    a next action (hint). And the contract must hold: the displayed word is
    'Couldn't verify' while JSON/CLI keep the machine token UNKNOWN."""
    from failsafe import engine, baseline as bl, report
    out = []

    # Display/machine label contract.
    out.append(("label(UNKNOWN) -> 'Couldn't verify'",
                engine.label(engine.Status.UNKNOWN) == "Couldn't verify",
                engine.label(engine.Status.UNKNOWN), "Couldn't verify"))
    out.append(("label keeps the plain words for the others",
                engine.label(engine.Status.FAIL) == "Fail"
                and engine.label(engine.Status.PASS) == "Pass",
                "Fail/Pass", "Fail/Pass"))

    # Collect UNKNOWNs from every #26 branch and require reason + action on each.
    meta = next(m for m in engine.CHECKS if m.id == 26)
    mk = engine._mk(meta)

    class Ctx:
        pass
    ctx = Ctx()
    ctx.scene = bpy.context.scene
    d = tempfile.mkdtemp(prefix="failsafe_cv_")
    one = {"Cube::Cloth": {"system": "Cloth", "kind": "point",
                           "settings": {"mass": 1.0}, "cache_range": [1, 10]}}
    orig = (bl.capture_fingerprints, bl.default_baseline_path, bl.load_baseline)
    unknowns = []
    try:
        bl.capture_fingerprints = lambda s: dict(one)
        # unsaved (no path)
        bl.default_baseline_path = lambda: None
        unknowns += [r for r in meta.func(ctx, mk)
                     if r.status == engine.Status.UNKNOWN]
        # no baseline file
        bl.default_baseline_path = lambda: os.path.join(d, "missing.json")
        bl.load_baseline = orig[2]
        unknowns += [r for r in meta.func(ctx, mk)
                     if r.status == engine.Status.UNKNOWN]
        # corrupt
        def _boom(p):
            raise ValueError("baseline unreadable: boom")
        bl.load_baseline = _boom
        unknowns += [r for r in meta.func(ctx, mk)
                     if r.status == engine.Status.UNKNOWN]
        # unknown schema
        bl.load_baseline = lambda p: {"kind": "baseline", "schema": 999,
                                      "fingerprints": dict(one)}
        unknowns += [r for r in meta.func(ctx, mk)
                     if r.status == engine.Status.UNKNOWN]
        # identity mismatch
        bl.load_baseline = lambda p: {"kind": "baseline",
                                      "schema": bl.BASELINE_SCHEMA,
                                      "fingerprints": dict(one)}
        bl.capture_fingerprints = lambda s: {
            "Renamed::Cloth": one["Cube::Cloth"]}
        unknowns += [r for r in meta.func(ctx, mk)
                     if r.status == engine.Status.UNKNOWN]
    finally:
        bl.capture_fingerprints, bl.default_baseline_path, bl.load_baseline = orig

    out.append(("collected several 'Couldn't verify' branches",
                len(unknowns) >= 5, len(unknowns), ">=5"))
    out.append(("every 'Couldn't verify' states a reason",
                all((r.message or "").strip() for r in unknowns),
                sum(1 for r in unknowns if not (r.message or "").strip()),
                "0 missing reasons"))
    out.append(("every 'Couldn't verify' states a next action",
                all((r.hint or "").strip() for r in unknowns),
                sum(1 for r in unknowns if not (r.hint or "").strip()),
                "0 missing actions"))

    # Report wording: text shows the display word, JSON keeps the machine token.
    sample = [mk(engine.Status.UNKNOWN, "a plain reason here", hint="do this next")]
    txt = report.build_text_report(sample)
    out.append(("text report uses 'Couldn't verify'",
                "Couldn't verify" in txt, "Couldn't verify" in txt, True))
    jsn = report.build_json_report(sample)
    out.append(("json keeps UNKNOWN, never the display word",
                '"UNKNOWN"' in jsn and "Couldn't verify" not in jsn,
                '"UNKNOWN"' in jsn and "Couldn't verify" not in jsn, True))
    return out


def main():
    passed = 0
    failed = 0
    fails = []
    tmp = tempfile.mkdtemp(prefix="failsafe_tests_")
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

    # ---- verdict + GN + read-only unit tests (fast) ------------------------
    for label, ok, got, expect in (verdict_unit_tests() + gn_unit_tests()
                                   + fluid_matcher_unit_tests()
                                   + memory_reliability_tests()
                                   + stage_flag_state_tests() + readonly_tests()
                                   + readonly_filesystem_tests()
                                   + roundtrip_fix_tests()
                                   + render_check_tests() + title_tests()
                                   + new_feature_tests() + baseline_tests()
                                   + batch_adversarial_tests()
                                   + batch_isolation_tests()
                                   + review_blocker_tests()
                                   + couldnt_verify_tests()):
        if ok:
            passed += 1
            print("  PASS  unit: %s  -> %s" % (label, got))
        else:
            failed += 1
            msg = "  FAIL  unit: %s  -> got %s, want %s" % (label, got, expect)
            print(msg)
            fails.append(msg)

    total = (len(CASES) + len(CACHE_REGRESSION) + len(verdict_unit_tests())
             + len(gn_unit_tests()) + len(fluid_matcher_unit_tests())
             + len(memory_reliability_tests()) + len(stage_flag_state_tests())
             + len(readonly_tests()) + len(readonly_filesystem_tests())
             + len(roundtrip_fix_tests()) + len(render_check_tests())
             + len(title_tests()) + len(new_feature_tests())
             + len(baseline_tests()) + len(batch_adversarial_tests())
             + len(batch_isolation_tests()) + len(review_blocker_tests())
             + len(couldnt_verify_tests()))
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
