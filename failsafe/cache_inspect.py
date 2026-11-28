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
import json
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


# Sentinel: a scandir entry that is legitimately NOT a measurable file (a plain
# subdirectory, a symlink to a directory, or a dangling symlink). Distinct from a
# measurement FAILURE (None) so one-level size sums can skip it without voiding the
# whole total, while a real stat error still forces the total to unknown.
_NOT_A_FILE = object()


def _entry_file_bytes(de):
    """Measured on-disk size of one scandir entry, or a sentinel. Read-only; no
    symlink is followed and no directory is traversed.

    Returns:
      * an int — ``de`` is a REGULAR file: its ``st_size`` (a genuine 0-byte file
        returns 0, a measured zero).
      * ``None`` — the size is UNKNOWN: either ``stat`` raised, OR ``de`` is a
        SYMLINK. A symlinked cache file is deliberately NOT measured at its target.
        Following it would conflate the REFERENCED target size with the space
        actually occupied or reclaimable HERE: the target may be shared, external,
        or referenced elsewhere, so deleting or reading the link frees/occupies a
        different amount than the target's bytes. The honest size is therefore
        unknown — never the target's bytes presented as a measured/reclaimable
        figure (review R33-1), and never a false 0 from silently skipping it
        (review R32-1).
      * ``_NOT_A_FILE`` — a plain directory (not a file, not a symlink): skipped by
        a one-level size sum without voiding the whole total.

    The earlier R32-1 approach measured a file symlink's target; review R33-1 showed
    that number is misleading as occupied/reclaimable space, so symlinks now read as
    unknown rather than a target-size promise."""
    try:
        if de.is_symlink():
            return None
        if de.is_file(follow_symlinks=False):
            return de.stat(follow_symlinks=False).st_size
        return _NOT_A_FILE
    except OSError:
        return None


def _dir_size(path):
    """Best-effort total size in bytes of files directly in ``path`` (one level).
    Read-only.

    Returns None if the directory can't be read OR if the size of ANY file in it
    could not be measured. A single per-file ``stat`` failure must force the whole
    result to unknown, never a silently understated partial sum: with the old
    ``except OSError: continue`` the failed file was dropped and a numeric total
    returned, so an unmeasurable 300-byte stage reported 200, and a wholly
    unmeasurable stage reported a false verified 0 (review R31-1). A genuine 0-byte
    file is a *measured* zero (``st_size`` returns 0 with no error), so it is summed
    normally and does NOT force None — only an actual measurement failure does. A
    symlinked cache file reads as unknown (None), never a false 0 and never its
    target's size presented as occupied space (reviews R32-1 / R33-1); a plain
    subdirectory is skipped."""
    if not path or not os.path.isdir(path):
        return None
    total = 0
    try:
        with os.scandir(path) as it:
            for de in it:
                v = _entry_file_bytes(de)
                if v is None:
                    # Cannot measure this file: the directory total is now
                    # incomplete, so report unknown rather than a partial number
                    # that would read as a verified size.
                    return None
                if v is _NOT_A_FILE:
                    continue
                total += v
    except OSError:
        return None
    return total


def _point_cache_bytes(cache_dir, prefix, index, frames_present):
    """Sum the on-disk size of the present point-cache frame files (A4).

    Returns None if the size of ANY present frame could not be read. A present
    frame whose ``getsize`` fails (the file was enumerated but can no longer be
    stat'd) must turn the whole total unknown, never be dropped to leave a
    silently understated number that would read as the full verified size
    (review R31-1). A genuine 0-byte frame returns 0 from ``getsize`` without
    error, so it is a *measured* zero and does not force None.

    A SYMLINKED frame reads as unknown (None), never its target's size: ``getsize``
    follows a symlink, so an owned point-cache frame that is a symlink to an
    external file would otherwise be measured at the target and presented as a
    verified occupied figure — the same symlink conflation closed for ``_dir_size``
    in review R33-1, which review R34-1 found still open on this point-cache path."""
    if not cache_dir or not os.path.isdir(cache_dir) or not frames_present:
        return None
    total = 0
    for fr in frames_present:
        fn = "%s_%06d_%02d.bphys" % (prefix, fr, index)
        p = os.path.join(cache_dir, fn)
        try:
            if os.path.islink(p):
                # A symlinked frame: size unknown (the target may be shared,
                # external, or referenced elsewhere), never the followed target's
                # bytes presented as this cache's occupied space (R34-1).
                return None
            total += os.path.getsize(p)
        except OSError:
            return None
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
    "identity system obj_name sub_name cache_dir files required meta_unreadable")
PointCacheFiles.__new__.__defaults__ = ((),)   # meta_unreadable defaults to empty
# files:    list of (frame:int, index:int, abspath:str) for frames present on disk.
# required: list[int] of EVERY frame the cache range demands (range(cs, ce+1, step)),
#           present or not — so a hash verification can tell when a baseline covers
#           only part of the required range and must NOT report a clean PASS (B3).
# meta_unreadable: list[str] of metadata-file basenames that could NOT be parsed
#           (malformed JSON or invalid encoding). When non-empty the record's whole
#           sim is forced to S_META_UNREADABLE ('Couldn't verify') — the baked data a
#           corrupt metadata file describes, and the blob dependencies it names, can't
#           be trusted, so it must NEVER read as a clean PASS (review R5-1). Only the
#           Geometry Nodes meta record sets it; every other producer uses the default.


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


def _orphan_reclaimable_bytes(de):
    """Bytes that deleting this orphan file would ACTUALLY free, or None when that
    can't be honestly promised. Read-only; no symlink followed, no traversal.

    None (unknown reclaimable) when:
      * the entry is a SYMLINK — deleting it frees only the link, not its (possibly
        shared/external) target (review R33-1);
      * the file has MORE THAN ONE hard link (``st_nlink`` > 1) — the data blocks
        are shared, so deleting this name frees no blocks while another link
        survives (review R34-2);
      * ``stat`` raised, or the entry is not a regular file (a directory/other
        can't be given a reclaimable size).
    A plain regular file with a single link returns its ``st_size`` — a genuine
    0-byte file returns 0, a measured zero. Distinct from ``_entry_file_bytes``
    (used for OWNED-cache occupancy, where shared hardlinked blocks legitimately
    count as occupied): reclaimable space is about what deletion frees, so a shared
    link frees nothing and must not be promised."""
    try:
        if de.is_symlink():
            return None
        if not de.is_file(follow_symlinks=False):
            return None
        st = de.stat(follow_symlinks=False)
        if getattr(st, "st_nlink", 1) > 1:
            return None
        return st.st_size
    except OSError:
        return None


def scan_orphans_in_dir(cache_dir, owned_identities):
    """Pure scan: .bphys files in ``cache_dir`` whose ``(prefix, index)`` isn't in
    ``owned_identities``. Returns [{prefix, index, files, bytes}]. Read-only.

    Raises ``OSError`` if the directory can't be enumerated — a read failure must
    surface as "Couldn't verify", never be silently treated as "no orphans". (R22)

    ``files`` (detection) is ALWAYS counted — an orphan is reported whether or not
    its size can be read, so detection never depends on size availability. ``bytes``
    is the reclaimable size: it is ``None`` (unknown) the moment ANY file in that
    orphan group can't be stat'd, never a silently understated partial or a false 0
    — the customer-facing reclaimable figure must not read as measured when it was
    not (review R32-1). A genuine 0-byte file stats fine (``st_size`` 0, no error)
    and stays a measured zero. A symlinked .bphys voids the group's reclaimable size
    to ``None``: deleting the link frees only the link itself, not its (possibly
    shared or external) target, so no recoverable amount can be honestly promised
    (review R33-1). A HARDLINKED .bphys (``st_nlink`` > 1) likewise voids the
    group's reclaimable size: deleting this name frees no data blocks while another
    hard link survives, so its logical bytes are not guaranteed reclaimable space
    (review R34-2). In every such case the orphan is still DETECTED, only its size
    is unknown."""
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
            # Size is best-effort and must never OVERSTATE reclaimable space: once a
            # file here can't be measured, is a link, or shares its blocks, the whole
            # orphan group's reclaimable size is unknown.
            if rec["bytes"] is not None:
                sz = _orphan_reclaimable_bytes(de)
                if isinstance(sz, int):
                    rec["bytes"] += sz
                else:
                    rec["bytes"] = None
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

