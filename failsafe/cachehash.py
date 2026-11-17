# SPDX-License-Identifier: GPL-3.0-or-later
"""Baselined per-frame cache hashes — change detection, NOT a validity oracle.

What this is (and, loudly, what it is NOT), per review M2:

  * When the user clicks Save Baseline *with cache hashes*, we stream a SHA-256 of
    every present point-cache frame file and store it in the external sidecar,
    keyed to the sim's stable identity, the file's project-relative path and its
    frame number. Nothing is written into the .blend; the cache files are read,
    never modified.
  * A later verification re-hashes the files and compares:
      - match    -> "Bytes unchanged since the baseline was saved." This is NEVER
        a claim the cache is valid or renderable: if the baseline was taken AFTER
        the cache was already damaged, the hash faithfully records the damaged
        bytes and keeps matching them.
      - mismatch -> "Cache file changed since the baseline." This is NOT
        automatically "corrupt": a deliberate re-bake legitimately rewrites the
        bytes. It is a *detected change*, which may be exactly what the user
        intended.
  * A missing / stale / unreadable / absent reference can NEVER produce a PASS —
    it reports "Couldn't verify".

So this is a change-detector, only as trustworthy as the moment the baseline was
taken. It is complementary to — not a substitute for — actually having Blender
decode a frame (kept deliberately separate; see research/CACHE_FORMAT_NOTES.md).

Design for large caches (review M2 items 6/7): files are hashed in streamed
chunks (never loaded whole), every chunk invokes an optional ``progress`` and an
optional ``cancel`` callback so a modal GUI driver stays responsive and can be
stopped, and a file that changes size/mtime *while we read it* is reported as
volatile rather than trusted.
"""
import collections
import hashlib
import os

from . import baseline as bl


ALGO = "sha256"
CHUNK = 1 << 20          # 1 MiB streamed reads — bounded memory on multi-GB files

# Sentinel: the file changed under us during the read, so the digest can't be
# trusted. Distinct from None (couldn't open/stat at all).
VOLATILE = "__volatile__"


class Cancelled(Exception):
    """Raised out of hashing when a supplied ``cancel()`` callback returns True."""


def hash_file(path, chunk=CHUNK, cancel=None, progress=None):
    """Stream a cryptographic hash of one file.

    Returns ``(hexdigest, size)`` on success, ``None`` if the file can't be
    opened/stat'd, or :data:`VOLATILE` if its size or mtime changed between the
    stat before and after the read (i.e. it was being written while we hashed it).

    Reads in ``chunk``-sized blocks so a multi-GB cache file never loads whole.
    ``cancel`` (if given) is polled before each block and raises
    :class:`Cancelled` when it returns True. ``progress`` (if given) is called
    with the byte count of each block, so a driver can advance a bar."""
    try:
        st0 = os.stat(path)
    except OSError:
        return None
    h = hashlib.new(ALGO)
    read = 0
    try:
        with open(path, "rb") as fh:
            while True:
                if cancel is not None and cancel():
                    raise Cancelled()
                block = fh.read(chunk)
                if not block:
                    break
                h.update(block)
                read += len(block)
                if progress is not None:
                    progress(len(block))
    except OSError:
        return None
    try:
        st1 = os.stat(path)
    except OSError:
        return None
    # A torn read (size/mtime moved, or we read a different number of bytes than
    # the file claimed) must not be trusted as an authoritative fingerprint.
    if read != st0.st_size or st1.st_size != st0.st_size \
            or st1.st_mtime_ns != st0.st_mtime_ns:
        return VOLATILE
    return h.hexdigest(), st0.st_size


def _relkey(abspath, blend_dir):
    """A relocation-stable key for a cache file: the POSIX path relative to the
    .blend's folder when the file lives inside the project (the default
    ``blendcache_<file>`` layout), else the absolute POSIX path.

    Keying on the project-relative path means moving the whole project folder
    keeps the baseline valid; an external/absolute cache path is inherently not
    relocation-stable and is stored as-is (a move then reads as 'changed/missing'
    -> 'Couldn't verify', never a false match)."""
    if blend_dir:
        try:
            rel = os.path.relpath(abspath, blend_dir)
        except ValueError:       # different drive on Windows
            rel = abspath
    else:
        rel = abspath
    return rel.replace(os.sep, "/")


