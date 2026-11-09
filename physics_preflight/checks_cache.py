# SPDX-License-Identifier: GPL-3.0-or-later
"""Simulation-cache checks (17-23).

The headline differentiator: we never trust Blender's "baked" flags. We look at
the files on disk and report UNKNOWN wherever the truth cannot be established
(unsaved file, packed Geometry Nodes bake, memory cache).

Checks #17–#20 all read ONE authoritative verdict (``cache_inspect.cache_status``)
that compares the files on disk against the entire required frame range, so they
can never contradict each other — a missing first, middle or last frame fails
every one of them, not none.
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


def _missing_summary(missing):
    if not missing:
        return ""
    preview = ", ".join(str(g) for g in missing[:8])
    more = "" if len(missing) <= 8 else " …(+%d more)" % (len(missing) - 8)
    return preview + more


# -------------------------------------------------------------------- 17 ----
@check(17, "Is the simulation baked?", GROUP_CACHE)
def c17_baked(ctx, mk):
    entries = _caches(ctx)
    if not entries:
        return []
    out = []
    for e in entries:
        name = e.obj_name
        # Rigid Body World keeps its cache in the .blend; answer from the flag.
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
        v = ci.cache_status(e)
        s = v.state
        if s == ci.V_REPLAY:
            out.append(mk(Status.WARNING,
                          "Fluid cache type is Replay — frames are generated on "
                          "playback, not baked. A render farm will re-simulate.",
                          object_name=name,
                          hint="Set the cache type to 'All' and bake for a fixed "
                               "result."))
        elif s == ci.V_MEMORY:
            if e.baked_flag:
                out.append(mk(Status.PASS,
                              "%s is baked into the .blend (memory cache)."
                              % e.system, object_name=name))
            else:
                out.append(mk(Status.WARNING,
                              "%s is not baked; the render may differ from the "
                              "viewport." % e.system, object_name=name,
                              hint="Bake the simulation before rendering."))
        elif s == ci.V_UNVERIFIABLE:
            if not e.baked_determinable:
                out.append(mk(Status.UNKNOWN,
                              "Packed Geometry Nodes bake — Blender does not "
                              "expose whether it is baked.",
                              object_name=name,
                              hint="Open the bake panel to confirm, or bake to "
                                   "disk."))
            elif e.baked_flag:
                out.append(mk(Status.UNKNOWN,
                              "%s reports baked, but files can't be verified "
                              "(save the file, then re-scan)." % e.system,
                              object_name=name))
            else:
                out.append(mk(Status.WARNING,
                              "%s is not baked." % e.system, object_name=name,
                              hint="Bake the simulation before rendering."))
        elif s == ci.V_COMPLETE:
            out.append(mk(Status.PASS,
                          "%s is baked and all its cache files are on disk."
                          % e.system, object_name=name))
        elif s == ci.V_EMPTY:
            out.append(mk(Status.FAIL,
                          "%s is marked baked, but no cache files exist on disk "
                          "(see #18)." % e.system, object_name=name,
                          hint="Re-bake the simulation."))
        elif s in (ci.V_INCOMPLETE, ci.V_CORRUPT):
            out.append(mk(Status.FAIL,
                          "%s is marked baked, but its cache on disk is "
                          "incomplete (see #18 and #20)." % e.system,
                          object_name=name, hint="Delete the cache and re-bake."))
        elif s == ci.V_UNREADABLE:
            out.append(mk(Status.UNKNOWN,
                          "%s has cache files that can't be read; bake integrity "
                          "is uncertain." % e.system, object_name=name))
        else:  # V_NOT_BAKED
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
        v = ci.cache_status(e)
        s = v.state
        if s == ci.V_MEMORY:
            out.append(mk(Status.NA,
                          "%s uses a memory cache (stored in the .blend); there "
                          "are no cache files to verify." % e.system,
                          object_name=name,
                          hint="Enable Disk Cache if you render on a farm."))
        elif s == ci.V_REPLAY:
            out.append(mk(Status.WARNING,
                          "%s is in Replay mode — not a real bake. Frames on "
                          "disk don't guarantee a render-safe cache." % e.system,
                          object_name=name,
                          hint="Switch to 'All' and bake for a fixed result."))
        elif s == ci.V_UNVERIFIABLE:
            if not e.baked_determinable:
                out.append(mk(Status.UNKNOWN,
                              "Packed Geometry Nodes bake — no files to verify.",
                              object_name=name))
            else:
                out.append(mk(Status.UNKNOWN,
                              "%s cache location could not be resolved." % e.system,
                              object_name=name))
        elif s == ci.V_COMPLETE:
            out.append(mk(Status.PASS,
                          "All %d expected %s cache files exist and are non-empty."
                          % (len(v.required), e.system), object_name=name))
        elif s == ci.V_EMPTY:
            out.append(mk(Status.FAIL,
                          "Blender reports '%s' as baked, but NO cache files "
                          "exist on disk. The render farm will re-simulate or "
                          "freeze." % e.system, object_name=name,
                          hint="Re-bake the simulation."))
        elif s == ci.V_NOT_BAKED:
            out.append(mk(Status.WARNING,
                          "%s has no cache files on disk and is not baked."
                          % e.system, object_name=name,
                          hint="Bake the simulation before rendering."))
        elif s == ci.V_CORRUPT:
            out.append(mk(Status.FAIL,
                          "%s has %d empty (0-byte) cache file(s); those frames "
                          "are corrupt." % (e.system, len(v.empty)),
                          object_name=name,
                          hint="Delete the cache and re-bake."))
        elif s == ci.V_INCOMPLETE:
            extra = (" %s." % v.note) if v.note else ""
            out.append(mk(Status.FAIL,
                          "%s is missing %d of %d required cache frame(s) on "
                          "disk: %s.%s The render will freeze or re-simulate "
                          "there." % (e.system, len(v.missing), len(v.required),
                                      _missing_summary(v.missing), extra),
                          object_name=name,
                          hint="Delete the cache and re-bake the full range."))
        elif s == ci.V_UNREADABLE:
            out.append(mk(Status.UNKNOWN,
                          "%s has %d cache file(s) that can't be read; can't "
                          "confirm the bake." % (e.system, len(v.unreadable)),
                          object_name=name,
                          hint="Check file permissions, or re-bake."))
    return out


# -------------------------------------------------------------------- 19 ----
@check(19, "Baked range covers the render range", GROUP_CACHE)
def c19_range_covers(ctx, mk):
    entries = _caches(ctx)
    out = []
    for e in entries:
        if e.cache_range is None or e.scene_range is None:
            continue
        if not e.baked_determinable:   # packed GN
            continue
        if e.replay:                   # not a real bake
            continue
        cs, ce = e.cache_range
        ss, se = e.scene_range
        name = e.obj_name
        # Only meaningful if something is (meant to be) baked.
        baked_intent = e.baked_flag or e.frames_present
        if cs > ss or ce < se:
            out.append(mk(Status.WARNING,
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
    file_entries = [e for e in entries if e.kind in ("point", "fluid", "gn")]
    if not ci.blend_is_saved():
        if file_entries:
            return [mk(Status.UNKNOWN,
                       "File is not saved; frame-by-frame coverage can't be "
                       "checked.")]
        return []
    out = []
    for e in file_entries:
        name = e.obj_name
        v = ci.cache_status(e)
        s = v.state
        if s == ci.V_INCOMPLETE:
            lo, hi = min(v.required), max(v.required)
            out.append(mk(Status.FAIL,
                          "%s is missing %d cached frame(s) across its %d–%d "
                          "range: %s. Each gap is a freeze/pop in the render."
                          % (e.system, len(v.missing), lo, hi,
                             _missing_summary(v.missing)),
                          object_name=name,
                          hint="Delete the cache and re-bake the full range."))
        elif s == ci.V_COMPLETE:
            lo, hi = min(v.required), max(v.required)
            if e.sampled:
                out.append(mk(Status.WARNING,
                              "%s is cached every %d frames (sampled), not every "
                              "frame. In-between frames are interpolated and the "
                              "sim may pop." % (e.system, e.frame_step),
                              object_name=name,
                              hint="Set Cache Step to 1 and re-bake for an exact "
                                   "sim."))
            else:
                out.append(mk(Status.PASS,
                              "%s has every frame cached from %d to %d."
                              % (e.system, lo, hi), object_name=name))
        # EMPTY / CORRUPT / UNREADABLE / MEMORY / REPLAY / UNVERIFIABLE are
        # reported by #17/#18; #20 stays silent to avoid contradicting them.
    return out


# -------------------------------------------------------------------- 21 ----
@check(21, "Two simulations sharing one cache location", GROUP_CACHE)
def c21_shared_cache(ctx, mk):
    entries = _caches(ctx)
    buckets = {}
    resolved_any = False
    for e in entries:
        if e.identity is None:
            continue
        # ignore unresolved (None-path) identities
        if any(p is None for p in e.identity[1:2]):
            continue
        resolved_any = True
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
    if not out and resolved_any:
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
        if e.kind == "rbw" or e.memory:
            continue
        if e.portable is None:
            continue
        checked = True
        name = e.obj_name
        if not e.portable:
            note = (" (%s)" % e.path_note) if e.path_note else ""
            out.append(mk(Status.WARNING,
                          "%s cache path is absolute or outside the project%s. "
                          "It won't be found on another machine or render farm."
                          % (e.system, note),
                          object_name=name,
                          hint="Point the cache folder inside the project using "
                               "a relative (//) path."))
    if not out and checked:
        return [mk(Status.PASS, "All cache paths are relative and inside the "
                                "project folder.")]
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
