# SPDX-License-Identifier: GPL-3.0-or-later
"""Crash- and hang-isolated batch scanning for render farms / pipelines.

The in-process batch scanner (``cli.run_batch``) opens every ``.blend`` in the
SAME Blender process. That is fast, but a single corrupt or pathological file can
crash or hang the whole process, taking every other file's result down with it.

This module runs each ``.blend`` in its OWN Blender subprocess with a timeout, so:

  * a crash in one file  -> that file is recorded as an error; the batch continues;
  * a hang in one file   -> the subprocess is killed at the timeout and recorded
                            as a timeout; the batch continues;
  * files that scanned cleanly always keep their results (partial-failure safe).

The orchestration (iterate, time out, aggregate, preserve partial results) is kept
separate from the actual subprocess spawn, so it can be tested deterministically
with a fake ``runner`` — see the batch-isolation tests. Everything here is
read-only: each child only opens and reads its file, and the worst per-file exit
code wins for the batch as a whole (a blocking FAIL or an error never hides
behind a clean file).

Modularity: this is the *pipeline* edition's crash isolation. The consumer GUI
never imports it; it's only reached from the headless CLI.
"""
import glob
import json
import os
import subprocess

from . import cli


# Markers so the parent can pull the JSON result out of a child's stdout even when
# Blender prints its own banner / info lines around it.
_MARK_START = "<<FAILSAFE_JSON_START>>"
_MARK_END = "<<FAILSAFE_JSON_END>>"

DEFAULT_TIMEOUT = 300  # seconds per file


def list_blend_files(folder):
    """Every ``.blend`` under ``folder`` (recursive), sorted."""
    return sorted(glob.glob(os.path.join(folder, "**", "*.blend"),
                            recursive=True))


def _child_import_base():
    """Package import path to use inside the child: the installed extension
    package when installed (e.g. ``bl_ext.user_default.failsafe``), else
    ``failsafe`` when running from source."""
    return __package__ or "failsafe"


def build_child_argv(blender_bin, blend_file, strict=False, source_root=None):
    """Command line that scans ONE ``.blend`` in a fresh, isolated Blender and
    prints its JSON result between markers.

    ``source_root`` (running from source / tests) is put on the child's
    ``sys.path`` with ``--factory-startup`` so ``import failsafe`` resolves to our
    source; otherwise the installed extension is imported (the render-farm case)."""
    base = _child_import_base()
    strict_py = "True" if strict else "False"
    path_inject = ("import sys; sys.path.insert(0, %r)\n" % source_root
                   if source_root else "")
    expr = (
        "%s"
        "import json\n"
        "import bpy\n"
        "from %s import engine as _e, report as _r, cli as _c, "
        "cache_inspect as _ci\n"
        "_res = _e.run_all(bpy.context)\n"
        "try:\n"
        "    _entries = _ci.enumerate_caches(bpy.context.scene)\n"
        "except Exception:\n"
        "    _entries = []\n"
        "_code = _c.verdict_exit_code(_res, %s)\n"
        "_data = json.loads(_r.build_json_report(_res, entries=_entries))\n"
        "_data['exit'] = _code\n"
        "print(%r + json.dumps(_data) + %r)\n"
        % (path_inject, base, strict_py, _MARK_START, _MARK_END)
    )
    argv = [blender_bin, "-b", blend_file]
    if source_root:
        argv.append("--factory-startup")
    argv += ["--python-expr", expr]
    return argv


def subprocess_runner(argv, timeout):
    """Real runner: run the child, return ``(returncode, stdout, stderr)``.

    Raises ``subprocess.TimeoutExpired`` (the process is killed) if it runs longer
    than ``timeout`` seconds."""
    proc = subprocess.run(argv, capture_output=True, text=True, timeout=timeout)
    return proc.returncode, proc.stdout, proc.stderr


def _extract_json(stdout):
    """Pull the marker-delimited JSON object out of a child's stdout, or None."""
    if not stdout:
        return None
    i = stdout.find(_MARK_START)
    if i == -1:
        return None
    j = stdout.find(_MARK_END, i + len(_MARK_START))
    if j == -1:
        return None
    try:
        return json.loads(stdout[i + len(_MARK_START):j])
    except ValueError:
        return None


