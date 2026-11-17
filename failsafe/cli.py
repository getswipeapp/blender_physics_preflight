# SPDX-License-Identifier: GPL-3.0-or-later
"""Headless command-line entry point (A6).

Run Failsafe on an open .blend from a render pipeline or a render farm's
pre-flight step, with no window and no person, and get an exit code a build
system can read:

    0  clean          no FAIL and no UNKNOWN (warnings don't block by default)
    1  blocking        at least one FAIL
    2  unverified      no FAIL, but something couldn't be verified (UNKNOWN)
    3  usage/internal  bad arguments or an internal error

With ``--strict``, a WARNING also blocks (exit 1).

Example (extension installed and enabled):

    blender -b shot.blend \\
      --python-expr "import bl_ext.user_default.failsafe.cli as c; c.main()" \\
      -- --json --strict

Example (running the source package directly, e.g. in tests/CI):

    blender -b shot.blend --python-expr "import failsafe.cli as c; c.main()" -- --text

Everything here is read-only: it never writes to the scene or the .blend. It only
prints a report to stdout and sets the exit code.
"""
import sys

from . import engine, report


EXIT_CLEAN = 0
EXIT_BLOCKING = 1
EXIT_UNVERIFIED = 2
EXIT_USAGE = 3


def _parse_args(argv):
    """Parse the args that follow ``--`` on the Blender command line."""
    opts = {"format": "text", "strict": False, "batch": None,
            "isolated": True, "timeout": 300, "verify_hashes": False}
    expect_batch = False
    expect_timeout = False
    for a in argv:
        if expect_batch:
            opts["batch"] = a
            expect_batch = False
            continue
        if expect_timeout:
            opts["timeout"] = _parse_timeout(a)
            expect_timeout = False
            continue
        if a in ("--json", "-j"):
            opts["format"] = "json"
        elif a in ("--html",):
            opts["format"] = "html"
        elif a in ("--text", "-t"):
            opts["format"] = "text"
        elif a in ("--strict", "-s"):
            opts["strict"] = True
        elif a in ("--help", "-h"):
            opts["format"] = "help"
        elif a in ("--batch", "-b"):
            expect_batch = True
        elif a.startswith("--batch="):
            opts["batch"] = a.split("=", 1)[1]
        elif a == "--in-process":
            # Opt out of per-file subprocess isolation (faster, but one bad file
            # can crash the whole batch). Isolation is the default for farms.
            opts["isolated"] = False
        elif a == "--verify-hashes":
            # Re-hash every baked frame and compare to the baseline (#27). Off by
            # default because it reads every cache byte (can be gigabytes).
            opts["verify_hashes"] = True
        elif a == "--timeout":
            expect_timeout = True
        elif a.startswith("--timeout="):
            opts["timeout"] = _parse_timeout(a.split("=", 1)[1])
        else:
            raise ValueError("unknown argument: %s" % a)
    if expect_batch:
        raise ValueError("--batch needs a folder path")
    if expect_timeout:
        raise ValueError("--timeout needs a number of seconds")
    return opts


def _parse_timeout(s):
    try:
        v = int(s)
    except (TypeError, ValueError):
        raise ValueError("--timeout must be a whole number of seconds: %r" % s)
    if v <= 0:
        raise ValueError("--timeout must be greater than 0 seconds")
    return v


def _args_after_dashdash():
    argv = list(sys.argv)
    if "--" in argv:
        return argv[argv.index("--") + 1:]
    return []


_HELP = (
    "Failsafe headless check\n"
    "  --text            human-readable report (default)\n"
    "  --json            machine-readable JSON report\n"
    "  --html            self-contained HTML report (single file; batch uses text/json)\n"
    "  --strict          treat WARNING as blocking (exit 1)\n"
    "  --batch <folder>  scan every .blend in a folder (recursively)\n"
    "  --timeout <secs>  per-file timeout in isolated batch mode (default 300)\n"
    "  --in-process      batch in one process (faster; NOT crash-isolated)\n"
    "  --verify-hashes   also re-hash every baked frame vs the baseline (#27;\n"
    "                    reads every cache byte — can be slow on big caches)\n"
    "  --help            this message\n"
    "Exit codes: 0 clean, 1 blocking (FAIL), 2 unverified (UNKNOWN), 3 usage.\n"
    "Batch mode must be run WITHOUT a .blend on the command line, e.g.\n"
    "  blender -b --python-expr \"import bl_ext.user_default.failsafe.cli as c; "
    "c.main()\" -- --batch /shots --json\n"
)


