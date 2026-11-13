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
import os

import bpy

from .engine import check, Status, GROUP_CACHE
from . import cache_inspect as ci
from . import baseline as bl


def _caches(ctx):
    # enumerate once per scan and stash on ctx to avoid rescanning the disk.
    cached = getattr(ctx, "_failsafe_caches", None)
    if cached is None:
        cached = ci.enumerate_caches(ctx.scene)
        try:
            ctx._failsafe_caches = cached
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
@check(17, "Simulation is baked", GROUP_CACHE,
       name_bad="Simulation isn't properly baked",
       name_unknown="Simulation bake couldn't be verified")
def c17_baked(ctx, mk):
    entries = _caches(ctx)
    if not entries:
        return []
    out = []
    for e in entries:
        name = e.obj_name
        # Rigid Body World keeps its cache in the .blend; answer from the flag —
        # but still honour the staleness flags so a baked-but-outdated RBW can't
        # get a clean PASS (R17).
        if e.kind == "rbw":
            reasons = ci.reliability_reasons(e)
            if not e.baked_flag:
                out.append(mk(Status.WARNING,
                              "Rigid Body World is not baked. The render farm "
                              "will re-simulate and may differ from the viewport.",
                              object_name=name,
                              hint="Bake it in Scene > Rigid Body World > Cache."))
            elif reasons:
                out.append(mk(Status.UNKNOWN,
                              "Rigid Body World is baked, but %s — it may not "
                              "match the current simulation."
                              % "; ".join(reasons), object_name=name,
                              hint="Re-bake the Rigid Body World cache to be "
                                   "sure it's current."))
            else:
                out.append(mk(Status.PASS,
                              "Rigid Body World cache is baked (stored in the "
                              ".blend).", object_name=name))
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
            reasons = ci.reliability_reasons(e)
            if not e.baked_flag:
                out.append(mk(Status.WARNING,
                              "%s is not baked; the render may differ from the "
                              "viewport." % e.system, object_name=name,
                              hint="Bake the simulation before rendering."))
            elif reasons:
                # A memory cache has no files to verify, but Blender's own flags
                # can still say it's stale — don't green-light it (R17).
                out.append(mk(Status.UNKNOWN,
                              "%s is baked into the .blend, but %s — it may not "
                              "match the current simulation."
                              % (e.system, "; ".join(reasons)), object_name=name,
                              hint="Re-bake the simulation to be sure the cache "
                                   "is current."))
            else:
                out.append(mk(Status.PASS,
                              "%s is baked into the .blend (memory cache)."
                              % e.system, object_name=name))
        elif s == ci.V_UNVERIFIABLE:
            if not e.baked_determinable:
                out.append(mk(Status.UNKNOWN,
                              "Packed Geometry Nodes bake — Blender does not "
                              "expose whether it is baked.",
                              object_name=name,
                              hint="Open the bake panel to confirm, or bake to "
                                   "disk."))
            elif not e.file_check_applicable:
                if e.baked_flag:
                    out.append(mk(Status.UNKNOWN,
                                  "%s reports baked, but files can't be verified "
                                  "(save the file, then re-scan)." % e.system,
                                  object_name=name))
                else:
                    out.append(mk(Status.WARNING,
                                  "%s is not baked." % e.system, object_name=name,
                                  hint="Bake the simulation before rendering."))
            else:
                # files are visible but integrity can't be proven (GN disk bake)
                out.append(mk(Status.UNKNOWN,
                              "%s: %s." % (e.system,
                                           v.note or "the bake can't be fully "
                                           "verified from Python"),
                              object_name=name,
                              hint="Open the bake panel to confirm it's current."))
        elif s == ci.V_COMPLETE:
            if e.baked_flag:
                out.append(mk(Status.PASS,
                              "%s is baked and all its cache files are on disk."
                              % e.system, object_name=name))
            else:
                # Files for the full range exist, but Blender's baked flag is
                # off — they could be a stale cache from an earlier bake. Don't
                # assert "baked" on file presence alone.
                out.append(mk(Status.WARNING,
                              "%s has a full set of cache files on disk, but "
                              "Blender's 'baked' flag is off — the cache may be "
                              "stale or from older settings." % e.system,
                              object_name=name,
                              hint="Re-bake to be sure the cache matches the "
                                   "current simulation."))
        elif s == ci.V_EMPTY:
            out.append(mk(Status.FAIL,
                          "%s is marked baked, but no cache files exist on disk."
                          % e.system, object_name=name,
                          hint="Re-bake the simulation."))
        elif s in (ci.V_INCOMPLETE, ci.V_CORRUPT):
            out.append(mk(Status.FAIL,
                          "%s is marked baked, but its cache on disk is "
                          "incomplete." % e.system,
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
@check(18, "Cache files are really on disk", GROUP_CACHE,
       name_bad="Cache files are missing from disk",
       name_unknown="Cache files couldn't be verified",
       name_na="No disk cache to verify")
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
                              "Packed Geometry Nodes bake: Blender keeps it "
                              "inside the .blend where its files can't be seen "
                              "from outside, so it can't be verified. This is a "
                              "Blender limitation, not a problem with your scene.",
                              object_name=name,
                              hint="Check it in the Geometry Nodes bake panel. "
                                   "Baking to a Disk cache instead would let "
                                   "Failsafe verify the files."))
            elif not e.file_check_applicable or e.cache_dir is None:
                out.append(mk(Status.UNKNOWN,
                              "%s cache location could not be resolved." % e.system,
                              object_name=name))
            else:
                out.append(mk(Status.UNKNOWN,
                              "%s on-disk bake is present, but %s." %
                              (e.system, v.note or "its data can't be fully "
                               "verified from Python"),
                              object_name=name,
                              hint="Open the bake panel to confirm it's current."))
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
            if v.missing:
                msg = ("%s is missing %d of %d required cache frame(s) on disk: "
                       "%s." % (e.system, len(v.missing), len(v.required),
                                _missing_summary(v.missing)))
                if v.note:
                    msg += " Also %s." % v.note
            else:
                # data frames are all present; a sub-cache (mesh/noise/particles)
                # or GN blob data is what's incomplete.
                msg = ("%s cache is incomplete: %s."
                       % (e.system, v.note or "a required sub-cache is missing "
                          "frames"))
            out.append(mk(Status.FAIL,
                          msg + " The render will freeze or re-simulate there.",
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
@check(19, "Baked frames cover the render", GROUP_CACHE,
       name_bad="Bake doesn't cover the render",
       name_unknown="Bake coverage couldn't be confirmed")
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
        off = int(getattr(e, "cache_frame_offset", 0) or 0)
        if off:
            # A cache frame offset shifts which cached frame plays at each scene
            # frame, so the baked range no longer lines up with the render range
            # directly. We won't assert coverage from the raw numbers. (R12)
            out.append(mk(Status.UNKNOWN,
                          "%s has a cache frame offset of %d, so the baked range "
                          "(%d–%d) doesn't map straight onto the render range "
                          "(%d–%d). Coverage can't be confirmed automatically."
                          % (e.system, off, cs, ce, ss, se),
                          object_name=name,
                          hint="Set the offset to 0, or check by hand that the "
                               "shifted range still covers the scene."))
            continue
        if cs > ss or ce < se:
            out.append(mk(Status.WARNING,
                          "Bake covers frames %d–%d but the scene renders %d–%d. "
                          "The simulation freezes outside the baked range."
                          % (cs, ce, ss, se),
                          object_name=name,
                          hint="Set the cache start/end to match the scene, then "
                               "re-bake."))
            continue
        # The configured range covers the render range. Only call it PASS when
        # the cache is actually there in full — otherwise the missing files are
        # the real story (reported by #18/#20) and #19 must not reassure.
        v = ci.cache_status(e)
        if v.state == ci.V_MEMORY:
            # Only call range coverage a PASS when the memory cache is both baked
            # and not flagged stale/outdated/baking — #17 carries the staleness
            # warning otherwise (R17).
            if e.baked_flag and not ci.reliability_reasons(e):
                out.append(mk(Status.PASS,
                              "Bake range %d–%d covers the render range %d–%d."
                              % (cs, ce, ss, se), object_name=name))
        elif v.state == ci.V_COMPLETE and e.baked_flag:
            out.append(mk(Status.PASS,
                          "Bake range %d–%d covers the render range %d–%d and "
                          "every frame is on disk." % (cs, ce, ss, se),
                          object_name=name))
        # INCOMPLETE / EMPTY / stale / UNKNOWN: stay silent here; #18 and #20
        # carry the failure so #19 never shows a green tick over missing files.
    return out


# -------------------------------------------------------------------- 20 ----
@check(20, "Every frame is cached (no gaps)", GROUP_CACHE,
       name_bad="Some frames are missing from the cache",
       name_warn="Cache is sampled, not every frame",
       name_unknown="Frame coverage couldn't be checked")
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
        if s == ci.V_INCOMPLETE and v.missing:
            lo, hi = min(v.required), max(v.required)
            out.append(mk(Status.FAIL,
                          "%s is missing %d cached frame(s) across its %d–%d "
                          "range: %s. Each gap is a freeze/pop in the render."
                          % (e.system, len(v.missing), lo, hi,
                             _missing_summary(v.missing)),
                          object_name=name,
                          hint="Delete the cache and re-bake the full range."))
        # INCOMPLETE with no missing data frames = a sub-cache gap, reported by
        # #18; #20 stays silent to avoid a "missing 0 frames" line.
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
@check(21, "Each sim has its own cache folder", GROUP_CACHE,
       name_bad="Two sims share a cache folder",
       name_unknown="Cache locations couldn't be fully checked")
def c21_shared_cache(ctx, mk):
    entries = _caches(ctx)
    buckets = {}
    resolved_any = False
    unresolved = False
    for e in entries:
        if e.kind not in ("point", "fluid", "gn") or e.memory:
            continue  # only disk-backed caches can clash on a location
        if e.identity is None or any(p is None for p in e.identity[1:2]):
            unresolved = True
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
    if out:
        return out
    if unresolved:
        return [mk(Status.UNKNOWN,
                   "Some cache locations couldn't be resolved, so a shared-"
                   "location clash can't be ruled out (save the file / check "
                   "external paths).")]
    if resolved_any:
        return [mk(Status.PASS, "Each simulation uses its own cache location.")]
    return []


# -------------------------------------------------------------------- 22 ----
@check(22, "Cache is saved inside the project", GROUP_CACHE,
       name_bad="Cache path may not be portable",
       name_unknown="Cache portability couldn't be confirmed")
def c22_portable(ctx, mk):
    entries = _caches(ctx)
    out = []
    checked = False
    unresolved = False
    for e in entries:
        if e.kind == "rbw" or e.memory:
            continue
        if e.portable is None:
            unresolved = True
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
    if out:
        return out
    if unresolved:
        return [mk(Status.UNKNOWN,
                   "Some cache paths couldn't be resolved (unsaved file or an "
                   "external path), so portability can't be confirmed.")]
    if checked:
        return [mk(Status.PASS, "All cache paths are relative and inside the "
                                "project folder.")]
    return []


# -------------------------------------------------------------------- 23 ----
@check(23, "Frame rate/speed unchanged since bake", GROUP_CACHE,
       name_bad="Frame rate/speed may have changed since bake",
       name_warn="Playback speed may have changed since bake",
       name_unknown="Bake timing couldn't be confirmed")
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


# -------------------------------------------------------------------- 24 ----
@check(24, "Caches aren't in a cloud-synced folder", GROUP_CACHE,
       name_warn="A cache sits in a cloud-synced folder",
       name_bad="A cache sits in a cloud-synced folder",
       name_unknown="Couldn't check the cache folder location")
def c24_cloud_path(ctx, mk):
    """Warn when a disk cache lives inside Dropbox/Google Drive/OneDrive/iCloud/
    etc. These clients can lock, partially upload, or swap in an offline
    placeholder for a frame file mid-render. Read-only: we only inspect paths."""
    entries = _caches(ctx)
    out = []
    checked = False
    for e in entries:
        if e.kind == "rbw" or e.memory:
            continue
        if e.cache_dir:
            checked = True
        if e.cloud_marker:
            out.append(mk(Status.WARNING,
                          "%s cache is inside a %s folder. Cloud clients can "
                          "lock or only partially sync a frame while the farm "
                          "reads it, which can corrupt a render."
                          % (e.system, e.cloud_marker),
                          object_name=e.obj_name,
                          hint="Move the cache to a local project folder before "
                               "baking for a render or farm submission."))
    if out:
        return out
    if checked:
        return [mk(Status.PASS,
                   "No simulation cache is inside a known cloud-synced folder.")]
    return []


# -------------------------------------------------------------------- 25 ----
@check(25, "No orphaned cache files on disk", GROUP_CACHE,
       name_warn="Orphaned cache files are taking up space",
       name_bad="Orphaned cache files are taking up space",
       name_unknown="Couldn't check for orphaned cache files")
def c25_orphan_files(ctx, mk):
    """Report .bphys files in the project's blendcache folder that no current
    simulation owns — usually left behind after renaming or deleting an object.
    Read-only: we report and size them; we never delete anything (that stays the
    user's call)."""
    entries = _caches(ctx)
    cache_dir = ci.default_blendcache_dir()
    if not cache_dir or not os.path.isdir(cache_dir):
        # No saved file / no default cache folder: nothing to assert.
        return []
    try:
        orphans = ci.find_orphan_point_caches(ctx.scene, entries)
    except OSError as exc:
        # Couldn't read the folder — say so, never report a clean folder we
        # didn't actually inspect. (R22)
        return [mk(Status.UNKNOWN,
                   "The blendcache folder couldn't be read (%s), so orphaned "
                   "files can't be checked." % exc,
                   hint="Check the folder's permissions, then scan again.")]
    if not orphans:
        return [mk(Status.PASS,
                   "Every cache file in the project's blendcache folder belongs "
                   "to a simulation in this .blend.")]
    files = sum(o["files"] for o in orphans)
    total = sum(o["bytes"] for o in orphans)
    return [mk(Status.WARNING,
               "%d cache file%s (%s) in the blendcache folder aren't owned by "
               "any simulation in this scene — likely left over from a renamed "
               "or deleted object."
               % (files, "" if files == 1 else "s", ci.human_bytes(total)),
               hint="Safe to delete to reclaim space once you're sure no other "
                    ".blend shares this folder. Failsafe never deletes them for "
                    "you.")]


# -------------------------------------------------------------------- 26 ----
@check(26, "Tracked settings unchanged since baseline", GROUP_CACHE,
       name_warn="Settings changed since the baseline",
       name_bad="Settings changed since the baseline",
       name_unknown="Couldn't compare against a settings baseline")
def c26_settings_baseline(ctx, mk):
    """Compare current simulation settings to a user-saved baseline (the external
    ``.failsafe-baseline.json`` written by the Save Baseline button). Read-only:
    it only reads that file, and never claims 'unchanged since bake' — only
    'unchanged since the baseline was saved'. No/unreadable/mismatched baseline
    is 'Couldn't verify', never Pass."""
    scene = ctx.scene
    current = bl.capture_fingerprints(scene)
    if not current:
        return []  # no simulations: nothing to baseline
    path = bl.default_baseline_path()
    if not path:
        return [mk(Status.UNKNOWN,
                   "The file isn't saved, so there's no baseline to compare "
                   "against yet.",
                   hint="Save your .blend, bake, then click Save Baseline to "
                        "record the settings. Future scans will flag changes.")]
    try:
        data = bl.load_baseline(path)
    except ValueError as exc:
        reason = str(exc)
        if reason == "no baseline file":
            return [mk(Status.UNKNOWN,
                       "No settings baseline has been saved yet, so changes to "
                       "the simulation settings can't be detected.",
                       hint="Right after you bake, click Save Baseline. It writes "
                            "a small .failsafe-baseline.json next to your .blend "
                            "(it never changes the .blend itself).")]
        return [mk(Status.UNKNOWN,
                   "The settings baseline file couldn't be read (%s)." % reason,
                   hint="Re-save it with Save Baseline, or delete the file.")]

    # Guard against comparing to a baseline that isn't this scene's: a newer/
    # unknown schema, or a baseline file copied in from a different .blend. Either
    # way we can't trust an identity match, so it's "Couldn't verify", not Pass.
    if not bl.schema_ok(data):
        return [mk(Status.UNKNOWN,
                   "The baseline was written by a different version of Failsafe "
                   "(schema %s), so it can't be compared safely."
                   % data.get("schema"),
                   hint="Click Save Baseline again to write a fresh one.")]
    foreign = bl.foreign_file_name(data, bpy.data.filepath)
    if foreign:
        return [mk(Status.UNKNOWN,
                   "This baseline was saved for a different file ('%s'), so its "
                   "settings don't necessarily describe this scene." % foreign,
                   hint="Click Save Baseline to record a baseline for this file.")]

    saved = data.get("fingerprints", {})
    out = []
    matched = 0

    # If two simulations collided onto one identity (e.g. an ambiguous name),
    # a complete comparison isn't possible — report "Couldn't verify", never a
    # PASS that could hide a changed sim. (R21)
    ambig = set(bl.ambiguities(current)) | set(bl.ambiguities(saved))
    for ident in sorted(ambig):
        out.append(mk(Status.UNKNOWN,
                      "%s matches more than one simulation, so its settings "
                      "can't be compared reliably." % ident.replace("::", " — "),
                      hint="Give the simulations distinct names, then click Save "
                           "Baseline again."))

    saved_sims = dict(bl.sim_items(saved))
    for ident, cur in bl.sim_items(current):
        nice = ident.replace("::", " — ")
        # identity is Scene::Owner::System[::Sub]; the object is field [1].
        parts = ident.split("::")
        obj_name = None if cur.get("kind") == "rbw" else (
            parts[1] if len(parts) > 1 else None)
        if ident not in saved_sims:
            out.append(mk(Status.UNKNOWN,
                          "%s isn't in the baseline (added or renamed after it "
                          "was saved), so its settings can't be compared." % nice,
                          object_name=obj_name,
                          hint="Click Save Baseline again after baking to "
                               "include it."))
            continue
        changed = bl.diff_fingerprint(saved_sims[ident], cur)
        if changed:
            preview = ", ".join(changed[:6])
            if len(changed) > 6:
                preview += ", …"
            out.append(mk(Status.WARNING,
                          "%s: settings changed since the baseline (%s). If you "
                          "changed these after baking, the cache may no longer "
                          "match — re-bake." % (nice, preview),
                          object_name=obj_name,
                          hint="Re-bake, then click Save Baseline to update the "
                               "reference."))
        else:
            matched += 1
    current_sims = dict(bl.sim_items(current))
    for ident in saved_sims:
        if ident not in current_sims:
            out.append(mk(Status.UNKNOWN,
                          "%s is in the baseline but not in the scene now."
                          % ident.replace("::", " — "),
                          hint="Update the baseline if you meant to remove it."))
    if not out and matched:
        return [mk(Status.PASS,
                   "The tracked settings of all %d simulation%s are unchanged "
                   "since the baseline was saved. (Failsafe compares a curated set "
                   "of key settings, not every property, and this is not proof the "
                   "bake itself is good.)"
                   % (matched, "" if matched == 1 else "s"))]
    return out
