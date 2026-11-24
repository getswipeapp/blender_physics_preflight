"""Certification-gate verdict — shared by the macOS and Windows test gates.

A suite run earns a PASS for one Blender version ONLY if its log proves the
suite ran to completion AND every test passed. The following are each a hard
FAILURE, even when Blender exits with code 0 (it does exactly that on a Python
``SystemError``, which is how a crashed Blender 4.2.9 fluid run used to be read
as a pass):

  * no completion sentinel                   -> the suite aborted/crashed
  * measurement-mode output (R19-1)          -> a non-certifiable run; rejected
  * no expected= inventory declaration (R19-1) -> a run that did not commit to a
                                                fixed test count cannot certify
                                                (this is how measurement mode and
                                                any pre-R19 output are refused)
  * any recorded test FAILURE/ERROR          -> failed != 0
  * inconsistent / short / wrong-count run   -> passed+failed != total, total==0,
                                                total below the floor, or
                                                total/passed != declared expected
  * wrong Blender version for the slot (R18-2) -> sentinel version != --version
  * a Python traceback / ViewLayer SystemError anywhere in the log
  * missing 'N passed, M failed, T total' summary line
  * a nonzero process exit code (when provided)

The whole point is that a green verdict can never rest on the process exit code
alone, and can never rest on a run that declined to declare how many tests it
should contain. ``evaluate_log`` is importable (the in-suite
``gate_selfcheck_tests`` regression calls it on crafted logs); run as a script it
is the CLI the gates invoke. The same function gates the main suite
(SUITE_DONE) and the Windows functional-acceptance run (ACCEPT_DONE) via
``sentinel_keyword`` — so acceptance gets the identical fixed-inventory
protection (R19-2), defeating a 0-passed/0-failed/0-total short run.

``require_marker`` (R18-3) is the sibling verdict for non-suite certification
steps (e.g. the Windows REAL multi-process batch proof) that do not emit a
sentinel but DO print an exact end-of-run success marker. It fails closed the
same way: the required marker must be present, no crash signature or forbidden
marker may appear, and the exit code (when given) must be 0.

Usage:
    python gate_check.py <logfile> [--exit-code N] [--min-total N] [--version LBL]
                         [--sentinel SUITE_DONE|ACCEPT_DONE]
    python gate_check.py <logfile> --marker "EXACT SUCCESS MARKER" \
        [--forbid "FORBIDDEN MARKER" ...] [--exit-code N]
"""
import json
import re
import sys

# Field layout shared by every certification sentinel. ``expected=`` is captured
# optionally so a MISSING declaration can be detected and rejected (R19-1) rather
# than silently tolerated; it is NOT optional for certification.
_SENTINEL_TMPL = (
    r"%s version=(?P<version>\S+) passed=(?P<passed>\d+) "
    r"failed=(?P<failed>\d+) total=(?P<total>\d+)"
    r"(?: expected=(?P<expected>\d+))? "
    r"consistent=(?P<consistent>\w+) ok=(?P<ok>\w+)")

SUMMARY_RE = re.compile(r"\b\d+ passed, \d+ failed, \d+ total\b")

# Fatal crash signatures. Verified absent from clean passing runs on
# 4.5.9 / 5.0.1 / 5.2.3, so their presence always means a real crash.
CRASH_SIGNATURES = (
    "Traceback (most recent call last)",
    "getDataPointer",
    "ViewLayer.update()> returned a result with an exception",
)

# A run emitted in measurement mode (inventory NOT enforced). Its presence is a
# hard rejection: measurement must stay possible WITHOUT earning certification.
MEASURE_MARKERS = (
    "SUITE_MEASURE_ONLY",
    "ACCEPT_MEASURE_ONLY",
)

# The display token build_json_report emits for a check that produced NO result.
# An all-NA report means engine.run_all returned nothing for every check: the 27
# JSON entries are just the static registry, with zero evidence any check ran
# (R21-2). build_json_report always lists all 27 REGISTERED checks, so "27
# entries" alone never proves 27 checks executed.
_NA_DISPLAY = "NOT APPLICABLE"