# A fluid sub-cache's filename scheme was established from REAL bakes on 4.2.9 and
# 5.2.3 (see research/FLUID_GN_CACHE_NOTES.md). Two groups:
#
#   FIXED — output never varies with any format setting:
#     config    -> config_NNNN.uni            (one solver-config file per frame; a
#                                               complete bake always has these, so
#                                               config is REQUIRED, not optional — R11)
#     noise     -> fluid_noise_NNNN.vdb        (cache_noise_format is accepted but does
#                                               NOT change the files on disk — always VDB)
#     particles -> fluid_particles_NNNN.vdb    (cache_particle_format's enum is only
#                                               ('UNI',), defaults to '' and likewise
#                                               does NOT change the files — always VDB)
#     guiding   -> fluid_guiding_NNNN.vdb      (velocity guide, packed VDB — R16)
#
#   FORMAT-AWARE — output genuinely depends on the stage's format setting:
#     data  OPENVDB -> one packed fluid_data_NNNN.vdb
#     data  UNI     -> several per-grid files pVel/pp/vel_NNNN.uni (liquid) or
#                      density/flame/heat/shadow/vel_NNNN.uni (gas) — NEVER
#                      fluid_data_*.uni (RAW is rejected by the setter, so unmapped)
#     mesh  BOBJECT -> fluid_mesh_NNNN.bobj.gz
#     mesh  OBJECT  -> fluid_mesh_NNNN.obj      (STL is not a valid mesh format — the
#                                                enum is only BOBJECT/OBJECT — so unmapped)
#
# Matching per component (and per the stage's REAL format) stops a file of one
# component or format from being counted as another's frame — the core false-PASS
# vector behind reviews R9-1, R10-1 and R10-2. Patterns are CASE-SENSITIVE: Blender
# writes these extensions lower-case, deterministically, so an upper-case name (a
# hand-made .VDB surviving on a case-sensitive filesystem) is not a real bake output
# and must not be counted toward coverage (review R10 hardening).
_FLUID_FIXED_RE = {
    "config":    re.compile(r"^config_(\d{4})\.uni$"),
    "noise":     re.compile(r"^fluid_noise_(\d{4})\.vdb$"),
    "particles": re.compile(r"^fluid_particles_(\d{4})\.vdb$"),
    "guiding":   re.compile(r"^fluid_guiding_(\d{4})\.vdb$"),
}

# data-stage patterns, keyed by cache_data_format. OPENVDB packs a whole frame into
# ONE fluid_data_NNNN.vdb; UNI is multi-file (one per grid) and is handled per-file by
# _FLUID_UNI_DATA_FILE_RE / _fluid_file_token below, NOT here — so this map only needs
# the single-file OpenVDB form (review R10-2, R11-1).
_FLUID_DATA_RE = {
    "OPENVDB": re.compile(r"^fluid_data_(\d{4})\.vdb$"),
}
# mesh-stage patterns, keyed by cache_mesh_format (review R10-1).
_FLUID_MESH_RE = {
    "BOBJECT": re.compile(r"^fluid_mesh_(\d{4})\.bobj\.gz$"),
    "OBJECT": re.compile(r"^fluid_mesh_(\d{4})\.obj$"),
}

# UNI data is MULTI-FILE: each frame is several per-grid files, and WHICH grids a
# genuine bake writes is fixed by the domain type. Verified IDENTICAL on real bakes of
# 4.2.9 / 4.5.9 / 5.0.1 / 5.2.3, across minimal / secondary-particles / mesh / smoke /
# fire configs:
#     LIQUID -> pVel_NNNN.uni, pp_NNNN.uni, vel_NNNN.uni
#     GAS    -> density_NNNN.uni, flame_NNNN.uni, heat_NNNN.uni, shadow_NNNN.uni,
#               vel_NNNN.uni
# These are the grids EVERY genuine bake of that domain type writes (the MANDATORY core),
# so UNI data coverage must require EACH of them FOR EACH frame — not merely "the frame
# has some .uni file". Keying coverage on the bare integer frame let a surviving sibling
# grid (pp/vel) — or a planted junk_NNNN.uni — stand in for a deleted required grid (pVel)
# and read as a clean PASS (review R11-1). The fix mirrors the Geometry-Nodes blob B3
# pattern: a per-(frame, grid) string coverage token that can never collapse.
# A bake may ALSO write OPTIONAL grids on top of the core — colored smoke adds
# color_r/color_g/color_b, a resumable cache adds restart-state grids (densityIn, flags,
# phiIn, velTmp, color_*_in, …) — which the required set picks up per-bake from the files
# actually present, so a deleted optional grid is caught too without forcing UNKNOWN on a
# bake that has none (review R12-1; see _fluid_stage_required).
_FLUID_UNI_CORE_GRIDS = {
    "LIQUID": ("pVel", "pp", "vel"),
    "GAS":    ("density", "flame", "heat", "shadow", "vel"),
}
# Colored smoke writes this THREE-grid set together (verified on real bakes, all four
# versions). It is OPTIONAL — a plain smoke/fire bake writes none of it — so it can't be
# mandatory core (that would force UNKNOWN on a legitimate plain bake). It IS tracked by
# name as a unit so one deleted channel can't hide behind its two siblings: present any
# of these and ALL three are required for every frame (review R12-1).
_FLUID_UNI_COLOR_GRIDS = ("color_r", "color_g", "color_b")
# When a cache is BOTH coloured AND resumable, Blender also writes a restart copy of each
# colour channel: color_r_in/color_g_in/color_b_in (verified on real bakes of all four
# versions). These are the colour family's restart-state grids, so they are required as a
# SET whenever a gas domain is resumable and colour is expected — otherwise deleting the
# whole _in family before baseline would leave no on-disk evidence and read PASS (R15-1).
_FLUID_UNI_COLOR_RESTART_GRIDS = ("color_r_in", "color_g_in", "color_b_in")
# Blender's colour trigger: a colour source (a SMOKE/BOTH flow's smoke_color, or a gas
# domain's flame_smoke_color when fire is active) writes colour grids IFF it differs from
# this default grey (verified on real bakes of all four versions — ANY deviation, including
# another grey, turns colour on; exactly the default does not). This is the CONFIG signal
# that colour data must exist, used to catch an entire colour family deleted before baseline
# (review R13-1 / R14-1). Blender stores these as 32-bit floats and compares them EXACTLY:
# the default grey reads back as float32(0.7) = 0.699999988079071, and a value as close as
# (0.70001, 0.7, 0.7) is a distinct float32 that turns colour on. So the comparison must be
# done in float32 (review R16-1): rounding to a few decimals missed a tiny real deviation
# (false PASS), while a float64 `!= 0.7` would flag EVERY genuine default bake (false
# UNKNOWN), because the stored default is float32(0.7), not Python's 0.7.
_FLUID_SMOKE_COLOR_DEFAULT = (0.7, 0.7, 0.7)
_FLUID_SMOKE_COLOR_DEFAULT_F32 = struct.unpack(
    "<f", struct.pack("<f", 0.7))[0]  # == 0.699999988079071, what Blender stores