# --------------------------------------------------------------- capture ----

def capture_iter(scenes, blend_dir, cancel=None):
    """Generator building the cache-hash manifest, one file per step.

    Yields ``("file", done_count)`` after each hashed file and finally
    ``("result", manifest)`` where manifest is ``{"algo": "sha256", "sims":
    {identity: {system, obj_name, frames: {relkey: {"sha256":.., "size":..}},
    volatile: N}}}``. One hash per step keeps a modal driver responsive.

    A frame that is unreadable or changing *while we capture it* is NOT stored
    (volatile frames are counted); storing a torn hash would later read as a false
    mismatch. Raises :class:`Cancelled` if ``cancel`` fires — callers then write
    NOTHING, so an interrupted capture never leaves a half-built baseline."""
    from . import cache_inspect as ci
    sims = {}
    done = 0
    for rec in ci.iter_point_cache_files(scenes):
        frames = {}
        volatile = 0
        for (_fr, _idx, p) in rec.files:
            if cancel is not None and cancel():
                raise Cancelled()
            res = hash_file(p, cancel=cancel)
            done += 1
            if res is None:
                yield ("file", done)
                continue                 # unreadable at capture: leave uncovered
            if res is VOLATILE:
                volatile += 1
                yield ("file", done)
                continue
            digest, size = res
            frames[_relkey(p, blend_dir)] = {"sha256": digest, "size": size}
            yield ("file", done)
        if frames or volatile:
            sims[rec.identity] = {"system": rec.system, "obj_name": rec.obj_name,
                                  "frames": frames, "volatile": volatile}
    yield ("result", {"algo": ALGO, "sims": sims})


def capture(scenes, blend_dir, cancel=None, progress=None):
    """Blocking capture. Returns the manifest dict. Drives :func:`capture_iter`;
    ``progress`` (if given) is called with the running file count."""
    manifest = {"algo": ALGO, "sims": {}}
    for ev in capture_iter(scenes, blend_dir, cancel=cancel):
        if ev[0] == "file" and progress is not None:
            progress(ev[1])
        elif ev[0] == "result":
            manifest = ev[1]
    return manifest


def capture_steps(scenes, blend_dir, cancel=None):
    """Generator form of :func:`capture` for a modal GUI driver. Yields
    ``("total", n_files)``, then ``("file", done)`` per file, then
    ``("done", manifest)``. On cancel, yields ``("cancelled", None)`` and stops —
    the caller writes nothing."""
    yield ("total", capture_total_files(scenes))
    try:
        manifest = {"algo": ALGO, "sims": {}}
        for ev in capture_iter(scenes, blend_dir, cancel=cancel):
            if ev[0] == "file":
                yield ("file", ev[1])
            elif ev[0] == "result":
                manifest = ev[1]
    except Cancelled:
        yield ("cancelled", None)
        return
    yield ("done", manifest)


def capture_total_files(scenes):
    """How many present point-cache frame files a capture will hash (for a
    progress bar's denominator, which steps per file)."""
    from . import cache_inspect as ci
    return sum(len(rec.files) for rec in ci.iter_point_cache_files(scenes))


# --------------------------------------------------------------- verify -----

# Per-sim verification outcome. Lists hold frame NUMBERS (ints) for messaging.
SimVerify = collections.namedtuple(
    "SimVerify", "identity system obj_name state matched changed missing "
                 "unreadable new")

# sim states
S_UNCHANGED = "UNCHANGED"     # every baselined frame present and byte-identical
S_CHANGED = "CHANGED"         # at least one frame's bytes differ from the baseline
S_DRIFT = "DRIFT"             # frame set differs (missing/new) but none changed
S_UNREADABLE = "UNREADABLE"   # some frames couldn't be read -> can't verify
S_NO_REF = "NO_REF"           # sim present now, but not in the baseline hashes
S_EMPTY_REF = "EMPTY_REF"     # baseline recorded this sim but with no usable frame
S_GONE = "GONE"               # sim in the baseline, not in the scene now


def _nice(identity):
    return identity.replace("::", " — ")