# Stable marker a report carries when a registered check RAISED inside
# engine.run_all: that check's one finding has this message (engine
# CHECK_INTERNAL_ERROR_MSG begins with it). It is a REAL execution failure, NOT a
# legitimate "Couldn't verify" UNKNOWN, so a report carrying it is not a
# certifiable scan (R22). Detection anchors on this stable MESSAGE, never on the
# traceback text — engine truncates the traceback to its tail and a long one
# loses its "Traceback (most recent call last)" header, so a traceback-only check
# could miss it; the message is always present whatever the traceback length.
CHECK_INTERNAL_ERROR = "This check could not run (internal error)"

# Distinguishes "caller passed declared_code=None" from "caller passed nothing".
_UNSET = object()


def _sentinel_re(keyword):
    return re.compile(_SENTINEL_TMPL % re.escape(keyword))


class Verdict:
    def __init__(self, ok, reasons, info):
        self.ok = ok
        self.reasons = reasons
        self.info = info


def evaluate_log(text, exit_code=None, min_total=1, expected_version=None,
                 sentinel_keyword="SUITE_DONE", require_expected=True):
    """Return a Verdict for one completion log. ``ok`` is True only if the run is
    a genuine, complete, all-passing run that declared and met a fixed test
    inventory."""
    reasons = []
    info = {}

    for sig in CRASH_SIGNATURES:
        if sig in text:
            reasons.append("crash signature present: %r" % sig)
    # R19-1: measurement-mode output can never certify, whatever else it says.
    for mk in MEASURE_MARKERS:
        if mk in text:
            reasons.append("measurement-mode marker present (%s): not a "
                           "certifiable run" % mk)

    matches = list(_sentinel_re(sentinel_keyword).finditer(text))
    if not matches:
        reasons.append("no %s completion sentinel (suite did not finish or ran "
                       "in a non-certifiable mode)" % sentinel_keyword)
        if exit_code is not None and int(exit_code) != 0:
            reasons.append("process exit code %s != 0" % exit_code)
        return Verdict(False, reasons, info)
    if len(matches) > 1:
        reasons.append("multiple %s sentinels (%d)"
                       % (sentinel_keyword, len(matches)))

    m = matches[-1]
    passed = int(m.group("passed"))
    failed = int(m.group("failed"))
    total = int(m.group("total"))
    expected = int(m.group("expected")) if m.group("expected") is not None else None
    consistent = m.group("consistent") == "yes"
    ok_flag = m.group("ok") == "yes"
    version = m.group("version")
    info.update(passed=passed, failed=failed, total=total, version=version,
                expected=expected, consistent=consistent, ok=ok_flag)

    if failed != 0:
        reasons.append("%d test(s) failed" % failed)
    if passed + failed != total:
        reasons.append("count mismatch: passed+failed=%d != total=%d"
                       % (passed + failed, total))
    if not consistent:
        reasons.append("suite reported inconsistent count")
    if not ok_flag:
        reasons.append("suite self-reported ok=no")
    if total < min_total:
        reasons.append("total=%d below expected minimum %d (incomplete suite)"
                       % (total, min_total))
    # R18-1 / R19-1: the run must declare its expected inventory as expected=,
    # and the live count must match it exactly. A missing expected= (measurement
    # mode, or any run that declined to commit to a count) is itself fatal, so a
    # shortened run can no longer ride under the floor by omitting the field.
    if expected is None:
        if require_expected:
            reasons.append("no expected= inventory declaration "
                           "(measurement-mode or pre-R19 output cannot certify)")
    else:
        if total != expected:
            reasons.append("test-inventory mismatch: total=%d != declared expected=%d"
                           % (total, expected))
        if passed != expected:
            reasons.append("test-inventory mismatch: passed=%d != declared expected=%d"
                           % (passed, expected))
    # R18-2: the slot must have run the Blender version it claims to certify.
    if expected_version and version != expected_version:
        reasons.append("version mismatch: log=%s expected=%s"
                       % (version, expected_version))
    if not SUMMARY_RE.search(text):
        reasons.append("no 'N passed, M failed, T total' summary line")
    if exit_code is not None and int(exit_code) != 0:
        reasons.append("process exit code %s != 0" % exit_code)

    return Verdict(len(reasons) == 0, reasons, info)


