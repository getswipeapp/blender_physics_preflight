# SPDX-License-Identifier: GPL-3.0-or-later
"""File-level simulation-cache inspection.

This is the part Blender's own API gets wrong (Phase 0, PHASE0_REPORT.md §3b):
for Cloth, Soft Body and Fluid, ``is_baked`` / ``has_cache_baked_*`` stay True
after the cache files have been deleted. So we never trust those flags as proof
of a cache — we look at the actual files on disk.

The completeness of a cache is decided in ONE place, ``cache_status()``, which
compares the files on disk against the *entire* required frame range. Checks
#17–#20 all read that single verdict, so they can never contradict each other
(e.g. #18 saying "files present" while a trailing frame is missing).

Filename schemes proven on official Blender 4.2.23 / 4.5.15 / 5.0.1 / 5.2.3:
  * Point cache (Cloth, Soft Body, Particles), disk mode:
        blendcache_<blendbasename>/<HEX(name)>_<frame:06d>_<index:02d>.bphys
    where HEX(name) is the ASCII/UTF-8 bytes of the cache name (or, when the
    cache name is empty, the object name) as uppercase hex. Example: object
    "Plane" -> 506C616E65.
  * Fluid (Mantaflow) bake:
        <cache_directory>/data/fluid_data_NNNN.{uni,vdb}
        <cache_directory>/config/config_NNNN.uni
        (+ mesh/ noise/ particles/ when those features are enabled)
    Fluid "Replay" is a playback cache, not a bake (only frame 1 written).
  * Geometry Nodes simulation zone, disk bake:
        <bake_directory>/<bake_id>/meta/NNNNN_II.json  (+ blobs/)
    Geometry Nodes *packed* bakes (4.3+) are invisible to Python -> UNKNOWN.
"""
import os
import re
import collections

import bpy

from .engine import Status


# --------------------------------------------------------- path helpers -----

def blend_is_saved():
    return bool(bpy.data.filepath)


def blend_dir():
    return os.path.dirname(bpy.path.abspath(bpy.data.filepath)) if blend_is_saved() else None


def blend_basename():
    if not blend_is_saved():
        return None
    return os.path.splitext(os.path.basename(bpy.data.filepath))[0]


def _hex_name(name):
    return "".join("%02X" % b for b in name.encode("utf-8"))


def _abspath(path):
    try:
        return os.path.normpath(bpy.path.abspath(path))
    except Exception:
        return path


def _realpath(path):
    """Resolve symlinks too, so a link pointing outside the project is caught."""
    try:
        return os.path.realpath(bpy.path.abspath(path))
    except Exception:
        return _abspath(path)


def _inside_blend_dir(path):
    d = blend_dir()
    if not d or not path:
        return None
    try:
        d_real = os.path.realpath(d)
        p_real = os.path.realpath(path)
        return os.path.commonpath([p_real, d_real]) == d_real
    except Exception:
        return None


def _portability(raw):
    """Classify a cache path. Returns (portable: True/False/None, note).

    A path is portable only when it is written relative (``//``) AND resolves
    to a location inside the project folder. An *absolute* path is never
    portable even when it currently points inside the project, because the
    absolute root differs on another machine. Symlinks are resolved first so a
    link that escapes the project is caught.
    """
    if not raw:
        return (None, "")
    is_relative = raw.startswith("//")
    inside = _inside_blend_dir(_realpath(raw))
    if not is_relative:
        # Absolute path: breaks on another machine regardless of where it
        # currently resolves.
        return (False, "absolute cache path")
    if inside is None:
        # No saved .blend to resolve against; can't be sure.
        return (None, "")
    if not inside:
        return (False, "resolves outside the project folder")
    return (True, "")


# ------------------------------------------------------------ data model ----