def _sim_state(matched, changed, missing, unreadable, new):
    # A confirmed byte change is the most actionable fact, so it leads even when
    # some other frames couldn't be read. Nothing here maps an unreadable/missing
    # reference to a PASS — the cardinal 'no false PASS' rule.
    if changed:
        return S_CHANGED
    if unreadable:
        return S_UNREADABLE
    if missing or new:
        return S_DRIFT
    if matched:
        return S_UNCHANGED
    return S_EMPTY_REF


def verify_total(scenes, manifest, blend_dir):
    """How many files the verification WILL hash (the baselined frames that exist
    now), for a progress bar's denominator. Cheap: stats only, no hashing."""
    from . import cache_inspect as ci
    saved_sims = manifest.get("sims", {}) if isinstance(manifest, dict) else {}
    n = 0
    for rec in ci.iter_point_cache_files(scenes):
        saved = saved_sims.get(rec.identity)
        if not isinstance(saved, dict):
            continue
        saved_frames = saved.get("frames", {})
        for (_fr, _idx, p) in rec.files:
            if _relkey(p, blend_dir) in saved_frames:
                n += 1
    return n


def verify_sims_iter(scenes, manifest, blend_dir, cancel=None):
    """Generator comparing current point-cache files against ``manifest``.

    Yields ``("file", done_count)`` after each file it hashes — so a modal driver
    can redraw and stay responsive, hashing one frame file per step — and finally
    ``("result", list[SimVerify])``. ``cancel`` is polled between files (and
    inside each file's streaming) and raises :class:`Cancelled`. This is the
    single comparison implementation; the blocking :func:`verify_sims` just drives
    it to completion."""
    from . import cache_inspect as ci
    saved_sims = manifest.get("sims", {}) if isinstance(manifest, dict) else {}
    out = []
    seen = set()
    done = 0
    for rec in ci.iter_point_cache_files(scenes):
        seen.add(rec.identity)
        saved = saved_sims.get(rec.identity)
        cur = {}
        for (fr, _idx, p) in rec.files:
            cur[_relkey(p, blend_dir)] = (fr, p)
        if saved is None:
            out.append(SimVerify(rec.identity, rec.system, rec.obj_name,
                                 S_NO_REF, [], [], [], [], []))
            continue
        saved_frames = saved.get("frames", {}) if isinstance(saved, dict) else {}
        matched, changed, missing, unreadable, new = [], [], [], [], []
        for key, meta in saved_frames.items():
            if key not in cur:
                # A baselined frame file is gone now (range shortened, deleted,
                # or project moved out from under an external path).
                missing.append(key)
                continue
            if cancel is not None and cancel():
                raise Cancelled()
            fr, p = cur[key]
            res = hash_file(p, cancel=cancel)
            if res is None or res is VOLATILE:
                unreadable.append(fr)
            elif res[0] == (meta.get("sha256") if isinstance(meta, dict) else None):
                matched.append(fr)
            else:
                changed.append(fr)
            done += 1
            yield ("file", done)
        for key, (fr, _p) in cur.items():
            if key not in saved_frames:
                new.append(fr)        # a frame present now that wasn't baselined
        state = _sim_state(matched, changed, missing, unreadable, new)
        out.append(SimVerify(rec.identity, rec.system, rec.obj_name, state,
                             sorted(matched), sorted(changed),
                             sorted(_frames_of(missing)), sorted(unreadable),
                             sorted(new)))
    # Sims the baseline knew about but which aren't in the scene now.
    for ident, saved in saved_sims.items():
        if ident in seen:
            continue
        sysname = saved.get("system", "") if isinstance(saved, dict) else ""
        objname = saved.get("obj_name", "") if isinstance(saved, dict) else ""
        out.append(SimVerify(ident, sysname, objname, S_GONE, [], [], [], [], []))
    yield ("result", out)


def verify_sims(scenes, manifest, blend_dir, cancel=None, progress=None):
    """Blocking comparison. Returns a list[:class:`SimVerify`]. Drives
    :func:`verify_sims_iter`; ``progress`` (if given) is called with the running
    file count."""
    result = []
    for ev in verify_sims_iter(scenes, manifest, blend_dir, cancel=cancel):
        if ev[0] == "file" and progress is not None:
            progress(ev[1])
        elif ev[0] == "result":
            result = ev[1]
    return result


