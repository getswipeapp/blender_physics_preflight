# SPDX-License-Identifier: GPL-3.0-or-later
"""Plain-text report builder (shared by the GUI export and the test harness)."""
import bpy

from .engine import CHECKS, Status, GROUP_SETUP, GROUP_CACHE, check_status, summary_counts

_ICON = {
    Status.PASS: "[ OK ]",
    Status.WARNING: "[WARN]",
    Status.FAIL: "[FAIL]",
    Status.UNKNOWN: "[ ?? ]",
    Status.NA: "[ -- ]",
}


def build_text_report(results):
    lines = []
    lines.append("Failsafe report")
    lines.append("Blender %s" % bpy.app.version_string)
    fp = bpy.data.filepath or "(unsaved file)"
    lines.append("File: %s" % fp)
    lines.append("=" * 68)

    counts = summary_counts(results)
    lines.append("Summary: %d FAIL  %d WARNING  %d UNKNOWN  %d PASS  %d N/A"
                 % (counts[Status.FAIL], counts[Status.WARNING],
                    counts[Status.UNKNOWN], counts[Status.PASS], counts[Status.NA]))
    lines.append("")

    for group in (GROUP_SETUP, GROUP_CACHE):
        lines.append(group)
        lines.append("-" * len(group))
        group_checks = [m for m in CHECKS if m.group == group]
        for m in group_checks:
            st = check_status(results, m)
            lines.append("%s #%d %s" % (_ICON[st], m.id, m.name))
            for r in [r for r in results if r.check_id == m.id]:
                who = (" (%s)" % r.object_name) if r.object_name else ""
                lines.append("        %s%s: %s" % (_ICON[r.status], who, r.message))
                if r.hint:
                    lines.append("               > %s" % r.hint)
        lines.append("")
    lines.append("=" * 68)
    lines.append("Read-only tool. For disk-backed caches we verify the actual "
                 "files frame by frame rather than trusting Blender's 'baked' "
                 "flag. Memory caches, packed Geometry Nodes bakes and unsaved "
                 "files can't be proven from disk and are reported UNKNOWN / N/A, "
                 "never a false PASS.")
    return "\n".join(lines)