def require_marker(text, marker, forbidden=(), exit_code=None):
    """R18-3: fail-closed verdict for a certification step that prints an exact
    end-of-run success marker instead of a sentinel (e.g. the Windows REAL batch
    proof). ``ok`` is True only if the required marker is present AND no crash
    signature or forbidden marker appears AND the exit code (if given) is 0. A
    script that crashes before printing its marker while Blender exits 0 is
    therefore rejected, not passed on the exit code."""
    reasons = []
    info = {"marker": marker}
    for sig in CRASH_SIGNATURES:
        if sig in text:
            reasons.append("crash signature present: %r" % sig)
    for bad in forbidden:
        if bad and bad in text:
            reasons.append("forbidden marker present: %r" % bad)
    if marker not in text:
        reasons.append("required completion marker absent: %r" % marker)
    if exit_code is not None and int(exit_code) != 0:
        reasons.append("process exit code %s != 0" % exit_code)
    return Verdict(len(reasons) == 0, reasons, info)


def valid_cli_report(returncode, text, expected_checks=27, min_executed=1,
                     allowed_codes=(0,), child_stderr="", declared_code=_UNSET,
                     required_ids=None):
    """A CLI scan child counts as a genuine, complete scan ONLY if ALL hold:

      * R20-1: it produced a complete, valid Failsafe JSON report (parses, is a
        dict, tool=="failsafe", exactly ``expected_checks`` checks, a non-empty
        summary, no ``error`` key, no "Failsafe internal error"). Verified real
        behaviour: a ``blender -b --python-expr`` child that raises a Python
        error still EXITS 0, so the exit code alone can never prove the scan ran.
      * R21-1: the REAL process exit code (``returncode``) — NOT a child-written
        sidecar — is an accepted verdict (``allowed_codes``), and when a
        ``declared_code`` sidecar is supplied it must AGREE with the real exit. A
        crash can write a sidecar of 0 then exit; a traceback it leaves on stderr
        used to be discarded, so ``child_stderr`` is scanned for crash signatures
        too, not just the report body.
      * R21-2: at least ``min_executed`` checks actually EXECUTED (status other
        than "NOT APPLICABLE"). build_json_report always lists all 27 REGISTERED
        checks, so a zero-result scan (engine.run_all()==[], or a no-op scan of an
        empty scene) still yields 27 entries, an all-N/A summary and exit 0 — and
        would otherwise be accepted. The summary's non-N/A tally must also match
        the checks array, so a forged summary cannot fake execution. Legitimate
        individual N/A results are preserved; only the all-N/A case is rejected.
      * R22-1: when ``required_ids`` is given, EVERY one of those registered check
        ids must have EXECUTED (non-N/A) in this report. ``min_executed`` alone
        only proves *some* check ran, so a partial scan that ran just one of 27
        (e.g. engine.run_all returning a single Result) still passed. A fixture
        the caller controls is known to exercise a specific SET of checks;
        requiring that whole set rejects a scan that ran fewer, because the
        missing checks are still N/A and "27 listed" never proves they ran.
      * R22: a report carrying the per-check internal-error marker
        (``CHECK_INTERNAL_ERROR`` — a registered check RAISED) is rejected. This
        is distinct from a legitimate "Couldn't verify" UNKNOWN, which is
        preserved; only a genuine internal execution failure is rejected, and the
        detection does not depend on the (truncatable) traceback text.

    ``allowed_codes`` defaults to ``(0,)`` (a clean verdict); a real scan of a
    fixture that legitimately WARNs/UNKNOWNs reaches a defined verdict (1/2) and
    callers may widen the set — the exit code is a sanity cross-check, never the
    proof of success."""
    reasons = []
    info = {}
    # R21-1: the real process exit code is authoritative, not a child-written
    # sidecar. Require a defined, accepted verdict and (if a sidecar was written)
    # that it agrees with what the process actually returned.
    if returncode is None or int(returncode) not in allowed_codes:
        reasons.append("exit code %s is not an accepted clean verdict %s"
                       % (returncode, tuple(allowed_codes)))
    if declared_code is not _UNSET and declared_code is not None \
            and returncode is not None:
        try:
            if int(declared_code) != int(returncode):
                reasons.append("child-written exit code %s disagrees with the "
                               "real process exit %s (R21-1)"
                               % (declared_code, returncode))
        except (TypeError, ValueError):
            reasons.append("child-written exit code %r is not an integer"
                           % (declared_code,))
    # R21-1: a crash can leave a valid-looking report but a traceback on stderr,
    # which the parent used to throw away. Inspect report body AND child output.
    blob = text + "\n" + (child_stderr or "")
    for sig in CRASH_SIGNATURES:
        if sig in blob:
            reasons.append("crash signature present: %r" % sig)
    if "Failsafe internal error" in blob:
        reasons.append("CLI reported an internal error")
    # R22: a registered check that RAISED is reported as an UNKNOWN finding with
    # this stable message. That is a real execution failure, not a legitimate
    # "Couldn't verify" UNKNOWN, so the scan cannot certify. Anchored on the
    # message (not the traceback, which engine truncates and can lose its header).
    if CHECK_INTERNAL_ERROR in blob:
        reasons.append("a registered check hit an internal error (not a "
                       "legitimate UNKNOWN): %r (R22)" % CHECK_INTERNAL_ERROR)
    if not text.strip():
        reasons.append("empty report (the scan produced no output)")
        return Verdict(False, reasons, info)
    try:
        jd = json.loads(text)
    except Exception as e:
        reasons.append("report is not valid JSON: %s" % e)
        return Verdict(False, reasons, info)
    if not isinstance(jd, dict):
        reasons.append("report is not a JSON object")
        return Verdict(False, reasons, info)
    if jd.get("tool") != "failsafe":
        reasons.append("missing failsafe tool marker")
    checks = jd.get("checks")
    n = len(checks) if isinstance(checks, list) else -1
    info["checks"] = n
    if n != expected_checks:
        reasons.append("report has %s checks, expected %d" % (n, expected_checks))
    summary = jd.get("summary")
    if not isinstance(summary, dict) or not summary:
        reasons.append("report missing summary")
    if jd.get("error"):
        reasons.append("report carries an error: %r" % jd.get("error"))
    # R21-2: prove checks actually executed, not merely that 27 registry entries
    # were listed. Count the checks that reached a real verdict (non-N/A); an
    # all-N/A report is exactly what engine.run_all()==[] produces and is no
    # evidence the scan ran.
    if isinstance(checks, list):
        executed = sum(1 for c in checks if isinstance(c, dict)
                       and c.get("status") != _NA_DISPLAY)
        findings = sum(len(c.get("findings") or []) for c in checks
                       if isinstance(c, dict))
        info["executed"] = executed
        info["findings"] = findings
        if executed < min_executed:
            reasons.append("report shows %d executed (non-N/A) checks (< %d): an "
                           "all-N/A report is not evidence the scan ran (R21-2)"
                           % (executed, min_executed))
        # Integrity: a report cannot claim execution in the summary that the
        # checks array denies (or vice versa).
        if isinstance(summary, dict):
            try:
                non_na = sum(int(v) for k, v in summary.items()
                             if k != _NA_DISPLAY)
                if non_na != executed:
                    reasons.append("summary non-N/A total %d disagrees with %d "
                                   "executed checks (R21-2)" % (non_na, executed))
            except (TypeError, ValueError):
                reasons.append("summary counts are not integers")
        # R22-1: a count floor (min_executed) only proves SOME check ran, so a
        # 1-of-27 partial scan still passed. The fixture the caller scans is known
        # to exercise a specific SET of checks; require every one of them to have
        # executed (non-N/A), so a scan that ran fewer is rejected — the missing
        # ids are still N/A and "27 listed" never proves they ran.
        if required_ids:
            executed_ids = {c.get("id") for c in checks if isinstance(c, dict)
                            and c.get("status") != _NA_DISPLAY}
            missing = sorted(i for i in required_ids if i not in executed_ids)
            info["required_missing"] = missing
            if missing:
                reasons.append("required checks did not execute (still N/A): %s — "
                               "a 27-entry report does not prove these ran (R22-1)"
                               % missing)
    elif required_ids:
        reasons.append("report has no checks array; required checks %s could not "
                       "be confirmed to execute (R22-1)" % sorted(required_ids))
    return Verdict(len(reasons) == 0, reasons, info)


