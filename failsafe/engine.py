# SPDX-License-Identifier: GPL-3.0-or-later
"""Check engine: result model, check registry, and the scan driver.

Design rules (from Phase 0, see repo PHASE0_REPORT.md):
  * Five statuses only: PASS / WARNING / FAIL / UNKNOWN / NOT APPLICABLE.
  * Never report a false PASS. Where Blender cannot prove a thing, report
    UNKNOWN, not PASS.
  * Read-only. No scene edits, no file writes, no network.

Every check is a plain function ``run(ctx) -> list[Result]`` registered with the
``@check(...)`` decorator. The same functions run in the GUI operator and in the
headless test harness, so they must not touch the UI.
"""


class Status:
    PASS = "PASS"
    WARNING = "WARNING"
    FAIL = "FAIL"
    UNKNOWN = "UNKNOWN"
    NA = "NOT APPLICABLE"


# User-facing wording. The INTERNAL status values above are the machine contract
# (JSON, CLI exit logic, tests) and never change. Only the words shown to a
# person are mapped here — "UNKNOWN" reads like the tool shrugged, so people see
# "Couldn't verify" instead (it means "not enough evidence to confirm", NOT
# "something is wrong"). Keep JSON/CLI on the raw Status strings.
DISPLAY_LABEL = {
    Status.PASS: "Pass",
    Status.WARNING: "Warning",
    Status.FAIL: "Fail",
    Status.UNKNOWN: "Couldn't verify",
    Status.NA: "Not applicable",
}


def label(status):
    """The user-facing word for a status (never used in JSON/CLI machine output)."""
    return DISPLAY_LABEL.get(status, status)


# Higher = more important. Used to roll per-object results up to a per-check
# status and to sort the report.
SEVERITY = {
    Status.FAIL: 4,
    Status.WARNING: 3,
    Status.UNKNOWN: 2,
    Status.NA: 1,
    Status.PASS: 0,
}

GROUP_SETUP = "Physics Setup"
GROUP_CACHE = "Simulation Caches"


class Result:
    """One finding. ``object_name`` is optional (scene-wide findings omit it)."""

    __slots__ = ("check_id", "check_name", "group", "status", "message",
                 "object_name", "hint")

    def __init__(self, check_id, check_name, group, status, message,
                 object_name=None, hint=""):
        self.check_id = check_id
        self.check_name = check_name
        self.group = group
        self.status = status
        self.message = message
        self.object_name = object_name
        self.hint = hint

    def as_dict(self):
        return {
            "check_id": self.check_id,
            "check_name": self.check_name,
            "group": self.group,
            "status": self.status,
            "message": self.message,
            "object_name": self.object_name,
            "hint": self.hint,
        }

    def __repr__(self):
        who = " [%s]" % self.object_name if self.object_name else ""
        return "<%s #%d %s%s: %s>" % (self.status, self.check_id,
                                      self.check_name, who, self.message)


# Ordered registry of (meta, func). Populated by the @check decorator at import.
CHECKS = []


class CheckMeta:
    __slots__ = ("id", "name", "group", "func",
                 "name_bad", "name_warn", "name_unknown", "name_na")

    def __init__(self, id, name, group, func, name_bad=None, name_warn=None,
                 name_unknown=None, name_na=None):
        self.id = id
        self.name = name                  # shown on PASS (positive)
        self.name_bad = name_bad          # shown on FAIL (and WARNING, unless…)
        self.name_warn = name_warn        # …a WARNING-specific headline is given
        self.name_unknown = name_unknown  # shown on UNKNOWN ("couldn't verify")
        self.name_na = name_na            # shown on NOT APPLICABLE (neutral)
        self.group = group
        self.func = func


def check(id, name, group, name_bad=None, name_warn=None, name_unknown=None,
          name_na=None):
    """Register a check function. Keeps CHECKS sorted by id.

    The display layer must never make a stronger claim than the verification. So
    each check can carry a headline per status, and ``display_name`` picks it:

      * PASS      -> ``name``        (the green positive statement)
      * FAIL      -> ``name_bad``    (a definite problem)
      * WARNING   -> ``name_warn`` if given, else ``name_bad``
      * UNKNOWN   -> ``name_unknown``  ("… couldn't be verified") — NOT the
                     positive ``name``; an unverified thing is never stated as a
                     fact, even with a blue "?" icon.
      * N/A       -> ``name_na`` if given, else ``name``

    ``name`` is always truthful for PASS; the others default sensibly so a check
    only needs to spell out the variants that would otherwise over-claim.
    """
    def deco(func):
        CHECKS.append(CheckMeta(id, name, group, func, name_bad, name_warn,
                                name_unknown, name_na))
        CHECKS.sort(key=lambda m: m.id)
        return func
    return deco


def display_name(meta, status):
    """The headline to show for a check given its (worst) status — never a
    stronger assertion than the status justifies."""
    if status == Status.FAIL:
        return meta.name_bad or meta.name
    if status == Status.WARNING:
        return meta.name_warn or meta.name_bad or meta.name
    if status == Status.UNKNOWN:
        return meta.name_unknown or meta.name
    if status == Status.NA:
        return meta.name_na or meta.name
    return meta.name


def _mk(meta):
    """Return a Result factory bound to a check's id/name/group."""
    def make(status, message, object_name=None, hint=""):
        return Result(meta.id, meta.name, meta.group, status, message,
                      object_name, hint)
    return make


class ScanContext:
    """Lightweight, stable wrapper over a Blender context for one scan.

    bpy.context does not accept arbitrary attributes, so the per-scan cache
    stash lives here. The evaluated depsgraph is captured once and reused by
    every check.
    """

    __slots__ = ("scene", "_dg", "_failsafe_caches")

    def __init__(self, context):
        self.scene = context.scene
        self._dg = context.evaluated_depsgraph_get()
        self._failsafe_caches = None

    def evaluated_depsgraph_get(self):
        return self._dg


def run_all(context):
    """Run every registered check. Returns a flat list[Result].

    A check that raises is reported as a single UNKNOWN result rather than
    aborting the whole scan — one broken check must never hide the others.
    """
    import traceback
    ctx = ScanContext(context)
    results = []
    for meta in CHECKS:
        mk = _mk(meta)
        try:
            out = meta.func(ctx, mk)
        except Exception:
            tb = traceback.format_exc()[-400:]
            out = [mk(Status.UNKNOWN,
                      "This check could not run (internal error). "
                      "Please report it.",
                      hint=tb)]
        if out:
            results.extend(out)
    return results


def check_status(results, meta):
    """Worst status among a check's results, or NA if it produced none."""
    rs = [r for r in results if r.check_id == meta.id]
    if not rs:
        return Status.NA
    return max((r.status for r in rs), key=lambda s: SEVERITY[s])


def summary_counts(results):
    counts = {Status.FAIL: 0, Status.WARNING: 0, Status.UNKNOWN: 0,
              Status.PASS: 0, Status.NA: 0}
    for m in CHECKS:
        counts[check_status(results, m)] += 1
    return counts
