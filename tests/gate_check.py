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
import os
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


def _same_file(a, b):
    """True iff paths ``a`` and ``b`` denote the SAME real file — not merely a
    matching basename (R29-1). Identity is by inode (``os.path.samefile``) when
    both exist, which is robust to path-spelling differences (Windows 8.3 short
    names, symlinks, redundant separators); otherwise it falls back to canonical
    real-path equality. Two different files that happen to share a basename
    (``/a/fix.blend`` vs ``/b/fix.blend``) are never treated as the same file."""
    if not a or not b:
        return False
    try:
        if os.path.samefile(a, b):
            return True
    except OSError:
        # One or both do not exist right now — fall back to canonical paths.
        pass
    # Canonical real-path equality, but ONLY when the resolved path actually
    # EXISTS. Two identical *nonexistent* paths resolve to the same string yet
    # prove no real file identity (R30-2): the identity of a missing/deleted file
    # cannot be established, so report False rather than a false match. (Two
    # genuinely different paths already differ here, preserving the R29-1
    # basename-is-not-enough rejection.)
    try:
        ra = os.path.realpath(str(a))
        rb = os.path.realpath(str(b))
        return ra == rb and os.path.exists(ra)
    except OSError:
        return False


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


def _norm_findings(rows):
    """Order-independent canonical form of a list of [status, object, message,
    hint] rows, for comparing a check's returned findings to the report's."""
    return sorted([["" if x is None else str(x) for x in (row or [])]
                   for row in (rows or [])])


# Severity of a FINDING status, mirroring engine.SEVERITY, for rolling a check's
# findings up to its per-check verdict (worst wins). A check with no findings is
# NOT APPLICABLE. Used to DERIVE the verdicts a truthful report must show from the
# findings the checks actually returned (R26-1).
_FINDING_SEVERITY = {"FAIL": 4, "WARNING": 3, "UNKNOWN": 2, _NA_DISPLAY: 1,
                     "PASS": 0}


def _derived_status(rows):
    """The per-check status the engine assigns from a check's findings: the worst
    finding status by severity, or NOT APPLICABLE when it returned none (mirrors
    engine.check_status)."""
    if not rows:
        return _NA_DISPLAY
    return max((("" if r[0] is None else str(r[0])) for r in rows if r),
               key=lambda s: _FINDING_SEVERITY.get(s, -1))


def _derived_overall(statuses):
    """The engine's overall verdict: the worst that actually occurred among the
    checks (NOT APPLICABLE / PASS -> PASS), mirroring build_json_report."""
    if "FAIL" in statuses:
        return "FAIL"
    if "WARNING" in statuses:
        return "WARNING"
    if "UNKNOWN" in statuses:
        return "UNKNOWN"
    return "PASS"