class CacheEntry:
    """One inspected simulation cache. Fields are filled best-effort; anything
    that cannot be determined is left None and surfaces as UNKNOWN."""

    def __init__(self, obj_name, system, kind):
        self.obj_name = obj_name
        self.system = system              # human label, e.g. "Cloth"
        self.kind = kind                  # point / fluid / rbw / gn
        self.baked_flag = None            # Blender's own flag (untrusted)
        self.baked_determinable = True    # False for GN packed bakes
        self.uses_disk = None             # True/False/None(memory or NA)
        self.file_check_applicable = False
        self.cache_dir = None             # absolute dir we scan
        self.raw_path = None              # the path as the user set it ("//..")
        self.scene_range = None           # (s, e)
        self.cache_range = None           # (s, e) or None
        self.frames_expected = None       # list[int]: the FULL required set
        self.frames_present = set()
        self.frames_empty = set()         # present but 0 bytes
        self.frames_unreadable = set()    # present but os.stat raised
        self.sampled = False              # frame_step > 1 (intentionally sparse)
        self.frame_step = 1
        self.external = False
        self.portable = None              # True/False/None
        self.path_note = ""
        self.replay = False               # fluid replay mode
        self.identity = None              # for duplicate-location detection (#21)
        self.time_scale = None            # rbw time scale, for #23
        self.components_missing = []      # fluid sub-caches not found (mesh/noise)
        self.memory = False               # cache lives inside the .blend
        self.certifiable = True           # False: files visible but integrity
        #                                   can't be proven (GN disk blob data)
        self.cache_frame_offset = 0       # fluid playback offset (R12)
        self.cache_outdated = None        # point cache is_outdated (R14)
        self.frame_skip = None            # point cache is_frame_skip (R15)
        self.baking_in_progress = False   # a bake is mid-flight (R16 test #4)


# The single authoritative verdict every cache check reads from.
CacheVerdict = collections.namedtuple(
    "CacheVerdict", "state missing empty unreadable present required note")

# verdict states
V_COMPLETE = "COMPLETE"        # every required frame present and readable
V_INCOMPLETE = "INCOMPLETE"    # some required frames missing (head/mid/tail)
V_EMPTY = "EMPTY"              # no files at all
V_CORRUPT = "CORRUPT"          # present but 0-byte frames
V_UNREADABLE = "UNREADABLE"    # present but could not be read/stat'd
V_UNVERIFIABLE = "UNVERIFIABLE"  # can't check (unsaved, unresolved, packed)
V_NOT_BAKED = "NOT_BAKED"      # not baked and no files
V_REPLAY = "REPLAY"            # fluid replay (never a real bake)
V_MEMORY = "MEMORY"           # stored in the .blend, no disk files
V_NA = "NA"


