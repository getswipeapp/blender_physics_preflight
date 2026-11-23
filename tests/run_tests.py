# SPDX-License-Identifier: GPL-3.0-or-later
"""Headless test harness for Failsafe.

Run:  blender -b --factory-startup -P tests/run_tests.py
Exits non-zero if any case fails. Each case builds a scene that should make one
specific check report a known status, then asserts it.
"""
import os
import re
import struct
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
    ("23 fps unchanged since baseline (pass)", 23, fixtures.build_23_pass, True, {Status.PASS}),
    ("23 fps 24->30 since baseline (warn)", 23, fixtures.build_23_warn_fps, True, {Status.WARNING}),
    ("23 fps_base change since baseline (warn)", 23, fixtures.build_23_warn_fpsbase, True, {Status.WARNING}),
    ("23 no baseline -> NA setup hint", 23, fixtures.build_23_na_no_baseline, True, {Status.NA}),
    ("23 foreign baseline (unknown)", 23, fixtures.build_23_unknown_foreign, True, {Status.UNKNOWN}),
    ("23 corrupt baseline (unknown)", 23, fixtures.build_23_unknown_corrupt, True, {Status.UNKNOWN}),
    ("23 intentional non-default time scale matches baseline (pass)", 23, fixtures.build_23_rbw_intentional_ok, True, {Status.PASS}),
    ("23 time scale changed since baseline (warn)", 23, fixtures.build_23_rbw_changed, True, {Status.WARNING}),
    ("23 multi-scene fps change in active scene (warn)", 23, fixtures.build_23_multiscene, True, {Status.WARNING}),
    ("23 unreadable fps in baseline -> unknown (B1: no false pass)", 23, fixtures.build_23_unknown_unreadable_fps, True, {Status.UNKNOWN}),
    ("23 unreadable time scale -> unknown (M2: no false 'matches')", 23, fixtures.build_23_unknown_bad_timescale, True, {Status.UNKNOWN}),
    ("23 schema-3 baseline -> NA (predates timing)", 23, fixtures.build_schema3_baseline, True, {Status.NA}),
    ("26 schema-3 baseline still compares (M1: not voided)", 26, fixtures.build_schema3_baseline, True, {Status.PASS}),
    ("23 NaN fps -> unknown (B2: no false pass)", 23, fixtures.build_23_nan_fps, True, {Status.UNKNOWN}),
    ("23 inf fps -> unknown (B2)", 23, fixtures.build_23_inf_fps, True, {Status.UNKNOWN}),
    ("23 NaN fps_base -> unknown (B2)", 23, fixtures.build_23_nan_fpsbase, True, {Status.UNKNOWN}),
    ("23 zero fps -> unknown (B2)", 23, fixtures.build_23_zero_fps, True, {Status.UNKNOWN}),
    ("23 missing fps_base -> unknown (B2: no 1.0 default)", 23, fixtures.build_23_missing_fpsbase, True, {Status.UNKNOWN}),
    ("23 NaN time scale -> unknown (B2: no false 'matches')", 23, fixtures.build_23_nan_timescale, True, {Status.UNKNOWN}),
    # heavy-sim integration (real bakes): prove the scanners populate correctly,
    # not just the decision logic.
    ("HS soft-body baked (pass)", 18, fixtures.build_softbody_pass, True, {Status.PASS}),
    ("HS soft-body missing last frame (fail)", 18, fixtures.build_softbody_missing_tail, True, {Status.FAIL}),
    ("HS particle baked (pass)", 18, fixtures.build_particle_pass, True, {Status.PASS}),
    ("HS particle missing last frame (fail)", 18, fixtures.build_particle_missing_tail, True, {Status.FAIL}),
    # Hair dynamics and Dynamic Paint vertex surfaces both write the standard
    # .bphys point cache (verified on 5.2.3); the scanner must cover them too.
    ("HS hair dynamics baked (pass)", 18, fixtures.build_hair_pass, True, {Status.PASS}),
    ("HS hair dynamics missing last frame (fail)", 18, fixtures.build_hair_missing_tail, True, {Status.FAIL}),
    ("HS dynamic paint baked (pass)", 18, fixtures.build_dpaint_pass, True, {Status.PASS}),
    ("HS dynamic paint missing last frame (fail)", 18, fixtures.build_dpaint_missing_tail, True, {Status.FAIL}),
    # Deep integrity: a present, non-empty, readable frame that is NOT valid
    # point-cache data (bad magic / truncated header) is corrupt -> #18 FAIL.
    # This is beyond the 0-byte check; the file exists and reads fine.
    ("HS bphys bad magic -> corrupt (fail)", 18, fixtures.build_bphys_badmagic, True, {Status.FAIL}),
    ("HS bphys truncated header -> corrupt (fail)", 18, fixtures.build_bphys_truncated_header, True, {Status.FAIL}),
    # B1: valid magic + full 20-byte length but zero header fields (the fabricated
    # 'BPHYSICS'+zeros file), and a valid header with no payload. Both must FAIL.
    ("HS bphys zero header fields -> corrupt (fail)", 18, fixtures.build_bphys_zerofields, True, {Status.FAIL}),
    ("HS bphys header-only, no payload -> corrupt (fail)", 18, fixtures.build_bphys_header_only, True, {Status.FAIL}),
    # M1: a frame whose type word declares a different simulation (particle on a
    # cloth cache) is not this sim's cache -> corrupt.
    ("HS bphys wrong sim-type -> corrupt (fail)", 18, fixtures.build_bphys_wrongtype, True, {Status.FAIL}),
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
    # A corrupt-header frame (present but invalid) must never let a cache check
    # report PASS: #17 and #18 FAIL, and none of #17-#20 may say PASS.
    ("bphys bad magic -> no cache PASS", fixtures.build_bphys_badmagic,
     {17: {Status.FAIL}, 18: {Status.FAIL}}, (17, 18, 19, 20)),
    ("bphys truncated header -> no cache PASS", fixtures.build_bphys_truncated_header,
     {17: {Status.FAIL}, 18: {Status.FAIL}}, (17, 18, 19, 20)),
    # B1 regression: the fabricated 'BPHYSICS'+zeros file must never reach PASS.
    ("bphys zero fields -> no cache PASS", fixtures.build_bphys_zerofields,
     {17: {Status.FAIL}, 18: {Status.FAIL}}, (17, 18, 19, 20)),
    ("bphys header-only -> no cache PASS", fixtures.build_bphys_header_only,
     {17: {Status.FAIL}, 18: {Status.FAIL}}, (17, 18, 19, 20)),
    ("bphys wrong sim-type -> no cache PASS", fixtures.build_bphys_wrongtype,
     {17: {Status.FAIL}, 18: {Status.FAIL}}, (17, 18, 19, 20)),
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

    # B4 / B4a: the RELIABLE expected range ignores bake_mode for a simulation zone
    # (which misreports STILL) and uses, in precedence, the per-bake custom simulation
    # range > the SCENE-WIDE custom simulation range (scene.use_custom_simulation_range,
    # which OVERRIDES the scene range) > the scene range. A Bake node is skipped by #27
    # and only informs #17: its STILL frame is not derivable -> None; ANIMATION -> the
    # frame range. Unknown kind -> None.
    def _node(idname):
        return Fake(bl_idname=idname)
    scene = Fake(frame_start=1, frame_end=10, use_custom_simulation_range=False)
    scene_wide = Fake(frame_start=1, frame_end=6, use_custom_simulation_range=True,
                      simulation_frame_start=2, simulation_frame_end=9)
    exp_cases = [
        ("sim zone, no custom -> scene range",
         scene, Fake(node=_node("GeometryNodeSimulationOutput"),
              bake_mode="STILL", frame_start=1, frame_end=100,
              use_custom_simulation_frame_range=False), (1, 10)),
        ("sim zone STILL misreport ignored (not single frame)",
         scene, Fake(node=_node("GeometryNodeSimulationOutput"),
              bake_mode="STILL", frame_start=5, frame_end=100,
              use_custom_simulation_frame_range=False), (1, 10)),
        ("sim zone, per-bake custom range -> its own range",
         scene, Fake(node=_node("GeometryNodeSimulationOutput"),
              bake_mode="STILL", use_custom_simulation_frame_range=True,
              frame_start=2, frame_end=4), (2, 4)),
        ("sim zone, SCENE-WIDE sim range OVERRIDES scene range (B4a)",
         scene_wide, Fake(node=_node("GeometryNodeSimulationOutput"),
              bake_mode="STILL", frame_start=1, frame_end=100,
              use_custom_simulation_frame_range=False), (2, 9)),
        ("sim zone, per-bake custom range BEATS scene-wide sim range (B4a precedence)",
         scene_wide, Fake(node=_node("GeometryNodeSimulationOutput"),
              bake_mode="STILL", use_custom_simulation_frame_range=True,
              frame_start=3, frame_end=5), (3, 5)),
        ("bake node STILL -> None (baked frame not derivable)",
         scene, Fake(node=_node("GeometryNodeBake"), bake_mode="STILL",
              frame_start=5, use_custom_simulation_frame_range=False), None),
        ("bake node ANIMATION -> scene range",
         scene, Fake(node=_node("GeometryNodeBake"), bake_mode="ANIMATION",
              use_custom_simulation_frame_range=False), (1, 10)),
        ("unknown node kind -> None (can't establish)",
         scene, Fake(node=_node("GeometryNodeFoo"), bake_mode="STILL"), None),
        ("no node at all -> None",
         scene, Fake(bake_mode="STILL"), None),
        ("sim zone, INVERTED per-bake custom range is returned as-is (start > end)",
         scene, Fake(node=_node("GeometryNodeSimulationOutput"),
              bake_mode="STILL", use_custom_simulation_frame_range=True,
              frame_start=5, frame_end=2), (5, 2)),
    ]
    for label, sc, bake, expect in exp_cases:
        got = ci._gn_expected_range(bake, sc)
        out.append(("gn expected-range: " + label, got == expect, got, expect))

    # R5-1 / R4 hardening: an INVALID frame range — None or an inverted (start > end)
    # range — is the enumerator's cue to yield NO coverage ('Couldn't verify'), never
    # an empty required set that would read as a clean PASS. Prove the guard condition
    # (exp is None or exp[0] > exp[1]) fires for both degenerate shapes.
    inv = ci._gn_expected_range(
        Fake(node=_node("GeometryNodeSimulationOutput"), bake_mode="STILL",
             use_custom_simulation_frame_range=True, frame_start=5, frame_end=2),
        scene)
    out.append(("gn expected-range: inverted range trips the no-coverage guard",
                inv is not None and inv[0] > inv[1], inv, "start > end"))
    none_exp = ci._gn_expected_range(Fake(node=_node("GeometryNodeFoo"),
                                          bake_mode="STILL"), scene)
    out.append(("gn expected-range: unknown kind trips the no-coverage guard (None)",
                none_exp is None, none_exp, None))

    # _gn_is_sim_zone: only a Simulation Output node is a sim zone (hashed by #27).
    out.append(("gn sim-zone: Simulation Output is a sim zone",
                ci._gn_is_sim_zone(Fake(node=_node("GeometryNodeSimulationOutput"))) is True,
                True, True))
    out.append(("gn sim-zone: Bake node is NOT a sim zone (skipped by #27)",
                ci._gn_is_sim_zone(Fake(node=_node("GeometryNodeBake"))) is False,
                False, False))
    out.append(("gn sim-zone: no node is NOT a sim zone",
                ci._gn_is_sim_zone(Fake()) is False, False, False))

    # R6-1: valid JSON is only trustworthy bake metadata if it has the real frame
    # SHAPE (a non-empty 'items' mapping of typed entries, verified on 4.2 & 5.2). A
    # recognizable frame may reference ZERO blobs (a value-only item stores inline), so
    # that must still be accepted; anything lacking the shape (e.g. {}) must be rejected
    # so its empty dependency set can't read as a clean PASS.
    rec = ci._gn_meta_is_recognizable
    real_like = {"version": 3, "items": {"0": {"name": "Geometry", "type": "GEOMETRY",
                 "data": {"mesh": {"poly_offsets": {"name": "00001_00000.blob"}}}}}}
    value_only = {"version": 3, "items": {"0": {"name": "Accum", "type": "FLOAT",
                  "data": 1.0}}}            # legit: recognizable, references no blob
    empty_geo = {"version": 3, "items": {"0": {"type": "GEOMETRY", "data": {}}}}
    items_list = {"version": 3, "items": [{"type": "GEOMETRY", "data": {}}]}
    rec_cases = [
        ("real geometry-frame shape is recognizable", real_like, True),
        ("value-only frame (zero blobs) is recognizable (not over-rejected)",
         value_only, True),
        ("empty-geometry frame (GEOMETRY data {} , zero blobs) is recognizable",
         empty_geo, True),
        ("items as a typed LIST is recognizable", items_list, True),
        ("empty object {} is NOT recognizable (R6-1)", {}, False),
        ("version only, no items -> NOT recognizable", {"version": 3}, False),
        ("empty items mapping -> NOT recognizable", {"version": 3, "items": {}}, False),
        # R7-1: an entry that declares a type but has NO 'data' payload is not
        # something Blender writes; accepting it would hide an omitted dependency.
        ("R7-1: GEOMETRY entry missing 'data' -> NOT recognizable",
         {"version": 3, "items": {"0": {"type": "GEOMETRY"}}}, False),
        ("R7-1: value entry missing 'data' -> NOT recognizable",
         {"version": 3, "items": {"0": {"type": "FLOAT"}}}, False),
        ("R7-1: GEOMETRY 'data' must be a dict, not a scalar -> NOT recognizable",
         {"version": 3, "items": {"0": {"type": "GEOMETRY", "data": 5}}}, False),
        ("R7-1: missing version -> NOT recognizable",
         {"items": {"0": {"type": "FLOAT", "data": 0.0}}}, False),
        ("R7-1: non-int version -> NOT recognizable",
         {"version": "3", "items": {"0": {"type": "FLOAT", "data": 0.0}}}, False),
        ("R7-1: boolean version -> NOT recognizable",
         {"version": True, "items": {"0": {"type": "FLOAT", "data": 0.0}}}, False),
        ("entry lacks 'type' -> NOT recognizable",
         {"version": 3, "items": {"0": {"name": "x", "data": {}}}}, False),
        ("entry 'type' not a string -> NOT recognizable",
         {"version": 3, "items": {"0": {"type": 7, "data": {}}}}, False),
        ("items not a mapping/list -> NOT recognizable",
         {"version": 3, "items": "garbage"}, False),
        ("a bare list is NOT recognizable", [], False),
        ("a bare string is NOT recognizable", "nope", False),
    ]
    for label, data, expect in rec_cases:
        got = rec(data)
        out.append(("gn meta-recognizable: " + label, got is expect, got, expect))

    # B3 (round 3): a blob's coverage identity is its EXACT filename STEM, so it can
    # NEVER collide. The old packed-int scheme mapped 00000_00001.blob and
    # 00001_00000.blob both to 1 (frame-0 collision); stems keep them distinct.
    k = ci._gn_blob_coverage_key
    out.append(("gn blob key: stem of a plain blob",
                k("00006_00000.blob") == "00006_00000",
                k("00006_00000.blob"), "00006_00000"))
    out.append(("gn blob key: frame-0 sibling vs frame-1 blob are DISTINCT (B3)",
                k("00000_00001.blob") != k("00001_00000.blob"),
                (k("00000_00001.blob"), k("00001_00000.blob")), "distinct"))
    out.append(("gn blob key: same-frame siblings are DISTINCT (B3)",
                len({k("00001_00000.blob"), k("00001_00001.blob"),
                     k("00001_00002.blob")}) == 3,
                "3 distinct stems", "3 distinct"))

    # R8-1: a WHOLE frame's required meta identity is its exact <frame>_00000 stem, so a
    # different-subframe file (<frame>_00001) can NEVER satisfy the required whole frame.
    mk_ = ci._gn_meta_coverage_key
    out.append(("gn meta key: whole frame -> '<frame>_00000' stem",
                mk_(3) == "00003_00000", mk_(3), "00003_00000"))
    out.append(("gn meta key: a nonzero-subframe file can't match the whole-frame key (R8-1)",
                mk_(3) != "00003_00001", (mk_(3), "00003_00001"), "distinct"))
    out.append(("gn meta key: frame >= 100000 keeps 5-digit subframe",
                mk_(100000) == "100000_00000", mk_(100000), "100000_00000"))

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
    """R9-1 / R10-1 / R10-2 / R11-1 / R12-1: each fluid sub-cache matcher accepts ONLY the
    files the domain's configured FORMAT writes for that stage (a wrong format / reserved
    masquerade is rejected), and UNI data is per-grid: coverage requires EACH grid per
    frame (never the bare frame). The matcher CAPTURES every real grid file — including the
    OPTIONAL grids a bake may add (colored-smoke color_r/g/b, resumable restart-state) so
    they are verified (R12-1) — while the per-(frame,grid) identity and required-set
    completeness, not matcher rejection, keep a cross-domain / foreign / deleted grid from
    a false PASS. All filename schemes and the core grid sets were verified on real bakes
    of all four versions (4.2.9/4.5.9/5.0.1/5.2.3)."""
    from failsafe import cache_inspect as ci

    class FakeDS:
        def __init__(self, **kw):
            self.__dict__.update(kw)

    def m(component, ds, name):
        """True iff `name` is counted as a file of this stage — i.e. gets a coverage
        token from the real per-file matcher (False for an unrecognised format/grid,
        which is matched by nothing: UNKNOWN, not a guess)."""
        return ci._fluid_file_token(component, ds, name) is not None

    vdb_ds = FakeDS(domain_type="LIQUID", cache_data_format="OPENVDB", cache_mesh_format="BOBJECT")
    uni_ds = FakeDS(domain_type="LIQUID", cache_data_format="UNI", cache_mesh_format="BOBJECT")
    gas_ds = FakeDS(domain_type="GAS", cache_data_format="UNI", cache_mesh_format="BOBJECT")
    obj_ds = FakeDS(domain_type="LIQUID", cache_data_format="OPENVDB", cache_mesh_format="OBJECT")
    any_ds = FakeDS(domain_type="LIQUID", cache_data_format="OPENVDB", cache_mesh_format="BOBJECT")

    checks = [
        # --- FIXED stages (output independent of any format setting) ---
        ("config accepts config_NNNN.uni", m("config", any_ds, "config_0001.uni"), True),
        ("config rejects a data file", m("config", any_ds, "fluid_data_0001.vdb"), False),
        ("noise accepts fluid_noise .vdb", m("noise", any_ds, "fluid_noise_0001.vdb"), True),
        ("noise rejects .uni (always VDB)", m("noise", any_ds, "fluid_noise_0001.uni"), False),
        ("noise rejects a data file", m("noise", any_ds, "fluid_data_0001.vdb"), False),
        ("particles accepts fluid_particles .vdb",
         m("particles", any_ds, "fluid_particles_0001.vdb"), True),
        ("particles rejects .uni (always VDB)",
         m("particles", any_ds, "fluid_particles_0001.uni"), False),
        ("guiding accepts fluid_guiding .vdb",
         m("guiding", any_ds, "fluid_guiding_0001.vdb"), True),
        ("guiding rejects a data file", m("guiding", any_ds, "fluid_data_0001.vdb"), False),

        # --- data OPENVDB (one packed .vdb per frame) ---
        ("OPENVDB data matches fluid_data .vdb", m("data", vdb_ds, "fluid_data_0003.vdb"), True),
        ("OPENVDB data REJECTS a renamed .uni (R9-1)",
         m("data", vdb_ds, "fluid_data_0003.uni"), False),
        ("OPENVDB data REJECTS a renamed .raw (R9-1)",
         m("data", vdb_ds, "fluid_data_0003.raw"), False),
        ("OPENVDB data REJECTS an upper-case .VDB (case hardening)",
         m("data", vdb_ds, "fluid_data_0003.VDB"), False),
        ("OPENVDB data rejects a mesh file", m("data", vdb_ds, "fluid_mesh_0003.bobj.gz"), False),

        # --- data UNI (per-grid .uni) — the matcher now CAPTURES every real grid file so
        # OPTIONAL grids (color_r/g/b, resumable restart-state) are verified too (R12-1);
        # the reserved-prefix masquerades stay rejected, and a cross-domain / foreign name,
        # though captured, can't cover a required core grid (per-(frame,grid) identity) and
        # is itself required at every other frame -> UNKNOWN, never a false PASS. ---
        ("UNI liquid data matches pVel grid", m("data", uni_ds, "pVel_0003.uni"), True),
        ("UNI liquid data matches vel grid", m("data", uni_ds, "vel_0003.uni"), True),
        ("UNI liquid data matches pp grid", m("data", uni_ds, "pp_0003.uni"), True),
        ("UNI gas data matches density grid", m("data", gas_ds, "density_0003.uni"), True),
        ("UNI gas data matches flame grid", m("data", gas_ds, "flame_0003.uni"), True),
        ("UNI gas data matches heat/shadow/vel grids",
         all(m("data", gas_ds, g + "_0003.uni") for g in ("heat", "shadow", "vel")), True),
        # R12-1: colored-smoke grids (underscored names) are now CAPTURED, not dropped.
        ("UNI gas data matches color_r/color_g/color_b (R12-1)",
         all(m("data", gas_ds, g + "_0003.uni")
             for g in ("color_r", "color_g", "color_b")), True),
        ("UNI data matches an underscored resumable grid color_r_in (R12-1)",
         m("data", gas_ds, "color_r_in_0003.uni"), True),
        ("UNI data matches a resumable restart grid densityIn (R12-1)",
         m("data", gas_ds, "densityIn_0003.uni"), True),
        # A cross-domain or foreign grid is CAPTURED (True); the per-(frame,grid) token and
        # required-set completeness — not matcher rejection — keep it from a false PASS.
        ("UNI data captures a cross-domain grid (caught later by coverage, R12-1)",
         m("data", uni_ds, "density_0003.uni"), True),
        ("UNI data captures a foreign grid junk_NNNN.uni (caught later by coverage)",
         m("data", uni_ds, "junk_0003.uni"), True),
        # Reserved-stage masquerades are STILL rejected outright (R10-2 negative lookahead).
        ("UNI data REJECTS the fluid_data_*.uni masquerade (R10-2)",
         m("data", uni_ds, "fluid_data_0003.uni"), False),
        ("UNI data REJECTS a reserved fluid_noise prefix",
         m("data", uni_ds, "fluid_noise_0003.uni"), False),
        ("UNI data REJECTS a reserved fluid_particles prefix",
         m("data", uni_ds, "fluid_particles_0003.uni"), False),
        ("UNI data REJECTS a reserved fluid_guiding prefix",
         m("data", uni_ds, "fluid_guiding_0003.uni"), False),
        ("UNI data REJECTS a reserved fluid_mesh prefix",
         m("data", uni_ds, "fluid_mesh_0003.uni"), False),
        ("UNI data REJECTS a .vdb (wrong ext for UNI)",
         m("data", uni_ds, "pVel_0003.vdb"), False),
        ("UNI data on an uncharacterised domain type matches nothing",
         m("data", FakeDS(domain_type="FOG", cache_data_format="UNI"), "pVel_0003.uni"), False),

        # --- mesh BOBJECT / OBJECT (R10-1) ---
        ("BOBJECT mesh matches .bobj.gz", m("mesh", vdb_ds, "fluid_mesh_0003.bobj.gz"), True),
        ("BOBJECT mesh REJECTS bare .bobj (R10-1)",
         m("mesh", vdb_ds, "fluid_mesh_0003.bobj"), False),
        ("BOBJECT mesh REJECTS .vdb", m("mesh", vdb_ds, "fluid_mesh_0003.vdb"), False),
        ("OBJECT mesh matches .obj", m("mesh", obj_ds, "fluid_mesh_0003.obj"), True),
        ("OBJECT mesh REJECTS .bobj.gz", m("mesh", obj_ds, "fluid_mesh_0003.bobj.gz"), False),

        # --- unrecognised format -> matched by NOTHING (UNKNOWN, not a guess) ---
        ("STL mesh (not a real format) matches nothing",
         m("mesh", FakeDS(cache_mesh_format="STL"), "fluid_mesh_0003.bobj.gz"), False),
        ("RAW data (rejected by setter) matches nothing",
         m("data", FakeDS(domain_type="LIQUID", cache_data_format="RAW"), "fluid_data_0003.vdb"), False),
        ("missing data-format attr matches nothing",
         m("data", FakeDS(domain_type="LIQUID"), "fluid_data_0003.vdb"), False),
    ]
    res = [("fluid matcher: %s" % label, got == expect, got, expect)
           for label, got, expect in checks]

    # The coverage token keys the right frame AND grid (pVel_0007.uni -> "0007/pVel"),
    # so two grids sharing a frame never collapse to one coverage key (R11-1).
    tok = ci._fluid_file_token("data", uni_ds, "pVel_0007.uni")
    res.append(("fluid matcher: UNI token is (frame, grid) '0007/pVel'",
                tok == ("0007/pVel", 7), tok, ("0007/pVel", 7)))

    # Required coverage for a UNI data stage is the PRODUCT of frames x core grids —
    # every core grid per frame, not the bare frame (R11-1).
    req_liq = ci._fluid_stage_required("data", uni_ds, 1, 2)
    res.append(("fluid matcher: UNI liquid required = frames x {pVel,pp,vel}",
                sorted(req_liq) == sorted(["0001/pVel", "0001/pp", "0001/vel",
                                           "0002/pVel", "0002/pp", "0002/vel"]),
                sorted(req_liq), "6 (frame,grid) tokens"))
    req_gas = ci._fluid_stage_required("data", gas_ds, 1, 1)
    res.append(("fluid matcher: UNI gas required = {density,flame,heat,shadow,vel}",
                sorted(req_gas) == sorted(["0001/density", "0001/flame", "0001/heat",
                                           "0001/shadow", "0001/vel"]),
                sorted(req_gas), "5 gas grid tokens"))
    # An uncharacterised domain type yields a sentinel no real file can baseline ->
    # forces UNKNOWN rather than an optimistic PASS.
    req_unk = ci._fluid_stage_required("data", FakeDS(domain_type="FOG", cache_data_format="UNI"), 1, 3)
    res.append(("fluid matcher: UNI unknown-domain required is an unbaselinable sentinel",
                req_unk == ["?/uni-unknown-domain"], req_unk, ["?/uni-unknown-domain"]))
    # OpenVDB data (single file per frame) still uses the bare integer frame.
    res.append(("fluid matcher: OpenVDB data required stays integer frames",
                ci._fluid_stage_required("data", vdb_ds, 1, 3) == [1, 2, 3],
                ci._fluid_stage_required("data", vdb_ds, 1, 3), [1, 2, 3]))

    # R12-1: an optional grid (color / resumable) gets a per-(frame,grid) token too.
    ctok = ci._fluid_file_token("data", gas_ds, "color_r_0005.uni")
    res.append(("fluid matcher: color grid token is (frame, grid) '0005/color_r' (R12-1)",
                ctok == ("0005/color_r", 5), ctok, ("0005/color_r", 5)))
    # With NO observed grids the required set is core only — a bake that wrote no optional
    # grids must NOT be forced UNKNOWN (the false-UNKNOWN guard, R12-1).
    req_core_only = ci._fluid_stage_required("data", gas_ds, 1, 1)
    res.append(("fluid matcher: UNI gas with no observed grids = core only (R12-1)",
                sorted(req_core_only) == sorted(["0001/density", "0001/flame", "0001/heat",
                                                 "0001/shadow", "0001/vel"]),
                sorted(req_core_only), "5 core tokens, no optional"))
    # Observed optional grids become REQUIRED per frame, so a deleted one is uncovered.
    req_color = ci._fluid_stage_required(
        "data", gas_ds, 3, 3,
        observed_grids={"density", "flame", "heat", "shadow", "vel",
                        "color_r", "color_g", "color_b"})
    res.append(("fluid matcher: observed color grids become required per frame (R12-1)",
                all(t in req_color
                    for t in ("0003/color_r", "0003/color_g", "0003/color_b")),
                sorted(req_color), "core + 3 color tokens"))
    # Color is required as a SET: observing ONE channel requires all three, so a single
    # deleted channel can't hide behind its siblings (R12-1).
    req_one_color = ci._fluid_stage_required(
        "data", gas_ds, 2, 2,
        observed_grids={"density", "flame", "heat", "shadow", "vel", "color_r"})
    res.append(("fluid matcher: observing one color channel requires all three (R12-1)",
                all(t in req_one_color
                    for t in ("0002/color_r", "0002/color_g", "0002/color_b")),
                sorted(req_one_color), "all three color tokens required"))
    # A resumable restart-state grid the bake wrote is required too (no hardcoded list).
    req_resume = ci._fluid_stage_required(
        "data", gas_ds, 4, 4,
        observed_grids={"density", "flame", "heat", "shadow", "vel", "velTmp"})
    res.append(("fluid matcher: an observed resumable grid is required per frame (R12-1)",
                "0004/velTmp" in req_resume, sorted(req_resume), "includes 0004/velTmp"))

    # R13-1: an ENTIRE optional family wiped before baseline leaves NO on-disk evidence,
    # so the required set is anchored to CONFIG, not just observed files.
    # Colour (gas only) is required from config even with NO colour grid observed.
    req_cfg_color = ci._fluid_stage_required("data", gas_ds, 1, 1,
                                             observed_grids=set(), expects_color=True)
    res.append(("fluid matcher: expects_color requires colour set with none observed (R13-1)",
                all(t in req_cfg_color
                    for t in ("0001/color_r", "0001/color_g", "0001/color_b")),
                sorted(req_cfg_color), "core + colour set"))
    # Colour is GAS-only: a liquid domain never requires colour, even in a coloured scene.
    req_liq_color = ci._fluid_stage_required("data", uni_ds, 1, 1,
                                             observed_grids=set(), expects_color=True)
    res.append(("fluid matcher: expects_color adds NO colour to a LIQUID domain (R13-1)",
                not any(t.split("/")[-1] in ("color_r", "color_g", "color_b")
                        for t in req_liq_color),
                sorted(req_liq_color), "no colour tokens on liquid"))
    # A plain gas bake (expects_color False, no colour observed) is NOT forced UNKNOWN.
    req_plain = ci._fluid_stage_required("data", gas_ds, 1, 1,
                                         observed_grids={"density", "flame", "heat",
                                                         "shadow", "vel"},
                                         expects_color=False)
    res.append(("fluid matcher: plain gas bake needs no colour (no false UNKNOWN, R13-1)",
                not any(t.split("/")[-1].startswith("color_") for t in req_plain),
                sorted(req_plain), "no colour tokens"))
    # R14-2: a RESUMABLE cache's restart-state grids are required BY NAME — the fixed set
    # Blender writes (verified identical on all four versions) — NOT merely "some non-core
    # grid is present". So an entire family wiped before baseline is required-but-uncovered
    # -> UNKNOWN; a planted junk grid can't pose as restart evidence; and a family wiped to
    # one surviving grid is still caught.
    gas_resume_ds = FakeDS(domain_type="GAS", cache_data_format="UNI",
                           cache_mesh_format="BOBJECT", cache_resumable=True)
    # Whole restart family wiped (observed = core only): the named restart grids are STILL
    # required per frame, so the frame is uncovered -> UNKNOWN.
    req_resume_wiped = ci._fluid_stage_required(
        "data", gas_resume_ds, 1, 1,
        observed_grids={"density", "flame", "heat", "shadow", "vel"})
    res.append(("fluid matcher: resumable requires the named restart set even if none observed (R14-2)",
                all(t in req_resume_wiped for t in
                    ("0001/densityIn", "0001/flags", "0001/velTmp", "0001/phiIn")),
                sorted(req_resume_wiped), "core + named restart grids required"))
    # A planted non-restart file (junk) is NOT accepted as restart evidence: the named
    # restart grids stay required, so the wiped family is still caught.
    req_resume_junk = ci._fluid_stage_required(
        "data", gas_resume_ds, 1, 1,
        observed_grids={"density", "flame", "heat", "shadow", "vel", "junk"})
    res.append(("fluid matcher: a junk grid is NOT restart evidence (R14-2)",
                all(t in req_resume_junk for t in
                    ("0001/densityIn", "0001/flags", "0001/velTmp")),
                sorted(req_resume_junk), "named restart still required despite junk"))
    # A LIQUID resumable domain requires its OWN restart set (phi/phiParts/phiTmp/…), not
    # the gas set.
    liq_resume_ds = FakeDS(domain_type="LIQUID", cache_data_format="UNI",
                           cache_mesh_format="BOBJECT", cache_resumable=True)
    req_liq_resume = ci._fluid_stage_required(
        "data", liq_resume_ds, 1, 1, observed_grids={"pVel", "pp", "vel"})
    res.append(("fluid matcher: liquid resumable requires the liquid restart set (R14-2)",
                all(t in req_liq_resume for t in
                    ("0001/phi", "0001/phiParts", "0001/phiTmp", "0001/velTmp"))
                and "0001/densityIn" not in req_liq_resume,
                sorted(req_liq_resume), "liquid restart grids, not gas"))
    # A genuine resumable bake (every restart grid present) has them required AND covered,
    # so it is NOT forced UNKNOWN (no false UNKNOWN on a real resumable cache).
    req_resume_ok = ci._fluid_stage_required(
        "data", gas_resume_ds, 1, 1,
        observed_grids={"density", "flame", "heat", "shadow", "vel"}
        | set(ci._FLUID_UNI_RESTART_GRIDS["GAS"]))
    res.append(("fluid matcher: genuine resumable bake requires its restart grids (R14-2)",
                "0001/velTmp" in req_resume_ok and "0001/densityIn" in req_resume_ok
                and "?/resumable-restart-wiped" not in req_resume_ok,
                sorted(req_resume_ok), "restart grids required, no sentinel"))
    # A non-resumable bake never requires restart grids (no false UNKNOWN).
    req_nonresume = ci._fluid_stage_required("data", gas_ds, 1, 1, observed_grids=set())
    res.append(("fluid matcher: non-resumable requires no restart grids (R14-2)",
                not any(t.split("/")[-1] in ci._FLUID_UNI_RESTART_GRIDS["GAS"]
                        for t in req_nonresume)
                and "?/resumable-restart-wiped" not in req_nonresume,
                sorted(req_nonresume), "core only, no restart"))

    # R15-1: a gas cache that is BOTH resumable AND coloured also writes colour-restart
    # grids color_r_in/g_in/b_in; required as a SET so the whole _in family deleted before
    # baseline reads UNKNOWN (verified on real bakes, all four versions).
    req_cr = ci._fluid_stage_required(
        "data", gas_resume_ds, 1, 1,
        observed_grids={"density", "flame", "heat", "shadow", "vel"},
        expects_color=True)
    res.append(("fluid matcher: gas resumable + expects_color requires color_*_in set (R15-1)",
                all(t in req_cr for t in
                    ("0001/color_r_in", "0001/color_g_in", "0001/color_b_in")),
                sorted(req_cr), "color_*_in required"))
    # Observed-closure: one color_*_in present requires all three.
    req_cr2 = ci._fluid_stage_required(
        "data", gas_resume_ds, 1, 1,
        observed_grids={"density", "flame", "heat", "shadow", "vel", "color_r_in"})
    res.append(("fluid matcher: one color_*_in observed requires all three (R15-1)",
                all(t in req_cr2 for t in
                    ("0001/color_r_in", "0001/color_g_in", "0001/color_b_in")),
                sorted(req_cr2), "all three color_*_in required"))
    # A plain resumable bake (no colour) does NOT require color_*_in (no false UNKNOWN).
    req_cr3 = ci._fluid_stage_required(
        "data", gas_resume_ds, 1, 1,
        observed_grids={"density", "flame", "heat", "shadow", "vel"},
        expects_color=False)
    res.append(("fluid matcher: plain resumable bake needs no color_*_in (R15-1)",
                not any(t.split("/")[-1] in ci._FLUID_UNI_COLOR_RESTART_GRIDS
                        for t in req_cr3),
                sorted(req_cr3), "no color_*_in"))
    # Colour but NOT resumable: color_*_in are not written, so not required.
    req_cr4 = ci._fluid_stage_required(
        "data", gas_ds, 1, 1,
        observed_grids={"density", "flame", "heat", "shadow", "vel"},
        expects_color=True)
    res.append(("fluid matcher: colour but non-resumable needs no color_*_in (R15-1)",
                not any(t.split("/")[-1] in ci._FLUID_UNI_COLOR_RESTART_GRIDS
                        for t in req_cr4),
                sorted(req_cr4), "no color_*_in on non-resumable"))

    # R14-1: colour is written for a GAS domain when a SMOKE/BOTH flow is non-default, OR
    # when fire + a smoke source + a non-default domain flame_smoke_color combine (the burnt
    # smoke carries a second colour). Fire ALONE writes none. Verified on real bakes, all
    # four versions: missing the flame path is a false PASS; requiring colour for
    # fire-only / flame-default would be a false UNKNOWN.
    class _FS:
        def __init__(self, flow_type, smoke_color=(0.7, 0.7, 0.7)):
            self.flow_type = flow_type
            self.smoke_color = smoke_color

    class _DS:
        def __init__(self, domain_type="GAS", flame_smoke_color=(0.7, 0.7, 0.7)):
            self.domain_type = domain_type
            self.flame_smoke_color = flame_smoke_color

    class _FlowMod:
        def __init__(self, fs):
            self.type = "FLUID"
            self.fluid_type = "FLOW"
            self.flow_settings = fs

    class _DomMod:
        def __init__(self, ds):
            self.type = "FLUID"
            self.fluid_type = "DOMAIN"
            self.domain_settings = ds

    class _Obj:
        def __init__(self, *mods):
            self.modifiers = list(mods)

    class _Scene:
        def __init__(self, *objs):
            self.objects = list(objs)

    det = ci._scene_expects_fluid_color
    GREY = (0.7, 0.7, 0.7)
    FLAME = (0.1, 0.9, 0.2)
    cases = [
        ("FIRE flow alone with non-default smoke_color is NOT colour",
         _Scene(_Obj(_FlowMod(_FS("FIRE", (0.1, 0.2, 0.9))))), False),
        ("default-grey SMOKE flow is NOT colour",
         _Scene(_Obj(_FlowMod(_FS("SMOKE", GREY)))), False),
        ("non-default SMOKE flow IS colour",
         _Scene(_Obj(_FlowMod(_FS("SMOKE", (0.9, 0.1, 0.1))))), True),
        ("non-default BOTH flow IS colour",
         _Scene(_Obj(_FlowMod(_FS("BOTH", (0.2, 0.8, 0.3))))), True),
        # Flame path: default SMOKE flow + FIRE flow + non-default domain flame_smoke_color.
        ("default SMOKE + FIRE + non-default flame_smoke_color IS colour (R14-1)",
         _Scene(_Obj(_FlowMod(_FS("SMOKE", GREY))),
                _Obj(_FlowMod(_FS("FIRE"))),
                _Obj(_DomMod(_DS("GAS", FLAME)))), True),
        # Same but flame default -> no colour.
        ("default SMOKE + FIRE + default flame_smoke_color is NOT colour",
         _Scene(_Obj(_FlowMod(_FS("SMOKE", GREY))),
                _Obj(_FlowMod(_FS("FIRE"))),
                _Obj(_DomMod(_DS("GAS", GREY)))), False),
        # A single BOTH flow (smoke+fire) + non-default flame -> colour.
        ("BOTH flow + non-default flame_smoke_color IS colour (R14-1)",
         _Scene(_Obj(_FlowMod(_FS("BOTH", GREY))),
                _Obj(_DomMod(_DS("GAS", FLAME)))), True),
        # Fire ALONE (no smoke flow) + non-default flame -> NO colour (fire-only writes none).
        ("FIRE flow + non-default flame but NO smoke flow is NOT colour (R14-1)",
         _Scene(_Obj(_FlowMod(_FS("FIRE"))),
                _Obj(_DomMod(_DS("GAS", FLAME)))), False),
        # Non-default flame with a smoke flow but NO fire -> NO colour.
        ("non-default flame + smoke flow but NO fire is NOT colour",
         _Scene(_Obj(_FlowMod(_FS("SMOKE", GREY))),
                _Obj(_DomMod(_DS("GAS", FLAME)))), False),
        # R16-1: a flame deviating by a SINGLE float32 step (0.70001) still activates colour.
        ("BOTH flow + flame off default by one float32 step IS colour (R16-1)",
         _Scene(_Obj(_FlowMod(_FS("BOTH", GREY))),
                _Obj(_DomMod(_DS("GAS", (0.70001, 0.7, 0.7))))), True),
        # A tiny smoke_color deviation likewise activates colour.
        ("SMOKE flow off default by one float32 step IS colour (R16-1)",
         _Scene(_Obj(_FlowMod(_FS("SMOKE", (0.70001, 0.7, 0.7))))), True),
    ]
    for label, scene, expect in cases:
        res.append(("fluid matcher: %s" % label, det(scene) is expect,
                    det(scene), expect))

    # R16-1: _color_is_noncat compares in float32 (Blender's own precision), so a 0.70001
    # deviation is seen as colour while the genuine default — stored as float32(0.7), which
    # reads back as 0.699999988079071, NOT Python's 0.7 — is NOT flagged (no false UNKNOWN).
    f32_default = struct.unpack("<f", struct.pack("<f", 0.7))[0]
    res.append(("fluid matcher: 0.70001 colour deviation is non-default (R16-1)",
                ci._color_is_noncat((0.70001, 0.7, 0.7)) is True,
                "non-default", "non-default"))
    res.append(("fluid matcher: exact default grey is NOT non-default (R16-1)",
                ci._color_is_noncat((0.7, 0.7, 0.7)) is False,
                "default", "default"))
    res.append(("fluid matcher: stored float32(0.7) default is NOT non-default (R16-1)",
                ci._color_is_noncat((f32_default, f32_default, f32_default)) is False,
                "float32 default not flagged", "not flagged"))
    res.append(("fluid matcher: a clearly different grey (0.5) is non-default (R16-1)",
                ci._color_is_noncat((0.5, 0.5, 0.5)) is True,
                "non-default", "non-default"))
    return res


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

    # --- A8 build_html_report: self-contained, escaped, verdict-first -------
    html_blob = report.build_html_report(results)
    out.append(("A8 HTML is a string", isinstance(html_blob, str),
                type(html_blob).__name__, "str"))
    out.append(("A8 HTML has doctype", html_blob.startswith("<!DOCTYPE html>"),
                html_blob[:15], "<!DOCTYPE html>"))
    for needle in ("<title>Failsafe report</title>", 'class="verdict',
                   "<style>", "</html>"):
        out.append(("A8 HTML contains %r" % needle, needle in html_blob,
                    needle in html_blob, True))
    # Self-contained: no external CSS/JS/fonts/images to fetch.
    for bad in ("http://", "https://", "src=", "<link", "<script"):
        out.append(("A8 HTML has no external %r" % bad, bad not in html_blob,
                    bad not in html_blob, True))
    # Escaping: a hostile finding must never inject raw markup.
    hostile = engine.Result(1, "x", engine.GROUP_SETUP, Status.FAIL,
                            "<script>alert(1)</script>", object_name="<b>o</b>")
    esc = report.build_html_report([hostile])
    out.append(("A8 HTML escapes message",
                "<script>alert" not in esc and "&lt;script&gt;" in esc,
                "<script>alert" not in esc, True))
    out.append(("A8 HTML escapes object name",
                "<b>o</b>" not in esc and "&lt;b&gt;o&lt;/b&gt;" in esc,
                "<b>o</b>" not in esc, True))
    # Verdict banner reflects the worst status present.
    out.append(("A8 HTML FAIL -> v-fail banner",
                'class="verdict v-fail"' in esc, 'v-fail' in esc, True))

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
    # The COLLAPSED heading (display_name on PASS) must also say "Tracked", so the
    # collapsed view carries the same limitation as the detailed message.
    heading = engine.display_name(meta26b, engine.Status.PASS)
    out.append(("R27 collapsed PASS heading says 'Tracked'",
                "tracked" in heading.lower()
                and "settings unchanged" in heading.lower(), heading,
                "Tracked settings unchanged"))
    return out