def verdict_exit_code(results, strict=False):
    counts = engine.summary_counts(results)
    if counts[engine.Status.FAIL]:
        return EXIT_BLOCKING
    if strict and counts[engine.Status.WARNING]:
        return EXIT_BLOCKING
    if counts[engine.Status.UNKNOWN]:
        return EXIT_UNVERIFIED
    return EXIT_CLEAN


# When several files are scanned, combine their codes by severity priority:
# a blocking FAIL anywhere wins, then a usage/internal error, then unverified,
# else clean.
_EXIT_PRIORITY = {EXIT_BLOCKING: 3, EXIT_USAGE: 2, EXIT_UNVERIFIED: 1,
                  EXIT_CLEAN: 0}


def aggregate_exit(codes):
    """Worst exit code across a batch, by severity priority. [] -> clean."""
    worst = EXIT_CLEAN
    for c in codes:
        if _EXIT_PRIORITY.get(c, 0) > _EXIT_PRIORITY.get(worst, 0):
            worst = c
    return worst


def _hash_report(opts):
    """Compute the on-demand cache-hash verification when --verify-hashes is set,
    else None. Isolated so a hashing error never aborts the whole scan — but a
    requested verification that fails must NOT masquerade as 'not run' (which would
    permit a false exit 0, review B1). On error we return an R_ERROR report, which
    #27 renders as 'Couldn't verify' and verify_floor escalates the exit code."""
    if not opts.get("verify_hashes"):
        return None
    from . import cachehash
    try:
        import bpy
        return cachehash.build_report(list(bpy.data.scenes))
    except Exception as exc:
        return cachehash.HashReport(cachehash.R_ERROR, str(exc)[:200], [], False)


def verify_floor(report, requested):
    """The minimum exit code the CLI must honour after a cache-hash verification.

    When the user asked to verify (``--verify-hashes``) but the verification did
    not fully resolve every saved reference, the scan must NOT report a clean exit
    0 (reviews B1/B4/B5). That covers two layers:

      * the report never reached a per-sim comparison — no baseline, unreadable /
        foreign / wrong-schema sidecar, an internal error, or a cancel (B1); and
      * it DID compare (``R_OK``) but some simulation outcome is unresolved — a
        reference whose frames couldn't be read, required frames that were never
        fingerprinted, a sim with no / empty reference, or a baselined sim that is
        gone from the scene (B5). A changed-file WARNING must never let one of
        these slip out as exit 0 (B4).

    Returns EXIT_UNVERIFIED as a floor in those cases, else EXIT_CLEAN (every
    reference resolved; a detected change is a WARNING, not an error). ``requested``
    False (or no report) imposes no floor."""
    from . import cachehash as ch
    if not requested or report is None:
        return EXIT_CLEAN
    if report.cancelled or report.state != ch.R_OK:
        return EXIT_UNVERIFIED
    unresolved = {ch.S_UNREADABLE, ch.S_INCOMPLETE_REF, ch.S_NO_REF,
                  ch.S_EMPTY_REF, ch.S_GONE}
    for sv in report.sims:
        # sv.uncovered / sv.unreadable catch frames masked under a CHANGED (or
        # other) headline state; the state set catches whole-sim gaps.
        if sv.state in unresolved or sv.uncovered or sv.unreadable:
            return EXIT_UNVERIFIED
    return EXIT_CLEAN


def _scan_current(context, opts):
    """Scan the open scene. Returns (exit_code, output_string)."""
    hr = _hash_report(opts)
    results = engine.run_all(context, hash_verify=hr)
    from . import cache_inspect as ci
    try:
        entries = ci.enumerate_caches(context.scene)
    except Exception:
        entries = []
    if opts["format"] == "json":
        out = report.build_json_report(results, entries=entries)
    elif opts["format"] == "html":
        out = report.build_html_report(results, entries=entries)
    else:
        out = report.build_text_report(results, entries=entries)
    # A requested-but-failed verification must never yield a clean exit 0 (B1).
    code = aggregate_exit([verdict_exit_code(results, opts["strict"]),
                           verify_floor(hr, opts.get("verify_hashes"))])
    return code, out


def _list_blend_files(folder):
    import glob
    import os
    return sorted(glob.glob(os.path.join(folder, "**", "*.blend"),
                            recursive=True))