def cache_status(e):
    """Decide a single, authoritative verdict for a CacheEntry by comparing the
    files on disk against the ENTIRE required frame range. All of checks
    #17–#20 derive from this, so they stay consistent."""
    if e.kind == "rbw" or e.memory:
        return CacheVerdict(V_MEMORY, [], [], [], set(), set(), e.path_note)
    if e.replay:
        return CacheVerdict(V_REPLAY, [], [], [], e.frames_present, set(), "")
    if not e.baked_determinable:
        return CacheVerdict(V_UNVERIFIABLE, [], [], [], set(), set(),
                            "packed bake (not visible to Python)")
    if not e.file_check_applicable or e.cache_dir is None:
        return CacheVerdict(V_UNVERIFIABLE, [], [], [], set(), set(),
                            e.path_note or "cache location can't be verified")

    required = set(e.frames_expected or [])
    present = set(e.frames_present or [])     # every file that exists on disk
    empty = set(e.frames_empty or [])         # exists but 0-byte
    unreadable = set(e.frames_unreadable or [])  # exists but couldn't be read
    if not required:
        return CacheVerdict(V_UNVERIFIABLE, [], [], [], present, required,
                            "cache frame range is empty")

    # Truly absent files (the F01 case: a deleted head/mid/tail frame).
    missing = sorted(required - present)

    if not present:
        state = V_EMPTY if e.baked_flag else V_NOT_BAKED
        return CacheVerdict(state, missing, [], [], present, required, "")
    # Precedence: absent frames (clear FAIL) -> corrupt 0-byte -> missing
    # sub-cache -> unreadable (can't verify, UNKNOWN) -> complete.
    if missing:
        return CacheVerdict(V_INCOMPLETE, missing, sorted(empty), sorted(unreadable),
                            present, required, "")
    if empty:
        return CacheVerdict(V_CORRUPT, missing, sorted(empty), sorted(unreadable),
                            present, required, "")
    if e.components_missing:
        return CacheVerdict(V_INCOMPLETE, missing, [], sorted(unreadable),
                            present, required,
                            "missing sub-cache: " + ", ".join(e.components_missing))
    if unreadable:
        return CacheVerdict(V_UNREADABLE, [], [], sorted(unreadable),
                            present, required, "")
    if not getattr(e, "certifiable", True):
        # Files cover the range, but we can't prove the referenced internal data
        # is intact (GN disk bakes reference blob files we can't validate from
        # Python). Honest answer: UNKNOWN, never a confident COMPLETE. (R09)
        return CacheVerdict(V_UNVERIFIABLE, [], [], [], present, required,
                            "bake files are present but their internal data "
                            "can't be fully verified")
    # Every required file is on disk — but Blender itself may signal the cache
    # is not a trustworthy finished bake. Each of these is an INDEPENDENT reason
    # to withhold a confident PASS (R14/R15): a skipped-frame cache is suspect
    # even when it isn't marked outdated, and vice-versa. Report UNKNOWN, never
    # a green tick. (Downgrade-only — a True "baked" flag is still distrusted.)
    baking = getattr(e, "baking_in_progress", False)
    outdated = getattr(e, "cache_outdated", False)
    skipped = getattr(e, "frame_skip", False)
    if baking or outdated or skipped:
        reasons = []
        if baking:
            reasons.append("a bake is still in progress")
        if outdated:
            reasons.append("the simulation settings changed since it was baked")
        if skipped:
            reasons.append("frames were skipped during baking")
        note = ("Blender flags this cache as not a reliable finished bake — "
                + "; ".join(reasons))
        return CacheVerdict(V_UNVERIFIABLE, [], [], [], present, required, note)
    return CacheVerdict(V_COMPLETE, [], [], [], present, required, "")


# --------------------------------------------------------- point caches -----

def _point_cache_dir_and_prefix(obj, pc, external):
    """Return (abs_cache_dir, filename_prefix, raw_path)."""
    name = pc.name if getattr(pc, "name", "") else obj.name
    prefix = _hex_name(name)
    raw = getattr(pc, "filepath", "") or ""
    if external and raw:
        return _abspath(raw), prefix, raw
    base = blend_basename()
    bdir = blend_dir()
    if not base or not bdir:
        return None, prefix, raw
    return os.path.join(bdir, "blendcache_" + base), prefix, raw


def _file_state(path):
    """Classify an existing file: 'ok' | 'empty' | 'unreadable'. Actually opens
    the file for a byte, so a non-zero size that Blender can't read still counts
    as unreadable rather than a silent pass."""
    try:
        if os.path.getsize(path) == 0:
            return "empty"
    except OSError:
        return "unreadable"
    try:
        with open(path, "rb") as fh:
            fh.read(1)
    except OSError:
        return "unreadable"
    return "ok"


def _scan_point_cache_files(cache_dir, prefix, index, frames):
    present, empty, unreadable = set(), set(), set()
    if not cache_dir or not os.path.isdir(cache_dir):
        return present, empty, unreadable
    for fr in frames:
        fn = "%s_%06d_%02d.bphys" % (prefix, fr, index)
        p = os.path.join(cache_dir, fn)
        if os.path.isfile(p):
            present.add(fr)
            st = _file_state(p)
            if st == "empty":
                empty.add(fr)
            elif st == "unreadable":
                unreadable.add(fr)
    return present, empty, unreadable


