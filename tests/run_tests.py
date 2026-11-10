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
    from physics_preflight import cache_inspect as ci

    def entry(present, expected=(1, 2, 3, 4, 5), baked=True, empty=(),
              unreadable=(), replay=False, memory=False, determinable=True,
              applicable=True, components=(), sampled=False, step=1,
              outdated=False, skipped=False, baking=False):
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
    from physics_preflight import cache_inspect as ci

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
    e.cache_dir = "/tmp/physpf_gn"
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
    e2.cache_dir = "/tmp/physpf_gn"
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
    from physics_preflight import cache_inspect as ci
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
    from physics_preflight import engine, checks_cache  # noqa: F401
    meta = next(m for m in engine.CHECKS if m.id == cid)
    mk = engine._mk(meta)

    class Ctx:
        pass
    ctx = Ctx()
    ctx.scene = bpy.context.scene
    ctx._physpf_caches = entries
    results = meta.func(ctx, mk)
    return worst_for_check(results, cid)


def memory_reliability_tests():
    """R17: the staleness guards (outdated / frame_skip / baking) must apply to
    MEMORY caches and the Rigid Body World too, not just disk caches. is_outdated
    doesn't flip under headless bake, so we drive the real #17/#19 check logic
    with constructed entries (the exact false-PASS combination from the review)."""
    from physics_preflight import cache_inspect as ci

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
    from physics_preflight import cache_inspect as ci

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
    e.cache_dir = "/tmp/physpf_fluid"
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


def readonly_filesystem_tests():
    """A scan must not WRITE to disk — it only reads cache files. Build a real
    baked soft-body (so there are cache files on disk), snapshot the whole cache
    tree (path -> size, mtime), run every check, and assert nothing changed and
    no file was added or removed."""
    out = []
    outdir = tempfile.mkdtemp(prefix="physpf_ro_fs_")
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

    # ---- verdict + GN + read-only unit tests (fast) ------------------------
    for label, ok, got, expect in (verdict_unit_tests() + gn_unit_tests()
                                   + fluid_matcher_unit_tests()
                                   + memory_reliability_tests()
                                   + stage_flag_state_tests() + readonly_tests()
                                   + readonly_filesystem_tests()):
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
             + len(readonly_tests()) + len(readonly_filesystem_tests()))
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
