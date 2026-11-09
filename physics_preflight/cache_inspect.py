# SPDX-License-Identifier: GPL-3.0-or-later
"""File-level simulation-cache inspection.

This is the part Blender's own API gets wrong (Phase 0, PHASE0_REPORT.md §3b):
for Cloth, Soft Body and Fluid, ``is_baked`` / ``has_cache_baked_*`` stay True
after the cache files have been deleted. So we never trust those flags as proof
of a cache — we look at the actual files on disk.

Filename schemes proven on official Blender 4.2.23 / 4.5.15 / 5.0.1 / 5.2.3:
  * Point cache (Cloth, Soft Body, Particles), disk mode:
        blendcache_<blendbasename>/<HEX(name)>_<frame:06d>_<index:02d>.bphys
    where HEX(name) is the ASCII/UTF-8 bytes of the cache name (or, when the
    cache name is empty, the object name) as uppercase hex. Example: object
    "Plane" -> 506C616E65.
  * Fluid (Mantaflow) "All" bake:
        <cache_directory>/config/config_NNNN.uni
        <cache_directory>/data/fluid_data_NNNN.vdb  (+ mesh/ noise/ particles/)
    Fluid "Replay" is a playback cache, not a bake (only frame 1 written).
  * Geometry Nodes simulation zone, disk bake:
        <bake_directory>/<bake_id>/meta/NNNNN_II.json  (+ blobs/)
    Geometry Nodes *packed* bakes (4.3+) are invisible to Python -> UNKNOWN.
"""
import os
import re
import bpy

from .engine import Status


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


def _inside_blend_dir(abspath):
    d = blend_dir()
    if not d or not abspath:
        return None
    try:
        return os.path.commonpath([os.path.normpath(abspath), d]) == d
    except Exception:
        return None


def _portability(raw):
    """Classify a cache path as portable (lives inside the project) or not.

    Returns (portable: True/False/None, note). We resolve the real location
    rather than trusting the ``//`` prefix: Blender's save-time relative remap
    turns an outside absolute path into ``//../..`` which still points outside
    the project and must be flagged.
    """
    if not raw:
        return (None, "")
    is_abs = not raw.startswith("//")
    absdir = _abspath(raw)
    inside = _inside_blend_dir(absdir)
    if inside is None:
        # No saved .blend to resolve against.
        if is_abs:
            return (False, "absolute cache path")
        return (None, "")
    if not inside:
        return (False, "outside the project folder")
    return (True, "")


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
        self.frames_expected = None       # list[int] or None
        self.frames_present = set()
        self.frames_empty = set()         # present but 0 bytes
        self.external = False
        self.portable = None              # True/False/None
        self.path_note = ""
        self.replay = False               # fluid replay mode
        self.identity = None              # for duplicate-location detection (#21)
        self.time_scale = None            # rbw time scale, for #23


# --------------------------------------------------------- point caches -----

def _point_cache_dir_and_prefix(obj, pc):
    """Return (abs_cache_dir, filename_prefix, external, raw_path)."""
    name = pc.name if getattr(pc, "name", "") else obj.name
    prefix = _hex_name(name)
    external = bool(getattr(pc, "use_external", False))
    raw = getattr(pc, "filepath", "") or ""
    if external and raw:
        d = _abspath(raw)
        return d, prefix, True, raw
    base = blend_basename()
    bdir = blend_dir()
    if not base or not bdir:
        return None, prefix, external, raw
    return os.path.join(bdir, "blendcache_" + base), prefix, external, raw


def _scan_point_cache_files(cache_dir, prefix, index, frames):
    present, empty = set(), set()
    if not cache_dir or not os.path.isdir(cache_dir):
        return present, empty
    for fr in frames:
        fn = "%s_%06d_%02d.bphys" % (prefix, fr, index)
        p = os.path.join(cache_dir, fn)
        if os.path.isfile(p):
            present.add(fr)
            try:
                if os.path.getsize(p) == 0:
                    empty.add(fr)
            except OSError:
                pass
    return present, empty