def inspect_point_cache(obj, system, pc, scene):
    e = CacheEntry(obj.name, system, "point")
    e.baked_flag = bool(getattr(pc, "is_baked", False))
    # Blender's own staleness bits. is_outdated means the sim settings changed
    # since the bake; is_frame_skip means frames were skipped. Used only to
    # DOWNGRADE a verdict (never to upgrade), since a True baked flag is the one
    # we distrust. (R14)
    e.cache_outdated = bool(getattr(pc, "is_outdated", False))
    e.frame_skip = bool(getattr(pc, "is_frame_skip", False))
    e.baking_in_progress = bool(getattr(pc, "is_baking", False))
    e.scene_range = (scene.frame_start, scene.frame_end)
    cs = int(getattr(pc, "frame_start", scene.frame_start))
    ce = int(getattr(pc, "frame_end", scene.frame_end))
    e.cache_range = (cs, ce)
    e.external = bool(getattr(pc, "use_external", False))
    use_disk = bool(getattr(pc, "use_disk_cache", False))
    # An external cache lives in files on disk even when "Disk Cache" (which only
    # controls *writing*) is off. Treat either as disk-backed. (F05)
    disk_backed = use_disk or e.external
    e.uses_disk = disk_backed

    cache_dir, prefix, raw = _point_cache_dir_and_prefix(obj, pc, e.external)
    e.cache_dir = cache_dir
    e.raw_path = raw
    e.identity = ("point", cache_dir, prefix, int(getattr(pc, "index", 0)))

    # portability
    if e.external:
        e.portable, note = _portability(raw)
        if getattr(pc, "use_library_path", False):
            e.path_note = "cache follows a linked library path"
        elif note:
            e.path_note = "external cache is " + note
    else:
        e.portable = True  # default blendcache lives next to the .blend

    if not disk_backed:
        # Memory cache: lives inside the .blend, no files to verify.
        e.memory = True
        e.file_check_applicable = False
        e.path_note = e.path_note or "cache is stored in the .blend (memory cache)"
        return e

    e.file_check_applicable = blend_is_saved() or e.external
    step = int(getattr(pc, "frame_step", 1) or 1)
    e.frame_step = step
    e.sampled = step > 1
    e.frames_expected = list(range(cs, ce + 1, step))
    e.frames_present, e.frames_empty, e.frames_unreadable = _scan_point_cache_files(
        cache_dir, prefix, int(getattr(pc, "index", 0)), e.frames_expected)
    return e


# --------------------------------------------------------- rigid body -------

def inspect_rigidbody_world(scene):
    rbw = scene.rigidbody_world
    if rbw is None:
        return None
    e = CacheEntry("Rigid Body World", "Rigid Body World", "rbw")
    pc = rbw.point_cache
    e.baked_flag = bool(getattr(pc, "is_baked", False))
    e.scene_range = (scene.frame_start, scene.frame_end)
    e.cache_range = (int(getattr(pc, "frame_start", scene.frame_start)),
                     int(getattr(pc, "frame_end", scene.frame_end)))
    e.uses_disk = None            # memory-only cache stored in the .blend
    e.memory = True
    e.file_check_applicable = False
    e.portable = True
    e.time_scale = float(getattr(rbw, "time_scale", 1.0))
    e.path_note = "stored in the .blend (no disk cache)"
    return e


# ------------------------------------------------------------- fluid --------

