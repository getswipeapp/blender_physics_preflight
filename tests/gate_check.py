"""Certification-gate verdict — shared by the macOS and Windows test gates.

A suite run earns a PASS for one Blender version ONLY if its log proves the
suite ran to completion AND every test passed. The following are each a hard
FAILURE, even when Blender exits with code 0 (it does exactly that on a Python
``SystemError``, which is how a crashed Blender 4.2.9 fluid run used to be read
as a pass):

  * no SUITE_DONE completion sentinel        -> the suite aborted/crashed
  * any recorded test FAILURE/ERROR          -> failed != 0
  * inconsistent or short test count         -> passed+failed != total, total==0,
                                                or total below an expected floor
  * a Python traceback / ViewLayer SystemError anywhere in the log
  * missing 'N passed, M failed, T total' summary line
  * a nonzero process exit code (when provided)

The whole point is that a green verdict can never rest on the process exit code
alone. ``evaluate_log`` is importable (the in-suite ``gate_selfcheck_tests``
regression calls it on crafted logs); run as a script it is the CLI the gates
invoke.

Usage:
    python gate_check.py <logfile> [--exit-code N] [--min-total N] [--version LBL]
"""
import re
import sys

SENTINEL_RE = re.compile(
    r"SUITE_DONE version=(?P<version>\S+) passed=(?P<passed>\d+) "
    r"failed=(?P<failed>\d+) total=(?P<total>\d+) "
    r"consistent=(?P<consistent>\w+) ok=(?P<ok>\w+)")

SUMMARY_RE = re.compile(r"\|\s+\d+ passed, \d+ failed, \d+ total")

# Fatal crash signatures. Verified absent from clean passing runs on
# 4.5.9 / 5.0.1 / 5.2.3, so their presence always means a real crash.
CRASH_SIGNATURES = (
    "Traceback (most recent call last)",
    "getDataPointer",
    "ViewLayer.update()> returned a result with an exception",
)


class Verdict:
    def __init__(self, ok, reasons, info):
        self.ok = ok
        self.reasons = reasons
        self.info = info


def evaluate_log(text, exit_code=None, min_total=1, expected_version=None):
    """Return a Verdict for one version's suite log. ``ok`` is True only if the
    run is a genuine, complete, all-passing suite."""
    reasons = []
    info = {}

    for sig in CRASH_SIGNATURES:
        if sig in text:
            reasons.append("crash signature present: %r" % sig)

    matches = list(SENTINEL_RE.finditer(text))
    if not matches:
        reasons.append("no SUITE_DONE completion sentinel (suite did not finish)")
        if exit_code is not None and int(exit_code) != 0:
            reasons.append("process exit code %s != 0" % exit_code)
        return Verdict(False, reasons, info)
    if len(matches) > 1:
        reasons.append("multiple SUITE_DONE sentinels (%d)" % len(matches))

    m = matches[-1]
    passed = int(m.group("passed"))
    failed = int(m.group("failed"))
    total = int(m.group("total"))
    consistent = m.group("consistent") == "yes"
    ok_flag = m.group("ok") == "yes"
    version = m.group("version")
    info.update(passed=passed, failed=failed, total=total, version=version,
                consistent=consistent, ok=ok_flag)

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
    if expected_version and version != expected_version:
        reasons.append("version mismatch: log=%s expected=%s"
                       % (version, expected_version))
    if not SUMMARY_RE.search(text):
        reasons.append("no 'N passed, M failed, T total' summary line")
    if exit_code is not None and int(exit_code) != 0:
        reasons.append("process exit code %s != 0" % exit_code)

    return Verdict(len(reasons) == 0, reasons, info)


def _main(argv):
    import argparse
    ap = argparse.ArgumentParser(description="Certification gate verdict.")
    ap.add_argument("logfile")
    ap.add_argument("--exit-code", type=int, default=None)
    ap.add_argument("--min-total", type=int, default=1)
    ap.add_argument("--version", default=None)
    a = ap.parse_args(argv)
    with open(a.logfile, "r", errors="replace") as fh:
        text = fh.read()
    v = evaluate_log(text, exit_code=a.exit_code, min_total=a.min_total,
                     expected_version=a.version)
    if v.ok:
        print("GATE PASS: version=%s passed=%s total=%s"
              % (v.info.get("version"), v.info.get("passed"),
                 v.info.get("total")))
        return 0
    print("GATE FAIL: " + "; ".join(v.reasons))
    return 1


if __name__ == "__main__":
    sys.exit(_main(sys.argv[1:]))