def valid_invocations(invoked_ids, expected_ids):
    """R23-1: prove the scan INVOKED every registered check function.

    A report's N/A is ambiguous — it means "the check ran and nothing was
    applicable" OR "the check never ran" — so counting non-N/A results, or even
    requiring a fixture's structural subset (``required_ids``), cannot prove the
    whole registry executed. The acceptance independently records each check
    function's actual invocation (wrapping every registered func, so a function
    that legitimately returns N/A / no findings still counts as invoked); this
    verdict then requires EXACTLY the expected ids, once each. A check that was
    skipped (missing id) or called twice (duplicate) is a hard failure. Once every
    function is proven to have run, an N/A in the report is unambiguously "ran and
    nothing applicable", which closes the whole missing-execution class."""
    reasons = []
    invoked = list(invoked_ids)
    expected = sorted(expected_ids)
    counts = {}
    for i in invoked:
        counts[i] = counts.get(i, 0) + 1
    missing = [i for i in expected if counts.get(i, 0) == 0]
    extra = sorted(i for i in counts if i not in set(expected))
    dups = sorted(i for i, n in counts.items() if n > 1)
    info = {"invoked": len(invoked), "unique": len(counts),
            "expected": len(expected)}
    if missing:
        reasons.append("checks never invoked (missing from the scan): %s" % missing)
    if extra:
        reasons.append("unexpected check ids invoked: %s" % extra)
    if dups:
        reasons.append("checks invoked more than once: %s" % dups)
    return Verdict(len(reasons) == 0, reasons, info)