def scan_file_isolated(blend_file, blender_bin, timeout=DEFAULT_TIMEOUT,
                       strict=False, source_root=None, runner=subprocess_runner):
    """Scan one ``.blend`` in its own subprocess. Returns a per-file dict that is
    always defined — a crash, a hang, or an unreadable file become a recorded
    error (exit 3), never a silent pass and never an exception that aborts the
    batch."""
    argv = build_child_argv(blender_bin, blend_file, strict=strict,
                            source_root=source_root)
    try:
        rc, out, err = runner(argv, timeout)
    except subprocess.TimeoutExpired:
        return {"file": blend_file, "exit": cli.EXIT_USAGE,
                "error": "timed out after %ss — subprocess killed "
                         "(isolated, so the batch continues)" % timeout}
    except Exception as exc:  # could not even launch Blender on this file
        return {"file": blend_file, "exit": cli.EXIT_USAGE,
                "error": "could not run Blender on this file: %s" % exc}

    if rc != 0:
        # A nonzero exit means the worker crashed or aborted. Do NOT trust a
        # report it may have printed just before dying — a child can print clean
        # JSON and then segfault. Record an error, never a pass. (R19)
        tail = (err or out or "").strip().splitlines()
        detail = tail[-1] if tail else "exit code %s" % rc
        return {"file": blend_file, "exit": cli.EXIT_USAGE,
                "error": "worker exited abnormally (rc=%s): %s" % (rc, detail)}

    data = _extract_json(out)
    if data is None:
        # Exited 0 but produced no parseable report. Treat as an error for this
        # file — never as a pass.
        tail = (err or out or "").strip().splitlines()
        detail = tail[-1] if tail else "no report produced (rc=%s)" % rc
        return {"file": blend_file, "exit": cli.EXIT_USAGE,
                "error": "scan produced no result (%s)" % detail}

    code = data.get("exit", cli.EXIT_USAGE)
    # Preserve the actionable per-check findings (incl. exact missing frames) so a
    # farm integration keeps them, not just the summary counts. (R25)
    findings = [c for c in (data.get("checks") or [])
                if c.get("status") not in ("PASS", "NOT APPLICABLE")]
    return {"file": blend_file, "exit": code,
            "overall": data.get("overall"),
            "summary": data.get("summary"),
            "findings": findings,
            "cache_disk_usage": data.get("cache_disk_usage")}


_EXIT_WORD = {cli.EXIT_CLEAN: "clean", cli.EXIT_BLOCKING: "BLOCKING",
              cli.EXIT_UNVERIFIED: "unverified", cli.EXIT_USAGE: "error"}


def format_batch_report(folder, files_count, per_file, agg, as_json):
    """Render the batch result. Same shape as the in-process scanner's, plus an
    ``isolated`` flag so a reader knows each file ran in its own process."""
    if as_json:
        return json.dumps({"tool": "failsafe", "schema": 1, "batch": True,
                           "isolated": True, "folder": folder,
                           "overall_exit": agg, "files": per_file}, indent=2)
    lines = ["Failsafe batch report (isolated — one subprocess per file)",
             "Folder: %s" % folder,
             "Files scanned: %d" % files_count, "=" * 68]
    for pf in per_file:
        if "error" in pf:
            lines.append("[error] %s  (%s)" % (pf["file"], pf["error"]))
        else:
            s = pf.get("summary") or {}
            lines.append("[%s] %s  (%dF %dW %dU)"
                         % (_EXIT_WORD.get(pf["exit"], "?"), pf["file"],
                            s.get("FAIL", 0), s.get("WARNING", 0),
                            s.get("UNKNOWN", 0)))
    lines.append("=" * 68)
    lines.append("Overall: %s" % _EXIT_WORD.get(agg, "?"))
    return "\n".join(lines)


def run_isolated_batch(folder, opts, blender_bin=None, timeout=DEFAULT_TIMEOUT,
                       source_root=None, runner=subprocess_runner):
    """Scan every ``.blend`` under ``folder``, each in its own Blender subprocess
    with a per-file timeout. Returns ``(aggregate_exit_code, output_string)``.

    Crash/hang/corruption in one file is isolated to that file; every other
    file's result is preserved, and the worst exit code wins overall."""
    if blender_bin is None:
        import bpy
        blender_bin = bpy.app.binary_path
    if not os.path.isdir(folder):
        return cli.EXIT_USAGE, "Failsafe: not a folder: %s\n" % folder

    files = list_blend_files(folder)
    if not files:
        # Scanning zero files is NOT a clean result — an empty or wrong folder
        # must never report success. (R20)
        msg = "Failsafe: no .blend files found in %s\n" % folder
        if opts.get("format") == "json":
            msg = json.dumps({"tool": "failsafe", "schema": 1, "batch": True,
                              "isolated": True, "folder": folder,
                              "overall_exit": cli.EXIT_USAGE, "files": [],
                              "error": "no .blend files found"}, indent=2)
        return cli.EXIT_USAGE, msg

    per_file = []
    codes = []
    for f in files:
        pf = scan_file_isolated(f, blender_bin, timeout=timeout,
                                strict=opts.get("strict", False),
                                source_root=source_root, runner=runner)
        per_file.append(pf)
        codes.append(pf["exit"])
    agg = cli.aggregate_exit(codes)
    out = format_batch_report(folder, len(files), per_file, agg,
                              opts.get("format") == "json")
    return agg, out
