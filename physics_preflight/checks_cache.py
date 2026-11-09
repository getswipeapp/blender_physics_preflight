# SPDX-License-Identifier: GPL-3.0-or-later
"""Simulation-cache checks (17-23).

The headline differentiator: we never trust Blender's "baked" flags. We look at
the files on disk (cache_inspect.py) and report UNKNOWN wherever the truth
cannot be established (unsaved file, packed Geometry Nodes bake, memory cache).
"""
from .engine import check, Status, GROUP_CACHE
from . import cache_inspect as ci


def _caches(ctx):
    # enumerate once per scan and stash on ctx to avoid rescanning the disk.
    cached = getattr(ctx, "_physpf_caches", None)
    if cached is None:
        cached = ci.enumerate_caches(ctx.scene)
        try:
            ctx._physpf_caches = cached
        except Exception:
            pass
    return cached


def _label(e):
    return "%s — %s" % (e.obj_name, e.system) if e.obj_name != e.system else e.system


# -------------------------------------------------------------------- 17 ----
@check(17, "Is the simulation baked?", GROUP_CACHE)
def c17_baked(ctx, mk):
    entries = _caches(ctx)
    if not entries:
        return []
    out = []
    for e in entries:
        name = e.obj_name
        if not e.baked_determinable:
            out.append(mk(Status.UNKNOWN,
                          "Packed Geometry Nodes bake — Blender does not expose "
                          "whether it is baked.",
                          object_name=name,
                          hint="Open the bake panel to confirm, or bake to disk."))
            continue
        if e.kind == "rbw":
            if e.baked_flag:
                out.append(mk(Status.PASS,
                              "Rigid Body World cache is baked (stored in the "
                              ".blend).", object_name=name))
            else:
                out.append(mk(Status.WARNING,
                              "Rigid Body World is not baked. The render farm "
                              "will re-simulate and may differ from the viewport.",
                              object_name=name,
                              hint="Bake it in Scene > Rigid Body World > Cache."))
            continue
        # file-backed systems: the real answer comes from disk (#18). Here we
        # only report the intent/flag, being honest about replay and unsaved.
        if e.replay:
            out.append(mk(Status.WARNING,
                          "Fluid cache type is Replay — frames are generated on "
                          "playback, not baked. A render farm will re-simulate.",
                          object_name=name,
                          hint="Set the cache type to 'All' and bake for a "
                               "fixed result."))
            continue
        # File-backed systems: answer from disk so #17 agrees with #18.
        if e.kind == "point" and e.uses_disk is False:
            # memory cache stored in the .blend
            if e.baked_flag:
                out.append(mk(Status.PASS,
                              "%s is baked into the .blend (memory cache)."
                              % e.system, object_name=name))
            else:
                out.append(mk(Status.WARNING,
                              "%s is not baked; the render may differ from the "
                              "viewport." % e.system, object_name=name,
                              hint="Bake the simulation before rendering."))
            continue
        if not e.file_check_applicable:
            if e.baked_flag:
                out.append(mk(Status.UNKNOWN,
                              "%s reports baked, but files can't be verified "
                              "(save the file, then re-scan)." % e.system,
                              object_name=name))
            else:
                out.append(mk(Status.WARNING,
                              "%s is not baked." % e.system, object_name=name,
                              hint="Bake the simulation before rendering."))
            continue
        if e.frames_present:
            out.append(mk(Status.PASS,
                          "%s is baked and its cache files are on disk."
                          % e.system, object_name=name))
        elif e.baked_flag:
            out.append(mk(Status.FAIL,
                          "%s is marked baked, but no cache files exist on disk "
                          "(see #18)." % e.system, object_name=name,
                          hint="Re-bake the simulation."))
        else:
            out.append(mk(Status.WARNING,
                          "%s is not baked." % e.system, object_name=name,
                          hint="Bake the simulation before rendering."))
    return out


# -------------------------------------------------------------------- 18 ----
@check(18, "Cache files actually present on disk (not just the 'baked' flag)",
       GROUP_CACHE)
