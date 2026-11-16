# SPDX-License-Identifier: GPL-3.0-or-later
"""Report builders (shared by the GUI export, the headless CLI and the tests).

Three formats: a human plain-text report, a machine JSON report and a self-contained
HTML report. All are pure functions of the scan ``results`` (plus an optional
pre-enumerated cache list for the disk-size section), so they run identically in the
GUI and headless."""
import html
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

# (label, css-slug) per status, for the HTML report.
_HTML_STATUS = {
    Status.PASS:    ("Pass", "pass"),
    Status.WARNING: ("Warning", "warn"),
    Status.FAIL:    ("Fail", "fail"),
    Status.UNKNOWN: ("Couldn’t verify", "unknown"),
    Status.NA:      ("N/A", "na"),
}

_HTML_CSS = """
:root{color-scheme:light}
*{box-sizing:border-box}
body{margin:0;background:#f4f5f7;color:#1c1f24;font:15px/1.5 -apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif}
.wrap{max-width:820px;margin:0 auto;padding:28px 20px 56px}
.verdict{font-size:22px;font-weight:700;color:#fff;padding:16px 20px;border-radius:12px;margin:0 0 14px}
.v-fail{background:#c0392b}.v-warn{background:#c8860a}.v-unknown{background:#2f6fb0}.v-pass{background:#2e8b57}.v-na{background:#6b7280}
.meta{color:#5b6672;margin:0 0 4px}
.summary{font-size:16px;margin:0 0 6px}
.note{color:#5b6672;font-size:13px;margin:0 0 20px}
h2{font-size:14px;text-transform:uppercase;letter-spacing:.04em;color:#5b6672;border-bottom:1px solid #dce0e6;padding-bottom:6px;margin:26px 0 10px}
.check{background:#fff;border:1px solid #e3e7ec;border-left-width:4px;border-radius:8px;padding:10px 14px;margin:0 0 8px}
.c-fail{border-left-color:#c0392b}.c-warn{border-left-color:#c8860a}.c-unknown{border-left-color:#2f6fb0}.c-pass{border-left-color:#2e8b57}.c-na{border-left-color:#c2c8d0}
.badge{display:inline-block;font-size:11px;font-weight:700;color:#fff;border-radius:999px;padding:2px 8px}
.b-fail{background:#c0392b}.b-warn{background:#c8860a}.b-unknown{background:#2f6fb0}.b-pass{background:#2e8b57}.b-na{background:#9aa2ad}
.title{font-weight:600;margin-left:6px}
.findings{list-style:none;margin:8px 0 2px;padding:0}
.findings li{padding:4px 0 4px 2px;font-size:14px;border-top:1px solid #f0f2f5}
.obj{font-weight:600}
.hint{color:#5b6672;font-size:13px;margin:2px 0 2px 14px}
.usage{border-collapse:collapse;width:100%;font-size:14px}
.usage td{padding:5px 8px;border-bottom:1px solid #eceef1}
.usage .num{text-align:right;font-variant-numeric:tabular-nums}
.usage .total td{font-weight:700;border-top:2px solid #cfd4da}
.foot{color:#7a828c;font-size:12px;margin-top:26px;border-top:1px solid #dce0e6;padding-top:12px}
""".strip()


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


def _overall(counts):
    """Worst status that actually occurred among real checks (shared by JSON/HTML)."""
    if counts[Status.FAIL]:
        return Status.FAIL
    if counts[Status.WARNING]:
        return Status.WARNING
    if counts[Status.UNKNOWN]:
        return Status.UNKNOWN
    return Status.PASS


def build_html_report(results, entries=None):
    """Self-contained, offline HTML report (no external CSS/JS/fonts). Verdict-first,
    like Cache Commander's HTML, but read-only and alongside the correctness checks.
    Pure function of ``results`` so it runs identically in the GUI and headless."""
    e = html.escape
    counts = summary_counts(results)
    overall = _overall(counts)
    _, oslug = _HTML_STATUS[overall]
    headline = {Status.FAIL: "Not ready to render",
                Status.WARNING: "Review before rendering",
                Status.UNKNOWN: "Couldn’t fully verify",
                Status.PASS: "All clear"}[overall]

    out = []
    out.append("<!DOCTYPE html>")
    out.append('<html lang="en"><head><meta charset="utf-8">')
    out.append('<meta name="viewport" content="width=device-width, initial-scale=1">')
    out.append("<title>Failsafe report</title>")
    out.append("<style>%s</style>" % _HTML_CSS)
    out.append("</head><body><div class=\"wrap\">")
    out.append('<div class="verdict v-%s">%s</div>' % (oslug, e(headline)))
    out.append('<p class="meta">Blender %s &middot; File: %s</p>'
               % (e(bpy.app.version_string), e(bpy.data.filepath or "(unsaved file)")))
    out.append('<p class="summary"><b>%d</b> Fail &middot; <b>%d</b> Warning &middot; '
               '<b>%d</b> Couldn’t verify &middot; <b>%d</b> Pass &middot; '
               '<b>%d</b> N/A</p>'
               % (counts[Status.FAIL], counts[Status.WARNING], counts[Status.UNKNOWN],
                  counts[Status.PASS], counts[Status.NA]))
    out.append('<p class="note">“Couldn’t verify” means there was not enough '
               'evidence to confirm — it is <b>not</b> a confirmed problem. Each one '
               'says why and what to do.</p>')

    for group in (GROUP_SETUP, GROUP_CACHE):
        out.append('<h2>%s</h2>' % e(group))
        for m in [m for m in CHECKS if m.group == group]:
            st = check_status(results, m)
            label, slug = _HTML_STATUS[st]
            out.append('<div class="check c-%s">' % slug)
            out.append('<span class="badge b-%s">%s</span>'
                       '<span class="title">%s</span>'
                       % (slug, e(label), e(display_name(m, st))))
            frs = [r for r in results if r.check_id == m.id]
            if frs:
                out.append('<ul class="findings">')
                for r in frs:
                    who = ('<span class="obj">%s</span> ' % e(r.object_name)
                           if r.object_name else "")
                    out.append('<li>%s%s' % (who, e(r.message)))
                    if r.hint:
                        out.append('<div class="hint">%s</div>' % e(r.hint))
                    out.append('</li>')
                out.append('</ul>')
            out.append('</div>')

    if entries is None:
        entries = _enumerate_caches_safe()
    rows = _cache_size_rows(entries)
    if rows:
        from . import cache_inspect as ci
        total = sum(b for _, _, b in rows)
        out.append('<h2>Cache disk usage</h2>')
        out.append('<table class="usage"><tbody>')
        for label, human, _b in sorted(rows, key=lambda r: r[2], reverse=True):
            out.append('<tr><td>%s</td><td class="num">%s</td></tr>'
                       % (e(label), e(human)))
        out.append('<tr class="total"><td>TOTAL</td><td class="num">%s</td></tr>'
                   % e(ci.human_bytes(total)))
        out.append('</tbody></table>')

    out.append('<p class="foot">Read-only tool. For disk-backed caches we verify the '
               'actual files frame by frame rather than trusting Blender’s '
               '“baked” flag. Memory caches, packed Geometry Nodes bakes and '
               'unsaved files can’t be proven from disk and are reported '
               '“Couldn’t verify” / N/A, never a false Pass.</p>')
    out.append('</div></body></html>')
    return "\n".join(out)