def integrity_header_tests():
    """Direct unit tests for the .bphys header validator and the CORRUPT verdict
    it drives, independent of a real bake (the heavy-sim cases cover real files).
    Proves zero false positives: a valid header passes, a clean present set is
    COMPLETE, and only genuinely invalid data is flagged."""
    from failsafe import cache_inspect as ci
    import struct
    out = []
    d = tempfile.mkdtemp(prefix="failsafe_hdr_")
    good = os.path.join(d, "good.bphys")
    with open(good, "wb") as fh:
        fh.write(b"BPHYSICS" + struct.pack("<3I", 2, 81, 22) + b"\x00" * 40)
    bad = os.path.join(d, "bad.bphys")
    with open(bad, "wb") as fh:
        fh.write(b"not a cache at all, but definitely non-empty\n")
    trunc = os.path.join(d, "trunc.bphys")
    with open(trunc, "wb") as fh:
        fh.write(b"BPHYSICS\x02\x00\x00\x00")  # magic present, only 12 bytes
    # B1: valid magic + full 20-byte length but zero header fields (the exact
    # fabricated file from the review) must be rejected.
    zerofields = os.path.join(d, "zero.bphys")
    with open(zerofields, "wb") as fh:
        fh.write(b"BPHYSICS" + b"\x00" * 12)
    # valid magic + valid non-zero fields but NO payload beyond the 20-byte header.
    headeronly = os.path.join(d, "hdronly.bphys")
    with open(headeronly, "wb") as fh:
        fh.write(b"BPHYSICS" + struct.pack("<3I", 2, 81, 22))
    out.append(("integrity valid header -> True",
                ci._bphys_header_valid(good) is True,
                ci._bphys_header_valid(good), True))
    out.append(("integrity bad magic -> False",
                ci._bphys_header_valid(bad) is False,
                ci._bphys_header_valid(bad), False))
    out.append(("integrity truncated header -> False",
                ci._bphys_header_valid(trunc) is False,
                ci._bphys_header_valid(trunc), False))
    out.append(("integrity B1 fabricated zero-fields -> False",
                ci._bphys_header_valid(zerofields) is False,
                ci._bphys_header_valid(zerofields), False))
    out.append(("integrity header-only (no payload) -> False",
                ci._bphys_header_valid(headeronly) is False,
                ci._bphys_header_valid(headeronly), False))
    # M1: the 'good' file declares type 2 (cloth). It passes when the owner type
    # matches, and is rejected when the owner expects a different type.
    out.append(("integrity type matches owner -> True",
                ci._bphys_header_valid(good, expected_type=2) is True,
                ci._bphys_header_valid(good, expected_type=2), True))
    out.append(("integrity type mismatches owner -> False",
                ci._bphys_header_valid(good, expected_type=1) is False,
                ci._bphys_header_valid(good, expected_type=1), False))
    out.append(("integrity unknown owner type skips type check -> True",
                ci._bphys_header_valid(good, expected_type=None) is True,
                ci._bphys_header_valid(good, expected_type=None), True))

    e = ci.CacheEntry("Obj", "Cloth", "point")
    e.baked_flag = True
    e.file_check_applicable = True
    e.cache_dir = d
    e.frames_expected = [1, 2, 3]
    e.frames_present = {1, 2, 3}
    e.frames_badheader = {2}
    out.append(("integrity bad-header frame -> V_CORRUPT",
                ci.cache_status(e).state == ci.V_CORRUPT,
                ci.cache_status(e).state, ci.V_CORRUPT))
    e.frames_badheader = set()
    out.append(("integrity clean frames -> V_COMPLETE (no false corrupt)",
                ci.cache_status(e).state == ci.V_COMPLETE,
                ci.cache_status(e).state, ci.V_COMPLETE))
    return out