def _frames_of(keys):
    """Best-effort frame numbers from relkey filenames (``..._000012_00.bphys``)
    for nicer 'missing frame' messages; falls back to leaving the key out."""
    frames = []
    for k in keys:
        base = k.rsplit("/", 1)[-1]
        parts = base.rsplit("_", 2)
        if len(parts) == 3:
            try:
                frames.append(int(parts[1]))
                continue
            except ValueError:
                pass
    return frames


# --------------------------------------------------------- report wrapper ---

# Top-level verification report. ``state`` gates whether a per-sim comparison was
# even possible; ``sims`` is populated only when state == "ok".
HashReport = collections.namedtuple("HashReport", "state detail sims cancelled")

R_UNSAVED = "unsaved"          # .blend not saved: no place for a baseline
R_NO_BASELINE = "no_baseline"  # no sidecar at all yet
R_UNREADABLE = "unreadable"    # sidecar exists but won't parse
R_SCHEMA = "schema"            # sidecar from a different Failsafe schema
R_FOREIGN = "foreign"          # sidecar was saved for a different .blend
R_NO_SECTION = "no_section"    # sidecar has no cache-hash section (older save)
R_OK = "ok"


def _resolve_manifest():
    """Load and trust-gate the baseline's cache-hash section (mirrors #23/#26).

    Returns ``(terminal_report, None)`` when a gate stops us before any
    comparison (unsaved / no baseline / unreadable / wrong schema / foreign /
    no section), or ``(None, manifest)`` when verification may proceed."""
    import bpy
    path = bl.default_baseline_path()
    if not path:
        return HashReport(R_UNSAVED, "", [], False), None
    try:
        data = bl.load_baseline(path)
    except ValueError as exc:
        if str(exc) == "no baseline file":
            return HashReport(R_NO_BASELINE, "", [], False), None
        return HashReport(R_UNREADABLE, str(exc), [], False), None
    if not bl.schema_ok(data):
        return HashReport(R_SCHEMA, str(data.get("schema")), [], False), None
    foreign = bl.foreign_file_name(data, bpy.data.filepath)
    if foreign:
        return HashReport(R_FOREIGN, foreign, [], False), None
    manifest = data.get("cache_hashes")
    if not isinstance(manifest, dict) or not manifest.get("sims"):
        return HashReport(R_NO_SECTION, "", [], False), None
    return None, manifest


def build_report(scenes, cancel=None, progress=None):
    """Resolve the baseline, gate for trust, and (only if everything checks out)
    verify per-sim. Does the heavy streamed hashing, so the CLI runs it inline and
    the GUI uses :func:`build_report_steps` to stay responsive. Returns a
    :class:`HashReport`.

    Honesty gates mirror checks #23/#26: unsaved file, no baseline, unreadable,
    wrong schema and foreign-file all stop BEFORE any comparison and can never be
    reported as a pass."""
    from . import cache_inspect as ci
    terminal, manifest = _resolve_manifest()
    if terminal is not None:
        return terminal
    try:
        sims = verify_sims(scenes, manifest, ci.blend_dir(),
                           cancel=cancel, progress=progress)
    except Cancelled:
        return HashReport(R_OK, "", [], True)
    return HashReport(R_OK, "", sims, False)


def build_report_steps(scenes, cancel=None):
    """Generator form of :func:`build_report` for a modal GUI driver.

    Yields ``("total", n_files)`` once (the denominator), then ``("file", done)``
    after each hashed file, and finally ``("done", HashReport)``. Hashing one file
    per step lets the operator redraw between steps and honour a cancel, so
    Blender stays responsive even on large caches."""
    from . import cache_inspect as ci
    terminal, manifest = _resolve_manifest()
    if terminal is not None:
        yield ("done", terminal)
        return
    blend_dir = ci.blend_dir()
    yield ("total", verify_total(scenes, manifest, blend_dir))
    try:
        sims = []
        for ev in verify_sims_iter(scenes, manifest, blend_dir, cancel=cancel):
            if ev[0] == "file":
                yield ("file", ev[1])
            elif ev[0] == "result":
                sims = ev[1]
    except Cancelled:
        yield ("done", HashReport(R_OK, "", [], True))
        return
    yield ("done", HashReport(R_OK, "", sims, False))