def run_batch(folder, opts):
    """Open and scan every .blend under ``folder`` (read-only — it only reads
    each file). Returns (aggregate_exit_code, output_string).

    Run this WITHOUT a .blend on the command line; it opens each file itself."""
    import json as _json
    import os
    import bpy
    from . import cache_inspect as ci

    if not os.path.isdir(folder):
        return EXIT_USAGE, "Failsafe: not a folder: %s\n" % folder
    files = _list_blend_files(folder)
    if not files:
        # Zero files scanned is never a clean result. (R20)
        if opts["format"] == "json":
            return EXIT_USAGE, _json.dumps(
                {"tool": "failsafe", "schema": 1, "batch": True, "folder": folder,
                 "overall_exit": EXIT_USAGE, "files": [],
                 "error": "no .blend files found"}, indent=2)
        return EXIT_USAGE, "Failsafe: no .blend files found in %s\n" % folder
    per_file = []
    codes = []
    for f in files:
        try:
            res = bpy.ops.wm.open_mainfile(filepath=f, load_ui=False)
            # Some failures report an error and return CANCELLED instead of
            # raising; treat anything but FINISHED as a failed open so a bad file
            # is never silently scanned as the previously-loaded scene.
            if "FINISHED" not in res:
                raise RuntimeError("could not open (result: %s)"
                                   % ", ".join(sorted(res)))
            hr = _hash_report(opts)
            results = engine.run_all(bpy.context, hash_verify=hr)
            try:
                entries = ci.enumerate_caches(bpy.context.scene)
            except Exception:
                entries = []
            # A requested-but-failed verification floors this file's code (B1).
            code = aggregate_exit([verdict_exit_code(results, opts["strict"]),
                                   verify_floor(hr, opts.get("verify_hashes"))])
            data = _json.loads(report.build_json_report(results, entries=entries))
            per_file.append({"file": f, "exit": code,
                             "overall": data["overall"],
                             "summary": data["summary"],
                             "cache_disk_usage": data["cache_disk_usage"]})
        except Exception as exc:
            code = EXIT_USAGE
            per_file.append({"file": f, "exit": code, "error": str(exc)})
        codes.append(code)
    agg = aggregate_exit(codes)

    if opts["format"] == "json":
        out = _json.dumps({"tool": "failsafe", "schema": 1, "batch": True,
                           "folder": folder, "overall_exit": agg,
                           "files": per_file}, indent=2)
    else:
        lines = ["Failsafe batch report", "Folder: %s" % folder,
                 "Files scanned: %d" % len(files), "=" * 68]
        label = {EXIT_CLEAN: "clean", EXIT_BLOCKING: "BLOCKING",
                 EXIT_UNVERIFIED: "unverified", EXIT_USAGE: "error"}
        for pf in per_file:
            if "error" in pf:
                lines.append("[error] %s  (%s)" % (pf["file"], pf["error"]))
            else:
                s = pf["summary"]
                lines.append("[%s] %s  (%dF %dW %dU)"
                             % (label.get(pf["exit"], "?"), pf["file"],
                                s["FAIL"], s["WARNING"], s["UNKNOWN"]))
        lines.append("=" * 68)
        lines.append("Overall: %s" % label.get(agg, "?"))
        out = "\n".join(lines)
    return agg, out


def run(argv=None, context=None):
    """Run the checks headless. Returns (exit_code, output_string).

    Does not exit the process — ``main()`` does that. Safe to call from tests."""
    try:
        opts = _parse_args(_args_after_dashdash() if argv is None else argv)
    except ValueError as exc:
        return EXIT_USAGE, "Failsafe: %s\n\n%s" % (exc, _HELP)
    if opts["format"] == "help":
        return EXIT_USAGE, _HELP
    try:
        import bpy
        if opts.get("batch"):
            if opts.get("isolated", True):
                # Default: each file in its own Blender subprocess with a timeout,
                # so a corrupt/hanging file can't take the whole batch down.
                from . import batch
                return batch.run_isolated_batch(
                    opts["batch"], opts, timeout=opts.get("timeout", 300))
            return run_batch(opts["batch"], opts)
        if context is None:
            context = bpy.context
        return _scan_current(context, opts)
    except Exception as exc:  # never let the CLI crash without a defined code
        import traceback
        return EXIT_USAGE, "Failsafe internal error: %s\n%s" % (
            exc, traceback.format_exc()[-800:])


def main(argv=None):
    """Entry point for ``blender -b ... --python-expr "...cli.main()"``.

    Prints the report and exits with the verdict code."""
    code, out = run(argv)
    sys.stdout.write(out)
    if not out.endswith("\n"):
        sys.stdout.write("\n")
    sys.stdout.flush()
    sys.exit(code)
