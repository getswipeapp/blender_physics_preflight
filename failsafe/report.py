# SPDX-License-Identifier: GPL-3.0-or-later
"""Report builders (shared by the GUI export, the headless CLI and the tests).

Two formats: a human plain-text report and a machine JSON report. Both are pure
functions of the scan ``results`` (plus an optional pre-enumerated cache list for
the disk-size section), so they run identically in the GUI and headless."""
import json

import bpy

from .engine import (CHECKS, Status, GROUP_SETUP, GROUP_CACHE, check_status,
                     summary_counts, display_name)

_ICON = {
    Status.PASS: "[ OK ]",
    Status.WARNING: "[WARN]",
    Status.FAIL: "[FAIL]",
    Status.UNKNOWN: "[ ?? ]",   # "Couldn't verify" — see the note under Summary
    Status.NA: "[ -- ]",
}


def _enumerate_caches_safe(scene=None):
    """Best-effort cache list for the disk-size section. Never raises."""
    try:
        from . import cache_inspect as ci
        if scene is None:
            scene = bpy.context.scene
        return ci.enumerate_caches(scene)
    except Exception:
        return []


def _cache_size_rows(entries):
    """(label, human_size, raw_bytes) for every cache that has a measured size."""
    from . import cache_inspect as ci
    rows = []
    for e in entries or []:
        b = getattr(e, "disk_bytes", None)
        if b is None:
            continue
        rows.append((("%s — %s" % (e.obj_name, e.system)), ci.human_bytes(b), b))
    return rows


def build_text_report(results, entries=None):
    lines = []
    lines.append("Failsafe report")
    lines.append("Blender %s" % bpy.app.version_string)
    fp = bpy.data.filepath or "(unsaved file)"
    lines.append("File: %s" % fp)
    lines.append("=" * 68)

    counts = summary_counts(results)
    lines.append("Summary: %d Fail  %d Warning  %d Couldn't verify  %d Pass  %d N/A"
                 % (counts[Status.FAIL], counts[Status.WARNING],
                    counts[Status.UNKNOWN], counts[Status.PASS], counts[Status.NA]))
    lines.append('("Couldn\'t verify" = not enough evidence to confirm — NOT a '
                 "confirmed problem. Each one says why and what to do.)")
    lines.append("")

    for group in (GROUP_SETUP, GROUP_CACHE):
        lines.append(group)
        lines.append("-" * len(group))
        group_checks = [m for m in CHECKS if m.group == group]
        for m in group_checks:
            st = check_status(results, m)
            lines.append("%s %s" % (_ICON[st], display_name(m, st)))
            for r in [r for r in results if r.check_id == m.id]:
                who = (" (%s)" % r.object_name) if r.object_name else ""
                lines.append("        %s%s: %s" % (_ICON[r.status], who, r.message))
                if r.hint:
                    lines.append("               > %s" % r.hint)
        lines.append("")

    # Disk usage (A4) — "see what your sims weigh", like Cache Commander, but
    # read-only and alongside the correctness checks.
    if entries is None:
        entries = _enumerate_caches_safe()
    rows = _cache_size_rows(entries)
    if rows:
        total = sum(b for _, _, b in rows)
        from . import cache_inspect as ci
        lines.append("Cache disk usage")
        lines.append("-" * len("Cache disk usage"))
        for label, human, _ in sorted(rows, key=lambda r: r[2], reverse=True):
            lines.append("        %-40s %s" % (label, human))
        lines.append("        %-40s %s" % ("TOTAL", ci.human_bytes(total)))
        lines.append("")

    lines.append("=" * 68)
    lines.append("Read-only tool. For disk-backed caches we verify the actual "
                 "files frame by frame rather than trusting Blender's 'baked' "
                 "flag. Memory caches, packed Geometry Nodes bakes and unsaved "
                 "files can't be proven from disk and are reported \"Couldn't "
                 "verify\" / N/A, never a false Pass.")
    return "\n".join(lines)


def build_json_report(results, entries=None):
    """Machine-readable report (A7). A dict, JSON-serialised. Stable shape:

      {
        "tool": "failsafe", "schema": 1,
        "blender": "...", "file": "...",
        "summary": {"FAIL":n,"WARNING":n,"UNKNOWN":n,"PASS":n,"NA":n},
        "overall": "FAIL"|"WARNING"|"UNKNOWN"|"PASS",
        "checks": [ {id,name,group,status,display,findings:[{status,object,message,hint}]} ],
        "cache_disk_usage": {"total_bytes":n,"items":[{object,system,bytes}]}
      }
    """
    counts = summary_counts(results)
    summary = {Status.FAIL: counts[Status.FAIL],
               Status.WARNING: counts[Status.WARNING],
               Status.UNKNOWN: counts[Status.UNKNOWN],
               Status.PASS: counts[Status.PASS],
               Status.NA: counts[Status.NA]}
    # Overall verdict: worst status that actually occurred among real checks.
    if counts[Status.FAIL]:
        overall = Status.FAIL
    elif counts[Status.WARNING]:
        overall = Status.WARNING
    elif counts[Status.UNKNOWN]:
        overall = Status.UNKNOWN
    else:
        overall = Status.PASS

    checks = []
    for m in CHECKS:
        st = check_status(results, m)
        findings = [{"status": r.status, "object": r.object_name,
                     "message": r.message, "hint": r.hint}
                    for r in results if r.check_id == m.id]
        checks.append({"id": m.id, "name": m.name, "group": m.group,
                       "status": st, "display": display_name(m, st),
                       "findings": findings})

    if entries is None:
        entries = _enumerate_caches_safe()
    items = [{"object": e.obj_name, "system": e.system,
              "bytes": getattr(e, "disk_bytes", None)}
             for e in (entries or []) if getattr(e, "disk_bytes", None) is not None]
    data = {
        "tool": "failsafe", "schema": 1,
        "blender": bpy.app.version_string,
        "file": bpy.data.filepath or None,
        "summary": summary,
        "overall": overall,
        "checks": checks,
        "cache_disk_usage": {"total_bytes": sum(i["bytes"] for i in items),
                             "items": items},
    }
    return json.dumps(data, indent=2)