# The restart-state grids a RESUMABLE cache (``cache_resumable``) writes EVERY frame, by
# domain type. Verified IDENTICAL on real resumable bakes of all four versions
# (4.2.9/4.5.9/5.0.1/5.2.3), so requiring the WHOLE set when resumable is on never forces
# UNKNOWN on a genuine bake. Naming them (rather than treating "any non-core grid present"
# as proof) makes a planted non-restart file (junk_NNNN.uni) INELIGIBLE as restart
# evidence and catches a family wiped down to a single surviving grid (review R14-2). The
# gas+colour restart grids color_r_in/g_in/b_in are driven by the colour config, not listed
# here: a wiped colour family is already caught by the colour requirement (review R13-1).
_FLUID_UNI_RESTART_GRIDS = {
    "GAS": ("densityIn", "emission", "flags", "fuel", "fuelIn", "heatIn",
            "phiIn", "phiObs", "phiOut", "react", "reactIn", "velTmp"),
    "LIQUID": ("flags", "phi", "phiIn", "phiObs", "phiOut", "phiParts",
               "phiTmp", "velTmp"),
}
# A UNI data file: <grid>_<frame>.uni. The negative lookahead preserves the R10-2
# masquerade rejection — a packed 'fluid_data_NNNN.uni' (and any reserved
# 'fluid_<stage>_' name) can never be read as a per-grid data file. group(1) is the
# grid base-name, group(2) the 4-digit frame. CASE-SENSITIVE, like every fluid pattern.
# The grid base-name MAY contain underscores: colored smoke writes color_r/color_g/
# color_b and a resumable cache writes restart-state grids like color_r_in (review R12-1).
# An earlier '[A-Za-z0-9]*' class silently REJECTED every underscore name, so those files
# were invisible to capture and verification — a deleted color channel read as a PASS.
_FLUID_UNI_DATA_FILE_RE = re.compile(
    r"^(?!fluid_(?:data|noise|particles|guiding|mesh)_)"
    r"([A-Za-z][A-Za-z0-9_]*)_(\d{4})\.uni$")


def _fluid_component_re(component, ds):
    """The filename pattern for one fluid stage, from the stage's REAL on-disk
    behaviour (verified on 4.2.9 + 5.2.3 bakes).

    config/noise/particles/guiding have a FIXED pattern — their output never varies
    with a format setting. data and mesh are driven by ``cache_data_format`` /
    ``cache_mesh_format``. A format value that isn't a recognised one returns
    ``None``: the stage is then matched by NO file, so its required frames read as
    uncovered (UNKNOWN / incomplete) instead of being matched by a permissive guess —
    the project's UNKNOWN-over-false-PASS rule, applied to an unfamiliar build
    (review R10 hardening)."""
    if component in _FLUID_FIXED_RE:
        return _FLUID_FIXED_RE[component]
    if component == "data":
        return _FLUID_DATA_RE.get(
            (getattr(ds, "cache_data_format", "") or "").upper())
    if component == "mesh":
        return _FLUID_MESH_RE.get(
            (getattr(ds, "cache_mesh_format", "") or "").upper())
    return None


def _fluid_data_is_uni(ds):
    """True iff the domain's data stage is configured to write the multi-file UNI
    format (so a per-grid completeness check applies instead of one file per frame)."""
    return (getattr(ds, "cache_data_format", "") or "").upper() == "UNI"


def _fluid_data_is_resumable(ds):
    """True iff the domain is configured for a RESUMABLE cache, which writes extra
    restart-state grids every frame. A reliable per-domain config signal (verified on all
    four versions), used to catch an entire restart-grid family wiped before baseline
    (review R13-1)."""
    return bool(getattr(ds, "cache_resumable", False))


def _f32(x):
    """Round a Python float to its 32-bit representation — what Blender actually stores and
    compares. Idempotent on a value already read from a float RNA property."""
    return struct.unpack("<f", struct.pack("<f", float(x)))[0]


def _color_is_noncat(col):
    """True if a colour triple is anything other than the default grey (or unreadable —
    treated as colour-possible, conservative). Compared in float32 to match Blender's exact
    comparison: a deviation as small as 0.70001 is a distinct float32 that turns colour on,
    and the genuine default (stored as float32(0.7)) is NOT flagged (review R16-1)."""
    if col is None:
        return False
    try:
        return any(_f32(c) != _FLUID_SMOKE_COLOR_DEFAULT_F32 for c in col)
    except Exception:
        return True  # unreadable -> assume colour is possible (safe)


def _scene_expects_fluid_color(scene):
    """True iff the scene could make Blender write colour grids (color_r/g/b) for a GAS
    domain — the CONFIG signal that colour data must exist, used to catch a whole colour
    family deleted before baseline (review R13-1 / R14-1). Verified on real bakes of all
    four versions, Blender writes colour grids IFF either:

      * a SMOKE or BOTH flow has a non-default ``smoke_color``, OR
      * fire is active (a FIRE or BOTH flow) AND a smoke source (SMOKE or BOTH flow) is
        present AND a GAS domain's ``flame_smoke_color`` is non-default — the burnt smoke
        then carries a second, different colour (review R14-1). Fire ALONE, with no smoke
        flow, writes no colour even with a non-default flame colour.

    Deliberately SCENE-WIDE (a flow is not linked in RNA to a particular domain): it can
    only ever OVER-report colour (a safe false UNKNOWN on a mixed multi-domain scene),
    never UNDER-report it — under-reporting would reintroduce the very false PASS this
    closes. Any colour value that can't be read is treated as 'colour possible'."""
    smoke_colored = False      # a SMOKE/BOTH flow has a non-default smoke_color
    has_smoke_source = False   # any SMOKE/BOTH flow
    has_fire = False           # any FIRE/BOTH flow
    flame_noncat = False       # a GAS domain has a non-default flame_smoke_color
    for obj in getattr(scene, "objects", ()):
        for mod in getattr(obj, "modifiers", ()):
            if getattr(mod, "type", "") != "FLUID":
                continue
            ftype = getattr(mod, "fluid_type", "")
            if ftype == "FLOW":
                fs = getattr(mod, "flow_settings", None)
                if fs is None:
                    continue
                flow_type = (getattr(fs, "flow_type", "") or "").upper()
                if flow_type in ("SMOKE", "BOTH"):
                    has_smoke_source = True
                    if _color_is_noncat(getattr(fs, "smoke_color", None)):
                        smoke_colored = True
                if flow_type in ("FIRE", "BOTH"):
                    has_fire = True
            elif ftype == "DOMAIN":
                ds = getattr(mod, "domain_settings", None)
                if ds is None:
                    continue
                if (getattr(ds, "domain_type", "") or "").upper() != "GAS":
                    continue
                if _color_is_noncat(getattr(ds, "flame_smoke_color", None)):
                    flame_noncat = True
    return smoke_colored or (has_smoke_source and has_fire and flame_noncat)


def _uni_core_grids(ds):
    """The per-frame grid files a genuine UNI data bake of THIS domain ALWAYS writes
    (verified on real bakes, all four versions), or ``None`` for a domain type we have
    not characterised — then UNI data coverage is forced UNKNOWN rather than guessed
    (the project's UNKNOWN-over-false-PASS rule)."""
    dt = (getattr(ds, "domain_type", "") or "").upper()
    return _FLUID_UNI_CORE_GRIDS.get(dt)


def _uni_restart_grids(ds):
    """The restart-state grids a RESUMABLE UNI bake of THIS domain always writes (verified
    identical on all four versions), or ``None`` for a domain type we have not characterised
    (then resumable coverage falls back to an unbaselinable sentinel). Used so the restart
    family is required BY NAME when ``cache_resumable`` is on — an unrelated planted grid
    can't pose as restart evidence (review R14-2)."""
    dt = (getattr(ds, "domain_type", "") or "").upper()
    return _FLUID_UNI_RESTART_GRIDS.get(dt)


def _uni_token(grid, frame):
    """The per-(frame, grid) coverage identity for one UNI data file, e.g.
    ``"0003/pVel"``. A real per-file identity (JSON-safe, stable-sorting, legible) so
    two grids sharing a frame never collapse and a missing required grid can't hide
    behind a present sibling (review R11-1; mirrors the GN-blob B3 key)."""
    return "%04d/%s" % (int(frame), grid)