def valid_cli_scan(returncode, text, invoked_ids, returned_findings, expected_ids,
                   allowed_codes=(0,), child_stderr="", declared_code=_UNSET,
                   required_ids=None, report_meta=None, require_meta=False,
                   provenance=None, expected_blender=None, expected_file=None,
                   require_provenance=False, require_cache_verified=False):
    """R24-1 / R25-1: certify a CLI scan from the SAME child's report AND that
    child's OWN recorded execution evidence — never from a second, independent
    scan.

    Combines, about the one child being certified:
      * ``valid_cli_report`` — the report is a complete, valid, EXECUTED, crash-free
        Failsafe report and the real exit code is an accepted verdict (R20/R21/R22).
      * ``valid_invocations`` — THAT child invoked every registered check function
        exactly once (``invoked_ids`` are the ids the child recorded as it ran), so
        a scan that skipped checks is rejected even though the report still lists
        all 27 registry entries (R24-1).
      * result-faithfulness (R25-1) — ``returned_findings`` maps EVERY expected
        check id to the exact findings that check RETURNED inside the child, each a
        ``[status, object, message, hint]`` row. The report is only certified if
        (a) there is a recorded entry for every expected id — missing evidence is a
        hard failure, not silently skipped — AND (b) for every id the report's
        findings match those recorded rows EXACTLY (status + content, order-
        independent). So a report that dropped findings, or swapped a genuine
        UNKNOWN/FAIL for a PASS while keeping the count, is rejected — counts alone
        never proved the report tells the truth about the findings.
      * verdict-consistency (R26-1) — the report's own verdicts must agree with
        those findings: each check's top-level ``status`` must equal the worst
        finding it returned (NOT APPLICABLE when none), the ``summary`` must hold
        the exact per-status distribution, and ``overall`` must be the worst
        verdict that occurred. All are derived from the recorded findings with the
        engine's severity rules, so a report that keeps real UNKNOWN/WARNING/FAIL
        findings yet declares a rosier status, summary or overall is rejected.
      * report integrity (R27-1) — when ``report_meta`` (the registry's canonical
        {id: {display, name, group}}, recorded by the child) is given, each
        check's customer-facing ``display`` must match ``display_name(meta,
        status)`` and its name/group must match the registry, so an UNKNOWN check
        cannot show reassuring PASS-style wording and no check can be relabelled.
        Also: check ids are unique and exactly the registry set, ``schema`` is the
        known value, and ``summary`` carries no unexpected buckets.
      * metadata completeness (R28-1) — with ``require_meta`` (certification mode)
        the canonical metadata must be COMPLETE: a recorded {display,name,group}
        for every registered id and those fields present on every report check,
        so the display check can never fail open when the evidence omits metadata.
      * provenance (R28-2 / R29-1) — when ``provenance`` (the child's actual
        {blender, file}) and/or ``expected_blender`` / ``expected_file`` are
        given, the report's ``blender`` and ``file`` must match what the child
        really ran and the intended fixture, so a report cannot claim it scanned
        a different version or .blend. With ``require_provenance`` (certification
        mode) the child's provenance must be PRESENT and COMPLETE — absent
        provenance is a hard failure, never a skipped check — and the scanned
        file is matched to the intended fixture by FILE IDENTITY (same inode /
        canonical path), not by basename, so a different file that merely shares
        the fixture's name (``/evil/win fixture.blend`` vs the real
        ``/good/win fixture.blend``) is rejected.
      * cache honesty (R28-2 / R29-2 / R30-1) — ``cache_disk_usage`` totals must add
        up, AND with ``require_cache_verified`` (certification mode) the cache
        INVENTORY enumeration must have succeeded (``enumerated`` True — a failure
        reports ``enumerated: false`` with a null total, never a fabricated ``0``,
        R29-2). Size honesty is enforced on the TOTAL: a NON-NULL ``total_bytes``
        claims a verified complete figure, so it must equal the sum of the item
        byte counts, carry a ``measured: True`` attestation, and have NO unmeasured
        caches behind it — a populated cache whose size could not be read can never
        launder its unknown size into a confident number or a verified ``0``
        (R30-1). A NULL ``total_bytes`` paired with ``measured: False`` is an honest
        "some cache sizes could not be read" and is accepted (the informational
        cache size need not be knowable for the correctness scan to certify); only a
        null total dishonestly paired with ``measured: True`` is rejected. The
        ``measured``/``unmeasured`` summary fields must also AGREE with the actual
        items: ``measured: True`` with any null-byte item, or an ``unmeasured``
        count that disagrees with the number of null-byte items, is a contradictory
        report and is rejected (R31-2) — the companion at the gate to the
        cache_inspect fix that stops a partial size measurement from surfacing as a
        numeric item in the first place (R31-1).

    The invocation ids and returned findings MUST come from inside the same child
    process that wrote ``text`` (a recorder wrapped around each registered check
    function before the child ran the CLI), so this proves what happened in the
    certified scan, not a parallel one."""
    v = valid_cli_report(returncode, text, allowed_codes=allowed_codes,
                         child_stderr=child_stderr, declared_code=declared_code,
                         required_ids=required_ids)
    reasons = list(v.reasons)
    info = dict(v.info)
    vinv = valid_invocations(invoked_ids, expected_ids)
    info["invoked"] = vinv.info.get("invoked")
    info["invoked_unique"] = vinv.info.get("unique")
    reasons.extend(vinv.reasons)
    expected = sorted(expected_ids)
    # Normalise the recorded evidence (JSON object keys arrive as strings).
    ev = {}
    for k, rows in (returned_findings or {}).items():
        try:
            ev[int(k)] = rows
        except (TypeError, ValueError):
            reasons.append("non-integer check id in returned findings: %r" % (k,))
    try:
        jd = json.loads(text)
        checks = jd.get("checks") if isinstance(jd, dict) else None
    except Exception:
        checks = None
    if isinstance(checks, list):
        rep_find = {}
        for c in checks:
            if isinstance(c, dict):
                rep_find[c.get("id")] = [[f.get("status"), f.get("object"),
                                          f.get("message"), f.get("hint")]
                                         for f in (c.get("findings") or [])]
        # R25-1 (A): complete per-id evidence — a recorded return for EVERY check.
        missing_ev = [i for i in expected if i not in ev]
        info["evidence_missing"] = missing_ev
        if missing_ev:
            reasons.append("incomplete result evidence: no recorded findings for "
                           "checks %s, so the report cannot be proven to reflect "
                           "them (R25-1)" % missing_ev)
        # R25-1 (B): exact findings match (status + content), not merely counts.
        mismatched = []
        for cid in expected:
            if cid in ev and _norm_findings(ev[cid]) != _norm_findings(rep_find.get(cid, [])):
                mismatched.append(cid)
        info["findings_mismatch"] = mismatched
        if mismatched:
            reasons.append("report findings disagree with what the checks returned "
                           "inside the scan for %s (results altered or suppressed) "
                           "(R25-1)" % mismatched)
        # R26-1: the report's own VERDICTS must agree with its findings. Derive
        # each check's status, the summary distribution and the overall verdict
        # from the child's recorded findings (ground truth) using the engine's
        # severity rules, and require the report to match — so a report that keeps
        # real UNKNOWN/WARNING/FAIL findings but declares a rosier per-check
        # status, summary count or overall verdict is rejected. Only meaningful
        # with complete evidence (otherwise already rejected above).
        if not missing_ev:
            derived = {cid: _derived_status(ev.get(cid) or []) for cid in expected}
            rep_status = {c.get("id"): c.get("status") for c in checks
                          if isinstance(c, dict)}
            st_bad = [(cid, rep_status.get(cid), derived[cid]) for cid in expected
                      if rep_status.get(cid) != derived[cid]]
            info["status_mismatch"] = [b[0] for b in st_bad]
            if st_bad:
                reasons.append("report per-check status disagrees with the findings "
                               "(id,reported,derived)=%s (R26-1)" % st_bad[:8])
            exp_summary = {"FAIL": 0, "WARNING": 0, "UNKNOWN": 0, "PASS": 0,
                           _NA_DISPLAY: 0}
            for cid in expected:
                exp_summary[derived[cid]] = exp_summary.get(derived[cid], 0) + 1
            rep_summary = jd.get("summary") if isinstance(jd.get("summary"), dict) else {}
            summ_bad = {}
            for k, want in exp_summary.items():
                try:
                    got = int(rep_summary.get(k, 0))
                except (TypeError, ValueError):
                    got = None
                if got != want:
                    summ_bad[k] = (got, want)
            if summ_bad:
                reasons.append("report summary distribution disagrees with the "
                               "findings (bucket: reported,derived)=%s (R26-1)"
                               % summ_bad)
            exp_overall = _derived_overall([derived[cid] for cid in expected])
            info["overall_expected"] = exp_overall
            if jd.get("overall") != exp_overall:
                reasons.append("report overall=%r disagrees with the findings-"
                               "derived verdict %r (R26-1)"
                               % (jd.get("overall"), exp_overall))
            # R27-1: the customer-facing display and per-check metadata must match
            # the registry, and the report's shape must be well-formed. So a check
            # with a real UNKNOWN/FAIL cannot show reassuring PASS-style wording,
            # no check can be relabelled, and no duplicate/extra id or summary key
            # can smuggle a different story past the machine-verdict checks.
            ids_seen = [c.get("id") for c in checks if isinstance(c, dict)]
            dups = sorted(i for i in set(ids_seen) if ids_seen.count(i) > 1)
            if dups:
                reasons.append("report has duplicate check ids %s (R27-1)" % dups)
            if set(ids_seen) != set(expected):
                reasons.append("report check ids %s != registry %s (R27-1)"
                               % (sorted(set(ids_seen)), expected))
            if jd.get("schema") != 1:
                reasons.append("report schema=%r != expected 1 (R27-1)"
                               % jd.get("schema"))
            extra_keys = sorted(k for k in rep_summary if k not in exp_summary)
            if extra_keys:
                reasons.append("report summary has unexpected keys %s (R27-1)"
                               % extra_keys)
            # R28-1: in certification mode (``require_meta``) the canonical
            # metadata must be COMPLETE — a recorded {display,name,group} for every
            # registered id AND those fields present on every report check — so the
            # display check can never silently switch off when the evidence omits
            # metadata. Outside certification mode the check only runs on the ids
            # that WERE recorded.
            if require_meta or report_meta:
                rm = {}
                for k, val in (report_meta or {}).items():
                    try:
                        rm[int(k)] = val
                    except (TypeError, ValueError):
                        pass
                rep_by_id = {c.get("id"): c for c in checks if isinstance(c, dict)}
                meta_bad = []
                for cid in expected:
                    want = rm.get(cid)
                    c = rep_by_id.get(cid, {})
                    if not isinstance(want, dict):
                        if require_meta:
                            meta_bad.append((cid, "no canonical meta"))
                        continue
                    if require_meta and any(want.get(f) is None
                                            for f in ("display", "name", "group")):
                        meta_bad.append((cid, "incomplete canonical meta"))
                    if c.get("display") != want.get("display"):
                        meta_bad.append((cid, "display"))
                    if (require_meta or "name" in c) and c.get("name") != want.get("name"):
                        meta_bad.append((cid, "name"))
                    if (require_meta or "group" in c) and c.get("group") != want.get("group"):
                        meta_bad.append((cid, "group"))
                info["meta_mismatch"] = meta_bad[:12]
                if meta_bad:
                    reasons.append("report display/name/group is missing or disagrees "
                                   "with the registry %s (R27-1/R28-1)" % meta_bad[:8])
        # R28-2 / R29-1: report provenance — the report must not claim a different
        # Blender version or .blend file than the child actually ran. ``provenance``
        # is the child's OWN recorded {blender, file}; ``expected_*`` are what the
        # acceptance intended to scan. In certification mode (``require_provenance``)
        # provenance must be present and complete, and the scanned file is matched
        # to the fixture by FILE IDENTITY, not basename.
        rep_bl = jd.get("blender")
        rep_file = jd.get("file")
        prov = provenance or {}
        pv_bl = prov.get("blender")
        pv_file = prov.get("file")
        if require_provenance:
            if provenance is None or not pv_bl or not pv_file:
                reasons.append("child provenance absent or incomplete; cannot "
                               "certify which Blender/file actually ran (R29-1)")
            if expected_blender is None or expected_file is None:
                reasons.append("certification requires an expected blender and "
                               "fixture to anchor provenance against (R29-1)")
        if (provenance is not None or expected_blender is not None
                or expected_file is not None or require_provenance):
            if pv_bl is not None and rep_bl != pv_bl:
                reasons.append("report blender=%r != the child's actual %r (R28-2)"
                               % (rep_bl, pv_bl))
            if expected_blender is not None and rep_bl != expected_blender:
                reasons.append("report blender=%r != expected %r (R28-2)"
                               % (rep_bl, expected_blender))
            if provenance is not None and rep_file != pv_file:
                reasons.append("report file=%r != the child's actual %r (R28-2)"
                               % (rep_file, pv_file))
            if expected_file is not None:
                # Identity, not basename (R29-1): the file the child really opened
                # must be the SAME file as the intended fixture. A different file
                # that merely shares the basename is rejected.
                actual = pv_file if pv_file is not None else rep_file
                if not actual:
                    reasons.append("no scanned-file path to verify against the "
                                   "intended fixture %r (R29-1)" % expected_file)
                elif not _same_file(actual, expected_file):
                    reasons.append("child scanned %r, not the intended fixture %r "
                                   "(a matching basename is not enough) (R29-1)"
                                   % (actual, expected_file))
        # Cache honesty (R28-2 / R29-2): totals must add up, and a certified report
        # must prove the figure was actually measured (``enumerated`` True). A
        # could-not-enumerate reports ``enumerated: false`` with a null total; it is
        # never certified as a verified zero.
        cdu = jd.get("cache_disk_usage")
        if isinstance(cdu, dict):
            enumerated = cdu.get("enumerated")
            measured = cdu.get("measured")
            if require_cache_verified and enumerated is not True:
                reasons.append("cache_disk_usage not verified (enumerated=%r); a "
                               "failed/absent enumeration cannot certify as a zero "
                               "(R29-2)" % (enumerated,))
            if enumerated is not False:
                items = cdu.get("items") or []
                try:
                    # ``bytes`` is null for a cache whose size couldn't be read; it
                    # contributes to the KNOWN subtotal as unknown, not as 0.
                    s = sum(int(i["bytes"]) for i in items
                            if isinstance(i, dict) and i.get("bytes") is not None)
                    # The number of enumerated caches whose size is genuinely
                    # unknown, read straight from the items — the ground truth the
                    # summary fields must agree with (R31-2).
                    null_count = sum(1 for i in items
                                     if isinstance(i, dict) and i.get("bytes") is None)
                    unmeasured = cdu.get("unmeasured")
                    # R32-2: in certification mode the unmeasured count must be an
                    # explicit integer. The R31-2 agreement check below only fires
                    # when ``unmeasured`` is an int, so a tampered/garbled report
                    # could dodge it by dropping the field to null or a string while
                    # still carrying null-byte items — close that by requiring the
                    # summary to be stated outright whenever any items were enumerated.
                    if (require_cache_verified and items
                            and not isinstance(unmeasured, int)):
                        reasons.append("cache_disk_usage omits an integer unmeasured "
                                       "count (unmeasured=%r) while reporting %d "
                                       "item(s); certification requires an explicit "
                                       "measured/unmeasured summary (R32-2)"
                                       % (unmeasured, len(items)))
                    # R31-2: the measured/unmeasured SUMMARY fields must match the
                    # actual items. A report cannot claim measured=True while an
                    # item's byte size is null, nor state an unmeasured count that
                    # disagrees with the null-byte items. Contradictory fields are a
                    # tamper/bug signal and must never certify — this closes the
                    # cache_inspect partial-stat leak at the gate as well as at the
                    # source: were a present-but-unmeasured frame ever to surface as
                    # a numeric item, measured=True over it would be rejected here.
                    if isinstance(unmeasured, int) and unmeasured != null_count:
                        reasons.append("cache_disk_usage unmeasured=%r disagrees with "
                                       "the %d item(s) carrying a null (unread) byte "
                                       "size (R31-2)" % (unmeasured, null_count))
                    if measured is True and null_count:
                        reasons.append("cache_disk_usage claims measured=True while %d "
                                       "item(s) have an unread (null) byte size "
                                       "(R31-2)" % (null_count,))
                    if measured is False and null_count == 0 and items:
                        reasons.append("cache_disk_usage claims measured=False yet every "
                                       "one of its %d item(s) has a measured byte size "
                                       "(R31-2)" % (len(items),))
                    known = cdu.get("known_subtotal_bytes")
                    if known is not None and int(known) != s:
                        reasons.append("cache_disk_usage known_subtotal_bytes=%r != "
                                       "sum of measured items %d (R30-1)"
                                       % (known, s))
                    tot = cdu.get("total_bytes")
                    if tot is not None:
                        # A NON-NULL total_bytes claims a VERIFIED COMPLETE figure.
                        # It must add up, nothing may have gone unmeasured behind it,
                        # and (in certification mode) it must carry the measured=True
                        # attestation — so a populated-but-unmeasured scan can never
                        # launder an unknown size into a confident number or a
                        # verified ZERO (R30-1 / R28-2).
                        if int(tot) != s:
                            reasons.append("cache_disk_usage total_bytes=%r != sum of "
                                           "items %d (R28-2)" % (tot, s))
                        if unmeasured:
                            reasons.append("cache_disk_usage declares a verified "
                                           "total_bytes=%r while %r cache(s) went "
                                           "unmeasured (R30-1)" % (tot, unmeasured))
                        if require_cache_verified and measured is not True:
                            reasons.append("cache_disk_usage states a total_bytes=%r "
                                           "without a measured=True attestation "
                                           "(measured=%r) — an unverified figure "
                                           "cannot certify (R30-1)" % (tot, measured))
                    elif require_cache_verified and measured is True:
                        # Null total WITH a measured=True claim is self-contradictory:
                        # a fully-measured cache set has a real total (0 for a
                        # genuinely cache-free scene), not a null.
                        reasons.append("cache_disk_usage claims measured=True yet "
                                       "reports total_bytes=null (R30-1)")
                    # A null total with measured not True is an HONEST unknown ("some
                    # cache sizes could not be read") — it is truthfully labelled, not
                    # a false zero, so it is accepted. The correctness certification
                    # does not depend on an informational cache size being knowable.
                except (TypeError, ValueError):
                    reasons.append("cache_disk_usage has non-integer byte counts "
                                   "(R28-2)")
        elif require_cache_verified:
            reasons.append("cache_disk_usage missing; a certified report must state "
                           "a verified cache figure (R29-2)")
    elif returned_findings:
        reasons.append("report has no checks array to cross-check returned findings "
                       "(R25-1)")
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