def inspect_point_cache(obj, system, pc, scene):
    e = CacheEntry(obj.name, system, "point")
    e.baked_flag = bool(getattr(pc, "is_baked", False))
    e.scene_range = (scene.frame_start, scene.frame_end)
    cs = int(getattr(pc, "frame_start", scene.frame_start))
    ce = int(getattr(pc, "frame_end", scene.frame_end))
    e.cache_range = (cs, ce)
    e.uses_disk = bool(getattr(pc, "use_disk_cache", False))
    e.external = bool(getattr(pc, "use_external", False))

    cache_dir, prefix, external, raw = _point_cache_dir_and_prefix(obj, pc)
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

    if not e.uses_disk:
        # Memory cache: lives inside the .blend, no files to verify.
        e.file_check_applicable = False
        e.path_note = e.path_note or "cache is stored in the .blend (memory cache)"
        return e

    e.file_check_applicable = blend_is_saved() or e.external
    step = int(getattr(pc, "frame_step", 1) or 1)
    e.frames_expected = list(range(cs, ce + 1, step))
    e.frames_present, e.frames_empty = _scan_point_cache_files(
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
    e.file_check_applicable = False
    e.portable = True
    e.time_scale = float(getattr(rbw, "time_scale", 1.0))
    e.path_note = "stored in the .blend (no disk cache)"
    return e


# ------------------------------------------------------------- fluid --------

_FRAME_RE = re.compile(r"_(\d{4})\.")


def _scan_fluid_frames(data_dir):
    present, empty = set(), set()
    if not data_dir or not os.path.isdir(data_dir):
        return present, empty
    for fn in os.listdir(data_dir):
        m = _FRAME_RE.search(fn)
        if not m:
            continue
        fr = int(m.group(1))
        present.add(fr)
        try:
            if os.path.getsize(os.path.join(data_dir, fn)) == 0:
                empty.add(fr)
        except OSError:
            pass
    return present, empty


def inspect_fluid_domain(obj, mod, scene):
    ds = mod.domain_settings
    e = CacheEntry(obj.name, "Fluid", "fluid")
    e.baked_flag = bool(getattr(ds, "has_cache_baked_data", False))
    e.scene_range = (scene.frame_start, scene.frame_end)
    cs = int(getattr(ds, "cache_frame_start", scene.frame_start))
    ce = int(getattr(ds, "cache_frame_end", scene.frame_end))
    e.cache_range = (cs, ce)
    e.replay = (getattr(ds, "cache_type", "") == "REPLAY")
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

    if e.cache_dir:
        data_dir = os.path.join(e.cache_dir, "data")
        e.frames_present, e.frames_empty = _scan_fluid_frames(data_dir)
        if not e.frames_present:
            # fall back to the config folder (replay writes config only)
            e.frames_present, e.frames_empty = _scan_fluid_frames(
                os.path.join(e.cache_dir, "config"))
    e.frames_expected = list(range(cs, ce + 1))
    return e


# -------------------------------------------------- geometry nodes ----------

def inspect_gn_bakes(obj, mod, scene):
    """Yield a CacheEntry per Geometry Nodes simulation bake on the modifier."""
    out = []
    bakes = list(getattr(mod, "bakes", []) or [])
    if not bakes:
        return out
    target = getattr(mod, "bake_target", None)
    raw = getattr(mod, "bake_directory", "") or ""
    for b in bakes:
        e = CacheEntry(obj.name, "Geometry Nodes", "gn")
        e.scene_range = (scene.frame_start, scene.frame_end)
        bt = getattr(b, "bake_target", None) or target
        if bt == "PACKED":
            # Packed GN bakes leave no Python-visible trace (Phase 0 §3b).
            e.baked_determinable = False
            e.baked_flag = None
            e.file_check_applicable = False
            e.path_note = "packed Geometry Nodes bake (not visible to Python)"
            out.append(e)
            continue
        # Disk bake
        e.uses_disk = True
        e.raw_path = raw
        base_dir = _abspath(raw) if raw else None
        bake_id = getattr(b, "bake_id", None)
        bdir = os.path.join(base_dir, str(bake_id)) if (base_dir and bake_id is not None) else None
        e.cache_dir = bdir
        e.identity = ("gn", bdir)
        e.file_check_applicable = blend_is_saved() and bool(bdir)
        # portability
        e.portable, note = _portability(raw)
        if note:
            e.path_note = "Geometry Nodes bake is " + note
        present, empty = set(), set()
        if bdir:
            meta = os.path.join(bdir, "meta")
            if os.path.isdir(meta):
                for fn in os.listdir(meta):
                    m = re.match(r"(\d{5,})_\d+\.json", fn)
                    if m:
                        fr = int(m.group(1))
                        present.add(fr)
                        try:
                            if os.path.getsize(os.path.join(meta, fn)) == 0:
                                empty.add(fr)
                        except OSError:
                            pass
        e.frames_present, e.frames_empty = present, empty
        e.baked_flag = bool(present) if e.file_check_applicable else None
        # GN bakes cover the whole scene frame range by design.
        e.cache_range = (scene.frame_start, scene.frame_end)
        e.frames_expected = (list(range(scene.frame_start, scene.frame_end + 1))
                             if e.file_check_applicable else None)
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
                        e = inspect_point_cache(obj, "Particles", pc, scene)
                        # particle cache uses the object-name hex too
                        entries.append(e)
    rbw = inspect_rigidbody_world(scene)
    if rbw is not None and scene_has_rigid_bodies(scene):
        entries.append(rbw)
    return entries


def scene_has_rigid_bodies(scene):
    for o in scene.objects:
        if getattr(o, "rigid_body", None) is not None:
            return True
    return False