def _fluid_file_token(component, ds, fn):
    """Map a filename in a fluid stage directory to ``(coverage_token, frame_int)``, or
    ``None`` if it is not a file of THIS stage in the domain's configured format.

    For the UNI data stage the token is the per-(frame, grid) string so sibling grids
    never collapse (review R11-1); every other stage (and OpenVDB data) uses the bare
    integer frame, which is also its token."""
    if component == "data" and _fluid_data_is_uni(ds):
        m = _FLUID_UNI_DATA_FILE_RE.match(fn)
        if not m:
            return None
        grid, fr = m.group(1), int(m.group(2))
        core = _uni_core_grids(ds)
        # An uncharacterised domain type has no known grids: match NO file, so required is
        # a lone unbaselinable sentinel and coverage is forced UNKNOWN (review R11-1).
        if not core:
            return None
        # EVERY grid file of a characterised domain gets a per-(frame, grid) token — the
        # mandatory core grids AND the optional ones a bake may add (color_r/g/b, resumable
        # restart-state grids). They must be captured and verified, not ignored (review
        # R12-1). Because the token is per-(frame, grid), a foreign name (junk_0003.uni)
        # can only ever cover its OWN identity (0003/junk), never stand in for a required
        # core grid (0003/density); and being then required at every other frame it is
        # absent from, it reads UNKNOWN, never a false PASS (review R11-1).
        return (_uni_token(grid, fr), fr)
    rx = _fluid_component_re(component, ds)
    if rx is None:
        return None
    m = rx.match(fn)
    if not m:
        return None
    fr = int(m.group(1))
    return (fr, fr)


def _fluid_stage_required(component, ds, cs, ce, observed_grids=None,
                          expects_color=False):
    """The coverage identities a fluid stage must have for the whole cache range
    ``cs..ce``. For UNI data it is EVERY (frame, grid) token for every REQUIRED grid — so
    a frame missing any required grid stays uncovered (review R11-1); for every other
    stage it is the integer frames. For an uncharacterised UNI domain type, a lone
    sentinel token that no real file can baseline forces UNKNOWN rather than an optimistic
    PASS.

    The required grid set is the MANDATORY core for the domain type UNION the OPTIONAL
    grids this bake actually wrote (``observed_grids`` — review R12-1) UNION the families
    the DOMAIN CONFIG says must exist (review R13-1). A single deleted optional file is
    caught by the observed union; an ENTIRE family deleted before baseline leaves no
    on-disk evidence, so it is caught instead from config — which cannot be erased by
    deleting cache files:

      * color_r/g/b: required (gas only) when ``expects_color`` — the scene configures
        colour (a non-default smoke_color flow, OR fire + a smoke flow + a non-default
        domain flame_smoke_color), Blender's colour triggers verified on all four versions
        (review R13-1 / R14-1). Required as a SET, so one deleted channel can't hide behind
        its siblings, and ALL colour deleted still reads UNKNOWN. A plain bake never expects
        colour, so it is not forced UNKNOWN. When the gas cache is ALSO resumable the colour
        restart grids color_r_in/g_in/b_in are required as a SET too (review R15-1).
      * resumable restart-state grids: when ``cache_resumable`` is on, a genuine bake
        ALWAYS writes a FIXED set of restart grids (densityIn/flags/velTmp/… — verified
        identical on all four versions). The whole set is required BY NAME, so a wiped
        family reads UNKNOWN (review R13-1), an unrelated planted file can't pose as restart
        evidence, and a family wiped down to one surviving grid is still caught (review
        R14-2). An uncharacterised domain falls back to an unbaselinable sentinel."""
    frames = range(cs, ce + 1)
    if component == "data" and _fluid_data_is_uni(ds):
        core = _uni_core_grids(ds)
        if not core:
            return ["?/uni-unknown-domain"]
        core_set = set(core)
        color_set = set(_FLUID_UNI_COLOR_GRIDS)
        observed = set(observed_grids or ())
        req = set(core_set)
        req |= observed
        is_gas = (getattr(ds, "domain_type", "") or "").upper() == "GAS"
        # Config-anchored colour family (gas only): required when the scene configures
        # colour, OR whenever any colour grid is present (observed closure) — either way
        # as the full {r,g,b} SET (review R12-1 / R13-1).
        if is_gas and (expects_color or (req & color_set)):
            req |= color_set
        # Config-anchored resumable family: when cache_resumable is on, Blender ALWAYS
        # writes a FIXED set of restart-state grids (verified identical on all four
        # versions), so require the WHOLE set BY NAME. This catches an entire restart family
        # wiped before baseline -> required-but-uncovered -> UNKNOWN (review R13-1); and
        # because the set is named, a planted non-restart file (junk_NNNN.uni) can't pose as
        # restart evidence, and a family wiped down to a single surviving grid is still
        # caught (review R14-2). A genuine resumable bake has every restart grid on disk, so
        # it stays covered and PASSES. A domain whose restart set we don't know (never
        # reached: only characterised GAS/LIQUID get here) falls back to a lone unbaselinable
        # sentinel rather than an optimistic PASS.
        sentinel = None
        if _fluid_data_is_resumable(ds):
            restart = _uni_restart_grids(ds)
            if restart:
                req |= set(restart)
            else:
                sentinel = "?/resumable-restart-wiped"
            # A gas cache that is BOTH resumable AND coloured also writes a restart copy of
            # each colour channel (color_r_in/g_in/b_in). Require the whole _in SET so the
            # family deleted before baseline reads UNKNOWN rather than hiding (review R15-1).
            color_restart_set = set(_FLUID_UNI_COLOR_RESTART_GRIDS)
            if is_gas and (expects_color or (req & color_set)
                           or (req & color_restart_set)):
                req |= color_restart_set
        tokens = [_uni_token(g, f) for f in frames for g in sorted(req)]
        if sentinel:
            tokens.append(sentinel)
        return tokens
    return list(frames)


def _uni_observed_grids(stage_dir, component, ds):
    """The grid base-names a UNI data stage ACTUALLY wrote (union across frames),
    restricted to real per-grid files (the reserved-prefix masquerades the matcher
    already rejects stay excluded). Lets the required set include whatever OPTIONAL grids
    THIS bake produced — colored-smoke color_r/g/b, resumable restart-state grids — with
    no version-specific whitelist (review R12-1). Empty for a non-UNI-data stage or an
    uncharacterised domain type (whose coverage the sentinel path already forces to
    UNKNOWN)."""
    grids = set()
    if not (component == "data" and _fluid_data_is_uni(ds)):
        return grids
    if not _uni_core_grids(ds):
        return grids
    if not stage_dir or not os.path.isdir(stage_dir):
        return grids
    try:
        names = os.listdir(stage_dir)
    except OSError:
        return grids
    for fn in names:
        m = _FLUID_UNI_DATA_FILE_RE.match(fn)
        if m:
            grids.add(m.group(1))
    return grids

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


def _scan_fluid_dir(data_dir, component, ds):
    """Scan one Mantaflow sub-cache directory for THAT component's frames, matching the
    domain's CONFIGURED format for the stage (review R9-1). Returns
    (present, empty, unreadable) as sets of INT frame numbers.

    For the UNI data stage a frame is 'present' only when EVERY required core grid for
    the domain type is on disk for it (review R11-1): a frame missing a core grid — or
    represented only by a foreign/sibling file such as a planted junk_NNNN.uni — is NOT
    present, so the structural checks report it missing instead of reading complete. An
    empty/unreadable core-grid file marks its frame (only among present frames)."""
    present, empty, unreadable = set(), set(), set()
    if not data_dir or not os.path.isdir(data_dir):
        return present, empty, unreadable
    try:
        names = os.listdir(data_dir)
    except OSError:
        return present, empty, unreadable

    if component == "data" and _fluid_data_is_uni(ds):
        core = _uni_core_grids(ds)
        if not core:
            # Uncharacterised domain type: don't guess which grids are required, so no
            # frame reads complete -> structural 'missing' upstream (UNKNOWN, not PASS).
            return present, empty, unreadable
        core_set = set(core)
        frame_grids = {}
        frame_empty, frame_unread = set(), set()
        for fn in names:
            m = _FLUID_UNI_DATA_FILE_RE.match(fn)
            if not m:
                continue
            grid, fr = m.group(1), int(m.group(2))
            frame_grids.setdefault(fr, set()).add(grid)
            if grid in core_set:
                st = _file_state(os.path.join(data_dir, fn))
                if st == "empty":
                    frame_empty.add(fr)
                elif st == "unreadable":
                    frame_unread.add(fr)
        for fr, grids in frame_grids.items():
            if core_set <= grids:
                present.add(fr)
        return present, frame_empty & present, frame_unread & present

    rx = _fluid_component_re(component, ds)
    if rx is None:
        return present, empty, unreadable
    for fn in names:
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
            os.path.join(e.cache_dir, "data"), "data", ds)
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
                os.path.join(e.cache_dir, comp_name), comp_name, ds)
            gap = required - cp
            if gap:
                e.components_missing.append(
                    "%s (missing %d frame%s)"
                    % (comp_name, len(gap), "" if len(gap) == 1 else "s"))
            # a 0-byte/unreadable sub-cache frame is also a defect
            e.frames_empty |= (ce_empty & data_present)
            e.frames_unreadable |= (cu & data_present)

    # total on-disk size across all fluid sub-caches (A4), best-effort.
    # A sub-cache directory that EXISTS but can't be fully measured must void the
    # whole fluid total (unknown), not silently drop to an understated number:
    # otherwise an unreadable `data/` stage would leave `config/`'s bytes posing
    # as the complete fluid size (review R31-1, point 4). A stage that is simply
    # absent (feature not enabled) is not an unknown — it is skipped. The total is
    # a verified figure only when at least one stage was measured AND no present
    # stage went unmeasured.
    if e.cache_dir and os.path.isdir(e.cache_dir):
        total = 0
        measured_any = False
        unmeasured_stage = False
        for sub in ("data", "config", "mesh", "noise", "particles", "guiding"):
            subpath = os.path.join(e.cache_dir, sub)
            if not os.path.isdir(subpath):
                continue  # stage legitimately absent — not an unknown
            sz = _dir_size(subpath)
            if sz is None:
                unmeasured_stage = True   # present but unmeasurable -> unknown total
            else:
                total += sz
                measured_any = True
        e.disk_bytes = total if (measured_any and not unmeasured_stage) else None
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