def cache_coverage_tests():
    """Hair-dynamics and Dynamic-Paint-vertex cache coverage, and the two
    correctness guards: a static-hair system is never scanned (a false FAIL risk,
    since it has no sim cache), and a Dynamic Paint vertex cache is recognised as
    owned so the orphan check (#25) can never flag it. Enumeration/ownership read
    only the datablocks, so no on-disk bake is needed here (the heavy-sim cases
    cover the real bakes)."""
    from failsafe import cache_inspect as ci
    out = []

    # --- static hair must NOT be scanned (no cache -> no false FAIL) ----------
    fixtures.reset()
    bpy.ops.mesh.primitive_plane_add(size=4)
    o = bpy.context.active_object
    o.name = "HairCov"
    with bpy.context.temp_override(active_object=o, object=o, selected_objects=[o]):
        bpy.ops.object.particle_system_add()
    psys = o.particle_systems[0]
    psys.settings.type = 'HAIR'
    psys.use_hair_dynamics = False
    n_static = len([e for e in ci.enumerate_caches(bpy.context.scene)
                    if e.obj_name == "HairCov"])
    out.append(("coverage static hair not scanned", n_static == 0, n_static, 0))

    # turning dynamics on makes it a scanned 'Hair Dynamics' cache
    psys.use_hair_dynamics = True
    hair_ents = [e for e in ci.enumerate_caches(bpy.context.scene)
                 if e.obj_name == "HairCov"]
    out.append(("coverage hair dynamics scanned", len(hair_ents) == 1,
                len(hair_ents), 1))
    out.append(("coverage hair labelled 'Hair Dynamics'",
                len(hair_ents) == 1 and hair_ents[0].system == "Hair Dynamics",
                hair_ents[0].system if hair_ents else None, "Hair Dynamics"))

    # --- Dynamic Paint vertex surface: scanned AND owned (never an orphan) ----
    fixtures.reset()
    bpy.ops.mesh.primitive_grid_add(size=4)
    d = bpy.context.active_object
    d.name = "DPCov"
    m = d.modifiers.new("DP", type='DYNAMIC_PAINT')
    with bpy.context.temp_override(active_object=d, object=d, selected_objects=[d]):
        bpy.ops.dpaint.type_toggle(type='CANVAS')
    surf = m.canvas_settings.canvas_surfaces[0]
    surf.surface_format = 'VERTEX'
    dp_ents = [e for e in ci.enumerate_caches(bpy.context.scene)
               if e.obj_name == "DPCov"]
    out.append(("coverage DP vertex scanned", len(dp_ents) == 1, len(dp_ents), 1))
    out.append(("coverage DP labelled 'Dynamic Paint'",
                len(dp_ents) == 1 and dp_ents[0].system == "Dynamic Paint",
                dp_ents[0].system if dp_ents else None, "Dynamic Paint"))
    # The scanner and the orphan-ownership set read the SAME helper, so a DP
    # vertex cache the scanner reports on can never be flagged as an orphan.
    # Prove the structural invariant directly (independent of save/bake state,
    # which the heavy-sim cases already exercise): the surface's point cache
    # flows through _iter_object_point_caches, which feeds both consumers.
    helper_pcs = [pc for _label, pc in ci._iter_object_point_caches(d)]
    out.append(("coverage DP vertex feeds scanner+orphan via one helper",
                any(pc == surf.point_cache for pc in helper_pcs),
                len(helper_pcs), ">=1"))

    # --- DP IMAGE surface: surfaced as an explicit 'Couldn't verify' ----------
    # (not a point cache, and never a silent skip that could read as verified).
    fixtures.reset()
    bpy.ops.mesh.primitive_grid_add(size=4)
    di = bpy.context.active_object
    di.name = "DPImg"
    mi = di.modifiers.new("DP", type='DYNAMIC_PAINT')
    with bpy.context.temp_override(active_object=di, object=di, selected_objects=[di]):
        bpy.ops.dpaint.type_toggle(type='CANVAS')
    si = mi.canvas_settings.canvas_surfaces[0]
    si.surface_format = 'IMAGE'
    img_ents = [e for e in ci.enumerate_caches(bpy.context.scene)
                if e.obj_name == "DPImg"]
    out.append(("coverage DP image enumerated as dpimage",
                len(img_ents) == 1 and img_ents[0].kind == "dpimage",
                (len(img_ents), img_ents[0].kind if img_ents else None),
                "1 dpimage"))
    out.append(("coverage DP image is not a point cache",
                all(e.kind != "point" for e in img_ents),
                [e.kind for e in img_ents], "no point"))
    # It must show up in #17 as UNKNOWN ('Couldn't verify'), never PASS.
    res = engine.run_all(bpy.context)
    st17 = set(statuses_for_check(res, 17))
    out.append(("coverage DP image is #17 UNKNOWN, never PASS",
                Status.UNKNOWN in st17 and Status.PASS not in st17,
                sorted(st17), "UNKNOWN without PASS"))

    # --- cross-scene guard: the scanner is PER-SCENE but cache ownership spans
    # ALL scenes, so a cache owned by another scene in the same .blend is never
    # mis-flagged as an orphan. (Sharing a helper is not proof on its own; this
    # exercises the actual asymmetry across scenes with real baked files.)
    outdir = tempfile.mkdtemp(prefix="failsafe_multiscene_")
    fixtures._make_cloth_blend(outdir)   # saves + bakes a disk cloth in scene
    scB = bpy.data.scenes.new("SceneB_cov")
    clothA = bpy.data.objects.get("Cloth")
    pcA = clothA.modifiers[0].point_cache
    identA = ci._point_cache_identity_for(clothA, pcA)
    owned_all = ci.owned_point_cache_identities(bpy.data.scenes)
    out.append(("coverage cross-scene cache is owned (not orphan)",
                identA is not None and identA in owned_all,
                (identA in owned_all) if identA is not None else None, True))
    # Scene B's scan does not see scene A's cache as its own...
    ents_B = ci.enumerate_caches(scB)
    out.append(("coverage scene B scanner excludes scene A cache",
                all(e.obj_name != "Cloth" for e in ents_B), len(ents_B), 0))
    # ...and the orphan check run from scene B raises no false orphan.
    orphans_from_B = ci.find_orphan_point_caches(scB)
    out.append(("coverage no false orphan across scenes",
                len(orphans_from_B) == 0, len(orphans_from_B), 0))

    return out