# Each Mantaflow sub-cache has a COMPONENT-SPECIFIC filename, verified against
# real 5.2.3 bakes: fluid_data_NNNN.vdb, fluid_mesh_NNNN.bobj.gz,
# fluid_noise_NNNN.vdb, fluid_particles_NNNN.vdb. Matching per component stops a
# file from one component (e.g. a data file sitting in mesh/) from being counted
# as another component's frame (R10).
_FLUID_COMPONENT_RE = {
    "data": re.compile(r"^fluid_data_(\d{4})\.(vdb|uni|raw)$", re.IGNORECASE),
    "mesh": re.compile(r"^fluid_mesh_(\d{4})\.(bobj\.gz|bobj|vdb)$", re.IGNORECASE),
    "noise": re.compile(r"^fluid_noise_(\d{4})\.(vdb|uni|raw)$", re.IGNORECASE),
    "particles": re.compile(r"^fluid_particles_(\d{4})\.(vdb|uni|raw)$", re.IGNORECASE),
    # Guiding sub-cache: verified against a real 5.2.3 guide bake — directory
    # "guiding/", files fluid_guiding_NNNN.vdb (same prefix scheme as the rest,
    # confirmed by probe rather than assumed). (R16)
    "guiding": re.compile(r"^fluid_guiding_(\d{4})\.(vdb|uni|raw)$", re.IGNORECASE),
    # Mantaflow writes one solver-config file per frame (config/config_NNNN.uni,
    # verified on real 5.2.3 bakes). A complete bake always includes these; if
    # they go missing the cache can't be reloaded for render, so config is a
    # REQUIRED component, not an optional sub-cache (R11).
    "config": re.compile(r"^config_(\d{4})\.uni$", re.IGNORECASE),
}

# Which fluid sub-cache maps to which per-stage "baked" flag. An enabled stage
# whose flag is OFF is not a valid bake even if stale files remain (R13).
_FLUID_STAGE_FLAG = {
    "mesh": "has_cache_baked_mesh",
    "noise": "has_cache_baked_noise",
    "particles": "has_cache_baked_particles",
    "guiding": "has_cache_baked_guide",
}

# Fluid "bake in progress" flags. A scan while any of these is True caught a
# half-written cache, so we never certify it COMPLETE (R16 test #4).
_FLUID_BAKING_FLAGS = (
    "is_cache_baking_data", "is_cache_baking_mesh", "is_cache_baking_noise",
    "is_cache_baking_particles", "is_cache_baking_guide")


def _scan_fluid_dir(data_dir, component):
    """Scan one Mantaflow sub-cache directory for THAT component's files only.
    Returns (present, empty, unreadable)."""
    present, empty, unreadable = set(), set(), set()
    rx = _FLUID_COMPONENT_RE.get(component)
    if rx is None or not data_dir or not os.path.isdir(data_dir):
        return present, empty, unreadable
    for fn in os.listdir(data_dir):
        m = rx.match(fn)
        if not m:
            continue
        fr = int(m.group(1))
        present.add(fr)
        st = _file_state(os.path.join(data_dir, fn))
        if st == "empty":
            empty.add(fr)
        elif st == "unreadable":
            unreadable.add(fr)
    return present, empty, unreadable


