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
  * Point cache (Cloth, Soft Body, Particles, Hair dynamics, Dynamic Paint
    vertex surfaces), disk mode:
        blendcache_<blendbasename>/<HEX(name)>_<frame:06d>_<index:02d>.bphys
    where HEX(name) is the ASCII/UTF-8 bytes of the cache name (or, when the
    cache name is empty, the object name) as uppercase hex. Example: object
    "Plane" -> 506C616E65. Verified on 5.2.3: a Dynamic Paint VERTEX surface and
    a hair system with ``use_hair_dynamics`` both write this exact scheme (the
    hex is of the owning object's name, the surface/system name being empty).
    A Dynamic Paint IMAGE surface bakes an image sequence instead (not a point
    cache); its frame contents aren't read yet, so it is surfaced as an explicit
    "Couldn't verify" (UNKNOWN) rather than silently skipped, while its output
    path is still checked for portability and cloud-sync risk.
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
import struct
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


# Folders a consumer cloud client continuously syncs. A live sim cache inside one
# is risky: the client can lock, partially upload, or re-download a frame file
# mid-render, or an offline-only placeholder can sit where a real frame should be.
# Match is on a whole path component, case-insensitively (A2, matches Cache
# Guardian's cloud-path warning).
_CLOUD_MARKERS = (
    ("dropbox", "Dropbox"),
    ("onedrive", "OneDrive"),
    ("google drive", "Google Drive"),
    ("googledrive", "Google Drive"),
    ("my drive", "Google Drive"),
    (".shortcut-targets-by-id", "Google Drive"),
    ("com~apple~clouddocs", "iCloud Drive"),
    ("mobile documents", "iCloud Drive"),
    ("icloud drive", "iCloud Drive"),
    ("pcloud", "pCloud"),
    ("nextcloud", "Nextcloud"),
    ("owncloud", "ownCloud"),
    ("sync.com", "Sync.com"),
    ("megasync", "MEGA"),
    ("box sync", "Box"),
)


def cloud_sync_marker(path):
    """Return the display name of a cloud-sync folder on ``path`` (a resolved
    absolute path), or None. Read-only — just inspects the string."""
    if not path:
        return None
    parts = [p.strip().lower() for p in os.path.normpath(path).split(os.sep)]
    whole = os.path.normpath(path).lower()
    for needle, label in _CLOUD_MARKERS:
        if needle in parts:
            return label
        # Some markers (e.g. "google drive", "com~apple~clouddocs") appear as a
        # component but may contain spaces/tildes the split keeps intact; also
        # allow a substring match for those multi-token names.
        if " " in needle or "~" in needle or "." in needle:
            if needle in whole:
                return label
    return None


def _dir_size(path):
    """Best-effort total size in bytes of files directly in ``path`` (one level).
    Read-only. Returns None if the directory can't be read."""
    if not path or not os.path.isdir(path):
        return None
    total = 0
    try:
        with os.scandir(path) as it:
            for de in it:
                try:
                    if de.is_file(follow_symlinks=False):
                        total += de.stat(follow_symlinks=False).st_size
                except OSError:
                    continue
    except OSError:
        return None
    return total


def _point_cache_bytes(cache_dir, prefix, index, frames_present):
    """Sum the on-disk size of the present point-cache frame files (A4)."""
    if not cache_dir or not os.path.isdir(cache_dir) or not frames_present:
        return None
    total = 0
    for fr in frames_present:
        fn = "%s_%06d_%02d.bphys" % (prefix, fr, index)
        p = os.path.join(cache_dir, fn)
        try:
            total += os.path.getsize(p)
        except OSError:
            continue
    return total


_BPHYS_RE = re.compile(r"^([0-9A-Fa-f]+)_(\d{6})_(\d{2})\.bphys$")


def default_blendcache_dir():
    """The ``blendcache_<file>`` folder next to a saved .blend, or None."""
    base = blend_basename()
    bdir = blend_dir()
    if not base or not bdir:
        return None
    return os.path.join(bdir, "blendcache_" + base)


def _point_cache_identity_for(obj, pc):
    """``(prefix.upper(), index)`` for a DEFAULT-location disk point cache, or
    None for a memory cache (no files) or an external/custom-dir cache (we don't
    police other folders)."""
    external = bool(getattr(pc, "use_external", False))
    use_disk = bool(getattr(pc, "use_disk_cache", False))
    if external or not use_disk:
        return None
    _, prefix, _ = _point_cache_dir_and_prefix(obj, pc, False)
    if not prefix:
        return None
    return (prefix.upper(), int(getattr(pc, "index", 0)))


def _iter_object_point_caches_named(obj):
    """Yield ``(system_label, sub_name, point_cache)`` for every point-cache-backed
    simulation on ``obj``: Cloth, Soft Body, emitter Particles, Hair dynamics,
    and Dynamic Paint *vertex* surfaces.

    This is the single source of truth shared by ``enumerate_caches`` (what the
    scanner reports on), ``owned_point_cache_identities`` (what the orphan check
    treats as live) and ``iter_point_cache_files`` (what the cache-hash baseline
    fingerprints). Routing them all through here means the orphan check (#25) can
    never flag a cache the scanner inspects, and the hash baseline can never key a
    sim differently from the scanner. Read-only.

    ``sub_name`` is the owning modifier / particle-system / surface name. It only
    disambiguates two sims on one object; it is NOT used to locate files (the
    on-disk prefix is the hex of the cache or object name), so it is safe for it to
    be a human label.

    Gating notes (verified on Blender 5.2.3):
      * Hair particle systems only have a sim cache when ``use_hair_dynamics`` is
        on — a static-hair system has no cache, so flagging it would be a false
        FAIL. (``use_hair_dynamics`` lives on the ParticleSystem, not its
        settings.)
      * Dynamic Paint stores a VERTEX surface in a standard ``.bphys`` point
        cache; an IMAGE surface bakes an image sequence instead and is not a
        point cache, so it is skipped here.
    """
    for mod in obj.modifiers:
        if mod.type == "CLOTH":
            pc = getattr(mod, "point_cache", None)
            if pc is not None:
                yield ("Cloth", mod.name, pc)
        elif mod.type == "SOFT_BODY":
            pc = getattr(mod, "point_cache", None)
            if pc is not None:
                yield ("Soft Body", mod.name, pc)
        elif mod.type == "DYNAMIC_PAINT":
            cs = getattr(mod, "canvas_settings", None)
            if cs is not None:
                for surf in getattr(cs, "canvas_surfaces", []) or []:
                    if getattr(surf, "surface_format", "") != "VERTEX":
                        continue
                    pc = getattr(surf, "point_cache", None)
                    if pc is not None:
                        yield ("Dynamic Paint", getattr(surf, "name", "") or mod.name, pc)
    if obj.type == "MESH":
        for psys in obj.particle_systems:
            st = psys.settings
            if st is None:
                continue
            if st.type == "EMITTER":
                pc = getattr(psys, "point_cache", None)
                if pc is not None:
                    yield ("Particles", psys.name, pc)
            elif st.type == "HAIR" and bool(getattr(psys, "use_hair_dynamics", False)):
                pc = getattr(psys, "point_cache", None)
                if pc is not None:
                    yield ("Hair Dynamics", psys.name, pc)


def _iter_object_point_caches(obj):
    """``(system_label, point_cache)`` for every point cache on ``obj``.

    Thin wrapper over :func:`_iter_object_point_caches_named` that drops the
    sub-name, for the callers (scanner, orphan check) that don't need it. Keeping
    one underlying walk means those callers and the hash baseline can never drift.
    """
    for system, _sub, pc in _iter_object_point_caches_named(obj):
        yield (system, pc)


def owned_point_cache_identities(scenes):
    """The ``(prefix, index)`` identity of every default-location disk point cache
    across ALL the given scenes. Using every scene (not just the active one) means
    a cache owned by another scene in the same .blend is never mistaken for an
    orphan. (R24)"""
    owned = set()
    for scene in scenes:
        for obj in scene.objects:
            for _system, pc in _iter_object_point_caches(obj):
                ident = _point_cache_identity_for(obj, pc)
                if ident is not None:
                    owned.add(ident)
    return owned


PointCacheFiles = collections.namedtuple(
    "PointCacheFiles",
    "identity system obj_name sub_name cache_dir files required")
# files:    list of (frame:int, index:int, abspath:str) for frames present on disk.
# required: list[int] of EVERY frame the cache range demands (range(cs, ce+1, step)),
#           present or not — so a hash verification can tell when a baseline covers
#           only part of the required range and must NOT report a clean PASS (B3).


def iter_point_cache_files(scenes):
    """Yield a :class:`PointCacheFiles` for every DISK-backed point cache across
    ``scenes`` (cloth, soft body, particles, hair dynamics, DP vertex surfaces).

    ``identity`` is the relocation-stable ``Scene::Owner::System::Sub`` string
    (object/sim NAMES, which don't change when a project folder moves), matching
    the settings-baseline identity scheme. ``files`` lists only the frames that
    actually exist on disk, each as ``(frame, index, abspath)``, reconstructed
    from the same ``<prefix>_<frame:06d>_<index:02d>.bphys`` scheme the scanner
    reads — so the cache-hash baseline and the scanner never disagree about which
    files a sim owns. Memory caches (no files) are skipped. Read-only."""
    for scene in scenes:
        for obj in scene.objects:
            for system, sub, pc in _iter_object_point_caches_named(obj):
                external = bool(getattr(pc, "use_external", False))
                disk = bool(getattr(pc, "use_disk_cache", False)) or external
                if not disk:
                    continue  # memory cache: nothing on disk to hash
                cache_dir, prefix, _raw = _point_cache_dir_and_prefix(
                    obj, pc, external)
                if not cache_dir:
                    continue
                index = int(getattr(pc, "index", 0) or 0)
                cs = int(getattr(pc, "frame_start", scene.frame_start))
                ce = int(getattr(pc, "frame_end", scene.frame_end))
                step = int(getattr(pc, "frame_step", 1) or 1)
                files = []
                required = list(range(cs, ce + 1, step))
                for fr in required:
                    p = os.path.join(
                        cache_dir, "%s_%06d_%02d.bphys" % (prefix, fr, index))
                    if os.path.isfile(p):
                        files.append((fr, index, p))
                identity = "%s::%s::%s::%s" % (scene.name, obj.name, system, sub)
                yield PointCacheFiles(identity, system, obj.name, sub,
                                      cache_dir, files, required)


def find_orphan_point_caches(scene, entries=None):
    """Find .bphys files in the project's ``blendcache_<file>`` folder that no
    point cache in **any scene of this .blend** owns (read-only — reports, never
    deletes).

    Returns a list of dicts: {prefix, index, files, bytes}. Ownership is matched
    on the full ``(prefix, index)`` identity, not the prefix alone, so a stale
    file sharing a live prefix but an unowned index is still caught (R22).

    Raises ``OSError`` if the cache folder exists but can't be read, so the caller
    can report "Couldn't verify" instead of a false clean."""
    cache_dir = default_blendcache_dir()
    if not cache_dir:
        return []
    owned = owned_point_cache_identities(bpy.data.scenes)
    return scan_orphans_in_dir(cache_dir, owned)


def scan_orphans_in_dir(cache_dir, owned_identities):
    """Pure scan: .bphys files in ``cache_dir`` whose ``(prefix, index)`` isn't in
    ``owned_identities``. Returns [{prefix, index, files, bytes}]. Read-only.

    Raises ``OSError`` if the directory can't be enumerated — a read failure must
    surface as "Couldn't verify", never be silently treated as "no orphans". (R22)"""
    if not cache_dir or not os.path.isdir(cache_dir):
        return []
    owned = {(str(p).upper(), int(i)) for (p, i) in owned_identities}
    found = {}
    with os.scandir(cache_dir) as it:   # OSError here propagates by design
        for de in it:
            m = _BPHYS_RE.match(de.name)
            if not m:
                continue
            key = (m.group(1).upper(), int(m.group(3)))
            if key in owned:
                continue
            rec = found.setdefault(key, {"prefix": key[0], "index": key[1],
                                         "files": 0, "bytes": 0})
            rec["files"] += 1
            try:
                rec["bytes"] += de.stat(follow_symlinks=False).st_size
            except OSError:
                pass
    return list(found.values())


def human_bytes(n):
    """Compact human size, e.g. 1.5 GB. Read-only formatting helper."""
    if n is None:
        return "unknown size"
    if n < 1024:
        return "%d B" % n
    units = ("KB", "MB", "GB", "TB")
    f = float(n)
    for u in units:
        f /= 1024.0
        if f < 1024.0:
            return "%.1f %s" % (f, u)
    return "%.1f PB" % (f / 1024.0)


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
        self.frames_badheader = set()     # present, non-empty, but not valid
        #                                   point-cache data (bad/truncated header)
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
        self.uncertain_note = None        # specific reason a cache is UNKNOWN (R18)
        self.file_prefix = None           # point-cache filename prefix (hex name)
        self.cache_index = 0              # point-cache index (for filename)
        self.disk_bytes = None            # total bytes of present cache files (A4)
        self.cloud_marker = None          # name of a cloud-sync folder on the path (A2)


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


def reliability_reasons(e):
    """Reasons Blender itself gives to distrust an otherwise-present cache,
    independent of the files on disk. Disk AND memory caches share these, so the
    same guard applies to both (R14/R15/R17). Returns a list of plain-English
    reasons (empty when the cache looks reliable)."""
    reasons = []
    if getattr(e, "baking_in_progress", False):
        reasons.append("a bake is still in progress")
    if getattr(e, "cache_outdated", False):
        reasons.append("the simulation settings changed since it was baked")
    if getattr(e, "frame_skip", False):
        reasons.append("frames were skipped during baking")
    return reasons


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
    badheader = set(getattr(e, "frames_badheader", None) or [])  # invalid header
    if not required:
        return CacheVerdict(V_UNVERIFIABLE, [], [], [], present, required,
                            "cache frame range is empty")

    # Truly absent files (the F01 case: a deleted head/mid/tail frame).
    missing = sorted(required - present)

    if not present:
        state = V_EMPTY if e.baked_flag else V_NOT_BAKED
        return CacheVerdict(state, missing, [], [], present, required, "")
    # Precedence: absent frames (clear FAIL) -> corrupt (0-byte or invalid
    # header) -> missing sub-cache -> unreadable (can't verify, UNKNOWN) ->
    # complete. A 0-byte frame and a present-but-garbage frame are both corrupt;
    # verdict.empty stays the 0-byte list (checks read e.frames_badheader for the
    # bad-header count, so the two causes can be named precisely).
    if missing:
        return CacheVerdict(V_INCOMPLETE, missing, sorted(empty), sorted(unreadable),
                            present, required, "")
    if empty or badheader:
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
        # is intact — either a GN disk bake whose blob files we can't validate
        # from Python (R09), or a stage whose baked flag this Blender build does
        # not expose (R18). Honest answer: UNKNOWN, never a confident COMPLETE.
        return CacheVerdict(V_UNVERIFIABLE, [], [], [], present, required,
                            getattr(e, "uncertain_note", None) or
                            "bake files are present but their internal data "
                            "can't be fully verified")
    # Every required file is on disk — but Blender itself may signal the cache
    # is not a trustworthy finished bake. Each of these is an INDEPENDENT reason
    # to withhold a confident PASS (R14/R15): a skipped-frame cache is suspect
    # even when it isn't marked outdated, and vice-versa. Report UNKNOWN, never
    # a green tick. (Downgrade-only — a True "baked" flag is still distrusted.)
    reasons = reliability_reasons(e)
    if reasons:
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


# A real disk point-cache FRAME file begins with this 8-byte magic, followed by a
# 20-byte header: magic(8) + type(4) + totpoint(4) + data_types(4), three LE
# uint32. This layout was verified byte-for-byte identical on official Blender
# 4.2.9, 4.5.9, 5.0.1 and 5.2.3 (only the high 16 bits of the type word differ by
# version, so we never key on it).
#
# SCOPE — this is a BASIC STRUCTURAL verification, not complete format validation
# and not payload correctness. We verify the signature, a full header, that the
# declared point count and data-type mask are non-zero, that the type word (low
# 16 bits) matches the type of the simulation that owns the cache, and that some
# payload exists beyond the header. We do NOT bound the payload size (it is
# compressed and version-variable — the compression toggle is even gone from
# 5.2's API) and we do NOT decode it. Blender itself exposes no error when a
# present frame fails to load (it silently falls back to the rest shape — verified
# by probe), so a frame that passes this is a well-formed cache file, NOT a
# guarantee that its simulation data is usable or numerically intact; payload
# integrity is reported as unverified, never as proven healthy. (Detecting a
# corrupted-but-well-formed body is a separate, future increment — baselined
# per-frame hashes.)
_BPHYS_MAGIC = b"BPHYSICS"
_BPHYS_HEADER_LEN = 20


# The point-cache ``type`` code (low 16 bits of the word at offset 8) for each
# kind of simulation that writes a .bphys cache. Verified against real bakes on
# official Blender 4.2.9, 4.5.9, 5.0.1 and 5.2.3. Keyed by the human ``system``
# label we assign in enumeration. We validate a frame's type ONLY against the
# type of the simulation that owns the cache — never against a guessed universal
# set. The mapping below covers the sim kinds and Blender versions we have
# actually baked and byte-inspected (4.2.9/4.5.9/5.0.1/5.2.3); it is not a proof
# about every future Blender variant. An owner we don't map (``.get`` -> None)
# simply skips the type check, so a sim kind we haven't characterised is not
# rejected — but we only *claim* correctness for the owner types and versions
# listed here, verified by the fixtures and real bakes.
#
# Hair Dynamics is DELIBERATELY omitted: a hair-dynamics cache is mixed — frame 0
# is a particle frame (type 1) while the simulated frames are a cloth solve
# (type 2, verified on all four versions). There is no single correct type for
# it, so enforcing one would reject a valid cache (exactly the false positive M1
# warns against). Hair still gets the magic/field/payload structural checks.
_EXPECTED_TYPE_CODE = {
    "Cloth": 2,
    "Soft Body": 0,
    "Particles": 1,
    "Dynamic Paint": 5,
}


def _bphys_header_valid(path, expected_type=None):
    """Basic STRUCTURAL check of a point-cache frame. True only if ``path`` has
    the BPHYSICS magic, a full 20-byte header, a non-zero declared point count
    AND data-type mask, and at least one payload byte beyond the header. False if
    present but structurally invalid — bad magic, a header shorter than 20 bytes,
    zero header fields (e.g. a fabricated 'BPHYSICS' + zero bytes file), a header
    with no payload, or — when ``expected_type`` is given — a type word (low 16
    bits) that does not match the type of the simulation that owns this cache
    (the file is then a wrong/foreign cache at the path). None if unreadable.

    This is a BASIC structural verification, not complete format validation: it
    does not prove the compressed payload is usable (we accept any non-empty
    payload) — see the module note above. An unrecognised owner type
    (``expected_type is None``) skips the type comparison rather than risk
    rejecting a valid cache."""
    try:
        with open(path, "rb") as fh:
            head = fh.read(_BPHYS_HEADER_LEN)
            if len(head) < _BPHYS_HEADER_LEN or head[:8] != _BPHYS_MAGIC:
                return False
            type_code = struct.unpack_from("<I", head, 8)[0] & 0xFFFF
            totpoint = struct.unpack_from("<I", head, 12)[0]
            data_types = struct.unpack_from("<I", head, 16)[0]
            # A frame that declares zero points or zero data channels is not a
            # usable cache frame (real frames always have both > 0).
            if totpoint == 0 or data_types == 0:
                return False
            # If we know the owning sim's type, the frame must declare it; a
            # mismatch means this isn't that simulation's cache file.
            if expected_type is not None and type_code != expected_type:
                return False
            # A valid frame carries per-point payload after the header; a file
            # that is exactly the header (no payload) is truncated/empty of data.
            fh.seek(0, os.SEEK_END)
            return fh.tell() > _BPHYS_HEADER_LEN
    except OSError:
        return None


def _scan_point_cache_files(cache_dir, prefix, index, frames, expected_type=None):
    present, empty, unreadable, badheader = set(), set(), set(), set()
    if not cache_dir or not os.path.isdir(cache_dir):
        return present, empty, unreadable, badheader
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
            else:
                # Non-empty and readable: now confirm it is actually this
                # simulation's point-cache data, not just any non-empty file.
                hv = _bphys_header_valid(p, expected_type)
                if hv is False:
                    badheader.add(fr)
                elif hv is None:
                    unreadable.add(fr)
    return present, empty, unreadable, badheader


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
    e.file_prefix = prefix
    e.cache_index = int(getattr(pc, "index", 0))
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
    (e.frames_present, e.frames_empty, e.frames_unreadable,
     e.frames_badheader) = _scan_point_cache_files(
        cache_dir, prefix, int(getattr(pc, "index", 0)), e.frames_expected,
        expected_type=_EXPECTED_TYPE_CODE.get(system))
    e.disk_bytes = _point_cache_bytes(cache_dir, prefix, e.cache_index,
                                      e.frames_present)
    e.cloud_marker = cloud_sync_marker(cache_dir)
    return e


# --------------------------------------------------------- rigid body -------

def inspect_rigidbody_world(scene):
    rbw = scene.rigidbody_world
    if rbw is None:
        return None
    e = CacheEntry("Rigid Body World", "Rigid Body World", "rbw")
    pc = rbw.point_cache
    e.baked_flag = bool(getattr(pc, "is_baked", False))
    # Memory cache, but the same staleness flags apply — a baked-but-outdated
    # RBW must not get a clean PASS either (R17).
    e.cache_outdated = bool(getattr(pc, "is_outdated", False))
    e.frame_skip = bool(getattr(pc, "is_frame_skip", False))
    e.baking_in_progress = bool(getattr(pc, "is_baking", False))
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

_MISSING = object()  # sentinel: an RNA property not exposed on this Blender build


def _stage_flag_state(ds, flag_attr):
    """Read a fluid stage's baked flag as 'baked' | 'unbaked' | 'unknown'.
    'unknown' means the property isn't exposed on this Blender build — under the
    UNKNOWN-over-false-PASS policy we must NOT assume success there (R18)."""
    val = getattr(ds, flag_attr, _MISSING)
    if val is _MISSING:
        return "unknown"
    return "baked" if val else "unbaked"


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
    e.cloud_marker = cloud_sync_marker(e.cache_dir)
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
            # folder. R18: if the flag property isn't exposed on this Blender
            # build, we can't verify the stage — report UNKNOWN, never assume it
            # is baked.
            flag_attr = _FLUID_STAGE_FLAG.get(comp_name)
            if flag_attr is not None:
                state = _stage_flag_state(ds, flag_attr)
                if state == "unknown":
                    e.certifiable = False
                    e.uncertain_note = (
                        "the '%s' stage's baked state isn't exposed on this "
                        "Blender version, so the cache can't be fully verified"
                        % comp_name)
                    continue
                if state == "unbaked":
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

    # total on-disk size across all fluid sub-caches (A4), best-effort
    if e.cache_dir and os.path.isdir(e.cache_dir):
        total = 0
        got = False
        for sub in ("data", "config", "mesh", "noise", "particles", "guiding"):
            sz = _dir_size(os.path.join(e.cache_dir, sub))
            if sz is not None:
                total += sz
                got = True
        e.disk_bytes = total if got else None
    return e


# config + data are written on every fluid bake; the rest only when their feature
# flag is on (same set inspect_fluid_domain requires). Order is stable for output.
_FLUID_ALWAYS_STAGES = ("config", "data")
_FLUID_OPTIONAL_STAGES = (
    ("noise", ("use_noise",)),
    ("mesh", ("use_mesh",)),
    ("particles", ("use_spray_particles", "use_foam_particles",
                   "use_bubble_particles", "use_tracer_particles")),
    ("guiding", ("use_guide",)),
)


def fluid_enabled_stages(ds):
    """The Mantaflow sub-cache stages this domain is CONFIGURED to write — config
    and data always, the rest only when their feature flag is on. A stage that is
    enabled but not yet baked still belongs here, so the hash verifier can report
    its frames as uncovered/missing rather than silently skipping the stage."""
    stages = list(_FLUID_ALWAYS_STAGES)
    for name, flags in _FLUID_OPTIONAL_STAGES:
        if any(bool(getattr(ds, f, False)) for f in flags):
            stages.append(name)
    return stages


def _fluid_stage_files(stage_dir, component):
    """Discover the ACTUAL files for one fluid stage — matched by the component's
    verified filename pattern, so the real extension on disk (``.vdb`` / ``.uni`` /
    ``.bobj.gz`` …) is found rather than assumed. Returns [(frame:int, abspath)]."""
    out = []
    rx = _FLUID_COMPONENT_RE.get(component)
    if rx is None or not stage_dir or not os.path.isdir(stage_dir):
        return out
    try:
        names = os.listdir(stage_dir)
    except OSError:
        return out
    for fn in names:
        m = rx.match(fn)
        if m:
            out.append((int(m.group(1)), os.path.join(stage_dir, fn)))
    return out


def iter_fluid_cache_files(scenes):
    """Yield a :class:`PointCacheFiles` per Mantaflow domain STAGE with a disk
    cache (one record for config, data, and each enabled optional stage), so the
    shared hash verifier treats each stage independently — a changed noise stage is
    distinct from a changed data stage.

    ``identity`` is the relocation-stable ``Scene::Owner::Fluid::<modifier>/<stage>``.
    ``required`` is the domain's OWN cache range (``cache_frame_start..end``), NOT
    the scene range. ``files`` are the stage's actual on-disk frame files, their
    real extensions discovered. ``index`` is always 0 (fluid frames aren't indexed
    like point caches). A REPLAY cache is a playback cache, not a bake, and is
    skipped (the structural checks report it as a Warning). Read-only."""
    for scene in scenes:
        for obj in scene.objects:
            for mod in obj.modifiers:
                if mod.type != "FLUID":
                    continue
                if getattr(mod, "fluid_type", "") != "DOMAIN":
                    continue
                ds = getattr(mod, "domain_settings", None)
                if ds is None:
                    continue
                if getattr(ds, "cache_type", "") == "REPLAY":
                    continue  # playback cache, not a bake we can fingerprint
                raw = getattr(ds, "cache_directory", "") or ""
                if not raw:
                    continue
                cache_dir = _abspath(raw)
                if not cache_dir:
                    continue
                cs = int(getattr(ds, "cache_frame_start", scene.frame_start))
                ce = int(getattr(ds, "cache_frame_end", scene.frame_end))
                required = list(range(cs, ce + 1))
                for stage in fluid_enabled_stages(ds):
                    stage_dir = os.path.join(cache_dir, stage)
                    files = [(fr, 0, p) for (fr, p)
                             in sorted(_fluid_stage_files(stage_dir, stage))]
                    identity = "%s::%s::Fluid::%s/%s" % (
                        scene.name, obj.name, mod.name, stage)
                    yield PointCacheFiles(identity, "Fluid", obj.name,
                                          "%s/%s" % (mod.name, stage),
                                          stage_dir, files, required)


def iter_hashable_cache_files(scenes):
    """Every disk cache the SHA-256 verifier covers: point caches (``.bphys``) and
    Mantaflow fluid stages. One place so capture and verify never disagree about
    what is hashable."""
    for rec in iter_point_cache_files(scenes):
        yield rec
    for rec in iter_fluid_cache_files(scenes):
        yield rec


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


# ----------------------------------------------- dynamic paint (image) ------

def inspect_dynamic_paint_image(obj, surface, scene):
    """A Dynamic Paint canvas surface in IMAGE format bakes an image *sequence*
    to ``image_output_path`` rather than a point cache. Failsafe does not yet
    read those image files, so this returns an entry that is HONESTLY
    unverifiable (surfaces as 'Couldn't verify'/UNKNOWN) — never a silent
    omission that a user could mistake for 'verified'. The output *path* is still
    genuinely checked for portability (#22) and cloud-sync risk (#24); only the
    frame *contents* are what we can't yet confirm."""
    e = CacheEntry(obj.name, "Dynamic Paint image output", "dpimage")
    raw = getattr(surface, "image_output_path", "") or ""
    e.raw_path = raw
    e.cache_dir = _abspath(raw) if raw else None
    e.cloud_marker = cloud_sync_marker(e.cache_dir)
    e.uses_disk = True
    e.memory = False
    e.baked_determinable = True
    e.baked_flag = None               # never assert baked/not for image output
    e.file_check_applicable = False   # we don't read the image files (yet)
    e.cache_range = None              # keep #19 (range) from asserting on it
    e.frames_expected = None
    e.portable, note = _portability(raw)
    if note:
        e.path_note = "Dynamic Paint image output is " + note
    e.identity = ("dpimage", e.cache_dir)
    return e


# -------------------------------------------------- top-level enumerator ----

def enumerate_caches(scene):
    """Return a list[CacheEntry] for every simulation cache in the scene."""
    entries = []
    for obj in scene.objects:
        # Point-cache-backed sims (Cloth, Soft Body, Particles, Hair dynamics,
        # Dynamic Paint vertex surfaces) all share one enumerator so the scanner
        # and the orphan check stay in lock-step.
        for system, pc in _iter_object_point_caches(obj):
            entries.append(inspect_point_cache(obj, system, pc, scene))
        # Everything else is inspected by its own specialised path.
        for mod in obj.modifiers:
            if mod.type == "FLUID":
                if getattr(mod, "fluid_type", "") == "DOMAIN" and getattr(mod, "domain_settings", None):
                    entries.append(inspect_fluid_domain(obj, mod, scene))
            elif mod.type == "NODES":
                entries.extend(inspect_gn_bakes(obj, mod, scene))
            elif mod.type == "DYNAMIC_PAINT":
                # VERTEX surfaces are point caches (handled above); IMAGE surfaces
                # bake an image sequence we don't read yet — surface them as an
                # explicit "Couldn't verify", never a silent omission.
                cs = getattr(mod, "canvas_settings", None)
                if cs is not None:
                    for surf in getattr(cs, "canvas_surfaces", []) or []:
                        if getattr(surf, "surface_format", "") == "IMAGE":
                            entries.append(inspect_dynamic_paint_image(obj, surf, scene))
    rbw = inspect_rigidbody_world(scene)
    if rbw is not None and scene_has_rigid_bodies(scene):
        entries.append(rbw)
    return entries


def scene_has_rigid_bodies(scene):
    for o in scene.objects:
        if getattr(o, "rigid_body", None) is not None:
            return True
    return False