def _fluid_stage_files(stage_dir, component, ds):
    """Discover the ACTUAL files for one fluid stage as ``(coverage_token, abspath)`` —
    matched by the component's FORMAT-AWARE scheme (the domain's configured ``.vdb`` /
    ``.uni`` / ``.bobj.gz`` … for the stage), so a wrong-format file can't be counted as
    a required frame (review R9-1). The token is the per-file coverage identity the hash
    verifier tracks: a per-(frame, grid) string for UNI data so a sibling grid can't
    stand in for a deleted required grid (review R11-1); the integer frame otherwise."""
    out = []
    if not stage_dir or not os.path.isdir(stage_dir):
        return out
    try:
        names = os.listdir(stage_dir)
    except OSError:
        return out
    for fn in names:
        tok = _fluid_file_token(component, ds, fn)
        if tok is not None:
            out.append((tok[0], os.path.join(stage_dir, fn)))
    return out


def iter_fluid_cache_files(scenes):
    """Yield a :class:`PointCacheFiles` per Mantaflow domain STAGE with a disk
    cache (one record for config, data, and each enabled optional stage), so the
    shared hash verifier treats each stage independently — a changed noise stage is
    distinct from a changed data stage.

    ``identity`` is the relocation-stable ``Scene::Owner::Fluid::<modifier>/<stage>``.
    ``required`` is the stage's coverage set over the domain's OWN cache range
    (``cache_frame_start..end``), NOT the scene range — integer frames for most stages,
    but per-(frame, grid) tokens for UNI data so a missing required grid can't hide
    behind a present sibling (review R11-1). ``files`` are the stage's actual on-disk
    files paired with the SAME coverage token. ``index`` is always 0 (fluid frames
    aren't indexed like point caches). A REPLAY cache is a playback cache, not a bake,
    and is skipped (the structural checks report it as a Warning). Read-only."""
    for scene in scenes:
        # Scene-wide colour config (there is no per-domain colour flag): does any
        # SMOKE/BOTH flow set a non-default smoke_color? Used to require the colour family
        # even when every colour file was deleted before baseline (review R13-1).
        scene_expects_color = _scene_expects_fluid_color(scene)
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
                for stage in fluid_enabled_stages(ds):
                    stage_dir = os.path.join(cache_dir, stage)
                    files = [(tok, 0, p) for (tok, p)
                             in sorted(_fluid_stage_files(stage_dir, stage, ds))]
                    observed = _uni_observed_grids(stage_dir, stage, ds)
                    required = _fluid_stage_required(
                        stage, ds, cs, ce, observed,
                        expects_color=scene_expects_color)
                    identity = "%s::%s::Fluid::%s/%s" % (
                        scene.name, obj.name, mod.name, stage)
                    yield PointCacheFiles(identity, "Fluid", obj.name,
                                          "%s/%s" % (mod.name, stage),
                                          stage_dir, files, required)


# A GN bake meta file is named <frame:05d>_<subframe:05d>.json. The SECOND field is
# the frame's SUBFRAME (fractional part), not an interchangeable index: 00001_00000 is
# frame 1.00000, 00001_00001 is frame 1.00001 (Blender's naming, verified on real bakes
# 4.2/4.5/5.0/5.2 — a normal integer-frame simulation always writes subframe 00000).
# group(1) is the exact stem "<frame>_<subframe>", group(2) the integer frame.
_GN_META_RE = re.compile(r"((\d{5,})_\d+)\.json$")
# A blob FILENAME as it appears referenced inside a meta JSON ("00001_00000.blob").
_GN_BLOB_NAME_RE = re.compile(r"(\d{5,}_\d+)\.blob")


def _gn_meta_coverage_key(frame):
    """The exact on-disk stem a baked WHOLE frame must have: ``<frame>_00000`` (subframe
    zero). Blender names a GN bake file ``<frame:05d>_<subframe:05d>``; a whole frame is
    subframe 0 (verified on real bakes, all four versions). Tracking the EXACT stem — not
    just the integer frame — means a different-subframe file (``00003_00001``) can NEVER
    satisfy the requirement for the whole frame (``00003_00000``); collapsing to the bare
    integer let a renamed/foreign subframe file hide a missing required frame and read as
    a false PASS (review R8-1), the same collision class fixed for blobs in B3."""
    return "%05d_%05d" % (frame, 0)

# A blob file's identity is (frame, index) — Blender names blobs <frame>_<index>.blob.
# Real bakes observed on 4.2/4.5/5.0/5.2 write exactly one blob per frame (index 0),
# packing every attribute into it at byte offsets; but the filename scheme ALLOWS a
# frame to spill into sibling blobs (index 1, 2, …), so coverage must be tracked by
# the exact (frame, index) file, never collapsed to the bare frame number — otherwise
# a referenced-but-absent sibling could hide behind a present same-frame blob and read
# as a false PASS (review B3). The coverage identity is therefore the blob's exact
# filename STEM ("00000_00001"): a real, per-file identity that can NEVER collide (an
# earlier packed-int scheme collided frame 0's siblings with low frame numbers — e.g.
# 00000_00001.blob and 00001_00000.blob both mapped to 1), is JSON-safe (stored in the
# baseline sidecar), sorts stably, and displays meaningfully (review B3, round 3).


def _gn_blob_coverage_key(name):
    """The coverage identity of a blob file: its exact filename stem (no ".blob").
    A real per-file identity, so two blobs sharing a frame number never collapse and a
    referenced-but-absent sibling can't hide behind a present one (review B3)."""
    return name[:-5] if name.endswith(".blob") else name


def _gn_has_bake_target(bake, mod):
    """Whether this Blender build exposes a GN bake storage target at all.

    Blender 4.2 has NO ``bake_target`` (packed storage for simulation zones arrived
    in 4.3), so a GN sim bake there is always written to disk. Both the bake item
    and the modifier are checked, since the enum lives on the modifier."""
    return hasattr(bake, "bake_target") or hasattr(mod, "bake_target")


def _gn_disk_status(bake, mod):
    """Classify a GN bake's storage: ``'disk'`` | ``'packed'`` | ``'unknown'``.

    On Blender 4.2 (no ``bake_target`` enum) a sim bake is ALWAYS on disk, so a bake
    with no target is ``'disk'``, never packed — treating it as packed wrongly
    disabled GN disk verification on 4.2, whose on-disk layout
    (``<bake_id>/meta/*.json`` + ``blobs/*.blob``) is byte-for-byte the same as
    4.5/5.0/5.2 (verified by real bakes on all four). On 4.3+ the resolved target
    decides; an unrecognised value is ``'unknown'`` (reported, never a false PASS)."""
    if not _gn_has_bake_target(bake, mod):
        return "disk"
    t = _resolve_gn_target(bake, mod)
    if t == "DISK":
        return "disk"
    if t == "PACKED":
        return "packed"
    return "unknown"