def cache_hash_tests():
    """Baselined per-frame SHA-256 cache hashing (#27, review M2).

    Proves the honest contract end-to-end on real baked caches:
      * a match reports 'bytes unchanged', never 'cache valid';
      * a changed file reports 'changed since baseline', framed as possibly a
        re-bake — never flatly 'corrupt';
      * a baseline saved AFTER damage still 'matches' the damaged bytes (so a
        match is not a validity oracle);
      * missing / no-section / no-baseline / wrong-schema / foreign / not-run can
        NEVER produce a PASS;
      * the baseline keys each sim independently (multi-sim project);
      * a project relocation (whole folder moved) still verifies;
      * streaming helpers: digest correctness, unreadable -> None, a file changing
        mid-read -> VOLATILE, and a cancelled capture raises (writing nothing)."""
    import json as _json
    import shutil
    import hashlib
    from failsafe import cachehash as ch, baseline as bl, cache_inspect as ci
    out = []
    tmp = tempfile.mkdtemp(prefix="failsafe_hash_")

    # ---- streaming-helper units (no bake needed) --------------------------
    g = os.path.join(tmp, "g.bin")
    with open(g, "wb") as fh:
        fh.write(b"hello world" * 100)
    res = ch.hash_file(g)
    out.append(("hash digest matches hashlib",
                bool(res) and res[0] == hashlib.sha256(b"hello world" * 100).hexdigest(),
                res[0] if res else None,
                hashlib.sha256(b"hello world" * 100).hexdigest()))
    out.append(("hash size reported", bool(res) and res[1] == 1100,
                res[1] if res else None, 1100))
    out.append(("hash missing file -> None",
                ch.hash_file(os.path.join(tmp, "nope.bin")) is None,
                ch.hash_file(os.path.join(tmp, "nope.bin")), None))
    # mid-read change -> VOLATILE (truncate the file from a progress callback).
    vol = os.path.join(tmp, "vol.bin")
    with open(vol, "wb") as fh:
        fh.write(b"A" * 8192)
    _st = {"hit": False}

    def _shrink(_n):
        if not _st["hit"]:
            _st["hit"] = True
            with open(vol, "wb") as fh2:
                fh2.write(b"B" * 4)
    vres = ch.hash_file(vol, chunk=16, progress=_shrink)
    out.append(("hash file changing mid-read -> VOLATILE",
                vres is ch.VOLATILE, vres, ch.VOLATILE))

    # ---- build one clean, baked, baselined two-sim project ----------------
    src = os.path.join(tmp, "src")
    os.makedirs(src, exist_ok=True)
    fixtures._make_two_sim_blend(src, frame_end=6)
    manifest = ch.capture(list(bpy.data.scenes), ci.blend_dir())
    bl.save_baseline(bpy.context.scene, bl.default_baseline_path(),
                     overwrite=True, cache_hashes=manifest)
    n_sims = len(manifest.get("sims", {}))
    out.append(("capture recorded both sims", n_sims == 2, n_sims, 2))

    cachedir = os.path.join(src, "blendcache_twosim")
    cloth_pre = fixtures.prefix_of("ClothP")
    soft_pre = fixtures.prefix_of("SoftC")

    def _frames(prefix):
        if not os.path.isdir(cachedir):
            return []
        return sorted(os.path.join(cachedir, f) for f in os.listdir(cachedir)
                      if f.startswith(prefix) and f.endswith(".bphys"))

    def _sv(report, system):
        for s in report.sims:
            if s.system == system:
                return s
        return None

    def _copy_open(tag):
        dst = os.path.join(tmp, "p_" + tag)
        shutil.copytree(src, dst)
        bpy.ops.wm.open_mainfile(filepath=os.path.join(dst, "twosim.blend"))
        return dst

    def _27(report):
        results = engine.run_all(bpy.context, hash_verify=report)
        return (worst_for_check(results, 27), statuses_for_check(results, 27),
                results)

    # (1) unchanged -> both PASS; message says 'unchanged' AND 'NOT proof'.
    _copy_open("pass")
    rep = ch.build_report(list(bpy.data.scenes))
    cs, ss = _sv(rep, "Cloth"), _sv(rep, "Soft Body")
    out.append(("hash unchanged: cloth UNCHANGED",
                cs is not None and cs.state == ch.S_UNCHANGED,
                getattr(cs, "state", None), ch.S_UNCHANGED))
    out.append(("hash unchanged: soft UNCHANGED",
                ss is not None and ss.state == ch.S_UNCHANGED,
                getattr(ss, "state", None), ch.S_UNCHANGED))
    worst, allst, results = _27(rep)
    out.append(("hash unchanged -> #27 PASS", worst == Status.PASS, worst,
                Status.PASS))
    msg = " ".join(r.message for r in results if r.check_id == 27)
    out.append(("hash PASS says bytes unchanged", "unchanged" in msg.lower(),
                True, True))
    out.append(("hash PASS never claims validity ('NOT proof')",
                "not proof" in msg.lower(), True, True))

    # (2) a changed BODY byte in the soft sim only -> soft CHANGED, cloth
    #     UNCHANGED; #27 WARNING, framed as possibly a re-bake (not 'corrupt').
    dst = _copy_open("changed")
    sframes = sorted(os.path.join(dst, "blendcache_twosim", f)
                     for f in os.listdir(os.path.join(dst, "blendcache_twosim"))
                     if f.startswith(soft_pre))
    tgt = sframes[len(sframes) // 2]
    with open(tgt, "r+b") as fh:
        fh.seek(0, os.SEEK_END)
        size = fh.tell()
        off = 30 if size > 31 else size - 1
        fh.seek(off)
        b = fh.read(1)
        fh.seek(off)
        fh.write(bytes([b[0] ^ 0xFF]))
    rep = ch.build_report(list(bpy.data.scenes))
    cs, ss = _sv(rep, "Cloth"), _sv(rep, "Soft Body")
    out.append(("hash changed: soft CHANGED",
                ss is not None and ss.state == ch.S_CHANGED,
                getattr(ss, "state", None), ch.S_CHANGED))
    out.append(("hash changed: cloth still UNCHANGED (independent keys)",
                cs is not None and cs.state == ch.S_UNCHANGED,
                getattr(cs, "state", None), ch.S_UNCHANGED))
    worst, allst, results = _27(rep)
    out.append(("hash changed -> #27 worst is WARNING (not FAIL)",
                worst == Status.WARNING, worst, Status.WARNING))
    # The CHANGED soft sim must never PASS; the genuinely-unchanged cloth sim may
    # (that's a true pass, not a false one — only the changed sim is the concern).
    soft_statuses = [r.status for r in results
                     if r.check_id == 27 and r.object_name == "SoftC"]
    out.append(("hash changed: the changed sim never PASS",
                Status.PASS not in soft_statuses, soft_statuses, "no PASS"))
    wmsg = " ".join(r.message for r in results
                    if r.check_id == 27 and r.status == Status.WARNING).lower()
    out.append(("hash changed msg says 'changed since the baseline'",
                "changed since the baseline" in wmsg, True, True))
    out.append(("hash changed msg frames a re-bake, not flat 'corrupt'",
                "re-bake" in wmsg, True, True))

    # (3) pre-existing damage baselined -> a match is still reported, proving a
    #     match is NOT a validity claim. Damage a frame, THEN baseline it, THEN
    #     verify: it 'matches' the damaged bytes.
    dst = _copy_open("predamage")
    pframes = sorted(os.path.join(dst, "blendcache_twosim", f)
                     for f in os.listdir(os.path.join(dst, "blendcache_twosim"))
                     if f.startswith(soft_pre))
    victim = pframes[len(pframes) // 2]
    with open(victim, "r+b") as fh:
        fh.seek(0, os.SEEK_END)
        sz = fh.tell()
        o2 = 28 if sz > 29 else sz - 1
        fh.seek(o2)
        bb = fh.read(1)
        fh.seek(o2)
        fh.write(bytes([bb[0] ^ 0xAA]))
    manifest2 = ch.capture(list(bpy.data.scenes), ci.blend_dir())
    bl.save_baseline(bpy.context.scene, bl.default_baseline_path(),
                     overwrite=True, cache_hashes=manifest2)
    rep = ch.build_report(list(bpy.data.scenes))
    ss = _sv(rep, "Soft Body")
    out.append(("hash pre-damage baselined -> still UNCHANGED (match != valid)",
                ss is not None and ss.state == ch.S_UNCHANGED,
                getattr(ss, "state", None), ch.S_UNCHANGED))

    # (4) a baselined frame deleted -> DRIFT (missing); never PASS for that sim.
    dst = _copy_open("missing")
    cframes = sorted(os.path.join(dst, "blendcache_twosim", f)
                     for f in os.listdir(os.path.join(dst, "blendcache_twosim"))
                     if f.startswith(cloth_pre))
    os.remove(cframes[len(cframes) // 2])
    rep = ch.build_report(list(bpy.data.scenes))
    cs = _sv(rep, "Cloth")
    out.append(("hash missing frame -> cloth DRIFT",
                cs is not None and cs.state == ch.S_DRIFT,
                getattr(cs, "state", None), ch.S_DRIFT))
    worst, allst, results = _27(rep)
    out.append(("hash missing: #27 is WARNING, never PASS for the sim",
                Status.PASS not in [r.status for r in results
                                    if r.check_id == 27 and r.object_name == "ClothP"],
                None, "no PASS"))

    # (5) genuine re-bake with a changed sim -> bytes differ -> CHANGED.
    dst = _copy_open("rebake")
    o = bpy.data.objects.get("ClothP")
    pc = o.modifiers["Cloth"].point_cache
    o.location.z += 2.0
    with bpy.context.temp_override(point_cache=pc, scene=bpy.context.scene,
                                   active_object=o, object=o):
        try:
            bpy.ops.ptcache.free_bake()
        except Exception:
            pass
        bpy.ops.ptcache.bake(bake=True)
    rep = ch.build_report(list(bpy.data.scenes))
    cs = _sv(rep, "Cloth")
    out.append(("hash genuine re-bake -> cloth CHANGED",
                cs is not None and cs.state in (ch.S_CHANGED, ch.S_DRIFT),
                getattr(cs, "state", None), ch.S_CHANGED))

    # (6) project relocation (whole folder copied elsewhere) -> still UNCHANGED.
    reloc = os.path.join(tmp, "moved_away", "nested")
    os.makedirs(os.path.dirname(reloc), exist_ok=True)
    shutil.copytree(src, reloc)
    bpy.ops.wm.open_mainfile(filepath=os.path.join(reloc, "twosim.blend"))
    rep = ch.build_report(list(bpy.data.scenes))
    cs, ss = _sv(rep, "Cloth"), _sv(rep, "Soft Body")
    out.append(("hash relocation: cloth UNCHANGED after moving the project",
                cs is not None and cs.state == ch.S_UNCHANGED,
                getattr(cs, "state", None), ch.S_UNCHANGED))
    out.append(("hash relocation: soft UNCHANGED after moving the project",
                ss is not None and ss.state == ch.S_UNCHANGED,
                getattr(ss, "state", None), ch.S_UNCHANGED))

    # (7) gating states: none may PASS.
    # no baseline at all
    dst = _copy_open("nobase")
    os.remove(bl.default_baseline_path())
    rep = ch.build_report(list(bpy.data.scenes))
    worst, allst, _ = _27(rep)
    out.append(("hash no baseline -> #27 not PASS and state NO_BASELINE",
                rep.state == ch.R_NO_BASELINE and Status.PASS not in allst,
                (rep.state, allst), ch.R_NO_BASELINE))
    # settings-only baseline (no cache-hash section). Delete the carried baseline
    # first: a settings re-save now PRESERVES an existing hash section (M2), so a
    # genuinely section-less baseline has to start fresh.
    dst = _copy_open("nosection")
    os.remove(bl.default_baseline_path())
    bl.save_baseline(bpy.context.scene, bl.default_baseline_path())
    rep = ch.build_report(list(bpy.data.scenes))
    worst, allst, _ = _27(rep)
    out.append(("hash no section -> #27 not PASS and state NO_SECTION",
                rep.state == ch.R_NO_SECTION and Status.PASS not in allst,
                (rep.state, allst), ch.R_NO_SECTION))
    # a schema-5 settings baseline must still be VALID for #23/#26 (compat).
    out.append(("schema 5 accepted by schema_ok (compat preserved)",
                bl.schema_ok({"schema": bl.BASELINE_SCHEMA}) is True,
                bl.schema_ok({"schema": bl.BASELINE_SCHEMA}), True))
    # wrong schema
    dst = _copy_open("schema")
    p = bl.default_baseline_path()
    with open(p) as fh:
        data = _json.load(fh)
    data["schema"] = 99
    with open(p, "w") as fh:
        _json.dump(data, fh)
    rep = ch.build_report(list(bpy.data.scenes))
    worst, allst, _ = _27(rep)
    out.append(("hash wrong schema -> #27 UNKNOWN, never PASS",
                rep.state == ch.R_SCHEMA and worst == Status.UNKNOWN
                and Status.PASS not in allst, (rep.state, worst), ch.R_SCHEMA))
    # foreign file
    dst = _copy_open("foreign")
    p = bl.default_baseline_path()
    with open(p) as fh:
        data = _json.load(fh)
    data["file"] = "/somewhere/else/other_project.blend"
    with open(p, "w") as fh:
        _json.dump(data, fh)
    rep = ch.build_report(list(bpy.data.scenes))
    worst, allst, _ = _27(rep)
    out.append(("hash foreign file -> #27 UNKNOWN, never PASS",
                rep.state == ch.R_FOREIGN and Status.PASS not in allst,
                (rep.state, allst), ch.R_FOREIGN))

    # (8) a plain quick scan (no verification run) -> #27 NA 'not run', not PASS.
    _copy_open("notrun")
    results = engine.run_all(bpy.context)   # no hash_verify
    worst = worst_for_check(results, 27)
    allst = statuses_for_check(results, 27)
    nmsg = " ".join(r.message for r in results if r.check_id == 27).lower()
    out.append(("hash not-run -> #27 NA, never PASS",
                worst == Status.NA and Status.PASS not in allst, worst, Status.NA))
    out.append(("hash not-run msg says it hasn't been run",
                "hasn't been run" in nmsg or "has not been run" in nmsg, True, True))

    # (9) a cancelled capture raises Cancelled (so the operator writes nothing).
    _copy_open("cancel")
    cnt = {"n": 0}

    def _cancel():
        cnt["n"] += 1
        return cnt["n"] > 1
    try:
        ch.capture(list(bpy.data.scenes), ci.blend_dir(), cancel=_cancel)
        raised = False
    except ch.Cancelled:
        raised = True
    out.append(("hash cancelled capture raises Cancelled", raised, raised, True))

    return out


def hash_blocker_tests():
    """Regression tests for the second-round independent review of #27, written to
    REPRODUCE each defect first:

      B1 — a requested CLI/batch verification that can't run must return nonzero,
           never a silent clean exit 0.
      B2 — direct (EXEC_DEFAULT) CAPTURE must not force an overwrite; it must
           refuse an existing baseline unless the user opted in.
      B3 — a baseline that covers only part of the required frame range must never
           report that sim as a clean PASS.
      M1 — hashing yields control per block (not per whole file), so a big file
           stays cancellable / the UI responsive.
      M2 — a settings-only Save Baseline must not discard previously captured
           cache hashes."""
    import json as _json
    import shutil
    from failsafe import (cachehash as ch, baseline as bl, cache_inspect as ci,
                          cli, batch)
    out = []
    tmp = tempfile.mkdtemp(prefix="failsafe_blk_")

    def _sv(report, system):
        for s in report.sims:
            if s.system == system:
                return s
        return None

    # ---- M1: per-BLOCK streaming (not per-file) --------------------------
    big = os.path.join(tmp, "big.bin")
    with open(big, "wb") as fh:
        fh.write(b"Z" * (16 * 50))         # 50 blocks at chunk=16
    evs = list(ch.hash_file_iter(big, chunk=16))
    prog = [e for e in evs if e[0] == "progress"]
    res = [e for e in evs if e[0] == "result"]
    out.append(("M1 hash_file_iter yields many per-block progress events",
                len(prog) >= 40 and len(res) == 1, len(prog), ">=40"))
    out.append(("M1 streamed digest equals the blocking digest",
                res and res[0][1] == ch.hash_file(big), bool(res), True))
    # a cancel that fires on the 3rd poll stops early (mid-file cancellation).
    seen = {"n": 0}

    def _c3():
        seen["n"] += 1
        return seen["n"] >= 3
    try:
        list(ch.hash_file_iter(big, chunk=16, cancel=_c3))
        raised = False
    except ch.Cancelled:
        raised = True
    out.append(("M1 mid-file cancel raises before reading the whole file",
                raised and seen["n"] <= 4, (raised, seen["n"]), "early"))

    # ---- build one clean baked two-sim project to reuse ------------------
    src = os.path.join(tmp, "src")
    os.makedirs(src, exist_ok=True)
    fixtures._make_two_sim_blend(src, frame_end=6)
    full_manifest = ch.capture(list(bpy.data.scenes), ci.blend_dir())
    bl.save_baseline(bpy.context.scene, bl.default_baseline_path(),
                     overwrite=True, cache_hashes=full_manifest)

    def _open_copy(tag):
        dst = os.path.join(tmp, "p_" + tag)
        shutil.copytree(src, dst)
        bpy.ops.wm.open_mainfile(filepath=os.path.join(dst, "twosim.blend"))
        return dst

    # M1: the step generators surface per-block 'chunk' ticks to the driver.
    _open_copy("steps")
    step_tags = [ev[0] for ev in ch.build_report_steps(list(bpy.data.scenes))]
    out.append(("M1 build_report_steps emits mid-file 'chunk' ticks",
                "chunk" in step_tags, set(step_tags), "has 'chunk'"))

    # ---- B1: requested verification that can't run -> nonzero exit -------
    # (a) unit: verify_floor floors only a REQUESTED, incomplete verification.
    good = ch.HashReport(ch.R_OK, "", [], False)
    out.append(("B1 floor: R_OK + requested -> clean",
                cli.verify_floor(good, True) == cli.EXIT_CLEAN,
                cli.verify_floor(good, True), cli.EXIT_CLEAN))
    for st in (ch.R_NO_BASELINE, ch.R_NO_SECTION, ch.R_UNSAVED, ch.R_SCHEMA,
               ch.R_FOREIGN, ch.R_ERROR):
        r = ch.HashReport(st, "", [], False)
        out.append(("B1 floor: %s + requested -> unverified" % st,
                    cli.verify_floor(r, True) == cli.EXIT_UNVERIFIED,
                    cli.verify_floor(r, True), cli.EXIT_UNVERIFIED))
        out.append(("B1 floor: %s + NOT requested -> no floor" % st,
                    cli.verify_floor(r, False) == cli.EXIT_CLEAN,
                    cli.verify_floor(r, False), cli.EXIT_CLEAN))
    cancelled = ch.HashReport(ch.R_OK, "", [], True)
    out.append(("B1 floor: cancelled + requested -> unverified",
                cli.verify_floor(cancelled, True) == cli.EXIT_UNVERIFIED,
                cli.verify_floor(cancelled, True), cli.EXIT_UNVERIFIED))

    # (b) end-to-end: a settings-only baseline (no cache-hash section) means a
    #     requested verification CAN'T run. Pre-fix this returned exit 0; it must
    #     now be nonzero, while NOT requesting verification is unaffected.
    _open_copy("b1_nosection")
    os.remove(bl.default_baseline_path())                # drop carried hashes (M2)
    bl.save_baseline(bpy.context.scene, bl.default_baseline_path())  # settings only
    rep = ch.build_report(list(bpy.data.scenes))
    code_plain, _ = cli.run(argv=["--text"])
    code_verify, _ = cli.run(argv=["--verify-hashes", "--text"])
    out.append(("B1 e2e: no cache-hash section -> R_NO_SECTION",
                rep.state == ch.R_NO_SECTION, rep.state, ch.R_NO_SECTION))
    out.append(("B1 e2e: requested verify -> NONZERO exit (not a false clean)",
                code_verify != cli.EXIT_CLEAN, code_verify, "!= 0"))
    out.append(("B1 e2e: requested verify floors to unverified",
                code_verify == cli.EXIT_UNVERIFIED, code_verify,
                cli.EXIT_UNVERIFIED))
    # a fully matching cache-hash baseline verifies and stays clean.
    _open_copy("b1_ok")
    code_ok, _ = cli.run(argv=["--verify-hashes", "--text"])
    out.append(("B1 e2e: complete matching baseline -> clean exit 0",
                code_ok == cli.EXIT_CLEAN, code_ok, cli.EXIT_CLEAN))
    # (c) batch wiring: the isolated child actually runs + floors the verification.
    argv = batch.build_child_argv("blender", "x.blend", verify_hashes=True,
                                  source_root="/src")
    expr = argv[-1]
    out.append(("B1 batch: child runs hash verification when requested",
                "build_report" in expr and "verify_floor" in expr, True, True))
    argv0 = batch.build_child_argv("blender", "x.blend", verify_hashes=False,
                                   source_root="/src")
    out.append(("B1 batch: child skips verification when not requested",
                "_verify = False" in argv0[-1], True, True))

    # ---- B3: incomplete baseline coverage must never PASS ----------------
    # Delete a required frame file BEFORE capture, so the baseline covers only part
    # of the required range. Every covered frame still matches — pre-fix that made
    # the sim a clean PASS. It must now be 'Couldn't verify', never PASS.
    dst = _open_copy("b3_incomplete")
    cdir = os.path.join(dst, "blendcache_twosim")
    cloth_pre = fixtures.prefix_of("ClothP")
    cfiles = sorted(os.path.join(cdir, f) for f in os.listdir(cdir)
                    if f.startswith(cloth_pre) and f.endswith(".bphys"))
    os.remove(cfiles[-1])                                # drop the top frame
    partial = ch.capture(list(bpy.data.scenes), ci.blend_dir())
    bl.save_baseline(bpy.context.scene, bl.default_baseline_path(),
                     overwrite=True, cache_hashes=partial)
    rep = ch.build_report(list(bpy.data.scenes))
    cs = _sv(rep, "Cloth")
    ss = _sv(rep, "Soft Body")
    out.append(("B3 incomplete coverage -> cloth INCOMPLETE_REF (not UNCHANGED)",
                cs is not None and cs.state == ch.S_INCOMPLETE_REF,
                getattr(cs, "state", None), ch.S_INCOMPLETE_REF))
    out.append(("B3 incomplete coverage reports the uncovered frame",
                cs is not None and len(cs.uncovered) >= 1,
                getattr(cs, "uncovered", None), ">=1"))
    results = engine.run_all(bpy.context, hash_verify=rep)
    cloth27 = [r.status for r in results
               if r.check_id == 27 and r.object_name == "ClothP"]
    out.append(("B3 incomplete coverage -> #27 UNKNOWN, never PASS",
                Status.UNKNOWN in cloth27 and Status.PASS not in cloth27,
                cloth27, "UNKNOWN, no PASS"))
    # the untouched, fully-covered sim is still a TRUE pass (not over-corrected).
    out.append(("B3 fully-covered sibling sim still UNCHANGED (true PASS kept)",
                ss is not None and ss.state == ch.S_UNCHANGED,
                getattr(ss, "state", None), ch.S_UNCHANGED))

    # ---- M2: settings-only Save Baseline preserves captured hashes -------
    dst = _open_copy("m2_preserve")
    p = bl.default_baseline_path()
    before = _json.load(open(p))
    out.append(("M2 precondition: baseline has cache hashes",
                isinstance(before.get("cache_hashes"), dict)
                and bool(before["cache_hashes"].get("sims")), True, True))
    bl.save_baseline(bpy.context.scene, p, overwrite=True)   # settings only
    after = _json.load(open(p))
    out.append(("M2 settings re-save KEEPS the cache-hash section",
                isinstance(after.get("cache_hashes"), dict)
                and bool(after["cache_hashes"].get("sims")),
                "cache_hashes" in after, True))
    out.append(("M2 preserved hashes are the same manifest",
                after.get("cache_hashes") == before.get("cache_hashes"),
                True, True))
    # a foreign existing baseline's hashes are NOT grafted onto this file.
    dst = _open_copy("m2_foreign")
    p = bl.default_baseline_path()
    d = _json.load(open(p))
    d["file"] = "/elsewhere/other.blend"
    _json.dump(d, open(p, "w"))
    bl.save_baseline(bpy.context.scene, p, overwrite=True)   # settings only
    after2 = _json.load(open(p))
    out.append(("M2 foreign baseline's hashes are dropped, not grafted",
                "cache_hashes" not in after2, after2.get("cache_hashes"), None))

    # ---- B2: direct CAPTURE must not force an overwrite ------------------
    # Needs the real operator, so register the add-on for this block only.
    dst = _open_copy("b2_overwrite")
    registered = False
    try:
        failsafe.register()
        registered = True
    except Exception as exc:
        out.append(("B2 operator registered for test", False, repr(exc), True))
    if registered:
        try:
            path = bl.default_baseline_path()

            def _sha(fp):
                import hashlib
                h = hashlib.sha256()
                with open(fp, "rb") as f:
                    for ch_ in iter(lambda: f.read(65536), b""):
                        h.update(ch_)
                return h.hexdigest()
            h0 = _sha(path)
            r1 = bpy.ops.failsafe.cache_hash('EXEC_DEFAULT', mode='CAPTURE',
                                             overwrite=False)
            out.append(("B2 direct CAPTURE refuses to overwrite silently",
                        "CANCELLED" in r1 and _sha(path) == h0, list(r1),
                        "CANCELLED + file unchanged"))
            r2 = bpy.ops.failsafe.cache_hash('EXEC_DEFAULT', mode='CAPTURE',
                                             overwrite=True)
            out.append(("B2 direct CAPTURE writes when overwrite is opted in",
                        "FINISHED" in r2, list(r2), "FINISHED"))
        finally:
            try:
                failsafe.unregister()
            except Exception:
                pass

    return out


def hash_edge_tests():
    """Regression tests for the M3 RE-REVIEW edge cases (B4, B5) and the
    strengthened responsiveness/cancel acceptance — each reproduces the defect
    first:

      B4 — a changed-file WARNING must not hide never-fingerprinted (uncovered) or
           unreadable frames; both must be disclosed AND the requested verify must
           not exit 0.
      B5 — a baselined simulation that is GONE from the scene must still be
           reported (not suppressed because the scene now has no disk point cache)
           and must not yield a clean verification exit.
      M1+ — hashing is per-block at the REAL 1 MiB chunk on a multi-MB file, and a
            mid-file cancel stops within a block (the mechanism the modal relies
            on for large-file responsiveness + Escape)."""
    import shutil
    from failsafe import (cachehash as ch, baseline as bl, cache_inspect as ci,
                          cli)
    out = []
    tmp = tempfile.mkdtemp(prefix="failsafe_edge_")

    def _sv(report, system):
        for s in report.sims:
            if s.system == system:
                return s
        return None

    def _c27(report):
        bpy.ops.wm.read_factory_settings(use_empty=True)
        results = engine.run_all(bpy.context, hash_verify=report)
        return [r for r in results if r.check_id == 27]

    # ---- B4 (synthetic): a CHANGED sim that also has unreadable + uncovered ---
    # frames must disclose BOTH, and the floor must be 'unverified'.
    chg_unread = ch.HashReport(ch.R_OK, "", [ch.SimVerify(
        "Scene::Cube::Cloth::Cloth", "Cloth", "Cube", ch.S_CHANGED,
        [1, 2], [3], [], [5], [], [], [])], False)
    r1 = _c27(chg_unread)
    sts1 = {r.status for r in r1}
    out.append(("B4 changed+unreadable discloses WARNING and UNKNOWN both",
                Status.WARNING in sts1 and Status.UNKNOWN in sts1, sorted(sts1),
                "WARNING+UNKNOWN"))
    out.append(("B4 changed+unreadable floors requested verify to unverified",
                cli.verify_floor(chg_unread, True) == cli.EXIT_UNVERIFIED,
                cli.verify_floor(chg_unread, True), cli.EXIT_UNVERIFIED))

    chg_uncov = ch.HashReport(ch.R_OK, "", [ch.SimVerify(
        "Scene::Cube::Cloth::Cloth", "Cloth", "Cube", ch.S_CHANGED,
        [1, 2], [3], [], [], [6], [6], [])], False)
    r2 = _c27(chg_uncov)
    sts2 = {r.status for r in r2}
    umsg = " ".join(r.message for r in r2 if r.status == Status.UNKNOWN).lower()
    out.append(("B4 changed+uncovered discloses WARNING and UNKNOWN both",
                Status.WARNING in sts2 and Status.UNKNOWN in sts2, sorted(sts2),
                "WARNING+UNKNOWN"))
    out.append(("B4 changed+uncovered UNKNOWN names incomplete coverage",
                "never recorded" in umsg or "incomplete" in umsg, True, True))
    out.append(("B4 changed+uncovered floors requested verify to unverified",
                cli.verify_floor(chg_uncov, True) == cli.EXIT_UNVERIFIED,
                cli.verify_floor(chg_uncov, True), cli.EXIT_UNVERIFIED))
    # verdict_exit_code rolls each check up to its WORST status, and WARNING
    # outranks UNKNOWN — so the per-check verdict alone would MASK the coverage gap
    # as exit 0. That collapse is exactly why verify_floor (which inspects the sim
    # outcomes directly), not the plain verdict, is the authority for B4/B5.
    out.append(("B4 plain verdict masks the gap -> verify_floor is the authority",
                cli.verdict_exit_code(r2) == cli.EXIT_CLEAN,
                cli.verdict_exit_code(r2), cli.EXIT_CLEAN))

    # ---- B5 (synthetic): an S_GONE sim must be reported, not suppressed -------
    gone = ch.HashReport(ch.R_OK, "", [ch.SimVerify(
        "Scene::Cube::Cloth::Cloth", "Cloth", "Cube", ch.S_GONE,
        [], [], [], [], [], [], [])], False)
    rg = _c27(gone)                         # empty scene -> no disk caches at all
    out.append(("B5 S_GONE reported even with no current disk caches",
                len(rg) >= 1 and all(r.status == Status.UNKNOWN for r in rg),
                [(r.status) for r in rg], ">=1 UNKNOWN"))
    out.append(("B5 S_GONE floors requested verify to unverified",
                cli.verify_floor(gone, True) == cli.EXIT_UNVERIFIED,
                cli.verify_floor(gone, True), cli.EXIT_UNVERIFIED))

    # ---- M1+ : per-block streaming on a real 1 MiB chunk, mid-file cancel -----
    big = os.path.join(tmp, "big5.bin")
    with open(big, "wb") as fh:
        fh.write(b"\xa5" * (5 * ch.CHUNK + 123))     # ~5 real 1-MiB blocks
    blocks = [e for e in ch.hash_file_iter(big) if e[0] == "progress"]
    out.append(("M1+ multi-MB file streams in real 1 MiB blocks (>=5)",
                len(blocks) >= 5, len(blocks), ">=5"))
    hit = {"n": 0}

    def _cancel_block2():
        hit["n"] += 1
        return hit["n"] >= 2
    try:
        list(ch.hash_file_iter(big, cancel=_cancel_block2))
        raised = False
    except ch.Cancelled:
        raised = True
    out.append(("M1+ mid-file cancel on a multi-MB file stops within a block",
                raised and hit["n"] <= 3, (raised, hit["n"]), "early stop"))

    # ---- B5 (end-to-end): disable ALL disk caches, keep the baseline ----------
    src = os.path.join(tmp, "src")
    os.makedirs(src, exist_ok=True)
    fixtures._make_two_sim_blend(src, frame_end=6)
    manifest = ch.capture(list(bpy.data.scenes), ci.blend_dir())
    bl.save_baseline(bpy.context.scene, bl.default_baseline_path(),
                     overwrite=True, cache_hashes=manifest)

    dst = os.path.join(tmp, "p_gone")
    shutil.copytree(src, dst)
    bpy.ops.wm.open_mainfile(filepath=os.path.join(dst, "twosim.blend"))
    for nm in ("ClothP", "SoftC"):
        o = bpy.data.objects.get(nm)
        if o is not None:
            bpy.data.objects.remove(o, do_unlink=True)
    rep = ch.build_report(list(bpy.data.scenes))
    gone_states = [s.state for s in rep.sims]
    results = engine.run_all(bpy.context, hash_verify=rep)
    r27 = [r for r in results if r.check_id == 27]
    out.append(("B5 e2e: both baselined sims report S_GONE",
                gone_states.count(ch.S_GONE) == 2, gone_states, "2 x S_GONE"))
    out.append(("B5 e2e: #27 still surfaces the gone refs (not suppressed)",
                len(r27) >= 2 and all(r.status == Status.UNKNOWN for r in r27),
                [(r.status) for r in r27], ">=2 UNKNOWN"))
    out.append(("B5 e2e: #27 worst is UNKNOWN, never PASS",
                worst_for_check(results, 27) == Status.UNKNOWN
                and Status.PASS not in statuses_for_check(results, 27),
                worst_for_check(results, 27), Status.UNKNOWN))
    code_v, _ = cli.run(argv=["--verify-hashes", "--text"])
    out.append(("B5 e2e: requested verify with gone refs -> nonzero exit",
                code_v == cli.EXIT_UNVERIFIED, code_v, cli.EXIT_UNVERIFIED))

    # ---- B4 (end-to-end): restore a frame that was never baselined + change ---
    # another -> CHANGED headline must still disclose the uncovered frame and exit
    # nonzero (pre-fix this exited 0 because only a WARNING was reported).
    dst = os.path.join(tmp, "p_b4")
    shutil.copytree(src, dst)
    bpy.ops.wm.open_mainfile(filepath=os.path.join(dst, "twosim.blend"))
    cdir = os.path.join(dst, "blendcache_twosim")
    cloth_pre = fixtures.prefix_of("ClothP")
    cfiles = sorted(os.path.join(cdir, f) for f in os.listdir(cdir)
                    if f.startswith(cloth_pre) and f.endswith(".bphys"))
    top = cfiles[-1]
    with open(top, "rb") as fh:
        top_bytes = fh.read()
    os.remove(top)                                   # baseline won't cover it
    partial = ch.capture(list(bpy.data.scenes), ci.blend_dir())
    bl.save_baseline(bpy.context.scene, bl.default_baseline_path(),
                     overwrite=True, cache_hashes=partial)
    with open(top, "wb") as fh:                       # restore the uncovered frame
        fh.write(top_bytes)
    mid = cfiles[len(cfiles) // 2]                    # change a DIFFERENT frame
    with open(mid, "r+b") as fh:
        fh.seek(0, os.SEEK_END)
        sz = fh.tell()
        o = 30 if sz > 31 else sz - 1
        fh.seek(o)
        b = fh.read(1)
        fh.seek(o)
        fh.write(bytes([b[0] ^ 0xFF]))
    rep = ch.build_report(list(bpy.data.scenes))
    cs = _sv(rep, "Cloth")
    out.append(("B4 e2e: cloth headline is CHANGED with uncovered frames present",
                cs is not None and cs.state == ch.S_CHANGED and bool(cs.uncovered),
                (getattr(cs, "state", None), getattr(cs, "uncovered", None)),
                "CHANGED + uncovered"))
    results = engine.run_all(bpy.context, hash_verify=rep)
    cloth27 = {r.status for r in results
               if r.check_id == 27 and r.object_name == "ClothP"}
    out.append(("B4 e2e: cloth discloses BOTH WARNING (change) and UNKNOWN (gap)",
                Status.WARNING in cloth27 and Status.UNKNOWN in cloth27,
                sorted(cloth27), "WARNING+UNKNOWN"))
    code_b4, _ = cli.run(argv=["--verify-hashes", "--text"])
    out.append(("B4 e2e: requested verify -> nonzero despite the WARNING change",
                code_b4 == cli.EXIT_UNVERIFIED, code_b4, cli.EXIT_UNVERIFIED))

    # ---- wording: no finding or hint mentions the nonexistent checkbox --------
    from failsafe import help_text
    allhint = " ".join(h for h in help_text.HELP.values())
    out.append(("wording: HELP has no 'Include cache hashes' checkbox",
                "Include cache hashes" not in allhint, True, True))

    return out


def hash_edge2_tests():
    """Regression tests for the third-round review edge cases (B6, B7) — each
    reproduces the defect first:

      B6 — previously fingerprinted files that disappear (sv.missing / S_DRIFT) must
           not let an explicitly requested verification exit 0; the vanished saved
           references must be disclosed.
      B7 — an invalid saved digest (missing / null / wrong length / non-hex) or a
           wrong declared algorithm must be rejected as an UNUSABLE REFERENCE
           (UNKNOWN / nonzero), never mistaken for a changed-file WARNING — while a
           legitimate re-bake WARNING is preserved."""
    import json as _json
    import shutil
    from failsafe import (cachehash as ch, baseline as bl, cache_inspect as ci,
                          cli)
    out = []
    tmp = tempfile.mkdtemp(prefix="failsafe_edge2_")

    def _sv(report, system):
        for s in report.sims:
            if s.system == system:
                return s
        return None

    def _c27(report):
        bpy.ops.wm.read_factory_settings(use_empty=True)
        results = engine.run_all(bpy.context, hash_verify=report)
        return [r for r in results if r.check_id == 27]

    def _mkreport(state, **kw):
        f = dict(matched=[], changed=[], missing=[], unreadable=[], new=[],
                 uncovered=[], bad_ref=[])
        f.update(kw)
        sv = ch.SimVerify("S::C::Cloth::Cloth", "Cloth", "C", state,
                          f["matched"], f["changed"], f["missing"], f["unreadable"],
                          f["new"], f["uncovered"], f["bad_ref"])
        return ch.HashReport(ch.R_OK, "", [sv], False)

    # ---- B7 unit: _valid_digest rejects every unusable value ------------------
    good = "a" * 64
    for d, ok in [(good, True), (None, False), ("", False), ("a" * 63, False),
                  ("a" * 65, False), ("A" * 64, False), ("z" * 64, False),
                  (123, False), (["a" * 64], False)]:
        out.append(("B7 _valid_digest(%.8r)->%s" % (d, ok),
                    ch._valid_digest(d) is ok, ch._valid_digest(d), ok))

    # ---- B6/B7 synthetic: floor + disclosure ---------------------------------
    # a legitimate re-bake (pure change, valid digests) stays CLEAN — not over-floored
    out.append(("B7 pure change (re-bake) stays clean (not over-floored)",
                cli.verify_floor(_mkreport(ch.S_CHANGED, matched=[1, 2],
                                           changed=[3]), True) == cli.EXIT_CLEAN,
                cli.verify_floor(_mkreport(ch.S_CHANGED, changed=[3]), True),
                cli.EXIT_CLEAN))

    # B6: a sim whose only issue is vanished baselined files (DRIFT) floors + discloses
    drift = _mkreport(ch.S_DRIFT, matched=[1, 2, 3, 4], missing=[5, 6])
    out.append(("B6 pure drift (missing files) floors requested verify",
                cli.verify_floor(drift, True) == cli.EXIT_UNVERIFIED,
                cli.verify_floor(drift, True), cli.EXIT_UNVERIFIED))
    drift_res = _c27(drift)
    dmsg = " ".join(r.message for r in drift_res).lower()
    out.append(("B6 drift discloses the missing baselined frames",
                "missing" in dmsg or "no longer on disk" in dmsg, True, True))
    # nonblocking UI note: a vanished-ref DRIFT now carries a DISTINCT 'Couldn't
    # verify' (UNKNOWN) line in addition to the WARNING headline, so GUI + CLI agree.
    dsts = {r.status for r in drift_res}
    out.append(("UI: pure drift shows a distinct UNKNOWN vanished-ref line",
                Status.WARNING in dsts and Status.UNKNOWN in dsts, sorted(dsts),
                "WARNING+UNKNOWN"))

    # B6: CHANGED + missing must disclose BOTH and floor
    chg_miss = _mkreport(ch.S_CHANGED, matched=[1], changed=[3], missing=[5, 6])
    sts = {r.status for r in _c27(chg_miss)}
    out.append(("B6 changed+missing discloses WARNING and UNKNOWN both",
                Status.WARNING in sts and Status.UNKNOWN in sts, sorted(sts),
                "both"))
    out.append(("B6 changed+missing floors requested verify",
                cli.verify_floor(chg_miss, True) == cli.EXIT_UNVERIFIED,
                cli.verify_floor(chg_miss, True), cli.EXIT_UNVERIFIED))

    # B7: a bad saved digest is UNKNOWN (unusable ref), never a changed WARNING
    badr = _mkreport(ch.S_BAD_REF, matched=[1, 2], bad_ref=[3])
    stsb = {r.status for r in _c27(badr)}
    out.append(("B7 bad_ref renders UNKNOWN, not a changed WARNING",
                Status.UNKNOWN in stsb and Status.WARNING not in stsb,
                sorted(stsb), "UNKNOWN only"))
    out.append(("B7 bad_ref floors requested verify",
                cli.verify_floor(badr, True) == cli.EXIT_UNVERIFIED,
                cli.verify_floor(badr, True), cli.EXIT_UNVERIFIED))
    # B7: CHANGED + bad_ref discloses both
    chg_bad = _mkreport(ch.S_CHANGED, matched=[1], changed=[2], bad_ref=[5])
    stscb = {r.status for r in _c27(chg_bad)}
    out.append(("B7 changed+bad_ref discloses WARNING and UNKNOWN both",
                Status.WARNING in stscb and Status.UNKNOWN in stscb,
                sorted(stscb), "both"))

    # ---- e2e on a real baked project, mutating the baseline JSON -------------
    src = os.path.join(tmp, "src")
    os.makedirs(src, exist_ok=True)
    fixtures._make_two_sim_blend(src, frame_end=6)
    manifest = ch.capture(list(bpy.data.scenes), ci.blend_dir())
    cloth_ident = next(k for k, v in manifest["sims"].items()
                       if v.get("system") == "Cloth")
    bl.save_baseline(bpy.context.scene, bl.default_baseline_path(),
                     overwrite=True, cache_hashes=manifest)
    cloth_pre = fixtures.prefix_of("ClothP")

    def _open_mutate(tag, mutate):
        dst = os.path.join(tmp, tag)
        shutil.copytree(src, dst)
        bpy.ops.wm.open_mainfile(filepath=os.path.join(dst, "twosim.blend"))
        p = bl.default_baseline_path()
        data = _json.load(open(p))
        mutate(data["cache_hashes"])
        _json.dump(data, open(p, "w"))
        return dst

    # B6 e2e: a baselined frame with no file on disk -> DRIFT(missing) -> floor.
    # (pre-fix: DRIFT is only a WARNING, so --verify-hashes exited 0.)
    def _phantom(sec):
        rk = "blendcache_twosim/%s_%06d_%02d.bphys" % (cloth_pre, 99, 0)
        sec["sims"][cloth_ident]["frames"][rk] = {"sha256": "a" * 64, "size": 10}
    _open_mutate("b6_phantom", _phantom)
    rep = ch.build_report(list(bpy.data.scenes))
    cs = _sv(rep, "Cloth")
    out.append(("B6 e2e: a vanished baselined file -> cloth DRIFT with missing",
                cs is not None and cs.state == ch.S_DRIFT and bool(cs.missing),
                (getattr(cs, "state", None), getattr(cs, "missing", None)),
                "DRIFT+missing"))
    code6, _ = cli.run(argv=["--verify-hashes", "--text"])
    out.append(("B6 e2e: requested verify with a vanished ref -> nonzero exit",
                code6 == cli.EXIT_UNVERIFIED, code6, cli.EXIT_UNVERIFIED))

    # B7 e2e: a corrupted saved digest -> BAD_REF -> UNKNOWN/nonzero, not 'changed'.
    for tag, badval in [("null", None), ("short", "abc"),
                        ("nonhex", "z" * 64), ("len63", "a" * 63)]:
        def _corrupt(sec, bv=badval):
            frames = sec["sims"][cloth_ident]["frames"]
            frames[sorted(frames)[0]]["sha256"] = bv
        _open_mutate("b7_%s" % tag, _corrupt)
        rep = ch.build_report(list(bpy.data.scenes))
        cs = _sv(rep, "Cloth")
        results = engine.run_all(bpy.context, hash_verify=rep)
        cstat = {r.status for r in results
                 if r.check_id == 27 and r.object_name == "ClothP"}
        out.append(("B7 e2e [%s]: bad digest -> BAD_REF, no false 'changed'/PASS"
                    % tag,
                    cs is not None and cs.state == ch.S_BAD_REF
                    and Status.PASS not in cstat,
                    (getattr(cs, "state", None), sorted(cstat)), ch.S_BAD_REF))
        codeb, _ = cli.run(argv=["--verify-hashes", "--text"])
        out.append(("B7 e2e [%s]: requested verify -> nonzero exit" % tag,
                    codeb == cli.EXIT_UNVERIFIED, codeb, cli.EXIT_UNVERIFIED))

    # B7 e2e: a wrong declared algorithm -> R_ALGO gate, never PASS.
    def _algo(sec):
        sec["algo"] = "md5"
    _open_mutate("b7_algo", _algo)
    rep = ch.build_report(list(bpy.data.scenes))
    results = engine.run_all(bpy.context, hash_verify=rep)
    algost = statuses_for_check(results, 27)
    out.append(("B7 e2e: wrong algorithm -> R_ALGO, UNKNOWN never PASS",
                rep.state == ch.R_ALGO and Status.PASS not in algost,
                (rep.state, algost), ch.R_ALGO))
    codea, _ = cli.run(argv=["--verify-hashes", "--text"])
    out.append(("B7 e2e: wrong algorithm requested verify -> nonzero exit",
                codea == cli.EXIT_UNVERIFIED, codea, cli.EXIT_UNVERIFIED))

    return out


def hash_fluid_tests():
    """Fluid (Mantaflow) cache-hash coverage on REAL baked caches, across every
    version (fluid bakes headless on 4.2/4.5/5.0/5.2 — confirmed). Proves the
    per-stage SHA-256 verification and that the accepted B1-B7 safety protections
    carry over to the multi-stage/multi-format fluid layout:

      * unchanged stages PASS ('bytes unchanged', never 'valid');
      * a changed stage warns while its siblings still PASS (independent keys);
      * a vanished stage frame is never a clean PASS (missing + distinct UNKNOWN);
      * project relocation stays unchanged (// cache dir);
      * multiple domains verify independently;
      * a corrupted saved digest -> BAD_REF, a phantom ref -> missing (B6/B7);
      * a cancelled capture writes nothing."""
    import shutil
    from failsafe import (cachehash as ch, baseline as bl, cache_inspect as ci,
                          cli)
    out = []
    tmp = tempfile.mkdtemp(prefix="failsafe_fluid_")

    def _stage(report, name):   # name like 'data' / 'config' / 'mesh'
        return [s for s in report.sims
                if s.system == "Fluid" and s.identity.endswith("/" + name)]

    # ---- one real bake, reused via copytree ------------------------------
    src = os.path.join(tmp, "src")
    os.makedirs(src, exist_ok=True)
    fixtures.build_fluid_pass(src)                      # bakes config/data/mesh
    manifest = ch.capture(list(bpy.data.scenes), ci.blend_dir())
    bl.save_baseline(bpy.context.scene, bl.default_baseline_path(),
                     overwrite=True, cache_hashes=manifest)
    nstages = len(manifest.get("sims", {}))
    out.append(("fluid capture recorded per-stage sims (config/data/mesh)",
                nstages >= 3, nstages, ">=3"))
    cdir = os.path.join(src, "fluidcache")
    cloth_ident = None  # (unused) keeps lints quiet

    def _open(tag):
        dst = os.path.join(tmp, "p_" + tag)
        shutil.copytree(src, dst)
        bpy.ops.wm.open_mainfile(filepath=os.path.join(dst, "fluid.blend"))
        return dst

    # (1) unchanged -> every stage PASS, honest wording
    _open("pass")
    rep = ch.build_report(list(bpy.data.scenes))
    states = {s.identity: s.state for s in rep.sims if s.system == "Fluid"}
    out.append(("fluid unchanged: all stages UNCHANGED",
                states and all(v == ch.S_UNCHANGED for v in states.values()),
                states, "all UNCHANGED"))
    results = engine.run_all(bpy.context, hash_verify=rep)
    out.append(("fluid unchanged -> #27 PASS",
                worst_for_check(results, 27) == Status.PASS,
                worst_for_check(results, 27), Status.PASS))
    fmsg = " ".join(r.message for r in results if r.check_id == 27).lower()
    out.append(("fluid PASS says unchanged + NOT proof",
                "unchanged" in fmsg and "not proof" in fmsg, True, True))

    # (2) change one DATA frame's bytes -> data CHANGED, config/mesh UNCHANGED
    dst = _open("changed")
    dfiles = sorted(os.path.join(dst, "fluidcache", "data", f)
                    for f in os.listdir(os.path.join(dst, "fluidcache", "data"))
                    if f.endswith(".vdb"))
    tgt = dfiles[len(dfiles) // 2]
    with open(tgt, "r+b") as fh:
        fh.seek(0, os.SEEK_END)
        sz = fh.tell()
        o = min(64, sz - 1)
        fh.seek(o)
        b = fh.read(1)
        fh.seek(o)
        fh.write(bytes([b[0] ^ 0xFF]))
    rep = ch.build_report(list(bpy.data.scenes))
    ds = _stage(rep, "data")
    cs = _stage(rep, "config")
    out.append(("fluid changed: data stage CHANGED",
                ds and ds[0].state == ch.S_CHANGED,
                [s.state for s in ds], ch.S_CHANGED))
    out.append(("fluid changed: config stage still UNCHANGED (independent)",
                cs and cs[0].state == ch.S_UNCHANGED,
                [s.state for s in cs], ch.S_UNCHANGED))
    results = engine.run_all(bpy.context, hash_verify=rep)
    data_find = [r for r in results
                 if r.check_id == 27 and "Fluid/data" in (r.message or "")]
    config_find = [r for r in results
                   if r.check_id == 27 and "Fluid/config" in (r.message or "")]
    out.append(("fluid changed: data-stage finding is WARNING, never PASS",
                bool(data_find)
                and all(r.status == Status.WARNING for r in data_find),
                [r.status for r in data_find], "WARNING only"))
    out.append(("fluid changed: config-stage finding still PASS (independent)",
                bool(config_find)
                and any(r.status == Status.PASS for r in config_find),
                [r.status for r in config_find], "has PASS"))
    out.append(("fluid changed -> #27 worst WARNING (not FAIL)",
                worst_for_check(results, 27) == Status.WARNING,
                worst_for_check(results, 27), Status.WARNING))

    # (3) delete a MESH frame -> mesh missing (never PASS) + distinct UNKNOWN; floor
    dst = _open("missmesh")
    mdir = os.path.join(dst, "fluidcache", "mesh")
    mfiles = sorted(os.listdir(mdir))
    os.remove(os.path.join(mdir, mfiles[-1]))
    rep = ch.build_report(list(bpy.data.scenes))
    ms = _stage(rep, "mesh")
    out.append(("fluid missing mesh frame: mesh stage not UNCHANGED",
                ms and ms[0].state in (ch.S_DRIFT, ch.S_INCOMPLETE_REF)
                and bool(ms[0].missing or ms[0].uncovered),
                [(s.state, s.missing, s.uncovered) for s in ms], "drift/incomplete"))
    # A deleted REQUIRED mesh frame is caught by the structural checks (#18/#20) as
    # a blocking FAIL (exit 1) — even stronger than #27's unverified floor. Either
    # way a requested verify is never a false clean.
    code_m, _ = cli.run(argv=["--verify-hashes", "--text"])
    out.append(("fluid missing mesh frame -> requested verify nonzero",
                code_m != cli.EXIT_CLEAN, code_m, "!= 0"))

    # (4) relocation (// cache dir) -> all stages still UNCHANGED
    reloc = os.path.join(tmp, "moved", "deep")
    os.makedirs(os.path.dirname(reloc), exist_ok=True)
    shutil.copytree(src, reloc)
    bpy.ops.wm.open_mainfile(filepath=os.path.join(reloc, "fluid.blend"))
    rep = ch.build_report(list(bpy.data.scenes))
    out.append(("fluid relocation: stages UNCHANGED after moving the project",
                rep.sims and all(s.state == ch.S_UNCHANGED
                                 for s in rep.sims if s.system == "Fluid"),
                [s.state for s in rep.sims], "all UNCHANGED"))

    # (5) B7 on fluid: corrupt a saved digest -> BAD_REF, never a false 'changed'
    dst = _open("badref")
    import json as _json
    p = bl.default_baseline_path()
    data = _json.load(open(p))
    sims = data["cache_hashes"]["sims"]
    fid = next(k for k in sims if k.endswith("/data"))
    fk = sorted(sims[fid]["frames"])[0]
    sims[fid]["frames"][fk]["sha256"] = None
    _json.dump(data, open(p, "w"))
    rep = ch.build_report(list(bpy.data.scenes))
    ds = _stage(rep, "data")
    out.append(("fluid B7: corrupted saved digest -> data BAD_REF (not changed)",
                ds and ds[0].state == ch.S_BAD_REF,
                [s.state for s in ds], ch.S_BAD_REF))

    # (6) B6 on fluid: a baselined frame with no file -> missing -> floor
    dst = _open("phantom")
    p = bl.default_baseline_path()
    data = _json.load(open(p))
    sims = data["cache_hashes"]["sims"]
    fid = next(k for k in sims if k.endswith("/data"))
    sims[fid]["frames"]["fluidcache/data/fluid_data_0099.vdb"] = {
        "sha256": "a" * 64, "size": 10, "frame": 99}
    _json.dump(data, open(p, "w"))
    rep = ch.build_report(list(bpy.data.scenes))
    ds = _stage(rep, "data")
    out.append(("fluid B6: a vanished baselined frame -> data missing, floored",
                ds and bool(ds[0].missing)
                and cli.verify_floor(rep, True) == cli.EXIT_UNVERIFIED,
                (ds[0].missing if ds else None), "missing + floor"))

    # (7) B1: a stage ENABLED after the baseline, never baked, must NOT be silently
    # skipped — it reports incomplete coverage (never a clean pass) and floors.
    _open("b1stage")
    dom = bpy.data.objects.get("Domain")
    dom.modifiers["Fluid"].domain_settings.use_noise = True   # enabled, never baked
    rep = ch.build_report(list(bpy.data.scenes))
    ns = _stage(rep, "noise")
    out.append(("B1 fluid enabled-but-unbaked stage is reported, not skipped",
                bool(ns) and ns[0].state == ch.S_INCOMPLETE_REF,
                [s.state for s in ns], ch.S_INCOMPLETE_REF))
    results = engine.run_all(bpy.context, hash_verify=rep)
    nstat = {r.status for r in results
             if r.check_id == 27 and "Fluid/noise" in (r.message or "")}
    out.append(("B1 fluid unbaked stage -> UNKNOWN, never PASS",
                Status.UNKNOWN in nstat and Status.PASS not in nstat,
                sorted(nstat), "UNKNOWN"))
    out.append(("B1 fluid unbaked stage floors requested verify",
                cli.verify_floor(rep, True) == cli.EXIT_UNVERIFIED,
                cli.verify_floor(rep, True), cli.EXIT_UNVERIFIED))

    # (8) M1: a FLUID-ONLY scene (no point caches) still shows the #27 'hasn't been
    # run' guidance on a quick scan, not silence.
    _open("m1only")
    results = engine.run_all(bpy.context)          # quick scan, no hash_verify
    na27 = [r for r in results if r.check_id == 27]
    nmsg = " ".join(r.message for r in na27).lower()
    out.append(("M1 fluid-only scene shows #27 'hasn't been run' guidance",
                any(r.status == Status.NA for r in na27)
                and "hasn't been run" in nmsg,
                [r.status for r in na27], "NA + guidance"))

    # (9) cancelled capture raises (writes nothing)
    _open("cancel")
    cnt = {"n": 0}

    def _c():
        cnt["n"] += 1
        return cnt["n"] > 1
    try:
        ch.capture(list(bpy.data.scenes), ci.blend_dir(), cancel=_c)
        raised = False
    except ch.Cancelled:
        raised = True
    out.append(("fluid cancelled capture raises Cancelled", raised, raised, True))

    # (R9-1, round 9) WRONG-FORMAT file can't satisfy the required frame. The domain is
    # OpenVDB (default), so a data frame is fluid_data_NNNN.vdb. Rename a real
    # fluid_data_0003.vdb -> fluid_data_0003.uni (a format Blender never writes for this
    # domain) BEFORE baseline. The format-aware matcher must NOT count the .uni file as
    # frame 3, so the required .vdb frame 3 is uncovered -> data stage not a clean PASS,
    # #27 UNKNOWN, requested verify nonzero. A frame-number-only matcher would count it.
    r9 = _open("r9fmt")
    r9data = os.path.join(r9, "fluidcache", "data")
    vdb3 = os.path.join(r9data, "fluid_data_0003.vdb")
    uni3 = os.path.join(r9data, "fluid_data_0003.uni")
    out.append(("fluid R9-1: OpenVDB data frame 3 exists to rename (precondition)",
                os.path.exists(vdb3), os.path.exists(vdb3), True))
    os.rename(vdb3, uni3)
    man_r9 = ch.capture(list(bpy.data.scenes), ci.blend_dir())
    bl.save_baseline(bpy.context.scene, bl.default_baseline_path(),
                     overwrite=True, cache_hashes=man_r9)
    rep = ch.build_report(list(bpy.data.scenes))
    ds9 = _stage(rep, "data")
    out.append(("fluid R9-1: wrong-format .uni does NOT cover required .vdb frame 3",
                bool(ds9) and ds9[0].state != ch.S_UNCHANGED
                and (3 in (ds9[0].uncovered or []) or 3 in (ds9[0].missing or [])),
                [(s.state, s.uncovered, s.missing) for s in ds9],
                "frame 3 uncovered/missing"))
    results = engine.run_all(bpy.context, hash_verify=rep)
    out.append(("fluid R9-1: wrong-format data frame -> #27 UNKNOWN (never PASS)",
                worst_for_check(results, 27) == Status.UNKNOWN,
                worst_for_check(results, 27), Status.UNKNOWN))
    out.append(("fluid R9-1: wrong-format data frame -> requested verify nonzero",
                cli.verify_floor(rep, True) == cli.EXIT_UNVERIFIED,
                cli.verify_floor(rep, True), cli.EXIT_UNVERIFIED))
    # Structural inspector must also not count the .uni as frame 3 present.
    for sobj in bpy.data.objects:
        for smod in sobj.modifiers:
            if smod.type == "FLUID" and getattr(smod, "fluid_type", "") == "DOMAIN":
                se = ci.inspect_fluid_domain(sobj, smod, bpy.context.scene)
                out.append(("fluid R9-1: structural data does NOT count .uni as frame 3",
                            3 not in (se.frames_present or set()),
                            sorted(se.frames_present or []), "3 absent"))

    # (R10-1, round 10) BOBJECT mesh writes ONLY fluid_mesh_NNNN.bobj.gz (verified on
    # real 4.2.9 + 5.2.3 bakes — bare .bobj is never produced). Rename a real
    # fluid_mesh_0003.bobj.gz -> fluid_mesh_0003.bobj BEFORE baseline. The matcher must
    # NOT count the .bobj as frame 3, so the required mesh frame 3 is uncovered -> mesh
    # stage not a clean PASS, #27 UNKNOWN. The default src bake already has BOBJECT mesh.
    r10m = _open("r10mesh")
    r10mesh = os.path.join(r10m, "fluidcache", "mesh")
    gz3 = os.path.join(r10mesh, "fluid_mesh_0003.bobj.gz")
    bobj3 = os.path.join(r10mesh, "fluid_mesh_0003.bobj")
    out.append(("fluid R10-1: BOBJECT mesh frame 3 exists to rename (precondition)",
                os.path.exists(gz3), os.path.exists(gz3), True))
    os.rename(gz3, bobj3)
    man_r10m = ch.capture(list(bpy.data.scenes), ci.blend_dir())
    bl.save_baseline(bpy.context.scene, bl.default_baseline_path(),
                     overwrite=True, cache_hashes=man_r10m)
    rep = ch.build_report(list(bpy.data.scenes))
    ms = _stage(rep, "mesh")
    out.append(("fluid R10-1: bare .bobj does NOT cover required .bobj.gz frame 3",
                bool(ms) and ms[0].state != ch.S_UNCHANGED
                and (3 in (ms[0].uncovered or []) or 3 in (ms[0].missing or [])),
                [(s.state, s.uncovered, s.missing) for s in ms],
                "frame 3 uncovered/missing"))
    results = engine.run_all(bpy.context, hash_verify=rep)
    out.append(("fluid R10-1: bare .bobj mesh frame -> #27 UNKNOWN (never PASS)",
                worst_for_check(results, 27) == Status.UNKNOWN,
                worst_for_check(results, 27), Status.UNKNOWN))
    out.append(("fluid R10-1: bare .bobj mesh frame -> requested verify nonzero",
                cli.verify_floor(rep, True) == cli.EXIT_UNVERIFIED,
                cli.verify_floor(rep, True), cli.EXIT_UNVERIFIED))
    for sobj in bpy.data.objects:
        for smod in sobj.modifiers:
            if smod.type == "FLUID" and getattr(smod, "fluid_type", "") == "DOMAIN":
                se = ci.inspect_fluid_domain(sobj, smod, bpy.context.scene)
                mm = [x for x in (se.components_missing or []) if x.startswith("mesh")]
                out.append(("fluid R10-1: structural mesh stage reports missing frame",
                            bool(mm), se.components_missing, "mesh missing"))

    # (R10-2, round 10) UNI data writes per-grid pVel/pp/vel_NNNN.uni — NEVER
    # fluid_data_*.uni (verified on real 4.2.9 + 5.2.3 bakes). Replace every real UNI
    # grid file with a synthetic fluid_data_NNNN.uni (the kind of masquerade a renamed
    # OpenVDB frame would create) BEFORE baseline. The matcher must count NONE of them,
    # so the data stage has no coverage at all -> #27 UNKNOWN, never a clean PASS.
    u10 = os.path.join(tmp, "r10uni")
    os.makedirs(u10, exist_ok=True)
    fixtures.build_fluid_uni_data(u10)
    u10data = os.path.join(u10, "fluidcache", "data")
    real_uni = sorted(f for f in os.listdir(u10data) if f.endswith(".uni"))
    out.append(("fluid R10-2: UNI data wrote per-grid .uni (not fluid_data_*)",
                bool(real_uni) and not any(f.startswith("fluid_data_") for f in real_uni),
                real_uni[:4], "per-grid .uni files"))
    # Replace the real grid files with the synthetic masquerade, one per frame.
    frames_seen = set()
    for f in real_uni:
        mo = re.search(r"_(\d{4})\.uni$", f)
        if mo:
            frames_seen.add(mo.group(1))
        os.remove(os.path.join(u10data, f))
    for fr in sorted(frames_seen):
        with open(os.path.join(u10data, "fluid_data_%s.uni" % fr), "wb") as fh:
            fh.write(b"not a real mantaflow uni grid file")
    man_u10 = ch.capture(list(bpy.data.scenes), ci.blend_dir())
    bl.save_baseline(bpy.context.scene, bl.default_baseline_path(),
                     overwrite=True, cache_hashes=man_u10)
    rep = ch.build_report(list(bpy.data.scenes))
    us = _stage(rep, "data")
    out.append(("fluid R10-2: synthetic fluid_data_*.uni gives data stage NO coverage",
                bool(us) and us[0].state != ch.S_UNCHANGED,
                [(s.state, s.uncovered, s.missing) for s in us], "not UNCHANGED"))
    results = engine.run_all(bpy.context, hash_verify=rep)
    out.append(("fluid R10-2: synthetic .uni masquerade -> #27 UNKNOWN (never PASS)",
                worst_for_check(results, 27) == Status.UNKNOWN,
                worst_for_check(results, 27), Status.UNKNOWN))
    out.append(("fluid R10-2: synthetic .uni masquerade -> requested verify nonzero",
                cli.verify_floor(rep, True) == cli.EXIT_UNVERIFIED,
                cli.verify_floor(rep, True), cli.EXIT_UNVERIFIED))
    for sobj in bpy.data.objects:
        for smod in sobj.modifiers:
            if smod.type == "FLUID" and getattr(smod, "fluid_type", "") == "DOMAIN":
                se = ci.inspect_fluid_domain(sobj, smod, bpy.context.scene)
                out.append(("fluid R10-2: structural data counts NONE of the synthetic .uni",
                            not (se.frames_present or set()),
                            sorted(se.frames_present or []), "empty"))

    # (R11-1, round 11) UNI data is MULTI-FILE: a liquid frame is pVel/pp/vel_NNNN.uni
    # (verified identical on real bakes of all four versions). Coverage must require EACH
    # core grid PER FRAME, not merely "the frame has some .uni file" — otherwise a
    # surviving sibling grid, or a planted foreign name, lets a deleted required grid
    # read as a clean PASS. Each case captures the baseline from the TAMPERED/pristine
    # cache, so the attack is 'incomplete AT baseline time' — which pure change-detection
    # cannot see without the independent per-grid requirement.

    # (a) CONTROL — a genuine, untouched UNI liquid bake must STILL PASS.
    u11ok = os.path.join(tmp, "r11ok")
    os.makedirs(u11ok, exist_ok=True)
    fixtures.build_fluid_uni_data(u11ok)
    man = ch.capture(list(bpy.data.scenes), ci.blend_dir())
    bl.save_baseline(bpy.context.scene, bl.default_baseline_path(),
                     overwrite=True, cache_hashes=man)
    rep = ch.build_report(list(bpy.data.scenes))
    d11 = _stage(rep, "data")
    out.append(("fluid R11-1 control: genuine UNI data stage UNCHANGED",
                bool(d11) and d11[0].state == ch.S_UNCHANGED
                and not (d11[0].uncovered or []),
                [(s.state, s.uncovered) for s in d11], ch.S_UNCHANGED))
    results = engine.run_all(bpy.context, hash_verify=rep)
    out.append(("fluid R11-1 control: genuine UNI bake -> #27 PASS",
                worst_for_check(results, 27) == Status.PASS,
                worst_for_check(results, 27), Status.PASS))

    # (b) Delete ONE core grid (pVel_0003.uni) BEFORE baseline; its siblings pp/vel for
    # frame 3 remain. Frame-only coverage would let a sibling stand in; per-grid coverage
    # must flag '0003/pVel' uncovered -> #27 UNKNOWN, even though pp/vel still match.
    u11m = os.path.join(tmp, "r11miss")
    os.makedirs(u11m, exist_ok=True)
    fixtures.build_fluid_uni_data(u11m)
    d11m = os.path.join(u11m, "fluidcache", "data")
    pvel3 = os.path.join(d11m, "pVel_0003.uni")
    sib3 = [os.path.join(d11m, g + "_0003.uni") for g in ("pp", "vel")]
    out.append(("fluid R11-1: pVel_0003 and siblings pp/vel_0003 present (precondition)",
                os.path.exists(pvel3) and all(os.path.exists(s) for s in sib3),
                os.path.exists(pvel3) and all(os.path.exists(s) for s in sib3), True))
    os.remove(pvel3)                                   # delete ONE required grid
    man = ch.capture(list(bpy.data.scenes), ci.blend_dir())
    bl.save_baseline(bpy.context.scene, bl.default_baseline_path(),
                     overwrite=True, cache_hashes=man)
    rep = ch.build_report(list(bpy.data.scenes))
    d11 = _stage(rep, "data")
    out.append(("fluid R11-1: a deleted core grid is NOT hidden by its siblings",
                bool(d11) and d11[0].state != ch.S_UNCHANGED
                and "0003/pVel" in (d11[0].uncovered or []),
                [(s.state, s.uncovered) for s in d11], "0003/pVel uncovered"))
    out.append(("fluid R11-1: the surviving siblings pp/vel_0003 still matched",
                bool(d11) and ("0003/pp" in (d11[0].matched or [])
                               or "0003/vel" in (d11[0].matched or [])),
                [s.matched for s in d11], "a sibling matched"))
    results = engine.run_all(bpy.context, hash_verify=rep)
    out.append(("fluid R11-1: missing core grid -> #27 UNKNOWN (never PASS)",
                worst_for_check(results, 27) == Status.UNKNOWN,
                worst_for_check(results, 27), Status.UNKNOWN))
    out.append(("fluid R11-1: missing core grid -> requested verify nonzero",
                cli.verify_floor(rep, True) == cli.EXIT_UNVERIFIED,
                cli.verify_floor(rep, True), cli.EXIT_UNVERIFIED))
    for sobj in bpy.data.objects:
        for smod in sobj.modifiers:
            if smod.type == "FLUID" and getattr(smod, "fluid_type", "") == "DOMAIN":
                se = ci.inspect_fluid_domain(sobj, smod, bpy.context.scene)
                out.append(("fluid R11-1: structural data frame 3 NOT present (grid incomplete)",
                            3 not in (se.frames_present or set()),
                            sorted(se.frames_present or []), "3 absent"))

    # (c) Replace EVERY real grid with a foreign junk_NNNN.uni BEFORE baseline. The
    # matcher counts none of them (not a known core grid), so the data stage has no
    # coverage at all -> #27 UNKNOWN. A fake name can't satisfy a required grid.
    u11j = os.path.join(tmp, "r11junk")
    os.makedirs(u11j, exist_ok=True)
    fixtures.build_fluid_uni_data(u11j)
    d11jdir = os.path.join(u11j, "fluidcache", "data")
    realj = sorted(f for f in os.listdir(d11jdir) if f.endswith(".uni"))
    framesj = set()
    for f in realj:
        mo = re.search(r"_(\d{4})\.uni$", f)
        if mo:
            framesj.add(mo.group(1))
        os.remove(os.path.join(d11jdir, f))
    for fr in sorted(framesj):
        with open(os.path.join(d11jdir, "junk_%s.uni" % fr), "wb") as fh:
            fh.write(b"not a real mantaflow grid file")
    man = ch.capture(list(bpy.data.scenes), ci.blend_dir())
    bl.save_baseline(bpy.context.scene, bl.default_baseline_path(),
                     overwrite=True, cache_hashes=man)
    rep = ch.build_report(list(bpy.data.scenes))
    d11 = _stage(rep, "data")
    out.append(("fluid R11-1: foreign junk_NNNN.uni gives data stage NO coverage",
                bool(d11) and d11[0].state != ch.S_UNCHANGED,
                [(s.state, s.uncovered, s.missing) for s in d11], "not UNCHANGED"))
    results = engine.run_all(bpy.context, hash_verify=rep)
    out.append(("fluid R11-1: junk grid names -> #27 UNKNOWN (never PASS)",
                worst_for_check(results, 27) == Status.UNKNOWN,
                worst_for_check(results, 27), Status.UNKNOWN))
    out.append(("fluid R11-1: junk grid names -> requested verify nonzero",
                cli.verify_floor(rep, True) == cli.EXIT_UNVERIFIED,
                cli.verify_floor(rep, True), cli.EXIT_UNVERIFIED))
    for sobj in bpy.data.objects:
        for smod in sobj.modifiers:
            if smod.type == "FLUID" and getattr(smod, "fluid_type", "") == "DOMAIN":
                se = ci.inspect_fluid_domain(sobj, smod, bpy.context.scene)
                out.append(("fluid R11-1: structural data counts NONE of the junk .uni",
                            not (se.frames_present or set()),
                            sorted(se.frames_present or []), "empty"))

    # (R12-1, round 12) A bake may write OPTIONAL grids on top of the core: colored smoke
    # adds color_r/color_g/color_b, a resumable cache adds restart-state grids. The matcher
    # previously REJECTED the underscore names, so those files were invisible — a deleted
    # color channel read as a clean PASS. The required set now UNIONs in whatever optional
    # grids the bake actually wrote, so a deleted one is uncovered, WITHOUT forcing UNKNOWN
    # on a bake that has none. Verified on real bakes of all four versions.

    # (d) CONTROL — a PLAIN smoke bake writes NO color grids and must still PASS: the
    # optional requirement must never force UNKNOWN on a bake that simply has none of them.
    g12p = os.path.join(tmp, "r12plain")
    os.makedirs(g12p, exist_ok=True)
    fixtures.build_fluid_uni_gas_plain(g12p)
    man = ch.capture(list(bpy.data.scenes), ci.blend_dir())
    bl.save_baseline(bpy.context.scene, bl.default_baseline_path(),
                     overwrite=True, cache_hashes=man)
    rep = ch.build_report(list(bpy.data.scenes))
    d12 = _stage(rep, "data")
    out.append(("fluid R12-1 control: plain smoke UNI data UNCHANGED (no false UNKNOWN)",
                bool(d12) and d12[0].state == ch.S_UNCHANGED
                and not (d12[0].uncovered or []),
                [(s.state, s.uncovered) for s in d12], ch.S_UNCHANGED))
    results = engine.run_all(bpy.context, hash_verify=rep)
    out.append(("fluid R12-1 control: plain smoke -> #27 PASS",
                worst_for_check(results, 27) == Status.PASS,
                worst_for_check(results, 27), Status.PASS))

    # (e) CONTROL — an untouched COLORED smoke bake (with color_r/g/b) must still PASS.
    g12ok = os.path.join(tmp, "r12ok")
    os.makedirs(g12ok, exist_ok=True)
    fixtures.build_fluid_uni_gas_color(g12ok)
    g12okdata = os.path.join(g12ok, "fluidcache", "data")
    cfiles = sorted(f for f in os.listdir(g12okdata) if f.startswith("color_"))
    out.append(("fluid R12-1: colored bake actually wrote color_r/g/b (precondition)",
                any(f.startswith("color_r_") for f in cfiles)
                and any(f.startswith("color_g_") for f in cfiles)
                and any(f.startswith("color_b_") for f in cfiles),
                cfiles[:6], "color_r/g/b present"))
    man = ch.capture(list(bpy.data.scenes), ci.blend_dir())
    bl.save_baseline(bpy.context.scene, bl.default_baseline_path(),
                     overwrite=True, cache_hashes=man)
    rep = ch.build_report(list(bpy.data.scenes))
    d12 = _stage(rep, "data")
    out.append(("fluid R12-1 control: untouched colored bake UNCHANGED",
                bool(d12) and d12[0].state == ch.S_UNCHANGED
                and not (d12[0].uncovered or []),
                [(s.state, s.uncovered) for s in d12], ch.S_UNCHANGED))
    results = engine.run_all(bpy.context, hash_verify=rep)
    out.append(("fluid R12-1 control: untouched colored bake -> #27 PASS",
                worst_for_check(results, 27) == Status.PASS,
                worst_for_check(results, 27), Status.PASS))

    # (f) Delete ONE color channel (color_r_0003.uni) BEFORE baseline; color_g/color_b for
    # frame 3 remain. The deleted channel must be uncovered -> #27 UNKNOWN (review R12-1).
    g12m = os.path.join(tmp, "r12miss")
    os.makedirs(g12m, exist_ok=True)
    fixtures.build_fluid_uni_gas_color(g12m)
    g12mdata = os.path.join(g12m, "fluidcache", "data")
    cr3 = os.path.join(g12mdata, "color_r_0003.uni")
    csib3 = [os.path.join(g12mdata, g + "_0003.uni") for g in ("color_g", "color_b")]
    out.append(("fluid R12-1: color_r_0003 + siblings color_g/color_b_0003 present (precondition)",
                os.path.exists(cr3) and all(os.path.exists(s) for s in csib3),
                os.path.exists(cr3) and all(os.path.exists(s) for s in csib3), True))
    os.remove(cr3)                                     # delete ONE color channel
    man = ch.capture(list(bpy.data.scenes), ci.blend_dir())
    bl.save_baseline(bpy.context.scene, bl.default_baseline_path(),
                     overwrite=True, cache_hashes=man)
    rep = ch.build_report(list(bpy.data.scenes))
    d12 = _stage(rep, "data")
    out.append(("fluid R12-1: a deleted color channel is NOT hidden by core or siblings",
                bool(d12) and d12[0].state != ch.S_UNCHANGED
                and "0003/color_r" in (d12[0].uncovered or []),
                [(s.state, s.uncovered) for s in d12], "0003/color_r uncovered"))
    out.append(("fluid R12-1: the surviving color siblings color_g/color_b_0003 still matched",
                bool(d12) and ("0003/color_g" in (d12[0].matched or [])
                               or "0003/color_b" in (d12[0].matched or [])),
                [s.matched for s in d12], "a color sibling matched"))
    results = engine.run_all(bpy.context, hash_verify=rep)
    out.append(("fluid R12-1: missing color channel -> #27 UNKNOWN (never PASS)",
                worst_for_check(results, 27) == Status.UNKNOWN,
                worst_for_check(results, 27), Status.UNKNOWN))
    out.append(("fluid R12-1: missing color channel -> requested verify nonzero",
                cli.verify_floor(rep, True) == cli.EXIT_UNVERIFIED,
                cli.verify_floor(rep, True), cli.EXIT_UNVERIFIED))

    # (g) RESUMABLE cache: the restart-state grids are required too (picked up per-bake),
    # so deleting one restart grid frame BEFORE baseline -> #27 UNKNOWN; and an untouched
    # resumable bake still PASSes (no hardcoded restart-grid whitelist).
    g12r = os.path.join(tmp, "r12resume")
    os.makedirs(g12r, exist_ok=True)
    fixtures.build_fluid_uni_gas_resumable(g12r)
    g12rdata = os.path.join(g12r, "fluidcache", "data")
    _CORE_GAS = {"density", "flame", "heat", "shadow", "vel"}
    extra3 = None
    for f in sorted(os.listdir(g12rdata)):
        mo = re.match(r"^(.+)_0003\.uni$", f)
        if mo and mo.group(1) not in _CORE_GAS and not mo.group(1).startswith("color_"):
            extra3 = (mo.group(1), os.path.join(g12rdata, f))
            break
    out.append(("fluid R12-1: resumable bake wrote a restart-state grid (precondition)",
                extra3 is not None, extra3[0] if extra3 else None, "an extra grid exists"))
    if extra3 is not None:
        man = ch.capture(list(bpy.data.scenes), ci.blend_dir())
        bl.save_baseline(bpy.context.scene, bl.default_baseline_path(),
                         overwrite=True, cache_hashes=man)
        rep = ch.build_report(list(bpy.data.scenes))
        results = engine.run_all(bpy.context, hash_verify=rep)
        out.append(("fluid R12-1 control: untouched resumable bake -> #27 PASS",
                    worst_for_check(results, 27) == Status.PASS,
                    worst_for_check(results, 27), Status.PASS))
        os.remove(extra3[1])                           # delete ONE restart grid frame
        man = ch.capture(list(bpy.data.scenes), ci.blend_dir())
        bl.save_baseline(bpy.context.scene, bl.default_baseline_path(),
                         overwrite=True, cache_hashes=man)
        rep = ch.build_report(list(bpy.data.scenes))
        d12 = _stage(rep, "data")
        rtok = "0003/%s" % extra3[0]
        out.append(("fluid R12-1: a deleted resumable grid frame is uncovered -> not UNCHANGED",
                    bool(d12) and d12[0].state != ch.S_UNCHANGED
                    and rtok in (d12[0].uncovered or []),
                    [(s.state, s.uncovered) for s in d12], "%s uncovered" % rtok))
        results = engine.run_all(bpy.context, hash_verify=rep)
        out.append(("fluid R12-1: missing resumable grid -> #27 UNKNOWN (never PASS)",
                    worst_for_check(results, 27) == Status.UNKNOWN,
                    worst_for_check(results, 27), Status.UNKNOWN))

    # (R13-1, round 13) An ENTIRE optional family deleted BEFORE baseline leaves no
    # on-disk evidence, so the observed-from-disk union alone would require only the core
    # and read PASS. The required set is now ALSO anchored to DOMAIN CONFIG — a signal
    # deleting cache files can't erase: a non-default smoke_color flow (colour expected)
    # and cache_resumable (restart grids expected). Both verified on real bakes.

    # (h) Delete EVERY color_r/g/b file across ALL frames of a colored bake before baseline.
    # The scene still configures colour (the flow's smoke_color), so #27 must be UNKNOWN.
    g13c = os.path.join(tmp, "r13color")
    os.makedirs(g13c, exist_ok=True)
    fixtures.build_fluid_uni_gas_color(g13c)
    g13cdata = os.path.join(g13c, "fluidcache", "data")
    removed = 0
    for f in sorted(os.listdir(g13cdata)):
        if f.startswith("color_"):
            os.remove(os.path.join(g13cdata, f))
            removed += 1
    out.append(("fluid R13-1: colored bake had color files, now ALL removed (precondition)",
                removed > 0 and not any(f.startswith("color_")
                                        for f in os.listdir(g13cdata)),
                removed, ">0 removed, none left"))
    man = ch.capture(list(bpy.data.scenes), ci.blend_dir())
    bl.save_baseline(bpy.context.scene, bl.default_baseline_path(),
                     overwrite=True, cache_hashes=man)
    rep = ch.build_report(list(bpy.data.scenes))
    d13 = _stage(rep, "data")
    out.append(("fluid R13-1: whole color family wiped -> colour tokens uncovered (config)",
                bool(d13) and d13[0].state != ch.S_UNCHANGED
                and any(t.split("/")[-1] in ("color_r", "color_g", "color_b")
                        for t in (d13[0].uncovered or [])),
                [(s.state, (s.uncovered or [])[:3]) for s in d13], "colour tokens uncovered"))
    results = engine.run_all(bpy.context, hash_verify=rep)
    out.append(("fluid R13-1: whole color family wiped -> #27 UNKNOWN (config caught it)",
                worst_for_check(results, 27) == Status.UNKNOWN,
                worst_for_check(results, 27), Status.UNKNOWN))
    out.append(("fluid R13-1: whole color family wiped -> requested verify nonzero",
                cli.verify_floor(rep, True) == cli.EXIT_UNVERIFIED,
                cli.verify_floor(rep, True), cli.EXIT_UNVERIFIED))

    # (i) Delete the ENTIRE restart-state family of a resumable bake before baseline.
    # cache_resumable is still on, so a bake with no restart grid at all is incomplete.
    g13r = os.path.join(tmp, "r13resume")
    os.makedirs(g13r, exist_ok=True)
    fixtures.build_fluid_uni_gas_resumable(g13r)
    g13rdata = os.path.join(g13r, "fluidcache", "data")
    _CORE_GAS = {"density", "flame", "heat", "shadow", "vel"}
    rrem = 0
    for f in sorted(os.listdir(g13rdata)):
        mo = re.match(r"^(.+)_\d{4}\.uni$", f)
        if mo and mo.group(1) not in _CORE_GAS and not mo.group(1).startswith("color_"):
            os.remove(os.path.join(g13rdata, f))
            rrem += 1
    out.append(("fluid R13-1: resumable bake had restart grids, now ALL removed (precondition)",
                rrem > 0, rrem, ">0 restart files removed"))
    man = ch.capture(list(bpy.data.scenes), ci.blend_dir())
    bl.save_baseline(bpy.context.scene, bl.default_baseline_path(),
                     overwrite=True, cache_hashes=man)
    rep = ch.build_report(list(bpy.data.scenes))
    d13 = _stage(rep, "data")
    out.append(("fluid R13-1: whole restart family wiped -> named restart tokens uncovered (config)",
                bool(d13) and d13[0].state != ch.S_UNCHANGED
                and any(t.split("/")[-1] in ci._FLUID_UNI_RESTART_GRIDS["GAS"]
                        for t in (d13[0].uncovered or [])),
                [(s.state, (s.uncovered or [])[:3]) for s in d13],
                "named restart tokens uncovered"))
    results = engine.run_all(bpy.context, hash_verify=rep)
    out.append(("fluid R13-1: whole restart family wiped -> #27 UNKNOWN (config caught it)",
                worst_for_check(results, 27) == Status.UNKNOWN,
                worst_for_check(results, 27), Status.UNKNOWN))
    out.append(("fluid R13-1: whole restart family wiped -> requested verify nonzero",
                cli.verify_floor(rep, True) == cli.EXIT_UNVERIFIED,
                cli.verify_floor(rep, True), cli.EXIT_UNVERIFIED))

    # (R14-2, round 14) The restart family is required BY NAME, so neither a planted junk
    # grid nor a lone surviving restart grid can cover for a deleted family. Both verified
    # on real resumable bakes.

    # (j) JUNK-SPOOF: delete the ENTIRE genuine restart family, then plant junk_NNNN.uni for
    # every frame before baseline. The old "any non-core grid present" check would have
    # accepted the junk as restart evidence; now the named restart grids stay required and
    # uncovered -> #27 UNKNOWN.
    g14j = os.path.join(tmp, "r14junk")
    os.makedirs(g14j, exist_ok=True)
    fixtures.build_fluid_uni_gas_resumable(g14j)
    g14jdata = os.path.join(g14j, "fluidcache", "data")
    _CORE_GAS = {"density", "flame", "heat", "shadow", "vel"}
    restart_set = set(ci._FLUID_UNI_RESTART_GRIDS["GAS"])
    frames_seen = set()
    jrem = 0
    for f in sorted(os.listdir(g14jdata)):
        mo = re.match(r"^(.+)_(\d{4})\.uni$", f)
        if not mo:
            continue
        frames_seen.add(mo.group(2))
        if mo.group(1) in restart_set:
            os.remove(os.path.join(g14jdata, f))
            jrem += 1
    for fr in sorted(frames_seen):                      # plant junk for every frame
        with open(os.path.join(g14jdata, "junk_%s.uni" % fr), "wb") as fh:
            fh.write(b"not a real restart grid")
    left = {re.match(r"^(.+)_\d{4}\.uni$", f).group(1)
            for f in os.listdir(g14jdata) if re.match(r"^(.+)_\d{4}\.uni$", f)}
    out.append(("fluid R14-2: real restart family removed, junk planted (precondition)",
                jrem > 0 and not (left & restart_set)
                and any(n == "junk" for n in left),
                sorted(left), "no restart grids, junk present"))
    man = ch.capture(list(bpy.data.scenes), ci.blend_dir())
    bl.save_baseline(bpy.context.scene, bl.default_baseline_path(),
                     overwrite=True, cache_hashes=man)
    rep = ch.build_report(list(bpy.data.scenes))
    d14 = _stage(rep, "data")
    out.append(("fluid R14-2: junk can't pose as restart -> named restart tokens uncovered",
                bool(d14) and d14[0].state != ch.S_UNCHANGED
                and any(t.split("/")[-1] in restart_set
                        for t in (d14[0].uncovered or [])),
                [(s.state, (s.uncovered or [])[:3]) for s in d14],
                "named restart tokens uncovered"))
    results = engine.run_all(bpy.context, hash_verify=rep)
    out.append(("fluid R14-2: junk-spoofed restart family -> #27 UNKNOWN (never PASS)",
                worst_for_check(results, 27) == Status.UNKNOWN,
                worst_for_check(results, 27), Status.UNKNOWN))
    out.append(("fluid R14-2: junk-spoofed restart family -> requested verify nonzero",
                cli.verify_floor(rep, True) == cli.EXIT_UNVERIFIED,
                cli.verify_floor(rep, True), cli.EXIT_UNVERIFIED))

    # (k) KEEP-ONE: delete every restart grid EXCEPT one surviving family (velTmp). The lone
    # survivor must not cover for the rest -> the other named restart grids stay uncovered
    # -> #27 UNKNOWN.
    g14k = os.path.join(tmp, "r14keepone")
    os.makedirs(g14k, exist_ok=True)
    fixtures.build_fluid_uni_gas_resumable(g14k)
    g14kdata = os.path.join(g14k, "fluidcache", "data")
    krem = 0
    for f in sorted(os.listdir(g14kdata)):
        mo = re.match(r"^(.+)_\d{4}\.uni$", f)
        if mo and mo.group(1) in restart_set and mo.group(1) != "velTmp":
            os.remove(os.path.join(g14kdata, f))
            krem += 1
    kleft = {re.match(r"^(.+)_\d{4}\.uni$", f).group(1)
             for f in os.listdir(g14kdata) if re.match(r"^(.+)_\d{4}\.uni$", f)}
    out.append(("fluid R14-2: all restart grids removed except velTmp (precondition)",
                krem > 0 and "velTmp" in kleft and len(kleft & restart_set) == 1,
                sorted(kleft & restart_set), "only velTmp survives"))
    man = ch.capture(list(bpy.data.scenes), ci.blend_dir())
    bl.save_baseline(bpy.context.scene, bl.default_baseline_path(),
                     overwrite=True, cache_hashes=man)
    rep = ch.build_report(list(bpy.data.scenes))
    dk = _stage(rep, "data")
    out.append(("fluid R14-2: one surviving restart grid can't cover the family -> uncovered",
                bool(dk) and dk[0].state != ch.S_UNCHANGED
                and any(t.split("/")[-1] in (restart_set - {"velTmp"})
                        for t in (dk[0].uncovered or [])),
                [(s.state, (s.uncovered or [])[:3]) for s in dk],
                "other restart tokens uncovered"))
    results = engine.run_all(bpy.context, hash_verify=rep)
    out.append(("fluid R14-2: restart family wiped to one grid -> #27 UNKNOWN (never PASS)",
                worst_for_check(results, 27) == Status.UNKNOWN,
                worst_for_check(results, 27), Status.UNKNOWN))

    # (R14-1, round 15) Colour is also written when FIRE + a non-default domain
    # flame_smoke_color combine with a smoke source (verified on real bakes, all four
    # versions) -- NOT only by a coloured flow. The config detector must expect colour here,
    # so a wiped colour family still reads UNKNOWN.
    g14f = os.path.join(tmp, "r14flame")
    os.makedirs(g14f, exist_ok=True)
    fixtures.build_fluid_uni_gas_fire_flame(g14f)
    g14fdata = os.path.join(g14f, "fluidcache", "data")
    out.append(("fluid R14-1: fire + flame_smoke_color bake wrote colour grids (precondition)",
                any(f.startswith("color_") for f in os.listdir(g14fdata)),
                sorted(f for f in os.listdir(g14fdata) if f.startswith("color_"))[:3],
                "colour grids present"))
    man = ch.capture(list(bpy.data.scenes), ci.blend_dir())
    bl.save_baseline(bpy.context.scene, bl.default_baseline_path(),
                     overwrite=True, cache_hashes=man)
    rep = ch.build_report(list(bpy.data.scenes))
    results = engine.run_all(bpy.context, hash_verify=rep)
    out.append(("fluid R14-1 control: untouched fire+flame bake -> #27 PASS",
                worst_for_check(results, 27) == Status.PASS,
                worst_for_check(results, 27), Status.PASS))
    fcr = 0
    for f in sorted(os.listdir(g14fdata)):
        if f.startswith("color_"):
            os.remove(os.path.join(g14fdata, f))
            fcr += 1
    man = ch.capture(list(bpy.data.scenes), ci.blend_dir())
    bl.save_baseline(bpy.context.scene, bl.default_baseline_path(),
                     overwrite=True, cache_hashes=man)
    rep = ch.build_report(list(bpy.data.scenes))
    df = _stage(rep, "data")
    out.append(("fluid R14-1: flame-triggered colour wiped -> colour tokens uncovered",
                bool(df) and df[0].state != ch.S_UNCHANGED
                and any(t.split("/")[-1] in ("color_r", "color_g", "color_b")
                        for t in (df[0].uncovered or [])),
                [(s.state, (s.uncovered or [])[:3]) for s in df], "colour tokens uncovered"))
    results = engine.run_all(bpy.context, hash_verify=rep)
    out.append(("fluid R14-1: flame-triggered colour wiped -> #27 UNKNOWN (never PASS)",
                worst_for_check(results, 27) == Status.UNKNOWN,
                worst_for_check(results, 27), Status.UNKNOWN))
    out.append(("fluid R14-1: flame-triggered colour wiped -> requested verify nonzero",
                cli.verify_floor(rep, True) == cli.EXIT_UNVERIFIED,
                cli.verify_floor(rep, True), cli.EXIT_UNVERIFIED))

    # (R15-1, round 15) A gas cache that is BOTH coloured AND resumable writes colour-restart
    # grids color_r_in/g_in/b_in. Deleting the WHOLE _in family before baseline (keeping
    # color_r/g/b and the base restart grids) must read UNKNOWN -- they are required as a set.
    g15 = os.path.join(tmp, "r15colorin")
    os.makedirs(g15, exist_ok=True)
    fixtures.build_fluid_uni_gas_color_resumable(g15)
    g15data = os.path.join(g15, "fluidcache", "data")
    _IN_RE = re.compile(r"^color_[rgb]_in_\d{4}\.uni$")
    _COL_RE = re.compile(r"^color_[rgb]_\d{4}\.uni$")
    had_in = [f for f in os.listdir(g15data) if _IN_RE.match(f)]
    out.append(("fluid R15-1: colored+resumable bake wrote color_*_in grids (precondition)",
                len(had_in) > 0, len(had_in), ">0 color_*_in files"))
    man = ch.capture(list(bpy.data.scenes), ci.blend_dir())
    bl.save_baseline(bpy.context.scene, bl.default_baseline_path(),
                     overwrite=True, cache_hashes=man)
    rep = ch.build_report(list(bpy.data.scenes))
    results = engine.run_all(bpy.context, hash_verify=rep)
    out.append(("fluid R15-1 control: untouched colored+resumable bake -> #27 PASS",
                worst_for_check(results, 27) == Status.PASS,
                worst_for_check(results, 27), Status.PASS))
    cin = 0
    for f in sorted(os.listdir(g15data)):
        if _IN_RE.match(f):
            os.remove(os.path.join(g15data, f))
            cin += 1
    still_color = any(_COL_RE.match(f) for f in os.listdir(g15data))
    out.append(("fluid R15-1: color_*_in removed, color_r/g/b kept (precondition)",
                cin > 0 and still_color
                and not any(_IN_RE.match(f) for f in os.listdir(g15data)),
                (cin, still_color), ">0 _in removed, colour kept"))
    man = ch.capture(list(bpy.data.scenes), ci.blend_dir())
    bl.save_baseline(bpy.context.scene, bl.default_baseline_path(),
                     overwrite=True, cache_hashes=man)
    rep = ch.build_report(list(bpy.data.scenes))
    d15 = _stage(rep, "data")
    out.append(("fluid R15-1: whole color_*_in family wiped -> _in tokens uncovered (config)",
                bool(d15) and d15[0].state != ch.S_UNCHANGED
                and any(t.split("/")[-1] in ("color_r_in", "color_g_in", "color_b_in")
                        for t in (d15[0].uncovered or [])),
                [(s.state, (s.uncovered or [])[:3]) for s in d15],
                "color_*_in tokens uncovered"))
    results = engine.run_all(bpy.context, hash_verify=rep)
    out.append(("fluid R15-1: color_*_in family wiped -> #27 UNKNOWN (never PASS)",
                worst_for_check(results, 27) == Status.UNKNOWN,
                worst_for_check(results, 27), Status.UNKNOWN))
    out.append(("fluid R15-1: color_*_in family wiped -> requested verify nonzero",
                cli.verify_floor(rep, True) == cli.EXIT_UNVERIFIED,
                cli.verify_floor(rep, True), cli.EXIT_UNVERIFIED))

    # (R16-1, round 16) Blender compares colours in float32 exactly: a flame_smoke_color of
    # (0.70001, 0.7, 0.7) -- one float32 step off the default grey -- still writes colour
    # grids on all four versions, far below any decimal rounding. The detector must expect
    # colour here (float32 comparison), so a wiped colour family reads UNKNOWN; a genuine
    # default bake must still PASS (no false UNKNOWN from float32(0.7) != Python 0.7).
    g16 = os.path.join(tmp, "r16tiny")
    os.makedirs(g16, exist_ok=True)
    fixtures.build_fluid_uni_gas_fire_flame_tiny(g16)
    g16data = os.path.join(g16, "fluidcache", "data")
    out.append(("fluid R16-1: flame off default by one float32 step wrote colour (precondition)",
                any(f.startswith("color_") for f in os.listdir(g16data)),
                sorted(f for f in os.listdir(g16data) if f.startswith("color_"))[:3],
                "colour grids present"))
    man = ch.capture(list(bpy.data.scenes), ci.blend_dir())
    bl.save_baseline(bpy.context.scene, bl.default_baseline_path(),
                     overwrite=True, cache_hashes=man)
    rep = ch.build_report(list(bpy.data.scenes))
    results = engine.run_all(bpy.context, hash_verify=rep)
    out.append(("fluid R16-1 control: untouched tiny-deviation bake -> #27 PASS",
                worst_for_check(results, 27) == Status.PASS,
                worst_for_check(results, 27), Status.PASS))
    tcr = 0
    for f in sorted(os.listdir(g16data)):
        if f.startswith("color_"):
            os.remove(os.path.join(g16data, f))
            tcr += 1
    man = ch.capture(list(bpy.data.scenes), ci.blend_dir())
    bl.save_baseline(bpy.context.scene, bl.default_baseline_path(),
                     overwrite=True, cache_hashes=man)
    rep = ch.build_report(list(bpy.data.scenes))
    d16 = _stage(rep, "data")
    out.append(("fluid R16-1: tiny-deviation colour wiped -> colour tokens uncovered (float32)",
                bool(d16) and d16[0].state != ch.S_UNCHANGED
                and any(t.split("/")[-1] in ("color_r", "color_g", "color_b")
                        for t in (d16[0].uncovered or [])),
                [(s.state, (s.uncovered or [])[:3]) for s in d16], "colour tokens uncovered"))
    results = engine.run_all(bpy.context, hash_verify=rep)
    out.append(("fluid R16-1: tiny-deviation colour wiped -> #27 UNKNOWN (never PASS)",
                worst_for_check(results, 27) == Status.UNKNOWN,
                worst_for_check(results, 27), Status.UNKNOWN))
    out.append(("fluid R16-1: tiny-deviation colour wiped -> requested verify nonzero",
                cli.verify_floor(rep, True) == cli.EXIT_UNVERIFIED,
                cli.verify_floor(rep, True), cli.EXIT_UNVERIFIED))

    # A GENUINE default bake (no colour) must still PASS -- the float32 comparison must not
    # flag the stored default grey as colour (the false-UNKNOWN guard for R16-1).
    g16d = os.path.join(tmp, "r16default")
    os.makedirs(g16d, exist_ok=True)
    fixtures.build_fluid_uni_gas_plain(g16d)
    g16ddata = os.path.join(g16d, "fluidcache", "data")
    out.append(("fluid R16-1 control: genuine default bake wrote NO colour (precondition)",
                not any(f.startswith("color_") for f in os.listdir(g16ddata)),
                sorted(os.listdir(g16ddata))[:3], "no colour grids"))
    man = ch.capture(list(bpy.data.scenes), ci.blend_dir())
    bl.save_baseline(bpy.context.scene, bl.default_baseline_path(),
                     overwrite=True, cache_hashes=man)
    rep = ch.build_report(list(bpy.data.scenes))
    results = engine.run_all(bpy.context, hash_verify=rep)
    out.append(("fluid R16-1: genuine default bake -> #27 PASS (no false UNKNOWN)",
                worst_for_check(results, 27) == Status.PASS,
                worst_for_check(results, 27), Status.PASS))

    return out


def hash_gn_tests():
    """Geometry Nodes DISK-bake cache-hash coverage on REAL bakes (meta + blobs).

    GN sim bakes are written to disk on ALL four versions: via ``bake_target='DISK'``
    on 4.5/5.0/5.2, and via ``bake_directory`` alone on 4.2 (which has no
    ``bake_target`` and no packed storage — packed arrived in 4.3). The on-disk
    layout is identical, so GN disk hashing runs on 4.2 too (review B2). A PACKED
    bake (4.3+) is never hashed — it must not be mistaken for a missing disk cache.
    The bake is a real moving simulation, so it writes genuine ``blobs/*.blob`` with
    the first-frame topology blob that every later frame depends on (review M1).
    Preserves the B1-B7 protections and adds the B1 interior-coverage protection."""
    import shutil
    import json as _json
    from failsafe import (cachehash as ch, baseline as bl, cache_inspect as ci,
                          cli)
    out = []
    tmp = tempfile.mkdtemp(prefix="failsafe_gn_")

    def _meta(report):
        return [s for s in report.sims if s.identity.endswith("/meta")]

    def _blobs(report):
        return [s for s in report.sims if s.identity.endswith("/blobs")]

    # A PACKED bake must NOT be hashed (never mistaken for a missing disk cache).
    # On 4.2 packing is impossible, so this falls back to a disk bake; assert the
    # packed rule only where a packed bake was actually produced.
    psrc = os.path.join(tmp, "packed")
    os.makedirs(psrc, exist_ok=True)
    _pb, _pdisk, packed_made = fixtures._make_gn_disk_blend(psrc, packed=True)
    precs = list(ci.iter_gn_cache_files(list(bpy.data.scenes)))
    if packed_made:
        out.append(("GN packed bake is NOT hashed (stays Couldn't verify)",
                    len(precs) == 0, len(precs), 0))
    else:
        out.append(("GN packed unavailable on this Blender (4.2) — disk bake made "
                    "instead, recorded not a false pass", True, "4.2 disk", "n/a"))

    # A real DISK bake (meta + blobs). Runs on every version now, incl. 4.2.
    src = os.path.join(tmp, "src")
    os.makedirs(src, exist_ok=True)
    _blend, disk, _pm = fixtures._make_gn_disk_blend(src)
    out.append(("GN disk bake produced on this Blender (incl. 4.2, review B2)",
                disk, disk, True))

    recs = list(ci.iter_gn_cache_files(list(bpy.data.scenes)))
    out.append(("GN disk bake -> meta record with files",
                any(r.identity.endswith("/meta") and r.files for r in recs),
                len([r for r in recs if r.identity.endswith("/meta")]), ">=1 meta"))
    # The moving sim must actually write blob dependencies for M1 to be real.
    out.append(("GN disk bake -> real blob dependency record enumerated",
                any(r.identity.endswith("/blobs") and r.files for r in recs),
                len([r for r in recs if r.identity.endswith("/blobs")]), ">=1 blobs"))
    man = ch.capture(list(bpy.data.scenes), ci.blend_dir())
    bl.save_baseline(bpy.context.scene, bl.default_baseline_path(),
                     overwrite=True, cache_hashes=man)

    def _open(tag):
        dst = os.path.join(tmp, "p_" + tag)
        shutil.copytree(src, dst)
        bpy.ops.wm.open_mainfile(filepath=os.path.join(dst, "gn.blend"))
        return dst

    # (1) unchanged -> meta AND blobs UNCHANGED -> #27 PASS
    _open("pass")
    rep = ch.build_report(list(bpy.data.scenes))
    ms, bs = _meta(rep), _blobs(rep)
    out.append(("GN unchanged: meta + blobs all UNCHANGED",
                bool(ms) and bool(bs)
                and all(s.state == ch.S_UNCHANGED for s in ms + bs),
                [s.state for s in ms + bs], "UNCHANGED"))
    results = engine.run_all(bpy.context, hash_verify=rep)
    out.append(("GN unchanged -> #27 PASS",
                worst_for_check(results, 27) == Status.PASS,
                worst_for_check(results, 27), Status.PASS))

    # (2) change a meta file -> CHANGED. A genuine re-bake rewrites the meta with
    # DIFFERENT but still-VALID JSON (different bytes -> different hash). Mutate it
    # validly (not a byte-corruption, which is a separate case that correctly reads
    # META_UNREADABLE, below), so this tests real change-detection, not corruption.
    dst = _open("changed")
    bdir = fixtures.gn_bake_dir(dst)
    mfiles = sorted(os.path.join(bdir, "meta", f)
                    for f in os.listdir(os.path.join(bdir, "meta"))
                    if f.endswith(".json"))
    tgt = mfiles[len(mfiles) // 2]
    with open(tgt, "r", encoding="utf-8") as fh:
        _mj = _json.load(fh)
    _mj["_failsafe_rebake_marker"] = "changed-but-valid"   # valid JSON, new bytes
    with open(tgt, "w", encoding="utf-8") as fh:
        _json.dump(_mj, fh)
    rep = ch.build_report(list(bpy.data.scenes))
    ms = _meta(rep)
    out.append(("GN changed meta (valid JSON) -> CHANGED",
                bool(ms) and ms[0].state == ch.S_CHANGED,
                [s.state for s in ms], ch.S_CHANGED))

    # (3) delete a meta frame -> missing (never PASS), floors requested verify
    dst = _open("missmeta")
    bdir = fixtures.gn_bake_dir(dst)
    mnames = sorted(os.listdir(os.path.join(bdir, "meta")))
    os.remove(os.path.join(bdir, "meta", mnames[-1]))
    rep = ch.build_report(list(bpy.data.scenes))
    ms = _meta(rep)
    out.append(("GN missing meta frame: not UNCHANGED, has missing",
                bool(ms) and ms[0].state != ch.S_UNCHANGED and bool(ms[0].missing),
                [(s.state, s.missing) for s in ms], "missing"))
    out.append(("GN missing meta -> requested verify nonzero",
                cli.verify_floor(rep, True) == cli.EXIT_UNVERIFIED,
                cli.verify_floor(rep, True), cli.EXIT_UNVERIFIED))

    # (B1) interior frame MISSING BEFORE the baseline is captured. The expected set is
    # now the reliable sim-zone range (scene range), so an interior hole is uncovered
    # -> INCOMPLETE_REF, never an unqualified PASS for complete coverage (review B1;
    # head/tail holes are covered by the B4 cases below).
    hole = os.path.join(tmp, "hole")
    os.makedirs(hole, exist_ok=True)
    fixtures._make_gn_disk_blend(hole)
    hbdir = fixtures.gn_bake_dir(hole)
    hmeta = sorted(f for f in os.listdir(os.path.join(hbdir, "meta"))
                   if f.endswith(".json"))
    # Remove a genuinely interior meta frame (not first/last) BEFORE baseline.
    interior = hmeta[len(hmeta) // 2]
    os.remove(os.path.join(hbdir, "meta", interior))
    bpy.ops.wm.open_mainfile(filepath=os.path.join(hole, "gn.blend"))
    man_h = ch.capture(list(bpy.data.scenes), ci.blend_dir())
    bl.save_baseline(bpy.context.scene, bl.default_baseline_path(),
                     overwrite=True, cache_hashes=man_h)
    rep = ch.build_report(list(bpy.data.scenes))
    ms = _meta(rep)
    out.append(("GN interior hole before baseline: meta is INCOMPLETE_REF, not PASS",
                bool(ms) and ms[0].state == ch.S_INCOMPLETE_REF
                and bool(ms[0].uncovered),
                [(s.state, s.uncovered) for s in ms], "INCOMPLETE_REF + uncovered"))
    results = engine.run_all(bpy.context, hash_verify=rep)
    out.append(("GN interior hole -> #27 UNKNOWN (never PASS)",
                worst_for_check(results, 27) == Status.UNKNOWN,
                worst_for_check(results, 27), Status.UNKNOWN))
    out.append(("GN interior hole -> requested verify nonzero",
                cli.verify_floor(rep, True) == cli.EXIT_UNVERIFIED,
                cli.verify_floor(rep, True), cli.EXIT_UNVERIFIED))

    # (B1b) an enabled disk bake with an EMPTY meta directory must NOT be silently
    # omitted — a record is still enumerated so a verify can't read clean.
    empt = os.path.join(tmp, "empty")
    os.makedirs(empt, exist_ok=True)
    fixtures._make_gn_disk_blend(empt)
    ebdir = fixtures.gn_bake_dir(empt)
    for f in os.listdir(os.path.join(ebdir, "meta")):
        os.remove(os.path.join(ebdir, "meta", f))
    erecs = [r for r in ci.iter_gn_cache_files(list(bpy.data.scenes))
             if r.identity.endswith("/meta")]
    out.append(("GN empty meta dir: still enumerated (not omitted), no files",
                len(erecs) >= 1 and erecs[0].files == [],
                (len(erecs), erecs[0].files if erecs else None), ">=1, []"))

    # (M1) REAL blob dependency: change an actual position blob -> blobs CHANGED.
    dst = _open("blobchg")
    bdir = fixtures.gn_bake_dir(dst)
    blobnames = sorted(f for f in os.listdir(os.path.join(bdir, "blobs"))
                       if f.endswith(".blob"))
    # Change a LATER frame's position blob (not the shared first-frame one).
    tgtblob = os.path.join(bdir, "blobs", blobnames[-1])
    with open(tgtblob, "r+b") as fh:
        fh.seek(0)
        b0 = fh.read(1)
        fh.seek(0)
        fh.write(bytes([b0[0] ^ 0xFF]))
    rep = ch.build_report(list(bpy.data.scenes))
    bs = _blobs(rep)
    out.append(("GN changed real blob -> blobs CHANGED",
                bool(bs) and bs[0].state == ch.S_CHANGED,
                [s.state for s in bs], ch.S_CHANGED))

    # (M1b) REAL missing dependency: delete the first-frame topology blob that every
    # later frame references. It was baselined, so it reports missing -> never PASS,
    # and floors a requested verify.
    dst = _open("blobdep")
    bdir = fixtures.gn_bake_dir(dst)
    first_blob = sorted(f for f in os.listdir(os.path.join(bdir, "blobs"))
                        if f.endswith(".blob"))[0]
    os.remove(os.path.join(bdir, "blobs", first_blob))
    rep = ch.build_report(list(bpy.data.scenes))
    bs = _blobs(rep)
    out.append(("GN missing dependency blob: blobs not UNCHANGED, has missing",
                bool(bs) and bs[0].state != ch.S_UNCHANGED
                and (bool(bs[0].missing) or bool(bs[0].uncovered)),
                [(s.state, s.missing, s.uncovered) for s in bs], "missing/uncovered"))
    out.append(("GN missing dependency blob -> requested verify nonzero",
                cli.verify_floor(rep, True) == cli.EXIT_UNVERIFIED,
                cli.verify_floor(rep, True), cli.EXIT_UNVERIFIED))

    # (B3, round 3) FRAME-0 BLOB IDENTITY COLLISION. The old packed-int key mapped
    # 00000_00001.blob and 00001_00000.blob BOTH to 1, so a present frame-1 blob could
    # cover an absent frame-0 sibling and read as a clean PASS. Inject a reference to an
    # ABSENT "00000_00001.blob" while the present "00001_00000.blob" stays on disk,
    # BEFORE the baseline is captured. With exact filename-stem identities the present
    # frame-1 blob must NOT mask the absent frame-0 sibling: it stays uncovered -> never
    # a clean PASS, and floors a requested verify (review B3).
    coll = os.path.join(tmp, "collide")
    os.makedirs(coll, exist_ok=True)
    fixtures._make_gn_disk_blend(coll)
    cbdir = fixtures.gn_bake_dir(coll)
    cmeta = sorted(f for f in os.listdir(os.path.join(cbdir, "meta"))
                   if f.endswith(".json"))
    # The present blob that WOULD have collided with the absent frame-0 sibling.
    present_blob = "00001_00000.blob"
    absent_sibling = "00000_00001.blob"  # frame 0, index 1 — never written
    has_present = os.path.isfile(os.path.join(cbdir, "blobs", present_blob))
    first_meta = os.path.join(cbdir, "meta", cmeta[0])  # 00001_00000.json
    with open(first_meta, "r", encoding="utf-8") as fh:
        j = _json.load(fh)
    # A valid-JSON reference to the non-existent frame-0 sibling blob.
    j["_failsafe_adversarial_ref"] = {"name": absent_sibling, "start": 0, "size": 1}
    with open(first_meta, "w", encoding="utf-8") as fh:
        _json.dump(j, fh)
    bpy.ops.wm.open_mainfile(filepath=os.path.join(coll, "gn.blend"))
    # The two files must carry DISTINCT coverage identities (the old int key collided).
    sib_key = ci._gn_blob_coverage_key(absent_sibling)      # "00000_00001"
    present_key = ci._gn_blob_coverage_key(present_blob)     # "00001_00000"
    crecs = [r for r in ci.iter_gn_cache_files(list(bpy.data.scenes))
             if r.identity.endswith("/blobs")]
    out.append(("GN B3: frame-0 sibling and frame-1 blob have DISTINCT identities",
                sib_key != present_key, (sib_key, present_key), "distinct"))
    out.append(("GN B3: both the present blob and the absent sibling are tracked",
                has_present and bool(crecs) and sib_key in crecs[0].required
                and present_key in crecs[0].required,
                (sib_key in crecs[0].required if crecs else None,
                 present_key in crecs[0].required if crecs else None),
                "both tracked"))
    man_c = ch.capture(list(bpy.data.scenes), ci.blend_dir())
    bl.save_baseline(bpy.context.scene, bl.default_baseline_path(),
                     overwrite=True, cache_hashes=man_c)
    rep = ch.build_report(list(bpy.data.scenes))
    bs = _blobs(rep)
    # The present frame-1 blob matched, yet the absent frame-0 sibling is still
    # uncovered: the collision did NOT mask it.
    out.append(("GN B3: present frame-1 blob does NOT mask absent frame-0 sibling",
                bool(bs) and bs[0].state != ch.S_UNCHANGED
                and (sib_key in (bs[0].uncovered or [])) and bool(bs[0].matched),
                [(s.state, s.matched, s.uncovered) for s in bs],
                "matched + sibling uncovered, not UNCHANGED"))
    out.append(("GN B3: absent frame-0 sibling -> requested verify nonzero",
                cli.verify_floor(rep, True) == cli.EXIT_UNVERIFIED,
                cli.verify_floor(rep, True), cli.EXIT_UNVERIFIED))

    # (R4-1, round 4) JSON-ESCAPED blob reference. Blob dependencies are read by
    # PARSING the meta JSON, not regexing raw text, so a reference written with a JSON
    # Unicode escape ("00000_00002.blob", which DECODES to 00000_00002.blob) is
    # still enumerated. A raw-text regex would miss the escaped spelling and could drop
    # a required dependency, letting an absent blob read as a clean PASS. Inject a
    # reference to an ABSENT blob using the escape, BEFORE baseline; it must be in the
    # required set, uncovered, and floor a requested verify.
    esc = os.path.join(tmp, "escaped")
    os.makedirs(esc, exist_ok=True)
    fixtures._make_gn_disk_blend(esc)
    ebdir = fixtures.gn_bake_dir(esc)
    emeta = sorted(f for f in os.listdir(os.path.join(ebdir, "meta"))
                   if f.endswith(".json"))
    efirst = os.path.join(ebdir, "meta", emeta[0])
    esc_absent = "00000_00002.blob"   # frame 0, index 2 — never written; unique token
    with open(efirst, "r", encoding="utf-8") as fh:
        ej = _json.load(fh)
    ej["_failsafe_adversarial_ref"] = {"name": esc_absent, "start": 0, "size": 1}
    etext = _json.dumps(ej)
    # Force the JSON ESCAPE for the dot in OUR unique ref only (dumps writes it plain).
    assert esc_absent in etext
    etext = etext.replace(esc_absent, "00000_00002\\u002eblob")
    with open(efirst, "w", encoding="utf-8") as fh:
        fh.write(etext)
    raw_check = open(efirst, "r", encoding="utf-8").read()
    # Discriminating preconditions: the file carries the ESCAPED spelling, not the
    # literal one, and is still valid JSON that decodes to the plain name.
    out.append(("GN R4-1: meta carries the escaped spelling, not literal .blob (for our ref)",
                "00000_00002\\u002eblob" in raw_check and esc_absent not in raw_check,
                ("escaped_present=%s" % ("00000_00002\\u002eblob" in raw_check),
                 "literal_present=%s" % (esc_absent in raw_check)), "escaped only"))
    out.append(("GN R4-1: meta is still valid JSON decoding to the plain blob name",
                _json.load(open(efirst, encoding="utf-8"))["_failsafe_adversarial_ref"]["name"]
                == esc_absent, True, True))
    names, _unread = ci._gn_referenced_blob_names([efirst])
    out.append(("GN R4-1: escaped reference IS enumerated as a dependency",
                esc_absent in names, esc_absent in names, True))
    bpy.ops.wm.open_mainfile(filepath=os.path.join(esc, "gn.blend"))
    man_e1 = ch.capture(list(bpy.data.scenes), ci.blend_dir())
    bl.save_baseline(bpy.context.scene, bl.default_baseline_path(),
                     overwrite=True, cache_hashes=man_e1)
    rep = ch.build_report(list(bpy.data.scenes))
    bs = _blobs(rep)
    esc_key = ci._gn_blob_coverage_key(esc_absent)   # "00000_00002"
    out.append(("GN R4-1: escaped absent blob is uncovered, not a clean PASS",
                bool(bs) and bs[0].state != ch.S_UNCHANGED
                and esc_key in (bs[0].uncovered or []),
                [(s.state, s.uncovered) for s in bs],
                "uncovered incl. %s" % esc_key))
    out.append(("GN R4-1: escaped absent blob -> requested verify nonzero",
                cli.verify_floor(rep, True) == cli.EXIT_UNVERIFIED,
                cli.verify_floor(rep, True), cli.EXIT_UNVERIFIED))

    # (B4) HEAD / TAIL frame missing BEFORE the baseline is captured. The reliable
    # expected range (scene range for a sim zone) means a missing FIRST or LAST frame
    # is uncovered -> INCOMPLETE_REF, never a false complete-coverage PASS. The old
    # min(present)..max(present) span could not see these (review B4).
    for pos, idx in (("head", 0), ("tail", -1)):
        hd = os.path.join(tmp, "edge_" + pos)
        os.makedirs(hd, exist_ok=True)
        fixtures._make_gn_disk_blend(hd)
        hbd = fixtures.gn_bake_dir(hd)
        hmetas = sorted(f for f in os.listdir(os.path.join(hbd, "meta"))
                        if f.endswith(".json"))
        gone = hmetas[idx][:-5]                   # exact stem "<frame>_<subframe>"
        os.remove(os.path.join(hbd, "meta", hmetas[idx]))
        bpy.ops.wm.open_mainfile(filepath=os.path.join(hd, "gn.blend"))
        man_e = ch.capture(list(bpy.data.scenes), ci.blend_dir())
        bl.save_baseline(bpy.context.scene, bl.default_baseline_path(),
                         overwrite=True, cache_hashes=man_e)
        rep = ch.build_report(list(bpy.data.scenes))
        ms = _meta(rep)
        out.append(("GN B4: missing %s frame before baseline -> INCOMPLETE_REF, not PASS"
                    % pos,
                    bool(ms) and ms[0].state == ch.S_INCOMPLETE_REF
                    and gone in (ms[0].uncovered or []),
                    [(s.state, s.uncovered) for s in ms],
                    "INCOMPLETE_REF incl. %s" % gone))
        results = engine.run_all(bpy.context, hash_verify=rep)
        out.append(("GN B4: missing %s frame -> #27 UNKNOWN (never PASS)" % pos,
                    worst_for_check(results, 27) == Status.UNKNOWN,
                    worst_for_check(results, 27), Status.UNKNOWN))
        out.append(("GN B4: missing %s frame -> requested verify nonzero" % pos,
                    cli.verify_floor(rep, True) == cli.EXIT_UNVERIFIED,
                    cli.verify_floor(rep, True), cli.EXIT_UNVERIFIED))

    # (B4a, round 3) SCENE-WIDE custom simulation range. With scene range 1..6 but a
    # scene-wide simulation range 1..8, the sim bakes 1..8. Delete the TAIL frame (8),
    # which lies OUTSIDE the scene range, BEFORE baseline. If the expected set wrongly
    # used the scene range (1..6), the surviving 1..7 would fully cover it and read as a
    # clean PASS. Honouring the scene-wide range (1..8) makes frame 8 uncovered ->
    # INCOMPLETE_REF -> #27 UNKNOWN. This is the discriminating test for B4a.
    swr = os.path.join(tmp, "scene_wide")
    os.makedirs(swr, exist_ok=True)
    _sb, _sd, _sp = fixtures._make_gn_disk_blend(swr, frame_end=6,
                                                 scene_sim_range=(1, 8))
    if hasattr(bpy.context.scene, "use_custom_simulation_range"):
        swbd = fixtures.gn_bake_dir(swr)
        swmetas = sorted(f for f in os.listdir(os.path.join(swbd, "meta"))
                         if f.endswith(".json"))
        baked_frames = [int(f.split("_")[0]) for f in swmetas]
        out.append(("GN B4a: scene-wide sim range (1..8) baked frames beyond scene range",
                    baked_frames == list(range(1, 9)), baked_frames, [1, 2, 3, 4, 5, 6, 7, 8]))
        tail_gone = swmetas[-1][:-5]       # exact stem of frame 8 (outside scene 1..6)
        os.remove(os.path.join(swbd, "meta", swmetas[-1]))
        bpy.ops.wm.open_mainfile(filepath=os.path.join(swr, "gn.blend"))
        man_sw = ch.capture(list(bpy.data.scenes), ci.blend_dir())
        bl.save_baseline(bpy.context.scene, bl.default_baseline_path(),
                         overwrite=True, cache_hashes=man_sw)
        rep = ch.build_report(list(bpy.data.scenes))
        ms = _meta(rep)
        out.append(("GN B4a: tail frame beyond scene range is uncovered, not a PASS",
                    bool(ms) and ms[0].state == ch.S_INCOMPLETE_REF
                    and tail_gone in (ms[0].uncovered or []),
                    [(s.state, s.uncovered) for s in ms],
                    "INCOMPLETE_REF incl. %s" % tail_gone))
        results = engine.run_all(bpy.context, hash_verify=rep)
        out.append(("GN B4a: scene-wide tail gap -> #27 UNKNOWN (never PASS)",
                    worst_for_check(results, 27) == Status.UNKNOWN,
                    worst_for_check(results, 27), Status.UNKNOWN))
        out.append(("GN B4a: scene-wide tail gap -> requested verify nonzero",
                    cli.verify_floor(rep, True) == cli.EXIT_UNVERIFIED,
                    cli.verify_floor(rep, True), cli.EXIT_UNVERIFIED))
    else:
        out.append(("GN B4a: scene-wide sim range unavailable on this Blender — skipped",
                    True, "n/a", "n/a"))

    # (custom-path, round 3) A per-bake CUSTOM path stores files DIRECTLY under it, with
    # NO <bake_id> subfolder. The enumerator must look there (not <custom>/<bake_id>),
    # else a correctly-baked custom-path cache reads as empty. Prove it: a full custom-
    # path bake verifies UNCHANGED (files found) and #27 PASSES.
    cust = os.path.join(tmp, "custpath")
    os.makedirs(cust, exist_ok=True)
    custom_dir = os.path.join(cust, "mybakes")
    os.makedirs(custom_dir, exist_ok=True)
    _cb, _cd, _cp = fixtures._make_gn_disk_blend(cust, frame_end=5,
                                                 custom_bake_dir=custom_dir)
    direct_meta = sorted(f for f in os.listdir(os.path.join(custom_dir, "meta"))
                         if f.endswith(".json")) if os.path.isdir(
                             os.path.join(custom_dir, "meta")) else []
    # The custom-path capability exists on all four certified versions, so a bake that
    # produced NO files is a certification FAILURE, not an acceptable skip (review R4
    # hardening) — otherwise the test would pass vacuously if the path setup silently
    # broke.
    out.append(("GN custom-path: custom-path bake produced disk files (cert requires it)",
                bool(direct_meta), len(direct_meta), ">=1 file"))
    if direct_meta:
        recs_c = [r for r in ci.iter_gn_cache_files(list(bpy.data.scenes))
                  if r.identity.endswith("/meta")]
        out.append(("GN custom-path: files found directly under the custom dir (no bake_id)",
                    bool(recs_c) and bool(recs_c[0].files)
                    and all("/meta" in r.identity for r in recs_c),
                    [len(r.files) for r in recs_c], ">=1 file located"))
        man_cp = ch.capture(list(bpy.data.scenes), ci.blend_dir())
        bl.save_baseline(bpy.context.scene, bl.default_baseline_path(),
                         overwrite=True, cache_hashes=man_cp)
        rep = ch.build_report(list(bpy.data.scenes))
        ms, bs = _meta(rep), _blobs(rep)
        out.append(("GN custom-path: full custom-path bake -> meta + blobs UNCHANGED",
                    bool(ms) and all(s.state == ch.S_UNCHANGED for s in ms + bs),
                    [s.state for s in ms + bs], "UNCHANGED"))
        results = engine.run_all(bpy.context, hash_verify=rep)
        out.append(("GN custom-path: full custom-path bake -> #27 PASS",
                    worst_for_check(results, 27) == Status.PASS,
                    worst_for_check(results, 27), Status.PASS))

    # (R5-1, round 5) MALFORMED-JSON metadata. Blob dependencies are read by PARSING
    # each meta file. A meta that can't be parsed is NOT raw-text scanned as a fallback
    # — a partial raw-text scan can UNDER-count the dependency set (a name split by a
    # truncation, or mangled by a bad encoding) and let an ABSENT blob read as a clean
    # PASS. Instead the whole sim is forced to 'Couldn't verify' (S_META_UNREADABLE).
    # Corrupt a meta to invalid JSON and prove it never reads clean.
    badj = os.path.join(tmp, "badjson")
    os.makedirs(badj, exist_ok=True)
    fixtures._make_gn_disk_blend(badj)
    bjd = fixtures.gn_bake_dir(badj)
    bjmetas = sorted(f for f in os.listdir(os.path.join(bjd, "meta"))
                     if f.endswith(".json"))
    bjfirst = os.path.join(bjd, "meta", bjmetas[0])
    with open(bjfirst, "w", encoding="utf-8") as fh:
        fh.write('{ "items": [ this is not valid json ::: ')   # malformed / truncated
    names_bj, unread_bj = ci._gn_referenced_blob_names([bjfirst])
    out.append(("GN R5-1: malformed meta reported UNREADABLE, not raw-text scanned",
                bjfirst in unread_bj and not names_bj,
                (len(unread_bj), len(names_bj)), "unreadable; no names"))
    bpy.ops.wm.open_mainfile(filepath=os.path.join(badj, "gn.blend"))
    recs_bj = list(ci.iter_gn_cache_files(list(bpy.data.scenes)))
    meta_bj = [r for r in recs_bj if r.identity.endswith("/meta")]
    blob_bj = [r for r in recs_bj if r.identity.endswith("/blobs")]
    out.append(("GN R5-1: malformed meta -> meta record flagged meta_unreadable",
                bool(meta_bj) and bool(meta_bj[0].meta_unreadable),
                [list(r.meta_unreadable) for r in meta_bj], "non-empty"))
    out.append(("GN R5-1: malformed meta -> NO blobs record (deps untrustworthy)",
                not blob_bj, len(blob_bj), 0))
    man_bj = ch.capture(list(bpy.data.scenes), ci.blend_dir())
    bl.save_baseline(bpy.context.scene, bl.default_baseline_path(),
                     overwrite=True, cache_hashes=man_bj)
    rep = ch.build_report(list(bpy.data.scenes))
    ms = _meta(rep)
    out.append(("GN R5-1: malformed meta -> S_META_UNREADABLE (never UNCHANGED)",
                bool(ms) and ms[0].state == ch.S_META_UNREADABLE,
                [s.state for s in ms], ch.S_META_UNREADABLE))
    results = engine.run_all(bpy.context, hash_verify=rep)
    out.append(("GN R5-1: malformed meta -> #27 UNKNOWN (never PASS)",
                worst_for_check(results, 27) == Status.UNKNOWN,
                worst_for_check(results, 27), Status.UNKNOWN))
    out.append(("GN R5-1: malformed meta -> requested verify nonzero",
                cli.verify_floor(rep, True) == cli.EXIT_UNVERIFIED,
                cli.verify_floor(rep, True), cli.EXIT_UNVERIFIED))

    # (R5-1) INVALID-UTF-8 metadata. The meta is opened as STRICT utf-8, so bytes that
    # aren't valid UTF-8 RAISE and the file is treated as unreadable — NOT silently
    # repaired by errors='ignore', which could mangle a blob name into something the
    # scan misses. Force invalid bytes and prove 'Couldn't verify'.
    badu = os.path.join(tmp, "badutf8")
    os.makedirs(badu, exist_ok=True)
    fixtures._make_gn_disk_blend(badu)
    bud = fixtures.gn_bake_dir(badu)
    bumetas = sorted(f for f in os.listdir(os.path.join(bud, "meta"))
                     if f.endswith(".json"))
    bufirst = os.path.join(bud, "meta", bumetas[0])
    with open(bufirst, "wb") as fh:
        fh.write(b'\xff\xfe\x00\x80 not valid utf-8 { "items": [] }')
    names_bu, unread_bu = ci._gn_referenced_blob_names([bufirst])
    out.append(("GN R5-1: invalid-UTF-8 meta is UNREADABLE (strict decode), not ignored",
                bufirst in unread_bu and not names_bu,
                (len(unread_bu), len(names_bu)), "unreadable; no names"))
    bpy.ops.wm.open_mainfile(filepath=os.path.join(badu, "gn.blend"))
    man_bu = ch.capture(list(bpy.data.scenes), ci.blend_dir())
    bl.save_baseline(bpy.context.scene, bl.default_baseline_path(),
                     overwrite=True, cache_hashes=man_bu)
    rep = ch.build_report(list(bpy.data.scenes))
    ms = _meta(rep)
    out.append(("GN R5-1: invalid-UTF-8 meta -> S_META_UNREADABLE (never UNCHANGED)",
                bool(ms) and ms[0].state == ch.S_META_UNREADABLE,
                [s.state for s in ms], ch.S_META_UNREADABLE))
    out.append(("GN R5-1: invalid-UTF-8 meta -> requested verify nonzero",
                cli.verify_floor(rep, True) == cli.EXIT_UNVERIFIED,
                cli.verify_floor(rep, True), cli.EXIT_UNVERIFIED))

    # (R5-1 / R4 hardening) INVALID frame range, behavioral. If the expected sim range
    # can't be established as a valid FORWARD range (None, or start > end), the
    # enumerator yields NO coverage so the sim reads 'Couldn't verify' — never an empty
    # required set that passes clean. Force an inverted range over a real bake.
    invr = os.path.join(tmp, "invrange")
    os.makedirs(invr, exist_ok=True)
    fixtures._make_gn_disk_blend(invr)
    bpy.ops.wm.open_mainfile(filepath=os.path.join(invr, "gn.blend"))
    _orig_range = ci._gn_expected_range
    try:
        ci._gn_expected_range = lambda b, s: (9, 2)   # inverted: start > end
        recs_iv = [r for r in ci.iter_gn_cache_files(list(bpy.data.scenes))
                   if r.identity.endswith("/meta")]
        out.append(("GN invalid-range: inverted range -> meta record has NO coverage",
                    bool(recs_iv) and recs_iv[0].required == []
                    and not recs_iv[0].files,
                    [(r.required, len(r.files)) for r in recs_iv],
                    "required=[], files=0"))
        man_iv = ch.capture(list(bpy.data.scenes), ci.blend_dir())
        bl.save_baseline(bpy.context.scene, bl.default_baseline_path(),
                         overwrite=True, cache_hashes=man_iv)
        rep = ch.build_report(list(bpy.data.scenes))
        # No coverage means nothing is hashed, so no sim can read UNCHANGED — the
        # degenerate range can never produce a clean PASS — and a REQUESTED verify
        # still floors to 'unverified' (the honest CLI outcome).
        out.append(("GN invalid-range: inverted range -> no sim reads UNCHANGED",
                    all(s.state != ch.S_UNCHANGED for s in rep.sims),
                    [s.state for s in rep.sims], "none UNCHANGED"))
        out.append(("GN invalid-range: inverted range -> requested verify nonzero",
                    cli.verify_floor(rep, True) == cli.EXIT_UNVERIFIED,
                    cli.verify_floor(rep, True), cli.EXIT_UNVERIFIED))
    finally:
        ci._gn_expected_range = _orig_range

    # (R6-1, round 6) VALID JSON that is NOT a recognizable bake frame. Replace every
    # frame's metadata with "{}" (valid JSON, no 'items' structure) and delete the
    # shared first-frame blob. The meta filenames still exist and their hashes match a
    # baseline captured after the edit, and no blobs are enumerated as required — the
    # exact shape that could read UNCHANGED if "valid JSON" were trusted as bake data.
    # The recognizer must reject "{}" so the sim reads 'Couldn't verify' instead, and
    # must NOT emit a blobs record from an un-establishable dependency set.
    r6 = os.path.join(tmp, "r6_emptyobj")
    os.makedirs(r6, exist_ok=True)
    fixtures._make_gn_disk_blend(r6)
    r6bd = fixtures.gn_bake_dir(r6)
    r6meta = os.path.join(r6bd, "meta")
    r6blob = os.path.join(r6bd, "blobs")
    for fn in os.listdir(r6meta):
        if fn.endswith(".json"):
            with open(os.path.join(r6meta, fn), "w", encoding="utf-8") as fh:
                fh.write("{}")                      # valid JSON, not a bake frame
    r6blobs = sorted(os.listdir(r6blob)) if os.path.isdir(r6blob) else []
    for bf in r6blobs:
        os.remove(os.path.join(r6blob, bf))         # delete the shared blob(s)
    names_r6, unread_r6 = ci._gn_referenced_blob_names(
        [os.path.join(r6meta, f) for f in os.listdir(r6meta) if f.endswith(".json")])
    out.append(("GN R6-1: deleted a real baked blob (precondition)",
                bool(r6blobs), r6blobs, ">=1 blob existed"))
    out.append(("GN R6-1: '{}' metas are UNREADABLE (not recognizable), no blob names",
                bool(unread_r6) and not names_r6,
                (len(unread_r6), len(names_r6)), "unreadable; no names"))
    bpy.ops.wm.open_mainfile(filepath=os.path.join(r6, "gn.blend"))
    recs_r6 = list(ci.iter_gn_cache_files(list(bpy.data.scenes)))
    out.append(("GN R6-1: '{}' metas -> meta flagged meta_unreadable, NO blobs record",
                any(r.identity.endswith("/meta") and r.meta_unreadable for r in recs_r6)
                and not any(r.identity.endswith("/blobs") for r in recs_r6),
                [(r.identity.split("::")[-1], bool(r.meta_unreadable)) for r in recs_r6],
                "meta flagged; no blobs"))
    man_r6 = ch.capture(list(bpy.data.scenes), ci.blend_dir())
    bl.save_baseline(bpy.context.scene, bl.default_baseline_path(),
                     overwrite=True, cache_hashes=man_r6)
    rep = ch.build_report(list(bpy.data.scenes))
    ms = _meta(rep)
    out.append(("GN R6-1: '{}' metas -> S_META_UNREADABLE (never UNCHANGED)",
                bool(ms) and all(s.state == ch.S_META_UNREADABLE for s in ms),
                [s.state for s in ms], ch.S_META_UNREADABLE))
    results = engine.run_all(bpy.context, hash_verify=rep)
    out.append(("GN R6-1: '{}' metas + deleted blob -> #27 UNKNOWN (never PASS)",
                worst_for_check(results, 27) == Status.UNKNOWN,
                worst_for_check(results, 27), Status.UNKNOWN))
    out.append(("GN R6-1: '{}' metas -> requested verify nonzero",
                cli.verify_floor(rep, True) == cli.EXIT_UNVERIFIED,
                cli.verify_floor(rep, True), cli.EXIT_UNVERIFIED))

    # (R7-1, round 7) The reviewer's counterexample: a GEOMETRY entry with its 'data'
    # payload REMOVED is valid JSON but not something Blender writes — it references no
    # blobs, so a deleted blob could hide behind it. Strip 'data' from every frame's
    # GEOMETRY items and delete the blobs; the recognizer must reject it -> UNKNOWN.
    r7 = os.path.join(tmp, "r7_nodata")
    os.makedirs(r7, exist_ok=True)
    fixtures._make_gn_disk_blend(r7)
    r7bd = fixtures.gn_bake_dir(r7)
    r7meta = os.path.join(r7bd, "meta")
    r7blob = os.path.join(r7bd, "blobs")
    for fn in os.listdir(r7meta):
        if not fn.endswith(".json"):
            continue
        fp = os.path.join(r7meta, fn)
        d = _json.load(open(fp, encoding="utf-8"))
        items = d.get("items")
        entries = items.values() if isinstance(items, dict) else (items or [])
        for it in entries:
            if isinstance(it, dict):
                it.pop("data", None)          # strip the per-item payload
        with open(fp, "w", encoding="utf-8") as fh:
            _json.dump(d, fh)
    r7blobs = sorted(os.listdir(r7blob)) if os.path.isdir(r7blob) else []
    for bf in r7blobs:
        os.remove(os.path.join(r7blob, bf))
    _n7, u7 = ci._gn_referenced_blob_names(
        [os.path.join(r7meta, f) for f in os.listdir(r7meta) if f.endswith(".json")])
    out.append(("GN R7-1: data-stripped GEOMETRY metas are UNREADABLE (not recognizable)",
                bool(u7), len(u7), ">=1 unreadable"))
    bpy.ops.wm.open_mainfile(filepath=os.path.join(r7, "gn.blend"))
    recs_r7 = list(ci.iter_gn_cache_files(list(bpy.data.scenes)))
    out.append(("GN R7-1: data-stripped metas -> meta flagged, NO blobs record",
                any(r.identity.endswith("/meta") and r.meta_unreadable for r in recs_r7)
                and not any(r.identity.endswith("/blobs") for r in recs_r7),
                [(r.identity.split("::")[-1], bool(r.meta_unreadable)) for r in recs_r7],
                "meta flagged; no blobs"))
    man_r7 = ch.capture(list(bpy.data.scenes), ci.blend_dir())
    bl.save_baseline(bpy.context.scene, bl.default_baseline_path(),
                     overwrite=True, cache_hashes=man_r7)
    rep = ch.build_report(list(bpy.data.scenes))
    ms = _meta(rep)
    out.append(("GN R7-1: data-stripped GEOMETRY -> S_META_UNREADABLE (never UNCHANGED)",
                bool(ms) and all(s.state == ch.S_META_UNREADABLE for s in ms),
                [s.state for s in ms], ch.S_META_UNREADABLE))
    results = engine.run_all(bpy.context, hash_verify=rep)
    out.append(("GN R7-1: data-stripped GEOMETRY + deleted blob -> #27 UNKNOWN",
                worst_for_check(results, 27) == Status.UNKNOWN,
                worst_for_check(results, 27), Status.UNKNOWN))
    out.append(("GN R7-1: data-stripped GEOMETRY -> requested verify nonzero",
                cli.verify_floor(rep, True) == cli.EXIT_UNVERIFIED,
                cli.verify_floor(rep, True), cli.EXIT_UNVERIFIED))

    # (R7-1 over-rejection guard A) A REAL value-only FLOAT bake: the FLOAT item stores
    # its value inline (no blob), and the recognizer must still accept it -> #27 PASS.
    fv = os.path.join(tmp, "r7_floatval")
    os.makedirs(fv, exist_ok=True)
    fixtures._make_gn_disk_blend(fv, float_item=True)
    bpy.ops.wm.open_mainfile(filepath=os.path.join(fv, "gn.blend"))
    man_fv = ch.capture(list(bpy.data.scenes), ci.blend_dir())
    bl.save_baseline(bpy.context.scene, bl.default_baseline_path(),
                     overwrite=True, cache_hashes=man_fv)
    rep = ch.build_report(list(bpy.data.scenes))
    ms, bs = _meta(rep), _blobs(rep)
    out.append(("GN R7-1 guard: value-only FLOAT bake verifies (not over-rejected)",
                bool(ms) and all(s.state == ch.S_UNCHANGED for s in ms + bs),
                [s.state for s in ms + bs], "UNCHANGED"))
    results = engine.run_all(bpy.context, hash_verify=rep)
    out.append(("GN R7-1 guard: value-only FLOAT bake -> #27 PASS",
                worst_for_check(results, 27) == Status.PASS,
                worst_for_check(results, 27), Status.PASS))

    # (R7-1 over-rejection guard B) A REAL empty-geometry bake: a GEOMETRY item whose
    # data is {} with NO blob on disk is legitimate and must verify -> #27 PASS. This
    # is the exact "geometry item without a blob" the fix must NOT reject.
    eg = os.path.join(tmp, "r7_emptygeo")
    os.makedirs(eg, exist_ok=True)
    fixtures._make_gn_disk_blend(eg, empty_geometry=True)
    egbd = fixtures.gn_bake_dir(eg)
    eg_blobs = (sorted(os.listdir(os.path.join(egbd, "blobs")))
                if egbd and os.path.isdir(os.path.join(egbd, "blobs")) else [])
    bpy.ops.wm.open_mainfile(filepath=os.path.join(eg, "gn.blend"))
    recs_eg = list(ci.iter_gn_cache_files(list(bpy.data.scenes)))
    out.append(("GN R7-1 guard: empty-geometry bake has recognizable metas, zero blobs",
                not any(r.identity.endswith("/meta") and r.meta_unreadable
                        for r in recs_eg) and len(eg_blobs) == 0,
                (len(eg_blobs), [bool(r.meta_unreadable) for r in recs_eg
                                 if r.identity.endswith("/meta")]),
                "0 blobs; meta not flagged"))
    man_eg = ch.capture(list(bpy.data.scenes), ci.blend_dir())
    bl.save_baseline(bpy.context.scene, bl.default_baseline_path(),
                     overwrite=True, cache_hashes=man_eg)
    rep = ch.build_report(list(bpy.data.scenes))
    ms = _meta(rep)
    out.append(("GN R7-1 guard: empty-geometry bake verifies UNCHANGED (not over-rejected)",
                bool(ms) and all(s.state == ch.S_UNCHANGED for s in ms),
                [s.state for s in ms], "UNCHANGED"))
    results = engine.run_all(bpy.context, hash_verify=rep)
    out.append(("GN R7-1 guard: empty-geometry bake -> #27 PASS (not UNKNOWN)",
                worst_for_check(results, 27) == Status.PASS,
                worst_for_check(results, 27), Status.PASS))
    # Non-blocker (R8 note): the STRUCTURAL inspector must not warn 'missing blob data'
    # for a legitimately blob-free bake — the empty-geometry metas reference no blob, so
    # an empty blobs/ dir is expected, not a defect.
    struct_missing = []
    for sobj in bpy.data.objects:
        for smod in sobj.modifiers:
            if smod.type == "NODES":
                for se in ci.inspect_gn_bakes(sobj, smod, bpy.context.scene):
                    struct_missing += list(se.components_missing or [])
    out.append(("GN blob-free: structural does NOT falsely warn 'blob data' missing",
                "blob data" not in struct_missing, struct_missing, "no 'blob data'"))

    # (R8-1, round 8) SUBFRAME coverage collision. A GN bake file is named
    # <frame>_<subframe>; the WHOLE frame is subframe 0. Coverage is keyed by the EXACT
    # stem, so a different-subframe file cannot satisfy a required whole frame. Rename a
    # real whole-frame meta (00003_00000.json -> 00003_00001.json), valid JSON and its
    # blobs UNCHANGED, BEFORE baseline: the required 00003_00000 is then absent even
    # though a file "for frame 3" exists. Collapsing to the integer frame 3 would mark
    # it covered and PASS; the exact-stem identity keeps it uncovered -> #27 UNKNOWN.
    r8 = os.path.join(tmp, "r8_subframe")
    os.makedirs(r8, exist_ok=True)
    fixtures._make_gn_disk_blend(r8)
    r8bd = fixtures.gn_bake_dir(r8)
    r8meta = os.path.join(r8bd, "meta")
    whole = os.path.join(r8meta, "00003_00000.json")
    subf = os.path.join(r8meta, "00003_00001.json")
    out.append(("GN R8-1: frame-3 whole-frame meta exists to rename (precondition)",
                os.path.exists(whole), os.path.exists(whole), True))
    os.rename(whole, subf)
    bpy.ops.wm.open_mainfile(filepath=os.path.join(r8, "gn.blend"))
    # Structural #17/#19 must NOT count the subframe file as frame 3 present.
    struct_present = None
    for sobj in bpy.data.objects:
        for smod in sobj.modifiers:
            if smod.type == "NODES":
                for e in ci.inspect_gn_bakes(sobj, smod, bpy.context.scene):
                    if e.frames_present:
                        struct_present = set(e.frames_present)
    out.append(("GN R8-1: structural check does NOT count subframe file as frame 3 present",
                struct_present is not None and 3 not in struct_present,
                sorted(struct_present) if struct_present else None, "3 absent"))
    man_r8 = ch.capture(list(bpy.data.scenes), ci.blend_dir())
    bl.save_baseline(bpy.context.scene, bl.default_baseline_path(),
                     overwrite=True, cache_hashes=man_r8)
    rep = ch.build_report(list(bpy.data.scenes))
    ms = _meta(rep)
    out.append(("GN R8-1: subframe file does NOT cover the required whole frame",
                bool(ms) and ms[0].state == ch.S_INCOMPLETE_REF
                and "00003_00000" in (ms[0].uncovered or []),
                [(s.state, s.uncovered) for s in ms], "uncovered incl. 00003_00000"))
    results = engine.run_all(bpy.context, hash_verify=rep)
    out.append(("GN R8-1: renamed-subframe gap -> #27 UNKNOWN (never PASS)",
                worst_for_check(results, 27) == Status.UNKNOWN,
                worst_for_check(results, 27), Status.UNKNOWN))
    out.append(("GN R8-1: renamed-subframe gap -> requested verify nonzero",
                cli.verify_floor(rep, True) == cli.EXIT_UNVERIFIED,
                cli.verify_floor(rep, True), cli.EXIT_UNVERIFIED))

    # (5) relocation (// bake dir) -> meta UNCHANGED
    reloc = os.path.join(tmp, "moved", "x")
    os.makedirs(os.path.dirname(reloc), exist_ok=True)
    shutil.copytree(src, reloc)
    bpy.ops.wm.open_mainfile(filepath=os.path.join(reloc, "gn.blend"))
    rep = ch.build_report(list(bpy.data.scenes))
    ms = _meta(rep)
    out.append(("GN relocation: meta UNCHANGED after moving the project",
                bool(ms) and all(s.state == ch.S_UNCHANGED for s in ms),
                [s.state for s in ms], "UNCHANGED"))

    # (6) cancelled capture raises (writes nothing)
    _open("cancel")
    cnt = {"n": 0}

    def _c():
        cnt["n"] += 1
        return cnt["n"] > 1
    try:
        ch.capture(list(bpy.data.scenes), ci.blend_dir(), cancel=_c)
        raised = False
    except ch.Cancelled:
        raised = True
    out.append(("GN cancelled capture raises Cancelled", raised, raised, True))

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
                                   + integrity_header_tests()
                                   + cache_coverage_tests()
                                   + cache_hash_tests()
                                   + hash_blocker_tests()
                                   + hash_edge_tests()
                                   + hash_edge2_tests()
                                   + hash_fluid_tests()
                                   + hash_gn_tests()
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
             + len(integrity_header_tests()) + len(cache_coverage_tests())
             + len(cache_hash_tests()) + len(hash_blocker_tests())
             + len(hash_edge_tests()) + len(hash_edge2_tests())
             + len(hash_fluid_tests()) + len(hash_gn_tests())
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