def inspect_fluid_domain(obj, mod, scene):
    ds = mod.domain_settings
    e = CacheEntry(obj.name, "Fluid", "fluid")
    e.baked_flag = bool(getattr(ds, "has_cache_baked_data", False))
    e.scene_range = (scene.frame_start, scene.frame_end)
    cs = int(getattr(ds, "cache_frame_start", scene.frame_start))
    ce = int(getattr(ds, "cache_frame_end", scene.frame_end))
    e.cache_range = (cs, ce)
    e.replay = (getattr(ds, "cache_type", "") == "REPLAY")
    e.cache_frame_offset = int(getattr(ds, "cache_frame_offset", 0) or 0)  # R12
    # If any sub-cache is mid-bake, the files on disk are not a finished bake.
    e.baking_in_progress = any(bool(getattr(ds, a, False))
                               for a in _FLUID_BAKING_FLAGS)  # R16 test #4
    raw = getattr(ds, "cache_directory", "") or ""
    e.raw_path = raw
    e.cache_dir = _abspath(raw) if raw else None
    e.identity = ("fluid", e.cache_dir)
    e.uses_disk = True
    e.file_check_applicable = blend_is_saved() and bool(e.cache_dir)

    # portability
    e.portable, note = _portability(raw)
    if note:
        e.path_note = "fluid cache is " + note

    e.frames_expected = list(range(cs, ce + 1))
    required = set(e.frames_expected)

    if e.cache_dir and e.file_check_applicable and not e.replay:
        data_present, data_empty, data_unread = _scan_fluid_dir(
            os.path.join(e.cache_dir, "data"), "data")
        e.frames_present = data_present
        e.frames_empty = data_empty
        e.frames_unreadable = data_unread
        # Each required sub-cache must cover the SAME frames, not merely "have at
        # least one file". A sub-cache missing frames makes the whole bake
        # incomplete (R01). config/ is required on every bake (R11); mesh/noise/
        # particles only when their feature is enabled.
        use_particles = any(bool(getattr(ds, a, False)) for a in (
            "use_spray_particles", "use_foam_particles",
            "use_bubble_particles", "use_tracer_particles"))
        components = [
            ("config", True),
            ("mesh", bool(getattr(ds, "use_mesh", False))),
            ("noise", bool(getattr(ds, "use_noise", False))),
            ("particles", use_particles),
            ("guiding", bool(getattr(ds, "use_guide", False))),  # R16
        ]
        for comp_name, enabled in components:
            if not enabled:
                continue
            # R13: an enabled stage whose own baked flag is OFF is not a valid
            # bake, even if stale files from an earlier bake still sit in its
            # folder. Flag it rather than counting those files as coverage.
            flag_attr = _FLUID_STAGE_FLAG.get(comp_name)
            if flag_attr is not None and not bool(getattr(ds, flag_attr, True)):
                e.components_missing.append("%s (stage not baked)" % comp_name)
                continue
            cp, ce_empty, cu = _scan_fluid_dir(
                os.path.join(e.cache_dir, comp_name), comp_name)
            gap = required - cp
            if gap:
                e.components_missing.append(
                    "%s (missing %d frame%s)"
                    % (comp_name, len(gap), "" if len(gap) == 1 else "s"))
            # a 0-byte/unreadable sub-cache frame is also a defect
            e.frames_empty |= (ce_empty & data_present)
            e.frames_unreadable |= (cu & data_present)
    return e


# -------------------------------------------------- geometry nodes ----------

def _resolve_gn_target(bake, mod):
    """Resolve a bake's effective storage target, following INHERIT to the
    modifier's own setting. Returns an upper-case string or '' if unknown."""
    bt = getattr(bake, "bake_target", None)
    if not bt or bt == "INHERIT":
        bt = getattr(mod, "bake_target", None)
    return (bt or "").upper()


def _gn_bake_range(bake, scene):
    """Effective frame range for one GN bake. The custom *path* and custom
    *frame range* are independent toggles — only a custom frame range (or a
    still-frame bake) changes the range (R07)."""
    if getattr(bake, "bake_mode", "ANIMATION") == "STILL":
        f = int(getattr(bake, "frame_start", scene.frame_start))
        return (f, f)
    if bool(getattr(bake, "use_custom_simulation_frame_range", False)):
        return (int(getattr(bake, "frame_start", scene.frame_start)),
                int(getattr(bake, "frame_end", scene.frame_end)))
    return (scene.frame_start, scene.frame_end)