def _gn_bake_base_dir(bake, mod):
    """Absolute base directory a GN bake writes under — its own custom path when
    ``use_custom_path`` is set, else the modifier's ``bake_directory`` (which exists
    and is honoured on 4.2 too). None if unresolved (empty path / unsaved file)."""
    mod_raw = getattr(mod, "bake_directory", "") or ""
    use_custom = bool(getattr(bake, "use_custom_path", False))
    raw = (getattr(bake, "directory", "") or mod_raw) if use_custom else mod_raw
    return _abspath(raw) if raw else None


def _gn_bake_cache_dir(bake, mod):
    """The directory that actually holds this bake's ``meta/`` and ``blobs/`` — or
    None if unresolved.

    Layout verified by real bakes on all four versions (review, round 3):
      * a per-bake CUSTOM path (``use_custom_path``) is that bake's own folder, so the
        files sit DIRECTLY under it — ``<directory>/meta`` — with NO ``<bake_id>``
        subfolder;
      * the shared modifier ``bake_directory`` is used by every bake on the modifier,
        so each bake gets its own ``<bake_directory>/<bake_id>/meta`` subfolder.
    Appending ``<bake_id>`` unconditionally looked in the wrong place for a custom
    path and would read a correctly-baked custom-path cache as empty."""
    base_dir = _gn_bake_base_dir(bake, mod)
    if base_dir is None:
        return None
    if bool(getattr(bake, "use_custom_path", False)):
        return base_dir
    bake_id = getattr(bake, "bake_id", None)
    return os.path.join(base_dir, str(bake_id)) if bake_id is not None else None


def _gn_meta_is_recognizable(data):
    """True iff a decoded meta JSON has the SHAPE of a real Geometry Nodes bake frame,
    so a blob dependency set can be trusted to come from it.

    Verified on real bakes (4.2.9 and 5.2.3, bracketing 4.5/5.0): a bake frame's meta
    is a dict ``{"version": 3, "items": {...}}`` whose ``items`` is a NON-EMPTY mapping
    (keys ``"0"``, ``"1"``, …) — or a list — of per-socket entries. EVERY entry is a
    dict carrying a non-empty ``"type"`` string (``GEOMETRY``, ``FLOAT``, …) AND a
    ``"data"`` payload, which Blender ALWAYS serialises per item. The data
    representation is type-appropriate: a GEOMETRY item's ``data`` is a dict (the
    mesh/pointcloud/curve/instances payload), while a value item (FLOAT, …) stores its
    value inline (a scalar or list).

    Two facts established from real bakes guard against over-rejection:
      * A pure value item stores its value INLINE and references NO blob.
      * An EMPTY-geometry item is a GEOMETRY whose ``data`` is an empty dict ``{}`` with
        NO blob on disk — a legitimate, blob-free geometry frame.
    So a recognizable frame may reference ZERO blobs: "zero blobs" is NOT a defect and
    must not reject a legitimate value-only or empty-geometry bake.

    What it REJECTS (valid JSON that Blender never writes, so its real dependency set
    can't be trusted — route to 'Couldn't verify', never accept an empty dependency set
    as a clean PASS — review R6-1/R7-1): a non-dict; a missing/non-int ``version``;
    ``items`` missing / empty / not a mapping-or-list; any entry that isn't a dict, or
    lacks a ``type`` string, or LACKS a ``data`` key (the R7-1 counterexample
    ``{"type": "GEOMETRY"}`` has no ``data``), or a GEOMETRY entry whose ``data`` isn't
    a dict."""
    if not isinstance(data, dict):
        return False
    ver = data.get("version")
    if not isinstance(ver, int) or isinstance(ver, bool):
        return False
    items = data.get("items")
    if isinstance(items, dict):
        vals = list(items.values())
    elif isinstance(items, list):
        vals = items
    else:
        return False
    if not vals:
        return False
    for it in vals:
        if not isinstance(it, dict):
            return False
        t = it.get("type")
        if not isinstance(t, str) or not t:
            return False
        if "data" not in it:                 # Blender always serialises a per-item payload
            return False
        if t == "GEOMETRY" and not isinstance(it.get("data"), dict):
            return False                     # geometry data is a dict (empty {} if empty geo)
    return True


def _iter_json_strings(obj):
    """Yield every string value inside a decoded JSON structure, recursively."""
    if isinstance(obj, str):
        yield obj
    elif isinstance(obj, dict):
        for v in obj.values():
            for s in _iter_json_strings(v):
                yield s
    elif isinstance(obj, list):
        for v in obj:
            for s in _iter_json_strings(v):
                yield s


def _gn_referenced_blob_names(meta_paths):
    """The set of blob filenames the given meta JSON files reference BY NAME — the
    bake's real blob DEPENDENCY set.

    A GN sim bake stores a frame's heavy attribute data in ``blobs/<frame>_<idx>.blob``
    and the per-frame ``meta/*.json`` references it by name (in ``...data.name``
    fields) with start/size offsets. Crucially, STATIC data (mesh topology, UVs) is
    written ONCE — on the first baked frame — and every later frame's meta references
    that SAME first-frame blob (verified on real bakes, all four versions). So the true
    dependency set is the union of the blob names referenced across every present meta
    file, not merely the files that happen to sit in ``blobs/``. Deleting the
    first-frame blob breaks every later frame, and this is what surfaces that.

    The meta is PARSED as JSON and blob names are read from the DECODED string values,
    so a reference written with a JSON escape (e.g. ``"00004_00000\\u002eblob"``, which
    decodes to ``00004_00000.blob``) is still seen. A raw-text regex would match only
    the literal ``.blob`` spelling and could silently drop an escaped dependency,
    letting an absent blob read as a clean PASS (review R4-1).

    Returns ``(names, unreadable)``. A meta file is put in ``unreadable`` — and the
    caller forces the whole sim to 'Couldn't verify', never trusting a dependency set
    drawn from it — when EITHER:

    * it can't be parsed — malformed / truncated JSON, or bytes that aren't valid
      UTF-8. It is NOT raw-text scanned as a fallback: a partial raw-text scan can MISS
      a referenced blob (its name split across a truncation, or mangled by the bad
      encoding) and under-count the dependency set, so an absent blob would read as a
      clean PASS (review R5-1); OR
    * it parses but is NOT a recognizable GN bake frame
      (:func:`_gn_meta_is_recognizable`) — e.g. ``{}``, a bad ``version``, or an item
      missing its ``data`` payload (``{"type": "GEOMETRY"}``). Its real dependency set
      can't be established, so accepting its empty blob set would let a frame whose blob
      was deleted read as a clean PASS (review R6-1/R7-1). A recognizable frame that
      references zero blobs (a value-only item stores its value inline, or an empty
      geometry has empty data) is fine and is NOT flagged.

    Read-only; never raises on a bad file."""
    names = set()
    unreadable = []
    for p in meta_paths:
        try:
            # encoding="utf-8" with the default strict errors so invalid UTF-8 RAISES
            # (it must be treated as unreadable), not silently dropped by errors="ignore".
            with open(p, "r", encoding="utf-8") as fh:
                txt = fh.read()
        except (OSError, UnicodeDecodeError):
            unreadable.append(p)
            continue
        try:
            data = json.loads(txt)
        except (ValueError, TypeError):
            unreadable.append(p)
            continue
        if not _gn_meta_is_recognizable(data):
            # Valid JSON, but not a GN bake frame: we can't establish its blob
            # dependency set, so DON'T accept an empty one — mark it unreadable so the
            # sim reads 'Couldn't verify', never a clean PASS (review R6-1).
            unreadable.append(p)
            continue
        for s in _iter_json_strings(data):
            for m in _GN_BLOB_NAME_RE.finditer(s):
                names.add(m.group(1) + ".blob")
    return names, unreadable