def _main(argv):
    import argparse
    ap = argparse.ArgumentParser(description="Certification gate verdict.")
    ap.add_argument("logfile")
    ap.add_argument("--exit-code", type=int, default=None)
    ap.add_argument("--min-total", type=int, default=1)
    ap.add_argument("--version", default=None)
    ap.add_argument("--sentinel", default="SUITE_DONE",
                    help="completion-sentinel keyword (SUITE_DONE for the suite, "
                         "ACCEPT_DONE for Windows functional acceptance)")
    ap.add_argument("--marker", default=None,
                    help="exact success marker for a non-suite proof step "
                         "(switches to require_marker mode)")
    ap.add_argument("--forbid", action="append", default=[],
                    help="a marker whose presence is a failure (repeatable); "
                         "marker mode only")
    a = ap.parse_args(argv)
    with open(a.logfile, "r", errors="replace") as fh:
        text = fh.read()

    if a.marker is not None:
        v = require_marker(text, a.marker, forbidden=a.forbid,
                           exit_code=a.exit_code)
        if v.ok:
            print("GATE PASS (marker): %r present, no crash/forbidden markers"
                  % a.marker)
            return 0
        print("GATE FAIL (marker): " + "; ".join(v.reasons))
        return 1

    v = evaluate_log(text, exit_code=a.exit_code, min_total=a.min_total,
                     expected_version=a.version, sentinel_keyword=a.sentinel)
    if v.ok:
        print("GATE PASS: %s version=%s passed=%s total=%s expected=%s"
              % (a.sentinel, v.info.get("version"), v.info.get("passed"),
                 v.info.get("total"), v.info.get("expected")))
        return 0
    print("GATE FAIL: " + "; ".join(v.reasons))
    return 1


if __name__ == "__main__":
    sys.exit(_main(sys.argv[1:]))