def c18_files_present(ctx, mk):
    entries = _caches(ctx)
    file_entries = [e for e in entries if e.kind in ("point", "fluid", "gn")]
    if not file_entries:
        if any(e.kind == "rbw" for e in entries):
            return [mk(Status.NA,
                       "The only simulation is the Rigid Body World, whose cache "
                       "lives in the .blend (no files to verify).")]
        return []
    if not ci.blend_is_saved():
        return [mk(Status.UNKNOWN,
                   "File is not saved, so disk caches can't be verified. Save "
                   "the .blend and re-scan.")]
    out = []
    for e in file_entries:
        name = e.obj_name
        if e.kind == "gn" and not e.baked_determinable:
            out.append(mk(Status.UNKNOWN,
                          "Packed Geometry Nodes bake — no files to verify.",
                          object_name=name))
            continue
        if e.kind == "point" and e.uses_disk is False:
            out.append(mk(Status.NA,
                          "%s uses a memory cache (stored in the .blend); there "
                          "are no cache files to verify." % e.system,
                          object_name=name,
                          hint="Enable Disk Cache if you render on a farm."))
            continue
        if not e.file_check_applicable or e.cache_dir is None:
            out.append(mk(Status.UNKNOWN,
                          "%s cache location could not be resolved." % e.system,
                          object_name=name))
            continue
        expected = set(e.frames_expected or [])
        present = e.frames_present
        if not expected:
            out.append(mk(Status.UNKNOWN,
                          "%s cache frame range is empty." % e.system,
                          object_name=name))
            continue
        missing = sorted(expected - present)
        if not present:
            if e.baked_flag:
                out.append(mk(Status.FAIL,
                              "Blender reports '%s' as baked, but NO cache files "
                              "exist on disk. The render farm will re-simulate or "
                              "freeze." % e.system,
                              object_name=name,
                              hint="Re-bake the simulation."))
            else:
                out.append(mk(Status.WARNING,
                              "%s has no cache files on disk and is not baked."
                              % e.system,
                              object_name=name,
                              hint="Bake the simulation before rendering."))
        elif e.frames_empty:
            out.append(mk(Status.FAIL,
                          "%s has %d empty (0-byte) cache file(s); those frames "
                          "are corrupt." % (e.system, len(e.frames_empty)),
                          object_name=name,
                          hint="Delete the cache and re-bake."))
        elif missing:
            # full coverage handled by #20; here we fail only on no/empty files,
            # and pass when at least the full expected set is present.
            out.append(mk(Status.PASS,
                          "%s cache files exist on disk (coverage checked in "
                          "#20)." % e.system, object_name=name))
        else:
            out.append(mk(Status.PASS,
                          "All %d expected %s cache files exist and are non-empty."
                          % (len(expected), e.system), object_name=name))
    return out


# -------------------------------------------------------------------- 19 ----
@check(19, "Baked range covers the render range", GROUP_CACHE)
def c19_range_covers(ctx, mk):
    entries = _caches(ctx)
    out = []
    for e in entries:
        if e.cache_range is None or e.scene_range is None:
            continue
        if e.kind == "gn" and not e.baked_determinable:
            continue
        cs, ce = e.cache_range
        ss, se = e.scene_range
        name = e.obj_name
        # Only meaningful if something is (meant to be) baked.
        baked_intent = e.baked_flag or e.frames_present
        if cs > ss or ce < se:
            status = Status.WARNING if baked_intent else Status.WARNING
            out.append(mk(status,
                          "Bake covers frames %d–%d but the scene renders %d–%d. "
                          "The simulation freezes outside the baked range."
                          % (cs, ce, ss, se),
                          object_name=name,
                          hint="Set the cache start/end to match the scene, then "
                               "re-bake."))
        elif baked_intent:
            out.append(mk(Status.PASS,
                          "Bake range %d–%d covers the render range %d–%d."
                          % (cs, ce, ss, se), object_name=name))
    return out