def inspect_gn_bakes(obj, mod, scene):
    """Yield a CacheEntry per Geometry Nodes simulation bake on the modifier."""
    out = []
    bakes = list(getattr(mod, "bakes", []) or [])
    if not bakes:
        return out
    mod_raw = getattr(mod, "bake_directory", "") or ""
    for b in bakes:
        e = CacheEntry(obj.name, "Geometry Nodes", "gn")
        e.scene_range = (scene.frame_start, scene.frame_end)
        target = _resolve_gn_target(b, mod)
        if target != "DISK":
            # PACKED (or an unrecognised/inherited-packed target) leaves no
            # Python-visible files. Phase 0 §3b: report UNKNOWN, never guess.
            e.baked_determinable = False
            e.baked_flag = None
            e.file_check_applicable = False
            e.path_note = ("packed Geometry Nodes bake (not visible to Python)"
                           if target in ("PACKED", "") else
                           "Geometry Nodes bake target '%s'" % target.title())
            out.append(e)
            continue
        # Disk bake. Honour a per-bake custom directory and frame range.
        use_custom = bool(getattr(b, "use_custom_path", False))
        raw = (getattr(b, "directory", "") or mod_raw) if use_custom else mod_raw
        e.uses_disk = True
        # We can see the meta frames and that blobs/ exists, but not prove the
        # referenced blob data is intact -> never certify COMPLETE (R09).
        e.certifiable = False
        e.raw_path = raw
        base_dir = _abspath(raw) if raw else None
        bake_id = getattr(b, "bake_id", None)
        bdir = os.path.join(base_dir, str(bake_id)) if (base_dir and bake_id is not None) else None
        e.cache_dir = bdir
        e.identity = ("gn", bdir)
        e.file_check_applicable = blend_is_saved() and bool(bdir)
        e.portable, note = _portability(raw)
        if note:
            e.path_note = "Geometry Nodes bake is " + note

        fs, fe = _gn_bake_range(b, scene)
        e.cache_range = (fs, fe)
        e.frames_expected = (list(range(fs, fe + 1)) if e.file_check_applicable else None)

        present, empty, unreadable = set(), set(), set()
        if bdir:
            meta = os.path.join(bdir, "meta")
            if os.path.isdir(meta):
                for fn in os.listdir(meta):
                    m = re.match(r"(\d{5,})_\d+\.json$", fn)
                    if m:
                        fr = int(m.group(1))
                        present.add(fr)
                        st = _file_state(os.path.join(meta, fn))
                        if st == "empty":
                            empty.add(fr)
                        elif st == "unreadable":
                            unreadable.add(fr)
            # The meta JSON is only an index; the real data lives in blobs/.
            # Metadata without blob data is a broken bake (R03).
            if present:
                blobs = os.path.join(bdir, "blobs")
                has_blobs = False
                if os.path.isdir(blobs):
                    try:
                        has_blobs = any(os.scandir(blobs))
                    except OSError:
                        has_blobs = False
                if not has_blobs:
                    e.components_missing.append("blob data")
        e.frames_present, e.frames_empty, e.frames_unreadable = present, empty, unreadable
        e.baked_flag = bool(present) if e.file_check_applicable else None
        out.append(e)
    return out


# -------------------------------------------------- top-level enumerator ----

def enumerate_caches(scene):
    """Return a list[CacheEntry] for every simulation cache in the scene."""
    entries = []
    for obj in scene.objects:
        for mod in obj.modifiers:
            if mod.type == "CLOTH":
                pc = getattr(mod, "point_cache", None)
                if pc is not None:
                    entries.append(inspect_point_cache(obj, "Cloth", pc, scene))
            elif mod.type == "SOFT_BODY":
                pc = getattr(mod, "point_cache", None)
                if pc is not None:
                    entries.append(inspect_point_cache(obj, "Soft Body", pc, scene))
            elif mod.type == "FLUID":
                if getattr(mod, "fluid_type", "") == "DOMAIN" and getattr(mod, "domain_settings", None):
                    entries.append(inspect_fluid_domain(obj, mod, scene))
            elif mod.type == "NODES":
                entries.extend(inspect_gn_bakes(obj, mod, scene))
        # Particle systems
        if obj.type == "MESH":
            for psys in obj.particle_systems:
                st = psys.settings
                if st is None:
                    continue
                if st.type == "EMITTER":
                    pc = getattr(psys, "point_cache", None)
                    if pc is not None:
                        entries.append(inspect_point_cache(obj, "Particles", pc, scene))
    rbw = inspect_rigidbody_world(scene)
    if rbw is not None and scene_has_rigid_bodies(scene):
        entries.append(rbw)
    return entries


def scene_has_rigid_bodies(scene):
    for o in scene.objects:
        if getattr(o, "rigid_body", None) is not None:
            return True
    return False