def iter_gn_cache_files(scenes):
    """Yield :class:`PointCacheFiles` for Geometry Nodes SIMULATION-ZONE bakes stored
    on DISK. Each disk bake yields a ``meta`` record (one ``<frame>_<idx>.json`` per
    baked frame, frame-indexed) and — when the present meta reference blob data — a
    ``blobs`` record (the referenced ``<frame>_<idx>.blob`` dependency files).

    Only SIMULATION zones (``GeometryNodeSimulationOutput``) are hashed. An explicit
    Bake node is a different feature whose baked frame set we can't establish reliably
    (a STILL bake stores the current-frame-at-bake-time, not derivable from any
    property), so hashing it could assert a wrong required set — it is skipped and left
    to the STRUCTURAL #17/#19 checks, never a false PASS (review, round 3).

    ``required`` for the meta record is the RELIABLE expected frame range
    (:func:`_gn_expected_range`): per-bake custom simulation range if set, else the
    SCENE-WIDE custom simulation range (``scene.use_custom_simulation_range``, which
    OVERRIDES the scene frame range — review B4a), else the scene range. ``bake_mode``
    (which misreports ``STILL``/``frame_end`` 100 for a sim zone) is ignored. This
    catches a missing HEAD or TAIL frame as well as interior holes (review B4) — none
    read as a complete PASS. The baked range lives directly under a per-bake CUSTOM
    path, or under ``<bake_directory>/<bake_id>`` otherwise (:func:`_gn_bake_cache_dir`
    — review, round 3).

    ``required`` for the blobs record is the set of EXACT filename-stem identities the
    meta files reference (:func:`_gn_blob_coverage_key`), so a referenced-but-absent
    dependency — including the shared first-frame topology blob, or a sibling blob
    sharing a frame number with a present one (review B3) — reports as
    uncovered/missing rather than a silent pass (review M1).

    PACKED bakes (4.3+ default — stored inside the .blend) leave no files and are
    NEVER yielded (they stay the honest 'Couldn't verify' of #17). A DISK bake we
    cannot LOCATE (no directory set, unsaved file) is NOT silently dropped either —
    it is yielded with no coverage so a requested verify reports 'Couldn't verify',
    never a clean pass (review B1). On Blender 4.2 a sim bake is always on disk and
    is verified here like any other (review B2).

    identity = ``Scene::Owner::Geometry Nodes::<modifier>/<bake_id>/<meta|blobs>``
    (relocation-stable). Read-only."""
    for scene in scenes:
        for obj in scene.objects:
            for mod in obj.modifiers:
                if mod.type != "NODES":
                    continue
                bakes = list(getattr(mod, "bakes", []) or [])
                if not bakes:
                    continue
                for b in bakes:
                    if _gn_disk_status(b, mod) != "disk":
                        continue  # packed / unknown target: not hashable (#17)
                    if not _gn_is_sim_zone(b):
                        # #27 hashes SIMULATION-ZONE caches, whose baked range we can
                        # establish reliably (every frame). An explicit Bake node is a
                        # different feature whose baked frame set we do NOT verify here
                        # (a STILL bake stores the current-frame-at-bake, not derivable
                        # from any property — review, round 3), so hashing it risks a
                        # wrong required set. Skip it: #17 still reports it structurally
                        # ('baked', range undetermined), so it's never a false PASS and
                        # never silently dropped from the overall verdict.
                        continue
                    bake_id = getattr(b, "bake_id", None)
                    label = "%s/%s" % (mod.name, bake_id)
                    ident_meta = "%s::%s::Geometry Nodes::%s/meta" % (
                        scene.name, obj.name, label)
                    ident_blobs = "%s::%s::Geometry Nodes::%s/blobs" % (
                        scene.name, obj.name, label)
                    bdir = _gn_bake_cache_dir(b, mod)
                    if bdir is None or bake_id is None:
                        # A disk bake we can't locate — surface it with no coverage
                        # so a requested verify can't read clean (review B1).
                        yield PointCacheFiles(ident_meta, "Geometry Nodes",
                                              obj.name, "%s/meta" % label, None,
                                              [], [])
                        continue
                    meta_dir = os.path.join(bdir, "meta")
                    mfiles = []
                    if os.path.isdir(meta_dir):
                        for fn in os.listdir(meta_dir):
                            m = _GN_META_RE.match(fn)
                            if m:
                                # Coverage identity is the EXACT filename stem
                                # ("<frame>_<subframe>"), never the bare integer frame,
                                # so a different-subframe file can't satisfy a required
                                # whole frame (review R8-1).
                                mfiles.append((m.group(1), 0,
                                               os.path.join(meta_dir, fn)))
                    mfiles.sort()
                    # Expected frame set: the reliable sim-zone range (per-bake custom
                    # range, else scene-wide custom simulation range, else scene range)
                    # catches a missing HEAD or TAIL frame, not only interior holes
                    # (review B4/B4a). Only sim zones reach here, so the range is
                    # normally resolvable. If it CAN'T be established — None, or a
                    # degenerate inverted custom range (start > end) — we do NOT fall
                    # back to the present span: that would silently accept whatever
                    # frames exist and could hide a head/tail gap. Instead yield no
                    # coverage so the sim reads 'Couldn't verify', never a clean pass
                    # (review R4 hardening; cf. B1).
                    exp = _gn_expected_range(b, scene)
                    if exp is None or exp[0] > exp[1]:
                        yield PointCacheFiles(ident_meta, "Geometry Nodes",
                                              obj.name, "%s/meta" % label, None,
                                              [], [])
                        continue
                    # Require each WHOLE frame's exact subframe-0 stem, so a renamed or
                    # foreign non-zero-subframe meta can't be counted as the required
                    # frame (review R8-1).
                    required = [_gn_meta_coverage_key(f)
                                for f in range(exp[0], exp[1] + 1)]

                    # The blob DEPENDENCY set is read by PARSING each present meta file.
                    # If ANY meta can't be parsed (malformed JSON or invalid encoding),
                    # that dependency set is untrustworthy AND the baked data the meta
                    # describes can't be verified — so the whole bake is forced to
                    # 'Couldn't verify' (S_META_UNREADABLE via meta_unreadable), and we
                    # do NOT emit a blobs record that could read clean from a possibly
                    # under-counted dependency set (review R5-1). Never a false PASS.
                    ref_names, bad_metas = _gn_referenced_blob_names(
                        [p for (_fr, _i, p) in mfiles])
                    if bad_metas:
                        yield PointCacheFiles(
                            ident_meta, "Geometry Nodes", obj.name,
                            "%s/meta" % label, meta_dir, mfiles, required,
                            [os.path.basename(p) for p in bad_metas])
                        continue

                    yield PointCacheFiles(ident_meta, "Geometry Nodes", obj.name,
                                          "%s/meta" % label, meta_dir, mfiles,
                                          required)

                    # Blobs: hash the files the present meta actually DEPEND on
                    # (referenced by name), including the shared first-frame topology
                    # blob reused by every later frame. A referenced blob missing on
                    # disk -> uncovered/missing -> floor (a broken dependency), never
                    # a silent pass (review M1).
                    blob_dir = os.path.join(bdir, "blobs")
                    if ref_names:
                        bfiles, req_keys = [], set()
                        for nm in ref_names:
                            # Track each referenced blob by its EXACT filename-stem
                            # identity, so a referenced-but-absent sibling can't hide
                            # behind a present same-frame blob (review B3).
                            key = _gn_blob_coverage_key(nm)
                            req_keys.add(key)
                            p = os.path.join(blob_dir, nm)
                            if os.path.isfile(p):
                                bfiles.append((key, 0, p))
                        yield PointCacheFiles(
                            ident_blobs, "Geometry Nodes", obj.name,
                            "%s/blobs" % label, blob_dir, sorted(bfiles),
                            sorted(req_keys))


def iter_hashable_cache_files(scenes):
    """Every disk cache the SHA-256 verifier covers: point caches (``.bphys``),
    Mantaflow fluid stages, and Geometry Nodes DISK bakes. One place so capture and
    verify never disagree about what is hashable."""
    for rec in iter_point_cache_files(scenes):
        yield rec
    for rec in iter_fluid_cache_files(scenes):
        yield rec
    for rec in iter_gn_cache_files(scenes):
        yield rec