# -------------------------------------------------------------------- 20 ----
@check(20, "Frame gaps: every frame cached (not sampled)", GROUP_CACHE)
def c20_frame_gaps(ctx, mk):
    entries = _caches(ctx)
    file_entries = [e for e in entries
                    if e.kind in ("point", "fluid", "gn") and e.file_check_applicable]
    if not ci.blend_is_saved():
        if any(e.kind in ("point", "fluid", "gn") for e in entries):
            return [mk(Status.UNKNOWN,
                       "File is not saved; frame-by-frame coverage can't be "
                       "checked.")]
        return []
    out = []
    for e in file_entries:
        if e.kind == "point" and e.uses_disk is False:
            continue  # memory cache, NA (reported in #18)
        name = e.obj_name
        expected = set(e.frames_expected or [])
        present = e.frames_present
        if not expected or not present:
            continue  # #18 handles the no-files case
        # intersect expected with the baked span actually on disk, so a bake
        # that is simply shorter than the scene (that's #19) doesn't double-fail.
        lo = min(present)
        hi = max(present)
        span = {f for f in expected if lo <= f <= hi}
        gaps = sorted(span - present)
        if gaps:
            preview = ", ".join(str(g) for g in gaps[:8])
            more = "" if len(gaps) <= 8 else " …(+%d more)" % (len(gaps) - 8)
            out.append(mk(Status.FAIL,
                          "%s is missing %d cached frame(s) inside its baked "
                          "span: %s%s. Each gap is a pop in the render."
                          % (e.system, len(gaps), preview, more),
                          object_name=name,
                          hint="Delete the cache and re-bake the full range."))
        else:
            out.append(mk(Status.PASS,
                          "%s has every frame cached from %d to %d."
                          % (e.system, lo, hi), object_name=name))
    return out


# -------------------------------------------------------------------- 21 ----
@check(21, "Two simulations sharing one cache location", GROUP_CACHE)
def c21_shared_cache(ctx, mk):
    entries = _caches(ctx)
    buckets = {}
    for e in entries:
        if e.identity is None:
            continue
        # ignore unresolved (None-path) identities
        if any(p is None for p in e.identity[1:2]):
            continue
        buckets.setdefault(e.identity, []).append(e)
    out = []
    for ident, group in buckets.items():
        if len(group) > 1:
            names = ", ".join("'%s'" % g.obj_name for g in group)
            out.append(mk(Status.WARNING,
                          "%s write to the same cache location. One will "
                          "silently overwrite the other." % names,
                          hint="Give each simulation its own cache name or "
                               "folder."))
    if not out and entries:
        return [mk(Status.PASS, "Each simulation uses its own cache location.")]
    return out


# -------------------------------------------------------------------- 22 ----
@check(22, "Non-portable cache paths (absolute / outside the project)",
       GROUP_CACHE)
def c22_portable(ctx, mk):
    entries = _caches(ctx)
    out = []
    checked = False
    for e in entries:
        if e.kind == "rbw":
            continue
        if e.kind == "point" and e.uses_disk is False:
            continue
        if e.portable is None:
            continue
        checked = True
        name = e.obj_name
        if e.external and e.kind == "point":
            if not e.portable:
                out.append(mk(Status.WARNING,
                              "%s uses an external cache path that isn't inside "
                              "the project. It will break on another machine or "
                              "render farm.%s"
                              % (e.system,
                                 " (%s)" % e.path_note if e.path_note else ""),
                              object_name=name,
                              hint="Use a relative (//) path inside the project."))
                continue
        if not e.portable:
            note = (" (%s)" % e.path_note) if e.path_note else ""
            out.append(mk(Status.WARNING,
                          "%s cache path is absolute or outside the project%s. "
                          "It won't be found on another machine." % (e.system, note),
                          object_name=name,
                          hint="Point the cache folder inside the project using "
                               "a relative (//) path."))
    if not out and checked:
        return [mk(Status.PASS, "All cache paths are inside the project folder.")]
    return out


# -------------------------------------------------------------------- 23 ----
@check(23, "FPS / time-scale changed after baking", GROUP_CACHE)
def c23_fps_timescale(ctx, mk):
    entries = _caches(ctx)
    baked_any = any((e.baked_flag or e.frames_present) for e in entries)
    if not baked_any:
        return []
    scene = ctx.scene
    out = []
    # Rigid Body World time scale is a clear, readable red flag.
    rbw = scene.rigidbody_world
    if rbw is not None and abs(getattr(rbw, "time_scale", 1.0) - 1.0) > 1e-4:
        out.append(mk(Status.WARNING,
                      "Rigid Body World time scale is %.3g (not 1.0). If it "
                      "changed after baking, the sim plays at the wrong speed."
                      % rbw.time_scale,
                      hint="Re-bake after changing time scale."))
    # Blender records no FPS at bake time, so this is UNKNOWN by nature.
    fps = scene.render.fps / max(scene.render.fps_base, 1e-6)
    out.append(mk(Status.UNKNOWN,
                  "Blender doesn't store the FPS used at bake time. Current "
                  "scene FPS is %.3g — if you changed FPS or time scale after "
                  "baking, re-bake so the timing matches." % fps,
                  hint="When in doubt, delete the cache and re-bake."))
    return out