# -------------------------------------------------- geometry nodes ----------

def _resolve_gn_target(bake, mod):
    """Resolve a bake's effective storage target, following INHERIT to the
    modifier's own setting. Returns an upper-case string or '' if unknown."""
    bt = getattr(bake, "bake_target", None)
    if not bt or bt == "INHERIT":
        bt = getattr(mod, "bake_target", None)
    return (bt or "").upper()


def _gn_is_sim_zone(bake):
    """True iff this bake item belongs to a Geometry Nodes SIMULATION zone
    (``GeometryNodeSimulationOutput``), as opposed to an explicit Bake node or an
    unknown/future kind. The node backlink is reliable on all four versions (a real
    bake always exposes ``bake.node.bl_idname`` — verified 4.2/4.5/5.0/5.2)."""
    node = getattr(bake, "node", None)
    return (getattr(node, "bl_idname", "") or "") == "GeometryNodeSimulationOutput"


def _scene_sim_range(scene):
    """The scene-level baked range for a SIMULATION: the scene-wide custom simulation
    range (``scene.use_custom_simulation_range`` -> ``simulation_frame_start`` /
    ``simulation_frame_end``) when enabled, else the ordinary scene frame range.

    Verified by real bakes on all four versions: with scene range 1..6 and a scene-wide
    simulation range 2..9, the sim baked frames 2..9 — so the scene frame range alone
    UNDERSTATES the baked set and would miss a tail frame (review B4a, round 3)."""
    if bool(getattr(scene, "use_custom_simulation_range", False)):
        return (int(getattr(scene, "simulation_frame_start", scene.frame_start)),
                int(getattr(scene, "simulation_frame_end", scene.frame_end)))
    return (int(scene.frame_start), int(scene.frame_end))


def _gn_expected_range(bake, scene):
    """The RELIABLE expected baked frame range for a GN bake, or ``None`` when it
    can't be established.

    ``bake.bake_mode`` is UNRELIABLE for a simulation-zone bake: it reports
    ``'STILL'`` (and ``frame_end`` 100) even for a multi-frame sim — verified on
    4.2/4.5/5.0/5.2. So the range can't be read from the bake item's own mode. The
    bake's ``node`` backlink tells us what KIND of bake it is, which is reliable:

      * ``GeometryNodeSimulationOutput`` — a simulation zone. Precedence, verified by
        real bakes on all four versions (review B4a, round 3):
          1. the per-bake custom simulation frame range
             (``use_custom_simulation_frame_range`` -> the bake's frame_start/end),
          2. else the SCENE-WIDE custom simulation range
             (``scene.use_custom_simulation_range``), which OVERRIDES the scene frame
             range (a tail frame beyond the scene range would otherwise be missed),
          3. else the ordinary scene frame range.
        A sim always runs from its start, so this is authoritative and lets #27 catch
        a missing HEAD or TAIL frame, not only interior holes (review B4).
      * ``GeometryNodeBake`` — an explicit Bake node (a DIFFERENT feature). Its
        ``bake_mode`` IS genuine. A STILL bake stores the CURRENT frame at bake time,
        which is NOT persisted to any readable property (``frame_start`` is NOT it —
        verified on real bakes), so its range can't be derived -> ``None``. An
        ANIMATION bake runs the frame range. NOTE: #27 does not hash Bake-node caches
        (only simulation zones — see :func:`iter_gn_cache_files`); this range is used
        only by the STRUCTURAL #17/#19 checks.

    An unknown/unavailable node kind returns ``None``."""
    node = getattr(bake, "node", None)
    idname = getattr(node, "bl_idname", "") or ""
    if idname == "GeometryNodeSimulationOutput":
        if bool(getattr(bake, "use_custom_simulation_frame_range", False)):
            return (int(getattr(bake, "frame_start", scene.frame_start)),
                    int(getattr(bake, "frame_end", scene.frame_end)))
        return _scene_sim_range(scene)
    if idname == "GeometryNodeBake":
        if getattr(bake, "bake_mode", "ANIMATION") == "STILL":
            return None  # baked frame = current frame at bake time, not derivable
        if bool(getattr(bake, "use_custom_simulation_frame_range", False)):
            return (int(getattr(bake, "frame_start", scene.frame_start)),
                    int(getattr(bake, "frame_end", scene.frame_end)))
        return (int(scene.frame_start), int(scene.frame_end))
    return None


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
        status = _gn_disk_status(b, mod)
        if status != "disk":
            # PACKED (or an unrecognised/inherited-packed target) leaves no
            # Python-visible files. Phase 0 §3b: report UNKNOWN, never guess.
            e.baked_determinable = False
            e.baked_flag = None
            e.file_check_applicable = False
            if status == "packed":
                e.path_note = "packed Geometry Nodes bake (not visible to Python)"
            else:
                t = _resolve_gn_target(b, mod)
                e.path_note = ("packed Geometry Nodes bake (not visible to Python)"
                               if t in ("PACKED", "") else
                               "Geometry Nodes bake target '%s'" % t.title())
            out.append(e)
            continue
        # Disk bake (incl. Blender 4.2, which has no bake_target and always writes
        # sim bakes to disk). Honour a per-bake custom directory and frame range.
        use_custom = bool(getattr(b, "use_custom_path", False))
        raw = (getattr(b, "directory", "") or mod_raw) if use_custom else mod_raw
        e.uses_disk = True
        # We can see the meta frames and that blobs/ exists, but not prove the
        # referenced blob data is intact -> never certify COMPLETE (R09).
        e.certifiable = False
        e.raw_path = raw
        base_dir = _abspath(raw) if raw else None
        bake_id = getattr(b, "bake_id", None)
        # Custom path -> files sit directly under it; shared bake_directory -> under a
        # <bake_id> subfolder (verified by real bakes, round 3). Appending <bake_id>
        # unconditionally looked in the wrong place for a custom path.
        bdir = _gn_bake_cache_dir(b, mod)
        e.cache_dir = bdir
        e.identity = ("gn", bdir)
        e.file_check_applicable = blend_is_saved() and bool(bdir)
        e.portable, note = _portability(raw)
        if note:
            e.path_note = "Geometry Nodes bake is " + note

        # Reliable expected range (ignores the STILL misreport for sim zones;
        # review B4). None when it can't be established -> don't assert a range, so
        # #19/#20 stay silent rather than comparing against a wrong one.
        exp = _gn_expected_range(b, scene)
        if exp is not None and exp[0] <= exp[1]:
            fs, fe = exp
            e.cache_range = (fs, fe)
            e.frames_expected = (list(range(fs, fe + 1))
                                 if e.file_check_applicable else None)
        else:
            e.cache_range = None
            e.frames_expected = None

        present, empty, unreadable = set(), set(), set()
        meta_paths = []
        if bdir:
            meta = os.path.join(bdir, "meta")
            if os.path.isdir(meta):
                for fn in os.listdir(meta):
                    m = re.match(r"(\d{5,})_(\d+)\.json$", fn)
                    # Only a WHOLE-frame file (subframe 0) counts as that integer frame
                    # present; a different-subframe file must not satisfy it (review
                    # R8-1), matching the hash-coverage identity above.
                    if m and int(m.group(2)) == 0:
                        fr = int(m.group(1))
                        present.add(fr)
                        mp = os.path.join(meta, fn)
                        meta_paths.append(mp)
                        st = _file_state(mp)
                        if st == "empty":
                            empty.add(fr)
                        elif st == "unreadable":
                            unreadable.add(fr)
            # The meta JSON is only an index; the heavy data lives in blobs/. Metadata
            # that REFERENCES blob data but has none on disk is a broken bake (R03). But
            # a legitimately blob-free frame — an empty-geometry or value-only
            # simulation stores its item inline and references NO blob (verified on real
            # bakes) — must NOT be flagged as missing blob data just because blobs/ is
            # empty (review R8 nonblocking note). So gate on the metas actually naming a
            # blob.
            if present:
                ref_names, _bad = _gn_referenced_blob_names(meta_paths)
                if ref_names:
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
